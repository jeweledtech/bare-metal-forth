\ ============================================
\ CATALOG: CATALOG-RESOLVER
\ CATEGORY: system
\ SOURCE: hand-written
\ SOURCE-BINARY: none
\ VENDOR-ID: none
\ DEVICE-ID: none
\ PORTS: none
\ MMIO: none
\ CONFIDENCE: high
\ ============================================
\
\ Vocabulary dependency resolver.
\ Reads the catalog block (block 1) to map
\ vocabulary names to block numbers, then
\ auto-loads dependencies (REQUIRES: lines).
\
\ Usage:
\   S" SERIAL-16550" LOAD-VOCAB
\
\ This will:
\   1. Look up SERIAL-16550 in the catalog
\   2. Scan its first block for REQUIRES:
\   3. Recursively load each dependency first
\   4. LOAD the vocabulary itself
\
\ Circular dependency detection: a small
\ stack of "currently loading" names
\ prevents infinite loops.
\
\ ============================================

VOCABULARY CATALOG-RESOLVER
CATALOG-RESOLVER DEFINITIONS
HEX

\ ---- Constants ----
1 CONSTANT CATALOG-BLK
4 CONSTANT CAT-NBLKS
8 CONSTANT MAX-LOADING
40 CONSTANT MAX-NAME

\ ---- Loading stack (circ. detect) ----
\ Each entry: 1 byte len + MAX-NAME bytes
VARIABLE LOADING-DEPTH
CREATE LOADING-NAMES
  MAX-LOADING MAX-NAME 1+ * ALLOT

\ ---- Forward ref for mutual recursion ----
VARIABLE 'RESOLVE-DEPS

\ ---- Helper: compare two strings ----
\ ( addr1 len1 addr2 len2 -- flag )
: STR=  ( a1 n1 a2 n2 -- flag )
    ROT OVER <> IF
        DROP DROP DROP FALSE EXIT
    THEN
    0 DO
        OVER I + C@  OVER I + C@
        <> IF
            DROP DROP FALSE
            UNLOOP EXIT
        THEN
    LOOP
    DROP DROP TRUE
;

\ ---- Push name onto loading stack ----
\ ( addr len -- flag )
\ TRUE if added, FALSE if circular/full
VARIABLE LP-EA
: LOADING-PUSH  ( addr len -- flag )
    LOADING-DEPTH @
    MAX-LOADING >= IF
        DROP DROP FALSE EXIT
    THEN
    LOADING-DEPTH @ DUP 0> IF
        0 DO
            LOADING-NAMES
            I MAX-NAME 1+ * +
            DUP 1+ SWAP C@
            3 PICK 3 PICK
            STR= IF
                DROP DROP FALSE
                UNLOOP EXIT
            THEN
        LOOP
    ELSE
        DROP
    THEN
    LOADING-NAMES
    LOADING-DEPTH @ MAX-NAME 1+ * +
    LP-EA !
    DUP LP-EA @ C!
    LP-EA @ 1+ SWAP CMOVE
    1 LOADING-DEPTH +!
    TRUE
;

\ ---- Pop name from loading stack ----
: LOADING-POP  ( -- )
    LOADING-DEPTH @ 0> IF
        -1 LOADING-DEPTH +!
    THEN
;

\ ---- Reset loading stack ----
: LOADING-RESET  ( -- )
    0 LOADING-DEPTH !
;

\ ---- Catalog lookup ----
\ Variable-based: no complex stack juggling.
VARIABLE CF-NA
VARIABLE CF-NL
VARIABLE CF-BUF
VARIABLE CF-LS
VARIABLE CF-LE
VARIABLE CF-WS
VARIABLE CF-WL
VARIABLE CF-NUM

