\ ============================================
\ CATALOG: NOTEPAD-FORM
\ CATEGORY: form
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ ============================================
\ In-memory form data for Notepad.
\ CREATE buffer + CATALOG-REGISTER.
\ No block disk needed.
\ ============================================

ALSO CATALOG-RESOLVER
HEX

CREATE NF-DATA C00 ALLOT
NF-DATA C00 20 FILL

VARIABLE NF-PTR
NF-DATA NF-PTR !

CREATE NF-TMP 40 ALLOT
VARIABLE NF-TP

: NF-TCLR  0 NF-TP ! ;
: NF-TC ( c -- )
  NF-TMP NF-TP @ + C!
  1 NF-TP +! ;
: NF-TS ( a l -- )
  0 DO DUP I + C@ NF-TC LOOP
  DROP ;
: NF-TQ  22 NF-TC ;

\ Flush temp buf as one 64-byte line
: NF-TF
  NF-TMP NF-PTR @ NF-TP @ CMOVE
  NF-PTR @ NF-TP @ +
  40 NF-TP @ - 20 FILL
  40 NF-PTR +! ;

DECIMAL

\ ---- Form data (24 lines) ----
\ Must be in a colon def: S" in interpret
\ mode truncates past BLOCK_SIZE when
\ BLK != 0 (embedded eval sets BLK=1).
\ Compile-mode S" has no such limit.

: NF-BUILD
  NF-TCLR S" FORM: notepad" NF-TS NF-TF
  NF-TCLR S" LABEL: 1 0 " NF-TS
  NF-TQ S" ForthOS Notepad" NF-TS
  NF-TQ NF-TF
  NF-TCLR S" DIVIDER: 1" NF-TS NF-TF
  NF-TCLR S" CARD: 0 2 39 " NF-TS
  NF-TQ S" File" NF-TS NF-TQ NF-TF
  NF-TCLR S" BUTTON: 1 3 6 " NF-TS
  NF-TQ S" New" NF-TS NF-TQ NF-TF
  NF-TCLR S" BUTTON: 8 3 7 " NF-TS
  NF-TQ S" Open" NF-TS NF-TQ NF-TF
  NF-TCLR S" BUTTON: 16 3 7 " NF-TS
  NF-TQ S" Save" NF-TS NF-TQ NF-TF
  NF-TCLR S" BUTTON: 24 3 10 " NF-TS
  NF-TQ S" Save As" NF-TS NF-TQ NF-TF
  NF-TCLR S" ENDCARD: 0 4 39" NF-TS
  NF-TF
  NF-TCLR S" CARD: 40 2 39 " NF-TS
  NF-TQ S" Edit" NF-TS NF-TQ NF-TF
  NF-TCLR S" BUTTON: 41 3 6 " NF-TS
  NF-TQ S" Cut" NF-TS NF-TQ NF-TF
  NF-TCLR S" BUTTON: 48 3 7 " NF-TS
  NF-TQ S" Copy" NF-TS NF-TQ NF-TF
  NF-TCLR S" BUTTON: 56 3 8 " NF-TS
  NF-TQ S" Paste" NF-TS NF-TQ NF-TF
  NF-TCLR S" BUTTON: 65 3 7 " NF-TS
  NF-TQ S" Undo" NF-TS NF-TQ NF-TF
  NF-TCLR S" ENDCARD: 40 4 39" NF-TS
  NF-TF
  NF-TCLR S" DIVIDER: 5" NF-TS NF-TF
  NF-TCLR S" LABEL: 1 6 " NF-TS
  NF-TQ S" File:" NF-TS NF-TQ NF-TF
  NF-TCLR S" INPUT: 7 6 50 " NF-TS
  NF-TQ NF-TQ NF-TF
  NF-TCLR S" DIVIDER: 7" NF-TS NF-TF
  NF-TCLR S" DIVIDER: 22" NF-TS NF-TF
  NF-TCLR S" LABEL: 1 23 " NF-TS
  NF-TQ S" Ln 1, Col 1" NF-TS
  NF-TQ NF-TF
  NF-TCLR S" BUTTON: 70 23 8 " NF-TS
  NF-TQ S" Exit" NF-TS NF-TQ NF-TF
  NF-TCLR S" END-FORM:" NF-TS NF-TF
;
NF-BUILD

\ ---- Register in catalog ----
HEX
: NF-REGISTER
  NF-DATA 3 S" NOTEPAD-FORM"
  CATALOG-REGISTER ;
NF-REGISTER

PREVIOUS
DECIMAL
