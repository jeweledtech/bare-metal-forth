\ ============================================
\ CATALOG: NTFS
\ CATEGORY: filesystem
\ PLATFORM: x86
\ SOURCE: hand-written
\ REQUIRES: AHCI HARDWARE
\ CONFIDENCE: medium
\ ============================================
\
\ NTFS MFT walker.
\ Finds files by name on NTFS partitions,
\ reads file content via AHCI DMA.
\
\ Usage:
\   USING NTFS
\   NTFS-INIT
\   S" bootmgr" MFT-FIND
\   S" i8042prt.sys" FILE-DUMP
\
\ ============================================

VOCABULARY NTFS
NTFS DEFINITIONS
ALSO AHCI
ALSO HARDWARE
HEX

\ ---- Constants ----
454C4946 CONSTANT FILE-SIG
30 CONSTANT ATTR-FNAME
80 CONSTANT ATTR-DATA
FFFFFFFF CONSTANT ATTR-END
400 CONSTANT MFT-REC-SZ
1FE CONSTANT FIXUP-OFF1
3FE CONSTANT FIXUP-OFF2
64 CONSTANT DOT-EVERY
5346544E CONSTANT NTFS-SIG

\ ---- Buffers ----
400 PHYS-ALLOC CONSTANT MFT-BUF
CREATE NAME-BUF 100 ALLOT
CREATE GPT-LBAS 20 ALLOT

\ ---- State ----
VARIABLE PART-LBA
VARIABLE MFT-BASE
VARIABLE SEC/CLUS
VARIABLE NAME-LEN
VARIABLE RUN-LBA
VARIABLE RUN-SECS
VARIABLE RUN-PREV
VARIABLE FOUND-REC
VARIABLE TGT-A
VARIABLE TGT-L
VARIABLE GPT-N

\ ---- Hex helpers ----
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

\ ============================================
\ String comparison
\ ============================================

: >UPC ( c -- C )
    DUP 61 < IF EXIT THEN
    DUP 7A > IF EXIT THEN
    20 -
;

: CAPS= ( c1 c2 -- flag )
    >UPC SWAP >UPC =
;

: NAME= ( a1 l1 a2 l2 -- flag )
    ROT OVER <> IF
        2DROP DROP 0 EXIT
    THEN
    DUP 0= IF
        2DROP DROP -1 EXIT
    THEN
    0 DO
        OVER I + C@
        OVER I + C@
        CAPS= 0= IF
            2DROP 0
            UNLOOP EXIT
        THEN
    LOOP
    2DROP -1
;

\ ============================================
\ MFT fixup + read
\ ============================================

: MFT-FIXUP ( -- flag )
    MFT-BUF 4 + W@
    MFT-BUF + >R
    R@ W@
    \ Check sector 0 signature
    MFT-BUF FIXUP-OFF1 + W@
    OVER <> IF
        DROP R> DROP 1 EXIT
    THEN
    \ Apply sector 0 fixup
    R@ 2 + W@
    MFT-BUF FIXUP-OFF1 + W!
    \ Check sector 1 signature
    MFT-BUF FIXUP-OFF2 + W@
    OVER <> IF
        DROP R> DROP 1 EXIT
    THEN
    DROP
    \ Apply sector 1 fixup
    R> 4 + W@
    MFT-BUF FIXUP-OFF2 + W!
    0
;

