# DESK CARD — HP 15-bs0xx: UEFI-2 — the kernel on its own GDT (M3)

> **PRE-FLIGHT — regenerated for the post-CARRIER-0b tree (2026-09-30).**
> This card was updated after the CARRIER-0b write-vector fix. The kernel
> is now `bmforth b9593319…`; the stick image is `combined.img 6fac2873…`
> (which embeds that kernel). Two things MUST be redone before the trip,
> or the stick runs a kernel that no longer matches the tree:
>
> 1. **Rebuild and re-confirm the BUILD hashes** in Section 0 — they are
>    filled for `b9593319` / `6fac2873`. If `make build/combined.img`
>    yields anything else, the tree moved again: STOP and regenerate.
> 2. **Rewrite the stick** (Section 0's file-copy) and confirm its
>    `forth.img` hashes to `6fac2873…`. A stick written before CARRIER-0b
>    carries the old kernel (`848971e1`) and must not be used.

Print this only after the owner rules on it. Fill every blank **before
leaving the desk**.

**What CARRIER-0b did and did not change (2026-09-30).** The HP boots
PXE / GRUB / memdisk, so its base cell (`BLK_IMAGE_BASE`, 0x28098) is
**non-zero**. Under the old code a non-zero cell already armed
`(BLK-WRITE-NONE)`; CARRIER-0b changed only the cell-**zero** branch. So
the HP's boot path behaves **identically** before and after the fix, and
block persistence still comes from `AHCI-RW` overriding the write vector
at runtime, not from the boot-time default. **For the bench:** a
block-write difference observed here is a **finding to record, not an
expected effect of the new kernel** — do not spend bench time blaming
CARRIER-0b for it.

**What this trip checks.** UEFI-2 changed the kernel.
- **Before:** it ran on the boot sector's GDT (QEMU: `GDT= 00007d90`).
- **Now:** it loads its **own** GDT first thing. That GDT is inside the
  kernel image (QEMU: `GDT= 0000abc8`), with the same selectors: code
  0x08, data 0x10.
- **Also changed:** the block-image base became one name
  (`BLK_IMAGE_BASE`) at the same cell, 0x28098.

This is the HP half of M3. Three things must still hold on iron:
1. it boots to `ok`;
2. blocks load from the memdisk RAM image;
3. a config-space read through PCI-BAR returns what HDA-3 logged.

Pre-registration: `docs/evidence/uefi-2-prereg-2026-09-28.md`, amendment
(c).

**Read-only.** No store and no PCI-ENABLE. ONE evidence log:
`docs/evidence/uefi2-iron-<date>.log`. **Commit it only after the
listener stops** (ruled 2026-09-27).

**Dry-run (rule 16):** `docs/evidence/uefi-2-dryrun-2026-09-28.log`, QEMU
with `-device intel-hda` at 00:04.0 (BAR0 FEBB0000). The dry run
substitutes `0 4 0` for the HP's `0 1F 3`. Its readings are QEMU's; the
expectations below are the HP's.

---

## 0. Desk prep — deploy provenance

```bash
git status --porcelain          # clean, or explain before proceeding
git remote -v
make build/combined.img
sha256sum build/bmforth.img     # expect b9593319b316b007c5176ec156ccd623f57d7ea1f344220a351194dbdb3f3c40
sha256sum build/combined.img    # expect 6fac2873dff359c2da9357fd6dc126e24b5b7e5546a5060e65d274d539ec5998
```
If either hash differs, the tree changed since this card was
regenerated (`b9593319` / `6fac2873`): **STOP** and regenerate.

**The image changed** (combined `51cad6cf…` HDA-3 → `be05f8e7…` UEFI-2
→ `6fac2873…` CARRIER-0b), so the stick must be refreshed with the usual
file copy, NOT `make-uefi-usb.sh`:
```bash
lsblk -o NAME,LABEL,SIZE,TRAN   # exactly ONE FORTHBOOT, TRAN usb
sudo mount -L FORTHBOOT /mnt/fb
sudo cp build/combined.img /mnt/fb/forth.img && sync
sha256sum /mnt/fb/forth.img build/combined.img   # MUST match, = 6fac2873…
```
**Stick and port.** The stick/port combination is marginal (HDA-3
addendum). If the stick does not show at F9 on one HP port, use the
other, and record which: ____.

Start the listener in a **second terminal**, while the stick is mounted:
```bash
python3 tools/hp-portread-capture.py --boot-path usb \
    --deployed /mnt/fb/forth.img \
    --out docs/evidence/uefi2-iron-$(date +%F).log
```
Expect `hash gate: PASS (deployed == build)` and `boot path: usb`. Then:
```bash
sudo umount /mnt/fb
```
BUILD == STICK: ____

**Block range.** `878 884 THRU` is PCI-BAR on this image. It was
checked two ways:
- the host resolver places PCI-BAR at 878–884;
- in the image's own bytes, block 878 begins `\ CATALOG: PCI-BAR`,
  block 884 holds PCI-BAR's last lines, and block 885 begins
  `\ CATALOG: PCI-ENUM`.

**Typing.** Erased characters echo as two stray spaces ((by)). The line
typed is what counts, and the outcome replays the bytes.

## 1. Boot — F9 → FORTHBOOT → banner → `ok`

The same banner as HDA-3: net console, the auto-detect lines, AHCI,
MBR/NTFS, then `ok`.
- [ ] Reached `ok`: ____
- [ ] No `ok`, a reboot loop or a hang ⇒ **STOP, and that is the
      result.** The kernel's first new instructions are the `lgdt` and
      the far jump. Photo the screen.

## 2. Blocks and the gate

```forth
ONLY FORTH DEFINITIONS
DECIMAL
878 884 THRU
ALSO PCI-ENUM
: DEF? WORD FIND NIP ;
DEF? DEF? .                    \ large nonzero
DEF? NO-SUCH-WORD .            \ expect 0; nonzero = STOP
DEF? PCI-BAR .                 \ nonzero; 0 = the blocks did not load, STOP
ALSO PCI-BAR
```
**The proof that the blocks loaded is `DEF? PCI-BAR` nonzero.** That
means the block path (memdisk RAM, through `BLK_IMAGE_BASE`) works on
iron.

The `." PCI-BAR vocab loaded"` at the end of `pci-bar.fth` does **not**
print when the file is block-loaded. The THRU line shows only `ok`, in
HDA-3's iron log and in this card's dry run. That is a named item,
separate from this trip, and not a failure.

## 3. One config-space read through PCI-BAR (amendment c)

```forth
HEX
DEPTH .                        \ expect 0
0 1F 3 0 PCI-BAR64@ .H8        \ expect B1228000
DEPTH .                        \ expect 0
DECIMAL
```
**Expect B1228000.** It is the raw config 0x10 value B1228004
(`hda-iron-and-spec-2026-09-25.md` l.10) with its flag bits masked by
PCI-BAR64@. HDA-3 logged it as `B1228000ok` (`hda3-iron-2026-09-27.log`
l.84).
- [ ] Anything else ⇒ record it and STOP.

Photo of the screen; stop the listener; **then** commit the log.

## Opportunistic captures — a skip here is NOT a trip failure

Two extras worth grabbing while at the machine. Neither gates the trip;
mark a skip as a skip, do not treat it as a red.

**R6 — firmware state, verbatim.** At the F10 firmware screen, before
changing anything, record exactly:
- CSM / Legacy Support: on / off ⇒ ____
- Secure Boot: on / off ⇒ ____
Its job is to make a *future* firmware-settings change diagnosable as a
settings change, not a code regression. Photo the screen too.

**R2 — `efibootmgr -v`, verbatim (UEFI-booted dev-box sessions only).**
On the dev box, only if this session came up UEFI-booted:
```bash
[ -d /sys/firmware/efi ] && efibootmgr -v \
  || echo "legacy/CSM session — R2 skipped (cannot capture from here)"
```
It is the G4 equality baseline and **cannot** be captured from a
legacy/CSM session. If legacy, skip it and write "legacy — skipped"
rather than improvising: ____
