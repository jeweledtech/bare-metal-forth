# TASK: MIRROR fix (reserved range, overlap refusal, honest result)

Status: PLAN, RULED (2026-10-11), no code changed. Owner ruling 2026-10-11:
MIRROR fix after the layout refactor (done: private 457c651, public
5f75b79), plan and red first, covering: a reserved MIRROR range in
write-catalog; MIRROR refuses a range overlapping the code store or a
partition, naming what it overlaps; no "saved" if any block write fails;
guard messages name the correct blocks, the odd-blocks-twice pattern
traced; the test on a scratch disk with a real writer, wired into
test-vocabs. Finding: docs/evidence/finding-test-mirror-stale-2026-10-10.md.
Rulings on §1 (2026-10-11): Q0 yes (kernel task first:
docs/TASK_BLK_EVICT_FIX.md); Q1 A; Q2 yes, and MIRROR discards any cached
buffer for blocks in its range; Q3 yes; Q4 yes, PG-WHICH looked up on
every call, never cached, and a missing PG-WHICH under AHCI's writer is a
refusal. Order: kernel fix, then this task; one HP stick rebuild covers
both.

## 0. The trace: odd blocks twice is a kernel buffer-manager defect

Observation run (2026-10-11, prediction written first; HP-549 fixture,
memdisk + combined.img `4cf66c6c…`, AHCI-INIT AHCI-RW; then for b =
908-916 `b BUFFER DROP UPDATE SAVE-BUFFERS`, printing the four buffer
headers at 0x28060 and `BLK_BUF_CUR` 0x28090 after each):

```
after 911: 38C 1 1 | 38D 1 2 | 38E 1 3 | 38F 3 4 | cur 3   FAIL 911
after 912: 390 3 5 | 38D 1 2 | 38E 1 3 | 38F 3 4 | cur 0   FAIL 912, FAIL 911
after 913: 391 1 6 | 38D 1 2 | 38E 1 3 | 38F 3 4 | cur 720 FAIL 912, FAIL 911
after 914: 392 3 7 | ...                          | cur 0   FAIL 914, FAIL 911
after 915: 393 1 8 | ...                          | cur 720 FAIL 914, FAIL 911
```

(header = block#, flags (1 valid, 2 dirty), age; 913 and 915 end valid
but clean and were never written.) Two defects in `blk_find_buffer`
(src/kernel/forth.asm, Block Buffer Manager):

- **K1, the LRU never runs: slot 0 is always the victim.** The scan
  starts from `mov edi, 0xFFFFFFFF` ("lowest age so far") and compares
  `cmp ebx, edi / jge .not_older`, a *signed* compare: every age is >=
  -1, so the index stays 0. Seen above: slots 1-2 (ages 2, 3) are never
  replaced; slot 0 takes 912, 913, 914, 915, 916.
