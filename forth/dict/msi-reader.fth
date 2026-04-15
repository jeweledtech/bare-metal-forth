\ ============================================
\ CATALOG: MSI-READER
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ REQUIRES: CAB-EXTRACT DEFLATE HARDWARE
\ ============================================
\
\ OLE2 Compound Document parser for MSI
\ (Windows Installer) files. Reads FAT
\ sector chains, directory stream, and
\ MSI file table. Counts embedded binaries.
\
\ Usage:
\   USING MSI-READER
\   buf size MSI-LIST
\
\ ============================================

VOCABULARY MSI-READER
MSI-READER DEFINITIONS
ALSO CAB-EXTRACT
ALSO DEFLATE
ALSO HARDWARE
HEX

\ ========================================
\ OLE2 constants
\ ========================================

\ OLE2 signature (first 8 bytes)
\ D0CF11E0 A1B11AE1
VARIABLE OLE2-SIG1
VARIABLE OLE2-SIG2

: OLE2-INIT ( -- )
  D0CF11E0 OLE2-SIG1 !
  A1B11AE1 OLE2-SIG2 ! ;

\ Sector sizes (default 512=200h)
VARIABLE OL-SSIZ
VARIABLE OL-MSSIZ

\ Special sector IDs
FFFFFFFE CONSTANT ENDCHAIN
FFFFFFFD CONSTANT FATSECT
FFFFFFFC CONSTANT DIFSECT
FFFFFFFB CONSTANT NOTUSED

\ Directory entry types
0 CONSTANT DE-EMPTY
1 CONSTANT DE-STORAGE
2 CONSTANT DE-STREAM
5 CONSTANT DE-ROOT

\ ========================================
\ Little-endian readers
\ ========================================

: OL@ ( addr -- u32 )
  DUP C@ SWAP
  DUP 1+ C@ 8 LSHIFT OR SWAP
  DUP 2 + C@ 10 LSHIFT OR SWAP
  3 + C@ 18 LSHIFT OR ;

: OLW@ ( addr -- u16 )
  DUP C@ SWAP 1+ C@ 8 LSHIFT OR ;

\ ========================================
\ State
\ ========================================

VARIABLE OL-BUF
VARIABLE OL-SZ
VARIABLE OL-FATST
VARIABLE OL-NFAT
VARIABLE OL-DIRST
VARIABLE OL-MFATST
VARIABLE OL-NMFAT

\ Counters
VARIABLE OL-NFILES
VARIABLE OL-NBINS
VARIABLE OL-NSTR

\ ========================================
\ OLE2 header parser
\ ========================================

: OLE2-CHECK ( buf -- flag )
  DUP OL@ D0CF11E0 = IF
    4 + OL@ A1B11AE1 =
  ELSE
    DROP 0
  THEN ;

: OLE2-PARSE ( buf sz -- flag )
  OL-SZ ! OL-BUF !
  OL-BUF @ OLE2-CHECK 0= IF
    0 EXIT
  THEN
  \ Sector size: 2^(word at offset 1E)
  OL-BUF @ 1E + OLW@
  1 SWAP LSHIFT OL-SSIZ !
  \ Mini-sector size: 2^(word at 20)
  OL-BUF @ 20 + OLW@
  1 SWAP LSHIFT OL-MSSIZ !
  \ FAT sectors count
  OL-BUF @ 2C + OL@ OL-NFAT !
  \ First directory sector
  OL-BUF @ 30 + OL@ OL-DIRST !
  \ First mini-FAT sector
  OL-BUF @ 3C + OL@ OL-MFATST !
  \ Mini-FAT sector count
  OL-BUF @ 40 + OL@ OL-NMFAT !
  -1 ;

\ ========================================
\ Sector addressing
\ ========================================

\ Sector ID to byte offset in file
: OL-SOFF ( sect-id -- offset )
  1+ OL-SSIZ @ * ;

\ Get sector data address
: OL-SADDR ( sect-id -- addr )
  OL-SOFF OL-BUF @ + ;

\ Read FAT entry for given sector
: OL-FAT@ ( sect-id -- next-sect )
  \ Each FAT entry is 4 bytes
  \ FAT sectors listed at header +4C
  DUP OL-SSIZ @ 4 / /
  \ ( sect-id fat-sect-idx )
  OL-BUF @ 4C + SWAP 4 * + OL@
  \ ( sect-id fat-sect-id )
  OL-SADDR
  SWAP OL-SSIZ @ 4 / MOD
  4 * + OL@ ;

\ ========================================
\ Directory stream reader
\ ========================================

\ Each directory entry is 128 bytes (80h)
\ +0: name (64 bytes UTF-16LE)
\ +40: name size in bytes (u16)
\ +42: object type (byte)
\ +43: color (byte)
\ +44: left sibling (u32)
\ +48: right sibling (u32)
\ +4C: child (u32)
\ +74: start sector (u32)
\ +78: size low (u32)

VARIABLE OD-SEC
VARIABLE OD-OFF
VARIABLE OD-ENT

\ Get directory entry address
: OL-DENT ( idx -- addr )
  80 *
  DUP OL-SSIZ @ /
  \ ( byte-off sect-idx )
  SWAP OL-SSIZ @ MOD
  \ ( sect-idx byte-in-sect )
  SWAP
  \ Walk FAT chain sect-idx times
  OL-DIRST @
  SWAP DUP 0> IF
    0 DO
      OL-FAT@
    LOOP
  ELSE DROP THEN
  OL-SADDR + ;

