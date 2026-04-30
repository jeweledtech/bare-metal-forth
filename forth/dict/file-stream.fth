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
