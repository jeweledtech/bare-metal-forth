\ ============================================
\ CATALOG: IMPORTS
\ CATEGORY: gui
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ REQUIRES: UI-CORE ( VGA-CLS DRAW-AT ATTR-NORM )
\ ============================================
\
\ A program's import table, as data, and a
\ panel that pages through it (private
\ TASK_REACTOS_NOTEPAD_FORMS). The data
\ comes from tools/imports2forth.py:
\   S" notepad.exe" IMP-PROGRAM
\   S" user32.dll" IMP-DLL
\   S" CreateWindowExW" IMP-FN  ...
\   IMP-END
\ The panel says what it is: the whole
\ program's imports, not what the button
\ that opened it does (that needs the
\ code). Space: next page; Esc: back.
\
\ Usage, as a button's word:
\   ' IMPORTS-SHOW 1 CID-WIRE DROP
\
\ ============================================

VOCABULARY IMPORTS
IMPORTS DEFINITIONS
ALSO UI-CORE

DECIMAL

\ ---- The table ---------------------------
\ A record: a tag byte (1 a DLL, 2 a
\ function, 0 the end), then a counted
\ name. The last IMP-PROGRAM's table is
\ the one shown.
VARIABLE IMP-NAME
VARIABLE IMP-TABLE
VARIABLE IMP-NFN
VARIABLE IMP-NDLL
0 IMP-TABLE !

: IMP-ALIGN ( -- ) HERE @ 3 + -4 AND HERE ! ;
\ A counted copy at HERE: S" text is
\ transient (the kernel's string buffer).
: IMP-STR, ( addr len -- )
  DUP C, DUP 0 > IF
    0 DO DUP I + C@ C, LOOP
  ELSE DROP THEN DROP ;

: IMP-PROGRAM ( addr len -- )
  IMP-ALIGN HERE @ IMP-NAME ! IMP-STR,
  HERE @ IMP-TABLE !
  0 IMP-NFN !  0 IMP-NDLL ! ;
: IMP-DLL ( addr len -- )
  1 C, IMP-STR,  1 IMP-NDLL +! ;
: IMP-FN ( addr len -- )
  2 C, IMP-STR,  1 IMP-NFN +! ;
: IMP-END ( -- ) 0 C, IMP-ALIGN ;

\ ---- Drawing -----------------------------
VARIABLE IM-X
VARIABLE IM-Y
: IM-ROW ( row -- ) IM-Y !  0 IM-X ! ;
: IM-TXT ( addr len -- )
  DUP >R IM-X @ IM-Y @ ATTR-NORM DRAW-AT
  R> IM-X +! ;

\ A number in decimal at the cursor.
CREATE IM-BUF 12 ALLOT
VARIABLE IM-ND
: IM-N ( n -- )
  0 IM-ND !
  BEGIN
    10 /MOD SWAP 48 +
    IM-BUF IM-ND @ + C!  1 IM-ND +!
    DUP 0 =
  UNTIL DROP
  IM-ND @ 0 DO
    IM-BUF IM-ND @ 1 - I - + 1 IM-TXT
  LOOP ;

: IM-COUNT ( -- n ) IMP-NFN @ IMP-NDLL @ + ;
: IM-PAGES ( -- n ) IM-COUNT 39 + 40 / ;

: IM-HEAD ( page -- )
  0 IM-ROW
  IMP-NAME @ DUP 1 + SWAP C@ IM-TXT
  S" : " IM-TXT  IMP-NFN @ IM-N
  S"  functions from " IM-TXT
  IMP-NDLL @ IM-N  S"  DLLs" IM-TXT
  1 IM-ROW
  S" What the whole program calls (its import table)," IM-TXT
  2 IM-ROW
  S" not what this button does." IM-TXT
  3 IM-ROW  S" Page " IM-TXT  IM-N
  S"  of " IM-TXT  IM-PAGES IM-N
  S"   Space: next page  Esc: back" IM-TXT ;

\ ---- Entries -----------------------------
\ Record r's successor.
: IM-NEXT ( r -- r' ) 1 + DUP C@ + 1 + ;

VARIABLE IM-R
\ IM-R to the record of entry n.
: IM-SKIP ( n -- )
  IMP-TABLE @ SWAP DUP 0 > IF
    0 DO
      DUP C@ IF IM-NEXT THEN
    LOOP
  ELSE DROP THEN IM-R ! ;

\ Record r as entry k of a page: col 0 or
\ 40, row 5 + k mod 20; a function two in.
: IM-ENTRY ( r k -- )
  DUP 20 MOD 5 + IM-ROW
  20 < 0= IF 40 IM-X ! THEN
  DUP C@ 2 = IF 2 IM-X +! THEN
  1 + DUP 1 + SWAP C@ IM-TXT ;

: IM-PAGE ( page -- )
  VGA-CLS  DUP IM-HEAD
  1 - 40 * IM-SKIP
  40 0 DO
    IM-R @ C@ IF
      IM-R @ I IM-ENTRY
      IM-R @ IM-NEXT IM-R !
    THEN
  LOOP ;

\ ---- The panel ---------------------------
VARIABLE IM-P
: IMPORTS-SHOW ( -- )
  IMP-TABLE @ 0 = IF EXIT THEN
  1 IM-P !
  BEGIN
    IM-P @ IM-PAGE
    KEY DUP 32 = IF
      IM-P @ IM-PAGES MOD 1 + IM-P !
    THEN
    27 =
  UNTIL ;

PREVIOUS
FORTH DEFINITIONS
DECIMAL
