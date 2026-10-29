\ ============================================
\ CATALOG: WINDOW
\ CATEGORY: gui
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ REQUIRES: HAL
\ ============================================
\
\ Windows: regions of the 80x25 text screen,
\ in a table read only through these words.
\ Window 0 is the console; its region is the
\ kernel's band (CON-REGION), full width.
\ Private DESIGN_WINDOW_FOCUS, step 1.
\
\ Usage:
\   S" WINDOW" LOAD-VOCAB  ALSO WINDOW
\   8 WIN-CONSOLE    console in rows 17-24
\   25 WIN-CONSOLE   the whole screen again
\   0 0 80 17 WIN-NEW   ( -- id )
\   col row id WIN-AT   ( -- addr )
\   id WIN-CLS
\
\ ============================================

VOCABULARY WINDOW
WINDOW DEFINITIONS
ALSO HAL
DECIMAL

8 CONSTANT WIN-MAX
80 CONSTANT WIN-COLS
25 CONSTANT WIN-ROWS
\ Per window: left, top, width, height.
CREATE WIN-TABLE WIN-MAX 4 * CELLS ALLOT
VARIABLE WIN-COUNT  1 WIN-COUNT !

: WIN-ENTRY ( id -- addr ) 4 * CELLS WIN-TABLE + ;
: WIN-ID ( id -- id )
  DUP 0< OVER WIN-COUNT @ < 0= OR
  ABORT" WINDOW: no such window" ;

\ ---- The console, window 0 --------------
\ The bottom band, rows high; 25 is the
\ whole screen. The kernel refuses fewer
\ than 3 rows (CON-REGION).
: WIN-CONSOLE ( rows -- )
  WIN-ROWS OVER - SWAP CON-REGION
  0= ABORT" WINDOW: console band is 3 to 25 rows" ;

\ ---- The table ---------------------------
: WIN-REGION ( id -- l t w h )
  WIN-ID DUP 0= IF
    DROP 0 CON-REGION@ WIN-COLS SWAP EXIT
  THEN
  WIN-ENTRY DUP @ SWAP CELL+ DUP @ SWAP
  CELL+ DUP @ SWAP CELL+ @ ;

VARIABLE WF-L  VARIABLE WF-T
VARIABLE WF-W  VARIABLE WF-H
\ True when the region is on the screen and
\ at least one cell.
: WIN-FITS ( l t w h -- flag )
  WF-H ! WF-W ! WF-T ! WF-L !
  WF-L @ 0<  WF-T @ 0< OR
  WF-W @ 1 < OR  WF-H @ 1 < OR
  WF-L @ WF-W @ + WIN-COLS > OR
  WF-T @ WF-H @ + WIN-ROWS > OR  0= ;

: WIN-NEW ( l t w h -- id )
  2OVER 2OVER WIN-FITS
  0= ABORT" WINDOW: region off the screen"
  WIN-COUNT @ WIN-MAX < 0= ABORT" WINDOW: table full"
  WIN-COUNT @ WIN-ENTRY >R
  R@ 3 CELLS + !  R@ 2 CELLS + !
  R@ CELL+ !  R> !
  WIN-COUNT @  1 WIN-COUNT +! ;

\ ---- Cells -------------------------------
VARIABLE WA-L  VARIABLE WA-T
\ The screen cell at col row of the window;
\ outside it is refused.
: WIN-AT ( col row id -- addr )
  WIN-REGION SWAP >R >R WA-T ! WA-L !
  DUP 0< OVER R> < 0= OR
  ABORT" WINDOW: row outside window"
  SWAP DUP 0< OVER R> < 0= OR
  ABORT" WINDOW: column outside window"
  WA-L @ +  SWAP WA-T @ +  WIN-COLS * +
  2 * FB-BASE + ;

\ Window 0: PAGE (the band). Others: blanks,
\ light grey on black, then FB-FLUSH.
VARIABLE WC-ID
: WIN-CLS ( id -- )
  DUP 0= IF DROP PAGE EXIT THEN
  DUP WC-ID !  WIN-REGION ROT DROP ROT DROP
  0 DO
    0 I WC-ID @ WIN-AT
    OVER 0 DO 1824 OVER I 2 * + W! LOOP DROP
  LOOP DROP  FB-FLUSH ;

PREVIOUS
FORTH DEFINITIONS
DECIMAL
