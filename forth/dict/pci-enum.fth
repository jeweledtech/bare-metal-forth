\ ============================================
\ CATALOG: PCI-ENUM
\ CATEGORY: pci
\ PLATFORM: x86
\ SOURCE: hand-written
\ PORTS: 0xCF8, 0xCFC
\ CONFIDENCE: high
\ ============================================
\
\ PCI bus enumeration and device discovery.
\ Config mechanism 1 (0xCF8/0xCFC). Bus 0.
\
\ Usage:
\   USING PCI-ENUM
\   PCI-LIST
\   HEX 8086 1237 PCI-FIND
\
\ ============================================

VOCABULARY PCI-ENUM
PCI-ENUM DEFINITIONS
HEX

\ ---- PCI Config Ports ----
CF8 CONSTANT PCI-APORT
CFC CONSTANT PCI-DPORT

\ ---- Build PCI config address ----
\ 80000000 | bus<<16 | dev<<11
\          | func<<8 | reg&FC
: PCI-ADDR ( bus dev func reg -- )
    FC AND
    SWAP 8 LSHIFT OR
    SWAP B LSHIFT OR
    SWAP 10 LSHIFT OR
    80000000 OR
;

\ ---- Config space read ----
: PCI-READ ( bus dev func reg -- val )
    PCI-ADDR PCI-APORT OUTL
    PCI-DPORT INL
;

\ ---- Config space write ----
: PCI-WRITE
    ( val bus dev func reg -- )
    PCI-ADDR PCI-APORT OUTL
    PCI-DPORT OUTL
;

\ ---- Device table (32 max) ----
20 CONSTANT MAX-DEVS
0C CONSTANT ENTRY-SZ

\ Entry: +0 bus +1 dev +2 func +3 pad
\        +4 vendor(w) +6 device(w)
\        +8 class +9 subclass +A irq
CREATE PCI-TBL
    MAX-DEVS ENTRY-SZ * ALLOT
VARIABLE PCI-COUNT

: PCI-ENTRY ( n -- addr )
    ENTRY-SZ * PCI-TBL +
;

\ ---- Saved loop indices ----
\ >R corrupts I/J offsets, so save
\ device and function before >R.
VARIABLE SCAN-D
VARIABLE SCAN-F
VARIABLE SCAN-B

\ ---- Scan one PCI bus ----
\ J=device(0-31) I=function(0-7)
: PCI-SCAN-BUS ( bus -- )
    SCAN-B !
    20 0 DO
        8 0 DO
            SCAN-B @ J I 0 PCI-READ
            DUP FFFF AND FFFF <> IF
                PCI-COUNT @
                MAX-DEVS < IF
                    J SCAN-D !
                    I SCAN-F !
                    PCI-COUNT @
                    PCI-ENTRY >R
                    SCAN-B @ R@ C!
                    SCAN-D @
                    R@ 1+ C!
                    SCAN-F @
                    R@ 2 + C!
                    DUP FFFF AND
                    R@ 4 + W!
                    10 RSHIFT
                    R@ 6 + W!
                    SCAN-B @ SCAN-D @
                    SCAN-F @
                    8 PCI-READ
                    DUP 18 RSHIFT
                    R@ 8 + C!
                    10 RSHIFT
                    FF AND
                    R@ 9 + C!
                    SCAN-B @ SCAN-D @
                    SCAN-F @
                    3C PCI-READ
                    FF AND
                    R@ A + C!
                    R> DROP
                    1 PCI-COUNT +!
                ELSE
                    DROP
                THEN
            ELSE
                DROP
            THEN
        LOOP
    LOOP
;

VARIABLE B0-CNT

\ ---- Scan behind PCI-to-PCI bridges ----
\ Class 06/04 = bridge. Reg 18 bits
\ 16-23 = secondary bus number.
: PCI-BRIDGES ( -- )
    PCI-COUNT @ DUP B0-CNT !
    0<> IF
        B0-CNT @ 0 DO
            I PCI-ENTRY
            DUP 8 + C@ 6 =
            OVER 9 + C@ 4 = AND IF
                DUP C@ OVER 1+ C@
                ROT 2 + C@
                18 PCI-READ
                10 RSHIFT FF AND
                DUP 0<> IF
                    PCI-SCAN-BUS
                ELSE DROP THEN
            ELSE DROP THEN
        LOOP
    THEN
;

\ ---- Scan all PCI buses ----
: PCI-SCAN ( -- )
    0 PCI-COUNT !
    0 PCI-SCAN-BUS
    PCI-BRIDGES
;

\ ---- Find by vendor:device ID ----
\ Returns bus dev func -1 if found,
\ or 0 if not found.
: PCI-FIND
    ( vendor device -- b d f -1 | 0 )
    PCI-COUNT @ DUP 0<> IF
        0 DO
            I PCI-ENTRY
            DUP 4 + W@
            3 PICK = IF
                DUP 6 + W@
                2 PICK = IF
                    NIP NIP
                    DUP C@
                    OVER 1+ C@
                    ROT 2 + C@
                    -1
                    UNLOOP EXIT
                THEN
            THEN
            DROP
        LOOP
    ELSE
        DROP
    THEN
    2DROP 0
;

\ ---- Read BAR ----
: PCI-BAR@
    ( bus dev func bar# -- addr )
    4 * 10 +
    PCI-READ
    DUP 1 AND IF
        FFFFFFFC AND
    ELSE
        FFFFFFF0 AND
    THEN
;

\ ---- Temp vars for PCI-ENABLE ----
VARIABLE PCI-B
VARIABLE PCI-D
VARIABLE PCI-F

\ ---- Enable bus master + I/O ----
: PCI-ENABLE ( bus dev func -- )
    PCI-F ! PCI-D ! PCI-B !
    PCI-B @ PCI-D @ PCI-F @
    4 PCI-READ 7 OR
    PCI-B @ PCI-D @ PCI-F @
    4 PCI-WRITE
;

\ ---- Read class/subclass ----
: PCI-CLASS@
    ( bus dev func -- class sub )
    8 PCI-READ
    DUP 18 RSHIFT FF AND
    SWAP 10 RSHIFT FF AND
;

\ ---- Read IRQ ----
: PCI-IRQ@
    ( bus dev func -- irq )
    3C PCI-READ FF AND
;

\ ---- Hex printing ----
: >HEXCH ( n -- char )
    F AND DUP 9 > IF
        7 +
    THEN
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

\ ---- List PCI devices ----
: PCI-LIST ( -- )
    CR ." B  D  F  Vend:Dev  Cl"
    PCI-COUNT @ DUP 0<> IF
        0 DO
            CR I PCI-ENTRY
            DUP C@ .H2 SPACE
            DUP 1+ C@ .H2 SPACE
            DUP 2 + C@ .H2 SPACE
            DUP 4 + W@ .H4
            ." :"
            DUP 6 + W@ .H4
            SPACE
            DUP 8 + C@ .H2
            ." /"
            9 + C@ .H2
        LOOP
    ELSE
        DROP
    THEN
    CR DECIMAL PCI-COUNT @ .
    HEX ." devices" CR
;

\ Auto-scan on vocabulary load
PCI-SCAN

FORTH DEFINITIONS
DECIMAL
