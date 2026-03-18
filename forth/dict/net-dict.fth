\ ============================================
\ CATALOG: NET-DICT
\ CATEGORY: network
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ REQUIRES: NE2000 ( NE2K-INIT NE2K-SEND )
\ REQUIRES: NE2000 ( NE2K-RECV NE2K-MAC. )
\ REQUIRES: NE2000 ( NE-MAC )
\ ============================================
\
\ Dictionary sharing over raw Ethernet.
\ Sends/receives Forth blocks between two
\ bare-metal ForthOS instances using the
\ NE2000 NIC and a custom EtherType.
\
\ No TCP/IP stack needed. Raw Ethernet
\ frames with EtherType 0x88B5 (IEEE
\ local experimental).
\
\ Usage:
\   USING NET-DICT
\   NE2K-INIT
\   5 BLOCK-SEND    \ send block 5
\   BLOCK-RECV      \ receive a block
\   2 8 BLOCKS-SEND \ send blocks 2-8
\
\ ============================================

VOCABULARY NET-DICT
NET-DICT DEFINITIONS
ALSO NE2000
HEX

\ ---- Frame format constants ----
\ All defined OUTSIDE colon defs (bug #20)

\ EtherType: 88B5 (IEEE local experimental)
88 CONSTANT ET-HI
B5 CONSTANT ET-LO

\ Commands
1 CONSTANT CMD-BDATA
2 CONSTANT CMD-BREQ
3 CONSTANT CMD-BDONE

\ Frame header size (before payload)
DECIMAL 22 CONSTANT FRM-HDR HEX

\ Max payload
DECIMAL 1024 CONSTANT BLK-SZ HEX
\ Frame size = header + block
DECIMAL 1046 CONSTANT FRM-SZ HEX

\ Ethernet min frame = 60 bytes
DECIMAL 60 CONSTANT FRM-MIN HEX

\ ---- Buffers ----
\ TX frame buffer (1536 = 600h bytes)
CREATE TX-FRM 600 ALLOT

\ RX frame buffer
CREATE RX-FRM 600 ALLOT

\ ---- Frame field offsets ----
\ 0-5: dst MAC, 6-11: src MAC
\ 12-13: EtherType
\ 14-15: command
\ 16-17: block#
\ 18-19: offset
\ 20-21: payload length
\ 22+: payload data

\ ---- Receive state ----
VARIABLE RX-CMD
VARIABLE RX-BLK
VARIABLE RX-OFF
VARIABLE RX-PLEN
VARIABLE TX-OK

\ ---- Build TX frame header ----
: BUILD-HDR  ( blk# cmd -- )
    TX-FRM 600 0 FILL
    \ Dst MAC: broadcast
    FF TX-FRM     C!
    FF TX-FRM 1+  C!
    FF TX-FRM 2 + C!
    FF TX-FRM 3 + C!
    FF TX-FRM 4 + C!
    FF TX-FRM 5 + C!
    \ Src MAC: copy from NE-MAC
    NE-MAC TX-FRM 6 + 6 MOVE
    \ EtherType
    ET-HI TX-FRM C + C!
    ET-LO TX-FRM D + C!
    \ Command (big-endian)
    0     TX-FRM E + C!
    SWAP
    \ Block# (big-endian)
    DUP 8 RSHIFT TX-FRM 10 + C!
    FF AND       TX-FRM 11 + C!
    \ Command byte
          TX-FRM F + C!
    \ Offset: 0
    0 TX-FRM 12 + C!
    0 TX-FRM 13 + C!
;

\ ---- Set payload length in header ----
: SET-PLEN  ( len -- )
    DUP 8 RSHIFT TX-FRM 14 + C!
    FF AND       TX-FRM 15 + C!
;

\ ---- BLOCK-SEND ----
\ Read block, build frame, transmit.
: BLOCK-SEND  ( blk# -- )
    DUP CMD-BDATA BUILD-HDR
    BLK-SZ SET-PLEN
    \ Copy block data into frame payload
    BLOCK TX-FRM FRM-HDR + BLK-SZ MOVE
    \ Send frame
    TX-FRM FRM-SZ NE2K-SEND
    1 TX-OK !
;

\ ---- Parse received frame ----
\ Extract fields from RX-FRM buffer.
: PARSE-FRM  ( -- )
    \ Check EtherType
    RX-FRM C + C@ ET-HI <>
    RX-FRM D + C@ ET-LO <> OR IF
        0 RX-CMD ! EXIT
    THEN
    \ Command
    RX-FRM F + C@ RX-CMD !
    \ Block#
    RX-FRM 10 + C@ 8 LSHIFT
    RX-FRM 11 + C@ OR RX-BLK !
    \ Offset
    RX-FRM 12 + C@ 8 LSHIFT
    RX-FRM 13 + C@ OR RX-OFF !
    \ Payload length
    RX-FRM 14 + C@ 8 LSHIFT
    RX-FRM 15 + C@ OR RX-PLEN !
;

\ ---- BLOCK-RECV ----
\ Poll for a block data frame.
\ Returns block# or -1 if no packet.
: BLOCK-RECV  ( -- blk# | -1 )
    RX-FRM 600 NE2K-RECV
    0= IF -1 EXIT THEN
    DROP
    PARSE-FRM
    RX-CMD @ CMD-BDATA <> IF
        -1 EXIT
    THEN
    \ Write received data into block buf
    RX-BLK @ BUFFER
    RX-FRM FRM-HDR + SWAP BLK-SZ MOVE
    UPDATE
    RX-BLK @
;

\ ---- BLOCKS-SEND ----
\ Send a range of blocks.
: BLOCKS-SEND  ( first last -- )
    1+ SWAP DO
        I BLOCK-SEND
    LOOP
;

\ ---- BLOCKS-RECV ----
\ Receive blocks until CMD-BDONE or timeout.
\ Returns count of blocks received.
VARIABLE RECV-CNT
VARIABLE RECV-TOUT
DECIMAL 50000 CONSTANT TOUT-MAX HEX

: BLOCKS-RECV  ( -- count )
    0 RECV-CNT !
    0 RECV-TOUT !
    BEGIN
        BLOCK-RECV
        DUP -1 <> IF
            DROP
            1 RECV-CNT +!
            0 RECV-TOUT !
        ELSE
            DROP
            1 RECV-TOUT +!
        THEN
        RECV-TOUT @ TOUT-MAX >=
    UNTIL
    RECV-CNT @
;

\ ---- SEND-DONE ----
\ Send a "transfer complete" frame.
: SEND-DONE  ( -- )
    0 CMD-BDONE BUILD-HDR
    0 SET-PLEN
    TX-FRM FRM-MIN NE2K-SEND
;

\ ---- NET-SEND ----
\ High-level: send blocks + done signal.
: NET-SEND  ( first last -- )
    BLOCKS-SEND
    SEND-DONE
    ." Sent" CR
;

\ ---- NET-RECV ----
\ High-level: receive all blocks, report.
: NET-RECV  ( -- )
    ." Waiting..." CR
    BLOCKS-RECV
    SAVE-BUFFERS
    ." Received "
    DECIMAL . HEX
    ." blocks" CR
;

." NET-DICT loaded" CR

PREVIOUS FORTH DEFINITIONS
DECIMAL
