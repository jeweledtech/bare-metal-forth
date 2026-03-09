\ ============================================
\ CATALOG: RTL8139
\ CATEGORY: network
\ PLATFORM: x86
\ SOURCE: extracted+refined
\ VENDOR-ID: 10EC
\ DEVICE-ID: 8139
\ PORTS: variable (PCI BAR0)
\ CONFIDENCE: high
\ REQUIRES: PCI-ENUM ( PCI-FIND PCI-BAR@ )
\ REQUIRES: HARDWARE ( US-DELAY )
\ ============================================
\
\ RealTek RTL8139 10/100 Ethernet driver.
\ Auto-extracted from Windows driver with
\ manual refinements for completeness.
\
\ Usage:
\   USING PCI-ENUM
\   USING HARDWARE
\   USING RTL8139
\   $C000 <rxbuf> RTL-INIT
\   <rxbuf> RTL-AUTO
\
\ ============================================

VOCABULARY RTL8139
RTL8139 DEFINITIONS
HEX

\ ---- PCI Identification ----
10EC CONSTANT RTL-VID
8139 CONSTANT RTL-DID

\ ---- Register Offsets (from I/O base) ----
00 CONSTANT RTL-IDR0
08 CONSTANT RTL-MAR0
10 CONSTANT RTL-TSD0
14 CONSTANT RTL-TSD1
18 CONSTANT RTL-TSD2
1C CONSTANT RTL-TSD3
20 CONSTANT RTL-TSAD0
24 CONSTANT RTL-TSAD1
28 CONSTANT RTL-TSAD2
2C CONSTANT RTL-TSAD3
30 CONSTANT RTL-RBSTART
37 CONSTANT RTL-CMD
38 CONSTANT RTL-CAPR
3A CONSTANT RTL-CBR
3C CONSTANT RTL-IMR
3E CONSTANT RTL-ISR
40 CONSTANT RTL-TCR
44 CONSTANT RTL-RCR
4C CONSTANT RTL-MPC
58 CONSTANT RTL-MSR

\ ---- Command Register Bits ----
01 CONSTANT CMD-BUFE
04 CONSTANT CMD-TE
08 CONSTANT CMD-RE
10 CONSTANT CMD-RST

\ ---- Interrupt Bits (IMR/ISR) ----
0001 CONSTANT INT-ROK
0002 CONSTANT INT-RER
0004 CONSTANT INT-TOK
0008 CONSTANT INT-TER
0010 CONSTANT INT-RXOVW
0020 CONSTANT INT-PUN
0040 CONSTANT INT-FOVW

\ All useful interrupts
INT-ROK INT-RER OR INT-TOK OR
INT-TER OR INT-RXOVW OR
INT-PUN OR
CONSTANT INT-ALL

\ ---- Receive Configuration Bits ----
0002 CONSTANT RCR-APM
0008 CONSTANT RCR-AB
0000 CONSTANT RCR-RBLEN-8K
0080 CONSTANT RCR-WRAP

\ ---- Module State ----
VARIABLE RTL-BASE
VARIABLE RTL-RX-BUF
VARIABLE RTL-TX-SLOT
CREATE RTL-MAC 6 ALLOT

\ Rx buffer size: 8K + 16 + 1500
DECIMAL
8192 16 + 1500 + CONSTANT RTL-RX-SZ
HEX

\ ---- Low-Level Register Access ----
: RTL-C@  ( offset -- byte )
    RTL-BASE @ + INB ;
: RTL-C!  ( byte offset -- )
    RTL-BASE @ + OUTB ;
: RTL-W@  ( offset -- word )
    RTL-BASE @ + INW ;
: RTL-W!  ( word offset -- )
    RTL-BASE @ + OUTW ;
: RTL-@  ( offset -- dword )
    RTL-BASE @ + INL ;
: RTL-!  ( dword offset -- )
    RTL-BASE @ + OUTL ;

\ ---- Chip Reset ----
: RTL-RESET  ( -- )
    CMD-RST RTL-CMD RTL-C!
    DECIMAL
    1000 0 DO
        RTL-CMD RTL-C@
        CMD-RST AND 0= IF
            HEX UNLOOP EXIT
        THEN
        1 US-DELAY
    LOOP
    HEX
    ." RTL8139: Reset timeout!" CR
;

\ ---- MAC Address ----
: RTL-READ-MAC  ( -- )
    6 0 DO
        RTL-IDR0 I + RTL-C@
        RTL-MAC I + C!
    LOOP
;

\ Print one hex byte as 2 digits
: .HEXBYTE ( byte -- )
    DUP 4 RSHIFT F AND
    DUP 9 > IF 7 + THEN 30 + EMIT
    F AND
    DUP 9 > IF 7 + THEN 30 + EMIT
