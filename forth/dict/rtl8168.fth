\ ============================================
\ CATALOG: RTL8168
\ CATEGORY: network
\ PLATFORM: x86
\ SOURCE: hand-written
\ PORTS: MMIO via PCI BAR0
\ REQUIRES: PCI-ENUM ECHOPORT HARDWARE
\ CONFIDENCE: medium
\ ============================================
\
\ Realtek RTL8168/8111 GbE NIC driver.
\ Phase 3: PCI discovery, MAC read,
\ link up, PHY auto-negotiate,
\ TX engine, UDP transmit,
\ network console send.
\
\ Register map from Linux r8169 driver.
\
\ Usage:
\   USING RTL8168
\   RTL8168-INIT
\   RTL8168-MAC.
\   RTL8168-STATUS
\   S" hello" NET-CONSOLE-SEND
\
\ ============================================

VOCABULARY RTL8168
RTL8168 DEFINITIONS
ALSO PCI-ENUM
ALSO ECHOPORT
ALSO HARDWARE
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
50 CONSTANT R-CFG9346
60 CONSTANT R-PHYAR
20 CONSTANT R-TNPDS-LO
24 CONSTANT R-TNPDS-HI
38 CONSTANT R-TXPOLL

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

\ ---- TX engine state ----
1000 PHYS-ALLOC CONSTANT TX-DESC
1000 PHYS-ALLOC CONSTANT TX-BUF

\ ---- Network configuration ----
CREATE DEV-MAC
    9C C, 6B C, 00 C, 2A C,
    A8 C, D0 C,
0A2A0064 CONSTANT HP-IP
0A2A0001 CONSTANT DEV-IP
DECIMAL 6666 HEX CONSTANT UDP-PORT

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

\ ---- 16-bit MMIO access ----
: RTLW@ ( off -- word )
    RTL-BASE @ + W@
;
: RTLW! ( word off -- )
    RTL-BASE @ + W!
;

\ ---- Config register lock ----
: RTL-UNLOCK ( -- )
    C0 R-CFG9346 RTLC!
;
: RTL-LOCK ( -- )
    0 R-CFG9346 RTLC!
;

\ ---- Software reset ----
: RTL-RESET ( -- )
    10 R-CMD RTLC!
    100 0 DO
        R-CMD RTLC@ 10 AND 0= IF
            UNLOOP EXIT
        THEN
        1 MS-DELAY
    LOOP
    ." reset timeout" CR
;

\ ---- PHY register access ----
\ PHYAR bit31=flag, 20:16=reg,
\ 15:0=data. Read: write reg with
\ bit31 clear, poll until set.
: PHY@ ( reg -- val )
    10 LSHIFT R-PHYAR RTL!
    14 0 DO
        1 MS-DELAY
        R-PHYAR RTL@
        DUP 80000000 AND IF
            FFFF AND
            UNLOOP EXIT
        THEN
        DROP
    LOOP
    FFFF
;

\ Write: set bit31 | reg | data,
\ poll until bit31 clears.
: PHY! ( val reg -- )
    10 LSHIFT SWAP FFFF AND OR
    80000000 OR R-PHYAR RTL!
    14 0 DO
        1 MS-DELAY
        R-PHYAR RTL@
        80000000 AND 0= IF
            UNLOOP EXIT
        THEN
    LOOP
;

\ ---- Diagnostic: print all BARs ----
: .BARS ( -- )
    6 0 DO
        ." BAR" I 30 + EMIT ." : "
        PCI-B @ PCI-D @ PCI-F @
        I 4 * 10 + PCI-READ
        DUP .H8
        DUP 1 AND IF
            ."  IO"
        ELSE
            ."  MEM"
            DUP 6 AND 4 = IF
                ."  64b"
            THEN
        THEN
        DROP CR
    LOOP
;

