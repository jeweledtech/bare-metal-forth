# CARRIER-0 — every reader of the memdisk base (read-only audit, 2026-09-29)

The coupling list §3a needs and N1 turns on. Read-only: no code changed.
It answers one question — **what breaks when the memdisk RAM image is
gone and the base cell reads 0** (a native-VBR stick boot, or, per the
owner's 2026-09-29 correction, *any UEFI boot*, since a UEFI load path
has no `memdisk raw` either).

## The cell

One physical dword at **0x28098**, written by the boot sector's memdisk
probe before the kernel runs (`boot.asm:131`, `vbr.asm:78,88`). `0` = not
a memdisk boot. It carries **four names** for the one address, because
public code cannot name a paid word:

| name | where | note |
|---|---|---|
| `BLK_IMAGE_BASE` | `forth.asm:141` (was `MEMDISK_BASE` until UEFI-2) | the kernel cell |
| `MEMDISK-VAR` | `ahci.fth:524` (`28098 CONSTANT`) | paid vocab |
| `MEM-BASE` | `install.fth:892` (`28098 @` snapshot) | installer's copy |
| `MEMDISK-BASE@` | `xhci.fth:168` (`28098 @`) | public diagnostic |

`install.fth:887` already carries the standing warning: if the bootloader
var moves, all copies must move together. **That is coupling #0** — four
independent literals of one address.

## Readers, by role, and what each does when the cell is 0

### A. Kernel block path (`src/kernel/forth.asm`) — RAM vs ATA

| site | reader | cell != 0 (memdisk) | cell == 0 (VBR/UEFI/installed) |
|---|---|---|---|
| :365 | `BLK_WRITE_VEC` choice at boot | `BLKWRITENONE` (loud refuse) | `BLKWRITEATA` |
| :374 | `BLK_READ_VEC` choice at boot | `BLKREADNONE` (loud refuse) | `BLKREADATA` |
| :2844 | `BLOCK` buffer loader | `ram_read_block` | ATA PIO (LBA = blk×2 + `BLOCKS_LBA_BASE`) |
| :3178 | `LOAD` | RAM path | ATA path |
| :3241 | `-->` (`CHAIN`) | RAM path | ATA path |
| :5422 | `ram_read_block` | source = cell + header + blk×1024 | (unused) |

**The core coupling.** With the cell 0, `BLOCK`/`LOAD`/`-->` read from
**ATA the internal disk**, not from the boot medium. A native-VBR stick
boots the *kernel* fine (its own bytes came in via the boot sector), but
the moment it needs a **block** (any `THRU`, any catalog load), it reads
the internal disk's block region, not the stick's. **A native stick has
no path to its own blocks today.** This is broader than N1 — N1 is the
installer; this is every block consumer.

### B. Paid AHCI override (`ahci.fth:535`) — RAM vs AHCI

`BLOCK` is redefined: `MEMDISK-VAR @` non-zero → kernel RAM block; else
if AHCI present → `AHCI-BLOCK` (the internal SATA disk); else kernel
block. Same shape as A: on a cell-0 boot, blocks come from the **AHCI
internal disk**, never the stick.

### C. Installer pristine source (`install.fth`) — **N1**

- `MEM-BASE` snapshots the cell at load (`:892`).
- `ABE-READY?` refuses unless `MEM-BASE @` is non-zero (`:905` region):
  the installer's pristine kernel/LBA-0 byte source **is** the memdisk
  RAM image. It reads sector 0 back through `SEC-READ-VEC` for the G1
  baseline (`LBA0-BASELINE`), all gated on `MEM-BASE != 0`.
- **So on a VBR or UEFI boot the installer cannot run:** cell 0 →
  `ABE-READY?` false → `LBA0-BASELINE`/`LBA0-SAME?` return 0, fail-closed.
  Its kernel-byte source is gone. **This is exactly N1, and it sits in
  front of the UEFI arc, not behind carrier removal.**

### D. Diagnostic / gate only (not a byte source)

- `xhci.fth:168` `MEMDISK-BASE@` — the xHCI desk cards STOP when it reads
  0 ("no memdisk = iron rule"). A reader, but read-only; nothing to
  re-source. It just needs its "0 is normal on a native/UEFI boot"
  meaning updated when that day comes.
- Tests that assert on the cell (informational, will need updating):
  `test_g6_chain.py:718,1227` (fatal if not non-zero on a memdisk boot),
  `test_install.py:1422` (notes it uses the snapshot, not the live cell),
  `test_xhci.py:1164,1232` (`MEMDISK-BASE@ = 0` gate).

## What CARRIER-0 concludes (for N1 and the stages)

1. **N1 is real and immediate.** The installer's only kernel-byte source
   is the memdisk RAM image. Any non-memdisk boot (native VBR *or* UEFI)
   already breaks it. A second source is required: read the bytes back
   through the same EDD/BIOS path the VBR used (BIOS side) or the UEFI
   loader's handoff (UEFI side) — or sequence so the installer and the
   native medium never coexist.
2. **The coupling is wider than the installer.** The block path (A) and
   the AHCI override (B) also branch on this cell to mean "RAM vs the
   internal disk." A native stick needs a *third* meaning — "blocks are
   on the boot medium" — or it cannot `THRU` its own catalog. This should
   be scoped into CARRIER-1/2, not discovered at CARRIER-3.
3. **The four-name duplication (#0)** should collapse to one owned
   definition before any of this moves, or the re-source work has four
   edit sites and a live drift risk.

**Nothing here is designed or changed — this is the audit. The resolution
(N1 and the block-source question) is the owner's call before CARRIER-1.**
