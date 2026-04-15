\ ============================================
\ CATALOG: SURVEYOR-DEEP
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ REQUIRES: SURVEYOR CAB-EXTRACT MSI-READER
\ ============================================
\
\ Deep binary survey extension.
\ After DISK-SURVEY finds filesystem files,
\ DEEP-SURVEY re-walks MFT for .cab/.msi/.zip
\ archives and counts binaries inside each.
\
\ Usage:
\   USING SURVEYOR-DEEP
\   DEEP-SURVEY
\
\ ============================================

VOCABULARY SURVEYOR-DEEP
SURVEYOR-DEEP DEFINITIONS
ALSO SURVEYOR
ALSO CAB-EXTRACT
ALSO MSI-READER
ALSO ZIP-READER
ALSO NTFS
ALSO AHCI
ALSO HARDWARE
HEX

\ ========================================
\ Archive counters
\ ========================================

VARIABLE SV-NCAB
VARIABLE SV-NMSI
VARIABLE SV-NZIP
VARIABLE SV-ARCBIN

\ ========================================
\ Extension matching for archives
\ ========================================

\ Counted strings for NTFS names
CREATE DA-CAB 3 C, 63 C, 61 C, 62 C,
CREATE DA-MSI 3 C, 6D C, 73 C, 69 C,
CREATE DA-ZIP 3 C, 7A C, 69 C, 70 C,

\ NTFS filename extension check
\ Reuse the surveyor pattern
VARIABLE DA-NA
VARIABLE DA-NL

: DA-EXT? ( na nl ext -- flag )
  OVER 4 < IF
    DROP DROP DROP 0 EXIT
  THEN
  DUP C@
  ROT ROT
  OVER + OVER C@ - 1-
  SWAP C@ 1+
  0 DO
    DUP I + C@
    DUP 41 >= IF
      DUP 5A <= IF 20 + THEN
    THEN
    OVER I + 1+ C@
    <> IF
      DROP DROP 0 UNLOOP EXIT
    THEN
  LOOP
  DROP DROP -1 ;

\ Check if name is .cab, .msi, or .zip
\ Returns 1=cab, 2=msi, 3=zip, 0=none
: DA-MATCH ( na nl -- type )
  2DUP DA-CAB DA-EXT? IF
    DROP DROP 1 EXIT
  THEN
  2DUP DA-MSI DA-EXT? IF
    DROP DROP 2 EXIT
  THEN
  2DUP DA-ZIP DA-EXT? IF
    DROP DROP 3 EXIT
  THEN
  DROP DROP 0 ;

\ ========================================
\ Archive buffer
\ ========================================

\ Buffer for reading archive headers
\ 16 sectors = 8KB, enough for headers
VARIABLE DA-ABUF

: DA-ALLOC ( -- )
  2000 PHYS-ALLOC DUP 0= IF
    ." Deep: no memory" CR EXIT
  THEN
  DA-ABUF ! ;

: DA-FREE ( -- )
  0 DA-ABUF ! ;

\ ========================================
\ Read first N sectors of a file
\ ========================================

\ Read sectors from data run into DA-ABUF
\ Uses AHCI-READ (reads into SEC-BUF)
\ then copies to our buffer
VARIABLE DA-RDOFF

: DA-READ ( lba nsec -- flag )
  DA-ABUF @ 0= IF
    DROP DROP -1 EXIT
  THEN
  OVER 0= IF
    DROP DROP -1 EXIT
  THEN
  DUP 10 > IF DROP 10 THEN
  0 DA-RDOFF !
  0 DO
    DUP I + 1 AHCI-READ IF
      DROP -1 UNLOOP EXIT
    THEN
    SEC-BUF DA-ABUF @ DA-RDOFF @ +
    200 CMOVE
    200 DA-RDOFF +!
  LOOP
  DROP 0 ;

\ ========================================
\ Process one archive file
\ ========================================

VARIABLE DA-TYPE
VARIABLE DA-NSEC

