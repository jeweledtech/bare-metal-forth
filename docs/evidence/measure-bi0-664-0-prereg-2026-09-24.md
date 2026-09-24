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

---

## Outcome

*(below this line, from the artefact only)*

**Inputs:** `translator.pre` `f8e18de7…`, current build `343e89fa…`; objdump
2.42; pefile 2024.8.26. Scripts and results are in
`~/corpus/tools-2026-09-24/` with `SHA256SUMS`. Pages are in
`~/references/ms-learn/bi0/` (54 files hashed). No binary and no page enters
a repository.

### 664-0

**The first run was voided by its own control.** v1 (`m664.v1.py`
`7bdc0e3f…`) took objdump's `rex.W` prefix token for the mnemonic, so every
`48 FF 15` call (`rex.W call *…(%rip)`) was classed D. **P4 failed: 8 of 179**
moved drivers showed a moved site, against a prediction of 179. v2
(`ddfa0a55…`) skips prefix tokens. **Only v2's numbers are used below**; v1's
result is kept, labelled voided.

| # | predicted | observed (v2) |
|---|---|---|
| P1 | ≥ 150 of the 213 have every site in class A | **missed: 3.** Class A sites (a `call [slot]` in an already-classified function) are on **147** drivers (732 sites). But **210** of the 213 also have class D sites |
| P2 | class C (outside every lifted function) ≥ 1 | **missed: 0.** Every reference site is inside a lifted function |
| P3 | E = 0 | **held**: every importer references what it imports |
| P4 | control: all 179 moved drivers show a moved site | **held**: **179 of 179** (790 moved sites) |
| — | class B (call in a function unclassified before and after) | **0** on both populations |

**Neither reading named in the ruling is the answer. A third one is.** The
**D** sites on the 213 are 273 `jmp [slot]` and 288 `mov reg,[slot]`.
- **The `jmp` sites are import thunks**: functions that are only
  `jmp [__imp_X]` followed by `int3` padding, reached by a direct call
  (sampled on three drivers).
- **66 of the 213 reach their class library only through thunks.** All 66
  are WDFLDR importers. The analyzer resolves an import edge only on
  `UIR_CALL`, so a thunk stays unclassified, and so do its callers. **That is
  a defect, and it is now `(bk)`** with its red and a harness control (the
  same fixture with `call` passes).
- **The `mov` sites load an import's address as a value.** In the five
  sampled it goes into RCX as the first argument of a local call. That is an
  address taken, not a call at that site, so it is **not** called a defect.
  A heuristic for what follows each `mov` was too loose (it matched any
  RIP-relative call) and is **not reported**.
- Across the 392, **75** drivers have thunks.

**The second number for the 1,135.** Of the 392 drivers a class DLL *names*,
~~**179 (46%)**~~ **178 (45%)** had any function change bucket when the names got categories (**recomputed on the fixed discovery** (`rerun-on-fixed-discovery-2026-09-24.md`); the classes below were also recomputed: A on 148, all-A 3, D on 211, B/C/E 0, thunk-only 66, which is the same shape).
The rest are 147 whose direct calls sit in already-classified functions and
66 whose only use goes through thunks the analysis does not follow. How many
of the 66 a `(bk)` fix would move is **not predicted here**.

### (bi)-0

**The sample** (seed 20260924, n = 30, `bi0-sample30.txt`): CreateFileW,
DbgBreakPointWithStatus, ExAllocatePool, ExFreePool,
ExfInterlockedInsertTailList, IoCompleteRequest, IoCreateDevice,
IoDetachDevice, IoFreeIrp, IoGetCurrentIrpStackLocation,
IoOpenDeviceRegistryKey, IoSetCompletionRoutine, IofCallDriver,
IofCompleteRequest, KeAcquireInterruptSpinLock, KeClearEvent,
KeInitializeEvent, KeQuerySystemTime, KfReleaseSpinLock,
MmBuildMdlForNonPagedPool, MmUnlockPages, NtDeviceIoControlFile,
PoRequestPowerIrp, READ_PORT_ULONG, READ_REGISTER_UCHAR, ReadFile,
RtlAnsiStringToUnicodeString, ZwCreateKey, ZwSetValueKey, memmove.

**Controls held.** The 3 invented names were found by **no** instrument. The
X3 four were found by **all three**. The index instrument read the kernel
index plus 22 header indexes: **1,818** distinct routine names.

