\ ============================================
\ CATALOG: SETTINGS-DASH
\ CATEGORY: app
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ ============================================
\ Operator dashboard: shows current state of
\ system knobs and diagnostics at a glance.
\ Type SETTINGS to view, use toggle words
\ (MORE-ON, NET-CON-ON etc.) at the REPL.
\ No persistence — runtime state only.
\ SETTINGS is defined in FORTH so it is
\ callable bare after loading.
\ ============================================

DECIMAL
VOCABULARY SETTINGS-DASH
SETTINGS-DASH DEFINITIONS

\ ---- Display helpers -----------------------
: SD-HLINE ( -- )
  40 0 DO [CHAR] - EMIT LOOP CR ;

: SD-ON/OFF ( flag -- )
  IF ." ON" ELSE ." off" THEN ;

\ ---- Settings display ----------------------
: SD-SHOW-BASE ( -- )
  ."  Base:     "
  BASE @ DUP 10 = IF
    ." decimal" DROP
  ELSE 16 = IF
    ." hex"
  ELSE
    ." other"
  THEN THEN CR ;

: SD-SHOW-MORE ( -- )
  ."  Paging:   "
  MORE-ENABLED C@ SD-ON/OFF CR ;

: SD-SHOW-NETCON ( -- )
  ."  Net-con:  "
  NET-CON-ENABLED C@ SD-ON/OFF CR ;

: SD-SHOW-TRACE ( -- )
  ."  Trace:    "
  TRACE-ENABLED C@ SD-ON/OFF CR ;

\ ---- Diagnostics ---------------------------
: SD-SHOW-DIAG ( -- )
  ."  Ticks: " TICK-COUNT @ .
  ."  Keys: " KB-RING-COUNT @ . CR
  ."  Mouse: "
  MOUSE-X-VAR @ . ." ,"
  MOUSE-Y-VAR @ . CR ;

\ ---- Search order (hex addresses) ----------
: SD-SHOW-ORDER ( -- )
  ."  Search order:" CR ."    "
  ORDER ;

\ ---- Promote SETTINGS to FORTH vocab ------
\ Helpers compiled by CFA — search order
\ does not matter at runtime.
ONLY FORTH DEFINITIONS
ALSO SETTINGS-DASH

: SETTINGS ( -- )
  CR ." === ForthOS Settings ===" CR
  SD-HLINE
  SD-SHOW-BASE
  SD-SHOW-MORE
  SD-SHOW-NETCON
  SD-SHOW-TRACE
  SD-HLINE
  SD-SHOW-DIAG
  SD-SHOW-ORDER
  SD-HLINE
  ."  Toggle: MORE-ON MORE-OFF" CR
  ."          NET-CON-ON NET-CON-OFF" CR
  ."          HEX DECIMAL" CR
  ."          1 TRACE-ENABLED C!" CR
  ."          0 TRACE-ENABLED C!" CR ;

PREVIOUS
DECIMAL