;

: RTL-PRINT-MAC  ( -- )
    ." MAC: "
    6 0 DO
        RTL-MAC I + C@ .HEXBYTE
        I 5 < IF ." :" THEN
    LOOP
    CR
;

\ ---- Receiver Setup ----
: RTL-RX-INIT  ( rx-buf-phys -- )
    DUP RTL-RX-BUF !
    RTL-RBSTART RTL-!
    RCR-AB RCR-APM OR
    RCR-RBLEN-8K OR RCR-WRAP OR
    RTL-RCR RTL-!
    FFF0 RTL-CAPR RTL-W!
;

\ ---- Transmitter Setup ----
: RTL-TX-INIT  ( -- )
    0 RTL-TSD0 RTL-!
    0 RTL-TSD1 RTL-!
    0 RTL-TSD2 RTL-!
    0 RTL-TSD3 RTL-!
    0 RTL-TX-SLOT !
;

\ ---- Enable/Disable Chip ----
: RTL-ENABLE  ( -- )
    CMD-RE CMD-TE OR RTL-CMD RTL-C!
;
: RTL-DISABLE  ( -- )
    0 RTL-CMD RTL-C!
;

\ ---- Interrupt Setup ----
: RTL-INT-ENABLE  ( mask -- )
    RTL-IMR RTL-W! ;
: RTL-INT-DISABLE  ( -- )
    0 RTL-IMR RTL-W! ;
: RTL-INT-ACK  ( -- status )
    RTL-ISR RTL-W@
    DUP RTL-ISR RTL-W!
;

\ ---- Link Status ----
: RTL-LINK?  ( -- flag )
    RTL-MSR RTL-C@
    04 AND 0=
;
: RTL-SPEED  ( -- 10|100 )
    RTL-MSR RTL-C@
    DECIMAL
    08 AND IF 10 ELSE 100 THEN
    HEX
;

\ ---- Transmit Packet ----
: RTL-TX  ( buf-phys length -- )
    RTL-TX-SLOT @
    DUP 4 * RTL-TSAD0 +
    SWAP 4 * RTL-TSD0 +
    ROT
    ROT SWAP RTL-!
    SWAP 1FFF AND
    SWAP RTL-!
    RTL-TX-SLOT @
    1+ 3 AND RTL-TX-SLOT !
;

\ Wait for TX completion
: RTL-TX-WAIT  ( slot -- ok? )
    4 * RTL-TSD0 +
    DECIMAL
    1000 0 DO
        DUP RTL-@
        DUP 8000 AND IF
            DROP DROP TRUE
            HEX UNLOOP EXIT
        THEN
        4000 AND IF
            DROP FALSE
            HEX UNLOOP EXIT
        THEN
        1 US-DELAY
    LOOP
    HEX
    DROP FALSE
;

\ ---- Receive Packet ----
: RTL-RX?  ( -- flag )
    RTL-CMD RTL-C@
    CMD-BUFE AND 0=
;
: RTL-RX-POS  ( -- offset )
    RTL-CAPR RTL-W@ 10 +
    RTL-RX-SZ 1- AND
;
: RTL-RX-ACK  ( pkt-len -- )
    RTL-RX-POS +
    4 + 3 INVERT AND
    10 - FFFF AND
    RTL-CAPR RTL-W!
;

\ ---- Full Initialization ----
: RTL-INIT  ( base-port rx-buf -- )
    SWAP RTL-BASE !
    ." RTL8139 at port "
    RTL-BASE @ . CR
    RTL-RESET
    RTL-READ-MAC
    RTL-PRINT-MAC
    RTL-RX-INIT
    RTL-TX-INIT
    INT-ALL RTL-INT-ENABLE
    RTL-ENABLE
    RTL-LINK? IF
        ." Link: UP at "
        RTL-SPEED DECIMAL . HEX
        ." Mbps" CR
    ELSE
        ." Link: DOWN" CR
    THEN
    ." RTL8139 ready" CR
;

\ ---- PCI Auto-Detection ----
\ Uses PCI-FIND/PCI-BAR@ from PCI-ENUM
\ PCI-FIND: ( vid did -- b d f -1 | 0 )
\ PCI-BAR@: ( b d f bar# -- addr )
: RTL-FIND-PCI  ( -- port | 0 )
    RTL-VID RTL-DID PCI-FIND
    IF   0 PCI-BAR@
    ELSE 0
    THEN
;

: RTL-AUTO  ( rx-buf -- )
    RTL-FIND-PCI DUP 0<> IF
        SWAP RTL-INIT
    ELSE
        DROP DROP
        ." RTL8139 not found" CR
    THEN
;

.( RTL8139 driver loaded) CR

FORTH DEFINITIONS
DECIMAL
