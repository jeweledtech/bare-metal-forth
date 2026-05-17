\ ============================================
\ CATALOG: GUI-HARVEST
\ CATEGORY: gui
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ REQUIRES: UI-CORE
\ ============================================
\
\ Widget registry and standard menu bar.
\ GET-GRAPHICS-ELEMENTS is a stub for now;
\ hooks into UBT when translator is ported
\ to a Forth vocabulary.
\
\ Usage:
\   USING GUI-HARVEST
\   S" MyBtn" WT-BUTTON ['] handler
\     WIDGET-REGISTER
\   S" MyBtn" WIDGET-FIND  ( -- xt|0 )
\   MENU-BAR
\
\ ============================================

VOCABULARY GUI-HARVEST
GUI-HARVEST DEFINITIONS
ALSO UI-CORE
ALSO CATALOG-RESOLVER

\ ---- Registry tables -------------------
\ Name table: 64 slots, 32 bytes each
\ (byte 0 = len, bytes 1-31 = name)
\ XT table: 64 x 4 bytes
\ Type table: 64 x 1 byte
HEX
20B000 CONSTANT REG-NAMES
20B800 CONSTANT REG-XTS
20B900 CONSTANT REG-TYPES
DECIMAL
64 CONSTANT REG-MAX
32 CONSTANT REG-NSIZE

VARIABLE REG-COUNT
0 REG-COUNT !

\ ---- Registry words --------------------

\ REG-NAME ( idx -- addr )
\ Address of name slot for index.
: REG-NAME ( idx -- addr )
  REG-NSIZE * REG-NAMES + ;

\ REG-XT ( idx -- addr )
: REG-XT ( idx -- addr )
  4 * REG-XTS + ;

\ REG-TYPE ( idx -- addr )
: REG-TYPE ( idx -- addr )
  REG-TYPES + ;

\ WIDGET-REGISTER ( na nl type xt -- )
\ Register widget name, type, and xt.
VARIABLE WR-XT
VARIABLE WR-TYPE
VARIABLE WR-NL
: WIDGET-REGISTER ( na nl type xt -- )
  REG-COUNT @ REG-MAX < IF
    WR-XT !  WR-TYPE !
    WR-NL !
    REG-COUNT @ REG-NAME
    WR-NL @ OVER C!
    1 +  WR-NL @ CMOVE
    WR-TYPE @
    REG-COUNT @ REG-TYPE C!
    WR-XT @
    REG-COUNT @ REG-XT !
    1 REG-COUNT +!
  ELSE
    DROP DROP DROP DROP
    ." Registry full" CR
  THEN ;

\ ---- Case-insensitive comparison ------
\ CHAR uses the outer interpreter which
\ uppercases input, but S" preserves case.
\ WIDGET-FIND needs case-insensitive match
\ so form labels ("Go") match registry
\ names ("GO") built via CHAR.
DECIMAL
: UPCASE-CHAR ( c -- C )
  DUP 97 < IF EXIT THEN
  DUP 122 > IF EXIT THEN
  32 - ;

: STR=CI ( a1 u1 a2 u2 -- flag )
  ROT OVER <> IF
    DROP DROP DROP FALSE EXIT
  THEN
  0 DO
    OVER I + C@ UPCASE-CHAR
    OVER I + C@ UPCASE-CHAR
    <> IF
      DROP DROP FALSE UNLOOP EXIT
    THEN
  LOOP
  DROP DROP TRUE ;
HEX

\ WIDGET-FIND ( na nl -- xt | 0 )
\ Search registry by name (case-insensitive).
: WIDGET-FIND ( na nl -- xt | 0 )
  REG-COUNT @ DUP 0 > IF
    0 DO
      2DUP
      I REG-NAME DUP C@
      SWAP 1 + SWAP
      STR=CI IF
        DROP DROP
        I REG-XT @
        UNLOOP EXIT
      THEN
    LOOP
    DROP DROP 0
  ELSE
    DROP DROP DROP 0
  THEN ;

\ WIDGETS-LIST ( -- )
: WIDGETS-LIST ( -- )
  ." Widgets: "
  REG-COUNT @ . CR
  REG-COUNT @ DUP 0 > IF
    0 DO
      I . ." : "
      I REG-NAME DUP C@
      SWAP 1 + SWAP TYPE
      ."  xt="
      I REG-XT @ .
      ."  type="
      I REG-TYPE C@ . CR
    LOOP
  ELSE DROP THEN ;

\ GET-GRAPHICS-ELEMENTS ( -- )
\ Stub: prints message. Future: hooks
\ into UBT vocabulary for GUI harvesting.
: GET-GRAPHICS-ELEMENTS ( -- )
  ." GET-GRAPHICS-ELEMENTS: stub" CR
  ." (future: UBT vocabulary)" CR ;

\ ---- Standard menu bar -----------------

VARIABLE MB-POS
VARIABLE MB-LEN
0 MB-POS !

: MB-ITEM ( addr len -- )
  DUP MB-LEN !
  MB-POS @ 0 ATTR-INV DRAW-AT
  MB-LEN @ MB-POS +!
  2 MB-POS +! ;

: MENU-FILE ( -- ) S" File" MB-ITEM ;
: MENU-EDIT ( -- ) S" Edit" MB-ITEM ;
: MENU-VIEW ( -- ) S" View" MB-ITEM ;
: MENU-INSERT ( -- )
  S" Insert" MB-ITEM ;
: MENU-FORMAT ( -- )
  S" Format" MB-ITEM ;
: MENU-TOOLS ( -- )
  S" Tools" MB-ITEM ;
: MENU-PRINT ( -- )
  S" Print" MB-ITEM ;
: MENU-WINDOW ( -- )
  S" Window" MB-ITEM ;
: MENU-HELP ( -- ) S" Help" MB-ITEM ;

: MENU-BAR ( -- )
  0 MB-POS !
  MENU-FILE  MENU-EDIT  MENU-VIEW
  MENU-INSERT MENU-FORMAT
  MENU-TOOLS MENU-PRINT
  MENU-WINDOW MENU-HELP ;

\ ---- Wire form buttons to registry ------
: FORM-WIRE ( -- )
  WT-COUNT @ DUP 0 > IF
    0 DO
      I WT-ESIZE * WT-BASE +
      W-ADDR !
      W-TYPE@ WT-BUTTON = IF
        W-LOFF@ W-LLEN@ POOL-STR
        WIDGET-FIND
        DUP IF W-XT!
        ELSE DROP THEN
      THEN
    LOOP
  ELSE DROP THEN ;

PREVIOUS PREVIOUS
FORTH DEFINITIONS
DECIMAL