\ ---- Find memory BAR ----
\ Scans BAR0-BAR5, returns first
\ non-zero memory BAR address
\ (masked), or 0 if none found.
: RTL-FIND-MMIO ( -- addr | 0 )
    6 0 DO
        PCI-B @ PCI-D @ PCI-F @
        I 4 * 10 + PCI-READ
        DUP 1 AND 0= IF
            FFFFFFF0 AND
            DUP 0<> IF
                ." Using BAR"
                I 30 + EMIT CR
                UNLOOP EXIT
            THEN
        THEN
        DROP
    LOOP
    0
;

\ ---- Full NIC initialization ----
: RTL8168-LINK-UP ( -- )
    RTL-UNLOCK
    \ 1. Software reset
    RTL-RESET
    \ Re-read MAC after reset
    READ-MAC
    \ Disable all interrupts
    0 R-IMR RTLW!
    \ Clear pending interrupts
    FFFF R-ISR RTLW!
    \ 4-5. RX config: broadcast +
    \ multicast + physical match,
    \ DMA unlimited, no FIFO thresh
    E70E R-RXCFG RTL!
    \ TX config: standard IFG,
    \ DMA unlimited
    3000700 R-TXCFG RTL!
    \ 3. Enable TX + RX
    C R-CMD RTLC!
    \ 6. PHY auto-negotiate enable
    \ BMCR reg 0: ANE=bit12,
    \ restart AN=bit9 -> 1200
    0 PHY@ 1200 OR 0 PHY!
    RTL-LOCK
    ." Link init done" CR
;

\ ---- Wait for link up ----
: RTL8168-WAIT-LINK ( -- )
    ." Waiting for link... "
    32 0 DO
        R-PHYSTS RTLC@ 2 AND IF
            ." UP" CR
            RTL8168-STATUS
            UNLOOP EXIT
        THEN
        A0 MS-DELAY
    LOOP
    ." timeout" CR
;

\ ============================================
\ TX Engine + UDP
\ ============================================

\ ---- Frame builder ----
VARIABLE FP
VARIABLE TX-PAYLOAD
VARIABLE TX-PLEN

: F! ( byte -- )
    FP @ C! 1 FP +!
;
: F-W! ( word -- )
    DUP 8 RSHIFT FF AND F!
    FF AND F!
;
: F-L! ( dword -- )
    DUP 18 RSHIFT FF AND F!
    DUP 10 RSHIFT FF AND F!
    DUP 8 RSHIFT FF AND F!
    FF AND F!
;
: F-COPY! ( addr n -- )
    0 DO
        DUP I + C@ F!
    LOOP
    DROP
;

\ ---- IP header checksum ----
\ Ones complement sum of 20-byte
\ IP header (10 x 16-bit words
\ in network byte order).
: IP-CKSUM ( addr -- checksum )
    0
    A 0 DO
        OVER I DUP + +
        DUP C@ 8 LSHIFT
        SWAP 1+ C@ OR +
    LOOP
    NIP
    DUP 10 RSHIFT +
    DUP 10 RSHIFT +
    FFFF AND FFFF XOR
;

\ ---- TX descriptor setup ----
: RTL8168-TX-INIT ( -- )
    TX-DESC 10 0 FILL
    TX-BUF 600 0 FILL
    \ Single descriptor, EOR set
    40000000 TX-DESC !
    \ Write ring address to NIC
    TX-DESC R-TNPDS-LO RTL!
    0 R-TNPDS-HI RTL!
    ." TX ready" CR
;

\ ---- Transmit frame from TX-BUF ----
\ Sets OWN+EOR+FS+LS + length,
\ triggers TX, polls for completion.
: RTL8168-TX ( len -- )
    F0000000 OR TX-DESC !
    TX-BUF TX-DESC 8 + !
    0 TX-DESC C + !
    40 R-TXPOLL RTLC!
    64 0 DO
        TX-DESC @
        80000000 AND 0= IF
            UNLOOP EXIT
        THEN
        1 MS-DELAY
    LOOP
    ." TX timeout" CR
