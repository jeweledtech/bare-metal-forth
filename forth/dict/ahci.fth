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
    CT-BUF 80 0 FILL
    258027 CT-BUF !
    RD-LBA @ DUP
    FFFFFF AND 40000000 OR
    CT-BUF 4 + !
    18 RSHIFT CT-BUF 8 + C!
    RD-CNT @ CT-BUF C + W!
;

: SET-PRD ( -- )
    SEC-BUF CT-BUF 80 + !
    RD-CNT @ 200 * 1-
    CT-BUF 8C + !
;

: ISSUE-CMD ( -- )
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
    ." MBR:" CR
    4 0 DO
        ." P" I 31 + EMIT ." : "
        SEC-BUF 1BE + I 10 * +
        DUP 4 + C@ .H2 SPACE
        DUP 8 + @ .H8
        ." +"
        C + @ .H8 CR
    LOOP
;

: GPT. ( -- )
    1 1 AHCI-READ IF
        ." Read err" CR EXIT
    THEN
    SEC-BUF @ 20494645 <> IF
        ." No GPT" CR EXIT
    THEN
    ." GPT:" CR
    2 1 AHCI-READ DROP
    4 0 DO
        SEC-BUF I 80 * +
        DUP @ OVER 4 + @ OR IF
            ." P" I 31 + EMIT ." : "
            DUP 20 + @ .H8
            ." -"
            28 + @ .H8 CR
        ELSE
            DROP
        THEN
    LOOP
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

ONLY FORTH DEFINITIONS
DECIMAL
