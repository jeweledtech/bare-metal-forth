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
\ Per-button records (private
\ TASK_ROS_NOTEPAD_BUTTON_PANEL), from
\ buttons2forth, after the table's IMP-END:
\   519 1 IMP-BUTTON
\   S" user32.dll!EndDialog" IMP-CALL
\   S" 0x464" IMP-POST  ...  IMP-END
\ What a button's branch may call, every
\ path followed. IMPORTS-BUTTON
\ ( dialog cid -- ) shows one button's
\ panel; P there opens IMPORTS-SHOW.
\ Menu items (private TASK_ROS_NOTEPAD_
\ MENUS) use the same records, keyed
\ menu id: IMPORTS-ITEM ( menu id -- ).
\ More than 40 entries: Space pages.
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
\ The button records: a list, newest
\ first. A record: link, dialog, cid,
\ calls, posts (cells), then entries
\ (tag 3 a call, 4 a post, 0 the end).
VARIABLE IMP-BTNS
VARIABLE IMP-NBTN
VARIABLE IMP-BOPEN
0 IMP-BTNS !  0 IMP-NBTN !  0 IMP-BOPEN !

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
  0 IMP-NFN !  0 IMP-NDLL !
  0 IMP-BTNS !  0 IMP-NBTN !  0 IMP-BOPEN ! ;
: IMP-DLL ( addr len -- )
  1 C, IMP-STR,  1 IMP-NDLL +! ;
: IMP-FN ( addr len -- )
  2 C, IMP-STR,  1 IMP-NFN +! ;
\ Ends the table, or the open record.
: IMP-END ( -- ) 0 C, IMP-ALIGN  0 IMP-BOPEN ! ;

\ ---- The button records ------------------
: IMP-BUTTON ( dialog cid -- )
  IMP-BOPEN @ IF 0 C, THEN IMP-ALIGN
  HERE @ IMP-BTNS @ , IMP-BTNS !
  SWAP , ,  0 , 0 ,
  -1 IMP-BOPEN !  1 IMP-NBTN +! ;
\ An entry of the open record; n the
\ count's offset. None open: refused.
: IMP-ENTRY ( addr len tag n -- )
  IMP-BOPEN @ 0= IF
    2DROP 2DROP ." IMP: no IMP-BUTTON" CR
    EXIT THEN
  >R C, IMP-STR,  1 IMP-BTNS @ R> + +! ;
: IMP-CALL ( addr len -- ) 3 12 IMP-ENTRY ;
: IMP-POST ( addr len -- ) 4 16 IMP-ENTRY ;

\ The record of button cid of dialog
\ dialog, or 0.
: IMP-BFIND ( dialog cid -- rec | 0 )
  IMP-BTNS @
  BEGIN DUP WHILE
    DUP 4 + @ 3 PICK =
    OVER 8 + @ 3 PICK = AND IF
      NIP NIP EXIT THEN
    @
  REPEAT
  NIP NIP ;

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

\ ---- One button's or menu item's panel ---
VARIABLE IB-D
VARIABLE IB-C
VARIABLE IB-R
\ 0 a dialog button, 1 a menu item
\ (private TASK_ROS_NOTEPAD_MENUS).
VARIABLE IB-KIND
VARIABLE IB-P
VARIABLE IB-LO

\ Entry k of record r's entries: as
\ IM-ENTRY, a post as `posts 0x...`.
: IB-ENTRY ( e k -- )
  DUP 20 MOD 5 + IM-ROW
  20 < 0= IF 40 IM-X ! THEN
  DUP C@ 4 = IF S" posts " IM-TXT THEN
  1 + DUP 1 + SWAP C@ IM-TXT ;

\ Pages of 40 entries; 1 with no record.
: IB-PAGES ( -- n )
  IB-R @ 0= IF 1 EXIT THEN
  IB-R @ 12 + @  IB-R @ 16 + @ +
  39 + 40 /  1 MAX ;

: IB-HEAD ( -- )
  VGA-CLS  0 IM-ROW
  IMP-NAME @ DUP 1 + SWAP C@ IM-TXT
  IB-KIND @ IF
    S" : menu " IM-TXT  IB-D @ IM-N
    S" , item " IM-TXT  IB-C @ IM-N
  ELSE
    S" : dialog " IM-TXT  IB-D @ IM-N
    S" , button " IM-TXT  IB-C @ IM-N
  THEN
  3 IM-ROW
  IB-PAGES 1 > IF
    S" Page " IM-TXT  IB-P @ IM-N
    S"  of " IM-TXT  IB-PAGES IM-N
    S"   Space: next page  Esc: back" IM-TXT
  ELSE
    S" P: whole program  Esc: back" IM-TXT
  THEN ;

: IB-PAGE ( -- )
  IB-HEAD  1 IM-ROW
  IB-R @ 0= IF
    S" No record for this button." IM-TXT EXIT
  THEN
  IB-KIND @ IF
    S" What this menu item may call (every path of its case):"
  ELSE
    S" What this button may call (every path of its branch):"
  THEN IM-TXT
  2 IM-ROW  S" Imports: " IM-TXT  IB-R @ 12 + @ IM-N
  IB-KIND @ IF
    S"   Posted messages: not measured" IM-TXT
  ELSE
    S"   Posted messages: " IM-TXT  IB-R @ 16 + @ IM-N
  THEN
  IB-P @ 1 - 40 * IB-LO !
  IB-R @ 20 + 0
  BEGIN OVER C@ WHILE
    DUP IB-LO @ - DUP 0< 0= SWAP 40 < AND IF
      2DUP IB-LO @ - IB-ENTRY
    THEN
    1 + SWAP IM-NEXT SWAP
  REPEAT 2DROP ;

\ Space: next page (wrapping); P or p:
\ the whole program's page; Esc: back.
: IB-RUN ( dialog cid -- )
  2DUP IMP-BFIND IB-R !  IB-C ! IB-D !
  1 IB-P !
  BEGIN
    IB-PAGE
    KEY DUP 32 = IF
      IB-P @ IB-PAGES MOD 1 + IB-P !
    THEN
    DUP 80 = OVER 112 = OR IF
      IMPORTS-SHOW
    THEN
    27 =
  UNTIL ;

\ Nothing loaded: returns.
: IMPORTS-BUTTON ( dialog cid -- )
  IMP-TABLE @ 0= IF 2DROP EXIT THEN
  0 IB-KIND !  IB-RUN ;

\ A menu item's panel (private
\ TASK_ROS_NOTEPAD_MENUS): the record of
\ item id of menu, as 513 256.
: IMPORTS-ITEM ( menu id -- )
  IMP-TABLE @ 0= IF 2DROP EXIT THEN
  1 IB-KIND !  IB-RUN ;

PREVIOUS
FORTH DEFINITIONS
DECIMAL
