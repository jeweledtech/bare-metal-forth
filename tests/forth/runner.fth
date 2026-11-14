\ runner.fth - in-machine test runner (TASK_FORTH_TEST_RUNNER)
\ SUITE name / T{ label code -> expected }T / END-SUITE
\ One case per block line. Leftovers fail: data and return
\ stack depth, STATE, HERE, LATEST, dirty block buffers,
\ keyboard ring. DEFINES / DIRTIES before T{ excuse one case.
DECIMAL
\ RP@ ( -- a ) push ebp ; NEXT = 55 AD FF 20, no assembler
CREATE RP@ HERE @ HERE @ 4 - ! 85 C, 173 C, 255 C, 32 C,
VARIABLE T#    VARIABLE T-FAIL  VARIABLE T-SKIP
VARIABLE T-D0  VARIABLE T-D1    VARIABLE T-NE
VARIABLE T-RP  VARIABLE T-RP2   VARIABLE T-BAD
VARIABLE T-H   VARIABLE T-L     VARIABLE T-OLDHK
VARIABLE T-DEF VARIABLE T-DRT
CREATE T-ACT 16 CELLS ALLOT
CREATE T-LBL 12 ALLOT  CREATE T-SNM 16 ALLOT
CREATE T-FLBL 12 ALLOT \ label of the first failing case
163936 CONSTANT T-BHDR  \ 0x28060: 4 headers x 12 B
: T-TYPEZ ( a -- ) BEGIN DUP C@ DUP WHILE EMIT 1+ REPEAT
  DROP DROP ;
: T-D. ( u -- ) 48 + EMIT ;
: T-N. ( u -- ) DUP 99 > IF DUP 100 / T-D. THEN
  DUP 9 > IF DUP 100 MOD 10 / T-D. THEN 10 MOD T-D. ;
: T-DIRTY ( -- mask ) 0 4 0 DO T-BHDR I 12 * + 4 + @
  2 AND IF 1 I LSHIFT OR THEN LOOP ;
: T-EOL ( -- ) ADDR-TOIN @ 64 / 1+ 64 * ADDR-TOIN ! ;
: T-ABORTED ( -- ) T-OLDHK @ ABORT-HOOK ! CR ." RESULT "
  T-SNM T-TYPEZ ."  ABORT case " T-LBL T-TYPEZ CR ;
: SUITE ( "name" -- ) WORD T-SNM 15 CMOVE 0 T-SNM 15 + C!
  0 T# ! 0 T-FAIL ! 0 T-SKIP ! 0 T-DEF ! 0 T-DRT ! 0 T-LBL C!
  ABORT-HOOK @ T-OLDHK ! ['] T-ABORTED ABORT-HOOK ! ;
: DEFINES ( -- ) 1 T-DEF ! ;
: DIRTIES ( -- ) 1 T-DRT ! ;
: T{ ( "label" -- ) WORD T-LBL 11 CMOVE 0 T-LBL 11 + C!
  1 T# +! T-SKIP @ IF T-EOL EXIT THEN T-LBL T-TYPEZ SPACE
  DEPTH T-D0 ! RP@ T-RP ! HERE @ T-H ! LATEST @ T-L ! ;
: T-DROP ( -- ) BEGIN DEPTH T-D0 @ > WHILE DROP REPEAT ;
: -> ( i*x -- ) DEPTH T-D0 @ - DUP T-D1 ! DUP 0 > IF
  DUP 16 > IF DROP T-DROP ELSE 0 DO T-ACT I CELLS + !
  LOOP THEN ELSE DROP THEN ; IMMEDIATE
: T-HDR ( -- ) T-BAD @ 0= IF CR ." FAIL " T-SNM T-TYPEZ
  ."  case " T-LBL T-TYPEZ CR T-FAIL @ 0= IF T# @ T-FAIL !
  T-LBL T-FLBL 12 CMOVE THEN THEN 1 T-BAD ! ;
: T-CMP ( j*x -- ) DEPTH T-D0 @ - DUP T-NE ! T-D1 @ <> IF
  T-HDR ."   results: want " T-NE @ . ." got " T-D1 @ . CR
  ELSE T-NE @ 0 > IF T-NE @ 0 DO T-ACT I CELLS + @ OVER <>
  IF T-HDR ."   item " I . ." want " DUP . ." got "
  T-ACT I CELLS + @ . CR THEN DROP LOOP THEN THEN T-DROP ;
: T-STATE ( -- ) T-RP2 @ T-RP @ <> IF T-HDR ."   RSTACK "
  T-RP @ T-RP2 @ - 4 / . CR THEN STATE @ IF T-HDR
  ."   STATE " STATE @ . CR 0 STATE ! THEN T-DEF @ 0= IF
  HERE @ T-H @ <> IF T-HDR ."   HERE " HERE @ T-H @ - . CR
  THEN LATEST @ T-L @ <> IF T-HDR ."   LATEST moved" CR
  THEN THEN T-DRT @ 0= IF T-DIRTY DUP IF T-HDR
  ."   BLK DIRTY mask " . CR ELSE DROP THEN THEN
  KB-RING-COUNT @ IF T-HDR ."   KB " KB-RING-COUNT @ . CR
  THEN ;
: }T ( j*x -- ) RP@ T-RP2 ! 0 T-BAD ! T-CMP T-STATE
  0 T-DEF ! 0 T-DRT ! T-BAD @ IF 1 T-SKIP ! THEN ; IMMEDIATE
: END-SUITE ( -- ) T-OLDHK @ ABORT-HOOK ! CR ." RESULT "
  T-SNM T-TYPEZ T-FAIL @ IF ."  FAIL case " T-FLBL T-TYPEZ
  SPACE T-FAIL @ T-N. ELSE ."  PASS " T# @ T-N. THEN ." /"
  T# @ T-N. CR ;
ONLY FORTH DEFINITIONS
