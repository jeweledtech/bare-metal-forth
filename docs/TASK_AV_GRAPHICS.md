# TASK: GRAPHICS Vocabulary — VGA Mode 13h for ForthOS
# Phase A/V Phase 1 of 4: Pixel Graphics Foundation

## Context

ForthOS already has VGA text mode at 0xB8000 (80×25, 16 colors). This task
adds pixel graphics via VGA Mode 13h (320×200, 256 colors, linear framebuffer
at 0xA0000). This is the first of four A/V phases inspired by the TAQOZ
RELOADED system (Parallax P2 Forth) which fit a complete audio/graphics/video
stack in 5,824 bytes. ForthOS targets the same philosophy: direct hardware
register access, no codec layers, no OS abstraction.

Mode 13h is the ideal starting point:
- Single write to 0xA0000 + (y*320 + x) sets a pixel — no page flipping
- QEMU emulates it perfectly
- It is the same mode used by DOOM, the original Wolfenstein 3D, and every
  DOS demo scene production. Proven, direct, fast.
- Bochs VBE (higher resolutions) builds on top of this as Phase 1b.

## Repository

~/projects/forthos (github.com/jeweledtech/bare-metal-forth)

## Block Assignment

Blocks 150–179 — GRAPHICS vocabulary
  150     : Catalog header + VGA register constants
  151     : Mode-switch words (TEXT-MODE, GFX-MODE, VGA-MODE13-INIT)
  152     : Pixel primitives (PLOT, HLINE, VLINE, CLS-GFX)
  153     : Rectangle and fill words (RECT, FILL-RECT)
  154     : BMP sector blit (BLIT-ROW, VIEW-SECTOR) — TAQOZ pattern
  155     : Palette words (PAL!, PAL@, SET-PALETTE, DEFAULT-PALETTE)
  156     : VSYNC word + frame timing constants
  157     : Bochs VBE init (QEMU 1024×768 32bpp) — Phase 1b
  158     : VBE pixel words + framebuffer address store
  159     : Demo words (TEST-PATTERN, GRADIENT, PIXEL-DEMO)
  160–179 : Reserved for expansion (sprite words, font blitter, etc.)

## Critical Constraints (do not violate)

1. 64-character line limit — hard limit from Forth block format (16×64)
2. No 2* — use DUP + instead (not in 178-word kernel)
3. No " (double-quote) in Forth-83 — use DECIMAL 34 CONSTANT QC + QC EMIT
4. Short strings under 6 chars in ." corrupt state — pad to 6+ or use EMIT
5. Every vocab must end: ONLY FORTH DEFINITIONS (prevents search order leak)
6. ALSO/PREVIOUS must be matched — count them
7. HEX/DECIMAL bleed — switch back explicitly; document every switch
8. Verify every word used against forth.asm before writing vocab source
9. No word name longer than 31 characters

## Kernel Words Available (verified in forth.asm)

Stack:    DUP DROP SWAP OVER ROT NIP 2DUP 2DROP
Arith:    + - * / MOD DUP + (for 2*) NEGATE ABS
Memory:   @ ! C@ C! MOVE FILL HERE ALLOT ,
Compare:  = < > 0= 0< MAX MIN
I/O:      INB OUTB INW OUTW EMIT KEY CR .S .
Blocks:   BLOCK BUFFER UPDATE SAVE-BUFFERS FLUSH LOAD THRU
Vocab:    VOCABULARY DEFINITIONS ALSO PREVIOUS ONLY FORTH USING ORDER
Control:  IF ELSE THEN DO LOOP BEGIN UNTIL WHILE REPEAT EXIT
Compiler: : ; CONSTANT VARIABLE CREATE DOES> IMMEDIATE ' EXECUTE LITERAL
Port I/O: INB OUTB (already proven in HARDWARE vocab)

## Part 1: forth/dict/graphics.fth

### Block 150 — Catalog header + VGA port constants

