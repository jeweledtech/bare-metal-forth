# The vocabulary's category definitions, read; (bl) re-read against them; (bi) rescoped (2026-09-24)

Owner ruling, 2026-09-24. Before any category changes, read the vocabulary's
own definitions of the categories in question, side by side with the page.
**Only a contradiction is a disagreement.** A page describing a different
aspect of the same call is not one. If the definitions do not exist, that is
the finding, and it is prior to `(bi)`.

## 1. The model that missed four times, recorded as a model

The (bi)-0 / 664-0 pass made four predictions and missed all four in one
direction: 150+ → **3**, ≥ 1 → **0**, 1 → **4**, 120 → **95**. That is one
wrong model, not four slips. **The model was: *the vocabulary and the import
analysis are healthier than they look*.** It predicted that the 213 unmoved
drivers were benign, that disagreements would be rare, and that most entries
were used. Every miss said otherwise. It is recorded here, because it is the
model, not the four numbers, that would mis-price the next pass.

## 2. Do definitions exist? Partly, as glosses and examples, never as criteria

There are three sources, found by one read of each:

| source | what it gives | carried into the translator? |
|---|---|---|
| `tools/driver-extract/driver_extract.h` (the enum's origin) | **one-line glosses**: DMA "DMA buffer operations"; PNP "Plug and Play"; REGISTRY "Registry access"; MEMORY_MGR "Memory manager calls"; IO_MGR "I/O manager (some parts useful)"; the hardware block "THESE ARE WHAT WE WANT" | **No.** `semantic.h`'s copy of the enum kept the values and **dropped the glosses**, except DEVICE_IO, BIOS_INT, DOS_API and DIAGNOSTIC, which it added. A fix that does not travel to a successor (rule 17), in its "definition" form |
| `docs/ARCHITECTURE-TRANSLATOR.md` (private) | **definition by example**: DMA "IoAllocateMdl, MmGetPhysicalAddress"; PNP "IoRegisterDeviceInterface"; and so on | not code |
| group comments in `SEM_API_TABLE` itself | for some groups, a **rationale**. PnP: "Device-object lifecycle and stack plumbing (WDK: device objects are the I/O manager's representation, not hardware access)" | yes, in the frozen table |

**None states an inclusion criterion**, a rule under which a new name could be
decided without asking its author. So the categories can be adjudicated only
loosely: against a gloss, an example list and a rationale. That is the
finding the ruling anticipated, in its partial form. **"146 uncited" measured
the second-order problem.** A citation can only be checked against a meaning,
and the meanings are glosses.

## 3. (bl), re-read: all four survive

| name | typed | the vocabulary's own meaning | the page | verdict |
|---|---|---|---|---|
| IoCreateDevice | PNP | the PnP group's rationale: "device-object lifecycle and stack plumbing" | "creates a device object for use by a driver" | **fits the group definition** |
| IoDetachDevice | PNP | same group | "releases an attachment between the caller's device object and a lower driver's device object" | **fits** |
| IoOpenDeviceRegistryKey | PNP | same group; gloss "Plug and Play" | "returns a handle to a registry state location for a particular **device instance**" | **a different aspect** (a registry call about a PnP device instance), not a contradiction |
| MmBuildMdlForNonPagedPool | DMA | gloss "DMA buffer operations"; the doc's own DMA examples are MDL and physical-address routines (`IoAllocateMdl`, `MmGetPhysicalAddress`) | updates an MDL "to describe the underlying physical pages" | **fits the gloss and the examples** |

**M = 0 contradictions.** The (bi)-0 outcome's "4 disagreements" answered
*what does the call do* where the vocabulary asks *what is the call for*.
That is the error the ruling named, and it is withdrawn here. **(bl) is not
established as four mislabels.**

**What remains is a definitional question, not a labelling one.** The DMA
gloss admits MDL bookkeeping. The hardware block's gloss is a purpose ("THESE
ARE WHAT WE WANT"), not a criterion. So whether MDL construction is *hardware
access* is exactly what no written definition decides. The post-hoc
counterfactual (~~290 hardware functions on 114 drivers~~ **288 on 113** when recomputed on the fixed discovery, 3 drivers emptied)
**prices that question**; it is not evidence that DMA is wrong. It stays
labelled post hoc and is never quoted as confirmation.

**Proposed restatement of (bl), for the owner:** *the categories have
glosses and examples, not inclusion criteria*. The first step is writing a
criterion for the hardware block, beginning with DMA, since that is where a
definition moves counts. No red until a criterion exists to test against.

## 4. (bi), rescoped by its own second number

**Free count, no pages:** of the 142 uncited entries, **53 are hardware-typed**
(PORT_IO 13, DMA 11, MMIO 11, DEVICE_IO 8, INTERRUPT 6, PCI_CONFIG 2, TIMING
2). **18 of those 53 are imported by at least one of the 1,322.** Only
hardware-typed categories can move a count. Everything outside the 18 prints
`vocabulary-uncited`, which is honest and sufficient.

| name | typed | drivers |
|---|---|---|
| IoFreeMdl | DMA | 415 |
| IoAllocateMdl | DMA | 406 |
| KeDelayExecutionThread | TIMING | 401 |
| MmBuildMdlForNonPagedPool | DMA | 316 |
| KeInsertQueueDpc | INTERRUPT | 212 |
| MmUnmapIoSpace | MMIO | 192 |
| MmMapIoSpaceEx | MMIO | 183 |
| MmGetPhysicalAddress | DMA | 117 |
| ZwDeviceIoControlFile | DEVICE_IO | 79 |
| IoGetDmaAdapter | DMA | 72 |
| KeSynchronizeExecution | INTERRUPT | 58 |
| MmFreeContiguousMemory | DMA | 57 |
| IoDisconnectInterrupt | INTERRUPT | 51 |
| IoConnectInterruptEx | INTERRUPT | 49 |
| IoConnectInterrupt | INTERRUPT | 42 |
| MmMapIoSpace | MMIO | 34 |
| MmAllocateContiguousMemory | DMA | 14 |
| NtDeviceIoControlFile | DEVICE_IO | 9 |

**(bi) is bounded: 18 names, not 142.** The four most-imported are exactly
the question §3 leaves open. IoFreeMdl, IoAllocateMdl and
MmBuildMdlForNonPagedPool are MDL routines typed DMA. KeDelayExecutionThread
is a thread sleep typed TIMING. So pinning them without a written criterion
would repeat §3's error at scale. **(bi)'s order is: criterion first, then
the 18.**

## 5. Method notes, banked

- **The v1 voiding is banked** as
  `measure-664-0-v1-voided-by-p4-2026-09-24.log`. It gives the P4 figure for
  v1 (8 of 179) against v2 (179 of 179), with the site-form counts that show
  why (2,274 `rex.W` tokens read as mnemonics). **A control that voids your
  own headline is the control earning its keep.**
- **The counterfactual keeps its label.** It was run after seeing a finding,
  to price it. It is evidence about that finding's **size**, never evidence
  **for** it.
