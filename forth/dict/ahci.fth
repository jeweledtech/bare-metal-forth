\ ============================================
\ CATALOG: AHCI
\ CATEGORY: storage
\ PLATFORM: x86
\ SOURCE: hand-written
\ PORTS: MMIO via PCI BAR5
\ REQUIRES: PCI-ENUM HARDWARE
\ CONFIDENCE: medium
\ ============================================
\
\ AHCI SATA disk driver.
\ Reads raw sectors via DMA.
\
\ Usage:
\   USING AHCI
\   AHCI-INIT
\   0 SECTOR.
\   MBR.
\   GPT.
\   NTFS-FIND
\   12345 NTFS-DUMP
\
\ ============================================

VOCABULARY AHCI
AHCI DEFINITIONS
ALSO PCI-ENUM
ALSO HARDWARE
HEX

\ ---- AHCI register offsets ----
4 CONSTANT GHC-CTL
C CONSTANT GHC-PI
0 CONSTANT PxCLB
8 CONSTANT PxFB
10 CONSTANT PxIS
18 CONSTANT PxCMD
20 CONSTANT PxTFD
28 CONSTANT PxSSTS
38 CONSTANT PxCI

\ ---- State ----
VARIABLE AH-BAR
VARIABLE AH-PORT
VARIABLE AH-FOUND
VARIABLE RD-LBA
VARIABLE RD-CNT
VARIABLE MBR-P1
VARIABLE MBR-P2
VARIABLE MBR-P3
VARIABLE MBR-P4

\ ---- DMA buffers ----
1000 PHYS-ALLOC CONSTANT CL-BUF
1000 PHYS-ALLOC CONSTANT FIS-BUF
1000 PHYS-ALLOC CONSTANT CT-BUF
1000 PHYS-ALLOC CONSTANT SEC-BUF

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
: AH@ ( off -- val )
    AH-BAR @ + @
;
: AH! ( val off -- )
    AH-BAR @ + !
;
: P@ ( off -- val )
    AH-PORT @ + AH-BAR @ + @
;
: P! ( val off -- )
    AH-PORT @ + AH-BAR @ + !
;

\ ---- PCI discovery ----
\ Try Intel 9D03 (HP hardware)
\ then 2922 (QEMU Q35)
: FIND-AHCI ( -- flag )
    8086 9D03 PCI-FIND IF
        PCI-F ! PCI-D ! PCI-B !
        -1 EXIT
    THEN
    8086 2922 PCI-FIND IF
        PCI-F ! PCI-D ! PCI-B !
        -1 EXIT
    THEN
    0
;