\ Parse decimal number at address.
: CF-PARSE-NUM ( addr -- addr' n )
  0 CF-NUM !
  BEGIN
    DUP C@ DUP
    30 >= SWAP 39 <= AND
  WHILE
    CF-NUM @ A *
    OVER C@ 30 - + CF-NUM !
    1+
  REPEAT
  CF-NUM @ ;

\ Match one catalog line against name.
\ Line at CF-LS, end at CF-LE.
\ Catalog format: NAME START END
\ Returns start end TRUE or FALSE.
: CF-MATCH-LINE ( -- s e T | F )
  CF-LS @
  BEGIN
    DUP C@ 20 =
    OVER CF-LE @ < AND
  WHILE 1+ REPEAT
  DUP C@ 20 <= IF DROP FALSE EXIT THEN
  DUP CF-WS !
  BEGIN
    DUP C@ 20 <>
    OVER CF-LE @ < AND
  WHILE 1+ REPEAT
  CF-WS @ - CF-WL !
  CF-WL @ CF-NL @ <> IF
    FALSE EXIT
  THEN
  CF-WS @ CF-WL @
  CF-NA @ CF-NL @ STR= IF
    CF-WS @ CF-WL @ +
    BEGIN DUP C@ 20 = WHILE
      1+
    REPEAT
    CF-PARSE-NUM SWAP
    BEGIN DUP C@ 20 = WHILE
      1+
    REPEAT
    CF-PARSE-NUM
    SWAP DROP TRUE
  ELSE
    FALSE
  THEN ;

\ Search all catalog blocks for vocab name.
\ Returns start end TRUE or FALSE.
: CATALOG-FIND ( a l -- s e T | F )
  CF-NL ! CF-NA !
  CAT-NBLKS 0 DO
    CATALOG-BLK I + BLOCK CF-BUF !
    10 1 DO
      CF-BUF @ I 40 * + CF-LS !
      CF-LS @ 40 + CF-LE !
      CF-MATCH-LINE IF
        TRUE UNLOOP UNLOOP EXIT
      THEN
    LOOP
  LOOP
  FALSE ;

\ ---- Core vocab loading (recursive) ----
\ Defined BEFORE RESOLVE-DEPS so it can
\ be referenced. Uses 'RESOLVE-DEPS
\ variable for the mutual callback.
: LOAD-VOCAB-INNER  ( addr len -- )
    2DUP LOADING-PUSH 0= IF
        DROP DROP EXIT
    THEN
    2DUP CATALOG-FIND IF
        OVER
        'RESOLVE-DEPS @ EXECUTE
        THRU
    ELSE
        \ Not found -- skip
    THEN
    DROP DROP
    LOADING-POP
;

\ ---- Parse REQUIRES from a block ----
\ Scan block for "REQUIRES:" lines
\ and load each dependency.
\ ( blk# -- )
VARIABLE RD-BLK
VARIABLE RD-BUFP
CREATE RD-BUF 42 ALLOT

: RESOLVE-DEPS  ( blk# -- )
    DUP RD-BLK !
    BLOCK RD-BUFP !
    10 0 DO
        RD-BUFP @ I 40 * +
        DUP 40 + SWAP
        FALSE
        2 PICK 40 + 2 PICK DO
            I     C@ 52 = IF
            I 1 + C@ 45 = IF
            I 2 + C@ 51 = IF
            I 3 + C@ 55 = IF
            I 4 + C@ 49 = IF
            I 5 + C@ 52 = IF
            I 6 + C@ 45 = IF
            I 7 + C@ 53 = IF
            I 8 + C@ 3A = IF
                DROP I 9 +
                TRUE LEAVE
            THEN THEN THEN
            THEN THEN THEN
            THEN THEN THEN
        LOOP
        IF
            BEGIN
                DUP C@ 20 =
            WHILE 1+ REPEAT
            DUP
            BEGIN
                DUP C@ DUP
                20 <>
                SWAP 28 <> AND
                OVER C@ 0<> AND
            WHILE 1+ REPEAT
            OVER -
            DUP 0> IF
                OVER RD-BUF
                2 PICK CMOVE
                SWAP DROP
                RD-BLK @ SWAP
                RD-BUF SWAP
                LOAD-VOCAB-INNER
                RD-BLK !
                RD-BLK @ BLOCK
                RD-BUFP !
            ELSE DROP DROP THEN
        THEN
        DROP DROP
    LOOP
;

\ Patch the forward reference
' RESOLVE-DEPS 'RESOLVE-DEPS !

\ Switch compilation to FORTH but keep
\ CATALOG-RESOLVER searchable so the
\ compiler resolves LOADING-RESET and
\ LOAD-VOCAB-INNER by XT at compile time.
FORTH DEFINITIONS
ALSO CATALOG-RESOLVER

: LOAD-VOCAB  ( addr len -- )
    LOADING-RESET
    LOAD-VOCAB-INNER
;

PREVIOUS
DECIMAL
