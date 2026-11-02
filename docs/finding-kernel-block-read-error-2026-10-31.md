# Finding: kernel BLOCK returns a buffer silently when the ATA read fails

Date: 2026-10-31. Status: ~~recorded, not fixed~~ Resolved 2026-11-02
(see the end: the failed read; the RAM path's bound is still open). Queued by the owner after
this session's stop line (pxe-push labelling), not this session.

## What the source says (src/kernel/forth.asm, BLOCK, read)

BLOCK's ATA PIO path reads two sectors with `ata_read_sector`; on a
carry (timeout or error) it jumps to `.read_error`, which restores the
buffer and header addresses and pushes the buffer address, commented
"Return buffer addr anyway (may contain garbage)". No message, no abort.
The buffer is not marked valid (that `or` is on the success path only),
so the next BLOCK of the same number reads again; but the caller of
this one gets the buffer's old contents as if they were the block.

Reasoned, not observed: a LOAD or LIST of an unreadable block interprets
or shows whatever the buffer held before. Not yet driven in QEMU.

## Related

- The kernel's persistent-read path already reports its failure:
  `(BLK-READ-NONE)` prints `BLOCK READ FAIL <n>` and returns ior 1, and
  the ATA PBLK-READ backend returns ior 1.
- The same defect in AHCI's BLOCK (AHCI-BLOCK, ahci.fth) is item 2 of the
  current queue (private TASK_READ_FLAGS): there the owner's design is an
  ABORT" on the failed read, the buffer not kept as valid.

## When it is taken up

A pre-registered red that drives a real failed ATA read in QEMU and shows
the old buffer returned, before any change to forth.asm.

## Boot paths and the end-of-image bound (2026-11-02; for the ESP32 work)

Observed in QEMU (2026-11-02): a BLOCK past the end of the IDE disk returns
an address with no message, and a second BLOCK of it returns whatever the
buffer was refilled with. LOAD interprets it.

BLOCK reads its medium two ways, and only the drive bounds either:
- **The RAM path** (BLK_IMAGE_BASE set): PXE and the USB stick (BIOS, both
  through memdisk; boot.asm reads memdisk's mBFT `diskbuf`), and UEFI (the
  multiboot2 module). `ram_read_block` copies from the base plus the
  offset with no bound, so a block past the image is whatever RAM follows
  it. This is the path the HP uses.
- **The ATA path** (BLK_IMAGE_BASE 0): an installed VBR boot and QEMU's
  IDE disk. The drive refuses a read past its end; the kernel ignored the
  refusal (this finding).

A bound whose size travels with the image, a count written by the build
into block 0 (reserved "for boot info"), gives every path the same check.
A size from the boot handoff (memdisk's mBFT disksize, the UEFI module's
size) covers only the boot paths that have one.

**For an ESP32 port** (or any edge device with no BIOS, GRUB or ATA): the
block image sits in flash or RAM behind a pointer, which is the RAM path's
shape. It needs a read path that copies from a base pointer, as
`ram_read_block` does, and the image as built, block 0 included. With the
bound taken from block 0, no handoff code is needed for that device. With
a handoff-based bound it would need a third source of the size.

Tracked privately: TASK_KERNEL_BLOCK_READ_ERROR (D2, pad measured per
option).

## Resolved 2026-11-02 (the failed read)

BLOCK, LOAD, `-->` and LIST each had their own copy of the read. BLOCK
returned the old buffer silently. LOAD, `-->` and LIST never tested the
error and marked the buffer valid anyway, so a failed read was cached as
a good block. LIST read over ATA only, with no memdisk branch. All four
now go through one routine, `blk_read`. It reads from the memdisk image
or over ATA, sets the buffer valid only after a good read, and on a
failure prints `BLOCK READ FAIL <n>` and takes ABORT's route.

- 7564304: the red, test-block-read-error (2/7 on the old kernel).
- 605d754: the red re-run with E7 (a `-->` chain past the end) and E8
  (LIST), 9 checks (2/9 on the old kernel).
- 1ba9d37: the fix, 9/9; kernel pad 5555 to 5627.
- 8be6e5f: the port inventory after the suite.

The full private suite and a fresh public clone (73 targets, none absent)
both pass on these commits.

**Still open:** the RAM path (PXE, the USB stick, UEFI) has no
end-of-image bound, so a block past the image still reads whatever RAM
follows it (Boot paths, above). The block-0 count is its own item, not
yet taken up. Tracked privately: TASK_KERNEL_BLOCK_READ_ERROR.
