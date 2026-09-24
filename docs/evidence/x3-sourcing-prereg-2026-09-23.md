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

**B. The domain assertion.** The guard `callgraph_scaf_domain_renders_as_itself`
is private `fd51ecc`; the suite reads 413 tests, 12 reds.

| # | predicted | observed |
|---|---|---|
| G1 | exactly 10 accepted | **held**: the guard prints `[accepted=10]` |
| G2 | all 10 render as themselves, directly and at the join; green | **held**: PASS |

**The guard was checked to discriminate.** In a throwaway copy of
`semantic.h`, the predicate was widened by one value (`<= SEM_CAT_DIAGNOSTIC +
1`). The guard then failed ("an accepted category has no name of its own").
The header was restored and diffed back to identical, and the guard passes.
**No live defect.** Widening the range and the encoding is one change under
one red, taken when values are chosen.

**D. The pin.** Search API queries were run for all 21 names, and their
responses are kept at `~/references/ms-learn/search/`. Qualifying pages were
fetched on 2026-09-23 (`~/references/ms-learn/FETCHED`,
`SHA256SUMS`). The derived line for each page is its own meta description.

| name | page | sha256 | derived line (the page's words) | vocabulary | agrees? |
|---|---|---|---|---|---|
| HalGetBusDataByOffset | `ddi/ntddk/nf-ntddk-halgetbusdatabyoffset` | `63ce5006aeb9…` | "retrieves information, starting at the offset, about a slot or address on an I/O bus"; and "The only supported BusDataType is PCIConfiguration" | PCI_CONFIG | **yes** |
| HalSetBusDataByOffset | `ddi/ntddk/nf-ntddk-halsetbusdatabyoffset` | `b54eaa3c9ffe…` | "sets bus-configuration data for a device on a dynamically configurable I/O bus"; BusDataType "can be PCIConfiguration" | PCI_CONFIG | **yes, weaker**: the page permits PCI configuration and does not say it is the only type, as the Get page does |
| KeQueryPerformanceCounter | `ddi/wdm/nf-wdm-kequeryperformancecounter` (also `ntifs`, `aa506cdd6901…`) | `01b3f30a4497…` | "retrieves the current value and frequency of the performance counter" | TIMING | **yes** |
| KeStallExecutionProcessor | `ddi/wdm/nf-wdm-kestallexecutionprocessor` (also `ntifs`, `725a330ebd50…`) | `05056aa07697…` | "stalls the caller on the current processor for a specified time interval" | TIMING | **yes** |

**The other 17 have no qualifying page.** Search returned nothing for 12 of
them. For HalBugCheckSystem, the two environment-variable routines,
HalTranslateBusAddress and KeFlushWriteBuffer it returned only forum threads
or index pages. **A second instrument, reported separately and not moving N:**
each of the 17 was also probed at the direct DDI URL pattern
(`ddi/{wdm,ntddk,ntifs,ntosp}/nf-<header>-<name>`). **0 of 17 exist.** The
probe was checked on known pages, which returned HTTP 200 (KeQueryPerformanceCounter,
HalGetBusDataByOffset).

| # | predicted | observed |
|---|---|---|
| N-HAL | **5** of 21 (range 4–7) | **4 of 21**. The point prediction **missed** by one, inside the range. The miss is **HalTranslateBusAddress**, which I expected from memory of the DDI reference. It has no page under either instrument today. What I recalled was not what is published |
| four | 4 → 4 pinned | **held**: **4 vocabulary-uncited → 4 pinned** |
| M | 0 disagreements | **held: M = 0**, named although zero. One of the four (HalSetBusDataByOffset) agrees on weaker wording |
| split | import directory 64, pinned page 5, none 16 | **import directory 64, pinned page 4, none 17** |

**X3's two numbers, as they will stand when values are chosen.**
- **85 of 85** names print a value.
- **68 of 85** carry a category from a source: 64 from the import directory,
  4 from a pinned page.
- **17 of 85 print `no-public-reference`.** All 17 are HAL names, and HAL is
  the one bucket already named a residue.

**And the vocabulary finding the order was chosen to preserve.** Before the
pin, the four were **4 of 146** vocabulary-uncited entries, and **146 of 146**
are uncited. The pin moved 4 and checked them: 4 agree, 0 contradict. **142
remain uncited**, never checked against any published source. That is the
bound on how much of the classifier rests on typed categories.

### Amended after owner review, 2026-09-23

**The negative on the 17, stated at its true width.** What was measured is
**no page at the four probed `nf-<header>-<name>` patterns** (wdm, ntddk,
ntifs, ntosp), plus search results that were **empty or index-only**. That is
not "no page". A routine documented under another header, on a legacy path,
or only inside a routines index is invisible to both instruments. **The
probe's control does not show coverage.** Its 200s came from pages search had
already found, which are known to follow the pattern. It shows only that the
probe works. **Two instruments that share a failure mode are one
instrument.** `no-public-reference` means exactly this: *no page at the four
probed patterns, and search returned nothing or index-only*. It does not mean
the routine is undocumented. The claim is not chased further.

**The HalTranslateBusAddress miss, named for what it was.** I predicted a
page because I remembered one. **A memory is not a source.** The prediction
was right to be made and is right to be recorded as a miss.

**HalSetBusDataByOffset is flagged here, not in the printed field.** Its
agreement with PCI_CONFIG is weaker than the other three ("can be
PCIConfiguration", not "the only supported"). The printed source record gets
no gradation for one name. **If PCI_CONFIG on this name is ever what a
decision turns on, this is the page to re-read first.**

**The larger finding goes to its own letter.** 146 of 146 uncited is **`(bi)`**,
opened in the register. It is not worked inside X3.

> **Vocabulary hash, 2026-09-24:** frozen at `b48923e8…` until 2026-09-24; superseded by `cd4278db…` (`(bl)`, `fix-bl-buffer-setup-prereg-2026-09-24.md`: three MDL routines DMA → BUFFER_SETUP). Every figure and citation above that names `b48923e8…` was measured against that table, and is left as written.
