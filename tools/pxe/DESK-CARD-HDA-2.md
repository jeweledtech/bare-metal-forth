# DESK CARD — HP 15-bs0xx: HDA-2 — how the controller can be found

Print this only after the owner rules on it. Fill every blank **before
leaving the desk**.

This trip's product is **three readings, all read-only**. They supply
the facts the base-finding design needs, and HDA-1 did not take them:
- the size of the PCI table that `PCI-FIND-CLASS` walks (it holds at
  most 32 entries, `MAX-DEVS`, and drops the rest without a word);
- whether `4 3 PCI-FIND-CLASS` finds 00:1F.3 on its own;
- how many memory BARs 00:1F.3 has. HDA-1 read only 0x10 and 0x14.

No writes: to config space, MMIO or RAM. ONE evidence log:
`docs/evidence/hda2-iron-<date>.log`.

**Dry-run (rule 16):** Sections 2–4 are typed into the QEMU fixture with
`-device intel-hda` (`docs/evidence/hda-2-dryrun-2026-09-26.log`, image
`840696e3…`). The fixture's controller is at 00:04.0, and the dry run
substitutes `0 4 0` for the HP's `0 1F 3`. Its readings are QEMU's.
The expectations below are the HP's.

---

## 0. Desk prep — deploy provenance

```bash
git status --porcelain          # clean, or explain before proceeding
git remote -v                   # verified, not assumed
make build/combined.img
sha256sum build/combined.img    # BUILD: ______  (expect 840696e3e6fafad6...)
```
If BUILD is not `840696e3…`, the tree changed since the dry run. Record
the hash; the dry-run log then describes a different image, so note
that. PCI-ENUM is embedded, so this card needs no THRU and no private
package.

If the FORTHBOOT stick still carries HDA-1's image, the hash gate below
proves it and no copy is needed. Otherwise refresh it (a file copy, NOT
`make-uefi-usb.sh`):
```bash
lsblk -o NAME,LABEL,SIZE,TRAN   # exactly ONE FORTHBOOT, TRAN usb
sudo mount -L FORTHBOOT /mnt/fb
sudo cp build/combined.img /mnt/fb/forth.img && sync
sha256sum /mnt/fb/forth.img build/combined.img   # MUST match
```
Start the listener in a **second terminal**, while the stick is mounted:
```bash
python3 tools/hp-portread-capture.py --boot-path usb \
    --deployed /mnt/fb/forth.img \
    --out docs/evidence/hda2-iron-$(date +%F).log
```
Expect `hash gate: PASS (deployed == build)` and `boot path: usb`. Only
THEN, back in the first terminal:
```bash
sudo umount /mnt/fb        # the listener keeps running; move the stick to the HP
```
BUILD == STICK: ____

**Typing:** fix typos with backspace as usual. The log's echo shows two
stray spaces per erased character ((by)); the line typed is still what
counts.

## 1. Boot — F9 → FORTHBOOT → banner → `ok`

NONCE / banner line: ______________________

## 2. Gate — with a control that must print 0

