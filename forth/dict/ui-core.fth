\ ============================================
\ CATALOG: UI-CORE
\ CATEGORY: gui
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ ============================================
\
\ Core widget rendering for VGA text mode.
\ Direct writes to 0xB8000. CRTC cursor.
\ Widget table, label pool, event ring.
\
\ Usage:
\   USING UI-CORE
\   5 3 S" Hello" ADD-LABEL
\   2 10 20 S" Go" ['] NOOP ADD-BUTTON
\   8 ADD-DIVIDER
\
\ ============================================

VOCABULARY UI-CORE
UI-CORE DEFINITIONS

\ ---- Widget types ----------------------
\ All constants defined outside colon defs
\ to avoid HEX/DECIMAL parse trap.
DECIMAL
1 CONSTANT WT-LABEL
2 CONSTANT WT-BUTTON
3 CONSTANT WT-DROPBOX
4 CONSTANT WT-LIST
5 CONSTANT WT-INPUT
6 CONSTANT WT-DIVIDER
7 CONSTANT WT-CARD-BEGIN
8 CONSTANT WT-CARD-END
9 CONSTANT WT-MENU-BUTTON

\ ---- Addresses -------------------------
HEX
B8000 CONSTANT VGA-BASE
200000 CONSTANT WT-BASE
202000 CONSTANT POOL-BASE
207000 CONSTANT EVT-BASE
209000 CONSTANT WT-VARS
3D4 CONSTANT CRTC-IDX
3D5 CONSTANT CRTC-DAT
0E CONSTANT CRTC-HI
0F CONSTANT CRTC-LO
FF CONSTANT BYTE-MASK

\ ---- Sizes and limits ------------------
DECIMAL
80 CONSTANT VGA-COLS
25 CONSTANT VGA-ROWS
64 CONSTANT WT-ESIZE
128 CONSTANT WT-MAX
512 CONSTANT EVT-MAX
8 CONSTANT EVT-ESIZE
511 CONSTANT EVT-MASK

\ ---- Widget entry field offsets --------
0 CONSTANT WTO-TYPE
1 CONSTANT WTO-X
2 CONSTANT WTO-Y
3 CONSTANT WTO-W
4 CONSTANT WTO-H
5 CONSTANT WTO-FLAGS
6 CONSTANT WTO-LLEN
8 CONSTANT WTO-LOFF
12 CONSTANT WTO-XT
16 CONSTANT WTO-DWORD
20 CONSTANT WTO-DW-HI

\ ---- D-word attribute bit masks ---------
1 CONSTANT DW-VISIBLE
2 CONSTANT DW-ENABLED
3 CONSTANT DW-VIS-ENA

\ ---- Characters and VGA attributes -----
32 CONSTANT CH-SPACE
45 CONSTANT CH-DASH
91 CONSTANT CH-LBRACK
93 CONSTANT CH-RBRACK
7 CONSTANT ATTR-NORM
112 CONSTANT ATTR-INV

\ ========================================
\ Colon defs below. Only named constants
\ and 0-9 (base-independent) are used
\ inside definitions.
\ ========================================
HEX

\ ---- State variables -------------------
\ Fixed addresses so reloading UI-CORE
\ does not create duplicate cells.
: WT-COUNT ( -- a ) WT-VARS ;
: WT-FOCUS ( -- a ) WT-VARS 4 + ;
: POOL-POS ( -- a ) WT-VARS 8 + ;
: EVT-HEAD ( -- a ) WT-VARS 0C + ;
: EVT-TAIL ( -- a ) WT-VARS 10 + ;

: WT-RESET ( -- )
  0 WT-COUNT !  0 WT-FOCUS !
  0 POOL-POS !
  0 EVT-HEAD !  0 EVT-TAIL ! ;
WT-RESET

\ ---- Input value pool ------------------
\ Per-widget text buffer for INPUT widgets.
\ 64 bytes per slot, 128 slots.
\ Byte 0 = length, bytes 1-63 = data.
DECIMAL
63 CONSTANT IV-MAX
HEX
20D000 CONSTANT IV-BASE

: IV-ADDR ( idx -- addr )
  IV-MAX 1 + * IV-BASE + ;
: IV-GET ( idx -- addr len )
  IV-ADDR DUP C@ SWAP 1+ SWAP ;
: IV-SET ( addr len idx -- )
  IV-ADDR SWAP DUP IV-MAX > IF
    DROP IV-MAX
  THEN
  2DUP C! 1+ SWAP CMOVE ;
: IV-CLEAR ( idx -- )
  IV-ADDR 0 SWAP C! ;

\ ---- VGA text mode ---------------------

: VGA-AT ( col row -- vga-addr )
  VGA-COLS * + 2 * VGA-BASE + ;

VARIABLE VPC-TMP
: VGA-PUTC ( ch attr col row -- )
  VGA-AT VPC-TMP !
  VPC-TMP @ 1+ C!
  VPC-TMP @ C! ;

: VGA-CLS ( -- )
  VGA-ROWS 0 DO
    VGA-COLS 0 DO
      CH-SPACE ATTR-NORM I J VGA-PUTC
    LOOP
  LOOP ;

: CURSOR-AT ( col row -- )
  VGA-COLS * +
  DUP BYTE-MASK AND
  CRTC-LO CRTC-IDX OUTB
  CRTC-DAT OUTB
  8 RSHIFT
  CRTC-HI CRTC-IDX OUTB
  CRTC-DAT OUTB ;

\ ---- Widget entry access ---------------

: W-ADDR ( -- a ) WT-VARS 14 + ;

: WT-ALLOC ( -- flag )
  WT-COUNT @ WT-MAX < IF
    WT-COUNT @ WT-ESIZE *
    WT-BASE + W-ADDR !
    1 WT-COUNT +!  TRUE
  ELSE  FALSE  THEN ;

: W-TYPE! ( n -- )
  W-ADDR @ WTO-TYPE + C! ;
: W-X! ( n -- )
  W-ADDR @ WTO-X + C! ;
: W-Y! ( n -- )
  W-ADDR @ WTO-Y + C! ;
: W-W! ( n -- )
  W-ADDR @ WTO-W + C! ;
: W-FLAGS! ( n -- )
  W-ADDR @ WTO-FLAGS + C! ;
: W-LLEN! ( n -- )
  W-ADDR @ WTO-LLEN + C! ;
: W-LOFF! ( n -- )
  W-ADDR @ WTO-LOFF + ! ;
: W-XT! ( n -- )
  W-ADDR @ WTO-XT + ! ;

: W-TYPE@ ( -- n )
  W-ADDR @ WTO-TYPE + C@ ;
: W-X@ ( -- n )
  W-ADDR @ WTO-X + C@ ;
: W-Y@ ( -- n )
  W-ADDR @ WTO-Y + C@ ;
: W-W@ ( -- n )
  W-ADDR @ WTO-W + C@ ;
: W-LLEN@ ( -- n )
  W-ADDR @ WTO-LLEN + C@ ;
: W-LOFF@ ( -- n )
  W-ADDR @ WTO-LOFF + @ ;
: W-XT@ ( -- n )
  W-ADDR @ WTO-XT + @ ;

\ ---- D-word attribute access ------------
: W-DW! ( n -- )
  W-ADDR @ WTO-DWORD + ! ;
: W-DW@ ( -- n )
  W-ADDR @ WTO-DWORD + @ ;
: W-DW-HI! ( n -- )
  W-ADDR @ WTO-DW-HI + ! ;
: W-DW-HI@ ( -- n )
  W-ADDR @ WTO-DW-HI + @ ;

: SET-VISIBLE ( idx -- )
  WT-ESIZE * WT-BASE + W-ADDR !
  W-DW@ DW-VISIBLE OR W-DW! ;
: CLR-VISIBLE ( idx -- )
  WT-ESIZE * WT-BASE + W-ADDR !
  W-DW@ DW-VISIBLE INVERT AND
  W-DW! ;
: SET-ENABLED ( idx -- )
  WT-ESIZE * WT-BASE + W-ADDR !
  W-DW@ DW-ENABLED OR W-DW! ;
: CLR-ENABLED ( idx -- )
  WT-ESIZE * WT-BASE + W-ADDR !
  W-DW@ DW-ENABLED INVERT AND
  W-DW! ;
: WIDGET-VIS? ( idx -- flag )
  WT-ESIZE * WT-BASE + W-ADDR !
  W-DW@ DW-VISIBLE AND ;
: WIDGET-ENA? ( idx -- flag )
  WT-ESIZE * WT-BASE + W-ADDR !
  W-DW@ DW-ENABLED AND ;

\ ---- Label string pool -----------------

VARIABLE WL-LEN
: W-LABEL! ( addr len -- )
  DUP WL-LEN !
  POOL-POS @ W-LOFF!
  POOL-BASE POOL-POS @ +
  SWAP CMOVE
  WL-LEN @ POOL-POS +!
  WL-LEN @ W-LLEN! ;

: POOL-STR ( off len -- addr len )
  SWAP POOL-BASE + SWAP ;

\ ---- Widget ADD words ------------------

: ADD-LABEL ( x y addr len -- )
  WT-ALLOC IF
    W-LABEL!  WT-LABEL W-TYPE!
    W-Y!  W-X!
    0 W-W!  1 W-FLAGS!
    DW-VIS-ENA W-DW!  0 W-DW-HI!
  ELSE
    DROP DROP DROP DROP
  THEN ;

: ADD-BUTTON ( x y w addr len xt -- )
  WT-ALLOC IF
    W-XT!  W-LABEL!
    WT-BUTTON W-TYPE!
    W-W!  W-Y!  W-X!  1 W-FLAGS!
    DW-VIS-ENA W-DW!  0 W-DW-HI!
  ELSE
    DROP DROP DROP
    DROP DROP DROP
  THEN ;

: ADD-DIVIDER ( y -- )
  WT-ALLOC IF
    WT-DIVIDER W-TYPE!  W-Y!
    VGA-COLS W-W!  1 W-FLAGS!
    DW-VIS-ENA W-DW!  0 W-DW-HI!
  ELSE DROP THEN ;

: ADD-INPUT ( x y w addr len -- )
  WT-ALLOC IF
    W-LABEL!  WT-INPUT W-TYPE!
    W-W!  W-Y!  W-X!  1 W-FLAGS!
    DW-VIS-ENA W-DW!  0 W-DW-HI!
    WT-COUNT @ 1- IV-CLEAR
  ELSE
    DROP DROP DROP DROP DROP
  THEN ;

: ADD-DROPBOX ( x y w addr len -- )
  WT-ALLOC IF
    W-LABEL!  WT-DROPBOX W-TYPE!
    W-W!  W-Y!  W-X!  1 W-FLAGS!
    DW-VIS-ENA W-DW!  0 W-DW-HI!
  ELSE
    DROP DROP DROP DROP DROP
  THEN ;

: ADD-CARD-BG ( x y w addr len -- )
  WT-ALLOC IF
    W-LABEL!  WT-CARD-BEGIN W-TYPE!
    W-W!  W-Y!  W-X!  1 W-FLAGS!
    DW-VIS-ENA W-DW!  0 W-DW-HI!
  ELSE
    DROP DROP DROP DROP DROP
  THEN ;

: ADD-CARD-ED ( x y w -- )
  WT-ALLOC IF
    WT-CARD-END W-TYPE!
    W-W!  W-Y!  W-X!
    1 W-FLAGS!
    DW-VIS-ENA W-DW!  0 W-DW-HI!
  ELSE DROP DROP DROP THEN ;

: ADD-MENU-BTN ( addr len -- )
  WT-ALLOC IF
    W-LABEL!
    WT-MENU-BUTTON W-TYPE!
    1 W-FLAGS!
    DW-VIS-ENA W-DW!  0 W-DW-HI!
  ELSE DROP DROP THEN ;

\ ---- Rendering -------------------------

VARIABLE RW-IDX
: RW-ATTR ( -- attr )
  RW-IDX @ WT-FOCUS @ = IF
    ATTR-INV
  ELSE
    ATTR-NORM
  THEN ;

VARIABLE DA-C
VARIABLE DA-R
VARIABLE DA-A
: DRAW-AT ( addr len col row attr -- )
  DA-A !  DA-R !  DA-C !
  DUP 0 > IF
    0 DO
      DUP I + C@
      DA-A @  DA-C @ I +  DA-R @
      VGA-PUTC
    LOOP
  ELSE DROP THEN
  DROP ;

: RENDER-LABEL ( -- )
  W-LOFF@ W-LLEN@ POOL-STR
  W-X@  W-Y@  ATTR-NORM  DRAW-AT ;

VARIABLE RB-X
: RENDER-BUTTON ( -- )
  W-X@ RB-X !
  CH-LBRACK RW-ATTR
  RB-X @  W-Y@  VGA-PUTC
  W-LOFF@ W-LLEN@ POOL-STR
  RB-X @ 1 +  W-Y@
  RW-ATTR  DRAW-AT
  CH-RBRACK RW-ATTR
  RB-X @ W-LLEN@ + 1 +
  W-Y@  VGA-PUTC ;

: RENDER-DIVIDER ( -- )
  W-W@ DUP 0 > IF
    0 DO
      CH-DASH ATTR-NORM
      I  W-Y@  VGA-PUTC
    LOOP
  ELSE DROP THEN ;

VARIABLE RI-X
VARIABLE RI-IDX
VARIABLE RI-VL
: RENDER-INPUT ( -- )
  W-X@ RI-X !
  W-ADDR @ WT-BASE - WT-ESIZE /
  RI-IDX !
  RI-IDX @ IV-ADDR C@ RI-VL !
  CH-LBRACK RW-ATTR
  RI-X @  W-Y@  VGA-PUTC
  W-W@ 2 - DUP 0 > IF
    0 DO
      RI-VL @ 0 > IF
        I RI-VL @ < IF
          RI-IDX @ IV-ADDR I + 1+
          C@
        ELSE CH-SPACE THEN
      ELSE
        I W-LLEN@ < IF
          W-LOFF@ I +
          POOL-BASE + C@
        ELSE CH-SPACE THEN
      THEN
      RW-ATTR
      RI-X @ I + 1 +  W-Y@
      VGA-PUTC
    LOOP
  ELSE DROP THEN
  CH-RBRACK RW-ATTR
  RI-X @ W-W@ + 1 -  W-Y@
  VGA-PUTC ;

VARIABLE RD-X
: RENDER-DROPBOX ( -- )
  W-X@ RD-X !
  CH-LBRACK ATTR-NORM
  RD-X @  W-Y@  VGA-PUTC
  W-LOFF@ W-LLEN@ POOL-STR
  RD-X @ 1 +  W-Y@
  ATTR-NORM  DRAW-AT
  W-W@ 2 - W-LLEN@ - DUP 0 > IF
    0 DO
      CH-SPACE ATTR-NORM
      RD-X @ W-LLEN@ + 1 + I +
      W-Y@  VGA-PUTC
    LOOP
  ELSE DROP THEN
  118 ATTR-NORM
  RD-X @ W-W@ + 2 -  W-Y@  VGA-PUTC
  CH-RBRACK ATTR-NORM
  RD-X @ W-W@ + 1 -  W-Y@  VGA-PUTC ;

: RENDER-CARD-BG ( -- )
  43 ATTR-NORM W-X@ W-Y@ VGA-PUTC
  W-W@ 2 - DUP 0 > IF
    0 DO
      I W-LLEN@ 4 + < IF
        I 2 < IF CH-DASH
        ELSE
          I 2 - W-LLEN@ < IF
            W-LOFF@ I 2 - +
            POOL-BASE + C@
          ELSE
            I W-LLEN@ 2 + = IF
              CH-DASH
            ELSE CH-DASH THEN
          THEN
        THEN
      ELSE CH-DASH THEN
      ATTR-NORM
      W-X@ I + 1 +  W-Y@  VGA-PUTC
    LOOP
  ELSE DROP THEN
  43 ATTR-NORM
  W-X@ W-W@ + 1 -  W-Y@  VGA-PUTC ;

: RENDER-CARD-ED ( -- )
  43 ATTR-NORM W-X@ W-Y@ VGA-PUTC
  W-W@ 2 - DUP 0 > IF
    0 DO
      CH-DASH ATTR-NORM
      W-X@ I + 1 +  W-Y@  VGA-PUTC
    LOOP
  ELSE DROP THEN
  43 ATTR-NORM
  W-X@ W-W@ + 1 -  W-Y@  VGA-PUTC ;

: RENDER-WIDGET ( idx -- )
  DUP RW-IDX !
  WT-ESIZE * WT-BASE + W-ADDR !
  W-DW@ DW-VISIBLE AND 0= IF
    EXIT THEN
  W-TYPE@
  DUP WT-LABEL = IF
    DROP RENDER-LABEL EXIT THEN
  DUP WT-BUTTON = IF
    DROP RENDER-BUTTON EXIT THEN
  DUP WT-DIVIDER = IF
    DROP RENDER-DIVIDER EXIT THEN
  DUP WT-INPUT = IF
    DROP RENDER-INPUT EXIT THEN
  DUP WT-DROPBOX = IF
    DROP RENDER-DROPBOX EXIT THEN
  DUP WT-CARD-BEGIN = IF
    DROP RENDER-CARD-BG EXIT THEN
  DUP WT-CARD-END = IF
    DROP RENDER-CARD-ED EXIT THEN
  DROP ;

\ ---- Event ring buffer -----------------

: EVENT-PUSH ( type sub -- )
  EVT-HEAD @ EVT-ESIZE *
  EVT-BASE + DUP
  ROT SWAP C!  1 + C!
  EVT-HEAD @ 1 +
  EVT-MASK AND EVT-HEAD ! ;

: EVENT-POP ( -- type sub | 0 0 )
  EVT-HEAD @ EVT-TAIL @ = IF
    0 0 EXIT THEN
  EVT-TAIL @ EVT-ESIZE *
  EVT-BASE + DUP
  C@ SWAP 1 + C@
  EVT-TAIL @ 1 +
  EVT-MASK AND EVT-TAIL ! ;

\ ---- Diagnostic dump --------------------

: WIDGET-DUMP ( -- )
  ." Widgets: " WT-COUNT @ . CR
  WT-COUNT @ DUP 0 > IF
    0 DO
      I WT-ESIZE * WT-BASE +
      W-ADDR !
      I . ." t=" W-TYPE@ .
      ." x=" W-X@ .
      ." y=" W-Y@ .
      ." w=" W-W@ .
      ." l=" W-LOFF@ W-LLEN@
      POOL-STR TYPE CR
    LOOP
  ELSE DROP THEN ;

FORTH DEFINITIONS
DECIMAL
