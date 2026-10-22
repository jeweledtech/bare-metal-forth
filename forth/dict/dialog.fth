\ ============================================
\ CATALOG: DIALOG
\ CATEGORY: gui
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ REQUIRES: UI-CORE
\ REQUIRES: UI-PARSER
\ REQUIRES: UI-EVENTS
\ ============================================
\
\ Modal dialog over a loaded form, as Win32
\ DialogBox: returns the control ID of the
\ button that ended it (BUTTON: x y w "l" id,
\ UI-PARSER's WTO-CID), IDCANCEL on Esc.
\ Tab moves focus, Enter on a button ends.
\ On exit PAGE clears the screen and puts
\ the console cursor at 0,0, so the console
\ never scrolls a stale form.
\
\ Drop-down items: ITEM: "text" lines right
\ after a DROPBOX: line. UI-PARSER's
\ PROCESS-LINE calls DL-HOOK by name after
\ every line while DIALOG is loaded, so load
\ DIALOG before FORM-LOAD. On a focused
\ DROPBOX with items Enter opens the list;
\ Space and Backspace move; Enter chooses;
\ Esc closes.
\
\ Usage:
\   S" DIALOG" LOAD-VOCAB  ALSO DIALOG
\   ( a form loaded with FORM-LOAD )
\   DIALOG-RUN .
\
\ ============================================

VOCABULARY DIALOG
DIALOG DEFINITIONS
ALSO UI-CORE
ALSO UI-PARSER
ALSO UI-EVENTS

DECIMAL
2 CONSTANT IDCANCEL

\ ---- Drop-down items -------------------
\ In a DROPBOX's widget entry: item count,
\ selected (index+1, 0 none), top row shown,
\ first item's pool offset. An item in the
\ pool: a length byte, then the text.
28 CONSTANT DLW-N
29 CONSTANT DLW-SEL
30 CONSTANT DLW-TOP
32 CONSTANT DLW-FIRST
255 CONSTANT DL-NMAX

VARIABLE DL-ITEMS
VARIABLE DL-LOST
VARIABLE DL-WTC
VARIABLE DL-POS
VARIABLE DL-OPEN
VARIABLE DL-HL
\ The DROPBOX an ITEM line may join: set by
\ the line that built it, cleared by any
\ other line that is not an ITEM.
VARIABLE DL-AT
-1 DL-AT !
-1 DL-WTC !
-1 DL-OPEN !

: DL-WA ( idx -- addr )
  WT-ESIZE * WT-BASE + ;

\ Item i of the DROPBOX at widget addr wa.
: DL-IT ( wa i -- addr len )
  SWAP DLW-FIRST + @ POOL-BASE + SWAP
  DUP 0 > IF
    0 DO DUP C@ 1 + + LOOP
  ELSE DROP THEN
  DUP 1 + SWAP C@ ;

\ Equal text; length 0 never enters a loop.
: DL-SAME? ( a1 n1 a2 n2 -- flag )
  ROT OVER <> IF DROP 2DROP FALSE EXIT THEN
  DUP 0 = IF DROP 2DROP TRUE EXIT THEN
  0 DO
    OVER I + C@ OVER I + C@ <> IF
      2DROP FALSE UNLOOP EXIT THEN
  LOOP 2DROP TRUE ;

\ A line built widget WT-COUNT-1. The first
\ widget of a form zeroes the counters.
: DL-BUILT ( -- )
  WT-COUNT @ 1 = IF
    0 DL-ITEMS !  0 DL-LOST ! THEN
  -1 DL-AT !
  WT-COUNT @ 1 - DL-WA
  DUP WTO-TYPE + C@ WT-DROPBOX = IF
    WT-COUNT @ 1 - DL-AT !
    0 OVER DLW-N + C!
    0 OVER DLW-SEL + C!
    0 OVER DLW-TOP + C!
    POOL-POS @ SWAP DLW-FIRST + !
  ELSE DROP THEN ;

\ ITEM: joins DL-AT's DROPBOX, else lost.
VARIABLE DA-W
VARIABLE DA-L
VARIABLE DA-A
: DL-ADD ( addr len -- )
  DA-L ! DA-A !
  DL-AT @ 0< IF 1 DL-LOST +! EXIT THEN
  DL-AT @ DL-WA DA-W !
  DA-W @ DLW-N + C@ DL-NMAX < 0= IF
    1 DL-LOST +! EXIT THEN
  DA-L @ POOL-BASE POOL-POS @ + C!
  DA-L @ 0 > IF
    DA-A @ POOL-BASE POOL-POS @ + 1 +
    DA-L @ CMOVE
  THEN
  DA-L @ 1 + POOL-POS +!
  DA-W @ W-ADDR !
  DA-W @ DLW-SEL + C@ 0 = IF
    W-LOFF@ W-LLEN@ POOL-STR DA-A @ DA-L @
    DL-SAME? IF
      DA-W @ DLW-N + C@ 1 +
      DA-W @ DLW-SEL + C!
    THEN
  THEN
  DA-W @ DLW-N + DUP C@ 1 + SWAP C!
  1 DL-ITEMS +! ;

\ Called by PROCESS-LINE after every line,
\ with the line's parse state.
: DL-HOOK ( -- )
  WT-COUNT @ PL-N @ > IF DL-BUILT
  ELSE
    S" ITEM:" P-MATCH IF P-QUOTED DL-ADD
    ELSE -1 DL-AT ! THEN
  THEN
  WT-COUNT @ DL-WTC !  POOL-POS @ DL-POS ! ;

\ Items count only for the form loaded
\ while DIALOG was (a later FORM-LOAD runs
\ DL-HOOK too, so the stamp follows it).
: DL-VALID? ( -- flag )
  WT-COUNT @ DL-WTC @ =
  POOL-POS @ DL-POS @ = AND ;

: DL-OWA ( -- wa ) DL-OPEN @ DL-WA ;
: DL-N ( -- n ) DL-OWA DLW-N + C@ ;
: DL-W@ ( off -- n ) DL-OWA + C@ ;
\ Rows shown: the items, cut at row 24.
: DL-VIS ( -- n )
  DL-N 24 WTO-Y DL-W@ - MIN 0 MAX ;

: DL-SCROLL ( -- )
  DL-OWA DLW-TOP +
  DL-HL @ OVER C@ < IF
    DL-HL @ SWAP C! EXIT THEN
  DL-HL @ OVER C@ DL-VIS + < 0= IF
    DL-HL @ DL-VIS - 1 + SWAP C! EXIT THEN
  DROP ;

: DL-TRY-OPEN ( -- )
  DL-VALID? 0= IF EXIT THEN
  FOCUS-IDX @ DL-WA
  DUP DLW-N + C@ 0 = IF DROP EXIT THEN
  DLW-SEL + C@ 1 - 0 MAX DL-HL !
  FOCUS-IDX @ DL-OPEN !
  DL-SCROLL ;

VARIABLE DD-A
VARIABLE DD-L
VARIABLE DD-AT
VARIABLE DD-R
\ Row i of the open list: | text |.
: DL-ROW ( i -- )
  DUP DLW-TOP DL-W@ +
  DUP DL-HL @ = IF ATTR-INV
  ELSE ATTR-NORM THEN DD-AT !
  DL-OWA SWAP DL-IT DD-L ! DD-A !
  WTO-Y DL-W@ 1 + + DD-R !
  CH-BAR ATTR-NORM WTO-X DL-W@ DD-R @
  VGA-PUTC
  WTO-W DL-W@ 2 - DUP 0 > IF
    0 DO
      I DD-L @ < IF DD-A @ I + C@
      ELSE CH-SPACE THEN
      DD-AT @ WTO-X DL-W@ 1 + I +
      DD-R @ VGA-PUTC
    LOOP
  ELSE DROP THEN
  CH-BAR ATTR-NORM
  WTO-X DL-W@ WTO-W DL-W@ + 1 -
  DD-R @ VGA-PUTC ;

: DL-DRAW ( -- )
  DL-OPEN @ 0< IF EXIT THEN
  DL-VIS DUP 0 > IF
    0 DO I DL-ROW LOOP
  ELSE DROP THEN ;

\ The box text becomes the item, cut to
\ w-3 so it never runs under the v].
: DL-CHOOSE ( -- )
  DL-OWA W-ADDR !
  DL-HL @ 1 + DL-OWA DLW-SEL + C!
  DL-OWA DL-HL @ DL-IT
  SWAP POOL-BASE - W-LOFF!
  W-W@ 3 - 0 MAX MIN W-LLEN! ;

