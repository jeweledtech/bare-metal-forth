\ ============================================
\ CATALOG: FILE-STREAM
\ CATEGORY: substrate
\ PLATFORM: x86
\ SOURCE: hand-written
\ REQUIRES: NTFS ( MFT-FIND MFT-READ MFT-BUF )
\ REQUIRES: NTFS ( MFT-ATTR ATTR-DATA PARSE-RUN )
\ REQUIRES: NTFS ( PR-PTR PR-LEN PR-OFF RUN-PREV )
\ REQUIRES: NTFS ( SEC/CLUS PART-LBA FOUND-REC )
\ REQUIRES: AHCI ( AHCI-READ SEC-BUF )
\ REQUIRES: RTL8168 ( UDP-SEND TX-PAYLOAD TX-PLEN )
\ CONFIDENCE: medium
\ ============================================
\
\ Stream complete files off NTFS over UDP.
\ Multi-run reader + FBLK chunked transport.
\
\ Usage:
\   USING FILE-STREAM
\   S" i8042prt.sys" FILE-STREAM
\
\ Receiver: tools/net-receive.py
\
\ ============================================

VOCABULARY FILE-STREAM
FILE-STREAM DEFINITIONS
ALSO NTFS
ALSO AHCI
ALSO RTL8168
HEX

\ ============================================
\ Section 1: CRC-32
\ ============================================

EDB88320 CONSTANT CRC32-POLY
FFFFFFFF CONSTANT CRC32-MASK

DECIMAL
CREATE CRC32-TABLE 1024 ALLOT

: CRC32-INIT ( -- )
    256 0 DO
        I
        8 0 DO
            DUP 1 AND IF
                1 RSHIFT CRC32-POLY XOR
            ELSE
                1 RSHIFT
            THEN
        LOOP
        CRC32-TABLE I 4 * + !
    LOOP
;

CRC32-INIT

: CRC32 ( addr len -- crc )
    CRC32-MASK SWAP
    0 DO
        OVER I + C@
        OVER XOR 255 AND 4 *
        CRC32-TABLE + @
        SWAP 8 RSHIFT XOR
    LOOP
    NIP CRC32-MASK XOR
;

\ ============================================
\ Section 2: FBLK framing
\ ============================================

HEX
46424C4B CONSTANT FBLK-MAGIC
DECIMAL
20 CONSTANT FBLK-HDR-SZ
256 CONSTANT FBLK-NAME-SZ
4096 CONSTANT FBLK-CHUNK-SZ
1434 CONSTANT MAX-PAYLOAD
1178 CONSTANT MAX-PL-C0
1 CONSTANT F-EOF
2 CONSTANT F-SPARSE

CREATE CHUNK-HDR  20 ALLOT
CREATE CHUNK-NAME 256 ALLOT
CREATE SEND-BUF   1500 ALLOT
VARIABLE CHUNK#
VARIABLE STREAM-SID
VARIABLE STREAM-SIZE
VARIABLE STREAM-SENT

\ Big-endian 16-bit store
: BE-W! ( val addr -- )
    OVER 8 RSHIFT OVER C!
    1+ SWAP 255 AND SWAP C!
;

\ Big-endian 32-bit store
: BE! ( val addr -- )
    OVER 24 RSHIFT OVER C!
    1+ OVER 16 RSHIFT 255 AND
    OVER C! 1+
    OVER 8 RSHIFT 255 AND
    OVER C! 1+
    SWAP 255 AND SWAP C!
;

\ Build 20-byte FBLK header in CHUNK-HDR
: BUILD-HDR ( payload-len flags -- )
    SWAP
    FBLK-MAGIC CHUNK-HDR BE!
    STREAM-SID @ CHUNK-HDR 4 + BE!
    STREAM-SIZE @ CHUNK-HDR 8 + BE!
    CHUNK# @ CHUNK-HDR 12 + BE!
    CHUNK-HDR 16 + BE-W!
    CHUNK-HDR 18 + BE-W!
;

\ ============================================
\ Section 3: Sink infrastructure
\ ============================================

VARIABLE 'FILE-SINK

: DO-SINK ( buf len -- )
    'FILE-SINK @ EXECUTE
;

\ Send one UDP packet from SEND-BUF.
\ Copies CHUNK-HDR + data into SEND-BUF,
\ then calls UDP-SEND.
: SEND-CHUNK ( data-addr data-len -- )
    DUP >R
    CHUNK-HDR SEND-BUF
    FBLK-HDR-SZ CMOVE
    CHUNK# @ 0= IF
        CHUNK-NAME SEND-BUF FBLK-HDR-SZ +
        FBLK-NAME-SZ CMOVE
        SEND-BUF FBLK-HDR-SZ +
        FBLK-NAME-SZ + SWAP CMOVE
        SEND-BUF
        R> FBLK-HDR-SZ +
        FBLK-NAME-SZ +
    ELSE
        SEND-BUF FBLK-HDR-SZ + SWAP
        CMOVE
        SEND-BUF
        R> FBLK-HDR-SZ +
    THEN
    UDP-SEND
    1 CHUNK# +!
