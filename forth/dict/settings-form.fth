\ ============================================
\ CATALOG: SETTINGS-FORM
\ CATEGORY: form
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ ============================================
\ In-memory form data for Settings panel.
\ CREATE buffer + CATALOG-REGISTER.
\ No block disk needed.
\ Milestone 4: fourth panel, tests forty-panel
\ hypothesis (declaration vs handler ratio).
\ ============================================

ALSO CATALOG-RESOLVER
HEX

CREATE SF-DATA 800 ALLOT
SF-DATA 800 20 FILL

VARIABLE SF-PTR
SF-DATA SF-PTR !

CREATE SF-TMP 40 ALLOT
VARIABLE SF-TP

: SF-TCLR  0 SF-TP ! ;
: SF-TC ( c -- )
  SF-TMP SF-TP @ + C!
  1 SF-TP +! ;
: SF-TS ( a l -- )
  0 DO DUP I + C@ SF-TC LOOP
  DROP ;
: SF-TQ  22 SF-TC ;

: SF-TF
  SF-TMP SF-PTR @ SF-TP @ CMOVE
  SF-PTR @ SF-TP @ +
  40 SF-TP @ - 20 FILL
  40 SF-PTR +! ;

DECIMAL

: SF-BUILD
  SF-TCLR S" FORM: settings" SF-TS SF-TF
  SF-TCLR S" LABEL: 1 0 " SF-TS
  SF-TQ S" ForthOS Settings" SF-TS
  SF-TQ SF-TF
  SF-TCLR S" DIVIDER: 1" SF-TS SF-TF
  SF-TCLR S" CARD: 0 2 40 " SF-TS
  SF-TQ S" Display" SF-TS SF-TQ SF-TF
  SF-TCLR S" LABEL: 2 3 " SF-TS
  SF-TQ S" Color:" SF-TS SF-TQ SF-TF
  SF-TCLR S" BUTTON: 10 3 8 " SF-TS
  SF-TQ S" Cycle" SF-TS SF-TQ SF-TF
  SF-TCLR S" LABEL: 20 3 " SF-TS
  SF-TQ S" Green" SF-TS SF-TQ SF-TF
  SF-TCLR S" LABEL: 2 5 " SF-TS
  SF-TQ S" Scanlines:" SF-TS SF-TQ SF-TF
  SF-TCLR S" BUTTON: 14 5 9 " SF-TS
  SF-TQ S" Toggle" SF-TS SF-TQ SF-TF
  SF-TCLR S" LABEL: 25 5 " SF-TS
  SF-TQ S" Off" SF-TS SF-TQ SF-TF
  SF-TCLR S" ENDCARD: 0 6 40" SF-TS SF-TF
  SF-TCLR S" DIVIDER: 7" SF-TS SF-TF
  SF-TCLR S" LABEL: 1 8 " SF-TS
  SF-TQ S" Operator:" SF-TS SF-TQ SF-TF
  SF-TCLR S" INPUT: 12 8 30 " SF-TS
  SF-TQ SF-TQ SF-TF
  SF-TCLR S" DIVIDER: 10" SF-TS SF-TF
  SF-TCLR S" BUTTON: 2 12 9 " SF-TS
  SF-TQ S" Apply" SF-TS SF-TQ SF-TF
  SF-TCLR S" BUTTON: 14 12 10 " SF-TS
  SF-TQ S" Cancel" SF-TS SF-TQ SF-TF
  SF-TCLR S" DIVIDER: 14" SF-TS SF-TF
  SF-TCLR S" LABEL: 1 16 " SF-TS
  SF-TQ S" (status)" SF-TS SF-TQ SF-TF
  SF-TCLR S" END-FORM:" SF-TS SF-TF
;
SF-BUILD

HEX
: SF-REGISTER
  SF-DATA 2 S" SETTINGS-FORM"
  CATALOG-REGISTER ;
SF-REGISTER

PREVIOUS
DECIMAL
