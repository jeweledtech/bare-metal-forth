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
