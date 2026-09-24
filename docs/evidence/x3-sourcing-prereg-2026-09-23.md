# X3 sourcing: the four recorded, the domain assertion, and the pin, pre-registered (2026-09-23)

**Written before any page is read and before any test runs.** Owner ruling,
2026-09-23, gives the order: domain assertion (the red, if any) → exit
sourcing amendment with its reason → **predict N** → pin the pages → record N
and M → then values. **No category value is chosen in this document.**
Outcomes go BELOW the line.

## A. The four, recorded as `vocabulary-uncited` before anything is pinned

`HalGetBusDataByOffset` and `HalSetBusDataByOffset` (PCI_CONFIG),
`KeQueryPerformanceCounter` and `KeStallExecutionProcessor` (TIMING). **Source
today: the frozen vocabulary (`b48923e8…`), with no citation.** Someone typed
these when the table was built, and they have not been checked since.

**How much of the vocabulary rests on the same footing, measured.** Of the
**146** entries in the frozen table (the extraction rule of
`vocab-freeze-tier1-prereg-2026-09-20.md`), **0 cite a pinned source**. No
entry carries a URL, a document version or a section. Four group comments name
"WDK" generically (e.g. "debug plumbing, WDK-documented"), with no edition and
no page. So **146 of 146 are vocabulary-uncited**, and the four in X3's 85 are
the part of that population X3 happens to touch.

## B. The domain assertion, before any layout change

**The property (owner ruling, 2a):** *every value `sem_is_scaffolding()`
accepts renders back as itself.* It is asserted over the predicate's whole
domain, not over the values in use (rule 33).

**The predicate, read from source** (`semantic.h`):
`(cat >= SEM_CAT_IRP && cat <= SEM_CAT_DIAGNOSTIC) || cat == SEM_CAT_DOS_API`,
that is 0x80–0x88 and 0x90.

**The guard,** `callgraph_scaf_domain_renders_as_itself` in
`test_callgraph.c`, runs every value 0–255 through `sem_is_scaffolding()`. For
each value it accepts, it builds B (one IAT call to an import whose category
is that value) and A (a direct call to B), then analyses and propagates.
- B's drop reason must equal `sem_category_filter_name(v)`, and that name
  must not be `OTHER`. This tests the writer (`semantic.c:789/791`) and the
  render loop (`:1731`).
- A's drop reason must equal `via:` + that name. This tests the join
  (`:992–993`), where masks merge.
- It prints the accepted count, so a changed predicate is visible.

| # | prediction |
|---|---|
| G1 | the predicate accepts **exactly 10** values, {0x80–0x88, 0x90}, the occupied set |
| G2 | all 10 render as themselves, directly **and** at the join, so the guard is **green today** |

If G1 and G2 hold, there is **no live defect**. Widening the range and
widening the encoding then become **one change under one red**, written when
values are chosen. If G2 fails, that failure is a live defect with its own
letter and a red before any layout change.

**Census of `sem_is_scaffolding()` callers** (confirming its range against
every consumer, not only the mask path): `semantic.c:785` (the mask writer's
branch), `semantic.c:1563` and `:1580` (the text report's import summary and
list), `semantic.h:355` (inside `sem_function_is_scaffolding()`). That last
function has **8** call sites: `translator.c:351`, and `semantic.c:862`,
`:929`, `:971`, `:1008`, `:1599`, `:1948`, `:1969` (plus a comment at
`semantic.h:377`). A widened range changes what **all** of them accept.

**`scaf_cat_mask` census, completed per the ruling:**
- The join, `semantic.c:992–993`, is a **reader and a writer** where masks
  merge.
- `test_callgraph.c:191` and `test_semantic.c:491` get their expectations
  rewritten **from the new layout's specification**, not read off the product
  (rule 30).
- The layout comments `semantic.h:210`, `:256`, `:429` change in the same
  commit as the layout.

## C. The exit's sourcing, amended, with its reason

**"From the DDK" was unsatisfiable as written.** Headers carry signatures, not
categories. The source is named per part:

| part | names | source |
|---|---|---|
| CLASSPNP, portcls, WDFLDR | 64 | **the import directory**: which DLL a name is imported from, observed per name in the bytes. Categories mirror the driver-level families (three values, not one) |
| HAL | 21 | **Microsoft Learn reference pages, pinned** (URL, retrieval time, sha256 of the fetched bytes, and one derived line per name). The bytes stay outside every repository, as with the SDM and the corpus |

**This changes the sourcing, not the count.** X3 stays **85 of 85 print a
value**. It gains a second number: **N of 85 carry a category from a pinned
source**. A HAL name whose page does not state what the call does prints
`no-public-reference`. It is never a category inferred from its spelling.

**X3 pins, compares and reports; it does not edit the vocabulary.** If a
pinned page contradicts one of the four hand-assigned categories, that is a
defect in the frozen vocabulary. It takes its own letter and its own red, and
the hash `b48923e8…` is not changed inside X3.

## D. The pin: method, then predictions

**Method, fixed before any fetch.**
- For each of the 21 HAL names, query Microsoft Learn's public search API
  (`https://learn.microsoft.com/api/search?search=<name>&locale=en-us`).
- **A page qualifies** only if its title names exactly that routine or
  variable and it sits under the Windows driver API reference
  (`/windows-hardware/drivers/ddi/`).
- Fetch the qualifying page. Record its URL, the retrieval time and the sha256
  of the fetched bytes. Store it at `~/references/ms-learn/`.
- **A name counts toward N only if the page states what the call does.** A
  page that says only "reserved for system use", or gives a signature with no
  description, does not count. Neither does a name with no qualifying page.
- The one derived line per name is quoted from the page's own description.

**Predictions, from my knowledge of the public DDI reference, before reading
any page.**

| # | prediction |
|---|---|
| N-HAL | **5 of 21** HAL names have a qualifying page that states what the call does: HalGetBusDataByOffset, HalSetBusDataByOffset, KeQueryPerformanceCounter, KeStallExecutionProcessor, HalTranslateBusAddress. **Range 4–7.** The other 16 (the interrupt-routing, crash-dump DMA, environment-variable, processor-id and bug-check names, the two `Kd*ComPortInUse` variables, KeFlushWriteBuffer and x86BiosCall) are predicted `no-public-reference` |
| four | all 4 vocabulary-uncited names pin: **4 → 4 pinned** |
| M | **0 disagreements** among the four: the pages describe PCI configuration access for the two bus-data routines, and a performance counter and a processor stall for the two Ke routines, matching PCI_CONFIG and TIMING |
| split | the 85 by source at exit: **import directory 64, pinned page 5, none 16** |

---

## Outcome

*(below this line, from the artefact only)*
