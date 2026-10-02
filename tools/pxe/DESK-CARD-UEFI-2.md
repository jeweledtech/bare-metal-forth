# DESK CARD — HP 15-bs0xx: UEFI-2 — the kernel on its own GDT (M3)

> **PRE-FLIGHT — hashes are generated, not pinned (2026-10-01).** This
> card no longer carries image hashes inline: pinned hashes went stale
> once from CARRIER-0b and will again when the wizard branch shifts the
> catalog blocks. The trip is pinned by the **commit**, and the stick is
> checked against a **generated** hash file:
>
> 1. **Record the commit:** `git status --porcelain` clean and
>    `git rev-parse HEAD`. That — not a hash printed here — says which
>    tree the trip ran.
> 2. **Generate the hashes:** `make desk-hashes` writes
>    `build/desk-hashes.txt` (bmforth + combined for the current build).
> 3. **Rewrite the stick** and confirm its `forth.img` equals the
>    `combined.img` line in that file. A stick written against an older
>    build carries a different kernel and must not be used.

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
git remote -v                   # destination verified, not assumed
git rev-parse HEAD              # RECORD this — it says which tree ran: ____
make desk-hashes               # builds images, writes build/desk-hashes.txt
cat build/desk-hashes.txt      # GENERATED for this build: 2 hashes + PCI-BAR range
```
Nothing build-derived is pinned on this card. `build/desk-hashes.txt`
carries, for the tree you just recorded, the `bmforth.img` and
`combined.img` hashes **and** the `PCI-BAR` catalog block range. The stick is
checked against the combined.img line (below); the THRU line in §2 uses the
PCI-BAR range. Neither is a literal printed here that could go stale — a
pinned hash went stale once at CARRIER-0b, and the firstboot-wizard merge
moves the PCI-BAR range the same way.

**The image changed at CARRIER-0b** (and will change again on the wizard
branch), so the stick must be refreshed with the usual file copy, **NOT**
`make-uefi-usb.sh`:
```bash
lsblk -o NAME,LABEL,SIZE,TRAN   # exactly ONE FORTHBOOT, TRAN usb
sudo mount -L FORTHBOOT /mnt/fb
sudo cp build/combined.img /mnt/fb/forth.img && sync
# Confirm the stick carries THIS build's kernel — compare, don't eyeball:
STICK=$(sha256sum /mnt/fb/forth.img | cut -d' ' -f1)
WANT=$(awk '/combined.img/{print $2}' build/desk-hashes.txt)
[ "$STICK" = "$WANT" ] && echo "BUILD == STICK OK" || echo "MISMATCH — rewrite"
```
BUILD == STICK: ____

**Stick and port.** The stick/port combination is marginal (HDA-3
addendum). If the stick does not show at F9 on one HP port, use the
other, and record which: ____. If it shows at no port and you fall back
to PXE, that is the USB-not-offered finding — record it, the trip still
runs over PXE.

Start the listener in a **second terminal**, while the stick is mounted:
```bash
python3 tools/hp-portread-capture.py --boot-path usb \
    --deployed /mnt/fb/forth.img \
    --out docs/evidence/uefi2-iron-$(date +%F).log
```
Expect `hash gate: PASS (deployed == build)`. The header records
`boot path (intended): usb`; the **actual** path is detected from this
box and appended when you stop the listener. If the stick was not offered
and you booted PXE, the footer says so and flags the flag/evidence
discrepancy — no hand-written correction note needed. Then:
```bash
sudo umount /mnt/fb
```

**Block range.** The THRU range for PCI-BAR is the `PCI-BAR` line of
`build/desk-hashes.txt` (e.g. `PCI-BAR 878 884` on the pre-wizard image) —
type those two numbers into §2. It is derived from the built blocks image by
`tools/catalog_layout.py`, the same parser the G6 harness and the catalog
completeness gate read, so a catalog shift re-derives here instead of
silently invalidating the card: the firstboot-wizard merge inserts FIRSTBOOT
ahead of PCI-BAR and moves it off 878–884. Cross-check in the image's own
bytes if in doubt — the first block of the range begins `\ CATALOG: PCI-BAR`,
and the block just past the range begins the next vocab's `\ CATALOG:`
banner.

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
878 884 THRU                   \ <first> <last> from desk-hashes.txt PCI-BAR line
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

**R2 — `efibootmgr -v` on the HP, the G4 equality baseline.** R2 is the
**HP's own** NVRAM boot-entry list, read **on the HP**, UEFI-booted,
**before and after an install** — the G4 equality gate checks that an
install leaves the HP's firmware boot variables unchanged. A dev-box
`efibootmgr -v` is a *different machine's* NVRAM and **cannot** serve this
baseline; do not substitute one (caught 2026-10-01 — a dev-box capture was
recorded as R2 and had to be withdrawn).
```bash
# ON THE HP, only when it came up UEFI-booted (not legacy/CSM):
[ -d /sys/firmware/efi ] && efibootmgr -v \
  || echo "legacy/CSM boot — R2 not capturable (needs a UEFI boot)"
```
This UEFI-2 trip is read-only and boots legacy PXE, so R2 is not
capturable here by construction — the log records "legacy — skipped". It
is owed from a UEFI-booted HP install trip, before and after: ____
