\ ============================================
\ CATALOG: FILE-BROWSER-FORM
\ CATEGORY: form
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ ============================================
\ In-memory form data for File Browser.
\ CREATE buffer + CATALOG-REGISTER.
\ No block disk needed.
\
\ Note: button label "Close" avoids collision
\ with NOTEPAD's "Exit" in shared registry.
\ ============================================

ALSO CATALOG-RESOLVER
HEX

CREATE BF-DATA 400 ALLOT
BF-DATA 400 20 FILL

VARIABLE BF-PTR
BF-DATA BF-PTR !

CREATE BF-TMP 40 ALLOT
VARIABLE BF-TP

: BF-TCLR  0 BF-TP ! ;
: BF-TC ( c -- )
  BF-TMP BF-TP @ + C!
  1 BF-TP +! ;
: BF-TS ( a l -- )
  0 DO DUP I + C@ BF-TC LOOP
  DROP ;
: BF-TQ  22 BF-TC ;

\ Flush temp buf as one 64-byte line
: BF-TF
  BF-TMP BF-PTR @ BF-TP @ CMOVE
  BF-PTR @ BF-TP @ +
  40 BF-TP @ - 20 FILL
  40 BF-PTR +! ;

DECIMAL

\ ---- Form data (11 lines x 64 bytes) ----
\ S" in colon def avoids BLK truncation bug.

: BF-BUILD
  BF-TCLR S" FORM: file-browser" BF-TS BF-TF
  BF-TCLR S" LABEL: 1 0 " BF-TS
  BF-TQ S" ForthOS File Browser" BF-TS
  BF-TQ BF-TF
  BF-TCLR S" DIVIDER: 1" BF-TS BF-TF
  BF-TCLR S" LABEL: 1 2 " BF-TS
  BF-TQ S" Path:" BF-TS BF-TQ BF-TF
  BF-TCLR S" BUTTON: 60 2 8 " BF-TS
  BF-TQ S" Mount" BF-TS BF-TQ BF-TF
  BF-TCLR S" DIVIDER: 3" BF-TS BF-TF
  BF-TCLR S" DIVIDER: 22" BF-TS BF-TF
  BF-TCLR S" LABEL: 1 23 " BF-TS
  BF-TQ S" Enter=open Bs=up Esc=menu" BF-TS
  BF-TQ BF-TF
  BF-TCLR S" BUTTON: 58 23 9 " BF-TS
  BF-TQ S" Open" BF-TS BF-TQ BF-TF
  BF-TCLR S" BUTTON: 68 23 9 " BF-TS
  BF-TQ S" Close" BF-TS BF-TQ BF-TF
  BF-TCLR S" END-FORM:" BF-TS BF-TF
;
BF-BUILD

\ ---- Register in catalog ----
HEX
: BF-REGISTER
  BF-DATA 1 S" FILE-BROWSER-FORM"
  CATALOG-REGISTER ;
BF-REGISTER

PREVIOUS
DECIMAL
