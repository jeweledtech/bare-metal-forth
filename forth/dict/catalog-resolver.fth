\ ====================================================================
\ CATALOG: CATALOG-RESOLVER
\ CATEGORY: system
\ SOURCE: hand-written
\ SOURCE-BINARY: none
\ VENDOR-ID: none
\ DEVICE-ID: none
\ PORTS: none
\ MMIO: none
\ CONFIDENCE: high
\ ====================================================================
\
\ Vocabulary dependency resolver.  Reads the catalog block (block 1)
\ to map vocabulary names to block numbers, then auto-loads
\ dependencies declared in REQUIRES: lines.
\
\ Usage:
\   S" SERIAL-16550" LOAD-VOCAB
\
\ This will:
\   1. Look up SERIAL-16550 in the catalog (block 1)
\   2. Scan its first block for REQUIRES: lines
\   3. Recursively load each dependency first
\   4. LOAD the vocabulary itself
\
\ Circular dependency detection: a small stack of "currently loading"
\ names prevents infinite loops.
\
\ ====================================================================

VOCABULARY CATALOG-RESOLVER
CATALOG-RESOLVER DEFINITIONS
HEX

\ ---- Constants ----
1 CONSTANT CATALOG-BLK       \ Block number containing the catalog
8 CONSTANT MAX-LOADING        \ Max concurrent loads (circ. detect)
40 CONSTANT MAX-NAME           \ Max vocab name length (64 chars)

\ ---- Loading stack for circular dependency detection ----
\ Each entry: 1 byte length + MAX-NAME bytes of name
VARIABLE LOADING-DEPTH
CREATE LOADING-NAMES  MAX-LOADING MAX-NAME 1+ * ALLOT

\ ---- Helper: compare two counted regions ----
\ ( addr1 len1 addr2 len2 -- flag )
: STR=  ( a1 n1 a2 n2 -- flag )
    ROT OVER <> IF  DROP DROP DROP FALSE EXIT  THEN
    \ lengths match, compare bytes
    0 DO
        OVER I + C@  OVER I + C@  <> IF
            DROP DROP FALSE UNLOOP EXIT
        THEN
    LOOP
    DROP DROP TRUE
;

\ ---- Push name onto loading stack ----
\ ( addr len -- flag )  flag=TRUE if added, FALSE if already there or full
: LOADING-PUSH  ( addr len -- flag )
    \ Check for circular dependency
    LOADING-DEPTH @ MAX-LOADING >= IF  DROP DROP FALSE EXIT  THEN
    \ Check if already in stack
    LOADING-DEPTH @ 0 ?DO
        LOADING-NAMES I MAX-NAME 1+ * +   \ entry addr
        DUP C@                              \ entry length
        SWAP 1+                             \ entry name addr
        2OVER                               \ copy search name
        STR= IF
            DROP DROP FALSE UNLOOP EXIT     \ circular!
        THEN
    LOOP
    \ Add to stack
    LOADING-NAMES LOADING-DEPTH @ MAX-NAME 1+ * +
    2DUP 1+ 2OVER DROP SWAP CMOVE     \ copy name bytes
    OVER SWAP C!                        \ store length
    DROP DROP                           \ clean up originals
    1 LOADING-DEPTH +!
    TRUE
;

\ ---- Pop name from loading stack ----
: LOADING-POP  ( -- )
    LOADING-DEPTH @ 0> IF  -1 LOADING-DEPTH +!  THEN
;

\ ---- Reset loading stack ----
: LOADING-RESET  ( -- )
    0 LOADING-DEPTH !
;

