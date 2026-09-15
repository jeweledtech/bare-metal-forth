# Pre-registration: operand-level differential (2026-09-15)

Written BEFORE the harness was built or run. Outcome goes below the line.

## Rule 22 gate: which pre-registered defect moves this metric?

The metric: for every instruction start both sides agree on, compare
our decode against Ghidra's as a canonical operand list (mnemonic,
operand count, and per operand: register name / memory base+index*
scale+disp / immediate value mod 2^64 / resolved absolute address).
Score = operand-correct instructions / Ghidra instructions (fixed
denominator; a start we do not reach counts as wrong).

| defect | our canonical today | Ghidra canonical | moves when fixed? |
|---|---|---|---|
| (a) RIP-relative LEA `48 8D 05 10 00 00 00` @401000 | `A:0x10` (disp32 as absolute) | `A:0x401017` | YES: fix makes ours `A:0x401017` |
| (b) imm64 `48 B8 ..` @401007 | `I:0x55667788`, len 6 | `I:0x1122334455667788`, len 10 | YES: immediate value and boundary |
| (c) REX.B base `49 8B 00` @401011 | `M:RAX,-,1,0` | `M:R8,-,1,0` | YES: base register name |

All three move. This is the arc's instrument. (Boundary agreement moved
for (b) only; see differential-2026-09-15.md.)

Named non-moving things, so nobody mistakes them for the score: operand
SIZE (qword/dword) is not compared in this revision; our 32-bit decoder
has no names for r8-r15 or 64-bit registers, so the dump side names
them by size and number and never produces r8-r15 today. Scoring
`M:R8` against Ghidra's text forces the fix to adopt the oracle's
register names; that is a constraint on the implementation, accepted.

## Blind spots (what this metric cannot see, owner ruling 2026-09-15)

- Segment prefixes are dropped on both sides, so this metric is BLIND
  to segment-handling defects. GS-relative access is routine in these
  drivers (KPCR); that is a real defect class, not a formatting choice.
  No instrument owns it yet.
- Starts we emit where Ghidra has none are outside the denominator, so
  a decoder that hallucinates instructions in data is NOT penalized
  here. The boundary harness's `none` column
  (differential-2026-09-15.md) owns that.

## The mnemonic alias table is a score-moving knob: frozen and hashed

Every alias added raises the score with no decoder change (the moveable
denominator wearing a different hat). Containment:

- The table lives in one place in the comparer and its sha256 is
  printed into every log alongside the code hashes.
- Scores are comparable ACROSS RUNS ONLY AT EQUAL TABLE HASH.
- When the table changes, the baseline is re-run with the new table
  before any delta is quoted. Table-constant comparison or no comparison.

## Inputs

The 14 on record (8 HP PE32+, 4 Linux ELF64, 2 ReactOS PE32 controls)
plus the 4-instruction fixture `tests/data/x64_reds/x64_reds.elf`
(LEA / MOV imm64 / MOV [R8] / RET) as a 15th input whose exact
per-instruction verdict is checkable by hand against the oracle log.

## Predictions

1. Fixture: Ghidra 4 instructions. Operand-correct today: at most 1 (RET),
   and (a), (b), (c) each mismatched. If any of the three is
   operand-correct, the harness is wrong (a canonicalization that hides
   the defect), not the decoder right; stop and fix the harness.
2. Controls (PE32 serial.sys, beep.sys) score higher than every 64-bit
   input. Named alternative: a control scoring at or below a 64-bit
   input means the canonicalization is broken for 32-bit forms
   (mnemonic aliases, implicit operands), and the number is not yet a
   decoder number.
3. On 64-bit inputs the score is well below boundary coverage (99%).
   No specific figure is predicted; the point of the run is to get one.
4. Mismatch classes are reported (undecoded / mnemonic / opcount /
   reg / mem / imm / addr) so the 64-bit-specific losses (mem base,
   imm, addr) can be told from the decoder's general opcode-coverage
   gaps (undecoded, mnemonic). No prediction on their ranking.

## Known limits of this revision (stated before the run)

- Mnemonic aliasing between our names and Ghidra's is a hand table
  (Jcc/SETcc/CMOVcc condition names, string ops, INS/OUTS). Aliases not
  in the table count as mnemonic mismatches. See the frozen-table
  section above: hashed into the log, comparable only at equal hash.
- Implicit operands (RET, PUSH/POP, IN/OUT, shifts by 1, string ops)
  differ in count between the two sides in places; those count as
  opcount mismatches and are not hidden.
- Segment prefixes (GS:) are dropped on both sides before comparing.

## Harness shakedown (after the predictions, BEFORE the baseline run)

