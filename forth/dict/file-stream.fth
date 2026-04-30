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
    CRC32-MASK -ROT
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
