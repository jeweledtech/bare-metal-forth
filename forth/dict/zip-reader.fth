\ ============================================
\ CATALOG: ZIP-READER
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ REQUIRES: DEFLATE HARDWARE
\ ============================================
\
\ ZIP archive directory reader.
\ Finds End of Central Directory, walks
\ Central Directory entries, prints file
\ listing with sizes. No body decompression.
\
\ Usage:
\   USING ZIP-READER
\   buf size ZIP-LIST
\
\ ============================================

VOCABULARY ZIP-READER
ZIP-READER DEFINITIONS
ALSO DEFLATE
ALSO HARDWARE
HEX

\ ========================================
\ Constants
\ ========================================

\ ZIP signatures
6054B50 CONSTANT EOCD-SIG
2014B50 CONSTANT CD-SIG
4034B50 CONSTANT LF-SIG

\ Binary extension strings for matching
CREATE ZE-SYS 3 C, 73 C, 79 C, 73 C,
CREATE ZE-DLL 3 C, 64 C, 6C C, 6C C,
CREATE ZE-EXE 3 C, 65 C, 78 C, 65 C,
CREATE ZE-DRV 3 C, 64 C, 72 C, 76 C,
CREATE ZE-EFI 3 C, 65 C, 66 C, 69 C,
CREATE ZE-KO  2 C, 6B C, 6F C,
CREATE ZE-SO  2 C, 73 C, 6F C,

\ ========================================
\ Counters
\ ========================================

VARIABLE ZIP-NFILES
VARIABLE ZIP-NBINS
VARIABLE ZIP-NARCH

\ ========================================
\ Little-endian field readers
\ ========================================

: Z@ ( addr -- u32 )
  DUP C@ SWAP
  DUP 1+ C@ 8 LSHIFT OR SWAP
  DUP 2 + C@ 10 LSHIFT OR SWAP
  3 + C@ 18 LSHIFT OR ;

: ZW@ ( addr -- u16 )
  DUP C@ SWAP 1+ C@ 8 LSHIFT OR ;

\ ========================================
\ EOCD finder (search backward)
\ ========================================

\ buf: start of loaded ZIP data
\ sz: size in bytes
\ Returns EOCD address or 0

VARIABLE ZR-BUF
VARIABLE ZR-SZ

: ZIP-FIND-EOCD ( buf sz -- addr | 0 )
  DUP ZR-SZ ! OVER ZR-BUF !
  \ Search backward from end for sig
  \ EOCD is at least 22 bytes
  + 16 -
  BEGIN
    DUP ZR-BUF @ >= IF
      DUP Z@ EOCD-SIG = IF
        EXIT
      THEN
    ELSE
      DROP 0 EXIT
    THEN
    1-
    DUP ZR-BUF @ <
  UNTIL
  DROP 0 ;

\ ========================================
\ Extension matching
\ ========================================

VARIABLE ZM-NA
VARIABLE ZM-NL

