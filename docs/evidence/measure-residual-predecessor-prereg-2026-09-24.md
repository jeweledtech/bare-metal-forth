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