\ ---- Catalog lookup ----
\ Search catalog block for a vocabulary name, return its start block.
\ ( addr len -- block# TRUE | FALSE )
: CATALOG-FIND  ( addr len -- blk true | false )
    CATALOG-BLK BLOCK              \ get catalog block buffer address
    \ The catalog is 16 lines x 64 chars.  Skip first line (header).
    \ Each data line: <NAME> <SPACE> <BLOCK#>
    10 1 DO                         \ scan lines 1-15 (skip line 0)
        DUP I 40 * +               \ line start address
        DUP 40 + SWAP              \ line end, line start
        \ Skip leading spaces
        BEGIN  DUP C@ 20 = OVER 2 PICK < AND  WHILE  1+  REPEAT
        \ Check if line is blank
        DUP C@ 20 <= IF  DROP DROP  ELSE
            \ Parse name: find space after name
            DUP  ( start-of-name start-of-name )
            BEGIN  DUP C@ 20 <> OVER 5 PICK < AND  WHILE  1+  REPEAT
            OVER -   ( line-start name-start name-len )
            \ Compare with search name
            4 PICK 4 PICK  3 PICK 3 PICK  STR= IF
                \ Match! Parse block number after the space
                2 PICK 2 PICK +  \ past-name address
                BEGIN  DUP C@ 20 = WHILE  1+  REPEAT  \ skip spaces
                \ Parse decimal number
                0 SWAP
                BEGIN
                    DUP C@ DUP 30 >= SWAP 39 <= AND
                WHILE
                    SWAP A * OVER C@ 30 - + SWAP 1+
                REPEAT
                DROP  ( block# )
                \ Clean up and return
                SWAP DROP  SWAP DROP  SWAP DROP  SWAP DROP
                TRUE
                UNLOOP EXIT
            THEN
            DROP DROP  ( clean up name-start name-len )
        THEN
        DROP   \ drop line-end
    LOOP
    DROP   \ drop catalog buffer address
    DROP DROP   \ drop search addr len
    FALSE
;

\ ---- Parse REQUIRES from a block ----
\ Scan block for "REQUIRES:" lines and load each dependency.
\ ( blk# -- )
: RESOLVE-DEPS  ( blk# -- )
    BLOCK                           \ get block buffer
    10 0 DO                          \ scan first 16 lines
        DUP I 40 * +                \ line address
        \ Look for "REQUIRES:" pattern
        \ Check if line contains "REQUIRES:"
        DUP 40 + SWAP
        FALSE  ( found-flag )
        2 PICK 40 + 2 PICK DO
            I     C@ 52 = IF   \ 'R'
            I 1+  C@ 45 = IF   \ 'E'
            I 2+  C@ 51 = IF   \ 'Q'
            I 3+  C@ 55 = IF   \ 'U'
            I 4+  C@ 49 = IF   \ 'I'
            I 5+  C@ 52 = IF   \ 'R'
            I 6+  C@ 45 = IF   \ 'E'
            I 7+  C@ 53 = IF   \ 'S'
            I 8+  C@ 3A = IF   \ ':'
                DROP TRUE
                I 9 +           \ address after "REQUIRES:"
                LEAVE
            THEN THEN THEN THEN THEN THEN THEN THEN THEN
        LOOP
        IF
            \ Found REQUIRES: — parse vocab name after it
            \ Skip spaces
            BEGIN  DUP C@ 20 =  WHILE  1+  REPEAT
            \ Extract name (until space or '(' or end)
            DUP
            BEGIN
                DUP C@ DUP 20 <> SWAP 28 <> AND   \ not space, not '('
                OVER C@ 0<> AND                     \ not NUL
            WHILE  1+  REPEAT
            OVER -  ( name-addr name-len )
            DUP 0> IF
                \ Recursively load this dependency
                2DUP LOAD-VOCAB-INNER
            THEN
            DROP DROP
        THEN
        DROP DROP  \ clean up line bounds
    LOOP
    DROP           \ drop block buffer address
;

\ ---- Core vocab loading (recursive) ----
: LOAD-VOCAB-INNER  ( addr len -- )
    \ Push onto loading stack (detects circular deps)
    2DUP LOADING-PUSH 0= IF
        DROP DROP EXIT              \ already loading or stack full
    THEN
    \ Look up in catalog
    2DUP CATALOG-FIND IF
        \ Found at block#
        DUP RESOLVE-DEPS           \ load dependencies first
        LOAD                        \ load the vocabulary itself
    ELSE
        \ Not found — silently skip (dependency may be a kernel builtin)
    THEN
    DROP DROP
    LOADING-POP
;

\ ---- Public interface ----
\ ( addr len -- )
: LOAD-VOCAB  ( addr len -- )
    LOADING-RESET
    LOAD-VOCAB-INNER
;

FORTH DEFINITIONS
DECIMAL
