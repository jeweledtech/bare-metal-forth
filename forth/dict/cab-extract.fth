\ ============================================
\ CATALOG: CAB-EXTRACT
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ REQUIRES: DEFLATE HARDWARE
\ ============================================
\
\ Microsoft Cabinet (.cab) format parser.
\ Reads CAB headers, lists files inside.
\ MSZIP decompression via DEFLATE vocab.
\ LZX decompression deferred to Phase 2.1.
\
\ Usage:
\   USING CAB-EXTRACT
\   buf size CAB-LIST
\
\ ============================================

VOCABULARY CAB-EXTRACT
CAB-EXTRACT DEFINITIONS
ALSO DEFLATE
ALSO HARDWARE
HEX

\ ========================================
\ CAB format constants
\ ========================================

\ CAB signature: "MSCF" = 4643534D
4643534D CONSTANT MSCF-SIG

\ Compression types
0 CONSTANT CT-NONE
1 CONSTANT CT-MSZIP
3 CONSTANT CT-LZX

\ Header flags
1 CONSTANT CF-PREV
2 CONSTANT CF-NEXT
4 CONSTANT CF-RESERVE

\ ========================================
\ Little-endian field readers
\ ========================================

: CB@ ( addr -- u32 )
  DUP C@ SWAP
  DUP 1+ C@ 8 LSHIFT OR SWAP
  DUP 2 + C@ 10 LSHIFT OR SWAP
  3 + C@ 18 LSHIFT OR ;

: CBW@ ( addr -- u16 )
  DUP C@ SWAP 1+ C@ 8 LSHIFT OR ;

\ ========================================
\ State variables
\ ========================================

VARIABLE CB-BUF
VARIABLE CB-SZ

\ Header fields
VARIABLE CB-CSIZ
VARIABLE CB-FOFF
VARIABLE CB-NFOLD
VARIABLE CB-NFILE
VARIABLE CB-FLAGS
VARIABLE CB-HRSZ
VARIABLE CB-FRSZ
VARIABLE CB-DRSZ

\ Counters
VARIABLE CB-NFILES
VARIABLE CB-NBINS

\ ========================================
\ Binary extension checking
\ ========================================

