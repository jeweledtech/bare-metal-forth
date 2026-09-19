# Pre-registration: fourth decoder fix, (e) the 64-bit default operand size of the stack/branch group (2026-09-18)

Written BEFORE any decoder line changes. Outcome below the line.

## Why (e) fourth, and its family

(e) precedes (d') because the (d') red also asserts the 64-bit PUSH
size. The mechanism (Intel SDM Vol 2A §2.2.1 / Vol 1 §3.6.1, "Default
64-bit operand size"): in 64-bit mode, near branches and the stack
instructions default to a 64-bit operand size WITHOUT REX.W, and the
0x66 prefix makes it 16. objdump (Binutils 2.42, x86-64) on the
hand-assembled cases, not from memory:

| bytes | objdump | today (decoder) |
|---|---|---|
| `55` | `push %rbp` | PUSH EBP (size 4) — red (e) `x64_RED_push_default_size_64` |
| `58` | `pop %rax` | size 4 |
| `41 54` / `41 5c` | `push %r12` / `pop %r12` | (d') site: reg + size |
| `66 55` | `push %bp` | PUSH EBP size 4 — **new red** `x64_RED_push_opsize_prefix_16` (0x66 ignored at that site) |
| `48 55` | `rex.W push %rbp` | size 8 by REX.W already |
| `68 78 56 34 12` / `6a 01` | `push $0x12345678` / `push $0x1` | imm size 4 |
| `ff 30` / `8f 00` | `push (%rax)` / `pop (%rax)` | FF /6 via op_size 4; `8F` is in the unknown-length path (not decoded as POP: general coverage, out of scope, recorded) |
| `ff d0` / `ff 20` | `call *%rax` / `jmp *(%rax)` | CALL EAX size 4 — **new red** `x64_RED_call_indirect_default_size_64` |
| `55` (i386) | `push %ebp` | size 4 — GUARD, must stay |

## Reads of the operand `size` field downstream (rule 24 check)

Every reader outside the decoder is a copy: `src/ir/uir.c` 120/128/133
(operand size) and 157-377 (instruction size, `uir->size =
x86->operands[n].size`); no branch on `size == 4/8/2/1` exists in
uir.c, semantic.c, or forth_codegen.c (grep). The meaning of `size`
does not change; its value changes for one instruction family. The
dump names registers by `size` (EBP vs RBP): that is how the
differential sees (e).

## The change (one family, decoder-only)

For `mode == X86_MODE_64`, a `stack_size` = 2 if the 0x66 prefix is
present, else 8, applied to: PUSH/POP r (50-5F) operand size; PUSH
imm (6A/68) operand size (the immediate stays 8/32 bits encoded,
sign-extended; only `size` changes); and, after the group-5 lookup on
FF, when the digit selected CALL, JMP, or PUSH (/2, /4, /6), the
operand's size is set to `stack_size` (the ModRM operand was decoded
with the default op_size before the digit was known). In 32/16-bit
mode nothing changes. REX.W on these forms is redundant and already
yields 8. `8F` stays out of scope.

Register-direct rm on `FF /2` (`call *%rax`) is already extended by
(k)'s `rex_b`; the size is what (e) adds, so `41 FF D0` (`call *%r8`)
becomes fully correct only with both.

## Reds (three names on the list for this fix)

- `x64_RED_push_default_size_64` (existing): `55` → size 8.
- `x64_RED_call_indirect_default_size_64` (new): `FF D0` → CALL, reg 0,
  **size 8**. Predicted first failure: `operand size: expected 8
  (64-bit default for a near indirect CALL)` (size 4 today).
- `x64_RED_push_opsize_prefix_16` (new): `66 55` → PUSH, reg 5, **size
  2**. Predicted first failure: `operand size: expected 2 (0x66 prefix
  on PUSH)` (size 4 today).
- Guard (green now, must stay): `55` in 32-bit mode → EBP, size 4.

## Gate

Run 1: fix in, three names listed → XPASS on all three; guards PASS;
pass = (60 + 1 guard) = 61, xfail = 5, xpass = 3 (tests = 69). Banked.
Run 2: three names removed → pass=64 xfail=5 fail=0 xpass=0 (tests=69).
Five remain: (a), (d'), (f), (g)×2.

## Fixture (v8, sha256 `4bc93d8efd1f756d2efa4ba8b4541a1eb994a0dfe4a440485cc09bd8c51538d5`; oracle `x64-reds-v8-oracle-2026-09-18.log`)

Baseline at the current decoder
(`operand-diff-fixture-v8-baseline-2026-09-18.log`), predicted from v7
plus the CALL: `ghidra=13 operand_ok=8 reg=4 addr=1 nostart=0` (the
CALL row: ours `R:EAX` vs Ghidra `R:RAX`, class reg).
After (e): **reg 4 → 2, operand_ok 8 → 10**: the rows `@40100f PUSH
RBP` and `@401025 CALL RAX`. `@40100d PUSH R12` stays reg (ours becomes
`R:RSP`, size right, register wrong: (d')); `@401017 MOV AL,SIL` stays
reg ((f)); addr 1, nostart 0 unchanged; boundary 13/13 unchanged.

## 14 inputs (as written 2026-09-18 morning: 8 HP + 4 modules + 2 ReactOS = 14; nmap made it 15 corpus inputs + the fixture = 16 by the time of the outcome below)

- Controls IDENTICAL (32-bit mode untouched; guard pins it).
- No figure predicted. Invariant rev 2: class addressed `reg`;
  `operand_ok` fed only from `reg` and `nostart`; `mem`/`imm`/`addr`
  must not decrease; `nostart`, `undecoded`, `mnemonic`, `opcount`
  IDENTICAL (no length change; no selector touched).
- Controls for the two halves, counted from the Ghidra dumps:
  PUSH/POP r64 sites: via-rng.ko 20, iTCO_wdt.ko 57, ne2k-pci.ko 101,
  8139too.ko 408, serial.sys 460, disk.sys 496, i8042prt.sys 672,
  HDAudBus.sys 1138, usbxhci.sys 3720, pci.sys 3850, storport.sys 4074,
  ACPI.sys 6468 → no 64-bit input with independent ground truth lacks
  them; via-rng.ko is the near-control (reg may fall by ≤ 20 + its
  near-indirect count). Near-indirect CALL/JMP sites: **all four
  modules 0** (ACPI 10, usbxhci 12, pci 7, storport 6, disk 2, i8042prt
  2, HDAudBus 1, serial 1): the modules are a genuine 64-bit CONTROL
  for the CALL/JMP half; any module row whose Ghidra mnemonic is CALL
  or JMP must not move.
- Matrix on ACPI.sys from a pre-(e) scratch decoder; must close.

## Named alternatives

- Fixture reg falls below 2: the fix leaked into (d') or (f); stop.
- A PUSH imm row's `imm` class moves: the immediate's value was
  changed, not only its size; stop.
- Any control number moves; any module CALL/JMP row moves; stop.
- `66 55` decodes size 2 but `55` still 4 after the fix: the prefix
  branch was written and the default was not; the two reds separate
  the cases on purpose.

---

**Observed before the fix (2026-09-18):** fixture v8 baseline
(`operand-diff-fixture-v8-baseline-2026-09-18.log`): `ghidra=13
operand_ok=8 reg=4 mem=0 imm=0 addr=1 nostart=0`, as predicted; the
four reg rows are PUSH R12, PUSH RBP, MOV AL,SIL, CALL RAX. Reds
(`x64-reds-e-family-red-2026-09-18.log`): first failures `operand
size: expected 8 (64-bit default for a near indirect CALL)` and
`operand size: expected 2 (0x66 prefix on PUSH)`, as predicted; guard
PASS; pass=61 xfail=8 fail=0 xpass=0 (tests=69). Eight names on the
list: (a), (d'), (e), (e2), (e3), (f), (g)×2. Awaiting review before
any line changes.

## Amendments (owner review 2026-09-18, five conditions + two framings), BEFORE any line changes

### 1. Can the differential see (e)? (rule 22)

YES for register operands, observed: the canonical form names
registers by size, and ACPI's largest rows today are exactly this
defect (`PUSH RDI` vs ours `R:EDI` ×930, `POP RDI` ×935, `PUSH R14`
×567, …, `PUSH RBP` ×284; the CALL row on the fixture reads `R:EAX` vs
`R:RAX`). So `reg 4 → 2` on the fixture and a `reg` fall on every 64-bit
input are real predictions.
**BLIND for the PUSH-immediate half:** no input contains a PUSH with a
scalar operand (ACPI: 0 Ghidra rows), and the canonical immediate for a
sole-immediate operand compares at Ghidra's ENCODED width against our
OPERAND width, so such a row could not match even where it existed.
The 68/6A part of (e) therefore has NO differential instrument; its
only evidence is the unit red `x64_RED_push_imm_default_size_64`
(6A 01 → size 8, length 2; 68 imm32 → size 8, length 5: D64 governs
the slot, never the encoded width). Stated so a null result there is
read as "unmeasured", not "unmoved".

### 2. `0xFF` is a mixed group: the rule is per digit

/0 INC and /1 DEC: normal operand size (objdump `ff 00` = `incl`).
/2 CALL near, /4 JMP near, /6 PUSH: D64. **/3 CALL far and /5 JMP far
are excluded** (objdump `ff 18` = `lcall *(%rax)`, `ff 28` = `ljmp`;
our group5 table maps both digits to the same CALL/JMP enum as the near
forms, so keying on the instruction enum would be wrong). The fix keys
on the RAW digit returned by `decode_modrm` (the selector (d) kept raw)
and sets the operand size only for digits 2, 4, 6. Guards:
`x64_GUARD_far_call_ff3_keeps_default_size` (`FF 18`, size must not
become 8), `x64_GUARD_inc_ff0_keeps_normal_size` (`FF 00` size 4),
`x64_GUARD_opsize_prefix_call_is_16` (`66 FF D0` = `call *%ax`).

### 3. The D64 set, enumerated from source, each objdump-verified

Members that reach a decoder site WITH a size field (the only ones (e)
can change): PUSH/POP r `50-5F`; PUSH imm `68`/`6A`; `FF` /2 /4 /6;
`8F` /0 (once decoded: see (m)). Members with NO size field in our
decoder (nothing for (e) to set; listed so the set is complete):
`E8` CALL rel32 / `E9` `EB` JMP rel / `70-7F` `0F 80-8F` Jcc (REL
operands, `A:` canonical); `C3`/`C2` RET (`C2` carries an imm16, size 2,
unchanged); `C9` LEAVE. Members that fall to the unknown-opcode path
today (no `case` in the one-byte switch: lines 204-830 grep): `9C`/`9D`
PUSHF/POPF, `C8` ENTER, `E0-E3` LOOP/JRCXZ; `0F A0`/`A8`/`A1`/`A9` PUSH/
POP FS/GS sit in the two-byte ModRM-less list with no operand. All are
general coverage, not (e). Exceptions verified: `CF` IRET defaults to
32 (`48 CF` = `iretq`), `CA`/`CB` far RET default 32, `06`/`0E`/`16`/`1E`/
`07`/`17`/`1F` are `(bad)` in 64-bit mode and already decode UNKNOWN
(unknown path); guard `x64_GUARD_legacy_segment_push_invalid_in_64bit`
pins `06` and `1F`.

### 4. D64 never changes the encoded width; every reader of `size` enumerated

Length invariance pre-registered as for (c): **`nostart` IDENTICAL on
every input**, and the boundary line identical. The PUSH-imm red
asserts lengths 2 and 5 explicitly. Readers of the operand `size`
field outside the decoder, from source: `src/ir/uir.c` operand copies
at 120/128/133, instruction-size copies at 157-377 (`uir->size =
x86->operands[n].size`), macro copies at 817/830/837/856/867/873/883/
890/919/925/933/939/972/987/991; constants at 194 (1), 256/262 (4),
810 (`is_64bit ? 8 : 4`), 1069 (8); `src/codegen/forth_codegen.c`
75/84 switch on a PORT size (IN/OUT width → C@-PORT etc.), unreachable
from PUSH/POP/CALL/JMP; `semantic.c` reads none. Classified: 26 copies,
5 constants, 1 port-width switch. The meaning of `size` is unchanged;
no reader branches on a stack operand's size.

### 5. Guards red-tested after the fix, and two more reds

After the fix, a scratch decoder that sets the PUSH size 8
UNCONDITIONALLY must fail `x64_GUARD_push_size_stays_4_in_32bit_mode`;
a scratch decoder that keys on the opcode (all of `FF`) must fail
`x64_GUARD_far_call_ff3_keeps_default_size` and
`x64_GUARD_inc_ff0_keeps_normal_size`. Both banked with the outcome.
New reds (objdump-verified): `x64_RED_push_rexw_redundant_64` (`48 55`
= `rex.W push %rbp`, size 8; `48 FF D0` = `rex.W call *%rax`, size 8: a
fix keyed on REX.W passes the other reds and is still wrong) and
`x64_RED_push_opsize_and_rexw_is_64` (`66 48 55` = `data16 rex.W push
%rbp`: REX.W overrides 0x66, size 8).

### Framing

- The near-indirect CALL/JMP half HAS 64-bit evidence outside the
  fixture: 41 sites across the eight HP drivers (ACPI 10, usbxhci 12,
  pci 7, storport 6, disk 2, i8042prt 2, HDAudBus 1, serial 1); the
  four modules have 0 and are the control for that half. The PUSH-imm
  half has NONE (condition 1). The PUSH/POP-register half has
  thousands.
- Fixture rows (v9, sha256
  `72217a29b992ee9fcb1495f9e420798e2bedab55e9b1eb3790ffb1e11e2faa09`,
  oracle `x64-reds-v9-oracle-2026-09-18.log`), one per red where a row
  is possible: (e) `@40100f PUSH RBP`; (e2) `@401025 CALL RAX`; (e3)
  `@401027 PUSH BP` (`66 55`); (e4) `@401029 PUSH RBP` (`48 55`); (m)
  `@40102b POP qword ptr [RAX]` (`8F 00`). NO row for
  `x64_RED_push_opsize_and_rexw_is_64` (`66 48 55`: Ghidra would render
  it as PUSH RBP identically to `48 55`, so the row could not
  discriminate) and NO row for the PUSH-imm red (condition 1). "Rows"
  is five; "reds in this fix" is six plus (m).

### (m) `8F` POP r/m: a defect found today gets its red today

`8F 00` = `pop (%rax)` (objdump), Ghidra `POP qword ptr [RAX]` len 2;
today the unknown-opcode path (UNKNOWN). Red `x64_RED_pop_rm_decoded`
asserts POP, MEM base 0, size 8. It is a decode gap, not a size
defect; it is fixed in the same commit only because its size is (e)'s
rule; its row on the fixture is `undecoded → ok`, attributable alone.

### Restated predictions

Fixture v9 baseline at the current decoder
(`operand-diff-fixture-v9-baseline-2026-09-18.log`), predicted:
`ghidra=16 operand_ok=8 reg=6 undecoded=1 addr=1 nostart=0`.
After (e)+(m): **reg 6 → 2** (PUSH RBP, CALL RAX, PUSH BP, PUSH RBP
via 48 55 all correct; PUSH R12 stays (d'), MOV AL,SIL stays (f)),
**undecoded 1 → 0**, **operand_ok 8 → 13**, addr 1 and nostart 0
unchanged, boundary 16/16 unchanged.
Gate run 1 (seven names listed: e, e2, e3, e4, e5, e6, m): XPASS on
all seven, all guards PASS; run 2 (seven removed): xfail=5, fail=0,
xpass=0; five remain: (a), (d'), (f), (g)×2.

### Correction before the fix: the v9 baseline missed my prediction, and (m)'s first failure was not the one predicted

Observed (`operand-diff-fixture-v9-baseline-2026-09-18.log`): `ghidra=16
ours=19 match=14 mid=5 nostart=2`, `operand_ok=6 reg=6 undecoded=1
addr=1`; predicted was `operand_ok=8, nostart=0, boundary 16/16`. The
undecoded `8F 00` is not only unrecognised: the unknown-opcode length
recovery consumes the wrong number of bytes for it, the walk resumes
inside `00 48 B8 …`, and both the imm64 MOV (`+2d`) and the RET (`+37`)
are never reached (5 mid-instruction starts). Consistently, red (m)'s
observed first failure (`x64-reds-e-family2-red-2026-09-18.log`) is
`length: expected 2`, not the predicted `8F /0 must decode as POP`. My
prediction assumed the recovery path consumed two bytes; it does not.
(m) is therefore a desync engine on any input where `8F` occurs, the
same shape as (b): its fix moves the boundary line as well as the
operand line. The other new reds fired on their predicted assertions;
guards green; pass=65 xfail=12 fail=0 xpass=0 (tests=77).

**Restated fixture prediction, from the observed before-line:** after
(e) and (m): reg 6 → 2 (PUSH RBP, CALL RAX, PUSH BP, PUSH RBP via
`48 55`; PUSH R12 and MOV AL,SIL stay), undecoded 1 → 0, **nostart 2 →
0** (the desync tail returns: imm64 MOV and RET), operand_ok 6 → 13,
addr 1 unchanged, boundary 16/16 with mid 0.

**Plan restated:** (e) and (m) are different mechanisms (a size rule;
a missing opcode) and land as two commits with two gate runs, each
attributable by its reds; ONE differential re-run after both, with the
fixture rows attributing per fix and the ACPI matrix closing against
the pair. For (m) the `nostart`-identical invariant is NOT expected to
hold (a length changes on every input that contains `8F`); it is
expected to hold for (e) alone and is checked on the (e) gate runs
only through the fixture (no length assertion moves).

## Outcome, fix (e) (2026-09-18, written after the gate; private commit `558240a`)

Applied as amended: `stack_size` computed once after `op_size` (8 in
64-bit mode; 2 under `0x66` without REX.W; 8 under `0x66`+REX.W; equal
to `op_size` in every other mode), applied to `50-5F`, `58-5F`, `6A`,
`68` (encoded immediate widths untouched: `read_i8`/`read_i32` as
before) and on `FF` to raw digits 2/4/6 only, after the `group_op`
lookup. No other line changed.

**Gate run 1** (`fix-e-xpass-gate-2026-09-18.log`, six names still
listed): XPASS on exactly the six (e)-family names; (m) XFAIL on
`length: expected 2`; all eleven guards PASS;
`pass=65 xfail=6 fail=0 xpass=6 (tests=77)`, exit 2 (hard failure by
design). **Gate run 2** (`fix-e-gate2-2026-09-18.log`, six names
removed): `pass=71 xfail=6 fail=0 xpass=0 (tests=77)`. Both totals
are 77; 65+6+6 = 71+6.

**(d') discharged by the gate:** `xpass` was 6, not 7.
`x64_RED_rex_b_push_r12` still fails on the register (`expected 12
(R12)`), so that red asserts the register and not only the size; (e)
did not close it silently.

**Guards red-tested** (`fix-e-guard-redtest-2026-09-18.log`), each
scratch being the real fix with one discipline removed:
- `stack_size = 8` unconditionally: FAILS
  `x64_GUARD_push_size_stays_4_in_32bit_mode`,
  `x64_GUARD_opsize_prefix_call_is_16` and the (now unlisted) red
  `x64_RED_push_opsize_prefix_16`; `pass=68 fail=3`.
- `FF` keyed on the opcode (every digit takes `stack_size`): FAILS
  `x64_GUARD_far_call_ff3_keeps_default_size` and
  `x64_GUARD_inc_ff0_keeps_normal_size`; `pass=69 fail=2`.

**Condition 1, the instrument's limit, stated for the record.** The
canonical operand form prints register names, so `RAX` versus `EAX`
is visible to `compare_operands.py` and the register half of (e)
(`50-5F`, `58-5F`, `FF /2 /4 /6` with a register or memory operand)
is measurable on the corpus. An immediate is canonicalized at the
destination's width, and `PUSH imm` (`68`/`6A`) has no destination
register: its slot size is not printed by either side. **The `68`/`6A`
half of (e) exists only in the unit suite
(`x64_RED_push_imm_default_size_64`).** On that half the corpus
*cannot* move; "did not move" would be the wrong reading. The
differential re-run after (m) is therefore evidence for the register
half and silent on the immediate half.

**`9C`/`9D` (PUSHF/POPF), asked at review:** the decoder does not
model them. The one-byte opcodes `9C`/`9D` appear nowhere in
`x86_decode_one` (the only `0x9C`/`0x9D` cases are the two-byte
`0F 9C-9F` SETcc arms); they fall to the one-byte `default:` and
decode as UNKNOWN, length 1. That length happens to be right, the
instruction is not. Their implicit 64-bit operand is therefore
neither modeled nor wrong today; they join the unknown-opcode set
that (n) below measures, and become a decode-gap red of their own if
the corpus shows them (none of the 15 inputs is known to; not
searched).

**(m) split at review.** The observed first failure of
`x64_RED_pop_rm_decoded` was length, not recognition. The mechanism:
the one-byte `default:` arm sets UNKNOWN and consumes nothing after
the opcode, so every unknown one-byte opcode reports
`length = prefixes + 1` whatever its ModRM/immediate bytes; the
two-byte `0F` path has a ModRM fallback (`decode_modrm` unless the
opcode is on a no-ModRM list), the one-byte path has none. That is a
general length-recovery defect, a desync engine on every input where
any unknown one-byte opcode occurs, same family as (b). Fixing (m)
alone would make the fixture clean and leave the engine running.
Ruling: (m) stays "POP r/m (`8F /0`) is not decoded"; **(n) is minted
today** as its own red, "unknown one-byte opcode length recovery
consumes only the opcode", measured on an opcode unknown for a reason
other than `8F`, pre-registered in
`x64-reds-n-prereg-2026-09-18.md` BEFORE the (m) fix is written.

## Outcome, fix (m) (2026-09-18, after (n) was pre-registered; private commit follows `b776e34`)

(n), (o) and (p) were pre-registered and their nine reds committed
red (`b776e34`, `x64-reds-n-red-2026-09-18.log`: `pass=71 xfail=15`)
before a line of the (m) fix was written. Fix: `case 0x8F` reads the
digit from the raw ModRM without consuming it; digit 0 decodes as POP
r/m with `stack_size`; other digits stay UNKNOWN, length 1 (as before).

**Gate run 1** (`fix-m-xpass-gate-2026-09-18.log`, name listed): XPASS
on `x64_RED_pop_rm_decoded` only; the nine (n)/(o)/(p) reds and the
five older reds XFAIL (14); new guard
`x64_GUARD_pop_rm_digit_nonzero_not_pop` PASS;
`pass=72 xfail=14 fail=0 xpass=1 (tests=87)`. **That the (n) reds
stayed red through the (m) fix is the evidence the owner asked for:
(m) did not eat (n).** **Gate run 2** (`fix-m-gate2-2026-09-18.log`,
name removed): `pass=73 xfail=14 fail=0 xpass=0 (tests=87)`.
**Guard red-test** (`fix-m-guard-redtest-2026-09-18.log`): the fix
with the digit test removed fails the guard on `8F /1 is undefined,
must not decode as POP`.

**Fixture prediction restated for v10** (the v9 prediction above
assumed the fixture ended at the imm64 row; v10 has the (n)/(o) rows
between `8F` and the imm64): rows 1-16 as predicted for (e)+(m)
(`operand_ok` 13, `reg` 2 = PUSH R12 and MOV AL,SIL, `addr` 1 = LEA
RIP, `undecoded` 0); row 17 (`63 C0`) is a matched start that is
`undecoded`; rows 18-23 are behind the first (n) desync and are NOT
predicted (they are (n)'s to move). Boundary: at least 17/23 starts
matched.

**Corpus prediction for the single re-run after (e)+(m)**
(`operand-diff-fix-e-2026-09-18.log`): `8F` occurs at no Ghidra start
on any of the 15 corpus inputs (8 HP + 4 modules + 2 ReactOS + nmap = 15; `nostart-run-attribution-2026-09-18.log`
tallies POP-triggered runs: only the fixture), so **every corpus input's
`nostart` count is identical to the (d)+(k) log**; `reg` falls on the
64-bit inputs by their PUSH/POP r and near CALL/JMP r/m rows, fed to
`operand_ok`; the three 32-bit controls are identical in every class;
the alias hash is unchanged. The ACPI transition matrix against the
pre-(e) decoder (private `3e799e8`) must close with `reg → ok` and no
row leaving `operand_ok`.

## Outcome, the single differential after (e)+(m) (`operand-diff-fix-e-2026-09-18.log`, run 2026-09-19 06:5x local, decoder = private `bf97521`)

**Run provenance.** A first launch died at input 12 of 16 (its
background subshell went down with the tool call that started it;
the partial log is not banked and its name was reused). The rerun is
one whole run: 16 `INPUT` lines and 16 `OPSUMMARY` lines (15 corpus
inputs + the fixture = 16; the 15 are 8 HP drivers + 4 modules + 2
ReactOS + nmap); its first eleven
`OPSUMMARY` lines are byte-identical to the killed attempt's. That
the subshell can die with its launching call is now a known failure
mode of this harness: completeness is checked against the log, never
inferred from the relaunch.

**Fixture v10** (`ghidra=23`): `operand_ok=11 reg=2 addr=1
undecoded=1 nostart=8`, boundary `match=15 mid=14`. My restated
prediction above said "rows 1-16, operand_ok 13"; that bookkeeping
was wrong, not the mechanism: v9's imm64 and RET rows are now rows 22
and 23, behind the (n) rows. Rows 1-14 (through `8F 00`): 11 ok
(6 + the four (e) rows + POP) , `reg` 2 (PUSH R12 = (d'), MOV AL,SIL
= (f)), `addr` 1 (LEA RIP = (a)); row 15 `63 C0` matched start,
`undecoded`; rows 16-23 all `nostart` behind the first (n) desync.
Exactly the predicted classes once the rows are counted right.

**Corpus, before ((d)+(k) log) → after:**

| input | operand_ok | score | reg | nostart | every other class |
|---|---|---|---|---|---|
| ACPI.sys | 118915 → 122231 | 79.9 → 82.1 | 9589 → 6272 | 190 → **191** | identical |
| disk.sys | 9853 → 10081 | 79.9 → 81.7 | 747 → 519 | 11 | identical |
| HDAudBus.sys | 18103 → 18694 | 74.8 → 77.2 | 1888 → 1297 | 50 | identical |
| i8042prt.sys | 14077 → 14373 | 73.7 → 75.3 | 1508 → 1212 | 8 | identical |
| pci.sys | 70832 → 73087 | 81.6 → 84.2 | 5585 → 3330 | 49 | identical |
| serial.sys | 11336 → 11609 | 81.8 → 83.8 | 772 → 499 | 32 | identical |
| storport.sys | 82687 → 85041 | 84.2 → 86.6 | 5500 → 3146 | 192 | identical |
| usbxhci.sys | 70399 → 72503 | 78.9 → 81.3 | 6232 → 4128 | 177 | identical |
| ne2k-pci.ko | 841 → 889 | 70.5 → 74.5 | 99 → 51 | 13 | identical |
| 8139too.ko | 2588 → 2758 | 64.3 → 68.5 | 432 → 262 | 11 | identical |
| iTCO_wdt.ko | 652 → 690 | 71.9 → 76.1 | 59 → 21 | 8 | identical |
| via-rng.ko | 118 → 126 | 67.0 → 71.6 | 19 → 11 | 0 | identical |
| serial.sys (ReactOS) | 4215 | 99.9 | 0 | 0 | identical |
| beep.sys (ReactOS) | 447 | 100.0 | 0 | 0 | identical |
| nmap_service.exe | 7885 | 95.0 | 0 | 145 | identical |

Alias hash `02101788edd2` on every line. Controls identical in every
class. `nostart` identical on every input except ACPI (+1) and the
fixture (v8 → v10, not comparable). 64-bit inputs now 68.5% to 86.6%
operand-correct (after (d)+(k): 64.3% to 84.2%; baseline 46.7% to
66.4%).

**ACPI matrix** (`fix-e-matrix-acpi-2026-09-18.log`, pre = `3e799e8`
dump, post = `bf97521` dump, same Ghidra file): `reg → ok` 3317; every
other class diagonal; **`ok → nostart` 1** (`.text+0x69d4c`). No other
row left `operand_ok`; no class increased from anything but `reg`.

**The one row, read from bytes** (`fix-em-acpi-69d4c-window-2026-09-18.log`).
The invariant "no instruction leaves `operand_ok`" is violated by one
row and the read settles why. At +69d3d the real instruction is `4c
63 c0` MOVSXD R8,EAX; the decoder returns UNKNOWN length 2 (defect
(n)), so the walk is inside the bytes of the following real
instructions. Pre-(m) it stepped `ac` (len 1), `8f` (len 1), `00 00`
(ADD, len 2) and re-synced by chance at +69d4c, where MOV RAX,[RBX+0x58]
was operand-correct **by accident**. Post-(m), `8f 00`, the second and
third displacement bytes of `4c 8d 15 ac 8f 00 00` LEA R10,[rip+0x8fac],
decode as POP [RAX] (length 2), the walk re-syncs at +69d50 instead,
and +69d4c is `nostart`. (m)'s digit guard is not under-tight: `8f 00`
is a valid POP encoding wherever a walker lands on it; no correct
decoder could do otherwise. **This is the invariant's first recorded
exception, with its mechanism: a row inside a desync run can be
operand-correct only by accident, and any length change in the garbage
walk, correct or not, can move the re-sync point either way.** The row
belongs to (n) (MOVSXD trigger, the largest class in
`nostart-run-attribution-2026-09-18.log`) and is predicted to return
to `operand_ok` when (n) fixes the `63` length. The invariant is
restated: it holds for rows outside desync runs; inside a run it
cannot be asserted at all.

**Scope of the attribution script's counting bug, for the record.**
The bug (counting Ghidra starts in sections our dump does not emit)
lives only in `nostart-run-attribution-2026-09-18.log`, written today.
Every earlier `nostart` figure in this arc came from
`compare_operands.py`'s `OPSUMMARY`/`OPD` lines, which iterate only
sections present on both sides (`for sec in ob: if sec not in gb:
continue`), so the (b), (c) and (d)+(k) "nostart identical" claims and
their tables are untouched. The per-instruction matrices ((b) and
today's) skip sections absent on our side; a section absent on both
before and after could only contribute `nostart → nostart`, never a
claimed transition. Today's matrix script is the one in
`fix-e-matrix-acpi-2026-09-18.log`'s header and does the skip
explicitly. No previously recorded figure changes.
