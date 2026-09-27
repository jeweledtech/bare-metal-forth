# DESK CARD — Older ASUS: ASUS-OLD-1 — boot and inventory (read-only)

**DRAFT, revised 2026-09-27 after the desk's first ruling. Do not print
until the desk approves this revision.**

**This is the first ForthOS trip to a machine other than the HP.** The
questions, in order:
1. Can its firmware boot the stick's path at all?
2. Does it boot to `ok`?
3. What is on its PCI bus?
4. Does the class search find its audio and SATA controllers?
5. Does AHCI see the disk?

Every line reads; nothing writes: no config space, no MMIO, no disk. The
only settings changed are firmware boot options, and only if Section 0
says so.

## Evidence: a photographic record, not a wire log (desk ruling 2026-09-27)

**Why no log.** The HP's evidence comes from the net console over its
RTL8168. **The Older ASUS has no wired NIC.** Its only network device
is an Intel Wireless-AC 9560 (8086:9DF0, `~/corpus/asus-old-pci-bound.csv`),
so no listener receives anything.

**What the record is.**
- **One photograph per section, at least.** Each section below names its
  file: `docs/evidence/asus-old-1-<date>-s<N>.jpg`, with `-s<N>b` for a
  second photo.
- The photos are committed under `docs/evidence/`.
- The outcome is **transcribed from the photos**, cites each file's
  sha256, and is headed **"photographic record, not a wire log"**.

**Named, later item:** there is no capture path for machines without
the RTL8168.

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

## Desk prep — deploy provenance

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

## 0. Firmware — before booting (the trip may stop here)

**The stick's boot path, from `tools/make-uefi-usb.sh`:** ForthOS boots
**only through Legacy BIOS / CSM** (GRUB BIOS, then `linux16 memdisk`,
then ForthOS in real mode). The stick's UEFI entry boots nothing: it
shows a menu saying CSM is required. Secure Boot must be off.

On the ASUS, enter firmware setup (key unknown; try F2 or Del at power-on)
and record, **before changing anything**:

| setting | as found |
|---|---|
| firmware setup key | ______ |
| Legacy / CSM support offered? | yes / no |
| CSM currently enabled? | yes / no |
| UEFI only? | yes / no |
| Secure Boot | on / off |
| boot-menu key | ______ |

- [ ] **No Legacy/CSM option at all ⇒ STOP.** The machine cannot boot
      this stick's path, and that is the result of the trip. Change
      nothing.
- [ ] CSM offered but off, or Secure Boot on ⇒ record the "as found"
      values first, then enable CSM and turn Secure Boot off, and record
      what was changed. **Every setting changed here is put back after
      the trip, and the card records that too.**

Photo: every firmware screen showing these settings
(`asus-old-1-<date>-s0.jpg`, `-s0b` …).

## 1. Boot — boot menu → FORTHBOOT (the Legacy/non-UEFI entry) → banner → `ok`

The boot banner prints, without typing, what auto-detect found. On the
HP that was graphics, xHCI, AHCI with "Drive on port N", the MBR and
NTFS.
- [ ] Reached `ok`: ____
- [ ] Banner lines about AHCI / "Drive on port" / NTFS: record them
      verbatim: ______
- [ ] No `ok`: record the last line on screen and STOP. That is the
      finding.

Photo: the whole banner (`asus-old-1-<date>-s1.jpg`).

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
Photo (`-s2.jpg`).

## 3. The bus

```forth
PCI-LIST
DECIMAL
```
- Record the device count: ____ (Windows lists 18 PCI functions; the
  bridges and host bridge are included there too).
- Record every row whose class is 04/03, 01/06 and 0C/03.

Photo: the whole list (`-s3.jpg`; `-s3b.jpg` if it scrolls).

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

Photo (`-s4.jpg`).

## 5. After

Power off. Put back every firmware setting Section 0 changed, and record
it: ______. Photo (`-s5.jpg`).
