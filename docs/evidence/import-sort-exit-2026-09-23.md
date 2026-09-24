# The import sort: its exit, written before any of its code (2026-09-23)

**Name.** This item has been called "tier 1". That phrase already means four
different things across ROADMAP, the multi-arch design doc, TASK_SHUTDOWN and
the metacompiler, so it is renamed here. **The import sort** is the sorting of
kernel drivers into coarse families from their import directory alone. It
reads no instructions. Its three pieces are as stated in
`vocab-freeze-tier1-prereg-2026-09-20.md`: category printed as a name, the
act-2 vocabulary, and a per-input report of the DLL set.

**Owner ruling, 2026-09-23.** The exit comes before any code. It is derived
from today's corpus, not from the item's own framing. It is stated as an exact
count, and scoped to kernel drivers. No code has been written for this item.

## 1. A figure withdrawn

**Withdrawn:** *"On every 64-bit driver, scaffolding recognised is 0"*, and the
STRIP table built on it (`finding-emission-and-tier1-2026-09-20.md` §1). That
reading was taken before (a) landed. It is **withdrawn, not replaced
silently**. The reading today, from the shipped build (`bin/translator`
`11f51761d4ad5d7a`, built from private `c821eff`, source identical to the
mirror):

| HP driver | hardware | scaffolding | unclassified | imports |
|---|---|---|---|---|
| ACPI | 45 | 1015 | 1517 | 272 |
| disk | 3 | 58 | 132 | 95 |
| HDAudBus | 21 | 71 | 254 | 91 |
| i8042prt | 31 | 50 | 122 | 97 |
| pci | 29 | 555 | 1058 | 256 |
| serial | 48 | 46 | 83 | 70 |
| storport | 85 | 408 | 1127 | 264 |
| usbxhci | 58 | 311 | 1097 | 143 |

Over the whole population below, scaffolding is 0 on **87 of 1,322** drivers
and hardware is 0 on **401**. Both zeros are **recorded here, not explained**,
and no item is opened for them. The premise that the classifier "does nothing
on 64-bit" no longer holds, and nothing below depends on it.

## 2. Scope: kernel drivers, and only kernel drivers

**The population is defined by bytes, not by file extension.** It is every PE
whose optional-header Subsystem is NATIVE (1), whose import directory names at
least one module, and none of them `ntdll.dll`. It is read from the four
Windows sets on disk (Dell, Older ASUS, Newer ASUS, hp_i3) plus the Dell 26100
System32. The scanner is `~/corpus/tools-2026-09-23/kdrv_scan.py`, sha256
`437b218afc60…`, pefile 2024.8.26.

**A first rule was withdrawn before any count was used.** "Imports
`ntoskrnl.exe`" dropped **37 miniports** that import only their port driver
(`lsi_sas.sys` imports only storport; `intelide.sys` only pciidex;
`drmkaud.sys` only drmk and ks).

| | files |
|---|---|
| **kernel drivers** | **1,368 rows, 1,322 distinct by sha256**, 522 distinct names, all PE32+ |
| excluded: Subsystem GUI (2) / console (3) | 1,616 / 2,448 |
| excluded: native, no import directory | 244 (215 `KBD*.DLL` layouts, 25 other `.dll`, 4 `.sys`), with **nothing for an import sort to read** |
| excluded: native, imports ntdll (user-mode native) | 11 |
| excluded: boot application (16) | 5 |
| excluded: not MZ | 189 |

Across the sets the distinct counts are: Dell 428, Newer ASUS 485, Older ASUS
433, hp_i3 8, and the System32 14. The System32 14 are the `kd*.dll` family, `pshed.dll`, `ci.dll`,
`bootvid.dll` and others, **including the kernel images `ntoskrnl.exe` and
`securekernel.exe`**. The kernel images meet the byte definition and are kept
rather than hand-excluded. Counts per set overlap, which is why the total is taken by sha256.

**Why the scope stops here.** The frozen vocabulary covers **5.7%** of the one
user-mode binary it was measured on (nmap), with **0** hardware marks. The
DLLs that discriminate are kernel-mode: CLASSPNP, portcls, WDFLDR, HAL.
Applications sort another way: console versus GUI, by the closure's
decomposition (`app-closure-prereg-2026-09-23.md`). That is a different
classifier and is **not** part of this item. Mac kexts are Mach-O, a different
loader, and are also outside.

## 3. The exit: three conditions, each an exact count

The import sort is done when the shipped `translator -t report` shows all
three on the **1,322 distinct kernel drivers**.

