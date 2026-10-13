# TASK — HAL: per-machine binding vocabularies, matched from SMBIOS (2026-10-12)

Owner, 2026-10-12 (rulings on PCI-TYPES and phase 0, item 4), no-plan flow:
- **Public, the mechanism:** a match table from SMBIOS manufacturer /
  product to a binding vocabulary; matching prints every BIND it runs;
  HAL-LIST shows the result; no match means the defaults stay, said
  plainly.
- **Private only:** the HP's model string and its binding vocabulary
  (machine identifiers stay out of public files).
- Gates in QEMU: made-up SMBIOS strings that match a test entry bind as
  expected; non-matching strings change nothing; the direct words still
  work; DEPTH 0. Nothing binds automatically on the real HP until the
  owner's session there. No writes. Pad cost reported. Commit, don't push.
Follows docs/TASK_HAL_DISPLAY.md, docs/TASK_HAL_BLOCK.md (the binding layer)
and docs/TASK_HAL_DISCOVERY.md (SMBIOS).

## Design note

- **Vocabulary HAL-MATCH** (hal-match.fth, public, block-loaded, REQUIRES
  SMBIOS; HAL is embedded). Nothing at boot calls it, so it costs catalog
  blocks only, and nothing matches or binds until someone types
  MATCH-BIND: loading a vocabulary of entries registers them, nothing more.
