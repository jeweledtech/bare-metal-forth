\ ============================================
\ CATALOG: SURVEYOR-DETAIL
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ REQUIRES: SURVEYOR NTFS HARDWARE
\ ============================================
\
\ Per-extension and per-directory binary
\ count breakdown. Extends DISK-SURVEY with
\ individual counters for all 14 extensions
\ and 6 directory buckets.
\
\ Usage:
\   USING SURVEYOR-DETAIL
\   DISK-SURVEY-DETAIL
\
\ ============================================

VOCABULARY SURVEYOR-DETAIL
SURVEYOR-DETAIL DEFINITIONS
ALSO SURVEYOR
ALSO NTFS
ALSO AHCI
ALSO HARDWARE
HEX

\ ========================================
\ Per-extension counters
\ ========================================

VARIABLE SD-NSYS
VARIABLE SD-NDRV
VARIABLE SD-NDLL
VARIABLE SD-NOCX
VARIABLE SD-NCPL
VARIABLE SD-NAX
VARIABLE SD-NMUI
VARIABLE SD-NEXE
VARIABLE SD-NSCR
VARIABLE SD-NEFI
VARIABLE SD-NCOM
VARIABLE SD-NKO
VARIABLE SD-NSO
VARIABLE SD-NOTHER

\ ========================================
\ Per-directory counters
\ ========================================

VARIABLE SD-SYSTEM32
VARIABLE SD-WINSXS
VARIABLE SD-DRIVERS
VARIABLE SD-PROGFILES
VARIABLE SD-PROGDATA
VARIABLE SD-DOTHER

\ ========================================
\ Extension counted strings
\ ========================================

CREATE SE-SYS 3 C, 73 C, 79 C, 73 C,
CREATE SE-DRV 3 C, 64 C, 72 C, 76 C,
CREATE SE-DLL 3 C, 64 C, 6C C, 6C C,
CREATE SE-OCX 3 C, 6F C, 63 C, 78 C,
CREATE SE-CPL 3 C, 63 C, 70 C, 6C C,
CREATE SE-AX  2 C, 61 C, 78 C,
CREATE SE-MUI 3 C, 6D C, 75 C, 69 C,
CREATE SE-EXE 3 C, 65 C, 78 C, 65 C,
CREATE SE-SCR 3 C, 73 C, 63 C, 72 C,
CREATE SE-EFI 3 C, 65 C, 66 C, 69 C,
CREATE SE-COM 3 C, 63 C, 6F C, 6D C,
CREATE SE-KO  2 C, 6B C, 6F C,
CREATE SE-SO  2 C, 73 C, 6F C,

\ ========================================
\ Extension matching (reuse pattern)
\ ========================================

: SD-EXT? ( na nl ext -- flag )
  OVER 3 < IF
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

\ Tally individual extension
: SD-TALLY ( na nl -- )
  2DUP SE-SYS SD-EXT? IF
    1 SD-NSYS +! DROP DROP EXIT THEN
  2DUP SE-DRV SD-EXT? IF
    1 SD-NDRV +! DROP DROP EXIT THEN
  2DUP SE-DLL SD-EXT? IF
    1 SD-NDLL +! DROP DROP EXIT THEN
  2DUP SE-OCX SD-EXT? IF
    1 SD-NOCX +! DROP DROP EXIT THEN
  2DUP SE-CPL SD-EXT? IF
    1 SD-NCPL +! DROP DROP EXIT THEN
  2DUP SE-AX SD-EXT? IF
    1 SD-NAX +! DROP DROP EXIT THEN
  2DUP SE-MUI SD-EXT? IF
    1 SD-NMUI +! DROP DROP EXIT THEN
  2DUP SE-EXE SD-EXT? IF
    1 SD-NEXE +! DROP DROP EXIT THEN
  2DUP SE-SCR SD-EXT? IF
    1 SD-NSCR +! DROP DROP EXIT THEN
  2DUP SE-EFI SD-EXT? IF
    1 SD-NEFI +! DROP DROP EXIT THEN
  2DUP SE-COM SD-EXT? IF
    1 SD-NCOM +! DROP DROP EXIT THEN
  2DUP SE-KO SD-EXT? IF
    1 SD-NKO +! DROP DROP EXIT THEN
  2DUP SE-SO SD-EXT? IF
    1 SD-NSO +! DROP DROP EXIT THEN
  DROP DROP
  1 SD-NOTHER +! ;

\ ========================================
\ Directory bucketing
\ ========================================

\ MFT parent ref is in $FILE_NAME attr
\ at offset 0 (8 bytes, lower 6 = recno)
\ Well-known parent MFT records are
\ not reliable across installs, so we
\ classify by path string instead.

\ Known path substrings (ASCII lower)
CREATE DP-S32 8 C,
  73 C, 79 C, 73 C, 74 C,
  65 C, 6D C, 33 C, 32 C,
CREATE DP-WXS 6 C,
  77 C, 69 C, 6E C,
  73 C, 78 C, 73 C,
CREATE DP-DRV 7 C,
  64 C, 72 C, 69 C, 76 C,
  65 C, 72 C, 73 C,
CREATE DP-PF  7 C,
  70 C, 72 C, 6F C, 67 C,
  72 C, 61 C, 6D C,
CREATE DP-PD  8 C,
  70 C, 72 C, 6F C, 67 C,
  64 C, 61 C, 74 C, 61 C,

