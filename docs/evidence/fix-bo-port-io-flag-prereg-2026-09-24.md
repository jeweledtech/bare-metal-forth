# (bo) the port I/O flag needs reachable code: pre-registration (2026-09-24)

**Written before the fix.** Owner ruling, 2026-09-24: (bo) first, because it
**completes** (bn). After (bn), functions print "hardware" with an empty port
list: the label survives while its evidence is gone, so a blank port list no
longer tells a reader "none found" from "found and discarded". **An internally
inconsistent output is worse than a consistently wrong one.** Outcomes go
BELOW the line.

## Records the ruling asked for

- **ClipSp, with the evidence in its order.** The load-bearing finding is
  **categorical**: ClipSp creates no device, claims no hardware resources and
  registers no PnP interface. A driver with nothing to talk to does not do
  port I/O. The 7.1–7.93 bits/byte entropy of the sections holding every one
  of its port sites **corroborates**; it does not decide. Entropy is a
  statistical cue, as the refuted value spread was. The corpus zero-fact rate
  stands at **99.03%**.
- **Standing line (owner):** *a name is a hypothesis about a thing, not a
  measurement of it.* There were four this week: `System32` read as user
  mode; `PAGEwx` read as writable; "hardware" meaning two things; and one
  integer, 320, standing for two figures. Each was settled by reading the
  thing, not its label.
- **`(bp)` is minted** (register), for code no entry of ours reaches. It
  carries the two RTKVHD64 sites. (bo) inherits it.

## The mechanism (read from source)

`has_port_io` has two writers:
1. **The lifter** (`uir.c`, `lift_one`) sets it for **any** `in`/`out`/`ins`/
   `outs` during linear lifting, before reachability exists.
2. **The analyzer** (`semantic.c:866`) sets it when a function calls a
   **PORT_IO import** (e.g. `READ_PORT_UCHAR`).

A function with `has_port_io` and no other hardware category becomes hardware
at `semantic.c:936`. **(bo) changes writer 1 only.** After pass 3's
reachability, `has_port_io` (and `uses_dx_port`) are recomputed from the port
instructions in **reachable** blocks. Writer 2 is untouched: an import call is
evidence from the import table, not from unreachable bytes.

## Reach, counted from the input before the fix

