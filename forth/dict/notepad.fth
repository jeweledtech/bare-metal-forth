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
\ Register button names to handler XTs.
\ NOTE: S" must run in compile mode (kernel S" interpret-mode bug
\ leaks source bytes to console). Wrap registrations in a colon def
\ and invoke once. Same workaround as notepad-form.fth:44.
: NP-REGISTER-BUTTONS ( -- )
  S" New"     WT-BUTTON ' NP-NEW     WIDGET-REGISTER
  S" Open"    WT-BUTTON ' NP-OPEN    WIDGET-REGISTER
  S" Save"    WT-BUTTON ' NP-SAVE    WIDGET-REGISTER
  S" Save As" WT-BUTTON ' NP-SAVE-AS WIDGET-REGISTER
  S" Cut"     WT-BUTTON ' NP-CUT     WIDGET-REGISTER
  S" Copy"    WT-BUTTON ' NP-COPY    WIDGET-REGISTER
  S" Paste"   WT-BUTTON ' NP-PASTE   WIDGET-REGISTER
  S" Undo"    WT-BUTTON ' NP-UNDO    WIDGET-REGISTER
  S" Exit"    WT-BUTTON ' NP-EXIT    WIDGET-REGISTER ;

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
  DUP SC-CTRL-Q = IF
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
