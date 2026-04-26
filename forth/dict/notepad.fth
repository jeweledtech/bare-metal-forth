\ ============================================
\ CATALOG: NOTEPAD
\ CATEGORY: app
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ REQUIRES: UI-CORE
\ REQUIRES: UI-PARSER
\ REQUIRES: UI-EVENTS
\ REQUIRES: GUI-HARVEST
\ REQUIRES: FILE-EDITOR
\ REQUIRES: CATALOG-RESOLVER
\ ============================================
\
\ ForthOS Notepad: text file editor form.
\ Wires form buttons to FILE-EDITOR actions.
\ Form layout in NOTEPAD-FORM blocks.
\
\ Usage:
\   USING NOTEPAD
\   NOTEPAD-RUN
\
\ ============================================

VOCABULARY NOTEPAD
NOTEPAD DEFINITIONS
ALSO UI-CORE
ALSO UI-EVENTS
ALSO UI-PARSER
ALSO GUI-HARVEST
ALSO FILE-EDITOR
ALSO CATALOG-RESOLVER

HEX

\ ---- Region constants (HEX/DECIMAL safe) --
DECIMAL
8  CONSTANT NP-EDIT-Y
14 CONSTANT NP-EDIT-H
23 CONSTANT NP-STATUS-ROW
HEX

\ ---- State variables ---------------------
VARIABLE NP-EDIT-MODE
VARIABLE NP-INPUT-IDX

: NP-FIND-INPUT ( -- )
  WT-COUNT @ 0 DO
    I WT-ESIZE * WT-BASE +
    C@ WT-INPUT = IF
      I NP-INPUT-IDX ! LEAVE
    THEN
  LOOP ;

\ ---- Button handlers -------------------

: NP-NEW ( -- )
  FE-BUF MAX-FILE 0 FILL
  0 FE-SIZE ! 0 FE-CX ! 0 FE-CY !
  0 FE-TOP ! 0 FE-DIRTY !
  0 FE-NLEN !
  1 NP-EDIT-MODE ! ;

: NP-OPEN ( -- )
  NP-INPUT-IDX @ IV-GET
  DUP 0= IF 2DROP EXIT THEN
  FE-OPEN
  0 FE-CX ! 0 FE-CY !
  0 FE-TOP !
  1 NP-EDIT-MODE ! ;

: NP-SAVE ( -- )
  FE-NLEN @ 0= IF EXIT THEN
  FE-SAVE ;

: NP-SAVE-AS ( -- )
  NP-INPUT-IDX @ IV-GET
  DUP 0= IF 2DROP EXIT THEN
  DUP FE-NLEN !
  FE-NAME SWAP CMOVE
  1 FE-DIRTY ! FE-SAVE ;

: NP-CUT ( -- )
  ." Cut    " CR ;

: NP-COPY ( -- )
  ." Copy   " CR ;

: NP-PASTE ( -- )
  ." Paste  " CR ;

: NP-UNDO ( -- )
  ." Undo   " CR ;

: NP-EXIT ( -- )
  1 QUIT-FLAG ! ;

\ ---- Widget registration ---------------
\ Counted-string labels (S" interpret-mode bug
\ workaround). S" inside a colon def hits
\ the embedded-evaluator STATE bug; counted
\ strings via CREATE bypass it entirely.
CREATE NP-LBL-NEW 3 C, CHAR N C,
  CHAR e C, CHAR w C,
CREATE NP-LBL-OPEN 4 C, CHAR O C,
  CHAR p C, CHAR e C, CHAR n C,
CREATE NP-LBL-SAVE 4 C, CHAR S C,
  CHAR a C, CHAR v C, CHAR e C,
CREATE NP-LBL-SAVEAS 7 C, CHAR S C,
  CHAR a C, CHAR v C, CHAR e C,
  20 C, CHAR A C, CHAR s C,
CREATE NP-LBL-CUT 3 C, CHAR C C,
  CHAR u C, CHAR t C,
CREATE NP-LBL-COPY 4 C, CHAR C C,
  CHAR o C, CHAR p C, CHAR y C,
CREATE NP-LBL-PASTE 5 C, CHAR P C,
  CHAR a C, CHAR s C, CHAR t C,
  CHAR e C,
CREATE NP-LBL-UNDO 4 C, CHAR U C,
  CHAR n C, CHAR d C, CHAR o C,
CREATE NP-LBL-EXIT 4 C, CHAR E C,
  CHAR x C, CHAR i C, CHAR t C,

: NP-COUNT ( a -- a+1 len ) DUP 1+ SWAP C@ ;

: NP-REGISTER-BUTTONS ( -- )
  NP-LBL-NEW NP-COUNT WT-BUTTON
  ' NP-NEW WIDGET-REGISTER
  NP-LBL-OPEN NP-COUNT WT-BUTTON
  ' NP-OPEN WIDGET-REGISTER
  NP-LBL-SAVE NP-COUNT WT-BUTTON
  ' NP-SAVE WIDGET-REGISTER
  NP-LBL-SAVEAS NP-COUNT WT-BUTTON
  ' NP-SAVE-AS WIDGET-REGISTER
  NP-LBL-CUT NP-COUNT WT-BUTTON
  ' NP-CUT WIDGET-REGISTER
  NP-LBL-COPY NP-COUNT WT-BUTTON
  ' NP-COPY WIDGET-REGISTER
  NP-LBL-PASTE NP-COUNT WT-BUTTON
  ' NP-PASTE WIDGET-REGISTER
  NP-LBL-UNDO NP-COUNT WT-BUTTON
  ' NP-UNDO WIDGET-REGISTER
  NP-LBL-EXIT NP-COUNT WT-BUTTON
  ' NP-EXIT WIDGET-REGISTER ;

NP-REGISTER-BUTTONS

\ ---- Wire button handlers ---------------
\ Match widget labels to registry XTs.
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

\ ---- Mode switch helpers ----------------

: NP-EXIT-EDIT ( -- )
  0 NP-EDIT-MODE ! ;

: NP-EDITOR-KEY ( scancode -- )
  DUP 1 = IF
    DROP NP-EXIT-EDIT EXIT THEN
  DUP SC-CTRL-Q =
  KB-MODS @ 2 AND AND IF
    DROP NP-EXIT-EDIT EXIT THEN
  FE-DISPATCH ;

\ ---- Main entry point ------------------
\ NOTEPAD-FORM: blocks 512-514.

: NP-RUN ( -- )
  INIT-KEYMAP NP-FIND-INPUT
  NP-EDIT-Y NP-EDIT-H NP-STATUS-ROW
  FE-SET-REGION
  0 QUIT-FLAG ! 0 NP-EDIT-MODE !
  0 NEXT-FOCUSABLE
  DUP 0 < IF DROP 0 THEN FOCUS-IDX !
  BEGIN
    NP-EDIT-MODE @ IF
      FE-REFRESH FE-CURSOR FE-STATUS
      FE-KEY DUP 1 = IF
        DROP NP-EDITOR-KEY
      ELSE 2DROP THEN
    ELSE
      FORM-RENDER
      KEY HANDLE-KEY
    THEN
    NET-FLUSH QUIT-FLAG @
  UNTIL VGA-CLS ;

: NOTEPAD-RUN ( -- )
  ." Loading NOTEPAD..." CR
  S" NOTEPAD-FORM" CATALOG-FIND
  0= IF ." Form not found" CR EXIT THEN
  FORM-LOAD FORM-WIRE
  ." NOTEPAD ready" CR
  NP-RUN
  ." NOTEPAD closed" CR ;

ONLY FORTH DEFINITIONS
DECIMAL
