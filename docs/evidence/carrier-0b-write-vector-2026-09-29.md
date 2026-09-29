# CARRIER-0b — the write vector on a cell-0 boot (read-only, 2026-09-29)

Verifies F3's write-vector question from the code, not the summary. The
worry (owner): a block write from a `BLK_IMAGE_BASE == 0` boot (UEFI, or
a native VBR stick) could write to the **host's fixed disk** instead of
its own medium, ungated. Read-only; nothing changed.

## What the code does

**Vector choice at boot** (`forth.asm:364-367`): `BLK_WRITE_VEC` =
`(BLK-WRITE-ATA)` when the base cell is 0, `(BLK-WRITE-NONE)` (loud
refuse) when it is non-zero. So **every cell-0 boot — UEFI, native VBR,
or an installed disk — arms the ATA writer.**

**The ATA writer** (`(BLK-WRITE-ATA)`, `forth.asm:2969`): for block N it
writes to LBA `225 + 2N` (`BLOCKS_LBA_BASE=225`, LBA = blk×2 + base) via
`ata_write_sector`, which selects the **primary channel (0x1F0), drive 1
(IDE slave)** — `ATA_DRIVE=0x1F6`, `or al,0xF0` = LBA mode + slave.
**There is no partition or LBA guard.** It writes wherever `225+2N`
lands on whatever answers as IDE-slave.

**The guard that exists is elsewhere and does not help.** The
`PART-LBA` / LBA-2048 guard lives only in the paid `ahci.fth`
`AHCI-BLK-WRITE`, a *different* vector installed only when `AHCI-RW` runs.
It confines writes to blocks 0–910 (the pre-partition gap) — which is
still the **internal disk**, deliberately, for persistence. It does
nothing for a native stick and is absent from the default path.

## The answer, with the nuance the inference missed

The concern is **real but conditional**, and the precise shape matters:

1. **The default cell-0 writer targets a fixed disk, never the boot
   medium.** On a native stick or a UEFI boot, `SAVE-BUFFERS` of a dirty
   block goes to IDE-slave 0x1F0, not to the stick. So the stick can
   never receive its own block writes today — the F3 "third meaning"
   gap, confirmed on the write side.

2. **Whether it reaches the host's data depends on the machine:**
   - **Pure UEFI/AHCI or NVMe, no legacy IDE at 0x1F0:** `ata_write_sector`
     gets no device, times out, `CF` set → `ior=1`, loud fail. **Safe by
     accident** — the write fails rather than lands wrong.
   - **SATA in legacy/IDE-compat mode (some CSM setups) exposing an
     IDE-slave at 0x1F0:** the write **lands on that disk, ungated.**
     This is the dangerous case the owner named. It is silent w.r.t. the
     host (no gate), and loud only in the sense that ForthOS reports
     `ior=0` success — success at writing to the wrong disk.

3. **LBA 0 specifically is not in range.** Block writes start at LBA 225
   (`225 + 2N`), so a fixed disk's MBR/GPT primary header at LBA 0 is not
   touched by the block writer. **Gate C5's "LBA 0 byte-identical" would
   pass while the host's data region above LBA 225 is still at risk** —
   so C5 should check a written span, not only LBA 0.

## Conclusion for the arc

- **F3's write-side concern is validated.** There is no gate binding a
  block write to the boot medium; the default path writes to IDE-slave
  0x1F0 unconditionally, and the only reason it is not routinely
  destructive is that modern UEFI/AHCI/NVMe machines usually have nothing
  at 0x1F0 (loud-fail), not any deliberate guard.
- **This is a host-safety property on the UEFI path**, present today,
  independent of carrier removal. When UEFI-5 brings the kernel up
  cell-0 on a CSM machine with SATA in IDE-compat mode, a `SAVE-BUFFERS`
  writes to the host disk and reports success.
- **Recommended gate, before UEFI-5 closes** (design, not done here): the
  block writer must refuse unless its target is the boot medium — i.e.
  the F3 "third meaning" is a *safety* requirement, not only a
  functionality one. Until it exists, a cell-0 boot should arm
  `(BLK-WRITE-NONE)`, not `(BLK-WRITE-ATA)`, so a write loud-fails
  everywhere instead of landing on a fixed disk where one happens to sit
  at 0x1F0.
- **C5 amendment:** compare a written LBA span on every fixed disk, not
  LBA 0 alone (block writes never touch LBA 0; they start at LBA 225).

The resolution is N1's three-state design plus this fail-closed default;
both are the owner's call before CARRIER-1.

## Follow-up (owner question, 2026-09-29): does a stock installed instance write blocks today?

- **Installer: no block writes.** `ADD-BOOT-ENTRY`/`ADD-PARTITION` write the
  VBR, 224 kernel sectors and partition metadata via `SAFE-WRITE` /
  `SEC-WRITE-VEC` (raw sector writes), never the block layer. Install is
  unaffected by the block write vector.
- **Block writes exist and are used** by `editor.fth`, `mirror.fth`,
  `net-dict.fth`, `video.fth` (`UPDATE SAVE-BUFFERS`). On real AHCI/NVMe
  hardware the default `(BLK-WRITE-ATA)` (IDE 0x1F0) has no device, so working
  persistence needs the paid `AHCI-RW`, which overrides the vector at runtime.
- **Nothing wired / on real HW / in G6 relies on the default ATA block
  writer** (G6's "persist" is the monitor channel; `test_persist_quick` is
  unwired). Only QEMU-with-IDE does.

**So blanket `(BLK-WRITE-NONE)` is nearly free but not entirely** — an installed
instance is also cell-0 and legitimately wants ATA writes on the QEMU-IDE /
legacy-IDE path. **The fail-closed default is thus N1's first half, not a
separate decision:** the legitimate case needs a positive "this is my medium"
signal first. UEFI-5 can close its own path early by setting the cell to a
not-internal-disk value (see the carrier task doc §3a.1).
