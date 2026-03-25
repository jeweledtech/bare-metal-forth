\ ============================================
\ CATALOG: RTL8168
\ CATEGORY: network
\ PLATFORM: x86
\ SOURCE: hand-written
\ PORTS: MMIO via PCI BAR0
\ REQUIRES: PCI-ENUM ECHOPORT
\ CONFIDENCE: medium
\ ============================================
\
\ Realtek RTL8168/8111 GbE NIC driver.
\ Phase 1: PCI discovery, MAC read,
\ link status, ECHOPORT integration.
\
\ Register map from Linux r8169 driver.
\
\ Usage:
\   USING RTL8168
\   RTL8168-INIT
\   RTL8168-MAC.
\   RTL8168-STATUS
\
\ ============================================

VOCABULARY RTL8168
RTL8168 DEFINITIONS
ALSO PCI-ENUM
ALSO ECHOPORT
HEX

\ ---- PCI device ID ----
10EC CONSTANT RTL-VID
8168 CONSTANT RTL-DID

\ ---- MMIO register offsets ----
\ From Linux kernel r8169_main.c
00 CONSTANT R-MAC0
37 CONSTANT R-CMD
3C CONSTANT R-IMR
3E CONSTANT R-ISR
40 CONSTANT R-TXCFG
44 CONSTANT R-RXCFG
6C CONSTANT R-PHYSTS

\ PHYstatus bits (offset 6C):
\   bit 0 = Full Duplex
\   bit 1 = Link Status
\   bit 2 = 10 Mbps
\   bit 3 = 100 Mbps
\   bit 4 = 1000 Mbps

\ ---- State ----
VARIABLE RTL-BASE
VARIABLE RTL-FOUND
CREATE RTL-MAC 6 ALLOT

\ ---- Hex print helpers ----
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
: .H8 ( dword -- )
    DUP 10 RSHIFT .H4 .H4
;

\ ---- MMIO access ----
\ On bare metal with identity mapping,
\ MMIO is just memory read/write.
: RTL@ ( off -- val )
    RTL-BASE @ + @
;
: RTLC@ ( off -- byte )
    RTL-BASE @ + C@
;
: RTL! ( val off -- )
    RTL-BASE @ + !
;
: RTLC! ( byte off -- )
    RTL-BASE @ + C!
;

\ ---- Read MAC from MMIO ----
: READ-MAC ( -- )
    6 0 DO
        I RTLC@ RTL-MAC I + C!
    LOOP
;

\ ---- Print MAC address ----
: RTL8168-MAC. ( -- )
    RTL-FOUND @ 0= IF
        ." No RTL8168" CR EXIT
    THEN
    ." MAC: "
    6 0 DO
        RTL-MAC I + C@ .H2
        I 5 < IF
            ." :"
        THEN
    LOOP
    CR
;

\ ---- Return MMIO base address ----
: RTL8168-BASE ( -- addr )
    RTL-BASE @
;

\ ---- PHY link status ----
: RTL8168-STATUS ( -- )
    RTL-FOUND @ 0= IF
        ." No RTL8168" CR EXIT
    THEN
    ." Link: "
    R-PHYSTS RTLC@
    DUP 2 AND IF
        ." UP "
        DUP 10 AND IF
            ." 1000M"
        ELSE
            DUP 8 AND IF
                ." 100M"
            ELSE
                ." 10M"
            THEN
        THEN
        DUP 1 AND IF
            ."  FD"
        ELSE
            ."  HD"
        THEN
    ELSE
        ." DOWN"
    THEN
    DROP CR
;

\ ---- Initialize ----
: RTL8168-INIT ( -- )
    0 RTL-FOUND !
    0 RTL-BASE !
    RTL-VID RTL-DID PCI-FIND
    0= IF
        ." RTL8168 not found" CR
        EXIT
    THEN
    \ Stack: ( bus dev func )
    PCI-F ! PCI-D ! PCI-B !
    \ Read BAR0 (MMIO base)
    PCI-B @ PCI-D @ PCI-F @
    0 PCI-BAR@
    RTL-BASE !
    \ Enable bus master + memory
    PCI-B @ PCI-D @ PCI-F @
    PCI-ENABLE
    \ Read MAC address from MMIO
    READ-MAC
    -1 RTL-FOUND !
    ." RTL8168 at "
    RTL-BASE @ .H8 CR
    RTL8168-MAC.
;

\ ---- ECHOPORT integration ----
\ Traces PCI config I/O during init.
\ MMIO accesses (C@/@) are not traced
\ by ECHOPORT (port I/O only).

: RTL8168-TRACE ( -- )
    ECHOPORT-ON
    RTL8168-INIT
    ECHOPORT-OFF
    ECHOPORT-DUMP
;

: RTL8168-ECHOPORT-WATCH ( -- )
    ECHOPORT-ON
    RTL8168-INIT
    ECHOPORT-OFF
    ECHOPORT-SUMMARY
;

FORTH DEFINITIONS
DECIMAL
