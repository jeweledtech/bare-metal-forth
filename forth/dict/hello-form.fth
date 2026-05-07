\ ============================================
\ CATALOG: HELLO-FORM
\ CATEGORY: form
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ ============================================
\ Minimal test form for engine generalization.
\ Proves FORM-LOAD/FORM-WIRE work with zero
\ NOTEPAD-specific code.
\ ============================================

ALSO CATALOG-RESOLVER
HEX

CREATE HF-DATA 400 ALLOT
HF-DATA 400 20 FILL

VARIABLE HF-PTR
HF-DATA HF-PTR !

CREATE HF-TMP 40 ALLOT
VARIABLE HF-TP

: HF-TCLR  0 HF-TP ! ;
: HF-TC ( c -- )
  HF-TMP HF-TP @ + C!
  1 HF-TP +! ;
: HF-TS ( a l -- )
  0 DO DUP I + C@ HF-TC LOOP
  DROP ;
: HF-TQ  22 HF-TC ;

: HF-TF
  HF-TMP HF-PTR @ HF-TP @ CMOVE
  HF-PTR @ HF-TP @ +
  40 HF-TP @ - 20 FILL
  40 HF-PTR +! ;

DECIMAL

: HF-BUILD
  HF-TCLR S" FORM: hello" HF-TS HF-TF
  HF-TCLR S" LABEL: 1 1 " HF-TS
  HF-TQ S" Hello Form Test" HF-TS
  HF-TQ HF-TF
  HF-TCLR S" DIVIDER: 2" HF-TS HF-TF
  HF-TCLR S" LABEL: 1 4 " HF-TS
  HF-TQ S" Type:" HF-TS HF-TQ HF-TF
  HF-TCLR S" INPUT: 7 4 30 " HF-TS
  HF-TQ HF-TQ HF-TF
  HF-TCLR S" BUTTON: 1 6 8 " HF-TS
  HF-TQ S" Go" HF-TS HF-TQ HF-TF
  HF-TCLR S" DIVIDER: 8" HF-TS HF-TF
  HF-TCLR S" LABEL: 1 10 " HF-TS
  HF-TQ S" (status)" HF-TS HF-TQ HF-TF
  HF-TCLR S" END-FORM:" HF-TS HF-TF
;
HF-BUILD

HEX
: HF-REGISTER
  HF-DATA 3 S" HELLO-FORM"
  CATALOG-REGISTER ;
HF-REGISTER

PREVIOUS
DECIMAL
