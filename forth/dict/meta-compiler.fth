\ ============================================
\ CATALOG: META-COMPILER
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ REQUIRES: X86-ASM ( T-C, T-, T-HERE %EAX )
\ ============================================
\
\ Self-hosting metacompiler.
\ Builds a new kernel image in a target buffer
\ using X86-ASM for CODE word definitions.
\
\ Usage:
\   USING META-COMPILER
\   META-BUILD
\   META-STATUS
\
\ ============================================

VOCABULARY META-COMPILER
ALSO META-COMPILER DEFINITIONS
ALSO X86-ASM
HEX

\ ---- Target buffer ----
CREATE T-IMAGE 10000 ALLOT
VARIABLE T-ORG
VARIABLE T-SIZE
VARIABLE T-LINK-VAR

\ ---- Target address calculation ----
: T-ADDR ( -- target-addr )
    T-HERE @ T-IMAGE - T-ORG @  +
;

\ ---- Target address translation ----
: T>HOST ( target-addr -- host-addr )
    T-ORG @ - T-IMAGE +
;

\ ---- Target memory access ----
: T-C@ ( taddr -- byte ) T>HOST C@ ;
: T-@ ( taddr -- cell ) T>HOST @ ;
: T-C! ( byte taddr -- ) T>HOST C! ;
: T-! ( cell taddr -- ) T>HOST ! ;
: T-ALLOT ( n -- ) T-HERE +! ;
: T-ALIGN ( -- )
    BEGIN T-ADDR 3 AND WHILE
        0 T-C,
    REPEAT
;

\ ---- Runtime address variables ----
VARIABLE DOCOL-ADDR
VARIABLE DOCREATE-ADDR
VARIABLE DOCON-ADDR
VARIABLE DOVOC-ADDR
VARIABLE DOLIT-ADDR
VARIABLE DOBRANCH-ADDR
VARIABLE DO0BRANCH-ADDR
VARIABLE DOEXIT-ADDR
VARIABLE DODO-ADDR
VARIABLE DOLOOP-ADDR
VARIABLE DOPLOOP-ADDR

\ ---- Forward reference table ----
\ Entry: len(1) name(1F) chain(4) flag(4) = 28h
VARIABLE FREF-COUNT
CREATE FREF-TBL 3E8 ALLOT

