# TASK — NET-DATA: test-network's reds (2026-10-13)

Owner, 2026-10-13: next in the HAL order, the NET-SEND contract, then
NET-DATA. No-plan flow; commit without pushing. NET-DATA owns test-network's
reds (docs/evidence/finding-test-network-six-reds-after-crash-fix-2026-10-05.md:
46/52, "B reads the previous block's data", four PIT-TIMER words undefined
on B).

## Measured first

Evidence: ~/forthos-evidence/2026-10-13-net-data/ (predictions before each run).

- **Baseline today** (image ae05cb9a): 48/52, 439.6 s. The two data reds are
  gone: B's blocks 902 and 904 now arrive right. Since 10-05 the block
  cache's K1 (the LRU victim was always slot 0) and K2 (the eviction path
  saved EDX, not EAX, across blk_flush_one) were fixed (test-blk-evict);
  candidate (a) of the finding, a slot mismatch, is that family. The four
  PIT reds remain. I had predicted 52/52: the finding's reading that the PIT
  reds followed from the wrong data does not hold.
- **Probe 1** (one instance, no network): THRU of PIT-TIMER's blocks
  (1385-1389, the catalog's own range) defines it: PIT-CH0 40, PIT-FREQ
  1193182. The fault is on B after the transfer.
- **Probe 2** (one instance, no network), from reading: since CARRIER-0b
  (2026-09-29) every boot's default writer is the fail-closed
  (BLK-WRITE-NONE), and test-network never installs one or reads its
  SAVE-BUFFERS replies. All four predictions held: `BLK-WRITER@` is
  (BLK-WRITE-NONE); a flush prints `BLOCK WRITE FAIL 1385`; after
  EMPTY-BUFFERS the block reads the disk's old byte (92); with
  (BLK-WRITE-ATA) installed the same sequence writes and reads back 66.

**Mechanism:** every SAVE-BUFFERS in test-network is refused, silently to
the test. A's sends still work (its blocks stay dirty in the cache), but
B's `SAVE-BUFFERS EMPTY-BUFFERS` discards the received PIT-TIMER blocks and
THRU compiles B's zeroed blocks: no error, no words. Not the network, not
NET-DICT, not the NE2000 receive ring.

## Fix (test side)

- Every flush is checked: A's writes of 900 and 902-904, B's two
  `SAVE-BUFFERS EMPTY-BUFFERS`, `BLOCK WRITE FAIL` absent; B's THRU checked
  for undefined words.
- After the NICs are up, each instance arms (BLK-WRITE-ATA) on its own disk
  copy, checked (`BLK-WRITER@ ' (BLK-WRITE-ATA) = ` -1). A now boots its own
  copy (combined-ide.img.a, removed by cleanup) instead of writing the
  shared combined-ide.img.
- Wired into `make test`; its GRANDFATHERED entry in test_make_wiring goes
  (the gate: a repaired entry gets wired). T_NETWORK 900 stays (about 2x
  447.6 s).

## Results

- Red (checks added, no fix): 34/43. I had predicted 44/54: the
  consecutive loop stops at the first failed write, so 903/904 were never
  checked; I predicted without reading the loop. Refusals on both
  instances (A 900, 902; B 384, 56D, 56A, ...), the four PIT reds.
- Green: 56/56, two runs, 447.6 s each.
- No kernel or vocabulary change.

Not changed: NET-DICT sends through NE2K-SEND directly, not the HAL's
NET-SEND (its block sender, once also named NET-SEND, is NET-SEND-BLOCKS
since 2026-10-13). Moving it onto the
contract is not needed for these reds; left for a later ruling.