Four canonicalization defects were found on the fixture and the two
PE32 controls and fixed in the harness (never in the decoder, never in
the alias table; alias_sha256 02101788edd2… unchanged throughout):

1. Ghidra renders a RIP-resolved address as a scalar inside brackets;
   disp-only memory now canonicalizes to `A:` on both sides. Without
   this, (a) classified as `other` instead of `addr`.
2. Ghidra spells a LOCK-prefixed instruction `SUB.LOCK`; the dump now
   renders our decoded LOCK flag the same way.
3. Immediates compare at declared width: Ghidra's scalar bit length on
   its side, our destination operand size on ours. This keeps (b)
   visible and WOULD expose imm32 zero- vs sign-extension under REX.W
   if the decoder had that defect. Correction (same day): that claim
   was reasoned, not observed. Reading every REX.W-eligible imm32 path
   (x86_decoder.c: 0x81 line 282, 0x05..0x3D line 382, 0x68 line 249,
   0xA9 line 556, 0xC7 line 639) shows all use the sign-extending
   `read_i32`; the only zero-extending path is B8+r (`read_u32`, line
   584), which is defect (b) itself. No separate fourth defect exists in
   the code; the byte sequence `48 C7 C0 FF FF FF FF` is in fixture v2
   so the verdict is observed, not inferred.
4. Ghidra prints a negative disp32 as its unsigned 32-bit pattern;
   canonical displacement is signed.

### Canonicalizer stopping rule (owner ruling 2026-09-15)

The canonicalizer may only be changed to remove a difference that is
NOT a decoder defect, and every such change must name the defect it is
not hiding. Defect-neutral or defect-revealing; never defect-concealing.
Fix 3 is the worked example: it removed a width-rendering difference
and named what it keeps visible ((b), and any extension defect). The
residue on the controls (undecoded IMUL, CMPXCHG.LOCK as NOP.LOCK, REP
STOSD implicit operand) is decoder fact and is where tuning stopped.
Tuning a comparer against controls until they read 100% is how an
instrument comes to agree with the oracle by construction.

Readings after shakedown, before the baseline: beep.sys 447/447
(100.0%), ReactOS serial.sys 4215/4220 (99.9%; residue = 1 undecoded
three-operand IMUL, 1 LOCK CMPXCHG decoded as NOP.LOCK, 3 REP STOSD
implicit-operand counts: all decoder facts, left in). Fixture 0/4:
(a) `addr`, (b) `imm`, (c) and RET `nostart` (the imm64 under-read
desynced the remaining 8 bytes). Prediction 1 holds.

Exact baseline command, run from `tools/translator/`:

```
make differential-all DIFF_LOG=../../docs/evidence/operand-diff-2026-09-15.log
```

---

## Outcome (appended after the baseline run)

Run 1 (superseded, `operand-diff-2026-09-15-run1-superseded.log`) used a
canonicalizer that compared immediates at Ghidra's ENCODED width; the
fixture's sign-extension probe showed that as a harness artifact (MOV
RAX,-0x1 is S:32 on Ghidra's side, 64-bit on ours, same value). Fixed
per the stopping rule (removes an encoded-vs-operand width rendering
difference; keeps (b) and any extension defect visible) and the full
set re-run. Baseline = run 2, `operand-diff-2026-09-15.log`, 15 inputs,
alias_sha256 02101788edd2… (unchanged since the table was written).
Command, from `tools/translator/`:

```
make differential-all DIFF_LOG=../../docs/evidence/operand-diff-2026-09-15.log
```