\ ---- Target compilation state ----
VARIABLE T-STATE
: T-] ( -- ) -1 T-STATE ! ;
: T-[ ( -- ) 0 T-STATE ! ; IMMEDIATE
: T-COMPILE, ( xt -- ) T-, ;
: T-LITERAL ( n -- )
    DOLIT-ADDR @ T-, T-,
;
: T-; ( -- )
    DOEXIT-ADDR @ T-, 0 T-STATE !
;

\ ---- Initialize target ----
: META-INIT ( -- )
    T-IMAGE 10000 0 FILL
    T-IMAGE T-HERE !
    7E00 T-ORG !
    0 T-LINK-VAR ! 0 T-SIZE !
    0 T-STATE ! 0 FREF-COUNT !
    0 DOCOL-ADDR !
    0 DOCREATE-ADDR !
    0 DOCON-ADDR ! 0 DOVOC-ADDR !
    0 DOLIT-ADDR !
    0 DOBRANCH-ADDR !
    0 DO0BRANCH-ADDR !
    0 DOEXIT-ADDR !
    0 DODO-ADDR !
    0 DOLOOP-ADDR !
    0 DOPLOOP-ADDR !
;

\ ---- Emit target dictionary header ----
\ Format: link(4) flags+len(1) name(n) align
VARIABLE TH-ADDR
VARIABLE TH-LEN
VARIABLE TH-FLAGS

: T-HEADER ( addr len flags -- )
    TH-FLAGS !
    TH-LEN !
    TH-ADDR !
    \ Emit link to previous word
    T-LINK-VAR @ T-,
    T-ADDR 4 - T-LINK-VAR !
    \ Emit flags + length byte
    TH-FLAGS @ TH-LEN @ OR T-C,
    \ Emit name chars
    TH-LEN @ 0 DO
        TH-ADDR @ I + C@ T-C,
    LOOP
    T-ALIGN
;

\ ---- Define a CODE word in target ----
: T-CODE ( addr len -- )
    0 T-HEADER
    T-ADDR 4 + T-,
;

: END-CODE ( -- )
    LODSD, %EAX JMP[],
;

\ ---- Define a COLON word in target ----
: T-COLON ( addr len -- )
    0 T-HEADER
    DOCOL-ADDR @ T-,
;

\ ============================================
\ Forward references
\ ============================================
\ Entry: namelen(1) name(1F) chain(4) flag(4)
\ chain = target addr of newest placeholder
\ flag = 0 unresolved, FFFFFFFF resolved
28 CONSTANT FREF-ESIZ
VARIABLE FR-ADDR
VARIABLE FR-LEN

: FREF-ENTRY ( idx -- addr )
    FREF-ESIZ * FREF-TBL +
;
: FREF-CHAIN ( idx -- addr )
    FREF-ENTRY 20 +
;
: FREF-FLAG ( idx -- addr )
    FREF-ENTRY 24 +
;

\ Name comparison
: FREF-NAMEEQ ( addr len idx -- flag )
    FREF-ENTRY DUP C@
    2 PICK <> IF
        DROP DROP DROP 0 EXIT
    THEN
    SWAP 0 DO
        OVER I + C@
        OVER 1+ I + C@
        <> IF
            DROP DROP 0
            UNLOOP EXIT
        THEN
    LOOP
    DROP DROP -1
;

\ Declare a forward reference
: FORWARD ( addr len -- )
    FR-LEN ! FR-ADDR !
    FREF-COUNT @ FREF-ENTRY
    FR-LEN @ OVER C!
    1+
    FR-ADDR @ SWAP FR-LEN @ CMOVE
    0 FREF-COUNT @ FREF-CHAIN !
    0 FREF-COUNT @ FREF-FLAG !
    1 FREF-COUNT +!
;

\ Compile a forward-ref placeholder
: T-FORWARD, ( addr len -- )
    FR-LEN ! FR-ADDR !
    FREF-COUNT @ 0 DO
        FR-ADDR @ FR-LEN @ I FREF-NAMEEQ
        IF
            I FREF-CHAIN @
            T-ADDR I FREF-CHAIN !
            T-,
            UNLOOP EXIT
        THEN
    LOOP
    ." FREF? " FR-ADDR @ FR-LEN @ TYPE CR
;

\ Patch all uses of a forward reference
VARIABLE FR-TMP
: RESOLVE ( tgt-addr addr len -- )
    FR-LEN ! FR-ADDR !
    FREF-COUNT @ 0 DO
        FR-ADDR @ FR-LEN @ I FREF-NAMEEQ
        IF
            I FREF-CHAIN @
            BEGIN DUP WHILE
                DUP T-@
                -ROT OVER SWAP T-!
                SWAP
            REPEAT
            DROP DROP
            -1 I FREF-FLAG !
            UNLOOP EXIT
        THEN
    LOOP
    DROP ." RESOLVE? "
    FR-ADDR @ FR-LEN @ TYPE CR
;

\ Report unresolved references
: META-CHECK ( -- )
    FREF-COUNT @ 0 DO
        I FREF-FLAG @ 0= IF
            ." Unresolved: "
            I FREF-ENTRY DUP C@
            SWAP 1+ SWAP TYPE CR
        THEN
    LOOP
;

\ ============================================
\ Defining words (target)
\ ============================================
VARIABLE TC-TMP
80 CONSTANT F-IMMED

: T-VARIABLE ( addr len -- )
    0 T-HEADER
    DOCREATE-ADDR @ T-, 0 T-,
;

: T-CONSTANT ( n addr len -- )
    ROT TC-TMP !
    0 T-HEADER
    DOCON-ADDR @ T-, TC-TMP @ T-,
;

: T-IMMEDIATE ( -- )
    T-LINK-VAR @ 4 + DUP T-C@
    F-IMMED OR SWAP T-C!
;

\ ============================================
\ Control flow (target)
\ ============================================
\ BRANCH: add esi,[esi]
\   offset = target - offset_cell
\ DOLOOP: lodsd; add esi,eax
\   offset = target - offset_cell - 4

: T-IF ( -- orig )
    DO0BRANCH-ADDR @ T-,
    T-ADDR 0 T-,
;
: T-THEN ( orig -- )
    T-ADDR OVER - SWAP T-!
;
: T-ELSE ( orig1 -- orig2 )
    DOBRANCH-ADDR @ T-,
    T-ADDR 0 T-,
    SWAP T-THEN
;
: T-BEGIN ( -- dest ) T-ADDR ;
: T-UNTIL ( dest -- )
    DO0BRANCH-ADDR @ T-,
    T-ADDR - T-,
;
: T-AGAIN ( dest -- )
    DOBRANCH-ADDR @ T-,
    T-ADDR - T-,
;
: T-WHILE ( dest -- orig dest )
    DO0BRANCH-ADDR @ T-,
    T-ADDR 0 T-,
    SWAP
;
: T-REPEAT ( orig dest -- )
    T-AGAIN T-THEN
;
: T-DO ( -- do-sys )
    DODO-ADDR @ T-, T-ADDR
;
: T-LOOP ( do-sys -- )
    DOLOOP-ADDR @ T-,
    T-ADDR - 4 - T-,
;
: T-+LOOP ( do-sys -- )
    DOPLOOP-ADDR @ T-,
    T-ADDR - 4 - T-,
;

\ ---- Build status ----
VARIABLE META-OK

: META-STATUS ( -- )
    META-OK @ IF
        ." META: OK" CR
    ELSE
        ." META: not built" CR
    THEN
    ." Target: "
    T-HERE @ T-IMAGE -
    DECIMAL . HEX
    ." bytes" CR
;

: META-SIZE ( -- n )
    T-HERE @ T-IMAGE -
;

\ ---- Minimal build (3-word kernel) ----
: META-BUILD ( -- )
    META-INIT
    \ Define EXIT (also sets DOEXIT-ADDR)
    S" EXIT" T-CODE
    T-ADDR 4 - DOEXIT-ADDR !
    C3 T-C,
    END-CODE
    \ Define DROP
    S" DROP" T-CODE
    %EAX POP,
    END-CODE
    \ Define DUP
    S" DUP" T-CODE
    %EAX PUSH,
    END-CODE
    T-HERE @ T-IMAGE - T-SIZE !
    1 META-OK !
    ." META-BUILD complete: "
    T-SIZE @ DECIMAL . HEX
    ." bytes" CR
;

\ ============================================
\ Context switching
\ ============================================
VOCABULARY TARGET

: IN-META ( -- )
    ONLY FORTH
    ALSO META-COMPILER DEFINITIONS
;
: IN-TARGET ( -- )
    ONLY FORTH ALSO TARGET
    DEFINITIONS
;

: [FORTH] FORTH ; IMMEDIATE
: [META] META-COMPILER ; IMMEDIATE
: [ASM] X86-ASM ; IMMEDIATE

\ ============================================
\ Base-forcing number parse (interpret only)
\ ============================================
: D# ( "num" -- n )
    BASE @ >R DECIMAL
    WORD NUMBER R> BASE !
;
: H# ( "num" -- n )
    BASE @ >R HEX
    WORD NUMBER R> BASE !
;

\ ---- Copy bytes from host to target ----
: T-BINARY, ( host-addr count -- )
    0 DO
        DUP I + C@ T-C,
    LOOP
    DROP
;

\ ---- Dump target bytes as hex ----
: TDUMP ( taddr n -- )
    0 DO
        DUP I + T-C@ .
    LOOP
    DROP
;

\ ---- META-SAVE: report T-IMAGE location ----
: META-SAVE ( -- )
    ." META-SAVE:" SPACE
    T-IMAGE DECIMAL . SPACE
    T-HERE @ T-IMAGE - .
    ." bytes" CR
;

PREVIOUS PREVIOUS FORTH DEFINITIONS
DECIMAL