: DL-NEXT ( -- )
  DL-HL @ 1 + DUP DL-N < 0= IF
    DROP 0 THEN DL-HL ! ;
: DL-PREV ( -- )
  DL-HL @ 1 - DUP 0< IF
    DROP DL-N 1 - THEN DL-HL ! ;

: DL-KEY ( key -- )
  DUP KEY-ESC = IF
    DROP -1 DL-OPEN ! EXIT THEN
  DUP KEY-ENTER = IF
    DROP DL-CHOOSE -1 DL-OPEN ! EXIT THEN
  DUP CH-SPACE = IF
    DROP DL-NEXT DL-SCROLL EXIT THEN
  IC-BS = IF DL-PREV DL-SCROLL THEN ;
HEX

VARIABLE DR-ID
VARIABLE DR-DONE

\ Control ID of the focused widget.
: DR-CID ( -- id )
  FOCUS-IDX @ WT-ESIZE * WT-BASE +
  WTO-CID + @ ;

: DR-END ( id -- )
  DR-ID !  TRUE DR-DONE ! ;

: DR-KEY ( key -- )
  DUP KEY-ESC = IF
    DROP IDCANCEL DR-END EXIT THEN
  DUP KEY-TAB = IF
    DROP FOCUS-NEXT EXIT THEN
  KEY-ENTER = IF
    FOCUSED-TYPE WT-BUTTON = IF
      DR-CID DR-END
    THEN
    FOCUSED-TYPE WT-DROPBOX = IF
      DL-TRY-OPEN
    THEN
  THEN ;

: DIALOG-RUN ( -- id )
  0 DR-ID !  FALSE DR-DONE !
  -1 DL-OPEN !
  0 NEXT-FOCUSABLE
  DUP 0 < IF DROP 0 THEN
  FOCUS-IDX !
  BEGIN
    FORM-RENDER  DL-DRAW
    KEY DL-OPEN @ 0< IF DR-KEY
    ELSE DL-KEY THEN
    DR-DONE @
  UNTIL
  PAGE  DR-ID @ ;

PREVIOUS PREVIOUS PREVIOUS
FORTH DEFINITIONS
DECIMAL
