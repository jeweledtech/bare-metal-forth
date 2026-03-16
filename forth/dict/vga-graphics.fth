\ ============================================
\ CATALOG: VGA-GRAPHICS
\ CATEGORY: video
\ PLATFORM: x86
\ SOURCE: hand-written
\ PORTS: 0x01CE, 0x01CF
\ MMIO: LFB via PCI BAR0
\ CONFIDENCE: high
\ REQUIRES: PCI-ENUM ( PCI-FIND PCI-BAR@ )
\ ============================================
\
\ Bochs VBE graphics driver for QEMU.
\ Sets video modes, draws to LFB.
\
\ Usage:
\   USING VGA-GRAPHICS
\   DECIMAL 640 480 32 VGA-MODE!
\   HEX FF0000 64 64 VGA-PIXEL!
\   VGA-TEXT
\
\ ============================================

VOCABULARY VGA-GRAPHICS
VGA-GRAPHICS DEFINITIONS
ALSO PCI-ENUM
HEX

\ ---- VBE I/O Ports ----
01CE CONSTANT VBE-INDEX
01CF CONSTANT VBE-DATA

\ ---- VBE Register Indices ----
0 CONSTANT VBE-ID
1 CONSTANT VBE-XRES
2 CONSTANT VBE-YRES
3 CONSTANT VBE-BPP
4 CONSTANT VBE-ENABLE
9 CONSTANT VBE-Y-OFF

\ ---- Enable bits ----
01 CONSTANT VBE-ON
02 CONSTANT VBE-LFB

\ ---- State ----
VARIABLE VGA-LFB
VARIABLE VGA-W
VARIABLE VGA-H
VARIABLE VGA-DEPTH
VARIABLE VGA-PITCH

\ ---- VBE register access ----
: VBE! ( val index -- )
    VBE-INDEX OUTW
    VBE-DATA OUTW
;
: VBE@ ( index -- val )
    VBE-INDEX OUTW
    VBE-DATA INW
;

\ ---- Find LFB from PCI VGA device ----
: VGA-FIND-LFB ( -- addr )
    1234 1111 PCI-FIND
    0= IF E0000000 EXIT THEN
    0 PCI-BAR@
    FFFFFFF0 AND
;

\ ---- Read VBE version ----
: VBE-VER ( -- ver )
    VBE-ID VBE@
;

\ ---- Set graphics mode ----
: VGA-MODE! ( width height bpp -- )
    VGA-DEPTH !
    VGA-H !
    VGA-W !
    VGA-W @ VGA-DEPTH @
    3 RSHIFT * VGA-PITCH !
    VGA-FIND-LFB VGA-LFB !
    0 VBE-ENABLE VBE!
    VGA-W @ VBE-XRES VBE!
    VGA-H @ VBE-YRES VBE!
    VGA-DEPTH @ VBE-BPP VBE!
    VBE-ON VBE-LFB OR
    VBE-ENABLE VBE!
;

\ ---- Return to text mode ----
: VGA-TEXT ( -- )
    0 VBE-ENABLE VBE!
;

\ ---- Pixel address ----
: VGA-PADDR ( x y -- addr )
    VGA-PITCH @ *
    SWAP VGA-DEPTH @
    3 RSHIFT * +
    VGA-LFB @ +
;

\ ---- Set pixel (32-bit color) ----
: VGA-PIXEL! ( color x y -- )
    VGA-PADDR !
;

\ ---- Horizontal line ----
VARIABLE HL-LEN
: VGA-HLINE ( color x y len -- )
    HL-LEN !
    VGA-PADDR
    HL-LEN @ 0 DO
        2DUP !
        SWAP 4 + SWAP
    LOOP
    2DROP
;

\ ---- Clear screen ----
: VGA-CLEAR ( color -- )
    VGA-LFB @
    VGA-H @ VGA-PITCH @ *
    4 / 0 DO
        2DUP !
        SWAP 4 + SWAP
    LOOP
    2DROP
;

\ ---- Status ----
: VGA-INFO ( -- )
    ." VBE ver: " VBE-VER . CR
    ." LFB: " VGA-LFB @ . CR
    ." Mode: " VGA-W @ .
    ." x" VGA-H @ .
    ." x" VGA-DEPTH @ . CR
;

PREVIOUS FORTH DEFINITIONS
DECIMAL
