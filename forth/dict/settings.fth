\ ============================================
\ CATALOG: SETTINGS
\ CATEGORY: app
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ REQUIRES: SETTINGS-FORM
\ REQUIRES: UI-CORE
\ REQUIRES: UI-PARSER
\ REQUIRES: UI-EVENTS
\ REQUIRES: GUI-HARVEST
\ REQUIRES: CATALOG-RESOLVER
\ ============================================
\
\ Settings panel: Milestone 4 (fourth panel).
\ Tests forty-panel hypothesis: declaration vs
\ handler ratio.
\
\ Findings (3 framework gaps surfaced):
\ #1 DROPBOX non-interactive (no XT/buffer)
\ #2 ATTR-NORM is CONSTANT (no live effect)
\ #3 Label pool leaks (no in-place mutation)
\ Uses BUTTONs for cycling as workaround.
\
\ Usage:
\   USING SETTINGS
\   SETTINGS-RUN
\
\ ============================================

VOCABULARY SETTINGS
SETTINGS DEFINITIONS
ALSO UI-CORE
ALSO UI-EVENTS
ALSO UI-PARSER
ALSO GUI-HARVEST
ALSO CATALOG-RESOLVER

HEX

\ ---- Constants (outside colon defs) ------
DECIMAL
2 CONSTANT SC-ATTR-GRN
6 CONSTANT SC-ATTR-AMB
15 CONSTANT SC-ATTR-WHT
3 CONSTANT SC-NUM-COLORS
16 CONSTANT SC-DEMO-ROW
80 CONSTANT SC-VCOLS
32 CONSTANT SC-SPC
HEX

\ ---- Setting VARIABLEs -------------------
VARIABLE SC-COLOR
VARIABLE SC-SCAN
VARIABLE SC-ATTR

\ ---- Widget index VARIABLEs --------------
VARIABLE SC-CLR-WI
VARIABLE SC-SL-WI
VARIABLE SC-STAT-WI
VARIABLE SC-INP-WI

\ ---- Label-update helper VARIABLEs -------
VARIABLE SC-SL
VARIABLE SC-SO
VARIABLE SC-SA

\ ---- Counted-string helper ---------------
: SC-COUNT ( a -- a+1 len ) DUP 1+ SWAP C@ ;

\ ---- Color name strings ------------------
CREATE SC-CN-GRN 5 C,
  CHAR G C, CHAR r C, CHAR e C,
  CHAR e C, CHAR n C,
CREATE SC-CN-AMB 5 C,
  CHAR A C, CHAR m C, CHAR b C,
  CHAR e C, CHAR r C,
CREATE SC-CN-WHT 5 C,
  CHAR W C, CHAR h C, CHAR i C,
  CHAR t C, CHAR e C,

\ ---- Scanlines name strings ---------------
CREATE SC-SN-OFF 3 C,
  CHAR O C, CHAR f C, CHAR f C,
CREATE SC-SN-ON 2 C,
  CHAR O C, CHAR n C,

\ ---- Status initial match string ----------
DECIMAL
CREATE SC-INIT-STAT 8 C,
  CHAR ( C, CHAR s C, CHAR t C,
  CHAR a C, CHAR t C, CHAR u C,
  CHAR s C, CHAR ) C,
HEX

\ ---- Apply prefix string ------------------
CREATE SC-PFX 9 C,
  CHAR A C, CHAR p C, CHAR p C,
  CHAR l C, CHAR i C, CHAR e C,
  CHAR d C, CHAR : C, 20 C,

\ ---- Status scratch buffer ----------------
DECIMAL
CREATE SC-SBUF 40 ALLOT
VARIABLE SC-SLEN
HEX

\ ---- Block persistence --------------------
DECIMAL
199 CONSTANT SET-BLK
VARIABLE SET-BUF
VARIABLE SET-I
VARIABLE SET-ACC
VARIABLE SET-POS
VARIABLE SET-MAX
CREATE NBUF 8 ALLOT

: SET-LINE ( n -- a )
  64 * SET-BUF @ + ;

: SET-MAGIC? ( -- f )
  0 SET-LINE
  DUP C@ 70 =
  OVER 1 + C@ 83 = AND
  OVER 2 + C@ 69 = AND
  OVER 3 + C@ 84 = AND
  SWAP 4 + C@ 49 = AND ;

