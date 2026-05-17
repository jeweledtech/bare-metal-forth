\ ============================================
\ CATALOG: UI-PARSER
\ CATEGORY: gui
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ REQUIRES: UI-CORE
\ ============================================
\
\ Tag/value .def file parser for forms.
\ Reads block data, parses LABEL: BUTTON:
\ DIVIDER: tags, creates widgets via
\ ADD-LABEL ADD-BUTTON ADD-DIVIDER.
\
\ Usage:
\   USING UI-PARSER
\   120 125 FORM-LOAD
\
\ ============================================

VOCABULARY UI-PARSER
UI-PARSER DEFINITIONS
ALSO UI-CORE
ALSO CATALOG-RESOLVER

\ ---- Parse constants (DECIMAL) ---------
DECIMAL
48 CONSTANT P-ZERO
57 CONSTANT P-NINE
32 CONSTANT P-SPC
34 CONSTANT P-QUOTE
92 CONSTANT P-BSLASH
64 CONSTANT LINE-LEN
16 CONSTANT LINES-BLK
10 CONSTANT P-TEN
HEX

\ ---- Parse state -----------------------
VARIABLE P-ADDR
VARIABLE P-LEN

: P-INIT ( addr len -- )
  P-LEN ! P-ADDR ! ;

: P-SKIP-SP ( -- )
  BEGIN
    P-LEN @ 0 > IF
      P-ADDR @ C@ P-SPC =
    ELSE FALSE THEN
  WHILE
    1 P-ADDR +!
    -1 P-LEN +!
  REPEAT ;

\ P-INT: parse decimal integer
: P-INT ( -- n )
  P-SKIP-SP 0
  BEGIN
    P-LEN @ 0 > IF
      P-ADDR @ C@ DUP
      P-ZERO >= SWAP
      P-NINE <= AND
    ELSE FALSE THEN
  WHILE
    P-TEN *
    P-ADDR @ C@ P-ZERO - +
    1 P-ADDR +!
    -1 P-LEN +!
  REPEAT ;

\ P-QUOTED: extract text between quotes
VARIABLE PQ-S
VARIABLE PQ-L
: P-QUOTED ( -- addr len )
  P-SKIP-SP
  P-LEN @ 0 > IF
    P-ADDR @ C@ P-QUOTE = IF
      1 P-ADDR +!
      -1 P-LEN +!
    THEN
  THEN
  P-ADDR @ PQ-S !
  0 PQ-L !
  BEGIN
    P-LEN @ 0 > IF
      P-ADDR @ C@ P-QUOTE <>
    ELSE FALSE THEN
  WHILE
    1 PQ-L +!
    1 P-ADDR +!
    -1 P-LEN +!
  REPEAT
  P-LEN @ 0 > IF
    1 P-ADDR +!
    -1 P-LEN +!
  THEN
  PQ-S @ PQ-L @ ;

\ ---- Tag matching ----------------------
VARIABLE TM-A
VARIABLE TM-L
: P-MATCH ( tag-a tag-l -- flag )
  TM-L ! TM-A !
  P-SKIP-SP
  P-LEN @ TM-L @ >= IF
    P-ADDR @ TM-L @
    TM-A @ TM-L @
    STR= IF
      TM-L @ P-ADDR +!
      TM-L @ NEGATE P-LEN +!
      TRUE EXIT
    THEN
  THEN
  FALSE ;

\ ---- Trim trailing spaces --------------
VARIABLE TL-A
VARIABLE TL-L
: TRIM-LINE ( addr maxlen -- addr len )
  TL-L ! TL-A !
  BEGIN
    TL-L @ 0 > IF
      TL-A @ TL-L @ + 1 - C@
      P-SPC =
    ELSE FALSE THEN
  WHILE
    -1 TL-L +!
  REPEAT
  TL-A @ TL-L @ ;

\ ---- Build widgets from parsed data ----

: BUILD-LABEL ( -- )
  P-INT P-INT P-QUOTED ADD-LABEL ;

VARIABLE BB-X
VARIABLE BB-Y
VARIABLE BB-W
: BUILD-BUTTON ( -- )
  P-INT BB-X !
  P-INT BB-Y !
  P-INT BB-W !
  BB-X @ BB-Y @ BB-W @
  P-QUOTED 0 ADD-BUTTON ;

: BUILD-DIVIDER ( -- )
  P-INT ADD-DIVIDER ;

VARIABLE BI-X
VARIABLE BI-Y
VARIABLE BI-W
: BUILD-INPUT ( -- )
  P-INT BI-X !
  P-INT BI-Y !
  P-INT BI-W !
  BI-X @ BI-Y @ BI-W @
  P-QUOTED ADD-INPUT ;

VARIABLE BD-X
VARIABLE BD-Y
VARIABLE BD-W
: BUILD-DROPBOX ( -- )
  P-INT BD-X !
  P-INT BD-Y !
  P-INT BD-W !
  BD-X @ BD-Y @ BD-W @
  P-QUOTED ADD-DROPBOX ;

VARIABLE BC-X
VARIABLE BC-Y
VARIABLE BC-W
: BUILD-CARD-BG ( -- )
  P-INT BC-X !
  P-INT BC-Y !
  P-INT BC-W !
  BC-X @ BC-Y @ BC-W @
  P-QUOTED ADD-CARD-BG ;

: BUILD-CARD-ED ( -- )
  P-INT P-INT P-INT ADD-CARD-ED ;

\ ---- Process one line ------------------
: PROCESS-LINE ( addr len -- )
  P-INIT P-SKIP-SP
  P-LEN @ 0 <= IF EXIT THEN
  P-ADDR @ C@ P-BSLASH = IF
    EXIT THEN
  S" LABEL:" P-MATCH IF
    BUILD-LABEL EXIT THEN
  S" BUTTON:" P-MATCH IF
    BUILD-BUTTON EXIT THEN
  S" DIVIDER:" P-MATCH IF
    BUILD-DIVIDER EXIT THEN
  S" INPUT:" P-MATCH IF
    BUILD-INPUT EXIT THEN
  S" DROPBOX:" P-MATCH IF
    BUILD-DROPBOX EXIT THEN
  S" CARD:" P-MATCH IF
    BUILD-CARD-BG EXIT THEN
  S" ENDCARD:" P-MATCH IF
    BUILD-CARD-ED EXIT THEN ;

\ ---- FORM-LOAD: parse blocks ----------

VARIABLE FL-BUF

: FL-PARSE-BUF ( -- )
  LINES-BLK 0 DO
    FL-BUF @ I LINE-LEN * +
    LINE-LEN TRIM-LINE
    DUP 0 > IF
      PROCESS-LINE
    ELSE DROP DROP THEN
  LOOP ;

: FORM-LOAD ( v1 v2 -- )
  WT-RESET
  CATALOG-MEM @ IF
    0 DO
      DUP FL-BUF ! 400 +
      FL-PARSE-BUF
    LOOP DROP
  ELSE
    1 + SWAP DO
      I BLOCK FL-BUF !
      FL-PARSE-BUF
    LOOP
  THEN ;

PREVIOUS PREVIOUS
FORTH DEFINITIONS
DECIMAL
