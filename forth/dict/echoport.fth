\ ============================================
\ CATALOG: ECHOPORT
\ CATEGORY: tools
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ REQUIRES: HARDWARE ( US-DELAY )
\ ============================================
\
\ Live hardware port activity recorder.
\ Wraps kernel INB/OUTB/INW/OUTW/INL/OUTL
\ with a 256-entry ring buffer trace log.
\
\ Usage:
\   USING ECHOPORT
\   ECHOPORT-ON
\   HEX 20 INB DROP
\   ECHOPORT-OFF
\   ECHOPORT-DUMP
\
\ ============================================

VOCABULARY ECHOPORT
ECHOPORT DEFINITIONS
HEX

\ ---- Hex printing (local) ----
: >HEXCH ( n -- char )
    F AND DUP 9 > IF 7 + THEN
    30 +
;
: .H2 ( byte -- )
    DUP 4 RSHIFT >HEXCH EMIT
    >HEXCH EMIT
;
: .H4 ( word -- )
    DUP 8 RSHIFT FF AND .H2
    .H2
;
: .H8 ( dword -- )
    DUP 10 RSHIFT .H4
    .H4
;

\ ---- Type name table ----
\ 0=INB 1=OUTB 2=INW 3=OUTW 4=INL 5=OUTL
: .TYPE ( n -- )
    DUP 0 = IF DROP ." INB " EXIT THEN
    DUP 1 = IF DROP ." OUTB" EXIT THEN
    DUP 2 = IF DROP ." INW " EXIT THEN
    DUP 3 = IF DROP ." OUTW" EXIT THEN
    DUP 4 = IF DROP ." INL " EXIT THEN
    DUP 5 = IF DROP ." OUTL" EXIT THEN
    DROP ." ????"
;

\ ---- Control words ----
: ECHOPORT-ON ( -- )
    0 TRACE-HEAD !
    0 TRACE-COUNT !
    1 TRACE-ENABLED C!
    ." ECHOPORT: tracing on" CR
;

: ECHOPORT-OFF ( -- )
    0 TRACE-ENABLED C!
    ." ECHOPORT: off ("
    TRACE-COUNT @ DECIMAL .
    HEX ." entries)" CR
;

: ECHOPORT-CLEAR ( -- )
    0 TRACE-HEAD !
    0 TRACE-COUNT !
;

: ECHOPORT-COUNT ( -- n )
    TRACE-COUNT @
;

\ ---- Entry access helpers ----
\ Each entry: [type:1][pad:1][port:2][val:4]
VARIABLE EP-IDX
: EP-ENTRY ( idx -- addr )
    TRACE-BUF-SIZE 1- AND
    TRACE-ENTRY-SZ * TRACE-BUF +
;

: EP-TYPE   ( addr -- n ) C@ ;
: EP-PORT   ( addr -- n ) 2 + W@ ;
: EP-VAL    ( addr -- n ) 4 + @ ;
: EP-CALLER ( addr -- n ) 8 + @ ;

\ Direct entry access for read/write
\ Usage: 5 EP-ENTRY@ gives raw addr
\   DUP EP-PORT .H4
\   42 OVER EP-VAL! (write val field)
: EP-ENTRY@ ( idx -- addr )
    EP-ENTRY
;

\ ---- Dump all entries ----
VARIABLE EP-N
: ECHOPORT-DUMP ( -- )
    MORE-ON
    ECHOPORT-COUNT DUP 0= IF
        DROP ." (no entries)" CR
        MORE-OFF EXIT
    THEN
    DUP TRACE-BUF-SIZE > IF
        DROP TRACE-BUF-SIZE
    THEN
    EP-N !
    TRACE-HEAD @
    EP-N @ - TRACE-BUF-SIZE 1- AND
    EP-IDX !
    EP-N @ 0 DO
        ." #"
        I DUP DECIMAL .
        HEX ." : "
        EP-IDX @ EP-ENTRY
        DUP EP-TYPE .TYPE
        SPACE ." port="
        DUP EP-PORT .H4
        ." val="
        DUP EP-VAL .H4
        ."  @"
        EP-CALLER .H8 CR
        EP-IDX @ 1+
        TRACE-BUF-SIZE 1- AND
        EP-IDX !
    LOOP
    MORE-OFF
;

\ ---- Summary: unique ports ----
\ Entry: [port:2][in_cnt:2][out_cnt:2]=6B
DECIMAL 64 CONSTANT MAX-UPORTS HEX
CREATE UPORT-TBL
    MAX-UPORTS 6 * ALLOT
VARIABLE UP-COUNT

\ Find port in table, return addr or 0
: UP-FIND ( port -- addr | 0 )
    UP-COUNT @ 0= IF
        DROP 0 EXIT
    THEN
    UP-COUNT @ 0 DO
        DUP I 6 * UPORT-TBL + W@
        = IF
            DROP I 6 * UPORT-TBL +
            UNLOOP EXIT
        THEN
    LOOP
    DROP 0
;

\ Record a port access
VARIABLE UP-PORT
VARIABLE UP-TYPE
: UP-RECORD ( port type -- )
    UP-TYPE ! UP-PORT !
    UP-PORT @ UP-FIND
    DUP 0= IF
        DROP
        UP-COUNT @ MAX-UPORTS < IF
            UP-COUNT @ 6 *
            UPORT-TBL +
            UP-PORT @ OVER W!
            0 OVER 2 + W!
            0 OVER 4 + W!
            1 UP-COUNT +!
        ELSE
            EXIT
        THEN
    THEN
    UP-TYPE @ 1 AND IF
        DUP 4 + W@ 1+ OVER 4 + W!
    ELSE
        DUP 2 + W@ 1+ OVER 2 + W!
    THEN
    DROP
;

: ECHOPORT-SUMMARY ( -- )
    0 UP-COUNT !
    ECHOPORT-COUNT DUP 0= IF
        DROP ." (no entries)" CR EXIT
    THEN
    DUP TRACE-BUF-SIZE > IF
        DROP TRACE-BUF-SIZE
    THEN
    EP-N !
    TRACE-HEAD @
    EP-N @ - TRACE-BUF-SIZE 1- AND
    EP-IDX !
    EP-N @ 0 DO
        EP-IDX @ EP-ENTRY
        DUP EP-PORT
        SWAP EP-TYPE UP-RECORD
        EP-IDX @ 1+
        TRACE-BUF-SIZE 1- AND
        EP-IDX !
    LOOP
    CR ." ECHOPORT: "
    DECIMAL UP-COUNT @ . HEX
    ." unique ports, "
    DECIMAL ECHOPORT-COUNT . HEX
    ." total" CR
    UP-COUNT @ 0 DO
        ."   port="
        I 6 * UPORT-TBL +
        DUP W@ .H4 ." : "
        DUP 2 + W@ DUP 0> IF
            DECIMAL . HEX ." IN "
        ELSE
            DROP
        THEN
        4 + W@ DUP 0> IF
            DECIMAL . HEX ." OUT"
        ELSE
            DROP
        THEN
        CR
    LOOP
;

\ ---- Watch a word ----
: ECHOPORT-WATCH ( xt -- )
    ECHOPORT-ON
    EXECUTE
    ECHOPORT-OFF
    ECHOPORT-SUMMARY
;

FORTH DEFINITIONS
DECIMAL
