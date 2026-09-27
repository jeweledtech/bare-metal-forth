# (bz) Base-finding for the HP: pre-registration (2026-09-27)

Written before any code for (bz) exists. The outcome goes **below**, and
nothing above the Outcome line is edited after the first build.

**The letter.** The translated HDAUDBUS vocabulary gets its register base
from the machine instead of a hand-typed address. `B1228000
HDAUDBUS-R58+4-W@` becomes `0 HDAUDBUS-R58-BASE HDAUDBUS-R58+4-W@`.

## Owner rulings this letter rests on (2026-09-27)

- **HP binding: INFERRED, not observed.** Three facts point the same way:
  1. The HP's INFs give 00:1F.3 no candidate except hdaudbus.inf
     (`PCI\CC_0403`, sha256 `09165ec02c40f812…`); hdbusext.inf is
     Class=Extension and has no AddService
     (`~/corpus/tools-2026-09-26/inf_cc0403.out`).
  2. Prog-IF is 00 (`hda2-iron-2026-09-27.log` l.47).
  3. The translated accessors read the spec's VMAJ/VMIN at BAR0 on iron
     (HDA-1, 2d3acbd).

  The owner is skipping the HP's Windows boot, so the HP's
  pci-bound.csv is optional and not a gate.
- **The binding rule is the class, read from the driver's INF.**
- **Instances:** every 04/03 function is exposed, numbered in scan order
  (PCI-TBL order), with its b:d:f printed. None is ever chosen
  implicitly.
- **Where the shared words live:** a new public, block-loaded
  `forth/dict/pci-bar.fth` (vocabulary PCI-BAR). It takes BAR64-MASK and
  PCI-BAR64@ from xhci.fth, plus the find-nth-by-class search. XHCI and
  HDAUDBUS both `ALSO PCI-BAR`. The 09-07 ruling stands (no boot caller,
  so not embedded), and embedded pci-enum.fth is not touched.
- **Base-finding only reads config space.** No PCI-ENABLE, which writes
  the command register.
- **The BAR:** for hdaudbus on the HP, the mapped region behaves as BAR0.
  BAR4 (B1200000) is present and unexplained. Its size bound (≤ 0x20000)
  is reasoned, not measured.
- **Recorded, not acted on:** 1C0022510 maps two regions (parked at 0x58
  and 0x60), and only 0x58 carries accesses. Which map corresponds to
  BAR4 is not measured.

## What gets built

### 1. `scripts/inf_binding.py` (translator, private)

Usage: `inf_binding.py <inf> <service-binary>`.

It takes the INF's AddService install sections whose ServiceBinary is
`<service-binary>`, collects the PCI IDs of the model lines that reach
them, and writes a binding file:
```
class 04
sub 03
id PCI\CC_0403
inf hdaudbus.inf 09165ec02c40f812
```
It **refuses** (exit 2, no file) when:
- no model line reaches the binary;
- any reaching ID is not of the class-only form `PCI\CC_xxxx`;
- the class-only IDs name more than one class/subclass.

A VEN-specific binding is a later letter's input, never a silent
fallback. The parsing rules are inf_count.py's (UTF-16 BOM, `;`
comments stripped outside quotes, `%strings%` substituted).

### 2. Translator option `-B FILE` (private)

It reads the binding file and does three things.
- **Adds PCI-BAR to REQUIRES**, so the preamble emits `ALSO PCI-BAR`
  after `ALSO HARDWARE`. The header REQUIRES line lists the four words
  used.
- **Emits the vocabulary-level binding block** after the preamble's
  `HEX`, before `\ ---- Extracted Functions ----`. For the HP's
  HDAudBus.sys it is exactly:
  ```
  \ ---- Binding (read from the driver's INF) ----
  \ PCI\CC_0403 from hdaudbus.inf 09165ec02c40f812
  \ instances in scan order, never chosen implicitly
  : HDAUDBUS-COUNT  ( -- n )
      4 3 PCI-CLASS-COUNT ;
  : HDAUDBUS-BDF  ( i -- b d f -1 | 0 )
      >R 4 3 R> PCI-CLASS-NTH ;
  : HDAUDBUS-LIST  ( -- )
      4 3 PCI-CLASS-LIST ;
  ```
  Every definition is two lines, the name line and then the body, so
  the ≤ 64 rule holds for any vocabulary name up to (bx)'s 31. On one
  line, a vocabulary name longer than HDAUDBUS would pass 64 (the BDF
  line is exactly 64 at this length).
- **Emits one base word per region** that has accessors, directly
  after that region's accessors, but only when the region is the
  function's **first** map (regions[0]). For 1C0022510 it is exactly:
  ```
  \ region 0x58 = first map = BAR0 (ruled, HP 2026-09-27)
  : HDAUDBUS-R58-BASE  ( i -- addr | 0 )
      HDAUDBUS-BDF
      IF 0 PCI-BAR64@ ELSE 0 THEN ;
  ```
  (With a 31-character name, the call on the same line as `IF ...`
  would be 65 characters, so it gets a line of its own.)
  When the region with accessors is not the first map, the translator
  emits no word, only the comment line `\ no base word: region is not
  the first map`. The map-order-to-BAR rule is proven for map 0 ↔ BAR0
  on the HP only.

