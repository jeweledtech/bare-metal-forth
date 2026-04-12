\ ============================================
\ CATALOG: GRAPHICS
\ CATEGORY: video
\ PLATFORM: x86
\ SOURCE: hand-written
\ PORTS: 0x3C7-0x3C9, 0x3DA
\ MMIO: 0xA0000-0xAFA00
\ CONFIDENCE: high
\ REQUIRES: VGA-GRAPHICS ( VBE! VBE@ VGA-MODE! )
\ ============================================
\
\ VGA Mode 13h pixel graphics + DAC palette
\ + VSYNC + TAQOZ-compatible A/V words.
\
\ Bochs VBE (higher res) via VGA-GRAPHICS.
\
\ Usage:
\   USING GRAPHICS
\   0 CLS-GFX
\   A 14 F PLOT
\   GRAY-PALETTE
\   TEST-PATTERN
\
\ ============================================

VOCABULARY GRAPHICS
GRAPHICS DEFINITIONS
ALSO VGA-GRAPHICS
HEX

\ ============================================
\ Mode 13h constants
\ ============================================
A0000 CONSTANT GFX-FB
FA00  CONSTANT GFX-FB-SIZE
\ 320*200 = 64000 = FA00h
DECIMAL
320 CONSTANT GFX-WIDTH
200 CONSTANT GFX-HEIGHT
HEX

VARIABLE GFX-ACTIVE
0 GFX-ACTIVE !

\ ============================================
\ VGA DAC palette port constants
\ ============================================
3C7 CONSTANT VGA-DAC-RDIDX
3C8 CONSTANT VGA-DAC-WRIDX
3C9 CONSTANT VGA-DAC-DATA
3DA CONSTANT VGA-STATUS1

\ ============================================
\ Mode 13h pixel address
\ ============================================
\ GFX-ADDR ( x y -- addr )
\ = base + y * 320 + x
: GFX-ADDR ( x y -- addr )
    GFX-WIDTH * + GFX-FB +
;

\ ============================================
\ Pixel primitives
\ ============================================

VARIABLE PL-C
: PLOT ( x y color -- )
    PL-C ! GFX-ADDR PL-C @ SWAP C!
;

VARIABLE HL-C
: HLINE ( x y len color -- )
    HL-C !
    -ROT GFX-ADDR SWAP HL-C @ FILL
;

VARIABLE VL-C
: VLINE ( x y len color -- )
    VL-C ! SWAP
    DUP ROT + SWAP DO
        DUP I VL-C @ PLOT
    LOOP DROP
;

: CLS-GFX ( color -- )
    GFX-FB GFX-FB-SIZE ROT FILL
;

\ ============================================
\ Rectangle words
\ ============================================

VARIABLE RX  VARIABLE RY
VARIABLE RW  VARIABLE RH
VARIABLE RC

: FILL-RECT ( x y w h color -- )
    RC ! RH ! RW ! RY ! RX !
    RH @ 0 DO
        RX @ RY @ I +
        RW @ RC @ HLINE
    LOOP
;

: RECT ( x y w h color -- )
    RC ! RH ! RW ! RY ! RX !
    \ top edge
    RX @ RY @ RW @ RC @ HLINE
    \ bottom edge
    RX @ RY @ RH @ 1- +
    RW @ RC @ HLINE
    \ left edge
    RX @ RY @ RH @ RC @ VLINE
    \ right edge
    RX @ RW @ 1- +
    RY @ RH @ RC @ VLINE
;

\ ============================================
\ BMP sector blit (TAQOZ pattern)
\ ============================================

: BLIT-ROW ( baddr row -- )
    GFX-WIDTH * GFX-FB +
    GFX-WIDTH CMOVE
;

: VIEW-SECTOR ( blk# -- )
    BLOCK 0 BLIT-ROW
;

\ ============================================
\ Palette words (VGA DAC, 6-bit RGB)
\ ============================================
\ DAC expects R, G, B in that order after
\ setting write index. Stack has r on bottom,
\ b on top — must rearrange.

: PAL! ( r g b index -- )
    VGA-DAC-WRIDX OUTB
    ROT VGA-DAC-DATA OUTB
    SWAP VGA-DAC-DATA OUTB
    VGA-DAC-DATA OUTB
;

: PAL@ ( index -- r g b )
    VGA-DAC-RDIDX OUTB
    VGA-DAC-DATA INB
    VGA-DAC-DATA INB
    VGA-DAC-DATA INB
;

\ 256-entry linear grayscale
\ I ranges 0-255, >>2 gives 0-63 (6-bit DAC)
: GRAY-PALETTE ( -- )
    DECIMAL
    256 0 DO
        I 4 /
        DUP DUP I PAL!
    LOOP
    HEX
;

\ ============================================
\ VSYNC — vertical retrace wait
\ ============================================
\ Port 3DA bit 3 = vertical retrace active.
\ Counted loop with LEAVE as timeout guard
\ (QEMU 3DA emulation can be imprecise).

: VSYNC-WAIT ( -- )
    FFFF 0 DO
        VGA-STATUS1 INB
        8 AND IF LEAVE THEN
    LOOP
;

\ Frame timing constant (60Hz = 16ms)
DECIMAL
16 CONSTANT VSYNC-MS
HEX

\ ============================================
\ TAQOZ-compatible arm/disarm words
\ ============================================

: !POST ( -- ) 1 GFX-ACTIVE ! ;

: !TVOFF ( -- )
    0 GFX-ACTIVE !
    0 CLS-GFX
;

\ ============================================
\ VBE convenience wrapper
\ ============================================
\ Delegates to VGA-GRAPHICS vocab's VGA-MODE!

: VBE-INIT-MODE ( w h bpp -- )
    VGA-MODE!
    2 GFX-ACTIVE !
;

: VBE-TEXT ( -- )
    VGA-TEXT
    0 GFX-ACTIVE !
;

\ ============================================
\ Demo words
\ ============================================

: TEST-PATTERN ( -- )
    !POST
    DECIMAL
    200 0 DO
        320 0 DO
            I J + FF AND
            I J ROT PLOT
        LOOP
    LOOP
    HEX
;

: GRADIENT ( -- )
    !POST
    DECIMAL
    200 0 DO
        320 0 DO
            I FF AND
            I J ROT PLOT
        LOOP
    LOOP
    HEX
;

: PIXEL-DEMO ( -- )
    ." Pixel demo..." CR
    GRAY-PALETTE
    TEST-PATTERN
    ." Press key..." CR
    KEY DROP
    VBE-TEXT
;

PREVIOUS FORTH DEFINITIONS
DECIMAL
