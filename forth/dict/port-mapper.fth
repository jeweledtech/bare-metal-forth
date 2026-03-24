\ ============================================
\ CATALOG: PORT-MAPPER
\ CATEGORY: tools
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ REQUIRES: HARDWARE ( US-DELAY MS-DELAY )
\ ============================================
\
\ Hardware I/O port discovery and mapping.
\ Scan port ranges, identify devices, dump
\ register state from the Forth prompt.
\
\ Usage:
\   USING PORT-MAPPER
\   MAP-LEGACY
\   HEX 3F8 3FF PORT-SCAN
\   CMOS-DUMP
\
\ ============================================

VOCABULARY PORT-MAPPER
PORT-MAPPER DEFINITIONS
ALSO HARDWARE
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

\ ---- Non-blocking key check ----
3FD CONSTANT COM1-LSR
: SERIAL-KEY? ( -- flag )
    COM1-LSR INB 1 AND 0<>
;

\ ---- Constants ----
FF CONSTANT FLOAT-BUS
DECIMAL 10 CONSTANT SCAN-DLY HEX
DECIMAL 100 CONSTANT WATCH-DLY HEX

\ ---- Shared counter ----
VARIABLE MAP-V

\ ---- Basic port probe ----
: PORT? ( port -- flag )
    INB FLOAT-BUS <> IF
        -1
    ELSE
        0
    THEN
;

: PORT. ( port -- )
    DUP .H4 ." : " INB .H2
;

\ ---- Range scanner ----
VARIABLE SC-BASE
: PORT-SCAN ( start end -- )
    0 MAP-V !
    OVER - 1+ DUP 0> IF
        SWAP SC-BASE !
        0 DO
            SC-BASE @ I + DUP INB
            DUP FLOAT-BUS <> IF
                SWAP CR .H4 ." ="
                .H2
                1 MAP-V +!
            ELSE
                DROP DROP
            THEN
            SCAN-DLY US-DELAY
        LOOP
    ELSE
        DROP DROP
    THEN
    CR DECIMAL MAP-V @ .
    HEX ." ports found" CR
;

\ ---- Device identification ----
VARIABLE PID-PORT
: IN-RANGE ( base count -- flag )
    OVER + PID-PORT @ SWAP < IF
        PID-PORT @ <=
    ELSE
        DROP 0
    THEN
;

: PORT-ID ( port -- )
    DUP PID-PORT ! INB
    DUP FF = IF DROP EXIT THEN
    1 MAP-V +!
    CR PID-PORT @ .H4 ." : "
    .H2 SPACE
    20 2 IN-RANGE IF
        ." PIC1" EXIT THEN
    A0 2 IN-RANGE IF
        ." PIC2" EXIT THEN
    40 4 IN-RANGE IF
        ." PIT" EXIT THEN
    60 1 IN-RANGE IF
        ." PS/2-Data" EXIT THEN
    64 1 IN-RANGE IF
        ." PS/2-Cmd" EXIT THEN
    70 2 IN-RANGE IF
        ." CMOS/RTC" EXIT THEN
    80 1 IN-RANGE IF
        ." POST" EXIT THEN
    170 8 IN-RANGE IF
        ." ATA-Sec" EXIT THEN
    1F0 8 IN-RANGE IF
        ." ATA-Pri" EXIT THEN
    2E8 8 IN-RANGE IF
        ." COM4" EXIT THEN
    2F8 8 IN-RANGE IF
        ." COM2" EXIT THEN
    3B0 10 IN-RANGE IF
        ." VGA-Mono" EXIT THEN
    3C0 10 IN-RANGE IF
        ." VGA-EGA" EXIT THEN
    3D0 10 IN-RANGE IF
        ." VGA-CGA" EXIT THEN
    3E8 8 IN-RANGE IF
        ." COM3" EXIT THEN
    3F0 8 IN-RANGE IF
        ." Floppy" EXIT THEN
    3F8 8 IN-RANGE IF
        ." COM1" EXIT THEN
    CF8 4 IN-RANGE IF
        ." PCI-Addr" EXIT THEN
    CFC 4 IN-RANGE IF
        ." PCI-Data" EXIT THEN
;

\ ---- Standard scans ----
: MAP-LEGACY ( -- )
    CR ." == Legacy I/O 0000-03FF =="
    0 MAP-V !
    400 0 DO
        I PORT-ID
        SCAN-DLY US-DELAY
    LOOP
    CR DECIMAL MAP-V @ .
    HEX ." ports found" CR
;

: MAP-EXTENDED ( -- )
    CR ." == Extended 0400-0FFF =="
    0 MAP-V !
    C00 0 DO
        I 400 + PORT-ID
        SCAN-DLY US-DELAY
    LOOP
    CR DECIMAL MAP-V @ .
    HEX ." ports found" CR
;

: MAP-PCI ( -- )
    CR ." == PCI Devices =="
    CR ." Load PCI-ENUM, then type:"
    CR ."   USING PCI-ENUM PCI-LIST"
    CR
;

\ ---- Register dumps ----
: .MASK8 ( byte -- )
    ." [" 8 0 DO
        DUP 1 AND IF
            ." M"
        ELSE
            ." ."
        THEN
        1 RSHIFT
    LOOP
    DROP ." ]"
;

: PIC-STATUS ( -- )
    CR ." PIC1 IMR=" 21 INB
    DUP .H2 SPACE .MASK8
    CR ." PIC2 IMR=" A1 INB
    DUP .H2 SPACE .MASK8
    CR
;

: PIT-STATUS ( -- )
    CR ." PIT Channel 0:"
    0 43 OUTB
    40 INB 40 INB 8 LSHIFT OR
    CR ."   Count=" .H4 CR
;

\ ---- CMOS dump ----
: CMOS@ ( reg -- byte )
    80 OR 70 OUTB 71 INB
;
: CMOS-RESTORE ( -- )
    0 70 OUTB
;
: CMOS-DUMP ( -- )
    CR ." CMOS Registers 00-3F:"
    40 0 DO
        I F AND 0= IF
            CR I .H2 ." :"
        THEN
        SPACE I CMOS@ .H2
    LOOP
    CMOS-RESTORE CR
;

\ ---- Live port monitor ----
VARIABLE W-CNT
: PORT-WATCH ( port count -- )
    CR ." Watching port "
    OVER .H4
    ." , key to stop" CR
    W-CNT !
    BEGIN
        W-CNT @ 0>
        SERIAL-KEY? 0= AND
    WHILE
        DUP INB .H2 SPACE
        -1 W-CNT +!
        WATCH-DLY MS-DELAY
    REPEAT
    DROP CR
;

\ ---- Init ----
: PM-INFO ( -- )
    CR ." PORT-MAPPER loaded"
    CR ." MAP-LEGACY MAP-EXTENDED"
    CR ." PIC-STATUS PIT-STATUS"
    CR ." CMOS-DUMP PORT-WATCH"
    CR
;

PM-INFO

FORTH DEFINITIONS
DECIMAL
