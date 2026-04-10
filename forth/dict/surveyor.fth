\ ============================================
\ CATALOG: SURVEYOR
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ REQUIRES: AHCI NTFS FAT32 HARDWARE
\ CONFIDENCE: medium
\ ============================================
\
\ Full-disk binary survey.
\ Scans all GPT partitions, catalogs every
\ binary by extension, classifies PE/ELF
\ headers, and prints a hardware driver
\ report. Output streams to network console.
\
\ Usage:
\   USING SURVEYOR
\   DISK-SURVEY
\   DRIVER-REPORT
\
\ ============================================

VOCABULARY SURVEYOR
SURVEYOR DEFINITIONS
ALSO NTFS
ALSO FAT32
ALSO AHCI
ALSO HARDWARE
HEX

\ ============================================
\ Constants
\ ============================================

\ GPT partition type GUIDs (first 4 bytes)
C12A7328 CONSTANT GUID-EFI
EBD0A0A2 CONSTANT GUID-MSDATA
DE94BBA4 CONSTANT GUID-RECOV
0FC63DAF CONSTANT GUID-LINUX
0657FD6D CONSTANT GUID-SWAP

\ Binary signatures
5A4D CONSTANT MZ-SIG
\ PE\0\0 as little-endian dword
4550 CONSTANT PE-DWORD

\ Partition type codes
0 CONSTANT PT-UNK
1 CONSTANT PT-NTFS
2 CONSTANT PT-FAT32
3 CONSTANT PT-RECOV
4 CONSTANT PT-LINUX

\ PE machine types
14C CONSTANT PE-I386
8664 CONSTANT PE-AMD64

\ PE subsystem codes
1 CONSTANT SUB-NATIVE
2 CONSTANT SUB-GUI
3 CONSTANT SUB-CONSOLE

\ MFT progress interval
3E8 CONSTANT DOT-K

\ ============================================
\ Partition table (8 entries x 12 bytes)
\ +0: start LBA (4 bytes)
\ +4: GUID first 4 bytes (4 bytes)
\ +8: type code (1 byte)
\ +9: reserved (3 bytes)
\ ============================================

CREATE PART-TBL 60 ALLOT
VARIABLE PART-N

\ Counters for extension survey
VARIABLE SV-NSYS
VARIABLE SV-NDLL
VARIABLE SV-NEXE
VARIABLE SV-NEFI
VARIABLE SV-NCOM
VARIABLE SV-NTOT

\ ============================================
\ Extension matching helpers
\ ============================================

\ Extension strings (stored as counted data)
CREATE EXT-SYS 4 C, 2E C, 53 C, 59 C, 53 C,
CREATE EXT-DLL 4 C, 2E C, 44 C, 4C C, 4C C,
CREATE EXT-EXE 4 C, 2E C, 45 C, 58 C, 45 C,
CREATE EXT-EFI 4 C, 2E C, 45 C, 46 C, 49 C,
CREATE EXT-COM 4 C, 2E C, 43 C, 4F C, 4D C,

\ Variables for extension comparison
VARIABLE EM-NA
VARIABLE EM-NL
VARIABLE EM-EA
VARIABLE EM-EL

\ Check if name ends with extension
\ Extension stored as counted string
: EXT-MATCH? ( na nl ext -- flag )
    DUP C@ EM-EL !
    1+ EM-EA !
    EM-NL ! EM-NA !
    EM-NL @ EM-EL @ < IF
        0 EXIT
    THEN
    \ Compare suffix
    EM-NA @
    EM-NL @ + EM-EL @ -
    EM-EL @
    EM-EA @ EM-EL @
    NAME=
;

\ Check FAT32 8.3 extension (bytes 8-10)
\ ext3 is 3-char uppercase extension
CREATE F3-BUF 3 ALLOT
VARIABLE F3-OK

: FAT-EXT? ( entry ext3-addr -- flag )
    F3-BUF 3 CMOVE
    0 F3-OK !
    DUP 8 + C@ F3-BUF C@ = IF
        DUP 9 + C@ F3-BUF 1+ C@ = IF
            A + C@ F3-BUF 2 + C@ = IF
                -1 F3-OK !
            THEN
        ELSE DROP THEN
    ELSE DROP THEN
    F3-OK @
;

\ 3-char FAT32 extensions (uppercase)
CREATE F3-SYS 53 C, 59 C, 53 C,
CREATE F3-DLL 44 C, 4C C, 4C C,
CREATE F3-EXE 45 C, 58 C, 45 C,
CREATE F3-EFI 45 C, 46 C, 49 C,
CREATE F3-COM 43 C, 4F C, 4D C,

