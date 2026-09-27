# DESK CARD — Older ASUS: ASUS-OLD-1 — boot and inventory (read-only)

**DRAFT. Do not print until the desk rules on it.**

**This is the first ForthOS trip to a machine other than the HP.** The
questions, in order:
1. Does it boot to `ok`?
2. What is on its PCI bus?
3. Does the class search find its audio controller?
4. Does AHCI see the disk?

Every line reads; nothing writes: no config space, no MMIO, no disk.

## ⚠ Evidence: no listener log on this machine — the desk rules first

The HP's evidence comes from the net console, which runs over its
RTL8168. **The Older ASUS has no wired NIC.** Its only network device
is an Intel Wireless-AC 9560 (8086:9DF0, per
`~/corpus/asus-old-pci-bound.csv`), and ForthOS has no driver for it.
So `hp-portread-capture.py` will receive nothing, and **the record of
this trip is photos of the screen**.

The (by) ruling holds that evidence logs are the product's record, so
this needs the desk's ruling before printing. Options, not chosen here:
- **(a) Accept photos** for this one inventory trip. Every photo is
  named by section, and the banner photo carries the image hash check
  (Section 0 still hash-gates the stick).
- **(b) A USB-Ethernet adapter.** Not usable: ForthOS's USB stack has no
  network class driver.
- **(c) Take the stick's own log.** Not possible today: ForthOS has no
  file write to the boot stick.

**If the desk picks (a):** each section below ends with "Photo:", and
the outcome is transcribed from the photos, with each photo's file name
and sha256 cited.

## Expectations, from the Windows inventory (not from any ForthOS run)

`asus-old-pci-bound.csv`, 18 PCI functions:
- **Audio:** 8086:9DC8, Windows binds IntcAudioBus. Its INF id is
  `CC_040380`, so the class is **04/03 with prog-IF 80**, and
  `4 3 PCI-FIND-CLASS` should find it.
- **Storage:** 8086:9DD3 SATA AHCI (Windows iaStorAC).
- **USB:** 8086:9DED xHCI.
- **Graphics:** 8086:3EA0 UHD 620.

The b:d:f of each is **not known** (the CSV gives no bus numbers), so
the card records them.

---

## 0. Desk prep — deploy provenance

```bash
git status --porcelain          # clean, or explain before proceeding
git remote -v
make build/combined.img
sha256sum build/combined.img    # BUILD: ______
lsblk -o NAME,LABEL,SIZE,TRAN   # exactly ONE FORTHBOOT, TRAN usb
sudo mount -L FORTHBOOT /mnt/fb
sha256sum /mnt/fb/forth.img build/combined.img   # MUST match
sudo umount /mnt/fb
```
BUILD == STICK: ____

**Firmware:** Secure Boot must be off (the bootloader is unsigned), as
on the HP. The ASUS's boot-menu key is not known yet, so record it:
____.

## 1. Boot — boot menu → FORTHBOOT → banner → `ok`

The boot banner prints, without typing, what auto-detect found. On the
HP that was graphics, xHCI, AHCI with "Drive on port N", the MBR and
NTFS.
- [ ] Reached `ok`: ____
- [ ] Banner lines about AHCI / "Drive on port" / NTFS: record them
      verbatim: ______
- [ ] No `ok`: record the last line on screen and STOP. That is the
      finding.

Photo: the whole banner.

## 2. Gate

```forth
ONLY FORTH DEFINITIONS
ALSO PCI-ENUM
DECIMAL
: DEF? WORD FIND NIP ;
: CLR BEGIN DEPTH WHILE DROP REPEAT ;
DEF? DEF? .                    \ large nonzero
DEF? NO-SUCH-WORD .            \ expect 0; nonzero = STOP
DEF? PCI-FIND-CLASS .          \ large nonzero; 0 = STOP
```
Photo.

## 3. The bus

```forth
PCI-LIST
DECIMAL
```
- Record the device count: ____ (Windows lists 18 PCI functions; the
  bridges and host bridge are included there too).
- Record every row whose class is 04/03, 01/06 and 0C/03.

Photo: the whole list. If it scrolls, take two photos.

## 4. The class search — audio and storage

```forth
HEX
4 3 PCI-FIND-CLASS .S          \ expect a found b d f -1 (9DC8)
CLR
1 6 PCI-FIND-CLASS .S          \ expect a found b d f -1 (9DD3)
CLR
DEPTH .                        \ expect 0
DECIMAL
```
The b:d:f from each line must match the PCI-LIST row with that class.

Photo.

End: photo of the screen.
