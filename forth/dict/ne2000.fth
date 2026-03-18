\ ============================================
\ CATALOG: NE2000
\ CATEGORY: network
\ PLATFORM: x86
\ SOURCE: hand-written
\ VENDOR-ID: 10EC
\ DEVICE-ID: 8029
\ CONFIDENCE: high
\ REQUIRES: PCI-ENUM ( PCI-FIND PCI-BAR@ )
\ ============================================
\
\ NE2000-compatible (RTL8029) NIC driver.
\ Requires QEMU -nic model=ne2k_pci.
\ Uses PCI for device discovery.
\
\ Usage:
\   USING NE2000
\   NE2K-INIT
\   NE2K-MAC.
\
\ ============================================

VOCABULARY NE2000
NE2000 DEFINITIONS
ALSO PCI-ENUM
HEX

\ ---- Register Offsets (page 0) ----
00 CONSTANT NE-CMD
01 CONSTANT NE-PSTART
02 CONSTANT NE-PSTOP
03 CONSTANT NE-BNRY
04 CONSTANT NE-TPSR
05 CONSTANT NE-TBCR0
06 CONSTANT NE-TBCR1
07 CONSTANT NE-ISR
08 CONSTANT NE-RSAR0
09 CONSTANT NE-RSAR1
0A CONSTANT NE-RBCR0
0B CONSTANT NE-RBCR1
0C CONSTANT NE-RCR
0D CONSTANT NE-TCR
0E CONSTANT NE-DCR
0F CONSTANT NE-IMR
10 CONSTANT NE-DATA
1F CONSTANT NE-RESET

\ ---- Page 1 registers ----
01 CONSTANT NE-PAR0
07 CONSTANT NE-CURR

\ ---- Command bits ----
01 CONSTANT CMD-STOP
02 CONSTANT CMD-START
04 CONSTANT CMD-TXP
08 CONSTANT CMD-RD
10 CONSTANT CMD-WR
20 CONSTANT CMD-DMABT
22 CONSTANT CMD-GO
40 CONSTANT CMD-PG1

\ ---- TCR loopback during init ----
02 CONSTANT TCR-LOOP

\ ---- NIC memory layout (pages) ----
\ QEMU writable mem starts at page 40.
\ TX: 40-45 (6 pages = 1536 bytes)
\ RX: 46-80 ring buffer
46 CONSTANT RX-START
80 CONSTANT RX-STOP
40 CONSTANT TX-START

\ ---- State ----
VARIABLE NE-BASE
CREATE NE-MAC 6 ALLOT
VARIABLE NE-TX-CNT
VARIABLE NE-RX-CNT
VARIABLE DMA-LEN

\ ---- Receive state ----
CREATE RX-HDR 4 ALLOT
VARIABLE RX-PG
VARIABLE RX-NXT
VARIABLE RX-DLEN
VARIABLE RX-BUFP
VARIABLE RX-MAXL

\ ---- Register access ----
: NE! ( val reg -- )
    NE-BASE @ + OUTB
;
: NE@ ( reg -- val )
    NE-BASE @ + INB
;

\ ---- Reset NIC ----
: NE2K-RESET ( -- )
    NE-RESET NE@
    NE-RESET NE!
    BEGIN NE-ISR NE@ 80 AND UNTIL
    FF NE-ISR NE!
;

\ ---- DMA read: NIC mem to host ----
\ WTS=1: word mode. INW per 2 bytes.
\ RBCR and loop use same rounded count.
VARIABLE DMA-DST
VARIABLE DMA-PORT
VARIABLE DMA-RC
DECIMAL 64 CONSTANT ISR-RDC HEX
: NE2K-DMA-RD ( addr len src -- )
    CMD-GO NE-CMD NE!
    ISR-RDC NE-ISR NE!
    ROT DMA-DST !
    SWAP 1+ -2 AND DMA-RC !
    DUP FF AND NE-RSAR0 NE!
    8 RSHIFT NE-RSAR1 NE!
    DMA-RC @ DUP
    NE-RBCR0 NE!
    8 RSHIFT NE-RBCR1 NE!
    CMD-RD CMD-START OR
    NE-CMD NE!
    NE-BASE @ NE-DATA + DMA-PORT !
    DMA-RC @ 2 / 0 DO
        DMA-PORT @ INW
        DUP FF AND
        DMA-DST @ I 2 * + C!
        8 RSHIFT
        DMA-DST @ I 2 * 1+ + C!
    LOOP
    BEGIN NE-ISR NE@ ISR-RDC AND UNTIL
    ISR-RDC NE-ISR NE!
;

\ ---- DMA write: host to NIC mem ----
\ WTS=1: word mode. OUTW per 2 bytes.
\ RBCR and loop use same rounded count.
VARIABLE DMA-SRC
: NE2K-DMA-WR ( addr len dest -- )
    CMD-GO NE-CMD NE!
    ISR-RDC NE-ISR NE!
    ROT DMA-SRC !
    SWAP 1+ -2 AND DMA-RC !
    DUP FF AND NE-RSAR0 NE!
    8 RSHIFT NE-RSAR1 NE!
    DMA-RC @ DUP
    NE-RBCR0 NE!
    8 RSHIFT NE-RBCR1 NE!
    CMD-WR CMD-START OR
    NE-CMD NE!
    NE-BASE @ NE-DATA + DMA-PORT !
    DMA-RC @ 2 / 0 DO
        DMA-SRC @ I 2 * + C@
        DMA-SRC @ I 2 * 1+ + C@
        8 LSHIFT OR
        DMA-PORT @ OUTW
    LOOP
    BEGIN NE-ISR NE@ ISR-RDC AND UNTIL
    ISR-RDC NE-ISR NE!
