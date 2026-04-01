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
\ Handles fragmented MFT via run map.
\
\ Usage:
\   USING NTFS
\   NTFS-INIT
\   0 25 MFT-LIST
\   S" ntoskrnl.exe" MFT-FIND
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
200 CONSTANT SECT-SZ

\ ---- Buffers ----
400 PHYS-ALLOC CONSTANT MFT-BUF
CREATE NAME-BUF 100 ALLOT
CREATE GPT-LBAS 20 ALLOT
\ MFT run map: 32 entries x 8 bytes
\ Each: +0 start-LBA, +4 record-count
CREATE MFT-RUNS 100 ALLOT

\ ---- State ----
VARIABLE PART-LBA
VARIABLE MFT-BASE
VARIABLE SEC/CLUS
VARIABLE RECS/CLUS
VARIABLE NAME-LEN
VARIABLE RUN-LBA
VARIABLE RUN-SECS
VARIABLE RUN-PREV
VARIABLE FOUND-REC
VARIABLE TGT-A
VARIABLE TGT-L
VARIABLE GPT-N
VARIABLE MFT-NRUNS
VARIABLE MFT-RN
VARIABLE PR-PTR
VARIABLE PR-LEN
VARIABLE PR-OFF

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
\ Little-endian multi-byte read
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
\ MFT fixup
\ ============================================

: MFT-FIXUP ( -- flag )
    MFT-BUF 4 + W@
    MFT-BUF + >R
    R@ W@
    MFT-BUF FIXUP-OFF1 + W@
    OVER <> IF
        DROP R> DROP 1 EXIT
    THEN
    R@ 2 + W@
    MFT-BUF FIXUP-OFF1 + W!
    MFT-BUF FIXUP-OFF2 + W@
    OVER <> IF
        DROP R> DROP 1 EXIT
    THEN
    DROP
    R> 4 + W@
    MFT-BUF FIXUP-OFF2 + W!
    0
;

\ ============================================
\ Data run parser (reusable)
\ ============================================

\ Parse one data run from PR-PTR.
\ Advances PR-PTR. Sets PR-LEN, PR-OFF.
\ Returns -1 if run parsed, 0 if end.
: PARSE-RUN ( -- more? )
    PR-PTR @ C@
    DUP 0= IF DROP 0 EXIT THEN
    DUP F AND
    SWAP 4 RSHIFT
    SWAP >R
    PR-PTR @ 1+ R@ LE-U@
    PR-LEN !
    PR-PTR @ 1+ R> +
    DUP >R SWAP
    2DUP LE-S@
    PR-OFF !
    + PR-PTR !
    R> DROP
    -1
;

\ ============================================
\ MFT run map + record LBA lookup
\ ============================================

