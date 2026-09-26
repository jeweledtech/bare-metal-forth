# DESK CARD — HP 15-bs0xx: HDA-1 — the translated accessors on iron

Print this. Fill every blank **before leaving the desk**.

This trip's product is **one comparison, on real hardware**. Seven
`( base -- x )` words written by the translator from the Windows driver
`HDAudBus.sys` (function `1c0022510`) read the HDA controller's
registers. Their answers must equal:
- the values read by hand on 2026-09-25,
- and a direct read of the same address.

All reads, no writes. ONE evidence log: `docs/evidence/hda-iron-<date>.log`.

**The pair that matters is Section 4's last three lines.** The accessor
`HDAUDBUS-R58+14-W@` compiles the literal `14` and is correct only if
BASE was 16 when it compiled (`base-at-accessors-2026-09-25.md`). In
DECIMAL it would read 0x0E. `B1228014 W@` reads 0x14 directly, and
`B122800E W@` shows what the wrong base would have read. If 0x0E and
0x14 hold the same value, **the pair cannot tell the two apart. Record
that; do not claim the base question answered.**

**Dry-run (rule 16):** Sections 2–5 are typed into the QEMU fixture with
`-device intel-hda` (`docs/evidence/hda-1-dryrun-2026-09-25.log`, image `840696e3…`, THRU 579 602). The
fixture's controller is at 00:04.0, BAR `FEBB0000`, and the dry run
substitutes those for the HP's 00:1F.3 and `B1228000`, printing each
substitution. Values marked "iron" below are the HP readings from
2026-09-25, not QEMU's.

---

## 0. Desk prep — deploy provenance

```bash
git status --porcelain          # clean, or explain before proceeding
git remote -v                   # verified, not assumed
make build/combined.img         # the catalog must include HDAUDBUS
sha256sum forth/dict/hdaudbus.fth   # expect 4813ac3589b744fd...
sha256sum build/combined.img    # BUILD: ______  (expect 840696e3e6fafad6...)
python3 tools/catalog_layout.py HDAUDBUS   # THRU: ___ ___  (expect 579 602)
```
If BUILD is not `840696e3…`, the tree changed since the dry run. Record
the hash and the THRU range it prints, and use that range in Section 2.
The dry-run log then describes a different image, so note that.

`forth/dict/hdaudbus.fth` must be present: it is private (it lives in the
vocabularies repo and is ignored in the public tree). Its sha256 must be
`4813ac3589b744fd…`, which is the translator's `-f 1C0022510` output
unedited. If it is absent, the catalog lacks HDAUDBUS and Section 2's
gate prints 0.

Refresh FORTHBOOT (a file copy, NOT `make-uefi-usb.sh`):
```bash
lsblk -o NAME,LABEL,SIZE,TRAN   # exactly ONE FORTHBOOT, TRAN usb
sudo mount -L FORTHBOOT /mnt/fb
sudo cp build/combined.img /mnt/fb/forth.img && sync
sha256sum /mnt/fb/forth.img build/combined.img   # MUST match
```
Start the listener in a **second terminal**, while the stick is still
mounted. It hashes `--deployed` at startup, aborts on a mismatch, and
keeps running:
```bash
python3 tools/hp-portread-capture.py --boot-path usb \
    --deployed /mnt/fb/forth.img \
    --out docs/evidence/hda-iron-$(date +%F).log
```
Expect `hash gate: PASS (deployed == build)` and `boot path: usb`. Only
THEN, back in the first terminal:
```bash
sudo umount /mnt/fb        # the listener keeps running; move the stick to the HP
```
BUILD == STICK: ____

## 1. Boot — F9 → FORTHBOOT → banner → `ok`

NONCE / banner line: ______________________

## 2. Load + gate

```forth
DECIMAL ______ ______ THRU     \ HDAUDBUS range from Section 0
ONLY FORTH DEFINITIONS
ALSO PCI-ENUM  ALSO HDAUDBUS
DECIMAL
: DEF? WORD FIND NIP ;
```
```forth
DEF? DEF? .                    \ large nonzero; `DEF? ?` = retype the : line
```
```forth
DEF? HDAUDBUS-R58+14-W@ .      \ large nonzero; 0 = wrong image, STOP
```

## 3. The base address, re-read before any MMIO read

```forth
HEX
0 1F 3 4 PCI-READ .H8          \ iron: 00100006 (bit 1 = memory decode)
0 1F 3 10 PCI-READ .H8         \ iron: B1228004
0 1F 3 14 PCI-READ .H8         \ iron: 00000000 (below 4 GB)
```
- [ ] Command bit 1 clear ⇒ STOP (memory decode off, reads are floating).
- [ ] BAR not `B1228004` ⇒ STOP. Record it. The addresses below are
      wrong for this boot.
- [ ] Upper dword nonzero ⇒ STOP (above 4 GB; unreachable here).

## 4. The accessors against the hand reading and a direct read

Still in HEX. One read per line.
```forth
B1228000 HDAUDBUS-R58+2-C@ .H8     \ VMIN   expect 00000000 (iron 00)
B1228000 HDAUDBUS-R58+3-C@ .H8     \ VMAJ   expect 00000001 (iron 01)
B1228000 HDAUDBUS-R58+0-W@ .H8     \ GCAP   expect 00009701 (iron 9701)
B1228000 HDAUDBUS-R58+8-@ .H8      \ GCTL   expect 00000001 (iron)
B1228000 HDAUDBUS-R58+4-W@ .H8     \ OUTPAY record: ________
B1228004 W@ .H8                    \        must equal the line above
B1228000 HDAUDBUS-R58+6-W@ .H8     \ INPAY  record: ________
B1228006 W@ .H8                    \        must equal the line above
B1228000 HDAUDBUS-R58+14-W@ .H8    \ 0x14   record: ________
B1228014 W@ .H8                    \        must equal the line above
B122800E W@ .H8                    \ 0x0E   record: ________ (must DIFFER
                                   \        from 0x14 for the pair to count)
```
- [ ] Any of the first four not as expected ⇒ record, continue; that is
      the finding.
- [ ] `+14` ≠ direct 0x14 ⇒ **the accessor read the wrong register.**
      If it equals the 0x0E line, BASE was 10 at compile time. Record it.
- [ ] 0x0E = 0x14 ⇒ the base question is **not answered** on this
      machine. Record it.

## 4b. The base question, answered without the hardware

Section 4's pair cannot discriminate when 0x0E and 0x14 hold the same
value, and in the QEMU dry run both read 0. This section settles the
question in RAM:
- It writes `1111` at scratch+0x0E and `2222` at scratch+0x14, then runs
  the accessor on the scratch base.
- The scratch is free dictionary space 0x40 above `HERE @`. **`HERE @`,
  not `HERE`**: in this kernel `HERE` pushes the variable's address, so
  writing there would hit the system variables.
- Every word is a kernel word except the accessor, which Section 2
  gated. Still in HEX.

```forth
1111 HERE @ 40 + 0E + W!
2222 HERE @ 40 + 14 + W!
HERE @ 40 + HDAUDBUS-R58+14-W@ .H8  \ expect 00002222; 00001111 = BASE 10
```

## 5. Exit

```forth
DEPTH .                        \ expect 0
DECIMAL
```
Photo of the screen; end the log.
