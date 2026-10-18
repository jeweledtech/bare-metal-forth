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
  THEN ;

: DIALOG-RUN ( -- id )
  0 DR-ID !  FALSE DR-DONE !
  0 NEXT-FOCUSABLE
  DUP 0 < IF DROP 0 THEN
  FOCUS-IDX !
  BEGIN
    FORM-RENDER
    KEY DR-KEY
    DR-DONE @
  UNTIL
  PAGE  DR-ID @ ;

PREVIOUS PREVIOUS PREVIOUS
FORTH DEFINITIONS
DECIMAL
