# TASK: block-cache eviction fix (LRU victim, victim index kept across the flush)

Status: PLAN + RED (2026-10-11). Owner ruling 2026-10-11 (Q0 of
docs/TASK_MIRROR_FIX.md): fix the kernel first, as its own task, plan and
red test first. The fix: keep the victim slot index across the eviction
flush, and make the age comparison unsigned. Red tests: LRU (re-touch
three of four slots, the fourth is evicted); refusing writer (every later
block reaches the writer, BLK_BUF_CUR stays 0-3, a sentinel at 0x1F0200
unchanged); succeeding writer (an eviction whose flush succeeds; before
fixing, find out whether the clobber also corrupts that path, and if it
does, every real writer is affected and the finding says so). Report the
kernel size against KERNEL_PADDED_SIZE. Run the full make -k, since
eviction order changes. Write the trace up as a finding. Then the MIRROR
fix; one HP stick rebuild covers both.

## 0. The defects, and that they were already on record

`blk_find_buffer` (src/kernel/forth.asm, Block Buffer Manager), the
not-cached path:

- **K1.** The LRU scan starts at `mov edi, 0xFFFFFFFF` ("lowest age so
  far") and keeps a slot only if `cmp ebx, edi / jge .not_older` falls
  through. Signed, 0xFFFFFFFF is -1, every age is >= -1, so the best index
  stays 0: when all four slots are valid, the victim is always slot 0.
- **K2.** If the victim is dirty, the path calls `blk_flush_one`
  (documented: clobbers EAX, ECX, EDX) saving only EDX, then uses EAX as
  the victim index for `BLK_BUF_CUR` and the data address. EBX (the
  victim's header) is preserved, so the header written is the victim's;
  the index and the data address come from whatever EAX holds.

Both were known and left unfixed:

- K1 is "Bug B" of Bug #34 (2026-09-05): the unsigned-compare fix was HELD
  by owner ruling so the Bug #34 reproduction stayed deterministic
  (tests/test_block_reload.py docstring: "the (held) LRU fix"). Bug #34 is
  fixed (6c1a6d7) and its gate uses only the free-slot order, so the reason
  for the hold no longer applies; the 2026-10-11 ruling lifts it.
- K2 was noted as a "latent follow-up" of Bug #32 (2026-07-04, commit
  2d2abb9): statically confirmed, judged runtime-benign, the stray read
  guessed at about 0xAB200.

New on 2026-10-11 (observed, MIRROR trace; TASK_MIRROR_FIX.md §0): K2 at
run time on a refused flush, EAX = 0x720 (the blank-cell word
`scroll_screen` leaves in AX), BLK_BUF_CUR = 0x720, the caller's 1 KB at
0x1F0200, UPDATE's dirty bit at 0x2D5E4, and the requested block lost
with no message. That is MIRROR's odd-blocks-twice pattern.

## 1. The success-path question (owner: find out before fixing)

Reasoned from the code: after a successful flush EAX is the ior, 0. With
K1 the victim is always slot 0, so the clobbered EAX equals the victim
index and the path is consistent by accident. Fixing K1 alone would
expose it: a successful flush of slot 1-3 would set the victim's header to
the new block but put the new block's data, and BLK_BUF_CUR, in slot 0,
whose header still names its own block. With any real writer that is
silent corruption: slot 0's block is later flushed with the new block's
bytes.

Discriminating experiment (prediction frozen before the run): the same
test on three kernels. TODAY (shipped), K1ONLY (an experiment image built
from a copy of forth.asm with only `jge` -> `jae`, one byte different,
outside the tree), FIXED. Success-path checks S2/S4 (fixture writer) and
A2/A3 (the real `(BLK-WRITE-ATA)`, disk read by the host afterwards) are
predicted PASS on TODAY, FAIL on K1ONLY, PASS on FIXED.

## 2. The fix

```
.find_free:   ...
    cmp ebx, edi
-   jge .not_older
+   jae .not_older             ; unsigned: 0xFFFFFFFF is the largest age
...
.find_lru:    ...
    pop esi
    push edx                   ; Save requested block#
+   push eax                   ; Save victim index (blk_flush_one clobbers EAX)
    call blk_flush_one
+   pop eax
    pop edx
```

Two bytes of code. The age counter `BLK_BUF_CLOCK` wraps after 2^32
touches; at the wrap one LRU choice is wrong once (a correctness-neutral
eviction order glitch, not data loss). Not addressed.

The kernel comment on `blk_flush_one` ("the loss is now announced, never
silent") becomes true again with K2 fixed: a refused eviction flush is
named once and the requested block gets its slot.

## 3. Red: tests/test_blk_evict.py (17 checks, one boot)

Floppy + IDE scratch copies of the combined image under
build/test-blk-evict.d/. A fixture writer (colon definition via
BLK-WRITER!) records (blk#, first byte) for every call and refuses one
chosen block; every block is filled with its own byte PAT(b) = 0x30 +
(b - 2000), so a slot or a write whose byte is not its block's is data in
the wrong place. Addresses derive from forth.asm equates.

| # | case | asserts |
|---|---|---|
| C1, C2 | controls (fatal) | fixture defined, DEPTH 0; fixture returns ior 0, and 1 for the refused block |
| L1 | 2000-2003 BLOCK, touch 2000 2001 2003, 2004 BLOCK | 2004 replaces 2002 (slot 2) |
| S1-S4 | fixture writer succeeding: 2005-2008 dirty, touch 2005, 2009 dirty | CUR 0-3; every valid slot holds its block's bytes; the eviction wrote one block with its own bytes; after SAVE-BUFFERS 2005-2009 each written once, own bytes |
| R1-R5 | fixture refusing 2014: 2010-2025 each BUFFER FILL UPDATE SAVE-BUFFERS | CUR 0-3 after every step; sentinel 0x5AA5C33C at 0x1F0200 unchanged; every block but 2014 reaches the writer once with its own bytes; 2014 refused and named exactly 5 times (4 SAVE-BUFFERS while resident + the eviction), nothing else named; DEPTH 0 |
| A1, A2, A3, A4, E1 | `(BLK-WRITE-ATA)` on the IDE copy, the S sequence on 2030-2034, SAVE-BUFFERS | CUR 0-3; slots hold their own bytes; on disk 2030-2034 each hold their own bytes; the rest of the IDE copy unchanged; DEPTH 0 |

Predictions (frozen in the evidence directory before the run): TODAY
12/17 (L1, R1-R4 red), K1ONLY 10/17 (S2, S4, A2, A3, R1-R3 red), FIXED
17/17. Named alternative: if the screen has not scrolled at the refused
eviction, EAX is 0x0A or 0x0D: R1 still red, R2 green, the 1 KB lands at
0x2AA00 or 0x2B600.

Blocks 2000-2034 lie past the code store's end (1930) and inside
blocks.img (2,048 blocks); only the IDE scratch copy is written.

## 4. Gates

- tests/test_blk_evict.py 17/17 on FIXED, wired as `make test-blk-evict`
  (pidfile kill, PIPE in its trap, port offset from the inventory) into
  `make test`; tools/qemu_ports.json regenerated; test-kill-traps count
  +1.
- Full `make -k test`: only test-xhci red (known). Eviction order changes
  for every multi-block load; predicted: no target changes result.
  Before-reading: the layout-refactor run on the same kernel (make -k
  green except test-xhci, 2026-10-11).
- test-block-reload and test-flush-stress named: both use EMPTY-BUFFERS
  and the free-slot order, predicted unchanged.
- test-meta margins unchanged (no dictionary change).
- Kernel size: content before 111,810 B of KERNEL_PADDED_SIZE 0x1C000
  (114,688), 2,878 B left (measured by assembling without the final pad
  line, prefix byte-identical to build/kernel.bin); after predicted
  111,812 B, 2,876 left.
- Finding: docs/evidence/finding-blk-evict-2026-10-11.md (the trace, the
  prior record, the success-path answer).
- No HP run; the stick is rebuilt once after the MIRROR fix.

## 5. Results (2026-10-11)

- Red as predicted, all three kernels, every check: TODAY 12/17
  (`4cf66c6c…`), K1ONLY 10/17 (`8b93fbf9…`, one byte), FIXED 17/17
  (`fb505bf9…`); test script `559dc84d…`. One earlier run was VOID: a
  `( )` comment typed over serial wedged the interpreter, caught by the
  fatal control C1; the typed definitions carry no comments now.
- Success path answered: not corrupted today (K1 keeps it right by
  accident); K1 alone corrupts every real writer (K1ONLY, ATA: block
  2030 on disk holds 2034's bytes, 2034 never written). Finding:
  docs/evidence/finding-blk-evict-2026-10-11.md.
- Kernel content 111,810 -> 111,814 B, 2,874 B left of 0x1C000.
  Predicted 111,812: missed the `align 4` before `exec_xt_thread` (two
  pad bytes, listing at 0x3892).
- `make -k test` on the fix: only test-xhci red (Error 124, known); 38
  `Passed:` lines all full; test-blk-evict 17/17 inside it; port
  inventory 0 problems; kill traps 34/34; make-wiring 52/52; check-sync
  OK. The corpus-absent gate's three refusals are its expected output
  (same three in the layout-refactor baseline).
