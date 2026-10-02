\ ============================================
\ CATALOG: LOG-HARNESS
\ CATEGORY: tools
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ REQUIRES: NE2000
\ Kernel words used: EMIT TICK-COUNT BLOCK UPDATE FILL MOVE
\ ============================================
\
\ Serial-first license telemetry logging harness.
\ Phase 1: synthetic Ethernet-frame fixture, no NIC.
\ Phase 2 extends TEST-ACTIVATION to NE2000 TX+RX.
\ Phase 3 waits on RTL8168 RX ring.
\
\ Scope: own ForthOS paid-vocab activation, own
\ legacy software, and abandoned third-party for
\ preservation. NOT active commercial third-party.
\
\ Ring: overwrite-on-overflow (telemetry never
\ stalls). LOG-TAIL advances to evict oldest bytes
\ before a saturating write.
\
\ Record frame: timestamp:4 port:2 len:2 bytes:len
\
\ ============================================

VOCABULARY LOG-HARNESS
LOG-HARNESS DEFINITIONS
HEX

\ ---- Hex printing ------------------------------
: >HEXCH ( n -- char )
    F AND DUP 9 > IF 7 + THEN 30 + ;

: .HEX2 ( byte -- )
    DUP 4 RSHIFT >HEXCH EMIT >HEXCH EMIT ;

: .HEX4 ( word -- )
    DUP 8 RSHIFT FF AND .HEX2 .HEX2 ;

: .HEX8 ( dword -- )
    DUP 10 RSHIFT .HEX4 .HEX4 ;

VARIABLE HD-ADDR
VARIABLE HD-LEN

: HEX-DUMP ( addr len -- )
    HD-LEN ! HD-ADDR !
    HD-LEN @ 0> IF
        HD-LEN @ 0 DO
            I 10 MOD 0= IF CR HD-ADDR @ I + .HEX8 ."  : " THEN
            HD-ADDR @ I + C@ .HEX2 SPACE
        LOOP
    THEN
    CR ;

\ ---- Big-endian 16-bit I/O ---------------------
: BE16@ ( addr -- u16 )
    DUP C@ 8 LSHIFT SWAP 1+ C@ OR ;

: BE16! ( u16 addr -- )
    OVER 8 RSHIFT OVER C! 1+ C! ;

\ ---- Ring buffer -------------------------------
1000 CONSTANT LOG-BUF-SIZE
CREATE LOG-BUF LOG-BUF-SIZE ALLOT
VARIABLE LOG-HEAD
VARIABLE LOG-TAIL
VARIABLE LOG-COUNT

