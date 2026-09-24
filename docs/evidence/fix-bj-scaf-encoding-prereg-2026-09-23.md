# (bj) change 1: the scaffolding encoding, no new values: pre-registration (2026-09-23)

**Written before any code.** Owner ruling, 2026-09-23: split X3's values step
in two. **Change 1 is the encoding, with no new values.** Change 2 (three
class-library categories and `no-public-reference`) comes after, under its
own pre-registration. `(bj)` is X3's letter. Outcomes go BELOW the line.

## What is wrong with the encoding, from source (`x3-sourcing-prereg` and exit §6)

- `sem_is_scaffolding()` (`semantic.h`) is a range test:
  `IRP(0x80)..DIAGNOSTIC(0x88) || DOS_API(0x90)`.
- The mask writer (`semantic.c:788–792`) sets bit `cat − 0x80`, with DOS_API
  hand-mapped to bit 9.
- The renderer (`:1731–1734`) reads bits 0–9 and maps bit 9 back to DOS_API.

The accepted set, the bit layout and the render order are therefore **three
separate statements of one fact, kept in agreement by arithmetic**. Any value
added at 0x89 aliases DOS_API; any value at 0x8A–0x8F is written and never
rendered.

## The change

**One declaration: the list macro `SEM_SCAF_LIST` (`semantic.h`)**, the ordered
list of scaffolding categories: IRP, PNP, POWER, WMI, REGISTRY, MEMORY_MGR, SYNC,
STRING, DIAGNOSTIC, DOS_API. That is today's ten, in today's bit order.
- **The range:** `sem_is_scaffolding(cat)` becomes "cat is in the list".
- **The layout:** a category's bit is its **index in the list**, through one
  function, `sem_scaf_bit()`. The indices are an enum generated from the same
  macro; any value not in the list gets −1.
- **The render order:** the renderer walks the list.
- **Capacity:** `_Static_assert(SEM_SCAF_COUNT <= 16)` against the `uint16_t` mask.
  The width is kept: 10 + 3 = 13 fits, and widening it without need would be
  a choice made for no measured reason.
- **The join** (`semantic.c:992–993`) ORs masks. It has no arithmetic of its
  own, so it is correct under any layout **only if every writer uses the same
  layout**. It is kept as-is, and **the guard exercises it for every accepted
  value** (A inherits from B). That is where this change is most likely to
  break silently, so it is tested on every value, not on one.
- The comments at `semantic.h:210`, `:256` and `:429` are rewritten in the
  same commit.
- `sem_is_scaffolding()` **stays `static inline`** and becomes
  `sem_scaf_bit(cat) >= 0`. (A first draft moved it into `semantic.c`, but
  every translation unit that uses the header's inline
  `sem_function_is_scaffolding()` would then have to link `semantic.c`.) Its
  **12 callers**
  (4 direct, 8 through `sem_function_is_scaffolding()`, census in
  `x3-sourcing-prereg` §B) see the same answers **by construction**: the list
  equals today's range.

**Adding a category after this is one row in one list.** The range, the bit
and the render position follow from it. The next category does not have to
find a free bit by hand, and a value cannot be "picked because it misses the
occupied bits".

## Where the ruling's red does not survive, stated rather than routed around

