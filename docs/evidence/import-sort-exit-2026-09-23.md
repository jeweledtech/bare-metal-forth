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
DLL* (printed `hal-residue`, see §5). A driver that imports none of the four prints **unsorted**. Unsorted is
a distinct value, never a family and never an empty field (the twenty-seventh
rule: zero-found must not print like a result).

| family | distinct drivers |
|---|---|
| storage class (CLASSPNP) | **17** |
| audio port class (portcls) | **15** |
| WDF (WDFLDR) | **360** |
| `hal-residue` (HAL, no class DLL) | **266** |
| **unsorted** | **664** |
| **total** | **1,322** |

Exit: the report's value equals `kdrv_scan.py`'s value on **1,322 of 1,322**.
The scanner is an independent reader (pefile, not the translator's PE loader).

*Stated so it is not read as derived:* the precedence was chosen with the
co-occurrence table in view. The table is printed so that any other
precedence can be re-derived from it. ~~The only overlaps are portcls with
WDFLDR (9, all with HAL too) and CLASSPNP with HAL (1).~~ **Resolved
2026-09-23: that sentence was wrong** and read the table incompletely. The
counts are in §5. No driver imports both CLASSPNP and portcls.

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

## 5. Amendments after owner review, 2026-09-23 (X1–X3 counts unchanged)

All three rulings accepted: the cut stands, the order stands, no widening.
Every figure below was re-read from `kdrv_scan.py`'s output. **No exit count
moved.**

**The HAL bucket is a residue, and is printed as one: `hal-residue`.** 266 of
the 658 sorted drivers land in it, and HAL is last in the order. Nearly
anything that touches hardware imports HAL, so the bucket is what is left
after the other three, not a family. On the HP eight it takes ACPI, i8042prt,
pci, serial and storport, and the hand reading told several of those apart. X2
passing means *266 drivers import HAL and no class DLL*. **It does not mean
266 drivers identified as a HAL family.** A residue printed under a family's
name is the error `(ax)` fixed for `none`, one level up.

**Overlap, corrected.** The §3 sentence I wrote said the only overlaps were 9
and 1. The owner's review then read that as "10 of 658 in more than one
family". Both are wrong. Counted:

| overlap | drivers |
|---|---|
| import more than one of the **three class DLLs** | **9** of the 392 that import any class DLL (all portcls + WDFLDR; CLASSPNP ∩ portcls 0, CLASSPNP ∩ WDFLDR 0) |
| import a class DLL **and** HAL | **126** of those 392 |
| import more than one of the four | **126** of 658 |

So there are two properties, not one. **The three class families are nearly
disjoint (9 of 392)**, and their order among themselves is almost arbitrary,
not load-bearing. **HAL's place is load-bearing:** 126 class-DLL drivers
(32%) also import HAL. Put HAL anywhere but last and it takes them. That is
the measured reason HAL is last, and the same fact is why it is a residue.

**The ceiling on any DLL-based rule: 1,135 of 1,322 (85.9%).** 187 drivers
import `ntoskrnl.exe` and nothing else. No rule that reads the DLL set can
ever sort them, however it is widened. This bounds every future widening, not
only this one. The 664 unsorted are the next item, with its own exit. The
most a DLL rule could reach there is 664 − 187 = 477.

**WMILIB and WppRecorder: the cut, as a measurement.** Across the 1,322 they
are imported by:

| DLL | drivers | CLASSPNP (17) | portcls (15) | WDFLDR (360) | hal-residue (266) | unsorted (664) |
|---|---|---|---|---|---|---|
| WppRecorder | 286 (21.6%) | 0 | 10 | 177 | 37 | 62 |
| WMILIB | 103 (7.8%) | 0 | 7 | 4 | 43 | 49 |

*Stated against the ruling's premise:* neither DLL is imported by nearly
everything; 21.6% and 7.8% is far from all. The measured reason for the cut
is spread. Each one sits in **four of the five buckets**, so on its own it
says nothing about which family a driver belongs to. WppRecorder is a tracing
library and WMILIB a WMI helper. Those two descriptions are readings of the
DLL names, not measurements, and are given only as context.

## 6. X3, before any category is chosen (owner ruling 2026-09-23, items 0 and 2)

**The 85, decomposed. 64 + 17 = 81, and the other four are named here.** X3's
85 is the distinct (DLL, name) pairs the 1,322 import from the four DLLs:
CLASSPNP 41 + portcls 15 + WDFLDR 8 + HAL **21** = 85. The "17" in the
proposal was HAL's **uncovered** names. The other four HAL names are
**already in the frozen vocabulary** (`b48923e8…`, re-read from `semantic.c`):

| name | vocabulary line | category |
|---|---|---|
| HalGetBusDataByOffset | 91 | PCI_CONFIG |
| HalSetBusDataByOffset | 93 | PCI_CONFIG |
| KeQueryPerformanceCounter | 65 | TIMING |
| KeStallExecutionProcessor | 63 | TIMING |

So **85 was produced to answer the question X3 asks** ("names from the four
DLLs"), and the exit's "covers 4 of 85" already counted these four. The
proposal's 64 + 17 dropped them because it priced only the uncovered names.
**But the four have no pinned source.** They were hand-assigned when the
vocabulary was built. Under item 6's three-way split (import directory /
pinned page / none) they are a fourth case, *vocabulary, uncited*. That goes
to the owner. It is not folded silently into "pinned page".

**The 0x89 collision, read from source (rule 31): it holds.**
- Field: `sem_function_t.scaf_cat_mask`, `uint16_t` (`semantic.h:215`),
  documented as "bit N = SEM_CAT_IRP + N seen; bit 9 = DOS_API".
- Values: `SEM_CAT_IRP = 0x80`, `SEM_CAT_DIAGNOSTIC = 0x88`,
  `SEM_CAT_DOS_API = 0x90` (`semantic.h`).
- Writer (`semantic.c:788–792`): DOS_API → `1u << 9`; every other
  scaffolding category → `1u << (cat - SEM_CAT_IRP)`. A category at 0x89 would
  therefore set bit 9, which is DOS_API's.
- Reader (`semantic.c:1731–1734`): bit 9 → DOS_API, bits 0–8 →
  `SEM_CAT_IRP + bit`. A 0x89 import would render as `DOS-API`.
- **A second hazard in the same encoding:** the reader loops bits 0–9 only.
  A category at 0x8A–0x8F would be written to bits 10–15 and never rendered,
  dropped without a word.

**Is it a bitmask, or an enum stored in one?** A bitmask: it holds a set.
Bits are OR-ed at every scaffolding call site and OR-inherited from callees,
and the reader renders every set bit. **No value is mis-mapped today**,
because every scaffolding category that exists (0x80–0x88 and 0x90) has its
own bit. So the collision is **not a defect in place today**. It is a closed
encoding: bit index = enum offset, plus one hard-coded exception. **Any** new
scaffolding category collides or is dropped unless the encoding changes.
Recorded as that; no red, because no present input moves.

**Exact census of `scaf_cat_mask`, rule 24** (`grep` over `src/ include/
tests/` and `scripts/`, which has none):

| role | site |
|---|---|
| writer | `semantic.c:789` (DOS_API bit), `semantic.c:791–792` (offset bit), `semantic.c:992–993` (OR-inherit from callees; also reads callee masks) |
| reader | `semantic.c:1725` (zero test), `semantic.c:1731–1734` (render loop), `test_callgraph.c:191`, `test_semantic.c:491` |
| comments only | `semantic.h:210`, `:256`, `:429` |

**Also on the path of any new scaffolding category, though not this
field:** `sem_is_scaffolding()` (`semantic.h:339–341`) is a range test,
`IRP..DIAGNOSTIC || DOS_API`. A value outside it is *not scaffolding at all*,
and the import-site writer above never runs for it. The enum readers
(`sem_is_hardware`, `sem_is_scaffolding`, `sem_category_filter_name`,
`sem_category_name`) are a separate census, owed before a value is chosen.

**No category value is chosen in this section.**

## 7. Met, 2026-09-23

X1 by `(bh)`, X2 by `(bh)`, and X3 by `(bj)`
(`fix-bj-values-prereg-2026-09-23.md`, outcome):
- **X1:** 0 of 128,142 imports print a hex category.
- **X2:** 1,322 of 1,322 agree with the scanner.
- **X3:** 85 of 85 print a value, 68 of 85 are sourced, and 17 print
  `NO_PUBLIC_REFERENCE`.

X3's count was met as amended in §6 and in `(bj)`'s pre-registration: the
vocabulary hash is unchanged, not re-pinned. The next items are the 664
unsorted drivers, with their own exit and the ceiling of 1,135 (§5), and
`(bi)`.

> **Vocabulary hash, 2026-09-24:** frozen at `b48923e8…` until 2026-09-24; superseded by `cd4278db…` (`(bl)`, `fix-bl-buffer-setup-prereg-2026-09-24.md`: three MDL routines DMA → BUFFER_SETUP). Every figure and citation above that names `b48923e8…` was measured against that table, and is left as written.