```forth
\ CATALOG: GRAPHICS
\ CATEGORY: video
\ SOURCE: hand-written
\ SOURCE-BINARY: none
\ PORTS: 0x3C0-0x3CF,0x3D4-0x3D5
\ MMIO: 0xA0000-0xA4B00 (mode13h), 0x01CE-0x01CF (VBE)
\ CONFIDENCE: high
\ REQUIRES: HARDWARE ( US-DELAY )
VOCABULARY GRAPHICS
GRAPHICS DEFINITIONS
HEX
3C0 CONSTANT VGA-AC-INDEX
3C1 CONSTANT VGA-AC-READ
3C2 CONSTANT VGA-MISC-WRITE
3C4 CONSTANT VGA-SEQ-INDEX
3C5 CONSTANT VGA-SEQ-DATA
3C6 CONSTANT VGA-DAC-MASK
3C7 CONSTANT VGA-DAC-READ-INDEX
3C8 CONSTANT VGA-DAC-WRITE-INDEX
3C9 CONSTANT VGA-DAC-DATA
3CC CONSTANT VGA-MISC-READ
3CE CONSTANT VGA-GC-INDEX
3CF CONSTANT VGA-GC-DATA
3D4 CONSTANT VGA-CRTC-INDEX
3D5 CONSTANT VGA-CRTC-DATA
```

### Block 151 — Mode switch words

The standard VGA BIOS INT 10h AH=00h sets the mode. Since we are bare metal
with no BIOS in protected mode, we must program the VGA registers directly.
Mode 13h requires writing a specific sequence to Sequencer, CRTC, Graphics
Controller, and Attribute Controller registers.

NOTE: The full register table for Mode 13h is 61 register writes. Rather than
inline all 61 values, we use a compact table in memory and loop over it. This
keeps it within the 64-char line limit and is much more readable.

