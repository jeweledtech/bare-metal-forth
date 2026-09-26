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
0 1F 3 18 PCI-READ .H8         \ BAR2  record: ________
0 1F 3 1C PCI-READ .H8         \ BAR3  record: ________
0 1F 3 20 PCI-READ .H8         \ BAR4  record: ________
0 1F 3 24 PCI-READ .H8         \ BAR5  record: ________
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
