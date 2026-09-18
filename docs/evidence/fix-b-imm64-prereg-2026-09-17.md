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
- **No figure is predicted for the eight drivers and four modules**,
  exactly as the baseline run predicted none. Whatever comes out is a
  measurement, not "the expected improvement": this is the first fix,
  and that framing would set the habit.

## Two claims, kept apart (owner, 2026-09-18)

- The FIXTURE attributes: two rows move, attributable to (b) alone,
  checkable by hand against the oracle log.
- The 14 INPUTS only measure: their scores move by some amount
  attributable to nothing in particular (every imm64 site's downstream
  desync junk disappears along with the site itself). Week 3's
  comparison table against 09-15 must carry this sentence, or it will
  be read as per-defect attribution.

## 64-bit control for this fix: NONE EXISTS (checked before the run, owner point 3)

The PE32 controls never reach a REX.W path, so their invariance proves
only that 32-bit decoding is untouched. A 64-bit control would be an
input with ZERO `MOV r64, imm64` sites. Counted from the banked Ghidra
dumps (a MOV with a 64-bit register destination and a 64-bit scalar):

| input | imm64 MOV sites |
|---|---:|
| via-rng.ko | 1 |
| iTCO_wdt.ko | 1 |
| serial.sys (hp_i3) | 3 |
| ne2k-pci.ko | 4 |
| HDAudBus.sys | 4 |
| disk.sys | 6 |
| 8139too.ko | 7 |
| i8042prt.sys | 17 |
| usbxhci.sys | 91 |
| pci.sys | 150 |
| storport.sys | 159 |
| ACPI.sys | 1039 |
| fixture v4 | 1 |

**No 64-bit input has zero sites; this fix has no 64-bit control.**
Recorded as such. The nearest substitutes are the two single-site
modules: their scores may move only by what one site and its desync
tail account for (a handful of instructions, not tens); a large move
on via-rng.ko or iTCO_wdt.ko means the change touched more than the
B8+r path. Per-input bound, stated now: the `imm` class can decrease
by at most the site count above.

## Named alternatives

- Fixture `nostart` stays 1: RET still not reached → something after
  the imm64 still desyncs (the fix is incomplete or another length
  defect sits between); stop.
- Any control number moves: the change touched a non-REX.W path; stop.
- Any class INCREASES on a 64-bit input: an imm64 read is landing on
  bytes that used to be (accidentally) decodable; investigate before
  quoting.

---

## Outcome (appended after the runs, 2026-09-18)

**Gate run 1** (`fix-b-imm64-xpass-gate-2026-09-18.log`): fix in, name
listed → `XPASS: x64_RED_mov_rax_imm64_len10`, HARD FAILURE line,
pass=48 xfail=8 fail=0 xpass=1, exit nonzero. The gate fired as built.
**Gate run 2** (`fix-b-imm64-green-2026-09-18.log`): name removed →
pass=49 xfail=8 fail=0 xpass=0 (tests=57), exit 0. Eight reds remain.

**Fixture** (`operand-diff-fix-b-2026-09-18.log`, alias_sha256
02101788edd2… equal to baseline): operand_ok 1 → **3**, imm 1 → **0**,
nostart 1 → **0**, reg 4, mem 1, addr 1 UNCHANGED; boundary mid 2 → 0,
agree 100%. Exactly the prediction, two rows, RET reached again.

**Controls**: ReactOS serial.sys 4215/4220, beep.sys 447/447,
nmap_service.exe 7885/8299: every number IDENTICAL to baseline.

**Near-controls** (one imm64 site each): via-rng.ko operand_ok 104 →
105, iTCO_wdt.ko 592 → 594. Within what one site and its shadow allow.

**14 inputs, measured (attributable to nothing in particular):**