\ Compare 3-char extension (lowercase)
: Z-LOWER ( c -- c' )
  DUP 41 >= IF
    DUP 5A <= IF 20 + THEN
  THEN ;

\ Check if name ends with given ext
: Z-EXT? ( na nl ext -- flag )
  OVER 4 < IF DROP DROP DROP 0 EXIT THEN
  DUP C@
  ROT ROT
  OVER + OVER C@ - 1-
  SWAP C@ 1+
  0 DO
    DUP I + C@ Z-LOWER
    OVER I + 1+ C@
    <> IF
      DROP DROP 0 UNLOOP EXIT
    THEN
  LOOP
  DROP DROP -1 ;

\ Check if file is a binary
: Z-ISBIN? ( na nl -- flag )
  2DUP ZE-SYS Z-EXT? IF
    DROP DROP -1 EXIT THEN
  2DUP ZE-DLL Z-EXT? IF
    DROP DROP -1 EXIT THEN
  2DUP ZE-EXE Z-EXT? IF
    DROP DROP -1 EXIT THEN
  2DUP ZE-DRV Z-EXT? IF
    DROP DROP -1 EXIT THEN
  2DUP ZE-EFI Z-EXT? IF
    DROP DROP -1 EXIT THEN
  2DUP ZE-KO Z-EXT? IF
    DROP DROP -1 EXIT THEN
  ZE-SO Z-EXT? ;

\ ========================================
\ Central Directory walker
\ ========================================

VARIABLE ZC-PTR
VARIABLE ZC-LEFT

\ Print n chars from addr
: Z-TYPE ( addr n -- )
  DUP 0> IF
    0 DO DUP I + C@ EMIT LOOP
  ELSE DROP THEN
  DROP ;

\ Process one CD entry
: ZIP-CD-ONE ( -- )
  ZC-PTR @
  DUP Z@ CD-SIG <> IF
    DROP 0 ZC-LEFT ! EXIT
  THEN
  DUP 1C + ZW@
  OVER 1E + ZW@
  OVER 20 + ZW@
  \ ( entry fnlen xlen clen )
  \ filename at entry + 2E
  3 PICK 2E +
  4 PICK 1C + ZW@
  \ ( entry fnlen xlen clen fna fnl )
  2DUP Z-TYPE CR
  1 ZIP-NFILES +!
  \ Check if binary extension
  2DUP Z-ISBIN? IF
    1 ZIP-NBINS +!
  THEN
  DROP DROP
  \ Advance pointer past entry
  \ size = 46 + fnlen + xlen + clen
  + + 2E + ZC-PTR !
  -1 ZC-LEFT +! ;

\ Walk all CD entries
: ZIP-CD-WALK ( cd-addr count -- )
  ZC-LEFT ! ZC-PTR !
  BEGIN
    ZC-LEFT @ 0>
  WHILE
    ZIP-CD-ONE
  REPEAT ;

\ ========================================
\ Main entry points
\ ========================================

\ List all files in ZIP buffer
: ZIP-LIST ( buf sz -- )
  0 ZIP-NFILES ! 0 ZIP-NBINS !
  2DUP ZIP-FIND-EOCD
  DUP 0= IF
    DROP DROP DROP
    ." Not a ZIP file" CR EXIT
  THEN
  \ EOCD fields:
  \ +8: entries in CD (16-bit)
  \ +10: CD offset from start (32-bit)
  DUP 8 + ZW@
  SWAP 10 + Z@
  \ ( buf sz entries cd-offset )
  DROP
  2 PICK + SWAP
  \ ( buf cd-addr entries )
  ROT DROP
  ZIP-CD-WALK
  ." --- ZIP Summary ---" CR
  ." Files: "
  ZIP-NFILES @
  DECIMAL . HEX CR
  ." Binaries: "
  ZIP-NBINS @
  DECIMAL . HEX CR ;

\ Count binaries only (no print)
: ZIP-COUNT ( buf sz -- nbins )
  0 ZIP-NFILES ! 0 ZIP-NBINS !
  2DUP ZIP-FIND-EOCD
  DUP 0= IF
    DROP DROP DROP 0 EXIT
  THEN
  DUP 8 + ZW@
  SWAP 10 + Z@
  DROP
  2 PICK + SWAP
  ROT DROP
  ZC-LEFT ! ZC-PTR !
  BEGIN
    ZC-LEFT @ 0>
  WHILE
    ZC-PTR @
    DUP Z@ CD-SIG <> IF
      DROP 0 ZC-LEFT ! EXIT
    THEN
    DUP 1C + ZW@
    OVER 1E + ZW@
    OVER 20 + ZW@
    3 PICK 2E +
    4 PICK 1C + ZW@
    2DUP Z-ISBIN? IF
      1 ZIP-NBINS +!
    THEN
    DROP DROP + + 2E + ZC-PTR !
    -1 ZC-LEFT +!
  REPEAT
  ZIP-NBINS @ ;

ONLY FORTH DEFINITIONS
DECIMAL