`bo_reach.py` **v3** (sha in `SHA256SUMS`) reads the current build
(`016001f9…`): report `has_port_io` and `hal_calls` (mapped through the
report's import categories), plus `-t uir` port sites and printed edges.
- **v2 was wrong, and was not used.** It counted as a "flip" any hardware
  function whose `has_port_io` came from writer 2 alone, with no port
  instruction at all. That gave 11 phantom flips on the PE32 and ELF
  snapshot inputs, whose UIR prints no `PORT I/O` header.
- v3 requires the function to have port instructions, none of them
  reachable, and no PORT_IO import call.

| | count |
|---|---|
| hardware functions that are hardware **only** through `has_port_io` | **3,135** on 316 drivers |
| … whose every port instruction is unreachable: **(bo) moves them out** | **830** on **244** drivers |
| hardware functions whose `has_port_io` flips (any, including those kept hardware by imports) | **837** on the same **244** |
| moved functions in drivers with a Ghidra dump / with a Ghidra-attested port site | **650 / 43** |
| HP eight | **1** (ACPI); the other seven 0 |

## Predictions

| # | prediction |
|---|---|
| O1 | the gate fires on **exactly** `uir_RED_bo_unreachable_port_not_port_io`; the (bn) red and guard stay green; the domain guard stays 14; 422 tests; reds 13 → 12 |
| O2 | hardware functions **−830 exactly**; buckets move on **exactly the 244** drivers; no other driver moves |
| O3 | report bytes change on **exactly the 244** flip drivers |
| O4 | nothing else moves: the port-fact function set (`ports_accessed`) **identical** on 1,322 of 1,322 (553 functions); X1–X3 and `iat_edges` unchanged; census 0 of 539 |
| O5 | HP: hardware **266 → 265**. Report and UIR change on **ACPI only** (1 of 12 snapshot UIR files); dumps 0 of 16 |
| O6 | **the convergence check still fails.** The product's zero-fact = (9,921 − 564) / 9,921 = **94.31%**, where 564 = 553 port-fact functions + 11 stage-2, unchanged. The oracle on the same denominator (non-ClipSp attested 91 + 11) is **98.97%**. **(bo) moves the denominator, not the gap.** The gap is still the 363 fall-through functions, which is (bn)'s second condition |
| O7 | of the 830 moved, **43** have a Ghidra-attested port site. Those are false negatives against the oracle, **presumed** `(bp)`'s class but **not read individually**. 180 moved functions are in drivers with no Ghidra dump, so they have no oracle |

**Independent checks:** the suites; the population run (O2–O4 and O6's
inputs); the census; the snapshot. **Four.**

## Amendment, before the population run (2026-09-24)

**A third writer I missed, found by the suite, not by reading.** The first
build failed `int10h_lifts_to_uir_int` ("has_port_io not set for BIOS INT").
`lift_one` also sets `has_port_io` for BIOS software interrupts (`int`
0x10/0x13/0x14/0x15/0x16/0x1A), and my recompute wiped that. **O1 therefore
missed on the first build**, with an unpredicted test failure. The fix now
includes reachable BIOS interrupts, under the same rule. The gate then fired
on exactly the (bo) red.

**A second effect of the same path.** `semantic.c` separately scans **every**
block for those interrupt vectors and marks the function hardware
(BIOS_INT), reachable or not. So a function holding such an `int`, even in
unreachable bytes, stays hardware after (bo).

**Reach re-counted (`bo_reach.py` v4, before any population run of the fixed
build):** flips **837** (unchanged), moves **826** (was 830; 4 functions hold
a BIOS-vector `int`), on the same **244** drivers. Of the 826, **43** have a
Ghidra-attested site, and 646 are in drivers with a dump. HP: 1 flip and 1
move (ACPI).

**Amended predictions** (O1 and O2 restated; O6's arithmetic follows):
- **O1:** 422 tests. The gate fired on exactly the (bo) red **after** the
  BIOS-interrupt writer was included. The first build's unpredicted failure
  is recorded as a miss.
- **O2:** hardware **−826 exactly**, buckets moving on exactly the 244.
- **O6:** product zero-fact (9,925 − 564) / 9,925 = **94.32%** against the
  oracle's (9,925 − 102) / 9,925 = **98.97%** on the same denominator. The
  gap stays.

**Not addressed here, named:** semantic's BIOS scan ignoring reachability is
the same defect class in a third place. It is left for its own letter, not
widened into (bo).

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `bin/translator` before `016001f9c343189b`, after
`e343fdb9f654c474`, built from private `6be84f3` (red `bdc6a4b`), mirror
identical. Readings are `bo-reports-post.tsv`, `bo-zero-fact.tsv` and
`bo-reach-v4.json` in `~/corpus/tools-2026-09-24/SHA256SUMS`. 0 empty
outputs.

| # | predicted (as amended) | observed |
|---|---|---|
| O1 | gate on exactly the (bo) red after the BIOS-interrupt writer was included; 422 tests | **held on the second build** (`fix-bo-xpass-gate-2026-09-24.log`). **Missed on the first build**, with an unpredicted failure, `int10h_lifts_to_uir_int`, recorded above |
| O2 | hardware −826 exactly; buckets on exactly the 244 | **held exactly**: **−826**; the moved set **equals** the 244; each driver's hardware loss equals its predicted move count on **244 of 244**. The moved functions went to scaffolding **+105** and unclassified **+721** |
| O3 | bytes change on exactly the 244 flip drivers | **held as an exact set**: 244, 0 others |
| O4 | nothing else moves | **held**: 0 hex; X2 and X3 1,322 of 1,322; `iat_edges` 1,322 of 1,322; port-fact functions **553** (count unchanged); census 0 of 539 |
| O5 | HP 266 → 265; ACPI only; UIR 1 of 12; dumps 0 of 16 | **held**: 265; ACPI's report and UIR only; dumps 0 |
| O6 | product zero-fact 94.32%; the gap to the oracle's 98.97% stays | **held**: **94.32%** (9,925 hardware, 564 with a fact). **The gap stays**, and it is the 363 fall-through functions |
| O7 | 43 of the moved have a Ghidra-attested site; presumed (bp) | **not read individually**: recorded as 43 unverified false negatives against the oracle |

**(bo) completes (bn).** A function no longer prints "hardware" on the
strength of a port instruction no path reaches. On **244 drivers**, **826**
functions that were hardware only through unreachable port bytes are no
longer labelled hardware. **HP: 265.**

**Found while fixing, and now its own red: `(bq)`** (private `d2fdd6c`).
`semantic.c`'s BIOS-interrupt scan walks every block and marks hardware
from an unreachable `int 0x10`. That is the same defect class in a third
place, held apart rather than widened into (bo).

**Independent checks: four**, as pre-registered.

**Next, per the owner:** decide (bn)'s second condition against the gap as it
now stands. 94.32% against 98.97% is 363 fall-through functions whose port
instructions are reachable only by falling through from real code.