\ ============================================
\ Partition table access
\ ============================================

: PART-ENT ( idx -- addr )
    C * PART-TBL +
;

: .PTYPE ( type -- )
    DUP PT-NTFS = IF
        DROP ." NTFS" EXIT
    THEN
    DUP PT-FAT32 = IF
        DROP ." FAT32" EXIT
    THEN
    DUP PT-RECOV = IF
        DROP ." Recovery" EXIT
    THEN
    DUP PT-LINUX = IF
        DROP ." Linux" EXIT
    THEN
    DROP ." Unknown"
;

\ ============================================
\ Unified GPT scanner
\ ============================================

\ Classify GUID first-4-bytes to type code
: GUID>TYPE ( guid4 -- type )
    DUP GUID-EFI = IF
        DROP PT-FAT32 EXIT
    THEN
    DUP GUID-MSDATA = IF
        DROP PT-UNK EXIT
    THEN
    DUP GUID-RECOV = IF
        DROP PT-RECOV EXIT
    THEN
    DUP GUID-LINUX = IF
        DROP PT-LINUX EXIT
    THEN
    DUP GUID-SWAP = IF
        DROP PT-LINUX EXIT
    THEN
    DROP PT-UNK
;

\ Read one GPT sector, collect entries
: SCAN-GPT-SEC ( sector-lba -- )
    1 AHCI-READ IF EXIT THEN
    4 0 DO
        SEC-BUF I 80 * +
        DUP @ OVER 4 + @ OR IF
            \ Non-empty entry
            PART-N @ 8 < IF
                DUP 20 + @
                PART-N @ PART-ENT !
                DUP @
                DUP PART-N @ PART-ENT
                4 + !
                GUID>TYPE
                PART-N @ PART-ENT
                8 + C!
                1 PART-N +!
            THEN
        THEN
        DROP
    LOOP
;

\ Probe GUID-MSDATA partitions for NTFS
: PROBE-PARTS ( -- )
    PART-N @ 0 DO
        I PART-ENT 8 + C@ PT-UNK = IF
            I PART-ENT 4 + @
            GUID-MSDATA = IF
                I PART-ENT @
                1 AHCI-READ 0= IF
                    SEC-BUF 3 + @
                    5346544E = IF
                        PT-NTFS
                        I PART-ENT
                        8 + C!
                    THEN
                THEN
            THEN
        THEN
    LOOP
;

\ Main partition scanner
: PARTITION-MAP ( -- )
    AH-FOUND @ 0= IF
        ." AHCI not init" CR EXIT
    THEN
    0 PART-N !
    PART-TBL 60 0 FILL
    1 1 AHCI-READ IF
        ." GPT read err" CR EXIT
    THEN
    SEC-BUF @ 20494645 <> IF
        ." No GPT" CR EXIT
    THEN
    2 SCAN-GPT-SEC
    3 SCAN-GPT-SEC
    4 SCAN-GPT-SEC
    5 SCAN-GPT-SEC
    PROBE-PARTS
    ." === Partitions ===" CR
    PART-N @ 0 DO
        ." P"
        I 1+ DECIMAL . HEX
        ." : "
        I PART-ENT 8 + C@ .PTYPE
        ."  LBA "
        I PART-ENT @ .H8
        CR
    LOOP
    PART-N @ DECIMAL . HEX
    ." partitions found" CR
;

\ ============================================
\ NTFS-PROBE: init NTFS at specific LBA
\ ============================================

: NTFS-PROBE ( lba -- flag )
    DUP PART-LBA !
    1 AHCI-READ IF
        0 EXIT
    THEN
    SEC-BUF 3 + @ 5346544E <> IF
        0 EXIT
    THEN
    SEC-BUF D + C@ SEC/CLUS !
    SEC-BUF 30 + @
    SEC/CLUS @ *
    PART-LBA @ +
    MFT-BASE !
    SEC/CLUS @ 200 *
    400 /
    RECS/CLUS !
    MFT-READ0 IF 0 EXIT THEN
    MFT-BUF @ FILE-SIG <> IF
        0 EXIT
    THEN
    BUILD-MFT-MAP
    ." NTFS at "
    PART-LBA @ .H8
    ."  MFT "
    MFT-NRUNS @
    DECIMAL . HEX
    ." runs, "
    MFT-COUNT
    DECIMAL . HEX
    ." records" CR
    -1
