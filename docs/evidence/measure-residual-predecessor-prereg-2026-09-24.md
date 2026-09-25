# The residual's boundary edges, classified population-wide: pre-registration (2026-09-24)

**Written before the run.** Owner ruling, 2026-09-24. 94% of the residual's
reachable port sites (10,739 of 11,453) sit where Ghidra's listing has no
instruction. **That means Ghidra's flow did not reach those bytes, not that
they are data.** Both analyses start from the same function entry. So **the
finding is the difference between the two edge sets**, and the instruction
where our flow leaves Ghidra's should name the mechanism, without reading a
single site. Outcomes go BELOW the line.

**A correlate recorded, not discarded (owner, point 2):** in 337 of the 362
unattested functions, the decoder refuses an instruction *before* the
fabricated ports. It is disqualified as an end rule (it loses 32% of real
functions), but it is kept as an observation with predictive value: the bytes
stopped being code slightly earlier.

## Instrument (`boundary_edges.py`)

For each residual site, the instrument walks **backward** over our CFG
(predecessor edges, reachable blocks only) from the site's block, through
blocks whose first instruction Ghidra does not list, to every **boundary
edge** u → v:
- **u** ends in an instruction Ghidra lists (inside Ghidra's flow);
- **v** starts where Ghidra lists nothing (outside it).

Each boundary edge is classed by **u's last instruction** and the **edge
kind**:

| class | u's last instruction | edge |
|---|---|---|
| `call-fall` | `call` | fall-through (Ghidra did not continue past the call) |
| `jcc-fall` / `jcc-taken` | a conditional branch | fall-through / branch |
| `jmp-taken` | `jmp` to a direct target | branch |
| `plain-fall` | any other instruction | fall-through |
| `no-boundary` | none found: the region is reached from our entry block, which Ghidra does not list either | — |

Each site takes the class of its boundary edges, or `mixed` if they differ.

## Predictions

| # | prediction |
|---|---|
| B1 | `call-fall` is the **largest** class: **~40%** of sites. Ghidra stops after calls it knows do not return (`KeBugCheckEx` and similar); our lifter always falls through a call |
| B2 | `plain-fall` **~25%**; `jcc-fall` plus `jcc-taken` **~20%**; `jmp-taken` **~5%**; `no-boundary` **~5%**; `mixed` the rest |
| B3 | ClipSp (977 of the 10,739) differs from the rest, with more `jcc-*` and `jmp-taken` (obfuscated control flow) |

**If one class carries most of the residual**, the mechanism is a
measurement. **If none does**, the stratified hand-read (owner, point 5)
decides.

---

## Outcome

*(below this line, from the artefact only)*

**Inputs:** build `adcbf3c1…`; `boundary_edges.py` v1 and v2,
`entry_coverage.py` and `entry_source.py`; results `residual-*.json` in
`~/corpus/tools-2026-09-24/SHA256SUMS`.

### The boundary-edge classification: predictions missed, and the instrument's frame was wrong

| # | predicted | observed |
|---|---|---|
| B1 | `call-fall` the largest, ~40% | **missed: 0 sites** |
| B2 | plain 25%, jcc 20%, jmp 5%, no-boundary 5% | **missed**: v1 put **98.8%** in `no-boundary`, and v2 (which also looks for the transition inside a block) put **96.7%** there |
| B3 | ClipSp differs | ClipSp holds almost all of the few boundary edges that were found (206 of 222 intra-block, 54 of 54 `jcc-fall`) |

**Why the frame was wrong.** A boundary edge assumes the region is entered
from code Ghidra reached. For most sites, walking back through our CFG never
meets a Ghidra-covered instruction: **53% walk all the way to the function's
own entry.** The divergence is not an edge inside the function. **It is the
function.**

### The partition that explains it: where each function's entry came from

Each kept port-fact function's entry, checked against Ghidra's listing and
against its source. Sites here are all uncovered port sites, reachable or
not: **12,747**.

| class | functions | uncovered port sites |
|---|---|---|
| **A. entries created from non-code** (Ghidra does not list the entry; median Ghidra coverage of the function's instructions **0%**) | **25** | **5,944 (46.6%)** |
| … a call target whose **every** caller is outside Ghidra's listing | 9 | 2,540 |
| … neither a call target nor a section base (the prologue pattern, or the nearest-instruction adjustment; **not read**) | 15 | 3,305 |
| … a section base Ghidra does not list | 1 | 99 |
| **B. real entries (Ghidra lists them) with no `.pdata` range** | **40** | **4,649 (36.5%)** |
| … the target of a call Ghidra lists | 23 | 1,995 |
| … a section base (discovery always adds one) | 17 | 2,654 |
| **C. `.pdata`-described functions** | 488 | 2,154 (16.9%) |

### Two findings

**1. (bm) has a side effect: it creates functions from non-code.** All 9
class-A call-target functions were checked against the pre-(bm) build
(`343e89fa…`), and **0 of 9 existed as entries before (bm)**. The fix is
correct as arithmetic. But `sem_discover_functions()` step 2 now takes the
target of **every** decoded `call`, including calls decoded from bytes that
are not code, and so it makes entries inside data. (bm)'s outcome counted
+16,593 functions on 198 drivers. **How many of those are this kind is not
measured.** This is minted as **`(br)`**, open without a red: the pass state
("a call target counts only if the call is code") needs a reachability or
coverage notion that discovery, which runs before lifting, does not have.
That is a design question.

**2. The extent reframe was refuted too broadly: correcting my own outcome.**
The extent outcome said the residual is "not mostly an extent problem",
because the `.pdata` rule resolved 0 of 362. But the `.pdata` rule is
*undetermined* for functions without a `.pdata` range, and **class B, real
functions with no unwind range whose extent runs on, holds 36.5% of the
uncovered sites.** That is **(bp)'s class**, and it is **not** the exception.
Stated precisely: for functions **with** `.pdata`, extent is not the problem
(class C, 16.9%). For real functions **without** `.pdata`, it plausibly is
(class B, 36.5%). That class-B extents run on is reasoned from the partition;
the cut is not measured. The largest share (class A, 46.6%) is **functions
that are not functions at all**.

**The residual is therefore three things, not one**, in order of size:
fabricated entries (A, including (br)); unbounded extents without `.pdata`
(B, (bp)'s class); and sites inside `.pdata` functions (C). Nothing is
designed yet. Class A's 15 "neither" entries have an unread source. Reading
them from the bytes is the next measurement, and the owner's stratified
hand-read now has its strata.

### Owner's record, end of 2026-09-24

- **The owner's own error, stated by the owner:** the extent hypothesis was
  abandoned on a summary number ("P resolves 0") instead of the partition
  behind it. "Resolves 0" and "cannot answer" are different results, which is
  the zero-measured-versus-zero-found error turned inward. It is the sixth
  desk error this week, and the first where something was dropped too quickly
  rather than asserted too quickly. **Corrected:** extent is not the problem
  for functions with `.pdata` (16.9% of uncovered sites). For real functions
  without it, it plausibly is (36.5%), reasoned from the partition and not
  measured.
- **(bm)'s scorecard is reopened** (register). The first measurement next
  session: how many of (bm)'s +16,593 new entries are call targets decoded
  from non-code.
- **The hand-read is not started tonight.** The strata stand. The sample
  design waits.
