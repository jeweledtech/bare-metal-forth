# (bg) `NP` forms both instruments accept, bounded by reading the SDM: pre-registration (2026-09-23)

**Written before the change.** Owner ruling: where both instruments agree,
only the specification adjudicates. So `(bg)`'s bound comes from **the
SDM's NP/NFx column read over every named row**, not from another
differential. Outcomes go BELOW the line.

## The spec-read

**Index.** The two-byte-map opcode rows of SDM 325462-092 were indexed
with their prefix marker (none, `NP`, `NFx`, or an explicit `66`/`F2`/`F3`
row): **755 rows in 308 cells**.

**The rows examined.** Every cell our decoder names without a prefix was
read against that index:
- that is **4,214 named, non-SSE cells**, and every one had an SDM row;
- SSE rows are keyed by their exact prefix, so they are complete by
  construction;
- `0F C7` shares one digit between register and memory forms with
  different markers, so it was read by hand in (bd) and is excluded here.

**For each prefix `66`/`F2`/`F3`, the SDM gives one of three outcomes:**
- an explicit row for that prefix (a different instruction);
- the prefix is forbidden (`NP`, or `NFx` for `F2`/`F3`);
- neither, so the prefix is allowed.

### The bound

| instruction | SDM row (line in the extraction) | named today under |
|---|---|---|
| STAC | `NP 0F 01 CB` (96732) | `66`, `F2`, `F3` |
| XGETBV | `NP 0F 01 D0` (138527) | `66`, `F2`, `F3` |
| XSETBV | `NP 0F 01 D1` (140137) | `66`, `F2`, `F3` |
| VMFUNC | `NP 0F 01 D4` (221339) | `66`, `F2`, `F3` |
| GETSEC | `NP 0F 37` (140608 and the leaf pages) | `66`, `F2`, `F3` |

**Five instructions and 15 (instruction, prefix) pairs: 228 cells of the
73,152-slot sample** (76 per prefix; GETSEC has no ModRM, so it occupies all
72 ModRM cells).
- **(bd)'s differential saw none of the 228.** objdump accepts these
  prefixed forms (`data16 stac`), so the two instruments agreed, and
  the agreement was wrong.
- **The spec-read reproduces no (bd) cell**, which confirms that fix from
  the other side.

**Withdrawn before it was claimed:** a first pass also flagged `F2 0F
80–8F` against `jcc`. The index had read SDM Table E-4, the MPX **BND
prefix on Jcc** (the same jump with bounds semantics), as an opcode row.
`jcc` is right.

**Reach: 0 corpus rows, a measured zero.** The same scan counts **835**
unprefixed rows of the five (XGETBV 805, VMFUNC 14, XSETBV 14, STAC 2).

## The change

In `system_identity()`, `0F 01 CB/D0/D1/D4` and `0F 37` name nothing under
any of `66`/`F2`/`F3`. The result is `UNKNOWN`, with the length unchanged,
following the (bd) and (bf) precedent.

## Predictions

| # | prediction |
|---|---|
| G1 | the `(bg)` red, **widened before the fix from the STAC witness to all 15 pairs**, XPASSes; nothing else moves |
| G2 | across the 73,152-slot sweep, **exactly 228 names change**, all at these five instructions, and 0 lengths |
| G3 | corpus sweep byte-identical (0 rows, measured) |
| G4 | differential, `-t uir` and park census byte-identical |
| G5 | suites green; tests unchanged; reds 13 → 12 |

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `x86_decoder.c` `fe0580db1ef2035e`, `bin/translator` `11f51761d4ad5d7a`.

| # | predicted | observed |
|---|---|---|
| G1 | the widened red XPASSes; nothing else moves | **held**: the gate fired on exactly `x64_RED_bg_np_prefix_objdump_accepts` (15 of 15 pairs now name nothing) |
| G2 | exactly 228 names change in the sweep, at these five; 0 lengths | **held exactly**: 228 (GETSEC 216 = 72 × 3; STAC, XGETBV, XSETBV and VMFUNC 3 each), 0 lengths |
| G3 | corpus sweep byte-identical | **held**, all seven sets |
| G4 | differential, `-t uir`, park census byte-identical | **held**: 0 of 16, 0 of 12, 0 of 539 |
| G5 | suites green; tests unchanged; reds 13 → 12 | **held**: 410 tests, 12 reds |

**What this closes.** These 228 cells were invisible to the differential
that found (bd): objdump and our decoder agreed on every one. They were
found only by reading the specification over every named row. This is the
first defect class in the project that is **bounded entirely by the pinned
specification**, with the two instruments serving only as the things being
checked. The spec-read also confirmed (bd) from the other side, since none
of its cells reappeared.