\ Check if path contains substring
VARIABLE SD-PA
VARIABLE SD-PL

: SD-PHAS? ( pa pl sub -- flag )
  DUP C@ SD-PL !
  1+
  ROT ROT
  DUP SD-PL @ < IF
    DROP DROP DROP 0 EXIT
  THEN
  SD-PL @ - 1+
  0 DO
    OVER I +
    DUP SD-PL @ 0 DO
      DUP I + C@
      DUP 41 >= IF
        DUP 5A <= IF 20 + THEN
      THEN
      3 PICK I + C@
      <> IF
        DROP DROP 0 LEAVE
      THEN
    LOOP
    DUP 0<> IF
      DROP DROP DROP DROP -1
      UNLOOP EXIT
    THEN
    DROP
  LOOP
  DROP DROP 0 ;

\ Classify path into bucket
: SD-BUCKET ( pa pl -- )
  2DUP DP-DRV SD-PHAS? IF
    1 SD-DRIVERS +!
    DROP DROP EXIT
  THEN
  2DUP DP-S32 SD-PHAS? IF
    1 SD-SYSTEM32 +!
    DROP DROP EXIT
  THEN
  2DUP DP-WXS SD-PHAS? IF
    1 SD-WINSXS +!
    DROP DROP EXIT
  THEN
  2DUP DP-PF SD-PHAS? IF
    1 SD-PROGFILES +!
    DROP DROP EXIT
  THEN
  2DUP DP-PD SD-PHAS? IF
    1 SD-PROGDATA +!
    DROP DROP EXIT
  THEN
  DROP DROP
  1 SD-DOTHER +! ;

\ ========================================
\ Reports
\ ========================================

: SD-ZERO ( -- )
  0 SD-NSYS ! 0 SD-NDRV !
  0 SD-NDLL ! 0 SD-NOCX !
  0 SD-NCPL ! 0 SD-NAX !
  0 SD-NMUI ! 0 SD-NEXE !
  0 SD-NSCR ! 0 SD-NEFI !
  0 SD-NCOM ! 0 SD-NKO !
  0 SD-NSO ! 0 SD-NOTHER !
  0 SD-SYSTEM32 !
  0 SD-WINSXS !
  0 SD-DRIVERS !
  0 SD-PROGFILES !
  0 SD-PROGDATA !
  0 SD-DOTHER ! ;

: SD-EXT-REPORT ( -- )
  ." === Per-Extension ===" CR
  ." .sys:    " SD-NSYS @
  DECIMAL . HEX CR
  ." .drv:    " SD-NDRV @
  DECIMAL . HEX CR
  ." .dll:    " SD-NDLL @
  DECIMAL . HEX CR
  ." .ocx:    " SD-NOCX @
  DECIMAL . HEX CR
  ." .cpl:    " SD-NCPL @
  DECIMAL . HEX CR
  ." .ax:     " SD-NAX @
  DECIMAL . HEX CR
  ." .mui:    " SD-NMUI @
  DECIMAL . HEX CR
  ." .exe:    " SD-NEXE @
  DECIMAL . HEX CR
  ." .scr:    " SD-NSCR @
  DECIMAL . HEX CR
  ." .efi:    " SD-NEFI @
  DECIMAL . HEX CR
  ." .com:    " SD-NCOM @
  DECIMAL . HEX CR
  ." .ko:     " SD-NKO @
  DECIMAL . HEX CR
  ." .so:     " SD-NSO @
  DECIMAL . HEX CR
  ." other:   " SD-NOTHER @
  DECIMAL . HEX CR ;

: SD-DIR-REPORT ( -- )
  ." === Per-Directory ===" CR
  ." System32:     " SD-SYSTEM32 @
  DECIMAL . HEX CR
  ." WinSxS:       " SD-WINSXS @
  DECIMAL . HEX CR
  ." drivers:      " SD-DRIVERS @
  DECIMAL . HEX CR
  ." Program Files:" SD-PROGFILES @
  DECIMAL . HEX CR
  ." ProgramData:  " SD-PROGDATA @
  DECIMAL . HEX CR
  ." Other dirs:   " SD-DOTHER @
  DECIMAL . HEX CR ;

\ ========================================
\ Main: detailed survey (MFT walk)
\ ========================================

: DETAIL-SCAN ( -- )
  MFT-COUNT 0= IF EXIT THEN
  MFT-COUNT 0 DO
    I MFT-READ IF ELSE
      MFT-BUF @ 454C4946 = IF
        MFT-FILENAME
        DUP IF
          2DUP SD-TALLY
          2DUP SD-BUCKET
        THEN
        DROP DROP
      THEN
    THEN
  LOOP ;

: DISK-SURVEY-DETAIL ( -- )
  SD-ZERO
  ." === Detailed Survey ===" CR
  PARTITION-MAP
  PART-N @ 0 DO
    I PART-ENT 8 + C@ PT-NTFS = IF
      ." --- NTFS P"
      I 1+ DECIMAL . HEX
      ." ---" CR
      I PART-ENT @
      NTFS-PROBE IF
        DETAIL-SCAN
      ELSE
        ." NTFS init fail" CR
      THEN
    THEN
  LOOP
  SD-EXT-REPORT
  SD-DIR-REPORT ;

ONLY FORTH DEFINITIONS
DECIMAL