;

\ ============================================
\ NTFS-SURVEY: single-pass MFT scan
\ ============================================

VARIABLE SV-REC

: TALLY-EXT ( na nl -- matched? )
    2DUP EXT-SYS EXT-MATCH? IF
        1 SV-NSYS +!
        2DROP -1 EXIT
    THEN
    2DUP EXT-DLL EXT-MATCH? IF
        1 SV-NDLL +!
        2DROP -1 EXIT
    THEN
    2DUP EXT-EXE EXT-MATCH? IF
        1 SV-NEXE +!
        2DROP -1 EXIT
    THEN
    2DUP EXT-EFI EXT-MATCH? IF
        1 SV-NEFI +!
        2DROP -1 EXIT
    THEN
    2DUP EXT-COM EXT-MATCH? IF
        1 SV-NCOM +!
        2DROP -1 EXIT
    THEN
    2DROP 0
;

\ Show first N filenames for diagnostics
VARIABLE DBG-SHOW
A CONSTANT DBG-MAX

: NTFS-SURVEY ( -- )
    ." Scanning MFT..." CR
    0 DBG-SHOW !
    MFT-COUNT SV-REC !
    ." Records: "
    SV-REC @ DECIMAL . HEX CR
    SV-REC @ 0 DO
        I MFT-READ 0= IF
            MFT-BUF @ FILE-SIG = IF
                MFT-BUF 16 + W@
                1 AND IF
                    MFT-FILENAME
                    DUP IF
                        \ Show first 10 names
                        DBG-SHOW @
                        DBG-MAX < IF
                            ." ["
                            I DECIMAL . HEX
                            ." ] "
                            2DUP TYPE CR
                            1 DBG-SHOW +!
                        THEN
                        1 SV-NTOT +!
                        2DUP TALLY-EXT
                        IF
                            TYPE CR
                        ELSE
                            2DROP
                        THEN
                    ELSE
                        2DROP
                    THEN
                THEN
            THEN
        THEN
        I DOT-K MOD
        0= IF 2E EMIT THEN
    LOOP
    CR
    ." NTFS: "
    SV-NSYS @ DECIMAL . HEX
    ." .sys, "
    SV-NDLL @ DECIMAL . HEX
    ." .dll, "
    SV-NEXE @ DECIMAL . HEX
    ." .exe, "
    SV-NCOM @ DECIMAL . HEX
    ." .com" CR
;

\ ============================================
\ FAT32-PROBE: init FAT32 at specific LBA
\ ============================================

: FAT32-PROBE ( lba -- flag )
    EFI-LBA !
    EFI-LBA @ 1 AHCI-READ IF
        0 EXIT
    THEN
    SEC-BUF 24 + @ 0= IF
        0 EXIT
    THEN
    PARSE-BPB
    ." FAT32 at "
    EFI-LBA @ .H8
    ."  root cl "
    ROOT-CLUST @
    DECIMAL . HEX CR
    -1
;

\ ============================================
\ FAT32-SURVEY: walk directories
\ ============================================

: FAT-TALLY ( entry -- )
    DUP F3-SYS FAT-EXT? IF
        1 SV-NSYS +! DROP EXIT
    THEN
    DUP F3-DLL FAT-EXT? IF
        1 SV-NDLL +! DROP EXIT
    THEN
    DUP F3-EXE FAT-EXT? IF
        1 SV-NEXE +! DROP EXIT
    THEN
    DUP F3-EFI FAT-EXT? IF
        1 SV-NEFI +! DROP EXIT
    THEN
    DUP F3-COM FAT-EXT? IF
        1 SV-NCOM +! DROP EXIT
    THEN
    DROP
;

\ Safe EMIT: skip non-printable chars
: ?EMIT ( c -- )
    DUP 20 > OVER 7F < AND IF
        EMIT
    ELSE
        DROP
    THEN
;

\ Print 8.3 name filtering garbage
: .FNAME-SAFE ( entry -- )
    8 0 DO
        DUP I + C@ ?EMIT
    LOOP
    DUP 8 + C@ 20 <> IF
        DUP 8 + C@ 7F < IF
            2E EMIT
            3 0 DO
                DUP 8 I + + C@ ?EMIT
            LOOP
        THEN
    THEN
    DROP
;

\ Flat directory scan (no recursion)
\ Walks one cluster chain, lists files
VARIABLE SD-END

