\ ============================================
\ CATALOG: FAT32
\ CATEGORY: filesystem
\ PLATFORM: x86
\ SOURCE: hand-written
\ REQUIRES: AHCI HARDWARE
\ CONFIDENCE: medium
\ ============================================
\
\ FAT32 filesystem reader.
\ Reads the EFI System Partition (GPT type
\ C12A7328) via AHCI DMA. Lists directories,
\ navigates subdirs, reads files.
\
\ Usage:
\   USING FAT32
\   FAT32-INIT
\   FAT32-LS
\   S" EFI" FAT32-CD
\   FAT32-LS
\
\ ============================================

VOCABULARY FAT32
FAT32 DEFINITIONS
ALSO AHCI
ALSO HARDWARE
HEX

\ ---- Constants ----
200 CONSTANT SECT-SZ
20 CONSTANT DIR-ESIZ
C12A7328 CONSTANT EFI-GUID
0FFFFFF8 CONSTANT FAT-EOC
0FFFFFFF CONSTANT FAT-MASK

\ ---- Hex helpers ----
: >HEXCH ( n -- char )
    F AND DUP 9 > IF 7 + THEN 30 +
;
: .H2 ( byte -- )
    DUP 4 RSHIFT >HEXCH EMIT
    >HEXCH EMIT
;
: .H4 ( word -- )
    DUP 8 RSHIFT FF AND .H2 .H2
;
: .H8 ( dword -- )
    DUP 10 RSHIFT .H4 .H4
;

\ ---- String helpers ----
: >UPC ( c -- C )
    DUP 61 < IF EXIT THEN
    DUP 7A > IF EXIT THEN
    20 -
;

\ ---- Buffers ----
CREATE DIR-BUF 1000 ALLOT
CREATE MATCH-BUF B ALLOT

\ ---- State variables ----
VARIABLE EFI-LBA
VARIABLE FAT-LBA
VARIABLE DATA-LBA
VARIABLE ROOT-CLUST
VARIABLE SECTS/CLUST
VARIABLE RSVD-SECTS
VARIABLE NUM-FATS
VARIABLE SECTS/FAT
VARIABLE CUR-DIR
VARIABLE M-POS

\ ============================================
\ 8.3 filename handling
\ ============================================

\ Convert "NAME.EXT" to 11-byte padded 8.3
: PAD83 ( addr len -- )
    MATCH-BUF B 20 FILL
    0 M-POS !
    0 DO
        DUP I + C@
        DUP 2E = IF
            DROP 8 M-POS !
        ELSE
            >UPC
            M-POS @ MATCH-BUF + C!
            1 M-POS +!
        THEN
    LOOP
    DROP
;

\ Compare entry's 8.3 name with MATCH-BUF
: NAME83= ( entry -- flag )
    B 0 DO
        DUP I + C@
        MATCH-BUF I + C@
        <> IF
            DROP 0 UNLOOP EXIT
        THEN
    LOOP
    DROP -1
;

\ Print 8.3 filename nicely
: .FNAME ( entry -- )
    8 0 DO
        DUP I + C@ DUP 20 <> IF
            EMIT ELSE DROP
        THEN
    LOOP
    DUP 8 + C@ 20 <> IF
        2E EMIT
        3 0 DO
            DUP 8 I + + C@ DUP 20 <> IF
                EMIT ELSE DROP
            THEN
        LOOP
    THEN
    DROP
;

\ ============================================
\ GPT: find EFI System Partition
\ ============================================

: SCAN-EFI ( sector-lba -- flag )
    1 AHCI-READ IF 0 EXIT THEN
    4 0 DO
        SEC-BUF I 80 * +
        DUP @ EFI-GUID = IF
            20 + @ EFI-LBA !
            -1 UNLOOP EXIT
        THEN
        DROP
    LOOP
    0
;

\ ============================================
\ FAT32 boot sector parsing
\ ============================================

: PARSE-BPB ( -- )
    SEC-BUF 0D + C@ SECTS/CLUST !
    SEC-BUF 0E + W@ RSVD-SECTS !
    SEC-BUF 10 + C@ NUM-FATS !
    SEC-BUF 24 + @ SECTS/FAT !
    SEC-BUF 2C + @ ROOT-CLUST !
    EFI-LBA @ RSVD-SECTS @ + FAT-LBA !
    FAT-LBA @
    NUM-FATS @ SECTS/FAT @ * +
    DATA-LBA !
    ROOT-CLUST @ CUR-DIR !
;

\ ============================================
\ Core FAT32 operations
\ ============================================

: CLUST>LBA ( cluster -- lba )
    2 - SECTS/CLUST @ * DATA-LBA @ +
;

: FAT-END? ( cluster -- flag )
    FAT-EOC >=
;

\ Read FAT entry for cluster
: FAT-NEXT ( cluster -- next )
    2 LSHIFT
    DUP 9 RSHIFT FAT-LBA @ +
    1 AHCI-READ DROP
    1FF AND SEC-BUF + @
    FAT-MASK AND
;

\ Read one cluster into DIR-BUF
: READ-CLUST ( cluster -- flag )
    CLUST>LBA SECTS/CLUST @ AHCI-READ IF
        1 EXIT
    THEN
    SEC-BUF DIR-BUF
    SECTS/CLUST @ SECT-SZ * CMOVE
    0
;

\ Entries per cluster
: DIR-ENTRIES ( -- n )
    SECTS/CLUST @ 4 LSHIFT
;