\ Lowercase a char
: CB-LOW ( c -- c' )
  DUP 41 >= IF
    DUP 5A <= IF 20 + THEN
  THEN ;

\ Check 3-char extension at end of name
VARIABLE CB-ENA
VARIABLE CB-ENL

: CB-EXT3? ( na nl c1 c2 c3 -- flag )
  ROT ROT
  3 PICK 4 < IF
    DROP DROP DROP DROP DROP 0 EXIT
  THEN
  4 PICK 3 PICK + 1-
  DUP C@ CB-LOW 2 PICK <> IF
    DROP DROP DROP DROP DROP 0 EXIT
  THEN
  1-
  DUP C@ CB-LOW 3 PICK <> IF
    DROP DROP DROP DROP DROP 0 EXIT
  THEN
  1-
  C@ CB-LOW <> IF
    DROP DROP 0 EXIT
  THEN
  DROP DROP
  \ Check dot before ext
  OVER OVER + 4 - C@ 2E = ;

\ Check if filename is a binary
: CB-ISBIN? ( na nl -- flag )
  2DUP 73 79 73 CB-EXT3? IF
    DROP DROP -1 EXIT THEN
  2DUP 64 6C 6C CB-EXT3? IF
    DROP DROP -1 EXIT THEN
  2DUP 65 78 65 CB-EXT3? IF
    DROP DROP -1 EXIT THEN
  2DUP 64 72 76 CB-EXT3? IF
    DROP DROP -1 EXIT THEN
  2DUP 65 66 69 CB-EXT3? IF
    DROP DROP -1 EXIT THEN
  DROP DROP 0 ;

\ ========================================
\ CAB header parser
\ ========================================

: CAB-CHECK ( buf -- flag )
  CB@ MSCF-SIG = ;

: CAB-PARSE ( buf sz -- flag )
  CB-SZ ! CB-BUF !
  CB-BUF @ CB@ MSCF-SIG <> IF
    0 EXIT
  THEN
  \ Parse fixed header (60 bytes)
  CB-BUF @ 8 + CB@ CB-CSIZ !
  CB-BUF @ 10 + CB@ CB-FOFF !
  CB-BUF @ 1A + CBW@ CB-NFOLD !
  CB-BUF @ 1C + CBW@ CB-NFILE !
  CB-BUF @ 1E + CBW@ CB-FLAGS !
  \ Handle reserved fields
  0 CB-HRSZ ! 0 CB-FRSZ !
  0 CB-DRSZ !
  CB-FLAGS @ CF-RESERVE AND IF
    CB-BUF @ 24 + CBW@ CB-HRSZ !
    CB-BUF @ 26 + C@ CB-FRSZ !
    CB-BUF @ 27 + C@ CB-DRSZ !
  THEN
  -1 ;

\ ========================================
\ Folder entry reader
\ ========================================

\ Folder entry: 8 bytes + reserve
\ +0: data offset (4)
\ +4: data block count (2)
\ +6: compression type (2)

VARIABLE CB-FBASE

: CB-FOLD-ADDR ( -- addr )
  CB-BUF @ 24 +
  CB-FLAGS @ CF-RESERVE AND IF
    4 + CB-HRSZ @ +
  THEN ;

: CB-FOLD-ENT ( idx -- addr )
  8 CB-FRSZ @ + * CB-FOLD-ADDR + ;

: CB-FOLD-COMP ( idx -- type )
  CB-FOLD-ENT 6 + CBW@ ;

\ ========================================
\ File entry reader
\ ========================================

\ File entry (variable size):
\ +0: uncompressed size (4)
\ +4: offset in folder (4)
\ +8: folder index (2)
\ +A: date (2)
\ +C: time (2)
\ +E: attributes (2)
\ +10: null-terminated filename

VARIABLE CF-PTR

\ Get null-terminated string length
: CB-SLEN ( addr -- len )
  0
  BEGIN
    OVER OVER + C@ 0<>
  WHILE
    1+
  REPEAT
  NIP ;

\ Print file entry and count
: CB-FILE-ONE ( -- bytes-consumed )
  CF-PTR @
  DUP CB@ CB-CSIZ !
  DUP 10 +
  DUP CB-SLEN
  \ ( entry name-addr name-len )
  2DUP
  0 DO
    DUP I + C@ EMIT
  LOOP
  DROP DROP
  ."  ("
  2 PICK CB@
  DECIMAL . HEX
  ." bytes)" CR
  1 CB-NFILES +!
  \ Check if binary
  CB-ISBIN? IF
    1 CB-NBINS +!
  THEN
  \ Advance past entry
  CF-PTR @ 10 +
  DUP CB-SLEN + 1+
  CF-PTR @ - ;

\ ========================================
\ Main entry points
\ ========================================

: CAB-LIST ( buf sz -- )
  0 CB-NFILES ! 0 CB-NBINS !
  CAB-PARSE 0= IF
    ." Not a CAB file" CR EXIT
  THEN
  ." --- CAB Contents ---" CR
  \ File entries start at CB-FOFF
  CB-BUF @ CB-FOFF @ + CF-PTR !
  CB-NFILE @ 0> IF
    CB-NFILE @ 0 DO
      CB-FILE-ONE CF-PTR +!
    LOOP
  THEN
  ." --- CAB Summary ---" CR
  ." Files: "
  CB-NFILES @
  DECIMAL . HEX CR
  ." Binaries: "
  CB-NBINS @
  DECIMAL . HEX CR
  ." Folders: "
  CB-NFOLD @
  DECIMAL . HEX CR
  ." Compression: "
  CB-NFOLD @ 0> IF
    0 CB-FOLD-COMP
    DUP CT-NONE = IF
      ." none" THEN
    DUP CT-MSZIP = IF
      ." MSZIP" THEN
    DUP CT-LZX = IF
      ." LZX" THEN
    DROP
  ELSE
    ." unknown"
  THEN CR ;

\ Count binaries only (no print)
: CAB-COUNT ( buf sz -- nbins )
  0 CB-NFILES ! 0 CB-NBINS !
  CAB-PARSE 0= IF 0 EXIT THEN
  CB-BUF @ CB-FOFF @ + CF-PTR !
  CB-NFILE @ 0> IF
    CB-NFILE @ 0 DO
      CF-PTR @
      DUP 10 +
      DUP CB-SLEN
      CB-ISBIN? IF
        1 CB-NBINS +!
      THEN
      CF-PTR @ 10 +
      DUP CB-SLEN + 1+
      CF-PTR @ -
      CF-PTR +!
    LOOP
  THEN
  CB-NBINS @ ;

\ MSZIP data block decompression
\ Each data block: 2-byte "CK" + DEFLATE
: CAB-MSZIP ( src dst slen -- end )
  DROP
  \ Check "CK" signature (43h 4Bh)
  OVER C@ 43 <> IF
    ." Bad MSZIP sig" CR EXIT
  THEN
  OVER 1+ C@ 4B <> IF
    ." Bad MSZIP sig" CR EXIT
  THEN
  SWAP 2 + SWAP
  DFL-DECOMPRESS ;

ONLY FORTH DEFINITIONS
DECIMAL
