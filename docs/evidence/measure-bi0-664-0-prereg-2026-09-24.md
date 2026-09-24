# Two cheap measurements before either build: (bi)-0 and 664-0: pre-registration (2026-09-24)

**Written before either runs.** Owner ruling, 2026-09-24. Both items' headline
numbers count what can be *reached*, not what reaching would *change*:
- **1,135 of 1,322** counts drivers a DLL rule can *name*.
- **146** counts vocabulary entries that a citation *could* touch.

Get the second number for each, then order the builds by what they say. No
build is chosen here. Outcomes go BELOW the line.

## First, the two checks on change 2 (answered, not measured here)

- **Pinned and uncited print differently in the product.** On the HP eight:
  4 distinct imports print `pinned-page`; 79 other vocabulary hits print
  `vocabulary-uncited`; 39 print `import-directory`; 497 print `none`.
- **The precedence between the tables is now stated in the header**
  (private `7ca779e`; binary unchanged, `343e89fa…`). One latent case is
  named there and measured:
  - the pin table is keyed by (DLL, name), the vocabulary by name alone;
  - so a pinned routine imported from another DLL would print
    `vocabulary-uncited`;
  - across the 1,322, all imports of the four pinned routines come from
    `hal.dll` (HalGetBusDataByOffset 24, HalSetBusDataByOffset 11,
    KeQueryPerformanceCounter 315, KeStallExecutionProcessor 160);
  - so this is **zero measured, latent**.

## 664-0: of the 213 class-DLL importers that moved nothing, why

(bj) V4 found 213 of the 392 CLASSPNP / portcls / WDFLDR importers with no
bucket change. There are two readings, and one measurement separates them.
The measurement also runs on the **179 that moved**, as the control.

**Three instruments, none of them the report's own bucket counts:**
1. **Reference sites, independent of the translator.** `objdump` (GNU
   Binutils 2.42) `-d` over every executable section. Each class-library IAT
   slot's virtual address comes from `pefile` (the import directory's thunk
   RVAs). A reference site is any instruction whose RIP-relative operand
   objdump resolves (`# 0x…`) to such a slot. Its **form** is recorded:
   `call [slot]`, `jmp [slot]`, or other (`mov`/`lea`/…).
2. **Which function holds a site, as the translator sees it.** `translator -t
   uir` prints `function @ addr` and the address of every lifted instruction.
   A site is **in a function** if its address is one of that function's
   lifted instruction addresses, and **outside** if no lifted function
   contains it.
3. **That function's bucket before and after change 2**, from the report of
   `translator.pre` (`f8e18de7…`) and of the current build (`343e89fa…`), by
   the function's address in `hardware_functions` / `scaffolding_functions`
   / `unclassified_functions`.

**Each site gets one class:**

| class | meaning | reading |
|---|---|---|
| A | `call [slot]`, in a function already hardware or scaffolding before change 2 | **(a) already classified**: the plausible reading |
| B | `call [slot]`, in a function unclassified both before and after | the analyzer saw the function but did not attribute the call: an analysis fact |
| C | any form, outside every lifted function | **(b) never reached by the analysis** |
| D | a form other than `call [slot]`, inside a function | reached as code, but not as an IAT call edge (e.g. a `mov` of the pointer) |

A driver with **no reference site** to any class-library slot is counted
separately: **imported and never referenced in code** (E).

**Predictions**, from what I know of how these drivers are built, before any
reading:

| # | prediction |
|---|---|
| P1 | on the 213, class **A dominates**: at least 150 of the 213 drivers have **every** class-library site in class A |
| P2 | class **C is non-zero**: at least 1 driver has a site outside every lifted function |
| P3 | **E = 0**: every importer references what it imports |
| P4 | control, the 179 that moved: **every** one has at least one site in a function that was unclassified **before** and scaffolding **after** change 2. That is the mechanism V4 counted; it checks that the instrument sees what moved |

## (bi)-0: pinnable yield on a drawn sample of the 142

**The sample:** Python `random.Random(20260924).sample()` over the 142
uncited names, sorted by name first, n = **30**. It is drawn before any page
is looked up, and the list is recorded in the outcome.

**The widened method,** three instruments, each widening the X3 pin:
1. **Search API**, as in X3.
2. **Direct probes** over a wider header set: `wdm, ntddk, ntifs, ntosp,
   ntddndis, ndis, wdmsec, ntstrsafe, procgrp, miniport, storport, iointex,
   pepfx, wdfdevice`, as `ddi/<h>/nf-<h>-<name>` and, for a variable or
   structure, `ns-`/`nc-`.
3. **Index membership.** The Windows kernel DDI index page (`ddi/_kernel/`)
   and the header index pages it links to, fetched once, with every
   `/ddi/…` link to a page titled with the routine collected. This finds
   pages by listing, not by URL pattern, so it **does not share the probe's
   failure mode**.

**Controls, not drawn from found pages:** 3 names known absent (made-up
routine names), which must be found by **no** instrument, and the X3 four,
re-run through the widened method, which must be found. A control that fails
voids the run.

**A name is pinnable** if any instrument finds a `/ddi/` page titled with the
routine that states what it does. For each pinnable name, its vocabulary
category is compared with the page, as X3 did.

| # | prediction |
|---|---|
| Y | **yield 27 of 30** pinnable (range 22–30). These are mostly ntoskrnl `Io`/`Ke`/`Ex`/`Rtl`/`Mm` routines, which I expect are documented |
| M | **disagreements: 1** (range 0–3) among the pinnable. The categories were typed by hand |
| U | **usage, the second number:** of the **142**, the number imported by **at least one** of the 1,322 drivers (by bytes, pefile), predicted **120** (range 100–142). An entry no driver imports is one a citation cannot move in any report |

**Stopping rule, stated now.** If Y is below 15 of 30, (bi)'s answer is to
**print the source honestly and stop**, not to run a campaign. `category_source`
already prints it.

**Independent checks:** 664-0 is three instruments with one control (P4).
(bi)-0 is three instruments with two control sets. Usage (U) is a pefile
count. **Five in all.**