\ Get start cluster from dir entry
: DIR-CLUST ( entry -- cluster )
    DUP 14 + W@ 10 LSHIFT
    SWAP 1A + W@ OR
;

\ ============================================
\ FAT32-INIT
\ ============================================

: FAT32-INIT ( -- )
    AH-FOUND @ 0= IF
        ." AHCI not init" CR EXIT
    THEN
    1 1 AHCI-READ IF
        ." GPT read err" CR EXIT
    THEN
    SEC-BUF @ 20494645 <> IF
        ." No GPT" CR EXIT
    THEN
    2 SCAN-EFI 0= IF
        3 SCAN-EFI 0= IF
            4 SCAN-EFI 0= IF
                5 SCAN-EFI 0= IF
                    ." No EFI part" CR
                    EXIT
                THEN
            THEN
        THEN
    THEN
    ." EFI at LBA " EFI-LBA @ .H8 CR
    EFI-LBA @ 1 AHCI-READ IF
        ." Boot sect err" CR EXIT
    THEN
    \ Check FAT32 signature at offset 52h
    SEC-BUF 24 + @ 0= IF
        ." Not FAT32" CR EXIT
    THEN
    PARSE-BPB
    ." FAT at LBA " FAT-LBA @ .H8 CR
    ." Data at LBA " DATA-LBA @ .H8 CR
    ." Root clust "
    ROOT-CLUST @ DECIMAL . HEX CR
    ." Sects/clust "
    SECTS/CLUST @ DECIMAL . HEX CR
    ." FAT32 ready" CR
;

\ ============================================
\ Directory listing
\ ============================================

VARIABLE DL-END

: DIR-LIST ( cluster -- )
    0 DL-END !
    BEGIN
        DUP READ-CLUST IF
            DROP ." Read err" CR EXIT
        THEN
        DIR-ENTRIES 0 DO
            DIR-BUF I DIR-ESIZ * +
            DUP C@ 0= IF
                DROP -1 DL-END !
                LEAVE
            THEN
            DUP C@ E5 = IF DROP ELSE
            DUP B + C@ 0F = IF DROP ELSE
            DUP B + C@ 8 = IF DROP ELSE
                DUP .FNAME
                DUP B + C@ 10 AND IF
                    ."  <DIR>" SPACE
                ELSE
                    SPACE
                    DUP 1C + @
                    DECIMAL . HEX
                THEN
                DIR-CLUST
                ." cl=" DECIMAL . HEX CR
            THEN THEN THEN
        LOOP
        DL-END @ IF DROP EXIT THEN
        FAT-NEXT
        DUP FAT-END? IF DROP EXIT THEN
    AGAIN
;

: FAT32-LS ( -- ) CUR-DIR @ DIR-LIST ;

\ ============================================
\ Directory navigation and search
\ ============================================

VARIABLE FD-CLUST
VARIABLE FD-SIZE
VARIABLE FD-FOUND

: FAT32-FIND ( addr len -- clust size -1 | 0 )
    PAD83
    0 FD-FOUND !
    CUR-DIR @
    BEGIN
        DUP READ-CLUST IF
            DROP 0 EXIT
        THEN
        DIR-ENTRIES 0 DO
            DIR-BUF I DIR-ESIZ * +
            DUP C@ 0= IF
                DROP LEAVE
            THEN
            DUP C@ E5 = IF DROP ELSE
            DUP B + C@ 0F = IF DROP ELSE
                DUP NAME83= IF
                    DUP DIR-CLUST FD-CLUST !
                    1C + @ FD-SIZE !
                    -1 FD-FOUND !
                    LEAVE
                ELSE DROP
                THEN
            THEN THEN
        LOOP
        FD-FOUND @ IF
            DROP
            FD-CLUST @ FD-SIZE @ -1
            EXIT
        THEN
        FAT-NEXT
        DUP FAT-END? IF
            DROP 0 EXIT
        THEN
    AGAIN
;

: FAT32-CD ( addr len -- )
    FAT32-FIND 0= IF
        ." Not found" CR EXIT
    THEN
    DROP CUR-DIR !
;

\ ============================================
\ File reading
\ ============================================

: FAT32-CAT ( addr len -- )
    FAT32-FIND 0= IF
        ." Not found" CR EXIT
    THEN
    ." Size: " DUP DECIMAL . HEX
    ." bytes" CR
    DROP
    CLUST>LBA 1 AHCI-READ IF
        ." Read err" CR EXIT
    THEN
    100 0 DO
        SEC-BUF I + C@ .H2 SPACE
        I F AND F = IF CR THEN
    LOOP
    CR
;

VARIABLE RD-BUF
VARIABLE RD-LEFT
VARIABLE RD-CLUST
VARIABLE RD-N

: FAT32-READ ( cluster count buf -- flag )
    RD-BUF ! RD-LEFT ! RD-CLUST !
    BEGIN RD-LEFT @ 0> WHILE
        SECTS/CLUST @ RD-LEFT @ MIN
        RD-N !
        RD-CLUST @ CLUST>LBA RD-N @
        AHCI-READ IF 1 EXIT THEN
        SEC-BUF RD-BUF @
        RD-N @ SECT-SZ * CMOVE
        RD-N @ SECT-SZ * RD-BUF +!
        RD-N @ NEGATE RD-LEFT +!
        RD-CLUST @ FAT-NEXT
        DUP FAT-END? IF
            DROP 0 EXIT
        THEN
        RD-CLUST !
    REPEAT
    0
;

ONLY FORTH DEFINITIONS
DECIMAL