The mode 13h register sequence is well-documented and identical across all
VGA-compatible hardware (including QEMU's standard VGA emulation).

```forth
\ VGA-WRITE-REGS ( table-addr count index-port -- )
\ Write count index/data pairs from table to index-port/data-port
: VGA-WRITE-REGS ( tbl cnt idx -- )
  >R                       \ save index port
  0 DO
    DUP I DUP + C@ R@ OUTB  \ write index
    DUP I DUP + 1 + C@ R@ 1 + OUTB  \ write data
    2 +
  LOOP
  DROP R> DROP
;
```

NOTE: The Mode 13h register table (61 pairs = 122 bytes) should be stored
as a CREATE/DOES> structure in a subsequent block. QEMU also supports the
simpler approach of using `INT 10h` via real-mode stub — but since we need
this to work in protected mode, direct register programming is required.

For the initial implementation, use the BOCHS VBE approach (Block 157) which
is simpler and gives higher resolution. Mode 13h direct register programming
can follow in a subsequent iteration.

```forth
A0000 CONSTANT GFX-FB        \ Mode 13h framebuffer base
4B00  CONSTANT GFX-FB-SIZE   \ 320*200 = 64000 bytes
0140  CONSTANT GFX-WIDTH      \ 320 decimal
00C8  CONSTANT GFX-HEIGHT     \ 200 decimal
VARIABLE GFX-ACTIVE           \ 0=text mode, 1=mode13, 2=VBE
0 GFX-ACTIVE !
```

```forth
\ TEXT-MODE ( -- ) Return to VGA 80x25 text mode
: TEXT-MODE ( -- )
  0 GFX-ACTIVE !
  \ INT 10h AH=00h AL=03h via BIOS is not available in PM.
  \ We rely on QEMU's soft reset or re-enter via Bochs VBE reset.
  \ For now: signal intent; full register restore in later iteration.
  ." Returning to text mode..." CR
;
```

### Block 152 — Pixel primitives

```forth
\ GFX-ADDR ( x y -- addr ) Compute framebuffer address
: GFX-ADDR ( x y -- addr )
  GFX-WIDTH * +           \ y*320 + x
  GFX-FB +                \ + base
;

\ PLOT ( x y color -- ) Write one pixel
: PLOT ( x y color -- )
  >R GFX-ADDR R> SWAP C!
;

\ HLINE ( x y len color -- ) Horizontal line
: HLINE ( x y len color -- )
  >R                       \ save color
  SWAP >R                  \ save len
  GFX-ADDR                 \ compute start addr
  R> R>                    \ restore len color
  FILL                     \ FILL ( addr len byte -- )
;

\ VLINE ( x y len color -- ) Vertical line
: VLINE ( x y len color -- )
  >R 2>R                   \ save color, save x y
  0 DO
    2R@ SWAP I + SWAP      \ x  y+i
    R@ PLOT
  LOOP
  R> 2R> 2DROP
;

\ CLS-GFX ( color -- ) Clear graphics screen
: CLS-GFX ( color -- )
  GFX-FB GFX-FB-SIZE ROT FILL
;
```

NOTE: 2>R and 2R@ require checking kernel. If not present, use two separate
>R operations. Verify against forth.asm before using.

### Block 153 — Rectangle words

```forth
\ RECT ( x y w h color -- ) Draw rectangle outline
: RECT ( x y w h color -- )
  >R                        \ save color
  2DUP 2OVER DROP R@        \ top: x y w color
  HLINE
  2DUP OVER + SWAP R@       \ bottom: x y+h w color
  HLINE
  2DUP R@                   \ left: x y 1 h color
  >R SWAP >R                \ save h color
  GFX-ADDR R> R>            \ addr h color
  VLINE
  ROT OVER + ROT R@ VLINE   \ right side
  R> DROP
;

\ FILL-RECT ( x y w h color -- ) Filled rectangle
: FILL-RECT ( x y w h color -- )
  >R                        \ save color
  0 DO
    2DUP I + R@             \ x y+i color
    OVER HLINE
  LOOP
  R> DROP 2DROP
;
```

### Block 154 — BMP sector blit (TAQOZ pattern)

This is the core of the TAQOZ video player — reading a 320-byte row
directly from disk sectors into the framebuffer. The TAQOZ BMV360.TASK
word reads sectors containing BMP pixel data and blits them row by row,
synchronized to VSYNC. This is the same pattern adapted for ForthOS with
AHCI/ATA block access.

A 320×200 BMP frame (uncompressed, 8bpp) is approximately 64KB, which is
62.5 Forth blocks. We round to 64 blocks per frame for alignment. At
~1000Mbps AHCI throughput, reading 64 blocks takes negligible time compared
to the 16.6ms frame budget.

```forth
\ BLIT-ROW ( block-addr row -- ) Blit one 320-byte row to framebuffer
\ block-addr: address of loaded block buffer (1024 bytes)
\ row: destination row in framebuffer (0-199)
: BLIT-ROW ( baddr row -- )
  GFX-WIDTH *              \ row offset in pixels
  GFX-FB +                 \ framebuffer destination
  SWAP                     \ ( dst src )
  GFX-WIDTH MOVE           \ copy 320 bytes
;

\ VIEW-SECTOR ( blk# -- ) Load block and blit to framebuffer at row 0
\ Simplified: one block = 1024 bytes = 3.2 rows (not aligned)
\ Real implementation stores sectors as 512-byte chunks aligned to rows
: VIEW-SECTOR ( blk# -- )
  BLOCK                    \ read block, get buffer addr
  0 BLIT-ROW               \ blit first row (proof of concept)
;

\ BLIT-FRAME ( first-blk# nblks -- ) Blit a full frame from blocks
: BLIT-FRAME ( first# count -- )
  0 DO
    DUP I + BLOCK           \ load block i
    I GFX-WIDTH * GFX-FB +  \ dest row addr
    SWAP GFX-WIDTH MOVE     \ copy 320 bytes per block row
  LOOP DROP
;
```

### Block 155 — Palette words

Mode 13h has a 256-entry DAC palette. Each entry is 6-bit RGB (0-63 each).
Reading/writing goes through ports 0x3C8 (write index), 0x3C9 (data, 3 bytes
per entry: R G B), 0x3C7 (read index).

```forth
\ PAL! ( r g b index -- ) Set one palette entry (values 0-63)
: PAL! ( r g b index -- )
  VGA-DAC-WRITE-INDEX OUTB  \ set write index
  VGA-DAC-DATA OUTB         \ write R
  VGA-DAC-DATA OUTB         \ write G
  VGA-DAC-DATA OUTB         \ write B
;

\ PAL@ ( index -- r g b ) Read one palette entry
: PAL@ ( index -- r g b )
  VGA-DAC-READ-INDEX OUTB   \ set read index
  VGA-DAC-DATA INB          \ read R
  VGA-DAC-DATA INB          \ read G
  VGA-DAC-DATA INB          \ read B
;

\ GRAY-PALETTE ( -- ) Set 256-entry linear grayscale palette
: GRAY-PALETTE ( -- )
  100 0 DO                  \ 256 entries (HEX 100 = 256)
    I 3 /                   \ R = index/3 (maps 0-255 → 0-85, scaled)
    DUP DUP                 \ R G B same = gray
    I PAL!
  LOOP
;
```

### Block 156 — VSYNC

The VGA vertical sync bit lives at I/O port 0x3DA bit 3. Waiting for vsync
prevents tearing — essential for smooth video playback.

```forth
3DA CONSTANT VGA-INPUT-STATUS1

\ VSYNC-WAIT ( -- ) Wait for vertical retrace start
: VSYNC-WAIT ( -- )
  BEGIN                     \ wait for end of previous vsync
    VGA-INPUT-STATUS1 INB
    8 AND 0=
  UNTIL
  BEGIN                     \ wait for start of new vsync
    VGA-INPUT-STATUS1 INB
    8 AND
  UNTIL
;

\ VSYNC-FRAME-MS: Mode 13h at 70Hz = 14.28ms per frame
\ At 60Hz: 16.67ms per frame
\ TAQOZ used 16.64ms (PAL timing). We target 60Hz = 16ms budget.
DECIMAL
16 CONSTANT VSYNC-MS        \ nominal frame time in ms
HEX

\ !POST ( -- ) Arm video output (TAQOZ pattern name preserved)
: !POST ( -- )
  1 GFX-ACTIVE !
;

\ !TVOFF ( -- ) Disarm video output (TAQOZ pattern name preserved)
: !TVOFF ( -- )
  0 GFX-ACTIVE !
  CLS-GFX                   \ clear framebuffer
;
```

### Block 157 — Bochs VBE init (QEMU higher-resolution path)

Bochs VBE is available in QEMU via I/O ports 0x01CE (index) and 0x01CF (data).
This provides resolutions up to 1920×1080 with 32bpp linear framebuffer.
The framebuffer address is at PCI BAR 0 of the Bochs VGA device (PCI 1234:1111).

QEMU auto-detect already identifies this device (1234:1111 VGA check in
AUTO-DETECT vocab). We reuse that detection to get the framebuffer address.

```forth
\ VBE port constants
01CE CONSTANT VBE-INDEX
01CF CONSTANT VBE-DATA

\ VBE register indices
0000 CONSTANT VBE-ID
0001 CONSTANT VBE-XRES
0002 CONSTANT VBE-YRES
0003 CONSTANT VBE-BPP
0004 CONSTANT VBE-ENABLE
0005 CONSTANT VBE-BANK
0006 CONSTANT VBE-VIRT-W
0007 CONSTANT VBE-VIRT-H
0009 CONSTANT VBE-X-OFF
000A CONSTANT VBE-Y-OFF

\ VBE-REG@ ( reg -- val ) Read VBE register
: VBE-REG@ ( reg -- val )
  VBE-INDEX OUTW
  VBE-DATA INW
;

\ VBE-REG! ( val reg -- ) Write VBE register
: VBE-REG! ( val reg -- )
  VBE-INDEX OUTW
  VBE-DATA OUTW
;

\ VBE-INIT ( width height bpp -- ) Init Bochs VBE mode
: VBE-INIT ( w h bpp -- )
  0 VBE-ENABLE VBE-REG!     \ disable VBE
  ROT VBE-XRES VBE-REG!     \ set width
  ROT VBE-YRES VBE-REG!     \ set height
  VBE-BPP VBE-REG!          \ set bpp
  41 VBE-ENABLE VBE-REG!    \ enable VBE + linear framebuffer
  2 GFX-ACTIVE !
;
```

### Block 158 — VBE framebuffer address + pixel word

The Bochs VBE framebuffer base address comes from PCI BAR0 of device
1234:1111. The AUTO-DETECT vocab already reads this. We store it in a
VARIABLE for use by VBE pixel words.

```forth
VARIABLE VBE-FB             \ framebuffer base address (from PCI BAR0)
VARIABLE VBE-WIDTH          \ current width in pixels
VARIABLE VBE-PITCH          \ bytes per row (width * bpp/8)

\ VBE-PIXEL-ADDR ( x y -- addr ) 32bpp framebuffer address
: VBE-PIXEL-ADDR ( x y -- addr )
  VBE-PITCH @ * +           \ y * pitch + x
  4 *                       \ * 4 bytes per pixel (32bpp)
  VBE-FB @ +
;

\ VBE-PLOT ( x y argb -- ) Write 32bpp pixel
: VBE-PLOT ( x y argb -- )
  >R VBE-PIXEL-ADDR R> SWAP !
;

\ VBE-CLS ( argb -- ) Clear VBE framebuffer
: VBE-CLS ( argb -- )
  VBE-FB @
  VBE-WIDTH @ VBE-PITCH @ *  \ total bytes
  ROT FILL                   \ NOTE: FILL is byte-fill; needs 32-bit version
;
```

NOTE: A 32-bit FILL word (FILL32) should be implemented for VBE-CLS since
the standard FILL does byte fills. This is a kernel extension task — for
now, VBE-CLS can loop with VBE-PLOT as a correct-if-slow implementation.

### Block 159 — Demo and test words

```forth
\ TEST-PATTERN ( -- ) Fill screen with color bands (mode 13h)
: TEST-PATTERN ( -- )
  0 GFX-ACTIVE ! !POST      \ ensure mode is active
  C8 0 DO                   \ 200 rows (C8 hex = 200)
    140 0 DO                \ 320 cols (140 hex = 320)
      I J + FF AND          \ color = (x+y) mod 256
      J I PLOT
    LOOP
  LOOP
;

\ GRADIENT ( -- ) Horizontal gradient demo
: GRADIENT ( -- )
  C8 0 DO
    140 0 DO
      I                     \ color = x (0-319, wraps mod 256)
      FF AND
      J I PLOT
    LOOP
  LOOP
;

\ PIXEL-DEMO ( -- ) Run test pattern then wait for key
: PIXEL-DEMO ( -- )
  ." Starting pixel demo..." CR
  TEST-PATTERN
  ." Press any key to continue..." CR
  KEY DROP
  TEXT-MODE
;

ONLY FORTH DEFINITIONS
```

## Part 2: Test File — tests/test_graphics.py

Follow the exact pattern of existing test files (test_hardware.py,
test_disasm.py, etc.) using serial automation.

```python
#!/usr/bin/env python3
"""Tests for GRAPHICS vocabulary — VGA Mode 13h + Bochs VBE"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.serial_test_helper import ForthTest

def test_graphics_load():
    """GRAPHICS vocabulary loads without errors"""
    t = ForthTest()
    r = t.send("150 159 THRU")
    assert '?' not in r, f"Load error: {r}"
    assert t.alive()

def test_using_graphics():
    """USING GRAPHICS adds vocab to search order"""
    t = ForthTest()
    t.send("150 159 THRU")
    r = t.send("USING GRAPHICS ORDER")
    assert 'GRAPHICS' in r
    assert t.alive()

def test_vga_constants():
    """VGA port constants are defined and correct"""
    t = ForthTest()
    t.send("150 159 THRU")
    t.send("USING GRAPHICS")
    r = t.send("HEX VGA-CRTC-INDEX . DECIMAL")
    assert '3D4' in r or '3d4' in r.lower()

def test_gfx_addr():
    """GFX-ADDR computes correct framebuffer offset"""
    t = ForthTest()
    t.send("150 159 THRU")
    t.send("USING GRAPHICS")
    # PLOT at x=0, y=0 should write to 0xA0000
    # PLOT at x=5, y=1 should write to 0xA0000 + 320 + 5 = 0xA0145
    r = t.send("HEX 5 1 GFX-ADDR . DECIMAL")
    # 0xA0000 + 320 + 5 = 0xA0145
    assert 'A0145' in r.upper()

def test_vbe_regs_accessible():
    """VBE register ports respond in QEMU"""
    t = ForthTest()
    t.send("150 159 THRU")
    t.send("USING GRAPHICS")
    r = t.send("HEX VBE-ID VBE-REG@ . DECIMAL")
    # Bochs VBE should return 0xB0C0-0xB0C5 depending on version
    assert 'B0C' in r.upper() or '45248' in r  # 0xB0C0 = 45248 decimal

def test_palette_write_read():
    """PAL! writes and PAL@ reads palette entry"""
    t = ForthTest()
    t.send("150 159 THRU")
    t.send("USING GRAPHICS")
    # Write palette entry 1: R=63, G=0, B=0 (pure red)
    t.send("HEX 3F 0 0 1 PAL!")
    r = t.send("1 PAL@ . . . DECIMAL")
    # Should read back 63 0 0 (order may vary — B G R from stack)
    assert '3F' in r.upper() or '63' in r

def test_search_order_clean():
    """Search order is clean after GRAPHICS loads"""
    t = ForthTest()
    t.send("150 159 THRU")
    r = t.send("ORDER")
    # Should not show GRAPHICS already in order (only loaded, not USINGed)
    # FORTH should be the only entry
    assert t.alive()

def test_vsync_word_exists():
    """VSYNC-WAIT is defined and callable"""
    t = ForthTest()
    t.send("150 159 THRU")
    t.send("USING GRAPHICS")
    r = t.send("' VSYNC-WAIT .")
    assert '?' not in r

def test_vbe_init_qemu():
    """VBE-INIT sets 640x480 mode in QEMU without crash"""
    t = ForthTest()
    t.send("150 159 THRU")
    t.send("USING GRAPHICS")
    # 640x480 32bpp
    r = t.send("HEX 280 1E0 20 VBE-INIT DECIMAL")
    assert '?' not in r
    assert t.alive()

def test_post_tvoff():
    """!POST and !TVOFF toggle GFX-ACTIVE correctly"""
    t = ForthTest()
    t.send("150 159 THRU")
    t.send("USING GRAPHICS")
    t.send("!POST")
    r = t.send("GFX-ACTIVE @ .")
    assert '1' in r
    t.send("!TVOFF")
    r = t.send("GFX-ACTIVE @ .")
    assert '0' in r

if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
```

## Part 3: Makefile additions

Add to the write-catalog target in Makefile (following existing pattern):

```makefile
# In write-catalog target, add:
	$(PYTHON) tools/write-block.py $(BUILD)/blocks.img 150 \
        forth/dict/graphics.fth

# Add to test-vocabs target:
	$(PYTHON) tests/test_graphics.py
```

The write-catalog should write the single graphics.fth file across blocks
150-159. The write-block.py tool handles multi-block files automatically
(each 1024-byte block is one screen of 16×64 chars).

NOTE: If graphics.fth exceeds 10 blocks (10×1024 = 10,240 bytes source),
split into graphics-1.fth (blocks 150-154) and graphics-2.fth (155-159)
and write them separately.

## Part 4: HP Hardware Validation Notes

For HP 15-bs0xx real hardware validation via PXE boot:

1. VGA text mode switch back (TEXT-MODE) must fully restore CRT registers
   because the HP uses Intel HD 620 in compatibility mode. The Bochs VBE
   init (VBE-INIT) is the safer path on real hardware — Intel HD 620
   exposes VBE-compatible registers at the same 0x01CE/0x01CF ports.

2. AUTO-DETECT vocab already identifies 1234:1111 (QEMU VGA) and skips
   auto-init on real hardware. The GRAPHICS vocab should check GFX-ACTIVE
   before attempting mode switches. Add a guard:
   ```forth
   : GFX-CHECK ( -- )
     GFX-ACTIVE @ 0= IF
       ." GFX not initialized. Call VBE-INIT first." CR
     THEN ;
   ```

3. The VBE framebuffer address on HP will differ from QEMU's default.
   The AUTO-DETECT vocab should store the PCI BAR0 of the display
   controller into VBE-FB during initialization. Add a hook:
   ```forth
   \ In AUTO-DETECT, after Intel HD 620 is found:
   \ PCI-BAR0-READ -> VBE-FB !
   ```
   This is a follow-up task (TASK_AV_GRAPHICS_HP.md) once QEMU path works.

## Sequence of Events for Claude Code

1. Create forth/dict/graphics.fth from blocks 150-159 as specified above
2. Verify all lines ≤ 64 chars:
   ```bash
   awk 'length > 64 {print NR": "length": "$0}' \
       forth/dict/graphics.fth
   ```
   Zero output required.
3. Add to tools/write-catalog.py (or Makefile write-catalog target)
4. Create tests/test_graphics.py
5. make blocks && make write-catalog
6. Boot QEMU, manually test:
   ```
   150 159 THRU
   USING GRAPHICS
   WORDS
   HEX VBE-ID VBE-REG@ . DECIMAL
   280 1E0 20 VBE-INIT
   TEST-PATTERN
   ```
7. Run make test — all existing + new tests must pass
8. Commit:
   ```
   Add GRAPHICS vocabulary: VGA Mode 13h + Bochs VBE pixel graphics

   - VGA-MODE13-INIT: direct register programming for 320x200x8
   - PLOT HLINE VLINE RECT FILL-RECT: pixel primitives
   - PAL! PAL@: 256-entry DAC palette access
   - VBE-INIT: Bochs VBE for QEMU 640x480/1024x768 32bpp
   - VSYNC-WAIT: VBL sync for tear-free video (TAQOZ pattern)
   - VIEW-SECTOR BLIT-ROW: block-based framebuffer blit
   - !POST !TVOFF: TAQOZ-compatible arm/disarm words
   - TEST-PATTERN GRADIENT PIXEL-DEMO: demo/validation words
   - Blocks 150-159, 10/10 tests passing
   ```

## Implementation Pitfalls to Watch

### The FILL word is byte-fill only
FILL ( addr n byte -- ) fills n bytes with byte. For VBE 32bpp clear you
need a 32-bit fill loop. Implement:
```forth
: FILL32 ( addr n argb -- )
  ROT ROT 0 DO
    2DUP I 2 RSHIFT          \ addr argb i/4 — only write aligned
    ... 
  LOOP 2DROP ;
```
Or, for the first iteration, just leave VBE-CLS as a commented stub and
use VBE-PLOT in a loop. Correctness first.

### VSYNC in QEMU
QEMU's VGA port 0x3DA may not accurately emulate the vsync bit timing.
If VSYNC-WAIT hangs (infinite loop), add a timeout counter:
```forth
: VSYNC-WAIT ( -- )
  FFFF 0 DO
    VGA-INPUT-STATUS1 INB 8 AND IF LEAVE THEN
  LOOP ;
```
This gives vsync or timeout after 65535 polls, whichever comes first.

### DO/LOOP with HEX literals
When in HEX mode, `200 0 DO` means 512 iterations, not 200.
Always comment hex loop bounds with their decimal meaning.
Example: `C8 0 DO  ( 200 rows )`

### Stack depth in nested words
GFX-ADDR, PLOT, HLINE all push/pop. The rectangle and fill-rect words
have deep stacks. Use .S liberally during interactive testing to verify
the stack is clean after each word. Write tests that explicitly check
stack balance.

## Connection to Future A/V Phases

This vocabulary is Phase 1 of 4:
- Phase 1 (this task): GRAPHICS — pixel primitives, VBE, palette, VSYNC
- Phase 2: AUDIO — AC97 (QEMU) / HDA (HP), PCM buffer, BEEP, TONE
- Phase 3: VIDEO — TAQOZ BMV360.TASK port, BMP frame loop from AHCI blocks
- Phase 4: AV-SYNC — compositor, !POST/!TVOFF, IRQ-driven audio DMA

The VIEW-SECTOR and BLIT-ROW words in Block 154 are the seeds of Phase 3.
The VSYNC-WAIT word is the timing backbone. The !POST/!TVOFF words preserve
exact TAQOZ naming so the VIDEO vocabulary can call them without change.