The ruling asks for the red to be *"the existing round-trip guard, now gating
the **widened** accepted range"*. **Change 1 widens no accepted range**, and
that is forced, not chosen.
- To widen the accepted set numerically without new values, the predicate
  would have to accept values that are **not enum members** (reserved
  slots). Each would then need a rendered name. The only honest name for an
  unassigned value is a number, so the round-trip property ("renders back as
  itself") would be unsatisfiable, or satisfied by printing a slot number.
- The other way to widen is to define the class-library values, and those are
  change 2.

**So change 1 is a behaviour-preserving change of representation, and it has
no red.** No correct test can fail before it and pass after it on today's
values, because on today's values nothing is meant to change. **Its gate is
the must-not-move set (C1–C4), plus the guard staying green, plus
discrimination re-demonstrated at the new boundary (C5).** The first red of
`(bj)` is change 2's. **This is a deviation from the ruling as written, for
the owner's review.**

## The tests, rewritten from the specification (rule 30)

The specification is: *bit i of `scaf_cat_mask` means the i-th entry of
`SEM_SCAF_LIST` was seen*. Each expected value is written from that sentence, not read off
the product.
- `test_semantic.c:491` currently tests bit `(IRP − IRP)`. It becomes "bit
  `sem_scaf_bit(SEM_CAT_IRP)` is set, **and it is the only bit set**". IRP is
  entry 0, so bit 0, which is the value the specification gives.
- `test_callgraph.c:191` currently tests "mask ≠ 0". It becomes "A's inherited
  mask **equals** B's mask, which is exactly IRP's bit". It asserts the join's
  result as a set, not as nonzero.

## Predictions

| # | prediction |
|---|---|
| C1 | **0 of 1,322** kernel-driver reports change: sha256 of each full report, before (`translator` `03c1e890…`, hashes banked) against after |
| C2 | **0 of 12** UIR files and **0 of 16** differential dumps change |
| C3 | **X2 stays 1,322 of 1,322**, a consequence of C1, stated separately because it is the exit figure |
| C4 | suites green; tests 413 → 413 (two rewritten, none added); reds 12 |
| C5 | **Discrimination at the new boundary**, in a throwaway copy, then restored and diffed identical. (a) A list row whose category has no name of its own (SEM_CAT_OBJECT appended) makes the guard fail. (b) A 17th row fails the build at the `_Static_assert`. |

**If any of C1–C3 moves, the encoding did something only the values change
was meant to do.** That is the catch the split exists for: stop, and read the
moved report from its bytes.

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `bin/translator` before `03c1e890068a86f7`, after
`f8e18de77b58bfa7`, built from private `0175461`, mirror identical.
`dump_starts` `f4cee936de91769a`. Report hash lists
`~/corpus/tools-2026-09-23/bj1-reports-{pre,post}.tsv`.

| # | predicted | observed |
|---|---|---|
| C1 | 0 of 1,322 reports change | **held**: **0 of 1,322**. Every full report was sha256'd before and after; the two hash lists are **byte-identical files** (both `eef4d0f954aa…`). **0** of the before-outputs were empty, so this is not two empty runs agreeing |
| C2 | 0 of 12 UIR, 0 of 16 dumps | **held**: **0 of 12** UIR, **0 of 16** dumps, and 0 of 12 snapshot reports differ from the post-`(bh)` snapshot |
| C3 | X2 stays 1,322 of 1,322 | **held**, as a consequence of C1: the reports are byte-identical, so `import_family` is unchanged on every driver |
| C4 | 413 tests, 12 reds, two tests rewritten | **held**: 413 across 27 suites, 12 reds, register union matches; the guard prints `[accepted=10]` |
| C5 | a nameless row fails the guard; a 17th row fails the build | **held**. (a) `X(OBJECT)` appended: the guard fails with "an accepted category has no name of its own". (b) Seven rows appended (17 in all): the build stops at `static assertion failed: "scaf_cat_mask is uint16_t"`. The header was restored and diffed identical to the private repo, and the rebuilt binary hash is again `f8e18de7…` |

**Nothing moved, as the split required.** `(bj)` has no red yet; its first
red is change 2's. The deviation from the ruling (no red for change 1, and
why) is stated above the line and stands for review.

### Amended after owner review, 2026-09-23

**Three independent checks, not five.** C3 is *entailed* by C1: identical
report bytes cannot carry a different `import_family`. C1 and C2 are **one
instrument**, byte comparison of outputs, pointed at two file sets. So the
independent checks are **three**: output invariance (C1/C2/C3), suite state
(C4) and discrimination (C5). *A count of predictions that includes entailed
ones is a number answering a different question.* The commit message of
`1b39e4a` says "five of five" and cannot be amended without a rewrite; this
paragraph supersedes it.

**No red, on three conditions.** "A behaviour-preserving change has no red"
holds here only because all three are met:
1. the must-not-move figures were pre-registered and are byte-exact;
2. discrimination was re-demonstrated at the new structure;
3. the property the change buys is named, as something no test can express:
   *before, the range and the bit layout were separate arithmetic that
   happened to agree; now they are one list and cannot disagree.*

**The C5 throwaways are banked.** The first runs' output was not kept, so both
were **re-run** for banking: `fix-bj-c5a-throwaway-2026-09-23.log` (a
nameless row fails the guard) and `fix-bj-c5b-throwaway-2026-09-23.log` (a
17th row stops the build at the static assertion; then the restore check,
header identical and guard green).

**A mask value on disk: none as bits, but the order is frozen.**
- **Bits.** No output site prints `scaf_cat_mask`, no struct is written
  whole, and the translator's only file write is its own output. A search of
  both repositories, `~/corpus/tools-*`, `~/references` and the session
  scratch finds the field name only in source copies and in these evidence
  documents.
- **Order.** The mask renders as **names in list order**, and that order is
  on disk:
  - `test_semantic.c:575` asserts `"IRP+DIAGNOSTIC"`. The reader census
    missed it, because it reads the rendered string, not the mask.
  - The i8042 demo script (private) prints a hard-coded
    `IRP+PNP+MEMORY+SYNC+DIAGNOSTIC`.
  - The committed `demo-i8042-transcript.txt` and `demo-i8042-copy.md`
    quote it.
  - `ARCHITECTURE-TRANSLATOR.md` quotes `via:IRP+DIAGNOSTIC`.
  - The banked `bj1-reports-*.tsv` hash report bytes that contain it.

  **The order is therefore frozen, append only**, and the header comment on
  `SEM_SCAF_LIST` now says so and names these. A fourth category goes at the
  end, where it moves no existing reason.
