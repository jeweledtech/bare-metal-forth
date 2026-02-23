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
: LOADING-PUSH  ( addr len -- flag )
    LOADING-DEPTH @
    MAX-LOADING >= IF
        DROP DROP FALSE EXIT
    THEN
    LOADING-DEPTH @ DUP 0> IF
        0 DO
            LOADING-NAMES
            I MAX-NAME 1+ * +
            DUP C@
            SWAP 1+
            2OVER
            STR= IF
                DROP DROP FALSE
                UNLOOP EXIT
            THEN
        LOOP
    ELSE
        DROP
    THEN
    LOADING-NAMES
    LOADING-DEPTH @
    MAX-NAME 1+ * +
    2DUP 1+
    2OVER DROP SWAP CMOVE
    OVER SWAP C!
    DROP DROP
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
\ Search catalog block for a vocab name.
\ ( addr len -- blk true | false )
: CATALOG-FIND  ( addr len -- blk T|F )
    CATALOG-BLK BLOCK
    10 1 DO
        DUP I 40 * +
        DUP 40 + SWAP
        BEGIN
            DUP C@ 20 =
            OVER 2 PICK < AND
        WHILE 1+ REPEAT
        DUP C@ 20 <= IF
            DROP DROP
        ELSE
            DUP
            BEGIN
                DUP C@ 20 <>
                OVER 5 PICK < AND
            WHILE 1+ REPEAT
            OVER -
            4 PICK 4 PICK
            3 PICK 3 PICK
            STR= IF
                2 PICK 2 PICK +
                BEGIN
                    DUP C@ 20 =
                WHILE 1+ REPEAT
                0 SWAP
                BEGIN
                    DUP C@ DUP
                    30 >= SWAP 39 <=
                    AND
                WHILE
                    SWAP A *
                    OVER C@ 30 - +
                    SWAP 1+
                REPEAT
                DROP
                SWAP DROP
                SWAP DROP
                SWAP DROP
                SWAP DROP
                TRUE
                UNLOOP EXIT
            THEN
            DROP DROP
        THEN
        DROP
    LOOP
    DROP
    DROP DROP
    FALSE
;

\ ---- Core vocab loading (recursive) ----
\ Defined BEFORE RESOLVE-DEPS so it can
\ be referenced. Uses 'RESOLVE-DEPS
\ variable for the mutual callback.
: LOAD-VOCAB-INNER  ( addr len -- )
    2DUP LOADING-PUSH 0= IF
        DROP DROP EXIT
    THEN
    2DUP CATALOG-FIND IF
        DUP
        'RESOLVE-DEPS @ EXECUTE
        LOAD
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
: RESOLVE-DEPS  ( blk# -- )
    BLOCK
    10 0 DO
        DUP I 40 * +
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
                DROP TRUE
                I 9 +
                LEAVE
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
                2DUP
                LOAD-VOCAB-INNER
            THEN
            DROP DROP
        THEN
        DROP DROP
    LOOP
    DROP
;

\ Patch the forward reference
' RESOLVE-DEPS 'RESOLVE-DEPS !

\ ---- Public interface ----
\ ( addr len -- )
: LOAD-VOCAB  ( addr len -- )
    LOADING-RESET
    LOAD-VOCAB-INNER
;

FORTH DEFINITIONS
DECIMAL