\ Print UTF-16LE name (skip every other)
: OL-PNAME ( entry -- )
  DUP 40 + OLW@
  DUP 2 > IF
    2 - 2 /
    0 DO
      DUP I DUP + + C@ EMIT
    LOOP
  ELSE DROP THEN
  DROP ;

\ Get entry type
: OL-ETYPE ( entry -- type )
  42 + C@ ;

\ Get entry stream size
: OL-ESIZE ( entry -- size )
  78 + OL@ ;

\ Get entry start sector
: OL-ESTART ( entry -- sect )
  74 + OL@ ;

\ ========================================
\ Binary extension check (UTF-16LE)
\ ========================================

\ Get byte at position in UTF-16 name
: OL-NC ( entry pos -- char )
  DUP + + C@ ;

\ Lowercase
: OL-LOW ( c -- c' )
  DUP 41 >= IF
    DUP 5A <= IF 20 + THEN
  THEN ;

\ Check if name ends with .ext (UTF-16)
: OL-EXT? ( entry nchars c1 c2 c3 -- f )
  3 PICK 5 < IF
    DROP DROP DROP DROP DROP 0 EXIT
  THEN
  \ Check last 4 chars: . c1 c2 c3
  4 PICK 3 PICK 1- OL-NC OL-LOW
  2 PICK <> IF
    DROP DROP DROP DROP DROP 0 EXIT
  THEN
  4 PICK 3 PICK 2 - OL-NC OL-LOW
  3 PICK <> IF
    DROP DROP DROP DROP DROP 0 EXIT
  THEN
  4 PICK 3 PICK 3 - OL-NC OL-LOW
  OVER <> IF
    DROP DROP DROP DROP DROP 0 EXIT
  THEN
  DROP DROP
  SWAP 4 - OL-NC 2E =
  NIP ;

: OL-ISBIN? ( entry -- flag )
  DUP 40 + OLW@ 2 - 2 /
  2DUP 73 79 73 OL-EXT? IF
    DROP DROP -1 EXIT THEN
  2DUP 64 6C 6C OL-EXT? IF
    DROP DROP -1 EXIT THEN
  2DUP 65 78 65 OL-EXT? IF
    DROP DROP -1 EXIT THEN
  2DUP 64 72 76 OL-EXT? IF
    DROP DROP -1 EXIT THEN
  2DUP 65 66 69 OL-EXT? IF
    DROP DROP -1 EXIT THEN
  DROP DROP 0 ;

\ ========================================
\ Directory tree walker
\ ========================================

\ Walk directory tree (iterative BFS)
\ Root entry is at index 0

VARIABLE OD-IDX
VARIABLE OD-MAX

: OL-WALK-DIR ( -- )
  \ Estimate max entries from file size
  OL-SZ @ 80 / OD-MAX !
  OD-MAX @ 0> IF
    OD-MAX @ 0 DO
      I OL-DENT OD-ENT !
      OD-ENT @ OL-ETYPE
      DUP DE-STREAM = IF
        DROP
        OD-ENT @ OL-PNAME
        ."  ("
        OD-ENT @ OL-ESIZE
        DECIMAL . HEX
        ." bytes)" CR
        1 OL-NSTR +!
        OD-ENT @ OL-ISBIN? IF
          1 OL-NBINS +!
        THEN
      ELSE DUP DE-STORAGE = IF
        DROP
        ." [" OD-ENT @ OL-PNAME
        ." ]" CR
      ELSE DUP DE-ROOT = IF
        DROP
        ." {Root: "
        OD-ENT @ OL-PNAME
        ." }" CR
      ELSE
        DROP
      THEN THEN THEN
    LOOP
  THEN ;

\ ========================================
\ Main entry points
\ ========================================

: MSI-LIST ( buf sz -- )
  0 OL-NFILES ! 0 OL-NBINS !
  0 OL-NSTR !
  OLE2-PARSE 0= IF
    ." Not an MSI/OLE2 file" CR EXIT
  THEN
  ." --- MSI Contents ---" CR
  ." Sector size: "
  OL-SSIZ @
  DECIMAL . HEX CR
  OL-WALK-DIR
  ." --- MSI Summary ---" CR
  ." Streams: "
  OL-NSTR @
  DECIMAL . HEX CR
  ." Binaries: "
  OL-NBINS @
  DECIMAL . HEX CR ;

\ Count binaries only
: MSI-COUNT ( buf sz -- nbins )
  0 OL-NFILES ! 0 OL-NBINS !
  0 OL-NSTR !
  OLE2-PARSE 0= IF 0 EXIT THEN
  OL-SZ @ 80 / OD-MAX !
  OD-MAX @ 0> IF
    OD-MAX @ 0 DO
      I OL-DENT OD-ENT !
      OD-ENT @ OL-ETYPE
      DE-STREAM = IF
        OD-ENT @ OL-ISBIN? IF
          1 OL-NBINS +!
        THEN
      THEN
    LOOP
  THEN
  OL-NBINS @ ;

ONLY FORTH DEFINITIONS
DECIMAL