- **K2, an eviction flush clobbers the victim index.** `blk_flush_one`
  is documented to clobber EAX, ECX, EDX; the eviction path saves only
  EDX, but EAX holds the victim index used afterwards for
  `BLK_BUF_CUR` and the data address. After a successful flush EAX = 0
  (the ior), which K1 makes accidentally right. After a refused flush
  EAX is what the failure message left: **0x720**, the VGA attribute
  word from `scroll_screen`, once the screen has scrolled. Then the
  header written is the victim's (block N+1, valid, clean), but
  `BLK_BUF_CUR` = 0x720, the caller's data goes to `0x28200 + 0x720 *
  1024 = 0x1F0200`, and `UPDATE` ORs the dirty bit into the dword at
  `0x28060 + 0x720 * 12 + 4 = 0x2D5E4`. **Block N+1 is lost with no
  message**; the kernel comment "the loss is now announced, never
  silent" is false on this path. Before the screen first scrolls, EAX
  would be 10 or 13 (the CR/LF just printed): the dirty bit would land
  at 0x280DC (system area) or 0x28100 (TIB) (reasoned, not observed).

Both defects were on record before this trace, and neither was fixed:
K1 as "Bug B" of Bug #34 (2026-09-05, memory note and
tests/test_block_reload.py docstring: the unsigned-compare fix HELD by
owner ruling so the Bug #34 reproduction stayed deterministic), K2 as a
"latent follow-up" of Bug #32 (2026-07-04, commit 2d2abb9 message:
statically confirmed, runtime-benign so far, the stray read guessed at
about 0xAB200). This trace is the first observation of K2 at run time and
of what it costs (a block lost, 1 KB written at 0x1F0200).

That is the MIRROR pattern exactly: with all four slots full, refused
block N lands in slot 0 and is named by `SAVE-BUFFERS`; N+1's `BUFFER`
evicts it, naming N again; N+1 is lost silently; N+2 lands in slot 0
clean. **The guard messages name the right block**; each refused block
is named twice and every second block never reaches the writer.

Who can hit it: any refused flush followed by an eviction of that slot.
Since CARRIER-0b every boot's default writer refuses everything, so any
`UPDATE SAVE-BUFFERS` before a real writer is installed, followed by
four more distinct blocks (a `LOAD-VOCAB` does that), takes this path
and writes 1 KB at 0x1F0200 (or near TIB before the first scroll).

## 1. Decisions for the owner

- **Q0 (ruled yes; plan docs/TASK_BLK_EVICT_FIX.md), priority: fix K1 + K2 first, as their own small kernel task?**
  Recommend yes, before MIRROR: it is substrate, it corrupts memory on a
  path every boot can reach, and MIRROR's red cases should not depend on
  it. Fix: save and restore EAX around the eviction `blk_flush_one`
  (or recompute the index from EBX); start the LRU scan from the first
  slot's age (or compare unsigned, `jae`). Red (QEMU, no disk needed):
  - R-K1: fill the four slots, touch three of them again, request a new
    block: the untouched slot is replaced. Today slot 0.
  - R-K2: install a fixture writer that refuses one block and records
    every other call in a Forth table; dirty the refused block, flush,
    then request four more blocks and dirty-and-flush each: every one
    of them reaches the writer once, `BLK_BUF_CUR` is always 0-3, and a
    sentinel at 0x1F0200 (and the dword at 0x2D5E4) is unchanged
    (monitor pmemsave). Today the block after the eviction never reaches
    the writer, `BLK_BUF_CUR` = 0x720, 0x1F0200 changes.
  - Gates: R-K1/R-K2, make -k test (only test-xhci red), test-meta.
- **Q1, MIRROR range size and place.** The dictionary runs from 0x30000
  to at most 0x7F800: 318 blocks + 1 header = 319. The range must lie at
  or below block 910 (the HP's writable gap, LBA < 2048) and outside
  the code store. Options:
  - A (recommended): **320 blocks at 216-535**, right after telemetry,
    so MIRROR never refuses for size. Cost: the code store moves up 320
    blocks (ends about 2,250), so `blocks.img` grows from 2,048 to
    2,560 blocks (combined.img +512 KB, 2.2 MB to 2.7 MB); every
    vocabulary's block numbers move (tests that hard-code a block range
    must be found and fixed; the catalog finds the rest); HP stick
    rebuilt once.
  - B: **192 blocks** (today's full dictionary is 187), MIRROR refuses a
    dictionary that does not fit, naming the size. Code store +192, still
    over 2,048: `blocks.img` grows anyway (to 2,304).
  Either way the reservation is checked by write-catalog like settings
  and telemetry: no vocabulary inside it, the range at or below 910.
  **Ruled A.** Pre-commit check done (2026-10-11, read-only): the
  10-08 HP boot-area copies (LBA 0-2047, before and after that run,
  both `17d5900a…`, checked against their SHA256SUMS) are all
  zero at LBA 657-1296 (blocks 216-535; block 535 ends at LBA 1296, one
  past the 657-1295 asked for, read too). Installer (install.fth): its
  only writes are SAFE-WRITE inside OWN-BASE/OWN-LEN, claimed by
  FREE-EXTENT from MIN-LBA 34 upward in the first all-zero gap, and
  GPT-WRITE at LBA 1, one entry sector in 2-33 and the backup header and
  its entry sector at the disk's end; FIRSTBOOT writes nothing. So the
  installer reaches LBA 657 only if the operator claims 624 sectors or
  more; the G6 card claims 225 (34-258), the HP's P6 is 34-582 (549,
  the 0x225 typo of 2026-08-21). Such a partition would make check 3
  below refuse MIRROR there, not overwrite it.
- **Q2 (ruled yes, plus: discard cached buffers in the range), how MIRROR learns a write failed.** `SAVE-BUFFERS` returns
  nothing; the kernel only prints. Recommend MIRROR **writes through the
  writer vector itself**, one call per block (`addr blk BLK-WRITER@
  EXECUTE` gives the ior): the header from its staging buffer, each
  dictionary block straight from dictionary memory. No block cache, so
  K1/K2 cannot touch it either way; it counts failures and prints
  `MIRROR FAILED: <n> of <m> blocks not written` instead of "saved".
  The alternative, a kernel failure counter that `SAVE-BUFFERS` sets, is
  a second kernel change for one caller.
- **Q3 (ruled yes), reading it back.** On memdisk (the HP), `BLOCK` reads the RAM
  image, so `MIRROR?`, `MIRROR-INFO` and `LOOKINGGLASS` can never see
  what MIRROR wrote (observed 2026-10-11: `900 MIRROR?` 0 after the
  write). Recommend they read through the persistent reader vector
  (`PBLK-READ`), as LOG-RESTORE does. Needed for the test to mean
  anything on the HP path.
- **Q4 (ruled yes: look up on every call, never cache; AHCI writer active and no PG-WHICH = refuse), the partition check.** Partition tables sit at LBA 0-33, below
  block 0 (LBA 225 + 2N), so MIRROR cannot read them through the block
  vectors; only AHCI's guard knows the extents (`PG-SCAN`, `PG-TBL`).
  mirror.fth is public and AHCI is paid, so MIRROR cannot `ALSO AHCI`.
  Recommend: AHCI gains `PG-WHICH ( lba -- first last true | false )`
  (both trees), and MIRROR looks it up by name at run time when the
  active writer is AHCI's, as RELOAD-VOCAB looks up its vectors. On the
  ATA path the block medium is the combined image, which has no
  partitions.

## 2. Design (as ruled)

- write-catalog.py: `MIRROR_RESERVED = range(216, 536)`, `MIRROR_BLK =
  216`; joins the reservation checks and the printed layout; mirror.fth
  gets `D8 CONSTANT MIRROR-BLK` (216, read by the test, like
  SET-BLK/LOG-BLK).
- `MIRROR ( block# -- )`, in order, refusing before any write:
  1. size: header + `DICT-BLKS` blocks;
  2. code store: walk the catalog; the first vocabulary whose blocks
     overlap prints `MIRROR REFUSED: blocks a-b overlap <NAME> (c-d)`;
  3. partition: if AHCI's writer is active (`BLK-WRITER@` equals the
     xt `AHCI-BLK-WRITE` resolves to, both looked up by name in this
     call), `PG-WHICH` is looked up by name in this call and never
     stored; not found prints `MIRROR REFUSED: AHCI writer active, no
     PG-WHICH` and writes nothing. Each block's two LBAs go through it;
     a hit prints `MIRROR REFUSED: blocks a-b overlap partition LBA
     c-d`;
  4. discard: every cached buffer whose block lies in the range is
     dropped, dirty or not, without a flush (a dirty one flushed later
     would overwrite the image; a clean one would be read instead of
     it). There is no kernel word for one slot today: the plan adds
     `DISCARD-BLOCK ( blk -- )` to the kernel next to EMPTY-BUFFERS
     (clears valid and dirty on the matching header; about 40 bytes of
     the 2,879 left, measured at build), rather than hard-coding the
     header address 0x28060 in a public vocabulary;
  5. writes through the vector, counting failures; prints `MIRROR saved
     to block N` only if the count is 0, else `MIRROR FAILED: n of m
     blocks not written`; every refusal and failure leaves DEPTH as it
     found it.
