# TASK — HAL slice 2: BLK-READ and BLK-WRITE on the contract (2026-10-12)

Owner, 2026-10-12: BLK-READ and BLK-WRITE on the binding layer, over the
existing BLK_READ_VEC / BLK_WRITE_VEC. Gates: memdisk, module (UEFI) and
IDE block paths unchanged; MIRROR and LOAD-VOCAB pass; HAL-LIST shows both
vectors bound; RL-HAL covers them; pad cost reported. Commit, don't push.
Follows slice 1 (docs/TASK_HAL_DISPLAY.md).

## Design note

- **Over the cells, not beside them.** The kernel already binds a block
  writer and a persistent reader in two cells (0x2809C, 0x280A0): set at
  boot (ATA, or the fail-closed NONE words on memdisk/UEFI), rebound by
  AHCI-RW through BLK-WRITER! / BLK-READER!, and called by SAVE-BUFFERS
  (blk_flush_one) and PBLK-READ. A second pair of vectors would be the
  "parallel vectors" ADAPTIVE-HAL warns against. So a vector's body now
  starts with **the address of its binding cell**: an ordinary vector
  points at a cell of its own (slice 1's FB-BASE, FB-FLUSH: behaviour
  unchanged), and BLK-READ / BLK-WRITE point at the kernel's two cells.
  BIND, BLK-WRITER! and the kernel all write the same cell; HAL-GET and
  BLK-WRITER@ read the same value.
- **The runtime** (DOVEC) fetches the cell address, then the XT: two
  fetches and a jump instead of one fetch (the price of not duplicating
  the cells). Body: [cell address | header | next vector | own cell].
  `HAL-VECTOR-AT ( addr "name" -- )` lays down a vector over an existing
  cell; HAL-VECTOR is HAL-VECTOR-AT on its own fourth cell. HAL-SET and
  HAL-GET go through the cell address; nothing else changes for callers.
- **Stack effects:** the cells' contract, `( buf-addr blk# -- ior )` for
  both (ior 0 = success). ADAPTIVE-HAL's sketch shows `( lba addr count --
  ior )`; this slice keeps the effect the kernel and every caller already
  use. A sector-level contract is a later slice if a caller needs one.
- **Where:** the kernel exposes the two cell addresses as constants
  (BLK-WRITE-CELL, BLK-READ-CELL); hal.fth defines `BLK-WRITE-CELL
  HAL-VECTOR-AT BLK-WRITE` and the same for BLK-READ. Their binding at
  boot stays the kernel's (kernel_start), so the memdisk, module and IDE
  paths can't change.
- **RELOAD-VOCAB:** RL-HAL walks every vector, so it covers both; the two
  explicit BLK-WRITER@ / BLK-READER@ lines in RL-VECTORS go (they would
  check the same cells twice, under other names).

## Gates

test-hal (BIOS image, IDE blocks): HAL-LIST shows BLK-READ and BLK-WRITE
bound; each vector's HAL-GET equals BLK-READER@ / BLK-WRITER@ (the same
cell); a writer bound with BIND is the one SAVE-BUFFERS calls (a counting
writer sees the flush), and BLK-WRITER! is seen by HAL-GET; RELOAD-VOCAB
refuses to free code BLK-WRITE is bound to, naming it; slice 1's checks
unchanged. The block paths, through the existing suites: memdisk
(test-memdisk), module under UEFI (test-uefi-boot I1/U2), IDE and the
persistent reader (test-block-reload, test-blk-evict, test-carrier-write-
safe), MIRROR (test-mirror), LOAD-VOCAB (test-pad-move, test-vocabs). Pad
cost reported.

## Results

Evidence: ~/forthos-evidence/2026-10-12-hal-block/ (predictions written
before each run, logs).

**Red** (slice 1 tree, the extended test-hal): run 1 stopped at T_HAL in
K3's flush, my test's fault: a K2 line set the writer to DUP and restored
it on the same line, the line aborted at the undefined `' BLK-WRITE` after
the set, and SAVE-BUFFERS called DUP. Every writer change now has its own
restore line, and an unrestored writer before K3 is an INSTRUMENT FAIL.
Run 2, every result as predicted: K1-K3 FAIL (K3 showed the kernel's
fail-closed writer, `BLOCK WRITE FAIL 7`, count 0), slice 1's checks PASS,
K4 INSTRUMENT FAIL (the binding line answers `?`). Also found: K4 and Q6b
matched any text containing the name, and `BLK-WRITE` is inside the old
`BLK-WRITER@ vector`; both now require `refused, <name> points into it`.

**Green:** test-hal 14/14, three runs, 13.7 s each (T_HAL 20 -> 30):

| check | result |
|---|---|
| K1 HAL-LIST: `BLK-READ -> A86C`, `BLK-WRITE -> A80C` (the kernel's ATA reader and fail-closed writer on this BIOS IDE boot) | PASS |
| K2 HAL-GET = BLK-READER@ / BLK-WRITER@; a BLK-WRITER! is seen by HAL-GET | PASS |
| K3 `' XQ-COUNT BIND BLK-WRITE`, then UPDATE + SAVE-BUFFERS: the counting writer counts 1 flush | PASS |
| K4 `MIRROR: RELOAD-VOCAB refused, BLK-WRITE points into it` | PASS |
| slice 1 (D1, Q1-Q7) | PASS |

**The block paths, full make -k on this tree:** every target passed but
one: test-interp-abort's U8f, whose behaviour was right (the load aborts,
is kept, `IA-VEC partial`) and whose message now names the vector by its
contract name, `BLK-WRITE points into it`, where the check looked for
`BLK-WRITER` (the old explicit line's text). The check was updated to the
exact contract text; test-interp-abort 34/34 after. The same expectation
in tests/test_reload_vocab.py (not wired into make test) was updated and
run by hand: 13/13. Passing in that run: test-memdisk (memdisk), test-uefi-
boot (the module under UEFI: I1, U2, and the screens), test-block-reload,
test-blk-evict, test-carrier-write-safe (IDE and the persistent reader),
test-mirror, test-pad-move and test-vocabs (LOAD-VOCAB), test-hal.

**Pad cost:** 132 B (11,264 -> 11,132 B free): HAL-VECTOR-AT, the shared
layout code, the two cell constants, the second fetch, and the two vector
lines in hal.fth, less the two RL-VECTORS lines removed.
