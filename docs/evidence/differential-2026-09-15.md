# Differential harness baseline: instruction-boundary agreement vs Ghidra (2026-09-15)

Log: `docs/evidence/differential-2026-09-15.log` (235 lines; input sha256
per binary, code sha256 per harness file, per-section detail).
Exact command, run from `tools/translator/`:

```
make differential-all
```

(equivalently `make differential BIN=<binary>` per input; the log's
`command:` line and per-binary `INPUT` hash lines are the provenance.)
Ghidra 12.1.2, snap rev 47, pinned in tools/translator/Makefile.

## Grammar

Ghidra dumps every instruction START it found in every executable
block (`tools/ghidra/InstrStarts.java`). `tests/dump_starts` runs our
decoder (`x86_decode_range`, same loaders, same mode, same sections as
`translate_file`) and dumps every START it produced. The comparer
(`scripts/compare_starts.py`) classifies each of OUR starts:

- match: coincides with a Ghidra start
- mid: falls inside a Ghidra instruction (a desync)
- none: Ghidra has no instruction there (padding, data, unreached)
- run: longest consecutive run of mid starts
- agree = match / ours

This counts instruction boundaries. It is a different grammar from the
09-15 survey figures (those counted emitted words) and is not
reconciled toward them or anything else.

## Status of this metric: SUPPORTING, not the arc's headline

Owner ruling 2026-09-15, after the run: boundary agreement is blind to
two of the three pre-registered defects BY CONSTRUCTION.

- (a) `48 8D 05 disp32` is 7 bytes whether disp32 is read as absolute
  or as RIP-relative. Fixing it moves no boundary.
- (c) `49 8B 00` is 3 bytes whether or not REX.B reaches the base.
  Fixing it moves no boundary.
- (b) imm64 is 10 bytes vs the 6 we read. The only one of the three
  that this metric can see.

A metric that cannot register two of three known defects is not the
number the arc is measured by. The arc's number is owed by an
OPERAND-level differential (week 2): for every start both sides agree
on, compare mnemonic, operand count, register operands, and the
resolved effective address of any memory operand against Ghidra's text,
which the Ghidra dump already carries. That number moves when each of
(a), (b), (c) is fixed.

What this harness keeps: desync EVENT counts (`mid`) are real and worth
tracking. ACPI.sys's 3742 is a genuine finding.

## Result (boundary grammar)

`agree` = match / ours has OUR sweep as its denominator, and ours >
ghidra on all fourteen inputs (a linear sweep vs Ghidra's
recursive-descent reach). It moves when the sweep policy changes with
no decoder change at all, so it is not reported as the score.
`coverage` = match / ghidra has a fixed denominator and cannot be moved
by sweeping more; it is the boundary figure to quote if one is quoted.

| binary | kind | ghidra | ours | match | mid | none | run | coverage (match/ghidra) | mid/ghidra | agree (match/ours) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ACPI.sys | HP PE32+ | 148921 | 169624 | 147674 | 3742 | 18208 | 16 | 99.2% | 2.51% | 87.1% |
| disk.sys | HP PE32+ | 12335 | 13836 | 12316 | 37 | 1483 | 8 | 99.8% | 0.30% | 89.0% |
| HDAudBus.sys | HP PE32+ | 24214 | 27186 | 24158 | 122 | 2906 | 9 | 99.8% | 0.50% | 88.9% |
| i8042prt.sys | HP PE32+ | 19090 | 21438 | 19053 | 102 | 2283 | 9 | 99.8% | 0.53% | 88.9% |
| pci.sys | HP PE32+ | 86827 | 99758 | 86700 | 574 | 12484 | 9 | 99.9% | 0.66% | 86.9% |
| serial.sys (tests/hp_i3) | HP PE32+ | 13852 | 16105 | 13813 | 53 | 2239 | 8 | 99.7% | 0.38% | 85.8% |
| storport.sys | HP PE32+ | 98228 | 111104 | 97782 | 1169 | 12153 | 19 | 99.5% | 1.19% | 88.0% |
| usbxhci.sys | HP PE32+ | 89234 | 100529 | 88960 | 758 | 10811 | 22 | 99.7% | 0.85% | 88.5% |
| ne2k-pci.ko | Linux ELF64 | 1193 | 1229 | 1178 | 29 | 22 | 4 | 98.7% | 2.43% | 95.9% |
| 8139too.ko | Linux ELF64 | 4026 | 4515 | 4006 | 57 | 452 | 11 | 99.5% | 1.42% | 88.7% |
| iTCO_wdt.ko | Linux ELF64 | 907 | 936 | 895 | 24 | 17 | 12 | 98.7% | 2.65% | 95.6% |
| via-rng.ko | Linux ELF64 | 176 | 180 | 176 | 2 | 2 | 2 | 100.0% | 1.14% | 97.8% |
| serial.sys (tests/data) | ReactOS PE32 control | 4220 | 4276 | 4220 | 2 | 54 | 2 | 100.0% | 0.05% | 98.7% |
| beep.sys | ReactOS PE32 control | 447 | 465 | 447 | 0 | 18 | 0 | 100.0% | 0.00% | 96.1% |

The controls score high, as pre-stated (mid = 0 and 2).

Coverage proves the blindness empirically: it runs 98.7% to 100.0%
across all fourteen, and the worst 64-bit driver (ACPI.sys, 99.2%) and
a PE32 control (beep.sys, 100.0%) are 0.8 points apart. A metric whose
entire dynamic range across the known working/broken boundary is under
one point is not measuring that boundary.

`mid/ghidra` is the column that discriminates: every 64-bit input
(0.30% to 2.65%) is worse than every 32-bit control (0.00%, 0.05%), by
50x at the extremes. It shares the fixed denominator, so sweep policy
cannot move it. It still cannot move when (a) or (c) is fixed, so it is
not the arc's number either; as the supporting figure it is the one to
quote, not coverage.

What 99.2% coverage on ACPI.sys says, and it is not good news: we find
where instructions begin. The three reds prove we get what is IN them
wrong (the effective address, the immediate, the register). x86
self-resynchronizes, so boundary recovery is nearly free and says
almost nothing about correctness. 99.2% boundary coverage and `rip`
appearing zero times in the emitted output are both true at once. The
failure mode that produces exactly this table is "a decoder that gets
lengths right and operands wrong," which is the one the reds show.

`none` conflates three things this harness cannot separate: padding
decoded as code (our error), real code Ghidra never reached (our
credit), and data wandered into after a desync (our error, hidden).

## Notes

- `mid` (a true desync) per Ghidra instruction: 0.30% to 2.51% on the
  HP drivers, 1.14% to 2.65% on the modules, 0.00% and 0.05% on the
  controls. Desync runs are short
  (max 22) because x86 self-resynchronizes within a few bytes, so each
  `mid` is an event that produced wrong instructions until resync.
- Comparer labels were cross-checked against the pinned single-address
  oracle on 8 sampled usbxhci.sys starts (4 mid, 4 none): all 8 agree
  (`docs/evidence/differential-oracle-check-2026-09-15.log`). Three of
  the four mid samples are inside a 10-byte imm64 MOV, the desync engine
  named 2026-09-14.
- Two inputs share the basename `serial.sys`; in this log the `===`
  path header before each block disambiguates. Later runs label by
  parent directory (`hp_i3_serial.sys` / `data_serial.sys`), a change
  made after this log was banked and not applied to it.
- ELF: only `.text` is compared (the ELF loader exposes only `.text`);
  Ghidra's other executable blocks (`.init.text`, etc.) are listed in
  the log as "executable Ghidra blocks we did not decode".