: >VALUE ( a -- a' )
  0 SET-I !
  BEGIN
    DUP C@ 61 <>
    SET-I @ 63 < AND
  WHILE
    1 +  1 SET-I +!
  REPEAT  1 + ;

: DIGITS>N ( a -- n )
  0 SET-ACC !
  BEGIN
    DUP C@ 48 -
    DUP 0 >= OVER 10 < AND
  WHILE
    SET-ACC @ 10 * +
    SET-ACC !  1 +
  REPEAT
  2DROP  SET-ACC @ ;

: N>TEXT ( n a -- )
  SWAP  8 SET-POS !
  BEGIN
    10 /MOD SWAP 48 +
    -1 SET-POS +!
    NBUF SET-POS @ + C!
    DUP 0=
  UNTIL DROP
  NBUF SET-POS @ +
  SWAP
  8 SET-POS @ - CMOVE ;

\ line-bounded: last non-space+1 within
\ SET-MAX bytes from a
: TEXT-LEN ( a -- len )
  0 SET-I !  0 SET-ACC !
  BEGIN SET-I @ SET-MAX @ <
  WHILE
    DUP SET-I @ + C@ 32 <> IF
      SET-I @ 1 + SET-ACC !
    THEN
    1 SET-I +!
  REPEAT
  DROP  SET-ACC @ ;

: SET-DEFAULTS ( -- )
  0 SC-COLOR !  0 SC-SCAN ! ;

: SET-LOAD ( blk -- )
  BLOCK SET-BUF !
  SET-MAGIC? 0= IF
    SET-DEFAULTS EXIT
  THEN
  1 SET-LINE >VALUE
  DIGITS>N SC-COLOR !
  2 SET-LINE >VALUE
  DIGITS>N SC-SCAN !
  59 SET-MAX !
  3 SET-LINE >VALUE
  DUP TEXT-LEN
  SC-INP-WI @ IV-SET ;

: SET-PUT ( a len n -- )
  SET-LINE SWAP CMOVE ;

: SET-SAVE ( blk -- )
  BUFFER SET-BUF !
  SET-BUF @ 1024 32 FILL
  S" FSET1"  0 SET-PUT
  S" COLOR=" 1 SET-PUT
  SC-COLOR @
  1 SET-LINE 6 + N>TEXT
  S" SCAN="  2 SET-PUT
  SC-SCAN @
  2 SET-LINE 5 + N>TEXT
  S" OPER="  3 SET-PUT
  SC-INP-WI @ IV-GET
  3 SET-LINE 5 +
  SWAP CMOVE
  UPDATE SAVE-BUFFERS ;

HEX

\ ---- Button labels (counted strings) ------
CREATE SC-LBL-CYC 5 C,
  CHAR C C, CHAR y C, CHAR c C,
  CHAR l C, CHAR e C,
CREATE SC-LBL-TOG 6 C,
  CHAR T C, CHAR o C, CHAR g C,
  CHAR g C, CHAR l C, CHAR e C,
CREATE SC-LBL-APL 5 C,
  CHAR A C, CHAR p C, CHAR p C,
  CHAR l C, CHAR y C,
CREATE SC-LBL-CAN 6 C,
  CHAR C C, CHAR a C, CHAR n C,
  CHAR c C, CHAR e C, CHAR l C,

\ ---- SC-SET-LABEL ( addr len wi -- ) ------
\ Update a label widget's displayed text by
\ allocating a new pool string.
: SC-SET-LABEL ( addr len wi -- )
  WT-ESIZE * WT-BASE + W-ADDR !
  SC-SL ! SC-SA !
  POOL-POS @ SC-SO !
  SC-SO @ W-LOFF!
  SC-SA @ POOL-BASE SC-SO @ +
  SC-SL @ CMOVE
  SC-SL @ W-LLEN!
  SC-SL @ POOL-POS +! ;

\ ---- Name lookup words -------------------
: SC-COLOR-NAME ( -- addr len )
  SC-COLOR @ 0 = IF
    SC-CN-GRN SC-COUNT EXIT THEN
  SC-COLOR @ 1 = IF
    SC-CN-AMB SC-COUNT EXIT THEN
  SC-CN-WHT SC-COUNT ;

: SC-SCAN-NAME ( -- addr len )
  SC-SCAN @ IF
    SC-SN-ON SC-COUNT
  ELSE
    SC-SN-OFF SC-COUNT
  THEN ;

: SC-COLOR-ATTR ( -- attr )
  SC-COLOR @ 0 = IF
    SC-ATTR-GRN EXIT THEN
  SC-COLOR @ 1 = IF
    SC-ATTR-AMB EXIT THEN
  SC-ATTR-WHT ;

\ ---- Find widgets by content matching ----
VARIABLE SC-FW-A
VARIABLE SC-FW-L

: SC-FIND-WIDGETS ( -- )
  WT-COUNT @ DUP 0 > IF
    0 DO
      I WT-ESIZE * WT-BASE +
      W-ADDR !
      W-TYPE@ WT-LABEL = IF
        W-LOFF@ W-LLEN@
        SC-FW-L ! SC-FW-A !
        SC-FW-A @ SC-FW-L @
        POOL-STR
        SC-CN-GRN SC-COUNT
        STR=CI IF
          I SC-CLR-WI !
        THEN
        SC-FW-A @ SC-FW-L @
        POOL-STR
        SC-SN-OFF SC-COUNT
        STR=CI IF
          I SC-SL-WI !
        THEN
        SC-FW-A @ SC-FW-L @
        POOL-STR
        SC-INIT-STAT SC-COUNT
        STR=CI IF
          I SC-STAT-WI !
        THEN
      THEN
      W-TYPE@ WT-INPUT = IF
        I SC-INP-WI !
      THEN
    LOOP
  ELSE DROP THEN ;

\ ---- Cycling handlers --------------------

: SC-CYCLE ( -- )
  SC-COLOR @ 1 +
  DUP SC-NUM-COLORS >= IF
    DROP 0
  THEN
  SC-COLOR !
  SC-COLOR-NAME SC-CLR-WI @
  SC-SET-LABEL ;

: SC-TOGGLE ( -- )
  SC-SCAN @ IF 0 ELSE 1 THEN
  SC-SCAN !
  SC-SCAN-NAME SC-SL-WI @
  SC-SET-LABEL ;

\ ---- Apply handler -----------------------
VARIABLE SC-TNA
VARIABLE SC-TNL

: SC-APPLY ( -- )
  SC-PFX 1+ SC-SBUF 9 CMOVE
  9 SC-SLEN !
  SC-COLOR-NAME SC-TNL ! SC-TNA !
  SC-TNA @
  SC-SBUF SC-SLEN @ +
  SC-TNL @ CMOVE
  SC-TNL @ SC-SLEN +!
  SC-SBUF SC-SLEN @
  SC-STAT-WI @ SC-SET-LABEL
  SC-COLOR-ATTR SC-ATTR !
  SET-BLK SET-SAVE ;

\ ---- Cancel handler ----------------------
: SC-CANCEL ( -- )
  1 QUIT-FLAG ! ;

\ ---- Register button handlers ------------
: SC-REGISTER ( -- )
  SC-LBL-CYC SC-COUNT WT-BUTTON
  ['] SC-CYCLE WIDGET-REGISTER
  SC-LBL-TOG SC-COUNT WT-BUTTON
  ['] SC-TOGGLE WIDGET-REGISTER
  SC-LBL-APL SC-COUNT WT-BUTTON
  ['] SC-APPLY WIDGET-REGISTER
  SC-LBL-CAN SC-COUNT WT-BUTTON
  ['] SC-CANCEL WIDGET-REGISTER ;

SC-REGISTER

\ ---- Post-exit color demo ----------------
\ Write colored banner after FORM-RUN exits
\ to prove Apply read the color setting.
\ This is a one-shot demo, not a live system-
\ wide effect. Live effect would require
\ ATTR-NORM to be a VARIABLE (Gap #2).

: SC-DEMO ( -- )
  SC-VCOLS 0 DO
    SC-SPC SC-ATTR @
    I SC-DEMO-ROW VGA-PUTC
  LOOP
  SC-SBUF SC-SLEN @
  2 SC-DEMO-ROW SC-ATTR @ DRAW-AT ;

\ ---- Entry point -------------------------
: SETTINGS-RUN ( -- )
  ." Loading SETTINGS..." CR
  S" SETTINGS-FORM" CATALOG-FIND
  0= IF
    ." Form not found" CR EXIT
  THEN
  FORM-LOAD FORM-WIRE
  SC-FIND-WIDGETS
  SET-BLK SET-LOAD
  0 SC-ATTR !
  SC-COLOR-NAME
  SC-CLR-WI @ SC-SET-LABEL
  SC-SCAN-NAME
  SC-SL-WI @ SC-SET-LABEL
  ." SETTINGS ready" CR
  FORM-RUN
  SC-ATTR @ IF
    SC-DEMO
    ." Color demo at row 16." CR
    ." Press any key..." CR
    KEY DROP VGA-CLS
  THEN
  ." SETTINGS closed" CR ;

ONLY FORTH DEFINITIONS
DECIMAL
