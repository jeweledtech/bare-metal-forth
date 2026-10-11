# FINDING: tests/test_mirror.py fails today, and its target block is inside the code store (2026-10-10)

Owner ruling 2026-10-10: run tests/test_mirror.py once on the current image;
wire it if it passes, write it up if it fails. It fails. Not wired.

## Run

Image `build/combined.img` `c33f0d3a…` (public `f3f46d1` + private main),
copied to `build/mirror.d/` as floppy + IDE; test `d50fdc5d…`, mirror.fth
`079a5724…`. The test connects to a QEMU it does not start (launched by
hand like test-vocabs: floppy + IDE index 1, pidfile, killed by pidfile).

**6/8.** Predicted 7/8, written before the run.

| check | result |
|---|---|
| MIRROR loads from blocks (822-841 THRU) | PASS |
| USING MIRROR | PASS |
| `950 MIRROR?` on an empty block = 0 | PASS |
| `900 MIRROR` runs without crash | PASS |
| `900 MIRROR?` true after MIRROR | **FAIL**: `BLOCK WRITE FAIL 1086`, `0` |
| MIRROR-INFO runs | PASS |
| MIRROR-INFO shows HERE | **FAIL**: `No valid MIRROR image` |
| stack clean | PASS |

The second FAIL is the first one again (no image was written, so there is
none to describe); my prediction did not follow that through. The IDE
copy was byte-identical to the image afterwards: nothing was written.

## Why it fails

`MIRROR` writes the dictionary image with `UPDATE SAVE-BUFFERS`. Since
CARRIER-0b (2026-09-29) the kernel's default block writer on every boot is
the fail-closed `(BLK-WRITE-NONE)` (forth.asm 361-372): every flush prints
`BLOCK WRITE FAIL <n>` and writes nothing. MIRROR writes about 187 blocks
(900 to at least 1086, about the size of the dictionary above 0x30000)
through a 4-buffer cache, so by the time `MIRROR?` reads block 900 back,
the refused header has been evicted and the disk still holds the old
block. The test was written in March (last touched `61d54a9`), before the
writer default changed; no make target runs it, so nothing noticed.

## The larger problem: block 900 is now code

The test's comment says block 900 is "well within 1024-block disk". Today
the packed vocabulary store (write-catalog.py) runs to block **1928**, and
blocks 900-1086 hold thirteen vocabularies: NET-DICT 886-900,
NOTEPAD-FORM 901-907, NOTEPAD 908-920, NTFS 921-976, PCI-BAR 977-983,
PCI-ENUM 984-1011, PIT-TIMER 1012-1016, PORT-MAPPER 1017-1033,
PORT-MONITOR-FORM 1034-1035, PORT-MONITOR 1036-1056, PS2-KEYBOARD
1057-1070, PS2-MOUSE 1071-1077, RTL8139 1078-1096.

Where the disk being written is the medium the blocks are read from (an
ATA writer on a QEMU IDE boot; no shipped configuration installs one),
`900 MIRROR` would overwrite that packed source: the code-store /
data-store collision the two-store model (write-catalog.py, settings
192-207, telemetry 208-215) exists to prevent. MIRROR has no reserved
range of its own. Only the fail-closed default made this run harmless.

## The shipped real writer: AHCI-RW on the HP path (run 2026-10-11)

Correction (2026-10-11): the draft of this finding also put AHCI-RW in
the paragraph above. On the HP path that is wrong. The blocks are read
from the RAM image (memdisk), and the writer writes the internal SATA
disk, where those LBAs hold no packed source.

AHCI-RW is the one real writer anything shipped installs. Nothing runs it
on its own: the operator types it, as the HP cards and kits say. Its two
guards are the partition table and the `PART-LBA` ceiling (LBA < 0x800,
blocks 0-910). On the HP layout (P6 34-582, ESP from 2048), blocks
179-910 lie in the gap and are writable by design.

One run, prediction written before it: the HP-549 fixture
(tests/g6_fixture.py + P6 34-582, gap zero), memdisk + combined.img
`c33f0d3a…`, ahci.fth `e0b648c7…` (both trees), mirror.fth
`079a5724…`; `USING AHCI`, `AHCI-INIT`, `AHCI-RW`,
`S" MIRROR" LOAD-VOCAB`, `USING MIRROR`, `DECIMAL 900 MIRROR`.

- `AHCI-RW`: `part guard: 1 extent(s)`, writer and reader installed.
- **Blocks 900-910 written**: LBA 2025-2046 on the SATA disk, all eleven
  blocks (block 900 starts `TROF` (bytes 54 52 4F 46), MIRROR's
  signature). These are raw disk writes outside any partition and outside
  every reserved range.
- Blocks 911 and up refused: 176 `BLK LBA GUARD` + `BLOCK WRITE FAIL`
  pairs. They name only the odd blocks 911-1085, each twice; the even
  blocks print nothing. The cause is not traced.
- LBA 0-2024 and 2047-8191 (P6, the GPT, the head of the ESP) unchanged.
- **MIRROR then printed `MIRROR saved to block 900`.** It reports
  success over 176 refused writes.
- `900 MIRROR?` = 0 afterwards (BLOCK reads the RAM image under memdisk,
  so the image just written cannot be read back on this path); DEPTH 0.

What lies at LBA 2025-2046 on the real HP disk has not been read; on
the fixture it is zero. No HP card, kit or doc tells the operator to type
MIRROR (grep of both trees' docs, tools and dictionaries).

## Not done here (owner decision)

Wiring as-is would make make test either red forever (fail-closed
writer) or destructive (any real writer). Options:

- reserve a MIRROR range in write-catalog.py (like settings and
  telemetry; about 190 blocks today, growing with the dictionary), or
  aim MIRROR past the code store's end and check it against it;
- give the test its own writable scratch disk and an installed writer, so
  it exercises a real write without touching packed source;
- then wire it into test-vocabs.