| binary | kind | ghidra | operand_ok | score | nostart | undecoded | mnemonic | opcount | reg | mem | imm | addr |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fixture v3 | ELF64, 8 instr | 8 | 1 | 12.5% | 1 | 0 | 0 | 0 | 3 | 1 | 1 | 1 |
| ACPI.sys | HP PE32+ | 148921 | 92933 | 62.4% | 1247 | 987 | 3269 | 3352 | 29893 | 5064 | 646 | 11529 |
| disk.sys | HP PE32+ | 12335 | 7733 | 62.7% | 19 | 55 | 293 | 352 | 2354 | 690 | 5 | 834 |
| HDAudBus.sys | HP PE32+ | 24214 | 14246 | 58.8% | 56 | 88 | 518 | 397 | 5362 | 691 | 3 | 2852 |
| i8042prt.sys | HP PE32+ | 19090 | 10947 | 57.3% | 37 | 19 | 341 | 447 | 3999 | 792 | 16 | 2492 |
| pci.sys | HP PE32+ | 86827 | 55919 | 64.4% | 127 | 370 | 2188 | 2484 | 17535 | 3044 | 134 | 5026 |
| serial.sys (hp_i3) | HP PE32+ | 13852 | 8730 | 63.0% | 39 | 21 | 286 | 471 | 2961 | 463 | 2 | 879 |
| storport.sys | HP PE32+ | 98228 | 65179 | 66.4% | 446 | 424 | 2316 | 2053 | 18679 | 4395 | 133 | 4603 |
| usbxhci.sys | HP PE32+ | 89234 | 55767 | 62.5% | 274 | 588 | 1695 | 1309 | 17979 | 3795 | 76 | 7751 |
| ne2k-pci.ko | ELF64 | 1193 | 617 | 51.7% | 15 | 10 | 8 | 1 | 259 | 67 | 32 | 184 |
| 8139too.ko | ELF64 | 4026 | 1881 | 46.7% | 20 | 12 | 21 | 23 | 1003 | 147 | 113 | 806 |
| iTCO_wdt.ko | ELF64 | 907 | 592 | 65.3% | 12 | 2 | 5 | 0 | 107 | 10 | 22 | 157 |
| via-rng.ko | ELF64 | 176 | 104 | 59.1% | 0 | 0 | 3 | 0 | 30 | 2 | 4 | 33 |
| serial.sys (data) | ReactOS PE32 control | 4220 | 4215 | 99.9% | 0 | 1 | 1 | 3 | 0 | 0 | 0 | 0 |
| beep.sys | ReactOS PE32 control | 447 | 447 | 100.0% | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

**The arc's number: 64-bit inputs 46.7% to 66.4% operand-correct;
controls 99.9% and 100.0%.** (`score` = operand_ok / ghidra; `other`
column omitted, ≤1 everywhere.)

Predictions: 1 holds (fixture: (a) addr, (b) imm, (c) mem, each
mismatched; the one operand-correct instruction is the sign-extension
probe, which is not a defect; RET nostart). 2 holds (every control
above every 64-bit input, by 33 points at the nearest). 3 holds (well
below 99% boundary coverage). 4: classes reported; on the 64-bit
inputs `reg` dominates everywhere, then `addr`, then `mem`, with
`undecoded`+`mnemonic` (general opcode coverage: SSE forms decoded as
NOP, three-operand IMUL, MOVSXD) a distant third.