| # | predicted | observed |
|---|---|---|
| Y | 27 of 30 pinnable (22–30) | **25 of 30**. The point prediction missed; the result is inside the range. Not found: CreateFileW and ReadFile (Win32, documented outside `/ddi/`, which the method excludes), memmove, ExfInterlockedInsertTailList and IofCompleteRequest |
| M | 1 disagreement (0–3) | **missed: 4 of 25**, above the range (the four are in the table below) |
| U | 120 of 142 imported by ≥ 1 driver (100–142) | **missed: 95 of 142**, below the range. The 47 unused include Win32 names, inline macros (IoCompleteRequest, IoGetCurrentIrpStackLocation, IoMarkIrpPending) and the x86 HAL port and register routines (`READ_PORT_*` / `WRITE_PORT_*` / `*_REGISTER_*`). That grouping is a reading of the names. The count is over the 1,322 x64 drivers only; the PE32 controls do import `READ_PORT_UCHAR` |

**A deviation from the registered method.** The probes were run as
`nf-<h>-<name>` only. The `ns-`/`nc-` forms registered for variables and
structures were **not run**. All 30 sampled names are routines, so the
omission cannot have hidden a routine's page. It is still a departure from
what was written, and it is recorded as one.

**The widened method paid once.** `KeQuerySystemTime`'s page lives at
`…/nf-wdm-kequerysystemtime-r1`. The `nf-<h>-<name>` probe cannot guess that
URL. The index listed it, and the listed URL redirects (301) there. That is a
concrete case of the probe's failure mode, the one the X3 negative was
narrowed for.

> **Withdrawn 2026-09-24** (`vocabulary-definitions-read-2026-09-24.md` §3).
> Read against the vocabulary's own glosses, examples and group rationale,
> **none of the four contradicts its category: M = 0.** The table below
> compared what each call *does* with what its category says it is *for*. It is
> kept as the record of that reading, not as a finding.

**The four disagreements** (the page's own words against the typed category):

| name | vocabulary | page | drivers importing |
|---|---|---|---|
| IoCreateDevice | PNP | "creates a device object for use by a driver" | 496 |
| IoDetachDevice | PNP | "releases an attachment between the caller's device object and a lower driver's device object" | 251 |
| IoOpenDeviceRegistryKey | PNP | "returns a handle to a registry state location for a particular device instance" | 247 |
| MmBuildMdlForNonPagedPool | **DMA (hardware)** | "updates [an MDL] to describe the underlying physical pages" | 316 |

**None of the pages says the typed category is wrong.** Each describes the
call as a different kind: device-object plumbing (IO_MGR), registry
(REGISTRY), memory management (MEMORY_MGR). Calling that a disagreement is
**my reading**, and it goes to the owner for adjudication. Per the X3 ruling
it is **not fixed here**. It is opened as `(bl)`.

**The second number for (bi), measured for the one that moves buckets.** The
three PNP names are scaffolding kinds, and any scaffolding replacement moves
only drop-reason text, not a bucket. That is reasoned from `sem_is_scaffolding`
and not run. **MmBuildMdlForNonPagedPool's DMA is a hardware category**, so it
was measured.
- **Instrument:** a counterfactual build in a scratch copy, never in a
  repository. It differs from the shipped source in **exactly one line**,
  DMA → MEMORY_MGR (diffed). Its binary is `1779b172…`, run over the 1,322
  with 0 empty outputs.
- A first counterfactual run produced **1,322 NOJSON**, from stale objects in
  the copied `build/`. It was caught by the empty-output check, rebuilt clean
  and re-run. **The first run's "0 changes" was not read as a result.**
- **Result:** ~~**114 drivers change buckets.** **290 hardware functions** go
  (1.8% of the 16,400 on the 921 drivers with any)~~ **Recomputed on the fixed discovery** (`rerun-on-fixed-discovery-2026-09-24.md`): **113 drivers, 288 hardware functions** (1.95% of **14,738**), +325 scaffolding, −37. The struck line follows: +327 scaffolding, −37
  unclassified (conserved), and **3 drivers lose every hardware function
  they had**.

**One uncited category on one name holds up ~~290~~ 288 hardware functions** (recomputed). That
is the answer to "which of the 146 would a citation move". **This number was
not pre-registered.** It was measured after M was known, to price M. It is
labelled that way, and no prediction is scored on it.

**Stopping rule:** Y = 25 ≥ 15, so the rule does not say stop. **What the
sample says instead:** yield is high (25 of 30), and the price is
concentrated. 4 of 30 sampled entries are unsupported by their page, all four
heavily imported, and one moves ~~290~~ 288 hardware functions (recomputed). A sample of 30 gives
4/30 ≈ 13% as a point estimate. That is too few to state a population count,
and none is stated.

**Independent checks:**
- 664-0: objdump sites, UIR ownership, report buckets, and the P4 control
  (which voided v1).
- (bi)-0: search, probe, index, and two control sets.
- U: pefile.
- The counterfactual, labelled post hoc.