\ ---- Find port with drive ----
\ Scans PI bitmask, checks PxSSTS
: FIND-PORT ( -- port# | -1 )
    GHC-PI AH@
    20 0 DO
        DUP 1 I LSHIFT AND IF
            I 80 * 100 + AH-PORT !
            PxSSTS P@ F AND 3 = IF
                DROP I UNLOOP EXIT
            THEN
        THEN
    LOOP
    DROP -1
;

\ ---- Port lifecycle ----
: PORT-STOP ( -- )
    \ Clear ST (bit 0), wait CR clear
    PxCMD P@
    FFFFFFFE AND PxCMD P!
    100 0 DO
        PxCMD P@ 8000 AND 0= IF
            LEAVE
        THEN
        1 MS-DELAY
    LOOP
    \ Clear FRE (bit 4), wait FR clear
    PxCMD P@
    FFFFFFEF AND PxCMD P!
    100 0 DO
        PxCMD P@ 4000 AND 0= IF
            UNLOOP EXIT
        THEN
        1 MS-DELAY
    LOOP
;

: PORT-START ( -- )
    \ Clear interrupts
    FFFFFFFF PxIS P!
    \ Set command list base
    CL-BUF PxCLB P!
    0 4 AH-PORT @ + AH-BAR @ + !
    \ Set FIS base
    FIS-BUF PxFB P!
    0 C AH-PORT @ + AH-BAR @ + !
    \ Enable FRE then ST
    PxCMD P@ 10 OR PxCMD P!
    PxCMD P@ 1 OR PxCMD P!
;

\ ---- Command engine ----
: WAIT-READY ( -- flag )
    100 0 DO
        PxTFD P@ 89 AND 0= IF
            -1 UNLOOP EXIT
        THEN
        1 MS-DELAY
    LOOP
    0
;

: BUILD-CMD ( -- )
    CL-BUF 20 0 FILL
    10005 CL-BUF !
    CT-BUF CL-BUF 8 + !
;

: SET-FIS ( -- )
    CT-BUF 100 0 FILL
    258027 CT-BUF !
    RD-LBA @ DUP
    FFFFFF AND 40000000 OR
    CT-BUF 4 + !
    18 RSHIFT CT-BUF 8 + C!
    RD-CNT @ CT-BUF C + W!
;

: SET-PRD ( -- )
    SEC-BUF CT-BUF 80 + !
    0 CT-BUF 84 + !
    0 CT-BUF 88 + !
    RD-CNT @ 200 * 1-
    CT-BUF 8C + !
;

: ISSUE-CMD ( -- )
    FFFFFFFF PxIS P!
    1 PxCI P!
    200 0 DO
        PxCI P@ 1 AND 0= IF
            UNLOOP EXIT
        THEN
        1 MS-DELAY
    LOOP
    ." CMD timeout" CR
;

\ ---- Core read ----
: AHCI-READ ( lba count -- flag )
    RD-CNT ! RD-LBA !
    WAIT-READY 0= IF
        ." not ready" CR 1 EXIT
    THEN
    BUILD-CMD SET-FIS SET-PRD
    ISSUE-CMD
    PxTFD P@ 1 AND
;

\ ---- Diagnostics ----
: AHCI-DIAG ( -- )
    ." CL=" CL-BUF .H8
    ."  CT=" CT-BUF .H8
    ."  SEC=" SEC-BUF .H8 CR
    ." PxCMD=" PxCMD P@ .H8
    ."  TFD=" PxTFD P@ .H8 CR
    ." PxIS=" PxIS P@ .H8
    ."  CI=" PxCI P@ .H8 CR
;

: CMD-DUMP ( -- )
    ." Hdr0=" CL-BUF @ .H8
    ."  CTBA=" CL-BUF 8 + @ .H8
    ."  CTBAU=" CL-BUF C + @ .H8 CR
    ." FIS="
    CT-BUF @ .H8 SPACE
    CT-BUF 4 + @ .H8 SPACE
    CT-BUF 8 + @ .H8 SPACE
    CT-BUF C + @ .H8 CR
    ." DBA=" CT-BUF 80 + @ .H8
    ."  DBAU=" CT-BUF 84 + @ .H8
    ."  DBC=" CT-BUF 8C + @ .H8 CR
    ." PRDBC=" CL-BUF 4 + @ .H8 CR
;

: SECTOR-DBG. ( lba -- )
    1 AHCI-READ IF
        ." Read err" CR
        CMD-DUMP EXIT
    THEN
    CMD-DUMP
    ." Data: "
    10 0 DO
        SEC-BUF I + C@ .H2 SPACE
    LOOP
    ." ..."
    SEC-BUF 1FE + C@ .H2 SPACE
    SEC-BUF 1FF + C@ .H2 CR
;

\ ---- Display words ----
: SECTOR. ( lba -- )
    1 AHCI-READ IF
        ." Read err" CR EXIT
    THEN
    200 0 DO
        SEC-BUF I + C@ .H2 SPACE
        I F AND F = IF CR THEN
    LOOP
;

: MBR. ( -- )
    0 1 AHCI-READ IF
        ." Read err" CR EXIT
    THEN
    ." MBR:  " CR
    4 0 DO
        50 EMIT I 31 + EMIT 3A EMIT SPACE
        SEC-BUF 1BE + I 10 * +
        DUP 4 + C@ .H2 SPACE
        DUP 8 + @ .H8
        2B EMIT
        C + @ .H8 CR
    LOOP
;

: .RAW8 ( -- )
    8 0 DO
        SEC-BUF I + C@ .H2 SPACE
    LOOP
;

: GPT-PARTS ( entry-lba -- )
    1 AHCI-READ DROP
    4 0 DO
        SEC-BUF I 80 * +
        DUP @ OVER 4 + @ OR IF
            50 EMIT I 31 + EMIT 3A EMIT SPACE
            DUP 20 + @ .H8
            2D EMIT
            28 + @ .H8 CR
        ELSE
            DROP
        THEN
    LOOP
;

: FIND-BACKUP ( -- lba -1 | 0 )
    0 1 AHCI-READ IF 0 EXIT THEN
    4 0 DO
        SEC-BUF 1BE + I 10 * +
        DUP 4 + C@ EE = IF
            DUP 8 + @
            OVER C + @ +
            1- SWAP DROP
            -1 UNLOOP EXIT
        THEN
        DROP
    LOOP
    0
;

: GPT. ( -- )
    1 1 AHCI-READ IF
        ." Read err" CR EXIT
    THEN
    ." LBA1: " .RAW8 CR
    SEC-BUF @ 20494645 = IF
        ." GPT:  " CR
        2 GPT-PARTS EXIT
    THEN
    ." No GPT at LBA 1" CR
    FIND-BACKUP IF
        DUP ." Backup at " .H8 CR
        1 AHCI-READ IF
            ." Read err" CR EXIT
        THEN
        SEC-BUF @ 20494645 = IF
            ." Backup GPT:" CR
            SEC-BUF 48 + @ GPT-PARTS
            EXIT
        THEN
        ." No sig at backup" CR
    ELSE
        ." No EE entry" CR
    THEN
;

\ ---- NTFS scanning ----
: NTFS? ( lba -- flag )
    1 AHCI-READ IF 0 EXIT THEN
    SEC-BUF 3 + @ 5346544E <> IF
        0 EXIT
    THEN
    SEC-BUF 1FE + C@ 55 <>
    SEC-BUF 1FF + C@ AA <>
    OR IF 0 EXIT THEN
    -1
;

: TRY-NTFS ( lba -- )
    DUP 0= IF DROP EXIT THEN
    DUP NTFS? IF
        ." NTFS at " .H8 CR
    ELSE
        2E EMIT DROP
    THEN
;

: SAVE-MBR ( -- )
    0 1 AHCI-READ IF
        ." Read err" CR EXIT
    THEN
    SEC-BUF 1C6 + @ MBR-P1 !
    SEC-BUF 1D6 + @ MBR-P2 !
    SEC-BUF 1E6 + @ MBR-P3 !
    SEC-BUF 1F6 + @ MBR-P4 !
;

: NTFS-FIND ( -- )
    SAVE-MBR
    MBR-P1 @ TRY-NTFS
    MBR-P2 @ TRY-NTFS
    MBR-P3 @ TRY-NTFS
    MBR-P4 @ TRY-NTFS
    CR
;

: NTFS-DUMP ( lba -- )
    1 AHCI-READ IF
        ." Read err" CR EXIT
    THEN
    SEC-BUF 3 + @ 5346544E <> IF
        ." Not NTFS" CR EXIT
    THEN
    ." NTFS Boot Sector:" CR
    ." Bytes/sect: "
    SEC-BUF B + C@
    SEC-BUF C + C@ 8 LSHIFT OR
    .H4 CR
    ." Sect/clust: "
    SEC-BUF D + C@ .H2 CR
    ." Total sect: "
    SEC-BUF 2C + @ .H8
    3A EMIT SEC-BUF 28 + @ .H8 CR
    ." MFT cluster: "
    SEC-BUF 34 + @ .H8
    3A EMIT SEC-BUF 30 + @ .H8 CR
    ." MFT offset:  "
    SEC-BUF 30 + @
    SEC-BUF D + C@ *
    .H8 ." sectors from part" CR
;

\ ---- Initialize ----
: AHCI-INIT ( -- )
    0 AH-FOUND !
    FIND-AHCI 0= IF
        ." No AHCI" CR EXIT
    THEN
    PCI-B @ PCI-D @ PCI-F @
    PCI-ENABLE
    PCI-B @ PCI-D @ PCI-F @
    5 PCI-BAR@
    AH-BAR !
    \ Enable AHCI mode
    GHC-CTL AH@
    80000000 OR GHC-CTL AH!
    ." AHCI at " AH-BAR @ .H8 CR
    \ Find port with drive
    FIND-PORT
    DUP -1 = IF
        DROP ." No disk" CR EXIT
    THEN
    ." Drive on port "
    DECIMAL . HEX CR
    PORT-STOP
    PORT-START
    -1 AH-FOUND !
    ." AHCI ok" CR
;

\ ============================================
\ AHCI-BLOCK: redirect BLOCK through AHCI
\ ============================================
\ On HP hardware, kernel BLOCK uses ATA PIO
\ which hangs (no legacy ATA ports). When AHCI
\ is loaded and in search order, these words
\ shadow the kernel versions.
\
\ AHCI-READ reads into SEC-BUF (4KB).
\ BLOCK = 1KB = 2 sectors at LBA = blk# * 2.
\ Read-only: SAVE-BUFFERS prints warning.

: AHCI-BLOCK ( n -- addr )
    DUP + 2 AHCI-READ DROP
    SEC-BUF
;

: BLOCK ( n -- addr )
    AH-FOUND @ IF
        AHCI-BLOCK
    ELSE
        BLOCK
    THEN
;

: BUFFER ( n -- addr ) BLOCK ;

: SAVE-BUFFERS ( -- )
    AH-FOUND @ IF
        ." AHCI read-only" CR
    ELSE
        SAVE-BUFFERS
    THEN
;

ONLY FORTH DEFINITIONS
DECIMAL
