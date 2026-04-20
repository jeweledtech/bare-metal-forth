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

HEX

\ ---- Button handlers -------------------

: NP-NEW ( -- )
  ." New file" CR ;

: NP-OPEN ( -- )
  ." Open file" CR ;

: NP-SAVE ( -- )
  ." Save file" CR ;

: NP-SAVE-AS ( -- )
  ." Save As" CR ;

: NP-CUT ( -- )
  ." Cut" CR ;

: NP-COPY ( -- )
  ." Copy" CR ;

: NP-PASTE ( -- )
  ." Paste" CR ;

: NP-UNDO ( -- )
  ." Undo" CR ;

: NP-EXIT ( -- )
  1 QUIT-FLAG ! ;

\ ---- Widget registration ---------------
\ Register button names to handler XTs.
\ GUI-HARVEST WIDGET-FIND uses these.

S" New" WT-BUTTON ' NP-NEW
  WIDGET-REGISTER
S" Open" WT-BUTTON ' NP-OPEN
  WIDGET-REGISTER
S" Save" WT-BUTTON ' NP-SAVE
  WIDGET-REGISTER
S" Save As" WT-BUTTON ' NP-SAVE-AS
  WIDGET-REGISTER
S" Cut" WT-BUTTON ' NP-CUT
  WIDGET-REGISTER
S" Copy" WT-BUTTON ' NP-COPY
  WIDGET-REGISTER
S" Paste" WT-BUTTON ' NP-PASTE
  WIDGET-REGISTER
S" Undo" WT-BUTTON ' NP-UNDO
  WIDGET-REGISTER
S" Exit" WT-BUTTON ' NP-EXIT
  WIDGET-REGISTER

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

\ ---- Main entry point ------------------
\ NOTEPAD-FORM: blocks 512-514.

DECIMAL
: NOTEPAD-RUN ( -- )
  ." Loading NOTEPAD..." CR
  512 514 FORM-LOAD
  FORM-WIRE
  ." NOTEPAD ready" CR
  FORM-RUN
  ." NOTEPAD closed" CR ;
HEX

ONLY FORTH DEFINITIONS
DECIMAL
