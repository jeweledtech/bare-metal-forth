# TASK: VIDEO Vocabulary — TAQOZ BMV360.TASK Port for ForthOS
# Phase A/V Phase 3 of 4: Block-Based Video Playback

## Context

GRAPHICS (Phase 1) gave us BLIT-ROW, VIEW-SECTOR, VSYNC-WAIT, !POST, !TVOFF.
AUDIO (Phase 2) gave us BEEP, TONE, AC97 DMA, AUDIO-MODE.
VIDEO (Phase 3) wires them together into a TAQOZ-compatible video player.

The original TAQOZ BMV360.TASK on Parallax P2:

```
pub BMV360.TASK
  !POST
  64 SDADR fname 32 CMOVE
  OPENDIR @FILE
  BEGIN
    ?DUP
  WHILE
    VSYNC ( 16.64ms ) DUP VIEW-SECTOR ( 33ms ) POST 512 + 5 ms
    PAL 54 - W@ $4D42 <> IF DROP OPEN.BMP THEN
  REPEAT
  !TVOFF
  ;
```

The ForthOS port has a different storage layer (block system over AHCI/ATA
instead of FAT32 SD card SPI) but the same structure:
- Frames stored as raw pixel data in consecutive Forth blocks
- Each frame read from disk, blitted to VGA framebuffer
- VSYNC-WAIT gates the frame rate
- BMP header detection for format validation

The TAQOZ system pushed ~33ms/sector at 320MHz on P2 silicon.
ForthOS on x86 with AHCI reads a 1KB block in <<1ms at 1000Mbps —
the disk is not the bottleneck. The frame budget is VSYNC-gated at 16.6ms
(60Hz) or 33.3ms (30Hz). Full 320×200 frame = 63 blocks.

## What VIDEO Does vs What GRAPHICS Does

GRAPHICS: primitive pixel operations, framebuffer write, palette, VSYNC word
VIDEO: frame-level operations — read a frame from blocks, blit, loop, sync

VIDEO REQUIRES: GRAPHICS (for BLIT-ROW, VSYNC-WAIT, !POST, !TVOFF, GFX-FB)
VIDEO REQUIRES: AUDIO (for BEEP, TONE — optional soundtrack sync)

The VIDEO vocab does NOT duplicate anything from GRAPHICS. It calls the
GRAPHICS words as its primitive layer.

## Frame Storage Format

A video stored in ForthOS blocks uses this layout:

```
Block N+0   : Frame header (optional — 16 bytes)
              Bytes 0-1 : magic 'BM' (0x42 0x4D) — BMP-compatible
              Bytes 2-3 : frame number (0-based)
              Bytes 4-5 : width in pixels (320 = 0x0140)
              Bytes 6-7 : height in pixels (200 = 0x00C8)
              Bytes 8-15: reserved
              Bytes 16-1023: first 1008 pixels of row 0
Block N+1   : next 1024 pixels (rows 0-3 continued)
...
Block N+62  : final pixels of frame (rows 196-199, last 64 bytes)
              Total: 63 blocks × 1024 bytes = 64,512 bytes > 64,000 (ok)
```

For simplicity in Phase 3, frames are stored WITHOUT headers — raw 8bpp
pixel data, row-major order, 320 pixels/row, 200 rows = 64,000 bytes.
Blocks N through N+62 hold one frame. The video player reads blocks
sequentially and blits them to the framebuffer.

The BMP header check in TAQOZ (`W@ $4D42 <>`) can be implemented as an
optional sanity check on block 0 of the video — if the first two bytes
are not 'BM', abort playback. This prevents playing garbage data.

## Tools: create-video.py

A host-side Python script converts a sequence of BMP files into a
ForthOS block image suitable for writing to the blocks disk.

```python
# tools/create-video.py
# Usage: python3 tools/create-video.py <dir-of-BMPs> <blocks.img> <start-block>
# Writes each BMP's pixel data (stripped of header) as consecutive blocks
# Each frame occupies exactly 63 blocks (64,512 bytes, 512 padding at end)
```