**X1: every category printed as a name.** The report emits **128,142** import
entries over the 1,322. That equals the count from the bytes on **every**
driver: 0 drivers differ. **Today 128,142 of 128,142 print a hex category**
(`"0x80"`). Exit: **0 of 128,142**, and the entry count unchanged at 128,142.
The before-reading is banked as
`~/corpus/tools-2026-09-23/import-sort-report-before-2026-09-23.tsv`, sha256
`77719b09b87b…`, one row per driver: sha256, imports, hex categories,
scaffolding, hardware.

**X2: a family per driver, equal to the bytes' answer on 1,322 of 1,322.** The
rule takes the first of these that the driver imports: CLASSPNP → *storage
class*; portcls → *audio port class*; WDFLDR → *WDF*; HAL → *HAL, no class
DLL*. A driver that imports none of the four prints **unsorted**. Unsorted is
a distinct value, never a family and never an empty field (the twenty-seventh
rule: zero-found must not print like a result).

| family | distinct drivers |
|---|---|
| storage class (CLASSPNP) | **17** |
| audio port class (portcls) | **15** |
| WDF (WDFLDR) | **360** |
| HAL, no class DLL | **266** |
| **unsorted** | **664** |
| **total** | **1,322** |

Exit: the report's value equals `kdrv_scan.py`'s value on **1,322 of 1,322**.
The scanner is an independent reader (pefile, not the translator's PE loader).

*Stated so it is not read as derived:* the precedence was chosen with the
co-occurrence table in view. The table is printed so that any other
precedence can be re-derived from it. The only overlaps are portcls with WDFLDR
(9, all with HAL too) and CLASSPNP with HAL (1). No driver imports both
CLASSPNP and portcls.

| imports, of the four | drivers |
|---|---|
| none | 664 |
| HAL | 266 |
| WDFLDR | 247 |
| WDFLDR + HAL | 113 |
| CLASSPNP | 16 |
| portcls + WDFLDR + HAL | 9 |
| portcls | 3 |
| portcls + HAL | 3 |
| CLASSPNP + HAL | 1 |

**X3: the four DLLs' names in the vocabulary.** The population imports **85
distinct (DLL, name) pairs** from the four: CLASSPNP 41, portcls 15, WDFLDR 8,
HAL 21. The frozen vocabulary (146 entries, sha256 `b48923e8…`, re-read today)
covers **4 of 85**, all from HAL: HalGetBusDataByOffset,
HalSetBusDataByOffset, KeQueryPerformanceCounter, KeStallExecutionProcessor.
Exit: **85 of 85** covered, with the hash re-pinned. **`is_hardware` stays
false for all 64 CLASSPNP, portcls and WDFLDR names.** Which of HAL's 17 new
names are hardware kinds is decided in act 2's own pre-registration, from the
DDK, not here.

*A change from act 2 as pre-registered on 2026-09-20.* That act also listed
WMILIB and WppRecorder. Neither is a discriminator, and they are **dropped from
the exit**. That is a scope cut, stated for the owner's review.

## 4. What the exit does not claim

- **The four-DLL rule is coarser than the hand read.** On the HP eight it gives
  disk → storage class, HDAudBus → audio, usbxhci → WDF, and **ACPI, i8042prt,
  pci, serial and storport all → HAL, no class DLL**. The hand read of
  2026-09-20 separated pci (PSHED) and ACPI (the ksr extension), and it
  separated storport only by function names. The rule cannot do any of that.
  This is the rule as scoped, not a defect.
- **Half the population is unsorted: 664 of 1,322.** Among those 664, the most
  common DLLs besides ntoskrnl are ndis 110, storport 102, netio 91,
  WppRecorder 62, WMILIB 49, cng 43, fltmgr 42 and ksecdd 39. **187 import
  ntoskrnl alone**, and no DLL rule can sort them. Widening the rule, for
  example ndis → network or storport → storage miniport, is an owner ruling,
  and it would move X2's counts. It is **not** part of this exit.
- **A family names what a driver links against, not what it does.** Saying
  what a driver does needs call-site attribution. The port signal remains a
  presence signal, never a port number, on 64-bit drivers (the 2026-09-20
  bound).
- **n = one corpus, four machines plus one System32, 1,322 distinct
  binaries.** That is not a sample of Windows drivers.

## Inputs

`bin/translator` `11f51761d4ad5d7a`. Vocabulary extraction sha256 `b48923e8…`
(146 entries). `kdrv_scan.py` `437b218a…`. Before-reading `77719b09…`. All
three banked files are listed in `~/corpus/tools-2026-09-23/SHA256SUMS`. No
binary, name slug or device identifier is published; the per-driver file
stays in the corpus.