: LOG-WRAP ( off -- off' )
    LOG-BUF-SIZE 1- AND ;

: LOG-RESET ( -- )
    0 LOG-HEAD !
    0 LOG-TAIL !
    0 LOG-COUNT !
    LOG-BUF LOG-BUF-SIZE 0 FILL ;

: LOG-WRITE1 ( ch -- )
    LOG-BUF LOG-HEAD @ + C!
    LOG-HEAD @ 1+ LOG-WRAP LOG-HEAD ! ;

: LOG-EVICT ( add-len -- )
    LOG-COUNT @ + DUP LOG-BUF-SIZE > IF
        LOG-BUF-SIZE -
        DUP LOG-TAIL @ + LOG-WRAP LOG-TAIL !
        LOG-COUNT @ SWAP - LOG-COUNT !
    ELSE
        DROP
    THEN ;

VARIABLE LP-SRC
VARIABLE LP-LEN

: LOG-PUT ( src len -- )
    LP-LEN ! LP-SRC !
    LP-LEN @ LOG-EVICT
    LP-LEN @ LOG-COUNT +!
    LP-LEN @ 0> IF
        LP-LEN @ 0 DO
            LP-SRC @ I + C@ LOG-WRITE1
        LOOP
    THEN ;

: LOG-GET1 ( offset -- ch )
    LOG-WRAP LOG-BUF + C@ ;

\ ---- Record framer -----------------------------
CREATE HDR-BUF 8 ALLOT
VARIABLE FR-TS
VARIABLE FR-PORT
VARIABLE FR-LEN

: HDR-PACK ( -- )
    FR-TS @ 18 RSHIFT FF AND HDR-BUF 0 + C!
    FR-TS @ 10 RSHIFT FF AND HDR-BUF 1 + C!
    FR-TS @ 8  RSHIFT FF AND HDR-BUF 2 + C!
    FR-TS @              FF AND HDR-BUF 3 + C!
    FR-PORT @ HDR-BUF 4 + BE16!
    FR-LEN  @ HDR-BUF 6 + BE16! ;

: LOG-TRANSACTION ( payload-addr payload-len port -- )
    FR-PORT ! FR-LEN !
    TICK-COUNT @ FR-TS !
    HDR-PACK
    CR ." T=" FR-TS @ .HEX8
    ."  P=" FR-PORT @ .HEX4
    ."  L=" FR-LEN @ .HEX4
    ."  | "
    DUP FR-LEN @ HEX-DUMP
    HDR-BUF 8 LOG-PUT
    FR-LEN @ LOG-PUT ;

\ ---- Frame parsing (Ethernet + IPv4) -----------
: EN-DST   ( frame -- addr ) ;
: EN-SRC   ( frame -- addr ) 6 + ;
: EN-TYPE  ( frame -- u16 )  C + BE16@ ;

: IP-IHL       ( frame -- bytes ) E + C@ F AND 4 * ;
: IP-PROTO     ( frame -- u8 )    17 + C@ ;
: IP-SRC       ( frame -- addr )  1A + ;
: IP-DST       ( frame -- addr )  1E + ;
: IP-TOTAL-LEN ( frame -- u16 )   10 + BE16@ ;

: L4-OFFSET ( frame -- off ) IP-IHL E + ;

: L4-SPORT ( frame -- u16 ) DUP L4-OFFSET + BE16@ ;
: L4-DPORT ( frame -- u16 ) DUP L4-OFFSET + 2 + BE16@ ;

VARIABLE PP-FR

: L4-PAYLOAD-UDP ( -- addr len )
    PP-FR @ DUP L4-OFFSET + 8 +
    PP-FR @ DUP L4-OFFSET + 4 + BE16@ 8 - ;

: L4-PAYLOAD-TCP ( -- addr len )
    PP-FR @ DUP L4-OFFSET + C + C@ F0 AND 2 RSHIFT
    DUP PP-FR @ DUP L4-OFFSET + + SWAP
    PP-FR @ IP-TOTAL-LEN PP-FR @ IP-IHL - SWAP - ;

: L4-PAYLOAD ( frame -- addr len )
    PP-FR !
    PP-FR @ IP-PROTO 11 = IF
        L4-PAYLOAD-UDP
    ELSE PP-FR @ IP-PROTO 6 = IF
        L4-PAYLOAD-TCP
    ELSE
        0 0
    THEN THEN ;

\ ---- Marker scan -------------------------------
\ Each marker: length byte + ASCII bytes.
CREATE M-CHALLENGE  9 C,
    43 C, 48 C, 41 C, 4C C, 4C C, 45 C, 4E C, 47 C, 45 C,
CREATE M-RESPONSE   8 C,
    52 C, 45 C, 53 C, 50 C, 4F C, 4E C, 53 C, 45 C,
CREATE M-KEYEQ      4 C,
    4B C, 45 C, 59 C, 3D C,
CREATE M-LICENSE    7 C,
    4C C, 49 C, 43 C, 45 C, 4E C, 53 C, 45 C,

VARIABLE SM-H
VARIABLE SM-HLEN
VARIABLE SM-M
VARIABLE SM-MLEN

: STR-MATCH ( haystack hlen marker -- flag )
    SM-M ! SM-HLEN ! SM-H !
    SM-M @ C@ SM-MLEN !
    SM-MLEN @ SM-HLEN @ > IF 0 EXIT THEN
    SM-MLEN @ 0 DO
        SM-H @ I + C@
        SM-M @ I 1+ + C@
        <> IF 0 UNLOOP EXIT THEN
    LOOP
    1 ;

VARIABLE MS-ADDR
VARIABLE MS-LEN

: MS-TRY ( marker -- flag )
    >R
    MS-ADDR @ MS-LEN @ R> STR-MATCH ;

: MARKER-SCAN ( addr len -- idx | -1 )
    DUP 0> 0= IF 2DROP -1 EXIT THEN
    MS-LEN ! MS-ADDR !
    MS-LEN @ 0 DO
        MS-ADDR @ I + MS-LEN @ I -
        2DUP M-CHALLENGE STR-MATCH IF 2DROP I UNLOOP EXIT THEN
        2DUP M-RESPONSE  STR-MATCH IF 2DROP I UNLOOP EXIT THEN
        2DUP M-KEYEQ     STR-MATCH IF 2DROP I UNLOOP EXIT THEN
             M-LICENSE   STR-MATCH IF        I UNLOOP EXIT THEN
    LOOP
    -1 ;

\ ---- INSPECT-PACKET ----------------------------
VARIABLE IP-FR
VARIABLE IP-FL

: INSPECT-PACKET ( frame framelen -- flag )
    IP-FL ! IP-FR !
    IP-FL @ E < IF 0 EXIT THEN
    IP-FR @ EN-TYPE 800 <> IF 0 EXIT THEN
    IP-FR @ IP-IHL 14 < IF 0 EXIT THEN
    IP-FL @ IP-FR @ IP-IHL E + < IF 0 EXIT THEN
    IP-FL @ IP-FR @ IP-TOTAL-LEN E + < IF 0 EXIT THEN
    IP-FR @ IP-PROTO 11 = IF
        IP-FL @ IP-FR @ L4-OFFSET 8 + < IF 0 EXIT THEN
    ELSE IP-FR @ IP-PROTO 6 = IF
        IP-FL @ IP-FR @ L4-OFFSET 14 + < IF 0 EXIT THEN
    ELSE
        0 EXIT
    THEN THEN
    IP-FR @ L4-PAYLOAD                ( paddr plen )
    IP-FR @ L4-DPORT                  ( paddr plen dport )
    LOG-TRANSACTION
    IP-FR @ L4-PAYLOAD                ( paddr plen )
    MARKER-SCAN -1 <> ;

\ ---- Block persistence -------------------------
\ D0 hex = 208 decimal = TELEMETRY_RESERVED.start
8  CONSTANT LOG-BLOCK-COUNT
D0 CONSTANT LOG-BLOCK-FIRST

VARIABLE BD-REMAIN
VARIABLE BD-TAILOFF

: BD-COPY-ONE ( blkaddr nbytes -- )
    DUP 0> IF
        DUP 0 DO
            BD-TAILOFF @ I + LOG-WRAP LOG-BUF + C@
            2 PICK I + C!
        LOOP
    THEN
    2DROP ;

: LOG-DUMP-TO-BLOCK ( -- )
    LOG-COUNT @ BD-REMAIN  !
    LOG-TAIL  @ BD-TAILOFF !
    LOG-BLOCK-COUNT 0 DO
        I LOG-BLOCK-FIRST + BUFFER      ( blkaddr )
        DUP 400 0 FILL
        DUP BD-REMAIN @ 400 MIN
        DUP >R BD-COPY-ONE              ( blkaddr | R:nbytes )
        R@ BD-TAILOFF @ + LOG-WRAP BD-TAILOFF !
        BD-REMAIN @ R> - BD-REMAIN !
        DROP
        I LOG-BLOCK-FIRST + UPDATE
    LOOP
    SAVE-BUFFERS ;

\ ---- Serial dump with forward-resync -----------
VARIABLE DUMP-OFF
VARIABLE DUMP-REM

: DUMP-REC-SIZE ( -- 8+len )
    DUMP-OFF @ 6 + LOG-GET1 8 LSHIFT
    DUMP-OFF @ 7 + LOG-GET1 OR
    8 + ;

: DUMP-RECORD ( -- )
    DUMP-OFF @ 0 + LOG-GET1 18 LSHIFT
    DUMP-OFF @ 1 + LOG-GET1 10 LSHIFT OR
    DUMP-OFF @ 2 + LOG-GET1 8  LSHIFT OR
    DUMP-OFF @ 3 + LOG-GET1              OR    ( ts )
    DUMP-OFF @ 4 + LOG-GET1 8 LSHIFT
    DUMP-OFF @ 5 + LOG-GET1 OR                 ( ts port )
    DUMP-OFF @ 6 + LOG-GET1 8 LSHIFT
    DUMP-OFF @ 7 + LOG-GET1 OR                 ( ts port len )
    CR ." T=" ROT .HEX8
    ."  P=" SWAP .HEX4
    ."  L=" DUP .HEX4
    ."  | "
    DUP 0> IF
        DUP 0 DO
            DUMP-OFF @ 8 + I + LOG-GET1 .HEX2 SPACE
        LOOP
    THEN
    DROP CR ;

: LOG-DUMP ( -- )
    LOG-COUNT @ 0 = IF ." (log empty)" CR EXIT THEN
    LOG-TAIL  @ DUMP-OFF !
    LOG-COUNT @ DUMP-REM !
    BEGIN
        DUMP-REM @ 8 < IF EXIT THEN
        DUMP-REC-SIZE DUMP-REM @ > IF
            DUMP-OFF @ 1+ LOG-WRAP DUMP-OFF !
            DUMP-REM @ 1- DUMP-REM !
        ELSE
            DUMP-RECORD
            DUMP-OFF @ DUMP-REC-SIZE + LOG-WRAP DUMP-OFF !
            DUMP-REM @ DUMP-REC-SIZE - DUMP-REM !
        THEN
    AGAIN ;

\ ---- TEST-ACTIVATION (Phase 1 stub) ------------
CREATE TA-FRAME 100 ALLOT

: TA-C! ( val offset -- )
    TA-FRAME + C! ;

: TA-16! ( val offset -- )
    TA-FRAME + BE16! ;

: TA-FILL-ETH ( -- )
    6 0 DO FF I TA-C! LOOP
    02 6 TA-C!  00 7 TA-C!  00 8 TA-C!
    00 9 TA-C!  00 A TA-C!  01 B TA-C!
    800 C TA-16! ;

: TA-FILL-IP ( total-len -- )
    45 E TA-C!
    00 F TA-C!
    10 TA-16!
    0 12 TA-16!
    0 14 TA-16!
    40 16 TA-C!
    11 17 TA-C!
    0 18 TA-16!
    0A 1A TA-C!  00 1B TA-C!  00 1C TA-C!  01 1D TA-C!
    0A 1E TA-C!  00 1F TA-C!  00 20 TA-C!  02 21 TA-C! ;

: TA-FILL-UDP ( udp-len sport dport -- )
    24 TA-16!
    22 TA-16!
    26 TA-16!
    0 28 TA-16! ;

: TA-COPY-PAYLOAD ( src len -- )
    TA-FRAME 2A + SWAP MOVE ;

\ Lengths hard-coded. HERE X - CONSTANT misreads HERE across
\ block-interpret boundaries in interpret mode.
CREATE TA-CHALLENGE-STR
    4B C, 45 C, 59 C, 3D C,
    30 C, 78 C,
    44 C, 45 C, 41 C, 44 C,
    42 C, 45 C, 45 C, 46 C,
E CONSTANT TA-CHALLENGE-LEN

CREATE TA-RESPONSE-STR
    52 C, 45 C, 53 C, 50 C,
    4F C, 4E C, 53 C, 45 C,
    3D C, 30 C, 78 C,
    43 C, 41 C, 46 C, 45 C,
    42 C, 41 C, 42 C, 45 C,
13 CONSTANT TA-RESPONSE-LEN

VARIABLE TB-SRC
VARIABLE TB-LEN
VARIABLE TB-SPORT
VARIABLE TB-DPORT

: TA-BUILD ( src paylen sport dport -- framelen )
    TB-DPORT ! TB-SPORT ! TB-LEN ! TB-SRC !
    TA-FRAME 100 0 FILL
    TA-FILL-ETH
    TB-LEN @ 1C + TA-FILL-IP
    TB-LEN @ 8 + TB-SPORT @ TB-DPORT @ TA-FILL-UDP
    TB-SRC @ TB-LEN @ TA-COPY-PAYLOAD
    TB-LEN @ 2A + ;

: TEST-ACTIVATION ( -- )
    LOG-RESET
    CR ." TEST-ACTIVATION phase 1 (synthetic, no NIC)" CR
    TA-CHALLENGE-STR TA-CHALLENGE-LEN 3039 1234 TA-BUILD
    TA-FRAME SWAP INSPECT-PACKET
    IF   ." challenge: marker hit"
    ELSE ." challenge: marker miss"
    THEN CR
    TA-RESPONSE-STR TA-RESPONSE-LEN 1234 3039 TA-BUILD
    TA-FRAME SWAP INSPECT-PACKET
    IF   ." response: marker hit"
    ELSE ." response: marker miss"
    THEN CR ;

\ ---- TEST-ACTIVATION-NIC (Phase 2: real NE2000) -
\ Pre-req: NE2K-INIT must have run successfully.
\ Uses QEMU SLiRP addressing: src 10.0.2.15,
\ dst 10.0.2.2 so host-side Python peer sees it.

ALSO NE2000

CREATE TA-RX-FRAME 600 ALLOT

\ Ethernet frame with QEMU SLiRP gateway MAC. The default SLiRP
\ gateway at 10.0.2.2 answers ARP with MAC 52:55:0a:00:02:02;
\ broadcast-MAC frames are not forwarded upstream.
: TA-FILL-ETH-NIC ( -- )
    52 0 TA-C!  55 1 TA-C!  0A 2 TA-C!
    00 3 TA-C!  02 4 TA-C!  02 5 TA-C!
    52 6 TA-C!  54 7 TA-C!  00 8 TA-C!
    12 9 TA-C!  34 A TA-C!  56 B TA-C!
    800 C TA-16! ;

\ IPv4 header checksum (same algorithm as rtl8168.fth:344).
\ Sums all 10 words of the 20-byte IP header, folds carries,
\ one's complements. SLiRP drops frames with zero checksum.
: IP-CKSUM ( ip-hdr-addr -- checksum )
    0
    A 0 DO
        OVER I DUP + +
        DUP C@ 8 LSHIFT
        SWAP 1+ C@ OR +
    LOOP
    NIP
    DUP 10 RSHIFT +
    DUP 10 RSHIFT +
    FFFF AND FFFF XOR ;

: TA-FILL-IP-NIC ( total-len -- )
    45 E TA-C!
    00 F TA-C!
    10 TA-16!
    0 12 TA-16!
    0 14 TA-16!
    40 16 TA-C!
    11 17 TA-C!
    0 18 TA-16!
    0A 1A TA-C!  00 1B TA-C!  02 1C TA-C!  0F 1D TA-C!
    0A 1E TA-C!  00 1F TA-C!  02 20 TA-C!  02 21 TA-C!
    TA-FRAME E + IP-CKSUM 18 TA-16! ;

: TA-BUILD-NIC ( src paylen sport dport -- framelen )
    TB-DPORT ! TB-SPORT ! TB-LEN ! TB-SRC !
    TA-FRAME 100 0 FILL
    TA-FILL-ETH-NIC
    TB-LEN @ 1C + TA-FILL-IP-NIC
    TB-LEN @ 8 + TB-SPORT @ TB-DPORT @ TA-FILL-UDP
    TB-SRC @ TB-LEN @ TA-COPY-PAYLOAD
    TB-LEN @ 2A + ;

VARIABLE NIC-DEADLINE

: TA-POLL-RX ( ticks -- addr len | 0 0 )
    TICK-COUNT @ + NIC-DEADLINE !
    BEGIN
        NE2K-RECV? IF
            TA-RX-FRAME 600 NE2K-RECV
            DUP 0> IF
                TA-RX-FRAME SWAP EXIT
            THEN
            DROP
        THEN
        TICK-COUNT @ NIC-DEADLINE @ >
    UNTIL
    0 0 ;

: TEST-ACTIVATION-NIC ( -- )
    LOG-RESET
    CR ." TEST-ACTIVATION-NIC phase 2 (NE2000 TX+RX)" CR
    TA-CHALLENGE-STR TA-CHALLENGE-LEN 3039 1234 TA-BUILD-NIC
    DUP >R
    TA-FRAME R@ NE2K-SEND
    TA-FRAME R> INSPECT-PACKET
    IF   ." nic tx: marker hit"
    ELSE ." nic tx: marker miss"
    THEN CR
    400 TA-POLL-RX
    DUP 0= IF
        2DROP ." nic rx: timeout" CR
    ELSE
        INSPECT-PACKET
        IF   ." nic rx: marker hit"
        ELSE ." nic rx: no marker"
        THEN CR
    THEN ;

PREVIOUS

\ ---- Initialize --------------------------------
LOG-RESET

ONLY FORTH ALSO DEFINITIONS
