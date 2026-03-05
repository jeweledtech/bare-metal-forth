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
HEX

\ ---- Target buffer ----
CREATE T-IMAGE 10000 ALLOT
VARIABLE T-ORG
VARIABLE T-SIZE
VARIABLE T-LINK-VAR

\ ---- Initialize target ----
: META-INIT ( -- )
    T-IMAGE 10000 0 FILL
    T-IMAGE T-HERE !
    7E00 T-ORG !
    0 T-LINK-VAR !
    0 T-SIZE !
;

\ ---- Target address calculation ----
: T-ADDR ( -- target-addr )
    T-HERE @ T-IMAGE - T-ORG @ +
;

\ ---- Emit target dictionary header ----
\ Format: link(4) flags+len(1) name(n) align
\ Takes name as addr+len on stack
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
    \ Align to 4 bytes
    BEGIN T-ADDR 3 AND WHILE
        0 T-C,
    REPEAT
;

\ ---- Define a CODE word in target ----
: T-CODE ( addr len -- )
    0 T-HEADER
    T-ADDR T-,
;

: END-CODE ( -- )
    LODSD, %EAX JMP[],
;

\ ---- Define a COLON word in target ----
VARIABLE DOCOL-ADDR

: T-COLON ( addr len -- )
    0 T-HEADER
    DOCOL-ADDR @ T-,
;

\ ---- Forward reference table ----
VARIABLE FREF-COUNT
CREATE FREF-TBL 400 ALLOT

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
    \ Define EXIT
    S" EXIT" T-CODE
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

FORTH DEFINITIONS
DECIMAL