\ Translate MFT record# to absolute LBA.
\ Uses MFT-RUNS table built by BUILD-MFT-MAP.
: REC-LBA ( record# -- lba | -1 )
    MFT-RN !
    MFT-NRUNS @ 0 DO
        I 8 * MFT-RUNS +
        DUP 4 + @
        MFT-RN @ OVER < IF
            DROP @
            MFT-RN @ DUP + +
            UNLOOP EXIT
        THEN
        MFT-RN @ SWAP -
        MFT-RN !
        DROP
    LOOP
    -1
;

\ ============================================
\ MFT read (uses run map)
\ ============================================

: MFT-READ ( record# -- flag )
    REC-LBA
    DUP -1 = IF DROP 1 EXIT THEN
    2 AHCI-READ IF
        1 EXIT
    THEN
    SEC-BUF MFT-BUF MFT-REC-SZ CMOVE
    MFT-FIXUP
;

\ Bootstrap read: record 0 directly from
\ MFT-BASE (before run map exists).
: MFT-READ0 ( -- flag )
    MFT-BASE @ 2 AHCI-READ IF
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
\ Build MFT run map from $MFT record 0
\ ============================================

\ Must be called with MFT-BUF containing
\ record 0 (the $MFT file itself).
: BUILD-MFT-MAP ( -- )
    0 MFT-NRUNS !
    0 RUN-PREV !
    ATTR-DATA MFT-ATTR
    DUP 0= IF
        ." No $MFT data" CR EXIT
    THEN
    DUP 8 + C@ 0= IF
        DROP ." $MFT resident?" CR EXIT
    THEN
    DUP 20 + W@ + PR-PTR !
    BEGIN
        PARSE-RUN
    WHILE
        PR-OFF @ RUN-PREV +!
        MFT-NRUNS @ 8 *
        MFT-RUNS +
        RUN-PREV @
        SEC/CLUS @ *
        PART-LBA @ +
        OVER !
        PR-LEN @
        RECS/CLUS @ *
        SWAP 4 + !
        1 MFT-NRUNS +!
        MFT-NRUNS @ 20 = IF
            EXIT
        THEN
    REPEAT
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

VARIABLE MFT-TOTAL
3E8 CONSTANT DOT-K

\ Compute total MFT records from run map
: MFT-COUNT ( -- n )
    0
    MFT-NRUNS @ 0 DO
        I 8 * MFT-RUNS + 4 + @
        +
    LOOP
;

: MFT-FIND ( addr len -- rec# -1 | 0 )
    TGT-L ! TGT-A !
    MFT-COUNT MFT-TOTAL !
    ." Searching "
    MFT-TOTAL @
    DECIMAL . HEX
    ." records" CR
    MFT-TOTAL @ 0 DO
        I MFT-READ 0= IF
            MFT-BUF @ FILE-SIG = IF
                MFT-BUF 16 + W@
                1 AND IF
                    MFT-FILENAME
                    DUP IF
                        TGT-A @
                        TGT-L @
                        NAME= IF
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
        I DOT-K MOD
        0= IF
            2E EMIT
        THEN
    LOOP
    CR ." Not found" CR
    0
;

\ ============================================
\ File data run parsing
\ ============================================

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
    DUP 20 + W@ +
    DUP C@
    DUP 0= IF
        2DROP ." No runs" CR
        EXIT
    THEN
    DUP F AND
    SWAP 4 RSHIFT
    >R >R
    1+
    DUP R@ LE-U@
    SEC/CLUS @ *
    RUN-SECS !
    R> +
    DUP R> LE-S@
    RUN-PREV !
    DROP
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
\ NTFS-INIT: GPT + MFT run map
\ ============================================

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
    \ Compute records per cluster
    SEC/CLUS @ SECT-SZ *
    MFT-REC-SZ /
    RECS/CLUS !
    ." NTFS at LBA "
    PART-LBA @ .H8 CR
    ." MFT at LBA "
    MFT-BASE @ .H8 CR
    SEC/CLUS @
    DECIMAL . HEX
    ." sect/clust, "
    RECS/CLUS @
    DECIMAL . HEX
    ." rec/clust" CR
    \ Bootstrap: read MFT record 0
    MFT-READ0 IF
        ." MFT read err" CR EXIT
    THEN
    MFT-BUF @ FILE-SIG <> IF
        ." Bad MFT sig" CR EXIT
    THEN
    \ Build run map from $MFT data runs
    BUILD-MFT-MAP
    ." MFT: "
    MFT-NRUNS @
    DECIMAL . HEX
    ." runs" CR
;

\ ============================================
\ Diagnostics
\ ============================================

: MFT-SHOW ( n -- )
    DUP MFT-READ IF
        DECIMAL . HEX
        ." : read err" CR EXIT
    THEN
    DECIMAL . HEX 3A EMIT SPACE
    MFT-BUF @ FILE-SIG <> IF
        ." (no sig)" CR EXIT
    THEN
    MFT-BUF 16 + W@ 1 AND 0= IF
        ." (free)" CR EXIT
    THEN
    MFT-FILENAME DUP IF
        TYPE
    ELSE
        2DROP ." (no name)"
    THEN
    CR
;

: MFT-LIST ( start count -- )
    OVER + SWAP DO
        I MFT-SHOW
    LOOP
;

: MFT-MAP. ( -- )
    ." MFT runs:" CR
    MFT-NRUNS @ 0 DO
        I 8 * MFT-RUNS +
        ."  LBA "
        DUP @ .H8
        ."  recs "
        4 + @
        DECIMAL . HEX CR
    LOOP
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
