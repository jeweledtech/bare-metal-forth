\ ============================================
\ CATALOG: WINDOW
\ CATEGORY: gui
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ REQUIRES: HAL
\ REQUIRES: UI-CORE ( RENDER-WIDGET WT-COUNT WT-FOCUS )
\ REQUIRES: UI-EVENTS ( FOCUS-IDX HANDLE-KEY QUIT-FLAG )
\ REQUIRES: HARDWARE ( PHYS-ALLOC )
\ REQUIRES: DIALOG ( DL-DRAW DR-KEY DL-KEY )
\ ============================================
\
\ Windows: regions of the 80x25 text screen,
\ in a table read only through these words.
\ Window 0 is the console; its region is the
\ kernel's band (CON-REGION), full width.
\ Private DESIGN_WINDOW_FOCUS, steps 1-3a.
\ Ctrl+W (FOCUS-HOOK) runs each window
\ with a key handler in id order, each
\ until it reads Ctrl+W; then the console.
\ A window's form is copied out of the
\ live table when it loses the keys and
\ back when it gets them.
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
\   id WIN-FORM!      the loaded form is
\                     id's, kept per window
\   id WIN-DIALOG!    the same, a dialog
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

\ ---- A form per window (step 3a) -------
\ Saved: widgets, pool and events, the
\ table's cells, the INPUT slots, and the
\ focus, quit and dialog cells.
EVT-BASE EVT-MAX EVT-ESIZE * + WT-BASE -
  CONSTANT WS-AN
24 CONSTANT WS-VN
IV-MAX 1+ WT-MAX * CONSTANT WS-IN
ALSO DIALOG
CREATE WS-VARS
  FOCUS-IDX , QUIT-FLAG , DL-ITEMS ,
  DL-LOST , DL-WTC , DL-POS , DL-OPEN ,
  DL-HL , DL-AT , DR-ID , DR-DONE ,
PREVIOUS
11 CONSTANT WS-CELLS
WS-AN WS-VN + WS-IN + WS-CELLS CELLS +
  CONSTANT WS-SIZE
\ Per window: its save area, 0 none.
CREATE WIN-SAVE WIN-MAX CELLS ALLOT
WIN-SAVE WIN-MAX CELLS 0 FILL
: WIN-AREA ( id -- a|0 ) CELLS WIN-SAVE + @ ;

VARIABLE WS-P
: WS-CELLS@ ( -- )
  WS-CELLS 0 DO
    WS-VARS I CELLS + @ @  WS-P @ I CELLS + !
  LOOP ;
: WS-CELLS! ( -- )
  WS-CELLS 0 DO
    WS-P @ I CELLS + @  WS-VARS I CELLS + @ !
  LOOP ;
\ live table -> area
: WS-OUT ( a -- )
  WS-P !
  WT-BASE WS-P @ WS-AN CMOVE  WS-AN WS-P +!
  WT-VARS WS-P @ WS-VN CMOVE  WS-VN WS-P +!
  IV-BASE WS-P @ WS-IN CMOVE  WS-IN WS-P +!
  WS-CELLS@ ;
\ area -> live table
: WS-IN! ( a -- )
  WS-P !
  WS-P @ WT-BASE WS-AN CMOVE  WS-AN WS-P +!
  WS-P @ WT-VARS WS-VN CMOVE  WS-VN WS-P +!
  WS-P @ IV-BASE WS-IN CMOVE  WS-IN WS-P +!
  WS-CELLS! ;

