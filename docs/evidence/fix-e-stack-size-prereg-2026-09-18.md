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

## 14 inputs

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