| input | operand_ok before → after | score | imm | nostart | reg | addr | mem |
|---|---|---|---|---|---|---|---|
| ACPI.sys | 92933 → 94198 | 62.4 → 63.3 | 646 → 0 | 1247 → 190 | 29893 → 30222 | 11529 → 11612 | 5064 → 5081 |
| disk.sys | 7733 → 7744 | 62.7 → 62.8 | 5 → 0 | 19 → 11 | 2354 → 2354 | 834 → 835 | 690 → 691 |
| HDAudBus.sys | 14246 → 14253 | 58.8 → 58.9 | 3 → 0 | 56 → 50 | 5362 → 5362 | 2852 → 2854 | 691 → 691 |
| i8042prt.sys | 10947 → 10985 | 57.3 → 57.5 | 16 → 0 | 37 → 8 | 3999 → 4000 | 2492 → 2497 | 792 → 793 |
| pci.sys | 55919 → 56114 | 64.4 → 64.6 | 134 → 0 | 127 → 49 | 17535 → 17544 | 5026 → 5031 | 3044 → 3047 |
| serial.sys (hp) | 8730 → 8738 | 63.0 → 63.1 | 2 → 0 | 39 → 32 | 2961 → 2961 | 879 → 880 | 463 → 463 |
| storport.sys | 65179 → 65523 | 66.4 → 66.7 | 133 → 0 | 446 → 192 | 18679 → 18702 | 4603 → 4607 | 4395 → 4402 |
| usbxhci.sys | 55767 → 55902 | 62.5 → 62.6 | 76 → 0 | 274 → 177 | 17979 → 17997 | 7751 → 7758 | 3795 → 3806 |
| ne2k-pci.ko | 617 → 622 | 51.7 → 52.1 | 32 → 28 | 15 → 13 | 259 → 260 | 184 → 184 | 67 → 67 |
| 8139too.ko | 1881 → 1893 | 46.7 → 47.0 | 113 → 109 | 20 → 11 | 1003 → 1004 | 806 → 806 | 147 → 147 |
| iTCO_wdt.ko | 592 → 594 | 65.3 → 65.5 | 22 → 23 | 12 → 8 | 107 → 108 | 157 → 157 | 10 → 10 |
| via-rng.ko | 104 → 105 | 59.1 → 59.7 | 4 → 3 | 0 → 0 | 30 → 30 | 33 → 33 | 2 → 2 |

**Named alternative fired and resolved by observation:** reg/addr/mem/
mnemonic INCREASED on the HP drivers. Transition matrix on ACPI.sys
(pre-fix decoder rebuilt from a scratch copy with the hunk reverted,
dumps compared per Ghidra instruction): imm→ok 646, nostart→ok 619,
nostart→reg 329, nostart→addr 83, nostart→mem 17, nostart→mnemonic 8,
nostart→undecoded 1, unchanged 147218, **instructions that left
operand_ok: 0**. Every newly reached instruction lies 1..44 bytes
after an imm64 site (median 13). The increases are instructions that
were hidden in the desync shadow and now show the REMAINING defects.
The prediction "no class may increase" was wrong as stated; the
correct invariant, now recorded for the next fix: no instruction moves
OUT of operand_ok, and every class increase is fed only from nostart.
The modules' residual `imm` (28/109/23/3) is not imm64 (relocation-
zeroed immediates against Ghidra's relocated values, to be measured
separately); iTCO's imm 22 → 23 is one newly reached instruction.

**FINDING, ruling owed:** the translator's full chain now FAILS at
`test-hp-drivers`: `storport_hw_function_count` expected ≥ 20, got
13; `usbxhci_hw_function_count` expected ≥ 5, got 2. Those floors were
calibrated on desync noise (2026-09-14: usbxhci's "hardware functions"
were phantom INS/OUTS decoded inside imm64 immediates). The fix
removed the phantoms and the floors no longer hold. Not moved here:
lowering them to the new output would be copying the run. Post-fix
counts, all eight: ACPI 13, disk 1, HDAudBus 1, i8042prt 2, pci 1,
serial 31, storport 13, usbxhci 2.

**The matrix CLOSES (checked 2026-09-18 from the two logs, not from
the table):** every class's delta between `operand-diff-2026-09-15.log`
and `operand-diff-fix-b-2026-09-18.log` equals its matrix inflow minus
outflow with ZERO residual on all ten classes (operand_ok +1265 = 646
imm→ok + 619 nostart→ok; nostart −1057 = 619+329+83+17+8+1; reg +329,
addr +83, mem +17, mnemonic +8, undecoded +1, imm −646, opcount 0,
other 0), and the after-run's classes sum to Ghidra's 148921. The
transitions account for the entire movement.

**Ruling (owner, 2026-09-18): `test-hp-drivers` SUSPENDED, not
re-floored.** Exempt from the chain with the defect named and the
re-enable condition stated (front end complete, xfail_names empty,
assertion rewritten against Ghidra). Post-fix counts recorded as an
observation in the test's header and the Makefile.