;

\ ---- Initialize NIC ----
\ Standard NE2000 init sequence:
\ stop, config, loopback, PROM, start.
: NE2K-INIT ( -- )
    10EC 8029 PCI-FIND
    0= IF
        ." NE2000 not found" CR
        EXIT
    THEN
    0 PCI-BAR@
    FFFFFFFC AND NE-BASE !
    NE2K-RESET
    \ Page 0, stop, abort DMA
    CMD-STOP CMD-DMABT OR
    NE-CMD NE!
    49 NE-DCR NE!
    0 NE-RBCR0 NE!
    0 NE-RBCR1 NE!
    4 NE-RCR NE!
    TCR-LOOP NE-TCR NE!
    RX-START NE-PSTART NE!
    RX-STOP NE-PSTOP NE!
    RX-START NE-BNRY NE!
    FF NE-ISR NE!
    0 NE-IMR NE!
    \ Page 1: set CURR
    CMD-STOP CMD-PG1 OR
    NE-CMD NE!
    RX-START 1+ NE-CURR NE!
    \ Page 0: read PROM (word mode)
    \ INW reads a word; low byte = MAC byte
    CMD-STOP CMD-DMABT OR
    NE-CMD NE!
    0 NE-RSAR0 NE!
    0 NE-RSAR1 NE!
    20 NE-RBCR0 NE!
    0 NE-RBCR1 NE!
    CMD-RD CMD-START OR
    NE-CMD NE!
    NE-BASE @ NE-DATA +
    6 0 DO
        DUP INW FF AND
        NE-MAC I + C!
    LOOP
    DROP
    \ Set PAR0-5 (page 1)
    CMD-STOP CMD-PG1 OR
    NE-CMD NE!
    6 0 DO
        NE-MAC I + C@
        NE-PAR0 I + NE!
    LOOP
    \ Clear ISR, start NIC
    CMD-STOP CMD-DMABT OR
    NE-CMD NE!
    FF NE-ISR NE!
    \ Normal RCR: broadcast + promisc
    1C NE-RCR NE!
    CMD-GO NE-CMD NE!
    0 NE-TCR NE!
    0 NE-TX-CNT !
    0 NE-RX-CNT !
    ." NE2000 at "
    NE-BASE @ .
    CR
;

\ ---- Show MAC address ----
: NE2K-MAC. ( -- )
    ." MAC: "
    6 0 DO
        NE-MAC I + C@ .
    LOOP
    CR
;

\ ---- Send packet ----
: NE2K-SEND ( addr len -- )
    DUP >R
    TX-START 8 LSHIFT
    NE2K-DMA-WR
    TX-START NE-TPSR NE!
    R@ NE-TBCR0 NE!
    R> 8 RSHIFT NE-TBCR1 NE!
    CMD-TXP CMD-START OR
    NE-CMD NE!
    1 NE-TX-CNT +!
;

\ ---- Check for received packet ----
: NE2K-RECV? ( -- flag )
    \ Page 1 (keep running)
    CMD-GO CMD-PG1 OR NE-CMD NE!
    NE-CURR NE@
    \ Back to page 0 (keep running)
    CMD-GO NE-CMD NE!
    NE-BNRY NE@ 1+ DUP
    RX-STOP >= IF
        DROP RX-START
    THEN
    <>
;

\ ---- Receive packet ----
\ Read next packet from ring buffer.
\ Returns actual bytes read, or 0.
: NE2K-RECV ( buf maxlen -- actual | 0 )
    NE2K-RECV? 0= IF
        2DROP 0 EXIT
    THEN
    RX-MAXL ! RX-BUFP !
    \ Read pointer: BNRY+1, wrap
    NE-BNRY NE@ 1+
    DUP RX-STOP >= IF
        DROP RX-START
    THEN
    RX-PG !
    \ Read 4-byte NIC header
    RX-HDR 4
    RX-PG @ 8 LSHIFT
    NE2K-DMA-RD
    \ Parse next page
    RX-HDR 1+ C@ RX-NXT !
    \ Parse data length (minus header)
    RX-HDR 2 + C@
    RX-HDR 3 + C@ 8 LSHIFT OR
    4 - RX-DLEN !
    \ Clamp to caller's max
    RX-DLEN @ RX-MAXL @ MIN
    RX-DLEN !
    \ Read packet data
    RX-BUFP @ RX-DLEN @
    RX-PG @ 8 LSHIFT 4 +
    NE2K-DMA-RD
    \ Update BNRY
    RX-NXT @ 1-
    DUP RX-START < IF
        DROP RX-STOP 1-
    THEN
    NE-BNRY NE!
    \ Clear RX interrupt
    1 NE-ISR NE!
    1 NE-RX-CNT +!
    RX-DLEN @
;

\ ---- Statistics ----
: NE2K-STATS ( -- )
    ." TX: " NE-TX-CNT @ . CR
    ." RX: " NE-RX-CNT @ . CR
;

PREVIOUS FORTH DEFINITIONS
DECIMAL