;

\ Default sink: chunk into UDP packets
: NET-CHUNK-SINK ( buf len -- )
    BEGIN DUP 0> WHILE
        DUP
        CHUNK# @ 0= IF
            MAX-PL-C0
        ELSE MAX-PAYLOAD THEN
        MIN
        DUP 0 BUILD-HDR
        2 PICK OVER SEND-CHUNK
        DUP STREAM-SENT +!
        ROT OVER + -ROT -
    REPEAT
    2DROP
;

\ Send EOF marker (zero-payload packet)
: STREAM-DONE ( -- )
    0 F-EOF BUILD-HDR
    CHUNK-HDR SEND-BUF
    FBLK-HDR-SZ CMOVE
    SEND-BUF FBLK-HDR-SZ UDP-SEND
;

\ ============================================
\ Section 4: FILE-STREAM
\ ============================================

HEX
20 CONSTANT ATTR-RUNOFF
30 CONSTANT ATTR-RSIZE
DECIMAL

VARIABLE FS-ATTR
VARIABLE FS-LBA
VARIABLE FS-RSECS
VARIABLE FS-SPARSE

\ Zero-fill SEC-BUF for sparse runs
: ZERO-SEC-BUF ( -- )
    SEC-BUF FBLK-CHUNK-SZ 0 FILL
;

\ Compute bytes to send for this batch.
\ Caps at remaining file size.
: BATCH-LEN ( secs -- bytes )
    512 *
    STREAM-SIZE @ STREAM-SENT @ -
    MIN
;

\ Send one run's data through sink.
\ FS-LBA = starting LBA of run.
\ FS-RSECS = total sectors in run.
: SEND-RUN ( -- )
    BEGIN FS-RSECS @ 0> WHILE
        FS-SPARSE @ IF
            ZERO-SEC-BUF
        ELSE
            FS-LBA @ 8 FS-RSECS @ MIN
            AHCI-READ DROP
        THEN
        8 FS-RSECS @ MIN BATCH-LEN
        DUP 0> IF
            SEC-BUF SWAP DO-SINK
        ELSE
            DROP
        THEN
        8 FS-LBA +!
        -8 FS-RSECS +!
    REPEAT
;

\ Stream a named file over the sink.
: FILE-STREAM ( addr len -- )
    \ Save filename into CHUNK-NAME
    CHUNK-NAME FBLK-NAME-SZ 0 FILL
    2DUP CHUNK-NAME SWAP CMOVE
    \ Compute session ID
    2DUP CRC32 STREAM-SID !
    \ Find file in MFT
    MFT-FIND 0= IF
        ." Not found" CR EXIT
    THEN
    FOUND-REC !
    FOUND-REC @ MFT-READ IF
        ." MFT read err" CR EXIT
    THEN
    \ Locate $DATA attribute
    ATTR-DATA MFT-ATTR
    DUP 0= IF
        DROP ." No DATA" CR EXIT
    THEN
    DUP 8 + C@ 0= IF
        DROP ." Resident" CR EXIT
    THEN
    FS-ATTR !
    \ Extract file size (+30h)
    FS-ATTR @ ATTR-RSIZE + @
    STREAM-SIZE !
    \ Initialize state
    0 CHUNK# !
    0 STREAM-SENT !
    0 RUN-PREV !
    \ Set run-list pointer
    FS-ATTR @ DUP ATTR-RUNOFF + W@ +
    PR-PTR !
    \ Walk all data runs
    BEGIN
        PR-PTR @ C@ DUP 0<> WHILE
        \ Peek high nibble for sparse
        4 RSHIFT 0= IF
            -1 FS-SPARSE !
        ELSE
            0 FS-SPARSE !
        THEN
        PARSE-RUN DROP
        \ Accumulate absolute cluster
        FS-SPARSE @ 0= IF
            PR-OFF @ RUN-PREV +!
        THEN
        \ Convert clusters to LBA
        RUN-PREV @ SEC/CLUS @ *
        PART-LBA @ + FS-LBA !
        PR-LEN @ SEC/CLUS @ *
        FS-RSECS !
        SEND-RUN
        \ Check if file fully sent
        STREAM-SENT @
        STREAM-SIZE @ >= IF
            0 PR-PTR @ C!
        THEN
    REPEAT
    DROP
    STREAM-DONE
    ." Streamed "
    STREAM-SENT @ .
    ." bytes" CR
;

\ Set default sink
' NET-CHUNK-SINK 'FILE-SINK !

ONLY FORTH DEFINITIONS
DECIMAL