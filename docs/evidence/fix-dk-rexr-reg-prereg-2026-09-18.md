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
