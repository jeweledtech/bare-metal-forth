\ ui-check.fth - checkboxes and radio buttons in a form
\ PRELOAD: DIALOG
\ (private TASK_READ_AND_REBUILD_FORMS step 9, part 4;
\ pre-registered 2026-11-18 before the first run). DIALOG
\ reads CHECK: x y "text" id and RADIO: x y "text" id g
\ through UI-PARSER's DL-HOOK: types 10 and 11, 4 cells and
\ the text, which UI-CORE draws through DIALOG's DL-PAINT and
\ UI-EVENTS focuses through DL-FOCUS?. A checkbox draws [ ]
\ or [x], a radio ( ) or (*), a space, then the text at x+4.
\ Space toggles a checkbox, or sets a radio and clears the
\ others of its group; the dialog goes on. CHECKED? reads one
\ by control ID. The form, built line by line (' stands for
\ the quote): 0 a checkbox, 1-3 radios in groups 1 1 2, 4 a
\ disabled checkbox with no text, 5 a button.
ONLY FORTH DEFINITIONS ALSO UI-CORE ALSO UI-PARSER
ALSO UI-EVENTS ALSO DIALOG DECIMAL
CREATE QL-BUF 64 ALLOT
: QL ( a n -- ) DUP >R QL-BUF SWAP CMOVE
  R@ 0 DO QL-BUF I + C@ 39 = IF 34 QL-BUF I + C! THEN LOOP
  QL-BUF R> PROCESS-LINE ;
: CFORM ( -- ) WT-RESET
  S" CHECK: 2 3 'Opt' 7" QL
  S" RADIO: 2 5 'A' 21 1" QL
  S" RADIO: 2 6 'B' 22 1" QL
  S" RADIO: 2 7 'C' 23 2" QL
  S" CHECK: 2 9 '' 8 DISABLED" QL
  S" BUTTON: 2 11 6 'OK' 1" QL ;
: AT@ ( c r -- ch ) VGA-AT C@ ;
: AT-A ( c r -- attr ) VGA-AT 1+ C@ ;
: TY ( i -- type ) DL-WA C@ ;
: ON@ ( i -- n ) DL-WA DCW-ON + C@ ;
: GRP@ ( i -- n ) DL-WA DCW-GRP + C@ ;
: CID@ ( i -- n ) DL-WA WTO-CID + @ ;
: SPK ( -- ) CH-SPACE DR-KEY ;
: TBK ( -- ) KEY-TAB DR-KEY ;
SUITE ui-check
T{ C1 CFORM WT-COUNT @ 0 TY 1 TY 3 TY 4 TY -> 6 10 11 11 10 }T
T{ C2 0 CID@ 1 GRP@ 2 GRP@ 3 GRP@ 3 CID@ -> 7 1 1 2 23 }T
T{ C3 0 DL-WA W-ADDR ! W-W@ 4 DL-WA W-ADDR ! W-W@ -> 7 4 }T
T{ C4 4 WIDGET-ENA? 0= 0 WIDGET-ENA? 0= -> -1 0 }T
T{ C5 10 FOCUSABLE? 11 FOCUSABLE? 12 FOCUSABLE? 1 FOCUSABLE?
  -> -1 -1 0 0 }T
T{ C6 IDCANCEL DR-START FOCUS-IDX @ FORM-RENDER 2 3 AT@
  3 3 AT@ 4 3 AT@ 5 3 AT@ 6 3 AT@ -> 0 91 32 93 32 79 }T
T{ C7 2 5 AT@ 3 5 AT@ 4 5 AT@ 6 5 AT@ 2 9 AT@
  -> 40 32 41 65 91 }T
T{ C8 2 3 AT-A 6 3 AT-A 5 3 AT-A 2 5 AT-A 2 9 AT-A
  -> 112 112 7 7 8 }T
T{ C9 SPK 0 ON@ DR-DONE @ FORM-RENDER 3 3 AT@ -> 1 0 120 }T
T{ C10 SPK 0 ON@ 7 CHECKED? -> 0 0 }T
T{ C11 TBK FOCUS-IDX @ SPK 1 ON@ 2 ON@ 3 ON@ -> 1 1 0 0 }T
T{ C12 TBK SPK 1 ON@ 2 ON@ 3 ON@ -> 0 1 0 }T
T{ C13 TBK SPK 1 ON@ 2 ON@ 3 ON@ -> 0 1 1 }T
T{ C14 SPK 3 ON@ FORM-RENDER 3 6 AT@ 3 5 AT@ 3 7 AT@
  -> 1 42 32 42 }T
T{ C15 22 CHECKED? 21 CHECKED? 23 CHECKED? 99 CHECKED?
  1 CHECKED?
  -> -1 0 -1 0 0 }T
T{ C16 TBK FOCUS-IDX @ -> 5 }T
T{ C17 KEY-ENTER DR-KEY DR-ID @ DR-DONE @ -> 1 -1 }T
T{ C18 CFORM 0 ON@ 1 ON@ 22 CHECKED? DEPTH -> 0 0 0 0 }T
END-SUITE
ONLY FORTH DEFINITIONS