- Nothing in MIRROR touches the range through the cache after step 4.
  On memdisk `BLOCK` still reads the RAM image (stale by design there);
  every reader of the image uses `PBLK-READ` (Q3).
- Inside the reserved range, check 2 can never hit; it matters for an
  explicit block# outside it, which stays allowed (the owner's rule is
  overlap, not "reserved only").

## 3. Red (run on today's code before any change)

Scratch disks only; the shipped writers are installed on copies:
QEMU IDE path = copy of combined.img with `' (BLK-WRITE-ATA)
BLK-WRITER!`; HP path = HP-549 fixture + memdisk + AHCI-RW.

| # | case | today (predicted) | after |
|---|---|---|---|
| M1 | `900 MIRROR`, ATA writer (900 is inside NET-DICT 886-900) | writes over packed source, "saved" | `MIRROR REFUSED ... NET-DICT`, disk unchanged, DEPTH unchanged |
| M2 | HP path, a block# whose LBAs fall in P6 (e.g. 100) | AHCI refuses block by block, "saved" | `MIRROR REFUSED ... partition LBA 34-582`, disk unchanged |
| M3 | ATA scratch disk, a fixture writer that wraps `(BLK-WRITE-ATA)` and refuses one chosen block of the range | "saved" over the refusal (and, through the cache, the next block lost: K2) | `MIRROR FAILED: 1 of m blocks not written`, no "saved"; every other block on disk |
| M4 | `MIRROR-BLK MIRROR` then `MIRROR-BLK MIRROR?` and `MIRROR-INFO`, both paths | MIRROR-BLK undefined | written, true, HERE shown, read back through PBLK-READ |
| M5 | LOOKINGGLASS after a reboot (ATA scratch disk), a word defined before MIRROR runs again | not tested today | restored |
| M6 | write-catalog: no vocabulary in 216-535, range <= 910 | no reservation | checked, build fails if violated |
| M7 | stale cache: `MIRROR-BLK BLOCK` (cached, clean) and `MIRROR-BLK 1+ BUFFER ... UPDATE` (cached, dirty, writer refusing nothing), then `MIRROR-BLK MIRROR`, then `MIRROR-BLK BLOCK` on the ATA path and four more distinct blocks (forcing eviction) | MIRROR-BLK undefined (red by absence; today's MIRROR writes through the cache, so with an explicit block# it is coherent today and the case guards the direct-write design, not a present bug) | BLOCK returns the image (signature `TROF`); the image's second block on disk equals dictionary block 0 |
| M8 | HP path, AHCI-RW active, `PG-WHICH` hidden (fixture: AHCI loaded from a copy without it) | no partition check exists | `MIRROR REFUSED: AHCI writer active, no PG-WHICH`, disk unchanged |
| M9 | lookup not cached: `MIRROR` twice with the AHCI writer, `PG-WHICH` redefined between the calls (new definition refuses everything) | n/a | second call uses the new definition (refuses), proving a run-time lookup |

With Q0, K1/K2 are covered by R-K1/R-K2 in the kernel task; here the
"guard names the right block" check is: on the HP path, every refused
block is named exactly once (MIRROR no longer goes through the cache).

## 4. Gates and wiring

- tests/test_mirror.py rewritten on scratch copies (both paths), wired
  into test-vocabs as the owner ruled; M1-M6.
- make -k test: only test-xhci red; test-meta margins; the catalog's new
  layout; tests with hard-coded block ranges found by search and fixed in
  the same change; HP stick rebuilt (layout moved), image hash and dd
  line for the owner.
- Order (ruled): kernel task (TASK_BLK_EVICT_FIX.md) -> MIRROR red ->
  fix -> gates -> report; one HP stick rebuild after both.
