# Function-unit figures recomputed on the fixed discovery (2026-09-24)

Owner ruling, 2026-09-24: **recompute or withdraw; flagging is not an
option.** A number that could be 10× off is unknown, not provisional. The
rerun is done **before (bk)**, so that (bk)'s own must-not-move set measures
against a true baseline, with (bm) in and (bk) out. The list recomputed is
**the candidate list written in (bm)'s pre-registration before the fix**
(`fix-bm-discovery-prereg-2026-09-24.md`), not a list rebuilt after the
result. It also covers the two figures (bm)'s outcome named as instances of
its item 1.

**Build:** `bin/translator` `60df7c753af56625` (private `2dbcdb3`). The two
counterfactuals are scratch builds, each **one line** from that source
(diffed): (bj)'s DLL rule off (`8e0982a8…`), and MmBuildMdlForNonPagedPool
DMA → MEMORY_MGR (`854225c1…`). 0 empty outputs in any run.

## 0. The fabrication mechanism, checked as a set (owner ruling 3)

**40** of the 1,322 are at image base `0x10000`, not 20. So the low base is
necessary (no driver at any other base fell) and **not sufficient**. The
missing condition comes from the arithmetic. The old target, `address +
length + absolute`, is roughly twice the call's address. It lands inside the
discovery range only when the driver's code range reaches past it.
`bm_doubled.py` counts, per driver, the old targets that land in range.

| | drivers |
|---|---|
| base `0x10000` **and** old targets in range > 0 (**predicted to fabricate**) | **24** |
| **actually lost ≥ 1 entry** under the fix (pre/post `-t uir` entry sets, all 225 affected drivers) | **24** |
| lost but not predicted / predicted but did not lose | **0 / 0** |

**Confirmed exactly.** The fabricated set is **24** drivers, not the 20 my
outcome named. The 20 fell on net. The other 4 (`sisraid4.sys` ×3,
`EUDCPEPM.sys`) lost 2 and 4 fabricated entries each while gaining more real
ones (20, 14), so they rose on net. **90,713** fabricated entries were
removed in total. The 16 other low-base drivers have code ranges ending at
`0x16600`–`0x24400`, too small for any doubled target to land inside.

## 1. The candidate list, recomputed

| candidate (from the pre-registration) | before the fix | **on the fixed build** |
|---|---|---|
| 1. total functions over the 1,322 | 872,613 | **801,111** |
| 1. hardware functions | 16,400 (921 drivers) | **14,738** (921 drivers) |
| 1. scaffolding / unclassified | — | **168,331 / 618,042** |
| 1. **(bj) V4**: importers whose buckets moved when the class libraries got categories | 179 of 392, scaffolding +742 | **178 of 392, scaffolding +485**, conserved 178 of 178, 0 others moved |
| 1. **the DMA counterfactual** (MmBuildMdlForNonPagedPool DMA → MEMORY_MGR) | 290 hardware on 114 drivers, 3 emptied | **288 hardware on 113 drivers, 3 emptied** (1.95% of 14,738) |
| 1. 664-0 split (moved / unmoved) | 179 / 213 | **178 / 214** |
| 1. 664-0 classes on the unmoved | A on 147, all-A 3, D on 210; B, C, E 0; thunk-only 66 | **A on 148, all-A 3, D on 211; B, C, E 0; thunk-only 66**; control 178 of 178 |
| 2. park census outcomes | — | **3 of 539** changed, all `none` → `frame` (`fix-bm` outcome) |
| 3. stage 2, the 320 HP hardware functions | — | **unchanged**: the HP eight are byte-identical (N1) |
| 4. (bk) thunk ownership | 52 own / 239 absorbed | **251 own / 40 absorbed** (31 `jmp`-only, 9 unreferenced) |
| 5. X1, X2, X3 | — | **unchanged** on 1,322 of 1,322 (N3) |

The "before" total, 872,613, is the sum of `total_functions` in
`bm-reports-pre.tsv`.

**What moved materially:** the hardware denominator (−1,662, the fabricated
hardware functions on the 24) and (bj) V4's scaffolding count (+742 → +485).
The rest moved by one driver or not at all. Each document quoting an old
figure now carries the recomputed one beside it, struck through where it was
a result.

## 2. The lesson, as the owner put it

**A one-sided instrument cannot see a two-sided defect.** `bm_extent` asked
*which call targets are not entries*, and so it was structurally blind to
*which entries are not call targets*. When a defect is a **wrong
computation** rather than a missing one, assume it errs in both directions,
and measure both. The should-move rule caught it on its first use, on a fix
whose must-not-move set was perfect.