The script strips the 54-byte BMP header (standard uncompressed BMP),
takes the 64,000-byte pixel array, and packs it into 63 Forth blocks.
A 10-second video at 30fps = 300 frames × 63 blocks = 18,900 blocks =
~18.4MB. This fits comfortably in the 1MB blocks.img for short clips,
or requires a larger blocks.img for longer content.

For the demo video: a 3-second clip at 15fps = 45 frames × 63 blocks =
2,835 blocks = 2.77MB. Well within a 4MB blocks.img.

## Block Assignment

Blocks 320–369 — VIDEO vocabulary
  320     : Catalog header + frame geometry constants
  321     : FRAME-ADDR ( frame# -- blk# ) frame-to-block mapping
  322     : BLIT-FRAME-RAW ( blk# -- ) read+blit one full frame (63 blocks)
  323     : BMV-CHECK ( blk# -- ok? ) optional BMP magic check on block
  324     : FRAME-LOOP ( start-blk# nframes fps -- ) main playback loop
  325     : VIDEO-PLAY ( start-blk# nframes -- ) play at 30fps
  326     : VIDEO-PLAY-15 ( start-blk# nframes -- ) play at 15fps (demo)
  327     : SLIDESHOW ( start-blk# nframes delay-ms -- ) still-frame mode
  328     : BMV360.TASK ( start-blk# nframes -- ) TAQOZ-compatible word
  329     : TV ( -- ) top-level demo word: plays from a default block#
  330     : VIDEO-INFO ( start-blk# -- ) print frame info + timing
  331     : VIDEO-TEST-FRAME ( -- ) generate a test frame in blocks
  332–369 : Reserved (sprite overlay, subtitle blitter, etc.)

## Critical Constraints (same as all vocabs)

1. 64-character line limit — hard limit from Forth block format
2. No 2* — use DUP + instead
3. No " in Forth-83 — QC EMIT pattern
4. Strings under 6 chars in ." corrupt state — pad to 6+
5. Every vocab: ONLY FORTH DEFINITIONS at end
6. ALSO/PREVIOUS matched
7. HEX/DECIMAL explicit — document every switch
8. Verify every word against forth.asm before using
9. No 2>R/2R@ in kernel — use VARIABLE for multi-value saves
10. BLOCK ( n -- addr ) reads 1KB from disk — this IS the I/O primitive

## Kernel Words Available

All GRAPHICS words via REQUIRES: GRAPHICS
All AUDIO words via REQUIRES: AUDIO (optional, for BEEP sync)
BLOCK ( n -- addr ) — the core I/O word for frame reading
MOVE ( src dst count -- ) — for framebuffer blit
FILL ( addr count byte -- ) — for clear
DO/LOOP/LEAVE/UNLOOP — for frame loops
US-DELAY ( us -- ) — for timing (from HARDWARE via GRAPHICS→HARDWARE chain)

## Part 1: forth/dict/video.fth

### Block 320 — Catalog header + frame constants

```forth
\ CATALOG: VIDEO
\ CATEGORY: video
\ PLATFORM: x86
\ SOURCE: hand-written
\ PORTS: none (uses GRAPHICS/AUDIO ports)
\ MMIO: GFX-FB (via GRAPHICS)
\ CONFIDENCE: high
\ REQUIRES: GRAPHICS ( BLIT-ROW VSYNC-WAIT !POST !TVOFF GFX-FB )
\ REQUIRES: AUDIO ( BEEP ) \ optional
VOCABULARY VIDEO
VIDEO DEFINITIONS
ALSO GRAPHICS
ALSO AUDIO
HEX
\ Frame geometry
0140 CONSTANT VID-WIDTH      \ 320 pixels per row
00C8 CONSTANT VID-HEIGHT     \ 200 rows per frame
\ Bytes per frame: 320*200 = 64000 = FA00 hex
FA00 CONSTANT VID-FRAME-BYTES
\ Blocks per frame: CEIL(64000/1024) = 63 = 3F hex
3F   CONSTANT VID-FRAME-BLKS
\ BMP magic word (little-endian: 'B'=42, 'M'=4D → word 4D42)
4D42 CONSTANT BMP-MAGIC
\ Video playback state
VARIABLE VID-FRAME     0 VID-FRAME !   \ current frame #
VARIABLE VID-PLAYING   0 VID-PLAYING ! \ 1 = playing
```

### Block 321 — FRAME-ADDR

```forth
\ FRAME-ADDR ( frame# -- blk# )
\ Convert frame number to starting block number.
\ Frames stored consecutively starting at VID-START.
\ VID-START must be set before playback.
VARIABLE VID-START  0 VID-START !

: FRAME-ADDR ( frame# -- blk# )
  VID-FRAME-BLKS *         \ frame# * 63 blocks/frame
  VID-START @ +             \ + base block
;

\ FRAME-ROWS ( frame-blk# -- ) Blit all rows from frame blocks
\ Reads VID-FRAME-BLKS blocks and blits rows to GFX-FB.
\ One block = 1024 bytes. One row = 320 bytes.
\ 3.2 rows per block — not aligned, so we track byte position.
VARIABLE VB-PTR   \ current byte position within frame
VARIABLE VB-BLK   \ current block number being read
VARIABLE VB-OFF   \ byte offset within current block

: VB-INIT ( blk# -- )
  VB-BLK ! 0 VB-OFF !
;

\ VB-NEXT-ROW ( dst -- ) Copy one 320-byte row to dst
\ Handles block boundaries: row may span two blocks
: VB-NEXT-ROW ( dst -- )
  DECIMAL 320 HEX           \ bytes to copy
  >R                        \ save dst
  BEGIN R@ 0> WHILE         \ while bytes remain
    VB-BLK @ BLOCK          \ load current block
    VB-OFF @ +              \ + offset into block
    \ bytes available in this block:
    400 VB-OFF @ -          \ 1024 - offset
    R@ MIN                  \ min(available, needed)
    DUP >R                  \ save count
    R> R> SWAP              \ dst src count
    OVER + >R               \ advance dst
    MOVE
    VB-OFF @ + DUP          \ advance offset
    400 >= IF               \ block boundary crossed?
      DROP 0 VB-OFF !
      VB-BLK @ 1 + VB-BLK !
    ELSE
      VB-OFF !
    THEN
    R> R> SWAP >R           \ update remaining count
  REPEAT
  R> 2DROP
;
```

NOTE: VB-NEXT-ROW above uses a complex >R/R> pattern. Since the kernel
has >R/R@ but not 2>R, use VARIABLE for multi-value state. The VB-PTR,
VB-BLK, VB-OFF variables make this explicit and debuggable.

SIMPLER ALTERNATIVE (preferred for first implementation):

Since 1024 bytes = exactly 3 rows + 64 bytes remainder, and 320 divides
into 1024 with remainder 64, we can use a simpler non-streaming approach:
read each block into the buffer and copy the relevant portion. The BLOCK
system already caches blocks so re-reads are free.

```forth
\ BLIT-FRAME-RAW ( start-blk# -- )
\ Read 63 blocks, blit 320 bytes per row, 200 rows total.
\ Simple byte-position tracking using VARIABLE.
VARIABLE BF-ROW   \ current output row (0-199)
VARIABLE BF-BYTE  \ byte position within frame

: BLIT-FRAME-RAW ( start-blk# -- )
  0 BF-ROW ! 0 BF-BYTE !
  VID-FRAME-BLKS 0 DO       \ 63 blocks (3F hex)
    DUP I + BLOCK            \ addr of block I
    \ blit up to VID-WIDTH bytes per row from this block
    \ one block = 1024 bytes = 3 full rows + 64 bytes of row 4
    400 0 DO                 \ 1024 bytes in this block
      BF-BYTE @ VID-WIDTH MOD 0= IF   \ row boundary?
        BF-ROW @ VID-HEIGHT < IF
          \ start of new row: blit from current block position
          OVER I +           \ src = block addr + offset
          BF-ROW @           \ row number
          BLIT-ROW           \ ( src row -- ) copies VID-WIDTH bytes
          BF-ROW @ 1 + BF-ROW !
        THEN
      THEN
      BF-BYTE @ 1 + BF-BYTE !
    VID-WIDTH +LOOP          \ advance by row width
  LOOP
  DROP
;
```

NOTE: The double-loop above is O(n^2) in block bytes. Simplify:
Since blocks are 1024 bytes and rows are 320 bytes, the mapping is:
  Block 0: rows 0, 1, 2 complete + 64 bytes of row 3
  Block 1: 256 bytes remaining of row 3 + rows 4, 5, 6 + 128 bytes of 7
  ...
This repeats with period LCM(1024,320) = 3200 bytes = 10 blocks for
exactly 10 rows. The pattern repeats 20 times for 200 rows.

The cleanest implementation uses a flat byte counter:

```forth
\ BLIT-FRAME-FLAT ( start-blk# -- )
\ Treats the frame as a flat byte array across 63 blocks.
\ For each row: compute which block contains its start,
\ copy 320 bytes handling the block boundary if needed.
VARIABLE BFF-ROW

: BLIT-ROW-AT ( row# start-blk# -- )
  \ row# * 320 = byte offset into frame
  \ byte offset / 1024 = which block
  \ byte offset mod 1024 = offset within that block
  SWAP VID-WIDTH *          \ byte_off = row * 320
  OVER + SWAP               \ start_blk + (byte_off/1024)
  SWAP 400 /                \ block_index = byte_off / 1024
  + SWAP                    \ ( blk#+block_index byte_off_in_blk )
  400 MOD                   \ byte_offset_in_block
  SWAP BLOCK +              \ src = block_buffer + offset
  ROT                       \ ( src row# )
  BLIT-ROW                  \ copy VID-WIDTH bytes to framebuffer row
;

\ BLIT-FRAME-FLAT ( start-blk# -- )
: BLIT-FRAME-FLAT ( start-blk# -- )
  VID-HEIGHT 0 DO           \ 200 rows (C8 hex)
    DUP I OVER              \ start-blk# row# start-blk#
    BLIT-ROW-AT
  LOOP
  DROP
;
```

NOTE: BLIT-ROW-AT handles the row-to-block mapping correctly but does
NOT handle the case where a row spans two blocks (which happens when
byte_offset_in_block + 320 > 1024). This occurs when byte_off_in_blk >
704 (1024 - 320). In that case, BLIT-ROW must copy from two consecutive
blocks. The simplest fix: BLIT-ROW-SPAN checks for the boundary case.

```forth
\ BLIT-ROW-SPAN ( src1 blk1 row# -- )
\ Blit one row that may span two blocks.
\ src1 = offset into blk1 where row starts
VARIABLE BRS-SRC
VARIABLE BRS-ROW

: BLIT-ROW-SPAN ( off blk# row# -- )
  BRS-ROW !                 \ save row#
  OVER BLOCK +              \ src = blk# buffer + offset
  BRS-SRC !                 \ save src
  SWAP 400 SWAP -           \ bytes available in first block
  DUP VID-WIDTH >= IF       \ fits in one block?
    DROP
    BRS-SRC @ BRS-ROW @ BLIT-ROW EXIT
  THEN
  \ crosses block boundary
  \ first_part bytes from blk, then rest from blk+1
  >R BRS-SRC @              \ src1 first_part
  BRS-ROW @ VID-WIDTH *     \ dest row addr
  GFX-FB +                  \ absolute framebuffer addr
  SWAP R@ MOVE              \ copy first_part bytes
  \ remaining bytes from next block
  VID-WIDTH R@ -            \ remaining = 320 - first_part
  R> SWAP                   \ remaining first_part
  OVER 1 + BLOCK            \ next block buffer
  SWAP MOVE
;
```

USE THE FLAT APPROACH (`BLIT-FRAME-FLAT` + `BLIT-ROW-SPAN`) for
correctness. Optimize later if throughput is a concern.

### Block 323 — BMV-CHECK + FRAME-LOOP

```forth
\ BMV-CHECK ( blk# -- ok? )
\ Check BMP magic at start of block.
\ Returns true if block starts with 'BM' (0x4D42).
: BMV-CHECK ( blk# -- ok? )
  BLOCK W@                  \ read 16-bit word at block start
  BMP-MAGIC =
;

\ FRAME-LOOP ( start-blk# nframes fps -- )
\ Core video playback loop.
\ fps: 15 or 30 (use 15 for safe demo, 30 for smooth)
\ Frame budget: 1000ms/fps per frame
VARIABLE FL-FPS
VARIABLE FL-FRAMES
VARIABLE FL-START
VARIABLE FL-I

: FRAME-LOOP ( start-blk# nframes fps -- )
  FL-FPS ! FL-FRAMES ! FL-START !
  !POST                     \ arm display (GRAPHICS word)
  0 FL-I !
  BEGIN
    FL-I @ FL-FRAMES @ <
  WHILE
    FL-I @ VID-FRAME-BLKS * FL-START @ +  \ block# of frame
    BLIT-FRAME-FLAT          \ read+blit frame
    VSYNC-WAIT               \ sync to display
    FL-I @ 1 + FL-I !
    VID-PLAYING @ 0= IF LEAVE THEN  \ stop if !TVOFF called
  REPEAT
  !TVOFF                    \ disarm display
;
```

### Block 324 — High-level playback words

```forth
\ VIDEO-PLAY ( start-blk# nframes -- ) Play at 30fps
: VIDEO-PLAY ( start-blk# nframes -- )
  DECIMAL 30 HEX FRAME-LOOP
;

\ VIDEO-PLAY-15 ( start-blk# nframes -- ) Play at 15fps
: VIDEO-PLAY-15 ( start-blk# nframes -- )
  DECIMAL 15 HEX FRAME-LOOP
;

\ SLIDESHOW ( start-blk# nframes ms -- ) Still-frame viewer
: SLIDESHOW ( start-blk# nframes ms -- )
  >R SWAP
  0 DO
    DUP I VID-FRAME-BLKS * + BLIT-FRAME-FLAT
    R@ DECIMAL 1000 * US-DELAY HEX  \ delay in us
    KEY? IF LEAVE THEN      \ any key stops slideshow
  LOOP
  R> 2DROP
;

\ BMV360.TASK ( start-blk# nframes -- ) TAQOZ-compatible name
: BMV360.TASK ( start-blk# nframes -- )
  VIDEO-PLAY-15             \ 15fps for reliable demo
;

\ TV ( -- ) Play demo video from default location
\ VID-START must be set first: n VID-START !
: TV ( -- )
  VID-START @ 0= IF
    ." VID-START not set" CR EXIT
  THEN
  VID-START @               \ start block
  DECIMAL 45 HEX            \ 45 frames (3 seconds at 15fps)
  VIDEO-PLAY-15
;
```

### Block 325 — VIDEO-INFO + VIDEO-TEST-FRAME

```forth
\ VIDEO-INFO ( start-blk# -- ) Print frame timing info
: VIDEO-INFO ( start-blk# -- )
  ." VIDEO: start=" DUP . CR
  ." Frame blocks: " VID-FRAME-BLKS . CR
  ." Frame bytes: " VID-FRAME-BYTES . CR
  ." 15fps budget: " DECIMAL 66 . ." ms" CR HEX
  ." 30fps budget: " DECIMAL 33 . ." ms" CR HEX
  DROP
;

\ VIDEO-TEST-FRAME ( -- ) Generate a test frame in blocks
\ Fills VID-START @ blocks with a color gradient for testing
\ without needing a real video file.
: VIDEO-TEST-FRAME ( -- )
  VID-START @ 0= IF
    ." Set VID-START first" CR EXIT
  THEN
  VID-HEIGHT 0 DO            \ 200 rows
    VID-WIDTH 0 DO           \ 320 pixels
      J VID-WIDTH * I +      \ frame byte offset
      VID-START @ SWAP       \ start-blk#  byte-offset
      400 /                  \ block index
      + SWAP 400 MOD         \ blk#  offset
      BUFFER +               \ buffer addr + offset
      J I + FF AND           \ color = (row+col) mod 256
      SWAP C!                \ write pixel
    LOOP
  LOOP
  VID-FRAME-BLKS 0 DO
    VID-START @ I + BUFFER DROP
    UPDATE                   \ mark modified
  LOOP
  SAVE-BUFFERS               \ write to disk
  ." Test frame written" CR
;

ONLY FORTH DEFINITIONS
```

## Part 2: tools/create-video.py

Host-side tool to convert BMP sequences to ForthOS block format.

```python
#!/usr/bin/env python3
"""
create-video.py — Convert BMP sequence to ForthOS block format.

Reads a directory of 320x200 8bpp BMP files (numbered 0000.bmp,
0001.bmp, ...) and writes them as consecutive Forth blocks into
an existing blocks.img file starting at the given block number.

Each frame = 63 blocks (64,512 bytes: 64,000 pixel data + 512 padding).

Usage:
  python3 tools/create-video.py <bmp-dir> <blocks.img> <start-block>

Example:
  python3 tools/create-video.py frames/ build/blocks.img 500
  # Writes frames to blocks 500, 563, 626, ... (63 blocks apart)
"""
import sys, os, struct, glob

FRAME_BLOCKS = 63
BLOCK_SIZE = 1024
FRAME_BYTES = 64000        # 320 * 200
BMP_HEADER_SIZE = 54       # standard uncompressed BMP header

def read_bmp_pixels(path):
    """Read 320x200 8bpp BMP, return 64000 bytes of pixel data."""
    with open(path, 'rb') as f:
        header = f.read(BMP_HEADER_SIZE)
        magic = header[0:2]
        if magic != b'BM':
            raise ValueError(f"{path}: not a BMP file")
        pixel_offset = struct.unpack_from('<I', header, 10)[0]
        width = struct.unpack_from('<i', header, 18)[0]
        height = struct.unpack_from('<i', header, 22)[0]
        bpp = struct.unpack_from('<H', header, 28)[0]
        if abs(width) != 320 or abs(height) != 200:
            raise ValueError(f"{path}: must be 320x200 (got {width}x{height})")
        if bpp != 8:
            raise ValueError(f"{path}: must be 8bpp (got {bpp}bpp)")
        f.seek(pixel_offset)
        pixels = f.read(FRAME_BYTES)
        # BMP rows are stored bottom-up; flip for top-down display
        rows = [pixels[i*320:(i+1)*320] for i in range(200)]
        if height > 0:   # positive height = bottom-up
            rows = list(reversed(rows))
        return b''.join(rows)

def write_frame(img_path, start_block, pixels):
    """Write one frame (64000 bytes) to blocks starting at start_block."""
    # Pad to FRAME_BLOCKS * BLOCK_SIZE bytes
    padded = pixels + b'\x00' * (FRAME_BLOCKS * BLOCK_SIZE - FRAME_BYTES)
    offset = start_block * BLOCK_SIZE
    with open(img_path, 'r+b') as f:
        f.seek(offset)
        f.write(padded)

def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    bmp_dir, img_path, start_block = sys.argv[1], sys.argv[2], int(sys.argv[3])
    bmps = sorted(glob.glob(os.path.join(bmp_dir, '*.bmp')))
    if not bmps:
        print(f"No .bmp files found in {bmp_dir}")
        sys.exit(1)
    img_size = os.path.getsize(img_path)
    for i, bmp_path in enumerate(bmps):
        blk = start_block + i * FRAME_BLOCKS
        if (blk + FRAME_BLOCKS) * BLOCK_SIZE > img_size:
            print(f"Frame {i}: block {blk} exceeds image size. Stopping.")
            break
        pixels = read_bmp_pixels(bmp_path)
        write_frame(img_path, blk, pixels)
        print(f"Frame {i:4d}: {os.path.basename(bmp_path)} → blocks {blk}-{blk+FRAME_BLOCKS-1}")
    print(f"Done. {len(bmps)} frames written starting at block {start_block}.")
    print(f"In ForthOS: {start_block} VID-START !")
    print(f"            {start_block} {len(bmps)} VIDEO-PLAY-15")

if __name__ == '__main__':
    main()
```

## Part 3: tests/test_video.py

The VIDEO vocabulary is harder to test in QEMU without a real video file.
Tests focus on: vocabulary loads, constants correct, word definitions exist,
FRAME-ADDR math correct, VIDEO-TEST-FRAME generates expected data.

```python
def test_video_load():
    """VIDEO vocabulary loads without errors"""

def test_using_video():
    """USING VIDEO adds to search order"""

def test_frame_constants():
    """VID-WIDTH=320, VID-HEIGHT=200, VID-FRAME-BLKS=63"""
    # HEX 140 = 320, C8 = 200, 3F = 63

def test_frame_addr_math():
    """FRAME-ADDR: frame 0 = VID-START, frame 1 = VID-START+63"""
    # 100 VID-START !  (set base to block 256)
    # 0 FRAME-ADDR . → 256 (0x100)
    # 1 FRAME-ADDR . → 319 (0x100 + 0x3F)
    # 2 FRAME-ADDR . → 382 (0x100 + 0x7E)

def test_bmp_magic():
    """BMP-MAGIC = 0x4D42"""

def test_vid_start_variable():
    """VID-START initialized to 0"""

def test_vid_playing_variable():
    """VID-PLAYING initialized to 0"""

def test_bmv360_task_defined():
    """BMV360.TASK word exists (TICK check)"""

def test_tv_word_defined():
    """TV word exists (TICK check)"""

def test_test_frame_generation():
    """VIDEO-TEST-FRAME generates data in blocks (needs VID-START set)"""
    # 100 VID-START !
    # VIDEO-TEST-FRAME
    # 100 BLOCK C@ . → some non-zero value (gradient pixel)

def test_slideshow_defined():
    """SLIDESHOW word exists"""

def test_search_order_clean():
    """Search order clean after VIDEO loads"""

def test_stack_clean():
    """Stack is clean after all tests"""
```

## Part 4: Makefile additions

Add to write-catalog target:
```makefile
# VIDEO blocks (auto-discovered by write-catalog.py if it finds video.fth)
# Add create-video tool as a new Makefile target:
create-video: tools/create-video.py
	@echo "Usage: make create-video FRAMES=<dir> START=<block>"
	$(PYTHON) tools/create-video.py $(FRAMES) $(BUILD)/blocks.img $(START)
```

## Sequence of Events for Claude Code

1. Create forth/dict/video.fth — check GRAPHICS words exist first:
   ```bash
   grep -n "BLIT-ROW\|VSYNC-WAIT\|!POST\|!TVOFF\|GFX-FB" \
     forth/dict/graphics.fth
   ```
   All must be present. VIDEO calls these directly.

2. Verify AUDIO is loaded before VIDEO in test (for BEEP):
   ```
   USING HARDWARE  USING PCI-ENUM
   USING VGA-GRAPHICS  USING GRAPHICS
   USING AUDIO  USING VIDEO
   ```

3. Create tools/create-video.py

4. Line-length check:
   ```bash
   awk 'length > 64 {print NR": "length": "$0}' forth/dict/video.fth
   ```

5. Build + test:
   ```bash
   make clean && make && make blocks && make write-catalog
   make write-catalog 2>&1 | grep VIDEO
   python3 tests/test_video.py [port]
   ```

6. Full regression:
   ```bash
   make test
   ```

7. Commit:
   ```
   VIDEO vocabulary: TAQOZ BMV360.TASK port for ForthOS

   - BLIT-FRAME-FLAT: read+blit one full frame from blocks
   - BLIT-ROW-SPAN: handle row-to-block boundary crossing
   - FRAME-LOOP: core 15/30fps playback loop with VSYNC-WAIT
   - VIDEO-PLAY VIDEO-PLAY-15: high-level playback words
   - BMV360.TASK: TAQOZ-compatible word (exact name preserved)
   - TV: top-level demo launcher from VID-START
   - SLIDESHOW: still-frame viewer with key-to-advance
   - VIDEO-TEST-FRAME: generate gradient test frame in blocks
   - tools/create-video.py: host-side BMP→blocks converter
   - Blocks 320-331, 12/12 tests passing
   ```

## Implementation Pitfalls

### BLOCK caching — only 4 buffers
The kernel has 4 block buffers. BLIT-FRAME-FLAT reads up to 63 blocks
per frame. Since only 4 can be cached, block reads will be frequent.
This is correct behavior — just be aware that BLOCK will trigger disk
I/O on most calls. The AHCI driver handles this transparently.

On QEMU (ATA PIO, not AHCI): each BLOCK call does 2 ATA sector reads.
At ~3MB/s ATA PIO throughput, 63 blocks = 64KB = ~21ms read time.
At 30fps budget (33ms/frame), this leaves only 12ms for blit + VSYNC.
At 15fps budget (66ms/frame), this leaves 45ms for blit + VSYNC — comfortable.

This is why VIDEO-PLAY-15 is the demo target. HP hardware with AHCI
at 1000Mbps reads 63 blocks in <<1ms, enabling 30fps.

### Row-to-block boundary math
The trickiest part is BLIT-ROW-AT correctly computing which block
contains each row's start. The formula:
  byte_offset = row * 320
  block_index = byte_offset / 1024  (integer division)
  block_offset = byte_offset mod 1024
  src_addr = BLOCK(start_blk + block_index) + block_offset

When block_offset + 320 > 1024, the row crosses a block boundary and
needs BLIT-ROW-SPAN. This condition occurs when block_offset > 704.

Use `/` for integer division and `MOD` for remainder — both are in
the Forth-83 kernel. Verify they are floored (Forth-83 semantics) —
for positive dividends this doesn't matter, but document the assumption.

### BUFFER vs BLOCK for VIDEO-TEST-FRAME
VIDEO-TEST-FRAME writes pixel data to blocks. Use BUFFER (not BLOCK)
for write operations — BUFFER allocates a buffer without reading the
old data from disk, which is faster and correct when writing entire
blocks from scratch. Then UPDATE + SAVE-BUFFERS flushes to disk.

### VID-START must be set before TV
TV calls VID-START @. If VID-START is 0, the video plays from block 0
which contains ForthOS vocabulary catalog data, producing garbage on
screen. Guard with the 0= check already in the spec. For the demo,
set VID-START to a block range that has been populated by create-video.py.

### DO/LOOP bounds in HEX mode
VID-HEIGHT in HEX = C8 (200). VID-WIDTH in HEX = 140 (320).
VID-FRAME-BLKS in HEX = 3F (63).
When writing loops: always comment the decimal meaning.

### BLIT-ROW signature
Verify the GRAPHICS vocab's BLIT-ROW signature is ( src row -- ) not
( row src -- ) before writing VIDEO. A wrong assumption here silently
blits to the wrong row. Check graphics.fth directly.

## Connection to A/V Phases

Phase 1 (GRAPHICS): pixel primitives, VSYNC-WAIT, !POST, !TVOFF ✓
Phase 2 (AUDIO): BEEP, TONE, AC97 DMA, HDA ✓
Phase 3 (this task): VIDEO — BMV360.TASK, block frame loop
Phase 4 (AV-SYNC): IRQ-driven audio + video synchronized compositor

The BMV360.TASK word in this vocab is the TAQOZ name preserved exactly.
Phase 4 AV-SYNC will wrap BMV360.TASK with concurrent audio DMA to
produce synchronized audio+video playback — the final demo capability.

## HP Hardware Validation Notes

On HP 15-bs0xx via PXE:
1. AHCI at 1000Mbps — 63 blocks reads in <<1ms, 30fps is viable
2. VID-START should point to blocks written to the AHCI disk by
   create-video.py running on the dev machine before PXE boot
3. The NTFS drive (Windows partitions) is read-only via NTFS vocab —
   video frames need to be in the ForthOS blocks partition (disk 2)
4. PXE blocks.img must be large enough: 4MB for 45-frame demo clip

## Demo Video Sequence (Final A/V chain)

```forth
\ On HP hardware, after PXE boot:
USING HARDWARE
USING PCI-ENUM
USING VGA-GRAPHICS
USING GRAPHICS
USING AUDIO
USING VIDEO

\ Initialize audio
AUDIO-INIT          \ auto-detects HDA on HP

\ Set video source
500 VID-START !     \ frames start at block 500

\ Play 3-second demo at 15fps with audio
440 500 TONE        \ startup beep (440Hz, 500ms)
500 45 VIDEO-PLAY-15  \ 45 frames at 15fps

\ Or with TAQOZ-compatible word:
500 45 BMV360.TASK

\ Or simplified TV word:
TV
```
