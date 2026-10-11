# FINDING: the block cache always evicts slot 0, and a refused eviction flush loses the next block silently (2026-10-11)

Owner ruling 2026-10-11: write the MIRROR odd-blocks-twice trace up as a
finding; before fixing, find out whether the clobber also corrupts an
eviction whose flush succeeds, and if it does, say that every real writer
is affected. Task: docs/TASK_BLK_EVICT_FIX.md.

## Summary

- **K1:** `blk_find_buffer`'s LRU never works. When all four slots are
  valid, slot 0 is always the victim, including the block touched a
  moment before.
- **K2:** an eviction flush clobbers the victim's slot index. After a
  **refused** flush, the requested block is never written and nothing is
  printed. `BLK_BUF_CUR` becomes 0x720, the caller's 1 KB goes to
  0x1F0200, and `UPDATE` sets a bit at 0x2D5E4.
- **Success path: not corrupted today, but only by accident.** A
  successful flush leaves EAX = 0, which is the right index only because
  K1 always picks slot 0. Fixing K1 alone corrupts every successful
  eviction of slots 1-3 with any real writer. Observed with
  `(BLK-WRITE-ATA)`: block 2034's bytes were written to disk as block
  2030, and 2034 was never written. So K1 and K2 are fixed together.
- **Both defects were on record before, and neither had been fixed.** K1
  was held by ruling on 2026-09-05 (Bug #34). K2 was noted as latent on
  2026-07-04 (Bug #32, commit 2d2abb9). What is new is K2 observed at run
  time, and its cost.

## The code

`src/kernel/forth.asm`, Block Buffer Manager, `blk_find_buffer`, the path
taken when the block is not cached:

- The LRU scan starts with `mov edi, 0xFFFFFFFF` (lowest age so far) and
  keeps a slot only when `cmp ebx, edi / jge .not_older` falls through.
  Compared signed, 0xFFFFFFFF is -1, every age is >= -1, and the best
  index stays 0.
- When the victim is dirty, the path calls `blk_flush_one` (documented:
  clobbers EAX, ECX, EDX) and saves only EDX. It then uses EAX as the
  victim index for `BLK_BUF_CUR` and the data address. EBX, the victim's
  header, is preserved, so the header gets the new block number while
  the index and the data go wherever EAX points.

## The trace that found it (MIRROR, HP path, 2026-10-11)

This was an observation run with the prediction written first; nothing
was changed. Setup:

- HP-549 fixture, memdisk + combined.img `4cf66c6c…`, `AHCI-INIT AHCI-RW`.
- For b = 908-916: `b BUFFER DROP UPDATE SAVE-BUFFERS`.
- After each block, the four headers (block#, flags, age) and
  `BLK_BUF_CUR` were printed (hex).

```
after 911: 38C 1 1 | 38D 1 2 | 38E 1 3 | 38F 3 4 | cur 3    FAIL 911
after 912: 390 3 5 | 38D 1 2 | 38E 1 3 | 38F 3 4 | cur 0    FAIL 912, FAIL 911
after 913: 391 1 6 | ...                          | cur 720  FAIL 912, FAIL 911
after 914: 392 3 7 | ...                          | cur 0    FAIL 914, FAIL 911
after 915: 393 1 8 | ...                          | cur 720  FAIL 914, FAIL 911
```

- Slots 1-2 are never replaced; slot 0 takes 912 through 916 (K1).
- 913 and 915 end valid but clean and are never written (K2).
- This accounts for MIRROR's pattern on the HP: blocks 911 and up are
  refused by the partition-table ceiling (LBA 0x800). Each refused odd
  block is named twice, once by `SAVE-BUFFERS` and once when the next
  block evicts it. Each even block is lost with no message.
- **The guard messages name the right block.**

## Prior record

- **K1** is "Bug B" of Bug #34 (2026-09-05). The unsigned-compare fix was
  held by owner ruling so that the Bug #34 reproduction stayed
  deterministic. tests/test_block_reload.py still calls it "the (held)
  LRU fix", and its cases use only the free-slot order, so they don't
  depend on it.
- **K2** was noted in commit 2d2abb9 (2026-07-04, Bug #32) as a latent
  follow-up: statically confirmed, judged runtime-benign, with the stray
  read guessed at about 0xAB200. The 2026-10-11 trace is its first
  observation at run time; the stray value is 0x720 once the VGA screen
  has scrolled.

## The experiment: one test, three kernels

The test is tests/test_blk_evict.py: 17 checks in one boot, run on floppy
+ IDE scratch copies.
- A fixture writer records (blk#, first byte) for every call and refuses
  one chosen block.
- Every block is filled with its own byte, PAT(b) = 0x30 + (b - 2000).
  A slot or a write whose byte isn't its block's is data in the wrong
  place.
- Case A uses the real `(BLK-WRITE-ATA)`, and the host reads the IDE copy
  after the run.

Predictions were frozen before the first run. The test script is
`559dc84d…` for all three runs.

| kernel | image | result | predicted |
|---|---|---|---|
| TODAY (shipped, public 5f75b79) | `4cf66c6c…` | **12/17** | 12/17 |
| K1ONLY (`jge` -> `jae` only, one byte, built outside the tree) | `8b93fbf9…` | **10/17** | 10/17 |
| FIXED (both changes) | `fb505bf9…` | **17/17** | 17/17 |

Every check matched its prediction on all three kernels. The details that
discriminate:

- **L1, the LRU case** (2000-2003 cached, 2000/2001/2003 touched again,
  then 2004 requested):
  - TODAY: slots [2004, 2001, 2002, 2003], so slot 0 was evicted.
  - K1ONLY and FIXED: [2000, 2001, 2004, 2003].
- **Refusing writer** (2010-2025, each `BUFFER FILL UPDATE SAVE-BUFFERS`,
  the fixture refusing 2014):
  - TODAY: `BLK_BUF_CUR` = 0x720 after step 2015; the sentinel at
    0x1F0200 became 0x3F3F3F3F (2015's byte); block 2015 never reached
    the writer; 2014 was named twice.
  - K1ONLY: the same loss, three steps later, when 2018 evicts 2014.
    `BLK_BUF_CUR` = 0x720, sentinel 0x42424242, block 2018 never written.
    K2 does not depend on K1.
  - FIXED: `BLK_BUF_CUR` stays 0-3, the sentinel is unchanged, every
    other block is written once with its own bytes, and 2014 is refused
    and named exactly 5 times: four `SAVE-BUFFERS` while it is resident,
    plus its eviction.
- **Succeeding writer, fixture** (2005-2008 dirty, 2005 touched, 2009
  dirty):
  - TODAY: the eviction writes 2005, the block just touched (K1). The
    result is consistent: `BLK_BUF_CUR` 0, every slot holds its own
    bytes, all five blocks are written correctly.
  - K1ONLY: the eviction writes 2006 correctly, then `BLK_BUF_CUR` = 0.
    Slot 1's header says 2009 but holds 2006's bytes; slot 0's header
    says 2005 but holds 2009's bytes. `SAVE-BUFFERS` writes 2005 with
    2009's bytes, and 2009 is never written.
  - FIXED: `BLK_BUF_CUR` 1, all consistent.
- **Succeeding writer, `(BLK-WRITE-ATA)`** (the same sequence on
  2030-2034, then `SAVE-BUFFERS`; the host reads the disk):
  - TODAY and FIXED: blocks 2030-2034 each hold their own bytes, and
    nothing else on the copy changed.
  - K1ONLY: block 2030 on disk holds 0x52 (2034's bytes), and block 2034
    is still zero.

## Who is affected

- **K2 on a refused flush.** It needs a slot that is dirty and holds a
  block the writer refuses, which K1 then evicts.
  - Since CARRIER-0b, every boot's default writer refuses everything, so
    any `UPDATE` before a real writer is installed, followed by any load
    that brings in four more distinct blocks, takes this path.
  - With AHCI-RW, any block past the guard's ceiling takes it.
  - Each time, one requested block is lost silently, 1 KB lands at
    0x1F0200, and one bit is set at 0x2D5E4.
  - Before the screen has first scrolled, EAX would be 0x0A or 0x0D (the
    LF or CR just printed): the data would land at 0x2AA00 or 0x2B600 and
    the bit at 0x280DC or 0x28100. This is reasoned, not observed.
- **K2 on a successful flush:** harmless today, because K1 always picks
  slot 0.
- **K1 alone:** a poor cache (the most recently used block can be
  evicted), not data loss.

## The fix (as built)

- `jge` -> `jae` in the scan.
- `push eax` / `pop eax` around the eviction `blk_flush_one`.
- Kernel content goes from 111,810 to 111,814 B of `KERNEL_PADDED_SIZE`
  0x1C000 (114,688), so 2,874 B are left. Measured by assembling without
  the final pad line; the prefix is byte-identical to the built
  kernel.bin.
- The code grew 2 bytes. The other 2 are an `align 4` before
  `exec_xt_thread`: the code now ends at 0x3892, so two pad bytes follow
  (listing). The prediction was +2; it missed the alignment.

Gates and the full `make -k test` are in the task doc.
