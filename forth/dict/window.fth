\ ============================================
\ CATALOG: WINDOW
\ CATEGORY: gui
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ REQUIRES: HAL
\ REQUIRES: UI-CORE ( RENDER-WIDGET WT-COUNT WT-FOCUS )
\ REQUIRES: UI-EVENTS ( FOCUS-IDX HANDLE-KEY QUIT-FLAG )
\ ============================================
\
\ Windows: regions of the 80x25 text screen,
\ in a table read only through these words.
\ Window 0 is the console; its region is the
\ kernel's band (CON-REGION), full width.
\ Private DESIGN_WINDOW_FOCUS, steps 1-2.
\ Ctrl+W (FOCUS-HOOK) runs the target
\ window's key handler until it reads
\ Ctrl+W again; then the console.
\
\ Usage:
\   S" WINDOW" LOAD-VOCAB  ALSO WINDOW
\   8 WIN-CONSOLE    console in rows 17-24
\   25 WIN-CONSOLE   the whole screen again
\   0 0 80 17 WIN-NEW   ( -- id )
\   col row id WIN-AT   ( -- addr )
\   id WIN-CLS
\   xt id WIN-KEYS!   Ctrl+W runs xt
\   ' WIN-FORM-KEYS id WIN-KEYS!  a form
\   id WIN-FOCUS      switch to id now
\
\ ============================================

VOCABULARY WINDOW
WINDOW DEFINITIONS
ALSO HAL
ALSO UI-CORE
ALSO UI-EVENTS
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

\ ---- Keys and focus (step 2) ------------
\ Per window: its key handler xt, 0 none.
CREATE WIN-KEYS WIN-MAX CELLS ALLOT
WIN-KEYS WIN-MAX CELLS 0 FILL
VARIABLE WIN-CUR     0 WIN-CUR !
VARIABLE WIN-TARGET  0 WIN-TARGET !
23 CONSTANT WIN-SWITCH-KEY  \ Ctrl+W

\ The window that owns the keys now: 0
\ unless a switch runs. An ABORT in a
\ handler skips WIN-SWITCH's reset, but
\ clears the kernel's FOCUS-BUSY.
: WIN-ACTIVE ( -- id )
  FOCUS-BUSY C@ IF WIN-CUR @ ELSE 0 THEN ;
: WIN-HANDLER ( id -- xt ) CELLS WIN-KEYS + @ ;

\ FOCUS-HOOK's xt: run the target's
\ handler as the active window.
: WIN-SWITCH ( -- )
  WIN-TARGET @ ?DUP 0= IF EXIT THEN
  DUP WIN-CUR !  WIN-HANDLER EXECUTE
  0 WIN-CUR ! ;

\ Ctrl+W goes to window id and runs xt.
: WIN-KEYS! ( xt id -- )
  WIN-ID DUP 0= ABORT" WINDOW: the console's keys are its own"
  DUP WIN-TARGET !  CELLS WIN-KEYS + !
  ['] WIN-SWITCH FOCUS-HOOK ! ;

\ Switch to window id now, as Ctrl+W.
: WIN-FOCUS ( id -- )
  WIN-ID DUP 0= IF DROP EXIT THEN
  DUP WIN-HANDLER 0= ABORT" WINDOW: no key handler"
  WIN-TARGET !  FOCUS-SWITCH DROP ;

\ A form as a window's handler: its own
\ region cleared, never the screen, so
\ the console band survives. Ctrl+W or
\ the form's quit leaves.
: WIN-FORM-KEYS ( -- )
  0 QUIT-FLAG !
  BEGIN
    WIN-ACTIVE WIN-CLS
    FOCUS-IDX @ WT-FOCUS !
    WT-COUNT @ 0 > IF
      WT-COUNT @ 0 DO I RENDER-WIDGET LOOP
    THEN
    KEY DUP WIN-SWITCH-KEY = IF DROP EXIT THEN
    HANDLE-KEY  QUIT-FLAG @
  UNTIL ;

PREVIOUS PREVIOUS PREVIOUS
FORTH DEFINITIONS
DECIMAL
