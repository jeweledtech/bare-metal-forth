# Pre-registration: third decoder fix, (d) REX.R on the ModRM reg field + (k) REX.B on the register-direct rm (2026-09-18)

Written BEFORE any decoder line changes. Outcome below the line.

## Why (d)+(k) third, together

Both live in `decode_modrm`, each on its own output line: (d) the
`*reg_out` value (REX.R, bit 2); (k) `rm_op->reg` when mod = 3 (REX.B,
bit 0). Neither has an escape case (Intel SDM Vol 2A §2.2.1.2: REX.R
and REX.B simply add bit 3 to the 3-bit field; the only REX special
cases are the SIB ones handled by (c) and the byte-register file (f)).
No length changes. One commit, two names, each with its own oracle
line and its own fixture row.

Out of scope, explicitly: opcode-embedded registers (d') live in the
PUSH/POP/B8/XCHG paths, not in `decode_modrm`, and (d') also asserts
the 64-bit PUSH size, so (e) precedes it. The byte-register file (f)
is a naming decision ((16..19) numbering) with its own red. (a) is
untouched. The reg field's byte-register naming under REX (DIL vs BH
in the fix-(c) example) stays (f)'s.

## The change (two lines in one function)

`decode_modrm`: `if (reg_out) *reg_out = reg | ((dec->rex & 4) ? 8 : 0);`
and, in the `mod == 3` branch, `rm_op->reg = rm | rex_b;` using the
`rex_b` already computed by (c). `dec->rex` is 0 in 32-bit mode and
cleared per instruction (guarded).

## Gate

Run 1: fix in, names listed → XPASS on `x64_RED_rex_r_reg_field_r8`
AND `x64_RED_rex_b_rm_register_r8`; pass=53 xfail=6 fail=0 xpass=2
(tests=61); the leak guard stays PASS. Banked.
Run 2: both names removed → pass=55 xfail=6 fail=0 xpass=0. Six
remain: (a), (d'), (e), (f), (g)×2.

## Fixture prediction (v7 baseline at the post-(c) decoder: `ghidra=12 operand_ok=6 reg=5 mem=0 addr=1 nostart=0`)

After (d)+(k): **reg 5 → 3, operand_ok 6 → 8**; addr 1, nostart 0
UNCHANGED; boundary 12/12 unchanged. The two instructions: `MOV R8,RAX`
(@40100a, (d)) and `MOV RAX,R8` (@401022, (k)). The three remaining
`reg` rows are `PUSH R12` (d'), `PUSH RBP` (e), `MOV AL,SIL` (f).

## 14 inputs

- Controls IDENTICAL (no REX in 32-bit mode).
- No figure predicted for the eight drivers and four modules.
- Invariant rev 2: no instruction leaves `operand_ok`; every class
  increase is fed only from `nostart` or from the class this fix
  addresses (`reg`). `nostart` IDENTICAL everywhere (no length change).
- 64-bit control: an input with zero r8-r15 REGISTER operands would be
  one. Counted from the Ghidra dumps: via-rng.ko 25, iTCO_wdt.ko 72,
  ne2k-pci.ko 245, 8139too.ko 930, disk.sys 2461, serial.sys 2932,
  i8042prt.sys 4182, HDAudBus.sys 5426, pci.sys 17385, usbxhci.sys
  17614, storport.sys 19003, ACPI.sys 31044; PE32 controls 0. **No
  64-bit control exists.** Those counts include (d') opcode-embedded
  sites (Ghidra's text cannot separate encodings), so `reg` will NOT
  fall to 0: the residue after this fix is (d') + (e) + (f) sites. The
  near-control is via-rng.ko (25 sites): its `reg` may fall by at most
  25 and nothing else there may move.
- Matrix on ACPI.sys after the run, from a pre-fix scratch decoder
  (the private head at that moment), and it must close.

## Named alternatives

- Fixture `addr` or `nostart` moves: leak into another path; stop.
- Any control number moves; stop.
- Fixture `reg` falls below 3 or above 3: a fix touched (d')/(e)/(f)
  or missed one of its two instructions; stop.
- An instruction leaves `operand_ok` anywhere: REX.R applied where the
  field was not a register (e.g. a group opcode using reg as an
  extension index: the group tables index by the RAW reg, and the fix
  must keep passing the raw value to those lookups; predicted first
  place this would show is `undecoded`/`mnemonic` rising). This is the
  load-bearing alternative: `decode_modrm`'s `reg_out` is used both as
  a register number AND as the /digit group selector (0x80-0x83, 0xC0/
  0xC1, 0xF6/0xF7, 0xFE/0xFF, 0x0F 0xBA...). REX.R must NOT be applied
  to the group selector. The fix therefore extends the value at the
  REGISTER-operand sites, not inside `decode_modrm`'s `*reg_out`, OR
  `decode_modrm` returns both the raw and the extended value. Decided
  before the line changes: **the group lookups keep the raw field**;
  the differential's `undecoded`/`mnemonic`/`opcount` classes must be
  IDENTICAL after the fix, and that is the check.

---

## Amendments (owner review 2026-09-18, four conditions + two wordings), BEFORE any line changes

Note on the review: the reviewed text was the quoted claim; the file
was on origin/master at cfc3607 under THIS name
(`fix-dk-rexr-reg-prereg-2026-09-18.md`); the 404 was a guessed name.

### 1. Every reader of the ModRM reg value, enumerated from source (not from a list)

`grep`/`awk` over `src/decoders/x86_decoder.c` at the post-(c) revision:
**44 `decode_modrm(..., &reg, ...)` call sites.** Classified by the
first use of `reg` after each call:

| class | sites (line numbers) | what `reg` means there |
|---|---|---|
| OPERAND REGISTER (must be extended by REX.R) | 341, 347, 426, 435, 447, 458, 467, 476, 485, 496, 957, 966, 977, 986, 997, 1017 (**16** sites, all of the form `out->operands[n].reg = reg;`) | the register in the reg field |
| OPCODE EXTENSION (must stay RAW; a group table or a digit test) | Group 1 `80/81/83` → `group1_ops[reg]` at 284, 293, 302; shift `C0/C1` and `D0-D3` → `shift_ops[reg]` at 614, 624, 684, 699; Group 3 `F6/F7` → `group3_ops[reg]` at 852, 865; `FE` → `reg == 0 ? INC : DEC` at 889; Group 5 `FF` → `group5_ops[reg]` at 897 (**11** sites) | /digit selector |
| IGNORED (reg consumed by `decode_modrm`, never read) | `C6/C7` (Group 11, MOV /0 only; other digits not refused today: recorded, out of scope), 0F two-byte forms at 949, 1006, 1032, 1038, 1045, 1050, 1056, 1060, 1102, 1108, 1115, 1125, 1135, 1163, 1194 (NOP/imm8 catch-alls: the `mnemonic` class's SSE/CMOV/BT residue) (**17** sites) | nothing |

Families from the reviewer's list and where they are today: `D0-D3`
are in the shift sites above; `8F` /0, `0F 00/01` (Groups 6/7), `0F 18`,
`0F AE` (Group 15), `0F C7` (Group 9), and the x87 escapes `D8-DF` are
handled in the unknown-opcode LENGTH recovery path (lines 928-1157:
ModRM consumed for length only, instruction UNKNOWN or NOP): `reg` is
never read as a selector there, so REX.R cannot reach a table. `82`
falls into the same recovery path (line 928) and decodes UNKNOWN, not
through Group 1: it is refused today; the guard below pins that.
Corpus check: no input carries RDRAND/RDSEED/CMPXCHG16B or Group 15
(Ghidra dumps, grep), so nothing in the differential exercises Groups
9/15; the guards are the only evidence for those paths and they are
hand-assembled.

**The fix therefore does NOT extend `*reg_out` inside `decode_modrm`.**
It extends at the 16 operand-register sites via one helper
`reg_ext(dec, reg) = reg | (REX.R ? 8 : 0)`, and the 11 selector sites
keep the raw value.

### 2. Hand-assembled guards (green today; red-tested after the fix against a NAIVE scratch fix that extends `*reg_out`)

Verified with `objdump -D -b binary -m i386:x86-64` (GNU Binutils
2.42), not from memory:

| bytes | objdump | guard asserts |
|---|---|---|
| `44 F7 D8` | `rex.R neg %eax` | NEG, operand REG 0 size 4 (REX.R ignored on a Group 3 digit) |
| `4C F7 D8` | `rex.WR neg %rax` | NEG, REG 0 size 8 |
| `44 FF D0` | `rex.R call *%rax` | CALL, REG 0 (Group 5 digit) |
| `44 80 C0 01` | `rex.R add $0x1,%al` | ADD, REG 0 size 1, imm 1 (Group 1 digit) |
| `82 C0 01` | `(bad)` | NOT decoded as an ALU op in 64-bit mode (UNKNOWN or refused) |
| `4C 8B C0` | `mov %rax,%r8` | (d)'s red: dest reg 8 |
| `49 8B C0` | `mov %r8,%rax` | (k)'s red: source reg 8 |

The naive scratch fix must FAIL the first four guards (a digit read as
11, 10, 8 → wrong mnemonic or an out-of-range table index) and the
real fix must pass all of them. Both runs banked.

### 3. Range check at the group tables

Every table lookup goes through `group_op(table, raw)` which refuses
(`X86_INS_UNKNOWN`) when `raw > 7` instead of reading past an
eight-entry table. Unreachable with the raw field by construction; it
exists so a future change that extends the wrong value fails loudly
rather than returning a plausible mnemonic (nineteenth rule).

### 4. Fixture rows, one per fix

- (d) REX.R reg field: `@40100a` `MOV R8,RAX` (`4C 8B C0`): ours today
  `R:RAX R:RAX`, after `R:R8 R:RAX`.
- (k) REX.B register rm: `@401022` `MOV RAX,R8` (`49 8B C0`): ours
  today `R:RAX R:RAX`, after `R:RAX R:R8`.
Each row's class is `reg` in the v7 baseline (both lines read `reg` in
`operand-diff-fixture-v7-baseline-2026-09-18.log`), so (k)'s class is
confirmed `reg`, not `mnemonic`. reg 5 → 3 closes only if BOTH move.

### Wording amendments

- "No 64-bit control exists" means precisely: there is no 64-bit input
  with independent ground truth that contains zero sites of this fix's
  mechanism. via-rng.ko IS 64-bit; it is a near-control because it has
  25 such sites, not because it lacks them.
- (f) reads the EXTENDED value: after (d), the byte-register file test
  is "size 1, any REX present (including a lone REX.R), reg in 4..7 →
  SPL/BPL/SIL/DIL; reg 12..15 → R12B..R15B, never SPL". (f) is built on
  the value (d) leaves, not the raw field.

### Invariant for this fix (owner)

Class addressed: `reg`. `operand_ok` may be fed only from `reg` and
`nostart`. `mem`, `addr`, `imm` must NOT decrease (nothing here makes
one of those correct); they may increase only by first-mismatch
exposure fed from `reg`. `undecoded`, `mnemonic`, `opcount` IDENTICAL
(the selector separation; vacuous on this corpus, hence the guards).

---

## Outcome (appended after the runs, 2026-09-18)

**Guards on HEAD** (`fix-dk-guards-green-on-head-2026-09-18.log`): the
five new guards green by construction (raw field feeds the tables);
pass=58 xfail=8 fail=0 xpass=0 (tests=66).
**Guards red-tested against the NAIVE fix**
(`fix-dk-guards-redtest-naive-2026-09-18.log`, a scratch decoder that
extends `*reg_out` inside `decode_modrm`): the four group guards FAIL
(`digit 3 must select NEG`, `digit 2 must select CALL`, `digit 0 must
select ADD`) and (d) XPASSes, as predicted. The guards have teeth.

**The real fix:** `reg_ext(dec, reg)` at the 16 operand-register sites
(count asserted by the patch), `rm | rex_b` in the mod-3 branch (k),
and every group table read through `group_op(table, raw)` which
refuses `raw > 7` (10 sites, count asserted). `*reg_out` stays raw.

**Gate run 1** (`fix-dk-xpass-gate-2026-09-18.log`): XPASS on (d) AND
(k), all six guards PASS, pass=58 xfail=6 fail=0 xpass=2, HARD FAILURE.
**Gate run 2** (`fix-dk-green-2026-09-18.log`): names removed →
pass=60 xfail=6 fail=0 xpass=0 (tests=66) (the pre-reg's 55 predates
the five guards: 55 + 5). Chain 23 suites green. Six reds remain:
(a), (d'), (e), (f), (g) imm32, (g) disp32.

**Fixture** (`operand-diff-fix-dk-2026-09-18.log`, alias hash equal):
operand_ok 6 → **8**, reg 5 → **3**, addr 1, nostart 0 UNCHANGED,
boundary 12/12. The two rows: `@40100a MOV R8,RAX` (d) and `@401022
MOV RAX,R8` (k). Remaining reg rows: PUSH R12 (d'), PUSH RBP (e),
MOV AL,SIL (f).

**Controls**: ReactOS serial.sys 4215/4220, beep.sys 447/447,
nmap_service.exe 7885/8299: identical. **Near-control** via-rng.ko:
reg 30 → 19 (−11 ≤ 25 sites), operand_ok 107 → 118, everything else
identical.

**Selector separation, the vacuous-on-corpus check:** `undecoded`,
`mnemonic`, `opcount` IDENTICAL on all 15 inputs (e.g. ACPI 988 / 3277
/ 3352, storport 425 / 2324 / 2053, usbxhci 588 / 1697 / 1309). The
guards are the non-vacuous evidence; this is the corroboration.

**14 inputs, measured:**

| input | operand_ok (post-c → post-dk) | score | reg | addr | mem / imm / nostart |
|---|---|---|---|---|---|
| ACPI.sys | 99023 → 118915 | 66.5 → 79.9 | 30479 → 9589 | 11612 → 12610 | identical |
| disk.sys | 8332 → 9853 | 67.5 → 79.9 | 2457 → 747 | 835 → 1024 | identical |
| HDAudBus.sys | 14895 → 18103 | 61.5 → 74.8 | 5412 → 1888 | 2854 → 3170 | identical |
| i8042prt.sys | 11723 → 14077 | 61.4 → 73.7 | 4055 → 1508 | 2497 → 2690 | identical |
| pci.sys | 58953 → 70832 | 67.9 → 81.6 | 17752 → 5585 | 5031 → 5319 | identical |
| serial.sys (hp) | 9146 → 11336 | 66.0 → 81.8 | 3016 → 772 | 880 → 934 | identical |
| storport.sys | 69567 → 82687 | 70.8 → 84.2 | 19060 → 5500 | 4607 → 5047 | identical |
| usbxhci.sys | 59552 → 70399 | 66.7 → 78.9 | 18153 → 6232 | 7758 → 8832 | identical |
| ne2k-pci.ko | 677 → 841 | 56.7 → 70.5 | 263 → 99 | 184 → 184 | identical |
| 8139too.ko | 2019 → 2588 | 50.1 → 64.3 | 1008 → 432 | 806 → 810 | mem 17 → 20 (fed from reg), imm/nostart identical |
| iTCO_wdt.ko | 604 → 652 | 66.6 → 71.9 | 108 → 59 | 157 → 158 | identical |
| via-rng.ko | 107 → 118 | 60.8 → 67.0 | 30 → 19 | 33 → 33 | identical |

**Matrix on ACPI.sys (pre-(d) decoder rebuilt from the private head),
and it CLOSES:** reg→ok 19892, reg→addr 998, unchanged 128031,
**instructions that left operand_ok: 0**; residual zero on all ten
classes. The 998 are first-mismatch exposure: e.g. `.text+c3c` `LEA
R9,[0x1c00296b0]`, before `R:RCX A:0x27a6d` (class reg), after `R:R9
A:0x27a6d` (class addr: defect (a), the RIP-relative operand behind a
now-correct register). Invariant rev 2 held: `operand_ok` fed only
from `reg`; `mem`/`imm` did not decrease; increases (`addr`, 8139too's
`mem`) fed from `reg`.

**Scores after three fixes:** 64-bit inputs 64.3% to 84.2%
operand-correct (baseline 46.7% to 66.4%); controls unchanged. The
`reg` residue is (d') + (e) + (f); the `addr` class is now the largest
loss and is (a).
