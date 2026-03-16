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
40 CONSTANT CMD-PG1

\ ---- NIC memory layout (pages) ----
40 CONSTANT RX-START
80 CONSTANT RX-STOP
20 CONSTANT TX-START

\ ---- State ----
VARIABLE NE-BASE
CREATE NE-MAC 6 ALLOT
VARIABLE NE-TX-CNT
VARIABLE NE-RX-CNT
VARIABLE DMA-LEN

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
: NE2K-DMA-RD ( addr len src -- )
    SWAP DUP DMA-LEN !
    SWAP
    DUP FF AND NE-RSAR0 NE!
    8 RSHIFT NE-RSAR1 NE!
    DMA-LEN @ DUP
    NE-RBCR0 NE!
    8 RSHIFT NE-RBCR1 NE!
    CMD-RD CMD-START OR
    NE-CMD NE!
    NE-BASE @ NE-DATA +
    DMA-LEN @ 0 DO
        DUP INB
        2 PICK I + C!
    LOOP
    2DROP
;

\ ---- DMA write: host to NIC mem ----
: NE2K-DMA-WR ( addr len dest -- )
    SWAP DUP DMA-LEN !
    SWAP
    DUP FF AND NE-RSAR0 NE!
    8 RSHIFT NE-RSAR1 NE!
    DMA-LEN @ DUP
    NE-RBCR0 NE!
    8 RSHIFT NE-RBCR1 NE!
    CMD-WR CMD-START OR
    NE-CMD NE!
    NE-BASE @ NE-DATA +
    DMA-LEN @ 0 DO
        OVER I + C@
        OVER OUTB
    LOOP
    2DROP
;

\ ---- Initialize NIC ----
: NE2K-INIT ( -- )
    10EC 8029 PCI-FIND
    0= IF
        ." NE2000 not found" CR
        EXIT
    THEN
    0 PCI-BAR@
    FFFFFFFC AND NE-BASE !
    NE2K-RESET
    CMD-STOP NE-CMD NE!
    49 NE-DCR NE!
    0 NE-RBCR0 NE!
    0 NE-RBCR1 NE!
    0C NE-RCR NE!
    0 NE-TCR NE!
    RX-START NE-PSTART NE!
    RX-STOP NE-PSTOP NE!
    RX-START NE-BNRY NE!
    CMD-STOP CMD-PG1 OR NE-CMD NE!
    RX-START 1+ NE-CURR NE!
    CMD-STOP NE-CMD NE!
    \ Read MAC from PROM (32 bytes)
    0 NE-RSAR0 NE!
    0 NE-RSAR1 NE!
    20 NE-RBCR0 NE!
    0 NE-RBCR1 NE!
    CMD-RD CMD-START OR NE-CMD NE!
    6 0 DO
        NE-DATA NE@
        NE-MAC I + C!
        NE-DATA NE@ DROP
    LOOP
    \ Set PAR0-5 (page 1)
    CMD-STOP CMD-PG1 OR NE-CMD NE!
    6 0 DO
        NE-MAC I + C@
        NE-PAR0 I + NE!
    LOOP
    CMD-START NE-CMD NE!
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
    CMD-STOP CMD-PG1 OR NE-CMD NE!
    NE-CURR NE@
    CMD-START NE-CMD NE!
    NE-BNRY NE@ 1+ DUP
    RX-STOP >= IF
        DROP RX-START
    THEN
    <>
;

\ ---- Statistics ----
: NE2K-STATS ( -- )
    ." TX: " NE-TX-CNT @ . CR
    ." RX: " NE-RX-CNT @ . CR
;

PREVIOUS FORTH DEFINITIONS
DECIMAL