: FLAT-DIR ( cluster -- )
    0 SD-END !
    BEGIN
        DUP READ-CLUST IF
            DROP EXIT
        THEN
        DIR-ENTRIES 0 DO
            DIR-BUF I DIR-ESIZ * +
            DUP C@ 0= IF
                DROP -1 SD-END !
                LEAVE
            THEN
            DUP C@ E5 = IF
                DROP
            ELSE
            DUP B + C@ 0F = IF
                DROP
            ELSE
            DUP B + C@ 8 = IF
                DROP
            ELSE
                DUP B + C@ 10 AND IF
                    \ Subdirectory: print name
                    DUP .FNAME-SAFE
                    ."  <DIR>" CR
                    DROP
                ELSE
                    DUP FAT-TALLY
                    1 SV-NTOT +!
                    DUP .FNAME-SAFE CR
                    DROP
                THEN
            THEN THEN THEN
        LOOP
        SD-END @ IF DROP EXIT THEN
        FAT-NEXT
        DUP FAT-END? IF
            DROP EXIT
        THEN
    AGAIN
;

\ Variables for two-level walk
VARIABLE F-SUB
CREATE F-SUBS 20 ALLOT
VARIABLE F-NSUB

\ Collect subdir clusters from root
: COLLECT-SUBS ( cluster -- )
    0 F-NSUB !
    0 SD-END !
    BEGIN
        DUP READ-CLUST IF
            DROP EXIT
        THEN
        DIR-ENTRIES 0 DO
            DIR-BUF I DIR-ESIZ * +
            DUP C@ 0= IF
                DROP -1 SD-END !
                LEAVE
            THEN
            DUP C@ E5 = IF DROP ELSE
            DUP B + C@ 0F = IF DROP ELSE
            DUP B + C@ 8 = IF DROP ELSE
                DUP B + C@ 10 AND IF
                    DUP DIR-CLUST
                    DUP 2 >= IF
                        F-NSUB @ 8 < IF
                            F-NSUB @
                            4 * F-SUBS + !
                            1 F-NSUB +!
                        ELSE
                            DROP
                        THEN
                    ELSE
                        DROP
                    THEN
                THEN
                DROP
            THEN THEN THEN
        LOOP
        SD-END @ IF DROP EXIT THEN
        FAT-NEXT
        DUP FAT-END? IF
            DROP EXIT
        THEN
    AGAIN
;

: FAT32-SURVEY ( -- )
    ." Scanning FAT32..." CR
    ROOT-CLUST @ CUR-DIR !
    ." Root:" CR
    CUR-DIR @ FLAT-DIR
    \ Collect subdirectory clusters
    CUR-DIR @ COLLECT-SUBS
    \ Walk each subdir (1 level only)
    F-NSUB @ 0 DO
        I 4 * F-SUBS + @ F-SUB !
        ." Subdir cl "
        F-SUB @ DECIMAL . HEX
        3A EMIT CR
        F-SUB @ FLAT-DIR
    LOOP
    ." FAT32: "
    SV-NEFI @ DECIMAL . HEX
    ." .efi" CR
;

\ ============================================
\ PE header parser
\ ============================================

VARIABLE PE-OFF

: PE-CHECK ( -- )
    SEC-BUF W@ MZ-SIG <> IF
        EXIT
    THEN
    SEC-BUF 3C + @ PE-OFF !
    PE-OFF @ 0< IF EXIT THEN
    PE-OFF @ 1C0 > IF EXIT THEN
    SEC-BUF PE-OFF @ + W@
    PE-DWORD <> IF EXIT THEN
    ." PE "
    \ Machine type at PE+4
    SEC-BUF PE-OFF @ + 4 + W@
    DUP PE-AMD64 = IF
        DROP ." AMD64"
    ELSE
        PE-I386 = IF
            ." x86"
        ELSE
            ." unk-arch"
        THEN
    THEN
    SPACE
    \ Subsystem at PE+5C
    SEC-BUF PE-OFF @ + 5C + W@
    DUP SUB-NATIVE = IF
        DROP ." driver"
    ELSE
    DUP SUB-GUI = IF
        DROP ." GUI"
    ELSE
        SUB-CONSOLE = IF
            ." console"
        ELSE
            ." sub?"
        THEN
    THEN THEN
;

\ ============================================
\ ELF header recognizer
\ ============================================

