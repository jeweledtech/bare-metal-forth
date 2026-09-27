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

---

## Outcome — 2026-09-27 (written from the log only)

Log: `docs/evidence/hda3-iron-2026-09-27.log`, sha256 `e31d60702bd40e59…`.
Line numbers below are that file's. All 15 lines with erases were
replayed byte by byte (`08 20 20 08 20` per erase, (by)). Each
resolves to the card's line exactly, with no stray `08`. The break
inside PCI-LIST at l.112–113 is a UDP packet boundary: a new timestamp
opens l.113, and the row reads `00 1C 00 8086:9D14 06/04`.

- **Section 0:** `hash gate: PASS (deployed == build)`, image
  `51cad6cf…` on both (l.5–8); boot path usb (l.9); HEAD 475484f (l.3).
- **Section 2:**
  - `DEF? DEF? .` = 377848 (l.51).
  - `DEF? NO-SUCH-WORD .` = 0 (l.53).
  - PCI-BAR 375788 (l.55), HDAUDBUS 377248 (l.57),
    HDAUDBUS-R58-BASE 377756 (l.63). All three equal the dry run's
    numbers.
- **Section 3:**
  - COUNT 1 (l.65).
  - LIST `0 00:1F.3` (l.68).
  - `0 HDAUDBUS-BDF .S` = `<0 1F 3 -1 >` (l.72) = `4 3 PCI-FIND-CLASS .S`
    (l.76).
  - `1 HDAUDBUS-R58-BASE` = 0 (l.80).
  - DEPTH 0 (l.82).
- **Section 4:**
  - base **B1228000** (l.84);
  - VMIN 00000000 (l.86), VMAJ 00000001 (l.88), GCAP 00009701 (l.90),
    GCTL 00000001 (l.92), OUTPAY 0000003C (l.94), INPAY 0000001C (l.96),
    0x14 00000C00 (l.98);
  - DEPTH 0 (l.100).

  **All eight equal HDA-1's.**
- **Section 5:** PCI-LIST shows **16 devices** (l.121). Exactly one
  row reads 04/03: `00 1F 03 8086:9D71` (l.117). That equals Section
  3's COUNT. DEPTH 0 (l.126).

**Every pre-registered HP prediction held**
(`bz-base-finding-prereg-2026-09-27.md`).

**Independent checks: three.**
1. The emitted base equals the address HDA-1 typed by hand
   (B1228000). This run reached it through the INF's class,
   PCI-CLASS-NTH and PCI-BAR64@, with no typed address.
2. PCI-CLASS-NTH (pci-bar.fth, block-loaded) and PCI-FIND-CLASS (embedded
   pci-enum) return the same b:d:f. They share PCI-TBL, but not the
   code that walks it.
3. COUNT 1 equals PCI-LIST's single 04/03 row. They share the table's
   class bytes; COUNT also confirms each hit with a live config read.

The eight register values repeat HDA-1 through the same accessors:
that is repetition, not a check.

**The HP's 04/03 count is now logged:** one function among 16. That
supersedes the 09-25 photo as the record, and the photo becomes
corroboration when it is committed.

**(bz) closes on iron.**

### Addendum — 2026-09-27, after the desk's review

**The independent-check count is four, not three.** The desk named the
instance-1 refusal (`1 HDAUDBUS-R58-BASE` = 0, l.80) as a check. It is
one: it runs PCI-CLASS-NTH's out-of-range branch, which no other line on
the card reaches. The list is then:
1. the found base = the hand-typed base;
2. BDF = PCI-FIND-CLASS;
3. COUNT = PCI-LIST's single 04/03 row;
4. the instance-1 refusal.

The desk also listed "the config BAR read". That is not a fifth check.
PCI-BAR64@ reads the same register (config 0x10 = B1228004 on 09-25),
so it belongs to check 1.

**The stick — observed (host kernel log, 2026-09-27):**
- **08:19:56–08:22:14.** Port 3-5 enumerated a `General UDisk`, USB id
  `abcd:1234`, serial `2306262320331016668715`, 126 MB (245,760
  sectors). That is the stick that carried HDA-2 (listener 08:21:59).
- **14:59:38–15:10:11.** On port 3-5, a device with the **same serial**
  connected and disconnected repeatedly, then failed to enumerate with
  **32 `error -71`** lines, the first at 14:59:42 and the last at
  15:10:11.
- **15:10:23, and again at 15:12:13.** Port **3-6** enumerated a device
  with the **same id and serial** cleanly. The listener started at
  15:11:43, so this is the stick that carried HDA-3. Its image is
  hash-gated `51cad6cf…` (l.5–8).
- **14:49:43.** A separate `SanDisk 3.2Gen1` (`0781:55ab`, 988 GB)
  attached on port 6-1. Nothing ties it to this run.

**Not established by the log:**
- **Whether HDA-3's stick is the one that failed or a second one.**
  Generic `abcd:1234` UDisks commonly share one factory serial, so the
  serial cannot tell two units apart.
- **How HDA-3's stick was provisioned** (the card's file copy or
  `make-uefi-usb.sh`). This session's shell history is not yet
  written to disk.

The owner says the old FORTHBOOT failed (-71, not enumerating) and was
retired. The -71 run on port 3-5 is consistent with that. It is also
consistent with a bad port or cable, because the same serial
enumerated on 3-6 eleven seconds later. **The owner records which
physical stick this was and how it was written.** Every trip's hash
gate still proves the image, whichever stick carries it.

**The stick, owner ruling (2026-09-27):**
- **It was the SAME stick for HDA-2 and HDA-3.**
  - On the HP, one USB port did not show it at F9; the other port booted
    it.
  - On the dev box it failed repeatedly on port 3-5 and worked on 3-6.
- **Recorded as a marginal stick/port combination, not a failed stick.**
  The desk's "failed and retired" was the desk's own inference, and it
  is recorded as a **desk error**. The kernel log above is consistent
  with the owner's account: same serial on both ports.
- **The image was written by the card's usual Section 0 copy** (a file
  copy, not `make-uefi-usb.sh`).
- **Recommended:** provision a spare stick. The hash gate stays the
  protection, whichever stick carries the image.
