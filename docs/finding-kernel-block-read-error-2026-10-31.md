# Finding: kernel BLOCK returns a buffer silently when the ATA read fails

Date: 2026-10-31. Status: recorded, not fixed. Queued by the owner after
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