**Without `-B`, the output is byte-identical to today's.**

Every new line is ≤ 64 characters ((bw)'s block rule), and every new
name is ≤ 31 ((bx)'s limit). The longest name is `HDAUDBUS-R58-BASE`,
at 17.

### 3. `forth/dict/pci-bar.fth` (public, block-loaded, `ALSO PCI-ENUM`)

- **Moved verbatim from xhci.fth:** BAR64-MASK, `VARIABLE XR-B XR-D
  XR-F XR-R`, and PCI-BAR64@. XHCI-BIND still uses XR-B/D/F, which it
  now reaches through `ALSO PCI-BAR`.
- **New words:**
  - `PCI-CLASS-COUNT ( class sub -- n )`
  - `PCI-CLASS-NTH ( class sub i -- b d f -1 | 0 )`. It refuses for
    `i < 0` or `i ≥ count`.
  - `PCI-CLASS-LIST ( class sub -- )`. It prints one line per match,
    `i bb:dd.f`.

  A match uses PCI-FIND-CLASS's rule: the table's +8/+9 bytes as a
  pre-filter, then one live `8 PCI-READ` as the authority. So
  `class sub 0 PCI-CLASS-NTH` must equal `class sub PCI-FIND-CLASS` on
  every machine.

### 4. `forth/dict/xhci.fth` (public)

- **Removed:** the moved words.
- **Added:** `ALSO PCI-BAR` after `ALSO PCI-ENUM`.
- **REQUIRES header:** gains PCI-BAR.

Nothing else changes.

## The reds, registered before the code

**R1 (translator, `test_mmio_consumer.c`): `bz_RED_binding_words_emitted`.**
With a binding (class 04, sub 03, the id and inf lines above) passed in
the options, the HP HDAudBus.sys forth output contains the binding
block and the base-word lines above verbatim, and `ALSO PCI-BAR` in the
preamble.
- **Red today:** the option does not exist, so the test holds the
  binding as the text it wants and fails.
- **Register:** it goes into `xfail_names[]` and into the register's
  *Open, with a red* table as (bz). The register union moves 12 → 13 at
  the red commit and back to 12 at the fix.

**R2 (public QEMU, new `tests/test_pci_bar.py`).** It runs on the
test-xhci fixture with **two** `-device intel-hda`, so instances are
exercised in QEMU, which the HP cannot do.
- **Red first:** its first check is "PCI-BAR has catalog placement",
  which fails before pci-bar.fth exists.
- **Checks after the fix:**
  - `4 3 PCI-CLASS-COUNT` = 2.
  - `0` and `1` PCI-CLASS-NTH give two different b:d:f.
  - `2` refuses (`<0 >`), and so does `-1`.
  - `4 3 0 PCI-CLASS-NTH` equals `4 3 PCI-FIND-CLASS`, an agreement
    control through a different word.
  - The two instances' `0 PCI-BAR64@` values are nonzero and differ.
  - PCI-CLASS-LIST prints exactly 2 lines.
  - A class with no device (`7 7`) counts 0 and NTH refuses.
  - DEPTH is 0 after each.

## Must not move

| # | what | how it is checked |
|---|---|---|
| M1 | `build/bmforth.img` sha256 `dfd7c5f30e22ecf3…` (kernel + embed) | re-hash after the build; pci-enum.fth byte-identical (`git diff` empty) |
| M2 | test_xhci.py passes with the same check count | full run (20+ min, logged); its ONLY edit is one added load step, PCI-BAR THRU before XHCI THRU, named here |
| M3 | translator: the 427 existing tests pass | `make test`; census becomes 428 in 27 suites (R1 added, baseline tsv +1, named here) |
| M4 | forth output WITHOUT `-B` for all 10 (bt) drivers | sha256 of each output before and after the change, identical |
| M5 | hdaudbus.fth WITH `-B` against a75e03f's file | diff shows only the REQUIRES header line, `ALSO PCI-BAR`, the binding block, and the base comment + word. The 7 accessor lines and MMIO-FN-1C0022510 are unchanged |
| M6 | public `make test` | green |

**Named moves (expected, not regressions):**
- **`build/combined.img` changes.** It is `$(IMAGE) + blocks.img`, and
  the catalog gains pci-bar.fth while xhci.fth and hdaudbus.fth change.
  Block ranges for vocabularies at or after the first changed one
  shift. **840696e3 therefore does NOT hold for the stick image**; it
  holds only in the sense of M1. The HP card states the new
  combined.img hash and the new ranges.

## Predictions

**QEMU dry run** (one intel-hda at 00:04.0; values from
`hda-1-dryrun-2026-09-25.log`, which reads BAR0 FEBB0000, 32-bit, and
command 0103):
- `HDAUDBUS-COUNT .` = 1
- `HDAUDBUS-LIST` prints `0 00:04.0`
- `0 HDAUDBUS-R58-BASE .H8` = FEBB0000
- `1 HDAUDBUS-R58-BASE .` = 0
- Through `0 HDAUDBUS-R58-BASE`: VMIN 00, VMAJ 01, GCAP 4401, OUTPAY 3C,
  INPAY 1D, and +14 0000 (QEMU's, as logged).

**HP card** (no hand-typed address; checked against HDA-1's
`hda-iron-2026-09-26.log` values):
- COUNT 1
- LIST prints `0 00:1F.3`
- base B1228000
- VMIN 00, VMAJ 01, GCAP 9701, GCTL 00000001, OUTPAY 3C, INPAY 1C,
  +14 0C00
- `1 HDAUDBUS-R58-BASE .` = 0

The HP COUNT of 1 rests on the 09-25 PCI-LIST photo (pending commit) and
HDA-2's PCI-COUNT of 16. The card's own COUNT line is the first logged
reading of it.

**Independent checks the HP card will carry:**
1. The emitted base equals HDA-1's hand-typed base (B1228000), reached
   by a path that shares no typed address.
2. The accessors, given the emitted base, reproduce HDA-1's register
   values.
3. The NTH/FIND-CLASS agreement control.

GCAP and GCTL repeating 09-25 is repetition, not a check.

## After this letter

(bx), the name-length guard, is next in line.

---

## Outcome

(written after the build; nothing above this line changes)

### Corrective C1 (2026-09-27, before any Forth code; found by reading test_xhci.py)

**M2 as written is wrong.** It says test_xhci.py's only edit is one
added load step. The suite also sets its search order itself: `ONLY
FORTH DEFINITIONS`, `ALSO PCI-ENUM` and a guarded `ALSO XHCI` (l.611–617).
It then checks `DEF? BAR64-MASK` (#7) and `DEF? PCI-BAR64@` (#8).

After the move those two words live in PCI-BAR. XHCI's own `ALSO
PCI-BAR` runs inside XHCI's load, and **`ALSO X` does not expose X's
ALSO chain** to the caller's search order (standing kernel lesson). So
#7 and #8 would fail for a reason that is not a regression.

**M2, restated:** test_xhci.py gets exactly two edits:
1. a PCI-BAR `THRU` before the XHCI `THRU`;
2. a guarded `ALSO PCI-BAR` after the `ALSO PCI-ENUM` at l.612.

Its check count and its pass count are unchanged. The mechanism
travels with the corrective: the move changes which vocabulary *holds*
the words, never what the words *do*.

**Named, not edited:** DESK-CARD-XHCI-2E, -3D and -4 type `ALSO PCI-ENUM
ALSO XHCI ALSO HARDWARE`. They are records of trips already run, against
images that predate the move. They are not re-run, so they are not
changed. A future xHCI card loads PCI-BAR and adds `ALSO PCI-BAR`.

### Corrective C2 (2026-09-27, before inf_binding.py is written; found by reading the HP's hdaudbus.inf)

The HP's `[Microsoft.ntamd64]` binds the install section
`HDAudio_Device` to **two** IDs:
- `PCI\CC_0403`;
- `ACPI\CLS_0004&SUBCLS_0003`.

**The refusal rule as written would refuse this INF**, because it
refuses when "any reaching ID is not of the class-only form
`PCI\CC_xxxx`". The rule's purpose was narrower: to refuse when the INF
binds a **PCI** device by vendor/device, where the class rule would be
the wrong choice (the intcaudiobus case).

**Mechanism:** ForthOS finds devices through PCI config space only
(`PCI-CLASS-NTH` walks PCI-TBL). An ID from another enumerator (ACPI,
HDAUDIO, ...) names devices that search can never return, so it
neither supports nor contradicts the PCI binding.

**The refusal rule, restated.** Refuse (exit 2, no file) when:
- no model line reaches the binary with a `PCI\` ID;
- any reaching `PCI\` ID is not class-only `PCI\CC_xxxx` (4 hex
  digits);
- the class-only IDs name more than one class/subclass.

Non-PCI IDs are written to the binding file as `other <id>` lines, for
provenance. The translator ignores them, so R1's pre-registered text is
unchanged. The HP binding file gains one line:
`other ACPI\CLS_0004&SUBCLS_0003`.

**Model sections** are the `[Manufacturer]` names with each listed
decoration (`Microsoft`, `Microsoft.ntamd64`). **Services sections** are
the install section's `.Services` sections, with or without a
`.NT`/`.NTamd64` decoration (here `HDAudio_Device.NT.Services`).
AddService's third field names the service-install section whose
ServiceBinary basename must equal the binary.