```forth
ONLY FORTH DEFINITIONS
ALSO PCI-ENUM
DECIMAL
: DEF? WORD FIND NIP ;
: CLR BEGIN DEPTH WHILE DROP REPEAT ;
```
```forth
DEF? DEF? .                    \ large nonzero; `DEF? ?` = retype the : line
DEF? NO-SUCH-WORD .            \ expect 0; nonzero = DEF? cannot say no, STOP
DEF? PCI-FIND-CLASS .          \ large nonzero; 0 = PCI-ENUM absent, STOP
```
`CLR` empties the stack whatever is on it. Section 3 uses it instead of
a fixed number of DROPs because the result's depth depends on the
reading, and dropping past the floor resets the machine silently (bug
#35).

## 3. The table and the class search

Still in DECIMAL. `PCI-LIST` prints its count in decimal, so the
comparison below is decimal.
```forth
PCI-COUNT @ .                  \ expect 16 (owner, 09-25 PCI-LIST); record: ____
```
- [ ] 32 ⇒ the table is **full**, and any device past the 32nd was
      dropped. Record it; the next line then decides whether 00:1F.3
      was one of them.
```forth
HEX
4 3 PCI-FIND-CLASS .S          \ expect <0 1F 3 -1 >; <0 > = not found
CLR
DEPTH .                        \ expect 0
```
- [ ] `<0 >` ⇒ `PCI-FIND-CLASS` does **not** find the controller.
      Record it with the count above. Continue; Section 4 does not use
      the search.
- [ ] Found, but not `0 1F 3` ⇒ another 04/03 device comes first in
      the table. Record the b d f.

## 4. 00:1F.3's class and the BAR slots HDA-1 did not read

Still in HEX. One read per line.
```forth
0 1F 3 8 PCI-READ .H8          \ class/rev  expect 04030021 (owner, 09-25)
0 1F 3 18 PCI-READ .H8         \ BAR2  record: __00000000______
0 1F 3 1C PCI-READ .H8         \ BAR3  record: __00000000______
0 1F 3 20 PCI-READ .H8         \ BAR4  record: __B1200004______
0 1F 3 24 PCI-READ .H8         \ BAR5  record: __00000000______
```
Candidates, named before the trip. They are **reasoned, not cited**:
no PCH datasheet is pinned in the repo. B comes from Intel's usual
layout for PCH audio, where a second, DSP register BAR sits at 0x20
with its upper half at 0x24.
- **A — one memory BAR.** 0x18–0x24 all `00000000`. BAR0 (read in
  HDA-1) is the only one, and "first memory resource" means BAR0 with
  nothing to choose.
- **B — two memory BARs.** 0x20 reads as a 64-bit memory BAR (low
  nibble `4`), with 0x24 its upper half; 0x18 and 0x1C are `00000000`.
  "First memory resource" then has to mean BAR0 by position, which is
  an assumption about Windows' resource order.
- **Neither** ⇒ record the four values. That is the finding.

A zero read is not proof that a slot is unimplemented: only a sizing
write can prove that, and this card writes nothing. Firmware assigns
every BAR a device implements, so zero is the expected reading for an
empty slot. Record it as "reads 0", not "absent".

## 5. Exit

```forth
DEPTH .                        \ expect 0
DECIMAL
```
Photo of the screen; end the log.

---

## Outcome — 2026-09-27 (written from the log only)

Log: `docs/evidence/hda2-iron-2026-09-27.log`, sha256 `2630c8cbb9fc78c2…`.
Line numbers below are that file's. Every line with erases was replayed
byte by byte (`08 20 20 08 20` per erase, (by)); each resolves to the
card's line exactly, with no stray `08`. The echo `01      1F 3 24` is
`0 1F 3 24`.

- Section 0: `hash gate: PASS (deployed == build)`, image `840696e3…`
  on both (l.5–8); boot path usb (l.9); HEAD b56a22e (l.3).
- Section 2: `DEF? DEF? .` = 375788 (l.31); `DEF? NO-SUCH-WORD .` = 0
  (l.33), so DEF? can say no; `DEF? PCI-FIND-CLASS .` = 212432 (l.35).
- Section 3: `PCI-COUNT @ .` = 16 (l.37), as expected; the table is not
  full. `4 3 PCI-FIND-CLASS .S` = `<0 1F 3 -1 >` (l.41), found on its
  own; DEPTH 0 after CLR (l.45).
- Section 4: class/rev 04030021 (l.47). BAR2 0x18 00000000 (l.49),
  BAR3 0x1C 00000000 (l.51), BAR4 0x20 B1200004 (l.53), BAR5 0x24
  00000000 (l.55).
- Section 5: DEPTH 0 (l.57).

**Candidate B.** 00:1F.3 reads as two 64-bit memory BARs: BAR0
0x00000000_B1228000 (HDA-1) and BAR4 0x00000000_B1200000. "First memory
resource" therefore has a choice to make on the HP. QEMU's intel-hda has
one BAR (candidate A), so the fixture cannot exercise that choice.

**Independent checks: two.**
1. The class search and the direct read agree by different paths:
   `PCI-FIND-CLASS` walks the table built at enumeration and finds
   0 1F 3, and `PCI-READ` of 0x08 at 0 1F 3 gives class 04/03. The class
   read repeats 09-25's hand read; that is repetition, not a third check.
2. The DEF? control prints 0 (the gap HDA-1's notes recorded, closed).
The four BAR readings are one read each, with no second path.

Notes, not defects of this card:
- Prog-if is 00 (040300), not 80. The INF trees give the same picture:
  the HP's only 0403 function-driver INF is hdaudbus.inf (`PCI\CC_0403`),
  while the intcaudiobus.inf IDs on the other three machines are
  `CC_040380` (`~/corpus/tools-2026-09-26/inf_cc0403.out`). Hardware
  and rules agree; what Windows actually bound waits on the HP's
  pci-bound.csv.
- `PCI-LIST` was advised for after Section 5 and was not typed (the log
  has 0 lines containing it). The HP's count of 04/03 functions is
  still not in any log; `PCI-FIND-CLASS` reports the first match only.
- BAR4's size is unknown: sizing needs a write, and this card writes
  nothing. *Reasoned, not measured:* with memory decode on (command
  0006, `hda-iron-and-spec-2026-09-25.md`) and BAR0 at B1228000, non-overlapping assignment would bound
  BAR4 at 0x20000 or less.

**Note, 2026-09-27 (after commit 134869d).** The listener was still
running when this log was committed. It was stopped at 15:11:39, just
before HDA-3's listener started, and the capture tool then appended
one footer line: `=== capture stopped 2026-09-27T15:11:39.287111-07:00
===`. **Nothing else was received between 08:28:15 and the stop.**

That footer is **not** committed (owner ruling): the committed file
stays `2630c8cbb9fc78c2…`, the sha this outcome cites. From now on,
iron logs are committed only after the listener stops.
