# `none` carries a route: pre-registration (2026-09-22)

**Written before the change.** Every park and every after-release stop carries
`park_route` (`path` / `address_order`). `none`, the column the census names
as weakest, carries nothing. The walk already tracks the flag, so this is a
report change plus one assignment. Outcomes go BELOW the line.

## What the route means, from the source (rule 31)

`address_order` is set when the walk **crosses an unconditional JMP**
(`semantic.c`, `crossed_jmp`). **Falling through a conditional branch is a
real path** (the not-taken edge), so a walk down a NULL check's failure path
with no JMP crossed stays `path`. **The limit, named and not built:** the
route cannot tell a real path from the *right* one. That would need branch
semantics (which side of `test %rax,%rax` the base is non-NULL on).

**The owner's prediction for the 12 `mlx4_bus` sites (address order) is
checked against the bytes**, and it holds for a different reason. At
`140013F29` (Dell) the walk falls through `jne` (a real path), passes
`call 0x14000d348` with the base in R15, and **crosses `jmp 0x140014182` at
`140013f79`**. From there it runs in address order until `pop %r15` clears
the base before `ret`. Read for this site and for `140014046`, where the walk
crosses `jmp 0x14001417b` at `14001409c`. The other two sites, and the other
two builds, are not read; they are predicted the same because they are the
same code at the same addresses.

## Predictions

| # | prediction |
|---|---|
| N1 | the red passes: a `none` reached past a JMP reports `address_order`; a straight-line `none` reports `path` |
| N2 | **no outcome changes and no site moves between classes**, on any machine; only the route appears on `none` rows |
| N3 | HP: the one `none` (storport `1C0038269`) reports **`address_order`**. Read from the bytes: after the call, the walk crosses `jmp 0x1c00382b0` at `1c00382a6` **before** `mov 0x60(%rsp),%rdi` at `1c00382a8` clears the last copy, and it stops only at the later `ret`. (A first draft of this row said `path`, misreading that order.) |
| N4 | the 12 `mlx4_bus` `none`s report **`address_order`** |
| N5 | census `none` split by route per machine: no prediction beyond N3/N4 |
| N6 | `-t uir` and the differential unchanged; suites green; **tests +1** (one red, two cases, no guard); 14 reds |

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `semantic.c` `60d5a740272cead1`, `bin/translator`
`6af3b08c536c0ec5`. Census scripts **v3** (`park_census_v3.py` `69bd60e6`,
`park_agg_v3.py` `76ab964f`); v2 is kept. v2 would print every `none`
without its route, which would hide exactly the split this item adds. v3
adds the `/ao` suffix to `none` and nothing else.

| # | predicted | observed |
|---|---|---|
| N1 | the red passes | **one XPASS**, `sem_RED_ax_none_carries_a_route` |
| N2 | no outcome changes, no class moves; only the route appears on `none` | **held**: 0 class changes on every machine once the route is set aside |
| N3 | HP storport `none` → `address_order` (the corrected reading) | **`address_order`**. The first draft's `path` would have been wrong |
| N4 | the 12 `mlx4_bus` `none`s → `address_order` | **all 12**, 4 per machine |
| N5 | the `none` split: observed only | see below |
| N6 | suites green, tests +1, 14 reds | **held**: 400 tests across 27 suites, 14 reds. The lifter and decoder are untouched, so `-t uir` and the differential are unchanged by construction |

**`none` by route** (binary `6af3b08c`):

| machine | `none`, path | `none`, address order | `none` total |
|---|---|---|---|
| HP | 0 | 1 | 1 |
| Dell | 19 | 20 | 39 |
| ASUS (older) | 23 | 19 | 42 |
| ASUS (newer) | 24 | 22 | 46 |

**About half of the census's weakest column was reached past an
unconditional jump**, where the walk cannot vouch for the route. The
`path` half is not vouched for either, as the limit above states: a real
path, not necessarily the one on which the base is valid.