: MFT-READ ( record# -- flag )
    DUP + MFT-BASE @ +
    2 AHCI-READ IF
        1 EXIT
    THEN
    SEC-BUF MFT-BUF MFT-REC-SZ CMOVE
    MFT-FIXUP
;

\ ============================================
\ Attribute walker
\ ============================================

: MFT-ATTR ( type -- addr | 0 )
    >R
    MFT-BUF 14 + W@
    MFT-BUF +
    BEGIN
        DUP @
        DUP ATTR-END = IF
            DROP DROP R> DROP
            0 EXIT
        THEN
        R@ = IF
            R> DROP EXIT
        THEN
        DUP 4 + @
        DUP 0= IF
            2DROP R> DROP
            0 EXIT
        THEN
        +
    AGAIN
;

\ ============================================
\ Filename extraction
\ ============================================

: EXTRACT-NAME ( value-addr -- a l )
    DUP 40 + C@
    DUP NAME-LEN !
    SWAP 42 +
    SWAP 0 DO
        DUP I DUP + + C@
        NAME-BUF I + C!
    LOOP
    DROP
    NAME-BUF NAME-LEN @
;

: MFT-FILENAME ( -- a l | 0 0 )
    MFT-BUF 14 + W@
    MFT-BUF + >R
    BEGIN
        R@ @
        DUP ATTR-END = IF
            DROP R> DROP
            0 0 EXIT
        THEN
        ATTR-FNAME = IF
            R@ 14 + W@ R@ +
            DUP 41 + C@
            2 <> IF
                EXTRACT-NAME
                R> DROP EXIT
            THEN
            DROP
        THEN
        R@ 4 + @
        DUP 0= IF
            DROP R> DROP
            0 0 EXIT
        THEN
        R> + >R
    AGAIN
;

\ ============================================
\ MFT search
\ ============================================

: MFT-FIND ( addr len -- rec# -1 | 0 )
    TGT-L ! TGT-A !
    ." Searching MFT"
    186A0 0 DO
        I MFT-READ 0= IF
            MFT-BUF @ FILE-SIG = IF
                MFT-BUF 16 + W@
                1 AND IF
                    MFT-FILENAME
                    DUP IF
                        TGT-A @
                        TGT-L @
                        NAME= IF
                            CR
                            ." Found rec "
                            I DECIMAL .
                            HEX CR
                            I -1
                            UNLOOP EXIT
                        THEN
                    ELSE
                        2DROP
                    THEN
                THEN
            THEN
        THEN
        I DOT-EVERY MOD
        0= IF
            2E EMIT
        THEN
    LOOP
    CR ." Not found" CR
    0
;

\ ============================================
\ Data run parsing
\ ============================================

: LE-U@ ( addr n -- value )
    0 SWAP
    0 DO
        OVER I + C@
        I 3 LSHIFT LSHIFT
        OR
    LOOP
    NIP
;

: LE-S@ ( addr n -- value )
    DUP >R
    LE-U@
    R> 3 LSHIFT
    2DUP
    1- 1 SWAP LSHIFT
    AND IF
        1 SWAP LSHIFT -
    ELSE
        DROP
    THEN
;

: MFT-DATA-RUNS ( -- )
    0 RUN-LBA !
    0 RUN-SECS !
    0 RUN-PREV !
    ATTR-DATA MFT-ATTR
    DUP 0= IF
        ." No DATA attr" CR
        EXIT
    THEN
    DUP 8 + C@ 0= IF
        DROP
        ." Resident data" CR
        EXIT
    THEN
    \ Data runs at attr + W@(attr+0x20)
    DUP 20 + W@ +
    \ Parse first run
    DUP C@
    DUP 0= IF
        2DROP ." No runs" CR
        EXIT
    THEN
    DUP F AND
    SWAP 4 RSHIFT
    \ ( runs-addr len-sz off-sz )
    >R >R
    1+
    \ Read run length (clusters)
    DUP R@ LE-U@
    SEC/CLUS @ *
    RUN-SECS !
    R> +
    \ Read run offset (signed clusters)
    DUP R> LE-S@
    RUN-PREV !
    DROP
    \ Absolute LBA
    RUN-PREV @
    SEC/CLUS @ *
    PART-LBA @ +
    RUN-LBA !
    ." Data: LBA "
    RUN-LBA @ .H8
    ."  + "
    RUN-SECS @
    DECIMAL . HEX
    ." sectors" CR
;

\ ============================================
\ NTFS-INIT: GPT scan + partition setup
\ ============================================

\ Collect partition start LBAs from one
\ sector of GPT entries (4 per sector)
: COLLECT-ENTRIES ( sector-lba -- )
    1 AHCI-READ IF EXIT THEN
    4 0 DO
        SEC-BUF I 80 * +
        DUP @ OVER 4 + @ OR IF
            20 + @
            GPT-N @ 4 *
            GPT-LBAS + !
            1 GPT-N +!
        ELSE
            DROP
        THEN
    LOOP
;

: SCAN-GPT ( -- flag )
    0 GPT-N !
    2 COLLECT-ENTRIES
    3 COLLECT-ENTRIES
    GPT-N @ 0= IF
        0 EXIT
    THEN
    GPT-N @ 0 DO
        I 4 * GPT-LBAS + @
        DUP PART-LBA !
        1 AHCI-READ 0= IF
            SEC-BUF 3 + @
            NTFS-SIG = IF
                SEC-BUF D + C@
                SEC/CLUS !
                SEC-BUF 30 + @
                SEC/CLUS @ *
                PART-LBA @ +
                MFT-BASE !
                -1
                UNLOOP EXIT
            THEN
        THEN
    LOOP
    0
;

: NTFS-INIT ( -- )
    AH-FOUND @ 0= IF
        ." AHCI not init" CR EXIT
    THEN
    1 1 AHCI-READ IF
        ." GPT err" CR EXIT
    THEN
    SEC-BUF @ 20494645 <> IF
        ." No GPT" CR EXIT
    THEN
    SCAN-GPT 0= IF
        ." No NTFS found" CR EXIT
    THEN
    ." NTFS at LBA "
    PART-LBA @ .H8 CR
    ." MFT at LBA "
    MFT-BASE @ .H8 CR
    SEC/CLUS @
    DECIMAL . HEX
    ." sect/clust" CR
;

\ ============================================
\ High-level file operations
\ ============================================

: FILE-DUMP ( addr len -- )
    MFT-FIND 0= IF EXIT THEN
    FOUND-REC !
    FOUND-REC @ MFT-READ IF
        ." Re-read err" CR EXIT
    THEN
    MFT-DATA-RUNS
    RUN-LBA @ 0= IF EXIT THEN
    RUN-LBA @ 1 AHCI-READ IF
        ." Read err" CR EXIT
    THEN
    100 0 DO
        SEC-BUF I + C@ .H2 SPACE
        I F AND F = IF CR THEN
    LOOP
;

: FILE-READ ( addr len -- flag )
    MFT-FIND 0= IF 1 EXIT THEN
    FOUND-REC !
    FOUND-REC @ MFT-READ IF
        1 EXIT
    THEN
    MFT-DATA-RUNS
    RUN-LBA @ 0= IF 1 EXIT THEN
    RUN-SECS @
    DUP 8 > IF DROP 8 THEN
    RUN-LBA @ SWAP
    AHCI-READ
;

ONLY FORTH DEFINITIONS
DECIMAL