- **An entry** is the SMBIOS type 1 manufacturer and product, exact, and a
  list of bindings, written as the Forth a person would type:
  ```
  : TM-IDS ( -- m u p u ) S" ForthGate" S" MatchTest" ;
  TM-IDS MATCH-ENTRY
  BINDS FB-BASE TM-BASE
  BINDS FB-FLUSH TM-FLUSH
  ```
  - `MATCH-ENTRY ( m-addr m-len p-addr p-len -- )` starts an entry (the
    strings are copied into the dictionary; newest entry first).
  - `BINDS ( "vector" "word" -- )` adds a binding to the newest entry, in
    written order. The vector must be a HAL vector (its code field is
    DOVEC's): anything else is refused, `BINDS: <name> is not a HAL
    vector`, and nothing is added. The word's name is kept with its XT
    (from the word buffer `'` just parsed), so the binding can be printed
    by name.
- **`MATCH-BIND ( -- )`** reads SMBIOS type 1 (SYSTEM.'s fields), finds
  the newest entry whose manufacturer and product are both equal, and
  then:
  - prints `Machine: <manufacturer> / <product>`, then, for each binding,
    the line `' <word> BIND <vector>` (what it runs) and runs it
    (HAL-SET);
  - with no matching entry: `No machine entry for <m> / <p>: the defaults
    stay`, and no vector changes;
  - with no SMBIOS type 1: `No SMBIOS type 1: the defaults stay`.
  HAL-LIST then shows the result; MATCH-BIND does not call it.
- **`MATCH-LIST ( -- )`** prints each entry: its strings and its
  bindings (a dry look before binding).
- **Private: HAL-MACHINES** (forthos-vocabularies, copied into forth/dict
  ignored, as the paid vocabularies are): the HP's entry and its binding
  vocabulary.
  - The display contract is not machine-specific (BOOT-MODE already
    chooses VGA or the framebuffer shadow, and the HP boots both ways), so
    the HP's list does not touch it.
  - ~~What is the HP's own is its disk: the block contract's reader on the
    HP is the AHCI reader (AHCI-RW binds it today). The HP list binds
    BLK-READ to a guarded word: the AHCI reader when AHCI-INIT reported
    the controller (AH-FOUND), else a refusal with ior 1.~~ Resolved
    2026-10-13: the bind is dropped (the AHCI reader maps to the image's
    layout, not an installed store's); the entry carries a note instead.
    See the last section. BLK-WRITE is not in the list: AHCI-RW installs
    the writer only after its partition guard, and a match never turns
    writes on.
  - The HP's SMBIOS strings are expected, not measured (no reading of
    the HP's SMBIOS exists): its entry says so, and SYSTEM. at the
    owner's session confirms them. A wrong string can only fail to match
    (the defaults stay).
- **No writes:** MATCH-BIND only sets binding cells; the bindings it can
  set in the public tree are the test's. Direct @ ! C@ C! INB OUTB are
  untouched.

## Gates

test-hal-match (public, BIOS image, SeaBIOS, two boots; the test entries
typed at the prompt as the doc writes them):
- Boot 1, QEMU told `-smbios type=1,manufacturer=ForthGate,product=MatchTest`;
  two entries: ForthGate / MatchTest (FB-BASE -> TM-BASE, FB-FLUSH ->
  TM-FLUSH) and ForthGate / OtherBox (FB-BASE -> TM-OTHER).
  - M1 MATCH-BIND prints `Machine: ForthGate / MatchTest`, then exactly
    `' TM-BASE BIND FB-BASE` and `' TM-FLUSH BIND FB-FLUSH`, in that order,
    and nothing about TM-OTHER.
  - M2 HAL-LIST: FB-BASE and FB-FLUSH bound to TM-BASE's and TM-FLUSH's
    XTs; FB-BASE returns TM-BASE's buffer; FB-FLUSH runs TM-FLUSH (its
    counter moves).
  - M3 BLK-READ and BLK-WRITE: the same HAL-LIST lines as before the match.
  - M4 `BINDS SPACE TM-BASE` is refused (`BINDS: SPACE is not a HAL
    vector`), and MATCH-LIST shows the entry's bindings unchanged.
  - M5 the direct words: `@ ! C@ C!` on a variable, `INB` from the PIC
    mask port (0x21) equals the value read before the match.
  - M6 DEPTH 0.
- Boot 2, QEMU told `product=NoMatch`, the same entries:
  - N1 MATCH-BIND prints `No machine entry for ForthGate / NoMatch: the
    defaults stay` and no `BIND` line.
  - N2 HAL-LIST after equals HAL-LIST before, every line; FB-BASE =
    B8000.
  - N3 DEPTH 0.
Private (forthos-vocabularies, SKIPPED in a public clone): test-hal-match-hp,
QEMU told the HP's expected strings, HAL-MACHINES block-loaded: MATCH-BIND
prints the HP's line and ~~binds BLK-READ to the guarded reader; on QEMU's
q35 (no AHCI-INIT run) the guard refuses a read with ior 1~~ (resolved
2026-10-13: its note; gates P1-P6 in the last section).
Kernel pad: no kernel change expected.

## Results

Evidence: ~/forthos-evidence/2026-10-12-hal-machine/ (predictions written
before the red run, logs).

**Red.** The first red run did not count: the test booted the floppy
without the IDE slave the kernel reads blocks from (test_hal.py attaches
both), so every catalog lookup failed, HAL-MATCH or not (a probe:
CATALOG-FIND returned false). Fixed in both tests, and a control added: SMBIOS
(in every image) must load first, else INSTRUMENT FAIL, no score. Rerun
against an image built without HAL-MATCH in the scratchpad (sha256
ece262b2, byte-identical to the phase-0-additions image): 5/11, every
result as predicted (M0 M1 M2 M4 N0 N1 FAIL on `HAL-MATCH ?` /
`MATCH-BIND ?`, M2 `0 0`; M3 M5 M6 N2 N3 PASS).

**Green, one fault on the way:** the first green run bound correctly (M2,
M3, N1, N2 passed) but printed names as garbage: the word buffer `'` leaves
is NUL-terminated, not counted (I read `movzx eax, byte [word_buffer]` in
CHAR as a length; it is the first character). MT-WORD measures to the NUL.
Then test-hal-match 11/11, two runs, 17.4 s (T_HAL_MATCH 35):

| check | result |
|---|---|
| M1 MATCH-BIND | `Machine: ForthGate / MatchTest`, `' TM-BASE BIND FB-BASE`, `' TM-FLUSH BIND FB-FLUSH`, nothing else |
| M2 | HAL-LIST FB-BASE -> TM-BASE's XT, FB-FLUSH -> TM-FLUSH's; FB-BASE = TM-SCR, two FB-FLUSH calls counted |
| M3 | BLK-READ AF7C / BLK-WRITE AF1C before and after |
| M4 | `BINDS: SPACE is not a HAL vector`; MATCH-LIST: OtherBox (1 binding), MatchTest (2) |
| M5 | `1234 41 FC` (the PIC mask as before) |
| N1 | `No machine entry for ForthGate / NoMatch: the defaults stay`, no BIND line |
| N2 | HAL-LIST identical, all four vectors; FB-BASE B8000 |
| M6 / N3 | DEPTH 0 |

~~Private (forthos-vocabularies 69a8ebd): test-hal-match-hp 5/5, two runs,
4.6 s (T_HAL_MATCH_HP 10): QEMU told the HP's expected strings, HAL-MACHINES
block-loads, MATCH-BIND prints its one BIND and binds BLK-READ, BLK-WRITE
unchanged, and on QEMU's i440fx (no AHCI) the bound reader refuses with
ior 1.~~ Resolved 2026-10-13: superseded by the amended entry (last section).

**Cost:** no kernel change (pad 8,995 B free, as after the phase 0
additions). HAL-MATCH and HAL-MACHINES are block-loaded: catalog blocks
only.

**Not covered:** no SMBIOS type 1 (`No SMBIOS type 1: the defaults stay`)
is not gated (every QEMU firmware here supplies one). The HP's strings are
unmeasured until the owner's session.

**Full make -k** on this tree (image 8c2fb84c, unchanged through the run):
all tests passed, 37.7 min, test-hal-match and test-hal-match-hp wired in.

## Notes, and the first private entry's bind dropped (2026-10-13)

Owner, 2026-10-13: the private entry's BLK-READ bind is held; bind BLK-READ
only on an installed-disk boot (BOOT-MODE 0), and only if the AHCI reader
uses the installed block store's layout; if not, the entry binds nothing
until the installed block store task, and says so.

**What the AHCI reader maps to.** `AHCI-BLK-READ` reads block N at absolute
LBA `BLOCKS-LBA-BASE + 2N` (225+2N), and refuses at LBA 0x800 or above: the
combined image's layout, as if the image began at LBA 0 of the SATA disk.
An installed instance has no block store at all: the installer writes the
VBR and the 224 kernel sectors into its partition, nothing more
(TASK_KERNEL_PAD_MOVE.md §3, red I1). So the bind is dropped; it returns
with the installed block store, on BOOT-MODE 0 only.

**Correction to the stated harm.** LOAD-VOCAB does not go through the
BLK-READ vector: catalog-resolver calls the kernel's `BLOCK`, which picks
the RAM image (memdisk, UEFI module) or ATA PIO by itself. The vector is
reached by `PBLK-READ` (SETTINGS, LOG-HARNESS, MIRROR). On a stick boot the
bind would have sent those persistent reads to the internal disk; vocabulary
loads were never affected. A gate on LOAD-VOCAB alone passes with or without
the bind, so the private gate also reads through the vector (P5 below).

**`MATCH-NOTE ( addr len -- )`** adds a line to the newest entry, in written
order among its binds:
```
: X-NOTE S" FB-FLUSH here only counts" ;
X-NOTE MATCH-NOTE
```
MATCH-BIND and MATCH-LIST print it as `Note: <text>`; it binds nothing. It
is kept as a binding with vector 0 (the text where the name goes), so the
one list holds binds and notes in the order written; MATCH-BIND skips
HAL-SET for it. With no MATCH-ENTRY: `MATCH-NOTE: no MATCH-ENTRY`.

Gates:
- test-hal-match: the MatchTest entry carries a note between its two binds.
  M1 expects `Machine`, `' TM-BASE BIND FB-BASE`, `Note: FB-FLUSH here only
  counts`, `' TM-FLUSH BIND FB-FLUSH`; M4's MATCH-LIST shows the note.
  Red (image 8c2fb84c, HAL-MATCH without MATCH-NOTE): 7/11, M0 M1 M4 N0, as
  predicted. Green 11/11, two runs, 18.8 s.
- Private, test-hal-match-hp, now booted as the stick boots (pxelinux ->
  memdisk, BOOT-MODE 1): P1 control (BOOT-MODE 1, the strings QEMU was
  told); P2 MATCH-LIST shows the entry and its note, no BIND; P3 MATCH-BIND
  prints the Machine line and the note only, HAL-LIST unchanged; P4
  LOAD-VOCAB still loads from the stick's blocks after MATCH-BIND; P5 a
  BLK-READ reaches the memdisk boot's own reader, `(BLK-READ-NONE)`
  (`BLOCK READ FAIL`, ior 1); P6 DEPTH 0. Red against the old entry: 3/6
  (P2 P3 P5), as predicted; P4 passed with the bad bind in place, which
  shows the LOAD-VOCAB gate is blind to it. The first red's P5 was void (my
  instrument: HAL not in the search order after LOAD-VOCAB). Green 6/6, two
  runs, 12.7 s (T_HAL_MATCH_HP 25: the boot is now PXE).
