# FINDING — test-network runs again and fails 6/52: B reads the previous block's data (2026-10-05)

Recorded on branch fix-test-network (from master `416af55`), after the 4a
crash fix (`start_qemu_pair` returned an undefined `blocks_b`; it now
returns `combined_ide_b`, the name 22aefd9 gave that variable). Not fixed
here.

## Observed

Two full runs, `make test-network T_NETWORK=1800`, each 439.5s wall,
**identical check-by-check**: `Passed: 46/52`. This is the first time since
22aefd9 (2026-04-13) that the script has reached its NE2000 checks.

Everything up to and including the single-block transfer passes: both
instances boot, PCI-ENUM / NE2000 / NET-DICT load on both, NE2K-INIT finds
the NIC on both, MACs differ, and block 900 arrives with the right first
and middle byte. The six failures:

| Check | Expected | Got |
|---|---|---|
| B: block 902 byte | 170 | **66** (block 900's fill) |
| B: block 904 byte | 204 | **187** (block 903's fill) |
| B: PIT-CH0 = 40h | 40 | `PIT-CH0 ?` (word undefined) |
| B: PIT-CMD = 43h | 43 | `PIT-CMD ?` |
| B: PIT-FREQ = 1193182 | 1193182 | `PIT-FREQ ?` |
| B: PIT-READ works | a value | `PIT-READ ?` |

Block 903 arrives correct. Every `BLOCK-RECV` returned the right block
number (the frame header is right). Between the single-block test and the
consecutive test, B ran `SAVE-BUFFERS EMPTY-BUFFERS`, and B's disk never
held 66 at block 902. So `902 BLOCK` on B returned buffer memory that
still held block 900's data.

## Candidates (reasoned from source, not tested)

- **(a) Block-buffer slot mismatch, receive side.** `BLOCK-RECV`
  (forth/dict/net-dict.fth:151) does `RX-BLK @ BUFFER`, MOVEs the payload
  in, `UPDATE`. If `BUFFER` and a later `BLOCK` disagree about which buffer
  holds block N, `BLOCK` returns the other buffer's old contents. The
  alternation (902 wrong, 903 right, 904 wrong) fits a two-buffer cache.
  Same family as test-flush's 8/17 (bulk SAVE-BUFFERS, bug #21) and Bug #34.
  The PIT-TIMER failures would follow: wrong data flushed, THRU compiles
  garbage, no words defined.
- **(b) The same on the send side.** A writes each block with
  `BUFFER ... FILL ... UPDATE SAVE-BUFFERS`, then `BLOCK-SEND` reads it back
  with `BLOCK`. If A's `BLOCK N` returns a stale buffer, A *sends* the old
  data and B stores it faithfully.
- **(c) NE2K receive ring wrap.** `NE2K-RECV` (forth/dict/ne2000.fth:297)
  reads the payload in one remote-DMA read and does not wrap at `RX-STOP`.
  The ring is pages 0x46-0x80 (58 pages); a 1050-byte frame takes 5 pages,
  so no frame should wrap before about the 12th. Frames 2 and 4 failing does
  not fit; kept as a weak candidate.
- **(d) The test side: B's readback runs before the receive has finished
  writing the block.** The script reads `N BLOCK C@` on B as soon as
  `BLOCK-RECV` has printed the block number. **Unexamined:** not ruled in
  or out; only the probe below can.
- Ruled out by reading: truncation. `RX-FRM` and `TX-FRM` are
  `600 ALLOT` and receives use `600` as the limit, but BASE is HEX there
  (0x600 = 1536 bytes, frame 1046).

## Owned by NET-DATA

These six reds are their own task, **NET-DATA** (owner, 2026-10-05), queued
after the LOG-HARNESS validation pass and before Phase 3. 4a merged as
"crash fixed, 6/52 recorded"; the probe was deliberately not run in 4a.

## The discriminating probe (NET-DATA's first step, not run)

On B, right after `BLOCK-RECV` returns 902, read the payload in the frame
buffer itself: `RX-FRM FRM-HDR + C@ .` (with NET-DICT in the search order).

- 170 → the frame carried the right data; the fault is on B, (a) or (d).
- 66 → A sent stale data; the fault is on A, (b).

To separate (a) from (d), repeat B's readback after a delay and see whether
the value changes.

Then, on one instance with no network, `902 BUFFER DUP 1024 170 FILL DROP
UPDATE 902 BLOCK C@ .` separates the block cache from the NIC entirely.

## Teardown (4a gate)

No QEMU left after a normal exit (both runs), SIGINT (net-a and net-b,
`tools/sigint_sweep.py`, SigIgn clear, aimed at `poll`, 0s), or SIGTERM
(net-a and net-b, 0s). After a signal the script's `.b` image copies
(`build/combined*.img.b`) stay on disk; the next run's `cleanup()` removes
them first.

## Status in the gates

`tests/test_make_wiring.py` listed test-network as BROKEN ("cannot run at
all"), which is no longer true. It moves to GRANDFATHERED (outside `test:`,
failing known checks, like test-flush) until these six are fixed.
