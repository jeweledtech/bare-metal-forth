\ ============================================
\ CATALOG: UI-EVENTS
\ CATEGORY: gui
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ REQUIRES: UI-CORE
\ REQUIRES: UI-PARSER
\ ============================================
\
\ Form event loop: render, focus, dispatch.
\ FORM-RUN is the main loop (KEY-driven).
\
\ Usage:
\   USING UI-EVENTS
\   120 125 FORM-LOAD
\   FORM-RUN
\
\ ============================================

VOCABULARY UI-EVENTS
UI-EVENTS DEFINITIONS
ALSO UI-CORE
ALSO UI-PARSER

\ ---- Key constants (DECIMAL) -----------
DECIMAL
113 CONSTANT KEY-Q
27 CONSTANT KEY-ESC
9 CONSTANT KEY-TAB
13 CONSTANT KEY-ENTER
49 CONSTANT KEY-1
57 CONSTANT KEY-9
48 CONSTANT KEY-0
HEX

\ ---- Event loop state ------------------
VARIABLE QUIT-FLAG
VARIABLE FOCUS-IDX

\ ---- Render all widgets ----------------
: FORM-RENDER ( -- )
  FOCUS-IDX @ WT-FOCUS !
  VGA-CLS
  WT-COUNT @ DUP 0 > IF
    0 DO
      I RENDER-WIDGET
    LOOP
  ELSE DROP THEN ;

\ ---- Focus management ------------------
\ Focusable types: BUTTON, INPUT, DROPBOX.
: FOCUSABLE? ( type -- flag )
  DUP WT-BUTTON = IF DROP TRUE EXIT THEN
  DUP WT-INPUT = IF DROP TRUE EXIT THEN
  WT-DROPBOX = IF TRUE ELSE FALSE THEN ;

: NEXT-FOCUSABLE ( start -- idx | -1 )
  BEGIN
    DUP WT-COUNT @ < IF
      DUP WT-ESIZE * WT-BASE +
      DUP C@ FOCUSABLE? IF
        WTO-DWORD + @
        DW-VIS-ENA AND
        DW-VIS-ENA = IF
          EXIT
        THEN
      ELSE
        DROP
      THEN
      1 +  FALSE
    ELSE
      DROP -1  TRUE
    THEN
  UNTIL ;

: FOCUS-NEXT ( -- )
  FOCUS-IDX @ 1 + NEXT-FOCUSABLE
  DUP 0 < IF
    DROP 0 NEXT-FOCUSABLE
  THEN
  DUP 0 < IF DROP ELSE
    FOCUS-IDX !
  THEN ;

\ ---- Activate focused widget ----------
: ACTIVATE-FOCUS ( -- )
  FOCUS-IDX @ WT-COUNT @ < IF
    FOCUS-IDX @ WT-ESIZE *
    WT-BASE + WTO-XT + @
    DUP IF EXECUTE ELSE DROP THEN
  THEN ;

\ ---- Button shortcut 1-9 --------------
VARIABLE BA-IDX
VARIABLE BA-N
: BUTTON-ACTIVATE ( key -- )
  KEY-0 - BA-N !
  0 BA-IDX ! 0
  WT-COUNT @ DUP 0 > IF
    0 DO
      I WT-ESIZE * WT-BASE +
      DUP C@ WT-BUTTON = IF
        WTO-DWORD + @
        DW-VIS-ENA AND
        DW-VIS-ENA = IF
          1 +
          DUP BA-N @ = IF
            I BA-IDX !
          THEN
        THEN
      ELSE DROP THEN
    LOOP
  ELSE DROP THEN
  DROP
  BA-IDX @ WT-ESIZE *
  WT-BASE + WTO-XT + @
  DUP IF EXECUTE ELSE DROP THEN ;

\ ---- Focused widget type ---------------
: FOCUSED-TYPE ( -- type )
  FOCUS-IDX @ WT-ESIZE * WT-BASE +
  C@ ;

\ ---- INPUT field character handling ----
\ Append a printable char to the focused
\ INPUT widget's value buffer.
DECIMAL
32 CONSTANT IC-SPACE
126 CONSTANT IC-TILDE
8 CONSTANT IC-BS
HEX

VARIABLE IC-BASE
VARIABLE IC-LEN

: INPUT-CHAR ( ch -- )
  FOCUS-IDX @ IV-ADDR IC-BASE !
  IC-BASE @ C@ IC-LEN !
  IC-LEN @ IV-MAX < IF
    IC-BASE @ IC-LEN @ + 1+  C!
    IC-LEN @ 1 + IC-BASE @ C!
  ELSE DROP THEN ;

: INPUT-BS ( -- )
  FOCUS-IDX @ IV-ADDR IC-BASE !
  IC-BASE @ C@ IC-LEN !
  IC-LEN @ 0 > IF
    IC-LEN @ 1 -
    IC-BASE @ C!
  THEN ;

\ ---- Event log buffer ------------------
\ Simple text log of all UI interactions.
\ EVT-LOG-DUMP prints it; future: write to
\ file via NTFS-WRITE-FILE.
DECIMAL
4096 CONSTANT ELOG-MAX
HEX

CREATE ELOG-BUF ELOG-MAX ALLOT
VARIABLE ELOG-POS

: ELOG-RESET ( -- ) 0 ELOG-POS ! ;
ELOG-RESET

: ELOG-STR ( addr len -- )
  ELOG-POS @ OVER +
  ELOG-MAX < IF
    ELOG-BUF ELOG-POS @ +
    SWAP DUP ELOG-POS +! CMOVE
  ELSE DROP DROP THEN ;

: ELOG-CR ( -- )
  ELOG-POS @ ELOG-MAX < IF
    DECIMAL 10 HEX
    ELOG-BUF ELOG-POS @ + C!
    1 ELOG-POS +!
  THEN ;

: ELOG-DUMP ( -- )
  ELOG-BUF ELOG-POS @ TYPE ;

\ ---- Key dispatch ----------------------
: HANDLE-KEY ( key -- )
  DUP KEY-ESC = IF
    DROP 1 QUIT-FLAG ! EXIT THEN
  DUP KEY-TAB = IF
    DROP FOCUS-NEXT EXIT THEN
  \ INPUT mode: printable chars go to buf
  FOCUSED-TYPE WT-INPUT = IF
    DUP IC-SPACE >= OVER IC-TILDE <= AND
    IF
      INPUT-CHAR EXIT
    THEN
    DUP IC-BS = IF
      DROP INPUT-BS EXIT
    THEN
  THEN
  DUP KEY-Q = IF
    DROP 1 QUIT-FLAG ! EXIT THEN
  DUP KEY-ENTER = IF
    DROP ACTIVATE-FOCUS EXIT THEN
  DUP KEY-1 >= OVER KEY-9 <= AND IF
    BUTTON-ACTIVATE EXIT THEN
  DROP ;

\ ---- Event flush to console -----------
: EVENT-FLUSH ( -- )
  BEGIN
    EVENT-POP DUP IF
      ." EVT: " . .  CR
    ELSE DROP DROP EXIT THEN
  AGAIN ;

\ ---- Main event loop -------------------
: FORM-RUN ( -- )
  0 QUIT-FLAG !
  0 NEXT-FOCUSABLE
  DUP 0 < IF DROP 0 THEN
  FOCUS-IDX !
  BEGIN
    FORM-RENDER
    KEY HANDLE-KEY
    NET-FLUSH
    QUIT-FLAG @
  UNTIL
  VGA-CLS ;

PREVIOUS PREVIOUS
FORTH DEFINITIONS
DECIMAL