\ ---- The cycle (step 3a) ----------------
\ A handler that leaves on Ctrl+W goes on
\ to the next window; one that leaves for
\ any other reason (a form's quit) ends
\ the cycle at the console.
VARIABLE WIN-GO
\ The next window after id with a key
\ handler; 0 (the console) if none.
: WIN-NEXT ( id -- id' )
  BEGIN 1+ DUP WIN-COUNT @ < WHILE
    DUP WIN-HANDLER IF EXIT THEN
  REPEAT DROP 0 ;
: WIN-RUN ( id -- )
  DUP WIN-CUR !  -1 WIN-GO !
  DUP WIN-AREA ?DUP IF WS-IN! THEN
  DUP WIN-HANDLER EXECUTE
  WIN-AREA ?DUP IF WS-OUT THEN ;
\ FOCUS-HOOK's xt: WIN-FOCUS's window,
\ else the first with a handler, then
\ each next on Ctrl+W, then the console.
: WIN-SWITCH ( -- )
  WIN-TARGET @ ?DUP 0= IF 0 WIN-NEXT THEN
  0 WIN-TARGET !
  BEGIN ?DUP WHILE
    DUP WIN-RUN
    WIN-GO @ IF WIN-NEXT ELSE DROP 0 THEN
  REPEAT
  0 WIN-CUR ! ;

\ Ctrl+W reaches window id and runs xt.
: WIN-KEYS! ( xt id -- )
  WIN-ID DUP 0= ABORT" WINDOW: the console's keys are its own"
  CELLS WIN-KEYS + !
  ['] WIN-SWITCH FOCUS-HOOK ! ;

\ Switch to window id now, as Ctrl+W.
: WIN-FOCUS ( id -- )
  WIN-ID DUP 0= IF DROP EXIT THEN
  DUP WIN-HANDLER 0= ABORT" WINDOW: no key handler"
  WIN-TARGET !  FOCUS-SWITCH DROP ;

\ The live form in the active window: its
\ region cleared, never the screen, so
\ the console band survives.
: WIN-DRAW ( -- )
  WIN-ACTIVE WIN-CLS
  FOCUS-IDX @ WT-FOCUS !
  WT-COUNT @ 0 > IF
    WT-COUNT @ 0 DO I RENDER-WIDGET LOOP
  THEN ;

\ A form as a window's handler. Ctrl+W
\ goes on; the form's quit ends the cycle.
: WIN-FORM-KEYS ( -- )
  0 QUIT-FLAG !
  BEGIN
    WIN-DRAW
    KEY DUP WIN-SWITCH-KEY = IF DROP EXIT THEN
    HANDLE-KEY  QUIT-FLAG @
  UNTIL  0 WIN-GO ! ;

ALSO DIALOG
\ A dialog as a window's handler: DIALOG-
\ RUN's loop, its own region, no PAGE. An
\ open drop-down stays open across Ctrl+W.
: WIN-DIALOG-KEYS ( -- )
  BEGIN
    WIN-DRAW  DL-DRAW
    KEY DUP WIN-SWITCH-KEY = IF DROP EXIT THEN
    DL-OPEN @ 0< IF DR-KEY ELSE DL-KEY THEN
    DR-DONE @
  UNTIL  0 WIN-GO ! ;

\ ---- Giving a window the loaded form ----
\ Refused, by name, when a widget, or a
\ drop-down's open list, would pass the
\ window's edge (absolute cells, step 3a).
VARIABLE WR-L  VARIABLE WR-T
VARIABLE WR-R  VARIABLE WR-B
VARIABLE WR-OK
: WR-CELL ( x y -- )
  DUP WR-T @ < OVER WR-B @ < 0= OR
  ROT DUP WR-L @ < SWAP WR-R @ < 0= OR
  OR IF 0 WR-OK ! THEN DROP ;
: WIN-HOLDS? ( id -- flag )
  WIN-REGION >R >R  2DUP WR-T ! WR-L !
  SWAP R> + WR-R !  R> + WR-B !
  -1 WR-OK !
  WT-COUNT @ DUP 0 > IF 0 DO
    I WT-ESIZE * WT-BASE + W-ADDR !
    W-X@ W-Y@ WR-CELL
    W-X@ W-W@ + 1- 0 MAX  W-Y@ W-H@ 1 MAX + 1-
      WR-CELL
    W-TYPE@ WT-DROPBOX = IF
      W-X@  W-Y@ W-ADDR @ DLW-N + C@
      24 W-Y@ - MIN 0 MAX +  WR-CELL
    THEN
  LOOP ELSE DROP THEN  WR-OK @ ;
PREVIOUS

ALSO HARDWARE
\ id's save area, taken once.
: WIN-AREA! ( id -- a )
  DUP WIN-AREA ?DUP IF NIP EXIT THEN
  WS-SIZE PHYS-ALLOC
  DUP 0= ABORT" WINDOW: no memory for the form"
  DUP ROT CELLS WIN-SAVE + ! ;
PREVIOUS

: WIN-TAKE ( xt id -- )
  WIN-ID DUP 0= ABORT" WINDOW: the console's form is its own"
  DUP WIN-HOLDS? 0= ABORT" WINDOW: form outside window"
  \ area first: a refusal leaves the window as it was
  DUP WIN-AREA! >R  WIN-KEYS!  R> WS-OUT ;

\ The loaded form becomes id's.
: WIN-FORM! ( id -- )
  0 NEXT-FOCUSABLE DUP 0< IF DROP 0 THEN
  FOCUS-IDX !  ['] WIN-FORM-KEYS SWAP WIN-TAKE ;

ALSO DIALOG
\ The loaded dialog becomes id's: focus
\ on its first control, list closed.
: WIN-DIALOG! ( id -- )
  0 DR-ID !  FALSE DR-DONE !  -1 DL-OPEN !
  0 NEXT-FOCUSABLE DUP 0< IF DROP 0 THEN
  FOCUS-IDX !
  ['] WIN-DIALOG-KEYS SWAP WIN-TAKE ;
PREVIOUS

PREVIOUS PREVIOUS PREVIOUS
FORTH DEFINITIONS
DECIMAL
