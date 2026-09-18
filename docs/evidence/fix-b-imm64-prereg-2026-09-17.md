# Pre-registration: FIRST decoder fix, (b) REX.W B8+r reads imm64 (2026-09-17)

Written BEFORE any decoder line changes. The first fix is the first
time a number moves on purpose (owner, 2026-09-15): the check is not
whether it moved but whether it moved by exactly the amount the
fixture predicts for this one defect, with nothing else moving.
Outcome below the line.

## Why (b) first

Of the nine XFAIL names, (b) is the only one that changes an
instruction LENGTH, so it is the only one the boundary harness can see
and the one whose misread desyncs everything after it (2026-09-14: 13
of usbxhci.sys's 16 phantom INS/OUTS sat inside a 10-byte imm64 MOV).
Blast radius: `x86_decoder.c` alone (the lifter copies `imm` as int64;
`length` is what the range loop advances by). No semantic.c change.

## The change (one site)

`src/decoders/x86_decoder.c` case 0xB8..0xBF (line ~581): when
`op_size == 8` (REX.W present) read eight bytes: low `read_u32`, high
`read_u32`, `imm = low | (high << 32)`; length becomes 10. No REX.W:
unchanged (`read_u32`, length 5). `op_size == 2`: unchanged. The
bounds check for the extra bytes is red (g)'s job, not this fix's;
this fix does not touch it.

## Gate on the red itself (the XPASS mechanism, exercised for real)

Run 1: fix applied, `xfail_names` UNCHANGED → `make test-x86` must
exit 1 with `XPASS: x64_RED_mov_rax_imm64_len10` and a HARD FAILURE
line, `pass=48 xfail=8 fail=0 xpass=1`. This is the gate working as
built; it is banked, not skipped.
Run 2: the one name removed from `xfail_names` → `pass=49 xfail=8
fail=0 xpass=0 (tests=57)`, exit 0. All other reds stay red.

## Fixture prediction (tests/data/x64_reds/x64_reds.elf v4, 9 Ghidra instructions)

Baseline line (operand-diff-2026-09-15.log, appended v4 run):
`ghidra=9 operand_ok=1 nostart=1 reg=4 mem=1 imm=1 addr=1`.
After (b): **operand_ok 1 → 3, imm 1 → 0, nostart 1 → 0**; reg 4, mem 1,
addr 1 UNCHANGED. Two rows move, not one, and that is the prediction:
the imm64 instruction itself becomes operand-correct, and the trailing
RET, which was `nostart` only because the 4-byte under-read desynced
into the immediate, is reached again. Any change to reg/mem/addr on
the fixture = a fix that leaked into another defect: stop.
Boundary line for the fixture: `mid` 2 → 0.

## 14-input prediction (equal alias hash 02101788edd2…; re-run
`make differential-all DIFF_LOG=../../docs/evidence/operand-diff-fix-b-2026-09-17.log`)

- Controls (PE32 serial.sys, beep.sys, nmap_service.exe): every number
  IDENTICAL (B8 without REX.W is untouched).
- 64-bit inputs: `imm` decreases by the number of imm64 MOVs on agreed
  starts; `nostart`, `undecoded`, `mnemonic`, `opcount` decrease
  (desync-born junk after each imm64); `reg`/`mem`/`addr` may decrease
  (junk decodes in those classes disappear) but MUST NOT increase;
  `operand_ok` increases on every 64-bit input. Boundary harness: `mid`
  decreases on every 64-bit input, `coverage` rises toward 100%.
- No prediction of magnitudes beyond the fixture; the point is the
  direction and the controls' invariance.

## Named alternatives

- Fixture `nostart` stays 1: RET still not reached → something after
  the imm64 still desyncs (the fix is incomplete or another length
  defect sits between); stop.
- Any control number moves: the change touched a non-REX.W path; stop.
- Any class INCREASES on a 64-bit input: an imm64 read is landing on
  bytes that used to be (accidentally) decodable; investigate before
  quoting.

---