;

\ ---- Build and send UDP packet ----
\ Builds Ethernet+IP+UDP frame in
\ TX-BUF, then transmits.
\ Frame layout:
\   0: dst MAC (6) src MAC (6)
\   C: ethertype (2)
\   E: IP header (20)
\  22: UDP header (8)
\  2A: payload (N)
: UDP-SEND ( payload-addr len -- )
    TX-PLEN ! TX-PAYLOAD !
    TX-BUF FP !
    \ Ethernet header (14 bytes)
    DEV-MAC 6 F-COPY!
    RTL-MAC 6 F-COPY!
    800 F-W!
    \ IP header (20 bytes)
    45 F!  0 F!
    TX-PLEN @ 1C + F-W!
    1 F-W!  4000 F-W!
    40 F!  11 F!
    0 F-W!
    HP-IP F-L!
    DEV-IP F-L!
    \ UDP header (8 bytes)
    UDP-PORT F-W!
    UDP-PORT F-W!
    TX-PLEN @ 8 + F-W!
    0 F-W!
    \ Payload
    TX-PAYLOAD @ TX-PLEN @ F-COPY!
    \ IP checksum (hdr at +E, cksum +18)
    TX-BUF E + IP-CKSUM
    DUP 8 RSHIFT TX-BUF 18 + C!
    FF AND TX-BUF 19 + C!
    \ Frame length (min 60 bytes)
    TX-PLEN @ 2A +
    DUP 3C < IF DROP 3C THEN
    RTL8168-TX
;

\ ---- Network console send ----
: NET-CONSOLE-SEND ( addr len -- )
    RTL-FOUND @ 0= IF
        2DROP EXIT
    THEN
    UDP-SEND
;

\ ---- Quick test word ----
: NET-TEST ( -- )
    S" Hello from ForthOS!"
    NET-CONSOLE-SEND
    ." Sent test packet" CR
;

\ ---- Network console ----
\ Mirror ALL output to UDP packets.
\ Kernel buffers chars in print_char,
\ flushes on LF or buffer full.
: NET-CONSOLE-ON ( -- )
    RTL-FOUND @ 0= IF
        ." Init RTL8168 first" CR
        EXIT
    THEN
    \ Store NIC state in kernel vars
    RTL-BASE @ NET-RTL-BASE !
    TX-DESC NET-TX-DESC !
    TX-BUF NET-TX-BUF !
    \ Build frame header template
    NET-HDR FP !
    DEV-MAC 6 F-COPY!
    RTL-MAC 6 F-COPY!
    800 F-W!
    \ IP header
    45 F!  0 F!
    0 F-W!  0 F-W!
    4000 F-W!
    40 F!  11 F!
    0 F-W!
    HP-IP F-L!
    DEV-IP F-L!
    \ UDP header
    UDP-PORT F-W!
    UDP-PORT F-W!
    0 F-W!  0 F-W!
    \ Enable kernel hook
    NET-CON-ON
    ." Net console ON" CR
;

: NET-CONSOLE-OFF ( -- )
    NET-CON-OFF
    ." Net console OFF" CR
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
    PCI-F ! PCI-D ! PCI-B !
    \ Enable bus master + memory
    PCI-B @ PCI-D @ PCI-F @
    PCI-ENABLE
    \ Show all BARs for diagnosis
    .BARS
    \ Find memory BAR (not I/O)
    RTL-FIND-MMIO
    DUP 0= IF
        DROP
        ." No MMIO BAR found" CR
        EXIT
    THEN
    RTL-BASE !
    \ Full NIC init + link up
    RTL8168-LINK-UP
    RTL8168-TX-INIT
    -1 RTL-FOUND !
    ." RTL8168 at "
    RTL-BASE @ .H8 CR
    RTL8168-MAC.
    RTL8168-WAIT-LINK
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

ONLY FORTH DEFINITIONS
DECIMAL