: DA-PROCESS ( type -- )
  DA-TYPE !
  \ Get file data run info
  MFT-DATA-Q
  RUN-LBA @ 0= IF EXIT THEN
  RUN-SECS @ DA-NSEC !
  DA-NSEC @ 0= IF EXIT THEN
  \ Read first 16 sectors (8KB)
  RUN-LBA @ DA-NSEC @
  DUP 10 > IF DROP 10 THEN
  DA-READ IF EXIT THEN
  \ Dispatch by type
  DA-TYPE @ 1 = IF
    DA-ABUF @
    DA-NSEC @ 200 *
    DUP 2000 > IF DROP 2000 THEN
    CAB-COUNT SV-ARCBIN +!
    1 SV-NCAB +!
  THEN
  DA-TYPE @ 2 = IF
    DA-ABUF @
    DA-NSEC @ 200 *
    DUP 2000 > IF DROP 2000 THEN
    MSI-COUNT SV-ARCBIN +!
    1 SV-NMSI +!
  THEN
  DA-TYPE @ 3 = IF
    DA-ABUF @
    DA-NSEC @ 200 *
    DUP 2000 > IF DROP 2000 THEN
    ZIP-COUNT SV-ARCBIN +!
    1 SV-NZIP +!
  THEN ;

\ ========================================
\ MFT walk for archives
\ ========================================

VARIABLE DA-REC
VARIABLE DA-NREC

\ Walk MFT records, find archives
: DEEP-SCAN ( -- )
  MFT-COUNT DA-NREC !
  DA-NREC @ 0= IF EXIT THEN
  DA-ALLOC
  DA-ABUF @ 0= IF EXIT THEN
  DA-NREC @ 0 DO
    I MFT-READ IF ELSE
      MFT-BUF @ 454C4946 = IF
        MFT-FILENAME
        DUP IF
          2DUP DA-MATCH
          DUP IF
            DA-PROCESS
          ELSE DROP THEN
        THEN
        DROP DROP
      THEN
    THEN
  LOOP
  DA-FREE ;

\ ========================================
\ NTFS partition deep scan
\ ========================================

: DEEP-PART ( lba -- )
  NTFS-PROBE IF
    DEEP-SCAN
  ELSE
    ." NTFS init fail" CR
  THEN ;

\ ========================================
\ Reports
\ ========================================

: DEEP-REPORT ( -- )
  ." === Deep Survey ===" CR
  ." CAB archives:  "
  SV-NCAB @ DECIMAL . HEX CR
  ." MSI archives:  "
  SV-NMSI @ DECIMAL . HEX CR
  ." ZIP archives:  "
  SV-NZIP @ DECIMAL . HEX CR
  ." Archived bins: "
  SV-ARCBIN @ DECIMAL . HEX CR
  ." --- Combined ---" CR
  ." Direct bins:   "
  SV-NSYS @ SV-NDLL @ +
  SV-NEXE @ + SV-NEFI @ +
  SV-NCOM @ + SV-NKO @ +
  SV-NSO @ +
  DECIMAL . HEX CR
  ." Archive bins:  "
  SV-ARCBIN @ DECIMAL . HEX CR
  ." Total:         "
  SV-NSYS @ SV-NDLL @ +
  SV-NEXE @ + SV-NEFI @ +
  SV-NCOM @ + SV-NKO @ +
  SV-NSO @ + SV-ARCBIN @ +
  DECIMAL . HEX CR ;

\ ========================================
\ Main entry point
\ ========================================

: DEEP-SURVEY ( -- )
  \ Phase 1: standard survey
  DISK-SURVEY
  \ Phase 2: archive deep scan
  0 SV-NCAB ! 0 SV-NMSI !
  0 SV-NZIP ! 0 SV-ARCBIN !
  ." === Deep Scan ===" CR
  PART-N @ 0 DO
    I PART-ENT 8 + C@ PT-NTFS = IF
      ." --- NTFS P"
      I 1+ DECIMAL . HEX
      ." ---" CR
      I PART-ENT @ DEEP-PART
    THEN
  LOOP
  DEEP-REPORT ;

ONLY FORTH DEFINITIONS
DECIMAL