What the reg class is (i8042prt.sys histogram, verbose comparer output):
3571 r8-r15 expected / low register decoded (REX.R on the reg field,
REX.B on register rm and opcode-embedded registers); 296 E-register
decoded / R-register expected (PUSH/POP default 64-bit operand size);
132 DH/BH/CH vs SIL/DIL/BPL (byte-register naming under REX). The first
two became reds (d), (d'), (e) the same day
(`x64-reds-def-prereg-2026-09-15.md`); the third is named, not tested.
The addr class is (a) across MOV/LEA/CMP/CALL-indirect. The opcount
class is dominated by multi-byte NOP operands (Ghidra `NOP dword ptr
[RAX + RAX*0x1]` vs our bare NOP), a stated limit.

Fixture v3 registers every XFAIL name in its own class: reg=3 ((d),
(d'), (e)), mem=1 (c), addr=1 (a), imm=1 (b). When a fix lands, the
fixture line moves by exactly that instruction, so deltas attribute.

## Addendum (owner follow-ups, same day)

**Seventh defect (f), byte-register naming under REX: WHICH function
(owner question, answered from the code).**

- `x86_reg_name` (src/decoders/x86_decoder.c:1238) takes (reg, size)
  only and is called from exactly one place: `x86_print_decoded`
  (lines 1305/1319/1324), the `-t disasm` printer.
- The UIR lifter copies the raw register NUMBER and size from the
  decoded struct (src/ir/uir.c:119, :124, :816) and drops `rex`. So
  downstream codegen sees reg=6 size=1 and cannot tell SIL from DH.
  The loss is at the struct level for everything past the decoder.
- The harness's `reg_name` (tests/dump_starts.c:38) names from the same
  two inputs (reg, size) the lifter carries forward. It measures what
  the pipeline sees; NO share of the baseline's `reg` misses is a
  harness artifact. Making the dump apply REX itself would conceal the
  pipeline defect (stopping rule: never defect-concealing), so it stays.

Therefore (f) IS a decoder-struct defect with a nameable pass state:
the fix gives SPL/BPL/SIL/DIL distinct register numbers that survive
the lifter's copy, `X86_REG_SPL..X86_REG_DIL = 16..19`, and
`x86_reg_name` names them. Red added the same day
(`x64_RED_byte_reg_sil_under_rex`, XFAIL now seven): `40 8A C6`,
Ghidra `MOV AL,SIL` @401017 (fixture v4, sha256
`e22204cc7596d80349d852538c70332642cc763fc09563dfdb8a482f018fcf3e`,
oracle `x64-reds-v4-oracle-2026-09-15.log`); asserts REX detected, then
operands[1].reg == 18. Predicted first failure: "source reg: expected
18 (SIL)" (reg = 6). The fixture line reads reg=4 = the four
register reds. Retracted: the earlier claim that (f) belongs in the
name function only.

**Third 32-bit control from outside the ReactOS corpus.**
`tests/data/controls/nmap_service.exe` (Debian nmap-common, PE32
console, 17 sections, provenance in `tests/data/controls/README.md`):

| | ghidra | operand_ok | score | nostart | undecoded | mnemonic | opcount | reg | mem | imm | addr |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| nmap_service.exe | 8299 | 7885 | 95.0% | 145 | 192 | 75 | 2 | 0 | 0 | 0 | 0 |

Every miss is opcode coverage (undecoded, mnemonic) or the boundary
desync those cause (nostart; boundary harness: mid=468, longest run
17); reg / mem / imm / addr are all ZERO. So the 32-bit operand
semantics generalize past the ReactOS build, and this control also
shows what the ReactOS pair could not: the general opcode-coverage gap
under a different compiler's idiom, cleanly separated from the 64-bit
classes. The control is added to `differential-all`.

**Defect class (g), unbounded read (owner ruling: not incidental).** On
this control the dump reports `covered=32057 of 32056 bytes`: the
decoder consumed one byte past the end of the section because an
immediate/displacement read is not bounds-checked once the opcode byte
is present. This tool's purpose is reading .sys/.dll/.exe files of
unknown provenance; an unbounded read driven by input bytes is a crash
on a malformed file and worse on a crafted one. It gets a red and a
place in the order (after step 4, before the REX fixes), as a defect
class, not an observation.

## Register-number map (the one place; owner follow-up, same day)

Pass states for two reds both claimed 16. Disjoint ranges, fixed here:

| range | meaning | which red introduces it |
|---|---|---|
| 0..7 | AL..BH / AX..DI / EAX..EDI / RAX..RDI by `size` (unchanged) | – |
| 8..15 | R8..R15 (and R8B/W/D by `size`) | (c) base, (d) reg field, (d') opcode-embedded |
| 16..19 | SPL, BPL, SIL, DIL (size 1, only reachable with a REX present) | (f) |
| 32 | `X86_REG_RIP`, memory base marker for mod=00 rm=101 in 64-bit mode | (a) |
| -1 | none (unchanged) | – |

`operands[].reg`, `.base` and `.index` share this numbering. The
x64-reds pre-reg's frozen text says 16 for RIP; its addendum points
here. tests/dump_starts.c already reads 32.

## Blast radius per red: is the fix decoder-only? (confirmed against uir.c)

What the lifter copies, verbatim as numbers (src/ir/uir.c:108-132 and
the `REG_OP`/`IMM_OP` macros at :813-822): `reg`, `base`→`reg`,
`index`, `scale`, `disp`, `imm`, `size`. It does not copy `rex`.
Downstream prints registers as `r%d` (uir.c:721); no table anywhere in
uir.c / semantic.c / forth_codegen.c is indexed by register number
(grep for 8- and 16-wide tables and name arrays: none).

| red | what carries the fix | decoder-only? |
|---|---|---|
| (b) imm64 | `imm` (int64) + `length` | yes |
| (c) REX.B base | `base` number 8..15 | yes |
| (d) REX.R reg field | `reg` number 8..15 | yes |
| (d') REX.B opcode-embedded | `reg` number 8..15 (+ `size` 8) | yes |
| (e) PUSH default size | `size` | yes |
| (f) byte file under REX | `reg` number 16..19 | yes |
| (a) RIP-relative | `base` = 32 | **NO**: src/ir/semantic.c:356 tests `dest.reg < 0 && dest.index < 0` to recognise `call [absolute]` for the IAT cross-reference and takes `(uint32_t)dest.disp` as the slot address. A RIP-relative indirect CALL (the 64-bit IAT form) has base -1 today and hits that branch with the raw disp32 truncated to 32 bits: a wrong slot address, silently. After (a), base = 32 misses the branch entirely. The fix for (a) must extend that site to base == RIP with the resolved address (instruction address + length + disp). One decoder file plus that one semantic.c site; grep found no other consumer of the base sign. |

So six of seven are x86_decoder.c alone (plus `x86_reg_name` for the
disasm printer); (a) is two files. Recorded so week 2 does not learn it
by surprise: the IAT cross-reference on 64-bit inputs is currently
computed from a truncated relative displacement, which is a finding in
its own right (it explains a class of "no hardware API calls found" on
the HP drivers without needing any other cause; not yet confirmed
against a run, stated as reasoned).
