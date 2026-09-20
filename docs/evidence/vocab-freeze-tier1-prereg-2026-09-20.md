# Classifier vocabulary: freeze, coverage, and tier-1 pre-registration (2026-09-20)

Owner condition, 2026-09-20: before a single name is added, freeze and
hash the vocabulary, name its coverage by bytes, and pre-register what
widening should change. The alias table taught this arc that an
unfrozen score-moving knob makes every later comparison meaningless;
`is_hardware` is the same object one layer up.

## The freeze

**Extraction rule** (stated so the hash is reproducible, not copied
from a run): the lines of `src/ir/semantic.c` from the line matching
`^const sem_api_entry_t SEM_API_TABLE\[\] = {` through the next line
matching `^};`, both inclusive.

- **195 lines, 144 entries, 144 distinct names**
- **sha256 `74610f24f1aab1178a867c9523d47a8ef130a90e537be4f6c9389bb590751405`**

Entry shape: `{name, category, forth_equiv, description, arg_count,
ret_count}` — **keyed on the function name alone, not on the DLL.**
Categories by count: SYNC 25, IRP 16, PORT_IO 13, PNP 11, DMA 11,
MMIO 10, STRING 9, MEMORY_MGR 9, DEVICE_IO 8, REGISTRY 6, DIAGNOSTIC
6, POWER 5, INTERRUPT 5, TIMING 4. The six that make `is_hardware`
true: PORT_IO, MMIO, DMA, TIMING, INTERRUPT, PCI_CONFIG.

## Coverage today, counted by bytes

Each input's imports parsed from its own import directory (descriptors
walked, thunk arrays to their terminators, hint/name strings read) and
matched against the frozen 144.

| input | imports | covered | coverage | hw-marked | largest uncovered sources |
|---|---|---|---|---|---|
| ACPI | 271 | 60 | 22.1% | 8 | ntoskrnl 191, HAL 8, ksr-ext 6 |
| HDAudBus | 91 | 27 | 29.7% | 6 | ntoskrnl 52, WppRecorder 4, WDFLDR 4 |
| disk | 95 | 27 | 28.4% | 3 | ntoskrnl 35, **CLASSPNP 33** |
| i8042prt | 97 | 47 | 48.5% | 7 | ntoskrnl 44, WppRecorder 4 |
| pci | 256 | 49 | 19.1% | 8 | ntoskrnl 189, WppRecorder 7 |
| HP serial | 70 | 37 | 52.9% | 7 | ntoskrnl 30, WMILIB 2 |
| storport | 264 | 62 | 23.5% | 11 | ntoskrnl 202 |
| usbxhci | 143 | 32 | 22.4% | 7 | ntoskrnl 89, WppRecorder 11, SleepStudy 7 |
| ReactOS serial | 47 | 38 | **80.9%** | 6 | ntoskrnl 8 |
| ReactOS beep | 23 | 14 | 60.9% | 1 | ntoskrnl 7 |
| nmap | 70 | 4 | **5.7%** | **0** | msvcrt 38, KERNEL32 23 |
| **total** | **1427** | **397** | **27.8%** | **64** | |

The two ends are the same fact from opposite sides: the vocabulary was
built for ReactOS-era driver APIs (81% on that control) and knows
almost nothing of user-mode names (5.7% on nmap, 0 hardware-marked).
**nmap's 0-of-45 classified matches and disk's 95 `is_hardware:false`
are one phenomenon, not two, and neither is a defect.**

## Most frequent uncovered names (candidates, none added)

`KfRaiseIrql` 8 inputs, `KeAcquireSpinLockRaiseToDpc` 8,
`IoWMIRegistrationControl` 8, `MmGetSystemRoutineAddress` 8,
**`MmMapIoSpaceEx` 7**, `KeLowerIrql` 7, `EtwWriteTransfer` 7,
`EtwRegister` 7, `_vsnwprintf` 6, `IoAttachDeviceToDeviceStack` 6,
`RtlFreeUnicodeString` 6, `IoReleaseCancelSpinLock` 6.

**One of these is a hardware-marking gap with a covered sibling:**
`MmMapIoSpace` is in the table (MMIO → `MAP-PHYS`, line 55) and
`MmMapIoSpaceEx` is not, on 7 inputs. `IoConnectInterrupt` is in
(INTERRUPT, line 78) and `IoConnectInterruptEx` is not. Those two
change `is_hardware`; the rest are scaffolding categories and change
only the strip.

## Pre-registered: what widening should change, before it is done

Widening happens in two separately measured acts, each against the
frozen hash, each re-measured on the same eleven inputs:

1. **Sibling repair (hardware-marking).** Add `MmMapIoSpaceEx`
   (MMIO) and `IoConnectInterruptEx` (INTERRUPT). **Predicted:**
   coverage 397 → 399 corpus-wide; hw-marked imports rise by the
   per-input count of those two names; **`hardware_functions` may rise
   only on 64-bit drivers whose functions call them, which requires
   (a) to attribute the call — so on today's decoder the predicted
   change to `hardware_functions` is 0 on all eight 64-bit drivers and
   the widening is measurable only in the imports array.** That
   prediction is itself a test of the (a) diagnosis.
2. **Class-DLL vocabulary (scaffolding).** Add the `CLASSPNP.SYS`,
   `portcls.sys`, `WDFLDR.SYS`, `WMILIB.SYS`, `WppRecorder.sys` names
   the corpus actually imports, categorised as scaffolding kinds.
   **Predicted:** coverage rises by their counts (disk +33 alone);
   **`is_hardware` unchanged for every one of them** (none is a
   hardware category); scaffolding recognised rises on the PE32
   controls and stays 0 on the 64-bit drivers until (a) lands.

**Any observed change outside those predictions stops the widening and
is read from bytes.** The hash is re-pinned in the same commit as each
act, and a coverage table is emitted beside it.

### Act 1 outcome (run 2026-09-20 before (a), log `vocab-widen-sibling-2026-09-20.log`)

**The substantive prediction held exactly: `hardware_functions` moved
on none of the eleven inputs**, while `hardware_imports` rose by 11
across seven of the eight 64-bit drivers. The diagnosis that (a)
blocks attribution survived the test that could have falsified it.
**One miss, arithmetic:** coverage was predicted 397 → 399 and observed
397 → **408**, because the prediction counted the two *names* added
while coverage counts import *entries*, and those names occur 11 times
across the corpus (`MmMapIoSpaceEx` on 7 inputs, `IoConnectInterruptEx`
on 4). Rule 26's shape: the sum was right for the population I had in
mind and the population was wrong. Vocabulary re-pinned at **146
entries, 197 lines, sha256 `b48923e815d3c731534e3d58ee3af484f46a3b7be61ae01368ac1bd56a5d66bf`**.

## Tier 1, stated as what it is

Three pieces, all reporting over data already parsed:
1. **`semantic.c:1393` prints `"category": "0x%X"`** — the raw enum
   value. There is no `sem_category_name()` in the codebase. Repair:
   add one, emit the name.
2. The vocabulary widening above, under its freeze.
3. A per-input report of DLL set plus function-signature marks.

**It is a sort into coarse families, not identification.** The DLL
sets separate disk (storage), HDAudBus (audio), usbxhci (USB/WDF), pci
(bus/platform) and ACPI (platform) unambiguously; storport needs its
function names; i8042prt and HP serial collapse to one family, which
is the right answer for two thin-HAL legacy port devices. "We can name
what a DLL is" must not become "we can say what it does": the second
needs call-site attribution, which is what (a) buys.