: ELF-CHECK ( -- )
    SEC-BUF C@ 7F <> IF EXIT THEN
    SEC-BUF 1+ C@ 45 <> IF EXIT THEN
    SEC-BUF 2 + C@ 4C <> IF EXIT THEN
    SEC-BUF 3 + C@ 46 <> IF EXIT THEN
    ." ELF "
    SEC-BUF 4 + C@
    DUP 1 = IF
        DROP ." 32-bit"
    ELSE
        2 = IF
            ." 64-bit"
        ELSE
            ." unk-class"
        THEN
    THEN
    SPACE
    SEC-BUF 12 + W@
    DUP 3 = IF
        DROP ." x86"
    ELSE
        3E = IF
            ." x86-64"
        ELSE
            ." unk-mach"
        THEN
    THEN
;

\ Dispatch: classify binary from SEC-BUF
: CLASSIFY ( -- )
    SEC-BUF W@ MZ-SIG = IF
        PE-CHECK EXIT
    THEN
    SEC-BUF C@ 7F = IF
        ELF-CHECK EXIT
    THEN
    ." unknown"
;

\ ============================================
\ MFT-DATA-Q: quiet data run extraction
\ Sets RUN-LBA and RUN-SECS without printing
\ ============================================

: MFT-DATA-Q ( -- )
    0 RUN-LBA !
    0 RUN-SECS !
    0 RUN-PREV !
    ATTR-DATA MFT-ATTR
    DUP 0= IF DROP EXIT THEN
    DUP 8 + C@ 0= IF
        DROP EXIT
    THEN
    DUP 20 + W@ +
    DUP C@
    DUP 0= IF
        2DROP EXIT
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
;

\ ============================================
\ DISK-SURVEY: main entry point
\ ============================================

: SURVEY-SUMMARY ( -- )
    ." === Survey Summary ===" CR
    ." .sys: "
    SV-NSYS @ DECIMAL . HEX CR
    ." .dll: "
    SV-NDLL @ DECIMAL . HEX CR
    ." .exe: "
    SV-NEXE @ DECIMAL . HEX CR
    ." .efi: "
    SV-NEFI @ DECIMAL . HEX CR
    ." .com: "
    SV-NCOM @ DECIMAL . HEX CR
    ." Total files: "
    SV-NTOT @ DECIMAL . HEX CR
;

: DISK-SURVEY ( -- )
    ." === ForthOS Disk Survey ===" CR
    0 SV-NSYS !
    0 SV-NDLL !
    0 SV-NEXE !
    0 SV-NEFI !
    0 SV-NCOM !
    0 SV-NTOT !
    PARTITION-MAP
    PART-N @ 0= IF
        ." No partitions" CR EXIT
    THEN
    PART-N @ 0 DO
        I PART-ENT 8 + C@
        DUP PT-NTFS = IF
            DROP
            ." --- NTFS P"
            I 1+ DECIMAL . HEX
            ." ---" CR
            I PART-ENT @
            NTFS-PROBE IF
                NTFS-SURVEY
            ELSE
                ." NTFS init fail" CR
            THEN
        ELSE
        DUP PT-FAT32 = IF
            DROP
            ." --- FAT32 P"
            I 1+ DECIMAL . HEX
            ." ---" CR
            I PART-ENT @
            FAT32-PROBE IF
                FAT32-SURVEY
            ELSE
                ." FAT32 init fail" CR
            THEN
        ELSE
            DROP
        THEN THEN
    LOOP
    SURVEY-SUMMARY
;

\ ============================================
\ DRIVER-REPORT: .sys PE classification
\ ============================================

VARIABLE DR-CNT

: DRIVER-REPORT ( -- )
    ." === Driver Report ===" CR
    0 DR-CNT !
    MFT-COUNT 0 DO
        I MFT-READ 0= IF
            MFT-BUF @ FILE-SIG = IF
                MFT-BUF 16 + W@
                1 AND IF
                    MFT-FILENAME
                    DUP IF
                        2DUP EXT-SYS
                        EXT-MATCH? IF
                            TYPE SPACE
                            MFT-DATA-Q
                            RUN-LBA @
                            0<> IF
                                RUN-LBA @
                                1 AHCI-READ
                                0= IF
                                    CLASSIFY
                                THEN
                            THEN
                            CR
                            1 DR-CNT +!
                        ELSE
                            2DROP
                        THEN
                    ELSE
                        2DROP
                    THEN
                THEN
            THEN
        THEN
        I DOT-K MOD
        0= IF 2E EMIT THEN
    LOOP
    CR
    DR-CNT @
    DECIMAL . HEX
    ." binaries classified" CR
;

ONLY FORTH DEFINITIONS
DECIMAL
