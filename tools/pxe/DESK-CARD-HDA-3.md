# DESK CARD — HP 15-bs0xx: HDA-3 — the vocabulary finds its own base ((bz))

Print this only after the owner rules on it. Fill every blank **before
leaving the desk**.

This trip's product: the translated HDAUDBUS vocabulary reaches the HD
audio controller's registers **with no hand-typed address**. It finds
00:1F.3 by the class its own INF names (`PCI\CC_0403`) and takes BAR0
through `PCI-BAR64@`. The register values must equal HDA-1's, which
were read at the hand-typed base `B1228000`
(`hda-iron-2026-09-26.log`). Pre-registration:
`docs/evidence/bz-base-finding-prereg-2026-09-27.md`.

**Read-only.** Every word on this card reads config space or MMIO.
There is no PCI-ENABLE and no store. ONE evidence log:
`docs/evidence/hda3-iron-<date>.log`.

**Dry-run (rule 16):** every forth line below was typed into the QEMU
fixture with `-device intel-hda`, whose controller is at 00:04.0 with
BAR0 FEBB0000 (`docs/evidence/hda-3-dryrun-2026-09-27.log`). No line
types an address, so the dry run needs **no substitution**. Its
readings are QEMU's; the expectations below are the HP's.

---

## 0. Desk prep — deploy provenance

```bash
git status --porcelain          # clean, or explain before proceeding
git remote -v                   # verified, not assumed
make build/combined.img
sha256sum build/combined.img    # BUILD: ______  (expect 51cad6cf5080f770...)
```
**The image changed since HDA-2** (`840696e3…` → `51cad6cf…`). The
catalog gained pci-bar.fth, xhci.fth lost PCI-BAR64@, and hdaudbus.fth
gained the binding words. The kernel and embed did not change
(`bmforth.img` `dfd7c5f3…`). **The stick must be refreshed.** Use a
file copy, NOT `make-uefi-usb.sh`:
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
    --out docs/evidence/hda3-iron-$(date +%F).log
```
Expect `hash gate: PASS (deployed == build)` and `boot path: usb`. Only
THEN, back in the first terminal:
```bash
sudo umount /mnt/fb        # the listener keeps running; move the stick to the HP
```
BUILD == STICK: ____

The block ranges below are this build's: PCI-BAR 878–884, HDAUDBUS
579–603. If BUILD is not `51cad6cf…`, STOP. The ranges may have
moved.

**Typing:** fix typos with backspace as usual. The log's echo shows two
stray spaces per erased character ((by)); the line typed is still what
counts.

## 1. Boot — F9 → FORTHBOOT → banner → `ok`

NONCE / banner line: ______________________

## 2. Load + gate — with a control that must print 0

```forth
ONLY FORTH DEFINITIONS
DECIMAL
878 884 THRU
579 603 THRU
ONLY FORTH DEFINITIONS
ALSO PCI-ENUM
: DEF? WORD FIND NIP ;
: CLR BEGIN DEPTH WHILE DROP REPEAT ;
DEF? DEF? .                    \ large nonzero
DEF? NO-SUCH-WORD .            \ expect 0; nonzero = DEF? cannot say no, STOP
DEF? PCI-BAR .                 \ nonzero; 0 = PCI-BAR did not load, STOP
DEF? HDAUDBUS .                \ nonzero; 0 = HDAUDBUS did not load, STOP
ALSO PCI-BAR
ALSO HDAUDBUS
DEF? HDAUDBUS-R58-BASE .       \ nonzero; 0 = old hdaudbus.fth, STOP
```
`PCI-BAR vocab loaded` prints during the first THRU. Each ALSO is typed
only after its DEF? line printed nonzero: ALSO of an undefined name
corrupts the dictionary.

## 3. The instances — every 04/03 function, none chosen implicitly

Still in DECIMAL.
```forth
HDAUDBUS-COUNT .               \ expect 1; record: ____
HDAUDBUS-LIST                  \ expect one row: 0 00:1F.3
HEX
0 HDAUDBUS-BDF .S              \ expect <0 1F 3 -1 >
CLR
4 3 PCI-FIND-CLASS .S          \ must equal the line above
CLR
1 HDAUDBUS-R58-BASE .          \ expect 0: no instance 1
DEPTH .                        \ expect 0
```
- [ ] COUNT ≥ 2 ⇒ **record every LIST row.** The HP then has more than
      one 04/03 function. Continue with instance 0, and say so on the
      outcome.
- [ ] `0 HDAUDBUS-BDF` differs from `PCI-FIND-CLASS` ⇒ the two
      searches disagree on the same table. Record both, STOP.

## 4. The base and the registers — no typed address

Still in HEX. Every value was read at the hand-typed base on 09-26.
```forth
0 HDAUDBUS-R58-BASE .H8                  \ expect B1228000
0 HDAUDBUS-R58-BASE HDAUDBUS-R58+2-C@ .H8
0 HDAUDBUS-R58-BASE HDAUDBUS-R58+3-C@ .H8
0 HDAUDBUS-R58-BASE HDAUDBUS-R58+0-W@ .H8
0 HDAUDBUS-R58-BASE HDAUDBUS-R58+8-@ .H8
0 HDAUDBUS-R58-BASE HDAUDBUS-R58+4-W@ .H8
0 HDAUDBUS-R58-BASE HDAUDBUS-R58+6-W@ .H8
0 HDAUDBUS-R58-BASE HDAUDBUS-R58+14-W@ .H8
DEPTH .                                  \ expect 0
```
Expected, line by line (HDA-1, `hda-iron-2026-09-26.log` l.56–76):

| line | register | expect | record |
|---|---|---|---|
| base | BAR0 | B1228000 | ________ |
| +2 C@ | VMIN | 00000000 | ________ |
| +3 C@ | VMAJ | 00000001 | ________ |
| +0 W@ | GCAP | 00009701 | ________ |
| +8 @ | GCTL | 00000001 | ________ |
| +4 W@ | OUTPAY | 0000003C | ________ |
| +6 W@ | INPAY | 0000001C | ________ |
| +14 W@ | 0x14 | 00000C00 | ________ |

- [ ] The base is `00000000` ⇒ the search or PCI-BAR64@ refused. Record
      it, and skip the register lines, which would read page 0.
- [ ] The base is not B1228000 ⇒ record it, then continue. The
      registers then say whether it is still an HDA controller (VMAJ 01).

## 5. The bus, for the count — read-only

```forth
PCI-LIST
DECIMAL
DEPTH .                        \ expect 0
```
Record every row whose class column reads `04/03`: ______. This is the
first **logged** count of the HP's 04/03 functions (the 09-25 count is a
photo). It must equal Section 3's COUNT.

Photo of the screen; end the log.
