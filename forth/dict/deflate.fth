\ ============================================
\ CATALOG: DEFLATE
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ REQUIRES: HARDWARE
\ ============================================
\
\ DEFLATE decompressor (RFC 1951).
\ Stored, fixed, and dynamic Huffman.
\ Shared by ZIP-READER, CAB-EXTRACT,
\ and MSI-READER vocabularies.
\
\ Usage:
\   USING DEFLATE
\   src dst DFL-DECOMPRESS ( -- end )
\
\ ============================================

VOCABULARY DEFLATE
DEFLATE DEFINITIONS
ALSO HARDWARE
HEX

\ ========================================
\ Bitstream reader (LSB first per RFC)
\ ========================================

VARIABLE DFL-SRC
VARIABLE DFL-BYTE
VARIABLE DFL-BREM

: DFL-BINIT ( src -- )
  DFL-SRC !
  0 DFL-BYTE ! 0 DFL-BREM ! ;

: DFL-BIT ( -- bit )
  DFL-BREM @ 0= IF
    DFL-SRC @ C@ DFL-BYTE !
    1 DFL-SRC +! 8 DFL-BREM !
  THEN
  DFL-BYTE @ 1 AND
  DFL-BYTE @ 1 RSHIFT DFL-BYTE !
  -1 DFL-BREM +! ;

: DFL-BITS ( n -- val )
  DUP 0= IF DROP 0 EXIT THEN
  0 SWAP 0 DO
    DFL-BIT I LSHIFT OR
  LOOP ;

\ ========================================
\ Output buffer
\ ========================================

VARIABLE DFL-DST
VARIABLE DFL-DSTA

: DFL-OUT ( byte -- )
  DFL-DST @ C! 1 DFL-DST +! ;

\ ========================================
\ Huffman table storage
\ ========================================

\ Literal/length table (288=120h symbols)
CREATE HL-LENS 120 ALLOT
CREATE HL-BLC 10 ALLOT
CREATE HL-NXC 40 ALLOT
VARIABLE HL-MAX

\ Distance table (32=20h symbols)
CREATE HD-LENS 20 ALLOT
CREATE HD-BLC 10 ALLOT
CREATE HD-NXC 40 ALLOT
VARIABLE HD-MAX

\ Code-length table (19=13h symbols)
CREATE HC-LENS 14 ALLOT
CREATE HC-BLC 10 ALLOT
CREATE HC-NXC 40 ALLOT
VARIABLE HC-MAX

\ ========================================
\ Current table pointers (generic ops)
\ ========================================

VARIABLE HT-LENS
VARIABLE HT-BLC
VARIABLE HT-NXC
VARIABLE HT-NSYM
VARIABLE HT-MAXB

\ Select literal table
: HT-LIT ( -- )
  HL-LENS HT-LENS ! HL-BLC HT-BLC !
  HL-NXC HT-NXC !
  120 HT-NSYM ! HL-MAX @ HT-MAXB ! ;

\ Select distance table
: HT-DST ( -- )
  HD-LENS HT-LENS ! HD-BLC HT-BLC !
  HD-NXC HT-NXC !
  20 HT-NSYM ! HD-MAX @ HT-MAXB ! ;

\ Select code-length table
: HT-CL ( -- )
  HC-LENS HT-LENS ! HC-BLC HT-BLC !
  HC-NXC HT-NXC !
  13 HT-NSYM ! HC-MAX @ HT-MAXB ! ;

\ ========================================
\ Build canonical Huffman code table
\ ========================================

: HT-BUILD ( -- )
  \ Clear bl_count
  10 0 DO
    0 HT-BLC @ I + C!
  LOOP
  \ Count code lengths (skip 0-length)
  HT-NSYM @ 0 DO
    HT-LENS @ I + C@ DUP IF
      HT-BLC @ + DUP C@ 1+ SWAP C!
    ELSE DROP THEN
  LOOP
  \ Find max bit length
  0 HT-MAXB !
  10 1 DO
    HT-BLC @ I + C@ IF
      I HT-MAXB !
    THEN
  LOOP
  \ Build next_code array
  0 HT-NXC @ !
  HT-MAXB @ 1+ 1 DO
    HT-NXC @ I 1- 4 * + @
    HT-BLC @ I 1- + C@ +
    DUP +
    HT-NXC @ I 4 * + !
  LOOP ;

\ Build and save max for each table
: HL-BUILD ( -- )
  HT-LIT HT-BUILD HT-MAXB @ HL-MAX ! ;
: HD-BUILD ( -- )
  HT-DST HT-BUILD HT-MAXB @ HD-MAX ! ;
: HC-BUILD ( -- )
  HT-CL HT-BUILD HT-MAXB @ HC-MAX ! ;

\ ========================================
\ Decode one Huffman symbol
\ ========================================

VARIABLE DC-CODE
VARIABLE DC-BLEN
VARIABLE DC-IDX

: HT-DEC ( -- sym )
  0 DC-CODE ! 1 DC-BLEN !
  BEGIN
    DC-CODE @ DUP +
    DFL-BIT OR DC-CODE !
    HT-BLC @ DC-BLEN @ + C@ IF
      DC-CODE @
      HT-NXC @ DC-BLEN @ 4 * + @
      -
      DUP 0< 0= IF
        DUP
        HT-BLC @ DC-BLEN @ + C@
        < IF
          DC-IDX !
          0
          HT-NSYM @ 0 DO
            HT-LENS @ I + C@
            DC-BLEN @ = IF
              DUP DC-IDX @ = IF
                DROP I
                UNLOOP EXIT
              THEN
              1+
            THEN
          LOOP
          DROP
        ELSE DROP THEN
      ELSE DROP THEN
    THEN
    1 DC-BLEN +!
    DC-BLEN @ 10 >
  UNTIL
  0 ;

\ Shorthand decoders
: LDEC ( -- sym ) HT-LIT HT-DEC ;
: DDEC ( -- sym ) HT-DST HT-DEC ;
: CDEC ( -- sym ) HT-CL HT-DEC ;

\ ========================================
\ Length/distance lookup tables
\ ========================================

\ Length extra bits (29 entries, 257-285)
CREATE LN-XB
  0 C, 0 C, 0 C, 0 C,
  0 C, 0 C, 0 C, 0 C,
  1 C, 1 C, 1 C, 1 C,
  2 C, 2 C, 2 C, 2 C,
  3 C, 3 C, 3 C, 3 C,
  4 C, 4 C, 4 C, 4 C,
  5 C, 5 C, 5 C, 5 C, 0 C,

\ Length base values (29 cells)
CREATE LN-BASE
  3 , 4 , 5 , 6 ,
  7 , 8 , 9 , A ,
  B , D , F , 11 ,
  13 , 17 , 1B , 1F ,
  23 , 2B , 33 , 3B ,
  43 , 53 , 63 , 73 ,
  83 , A3 , C3 , E3 , 102 ,

\ Distance extra bits (30 entries)
CREATE DT-XB
  0 C, 0 C, 1 C, 1 C,
  2 C, 2 C, 3 C, 3 C,
  4 C, 4 C, 5 C, 5 C,
  6 C, 6 C, 7 C, 7 C,
  8 C, 8 C, 9 C, 9 C,
  A C, A C, B C, B C,
  C C, C C, D C, D C, D C, D C,

\ Distance base values (30 cells)
CREATE DT-BASE
  1 , 2 , 3 , 5 ,
  7 , B , F , 17 ,
  1F , 2F , 3F , 5F ,
  7F , BF , FF , 17F ,
  1FF , 2FF , 3FF , 5FF ,
  7FF , BFF , FFF , 17FF ,
  1FFF , 2FFF , 3FFF , 5FFF ,
  7FFF , 9FFF ,

\ ========================================
\ Block decoder helpers
\ ========================================

\ Copy len bytes from distance back
: DFL-COPY ( len dist -- )
  DFL-DST @ SWAP -
  SWAP
  DUP 0> IF
    0 DO DUP I + C@ DFL-OUT LOOP
  ELSE DROP THEN
  DROP ;

\ Decode length from symbol 257-285
: DFL-LEN ( sym -- length )
  101 -
  DUP LN-XB + C@
  SWAP LN-BASE SWAP 4 * + @
  SWAP DFL-BITS + ;

\ Decode distance code and value
: DFL-DIST ( -- distance )
  DDEC
  DUP DT-XB + C@
  SWAP DT-BASE SWAP 4 * + @
  SWAP DFL-BITS + ;

\ Decode one Huffman-coded block
: DFL-HBLOCK ( -- )
  BEGIN
    LDEC
    DUP 100 < IF
      DFL-OUT 0
    ELSE DUP 100 = IF
      DROP 1
    ELSE
      DFL-LEN DFL-DIST DFL-COPY 0
    THEN THEN
  UNTIL ;

\ ========================================
\ Fixed Huffman (RFC 1951 sec 3.2.6)
\ ========================================

: DFL-FIXED ( -- )
  \ Lit 0-143: 8 bits
  90 0 DO 8 HL-LENS I + C! LOOP
  \ Lit 144-255: 9 bits
  70 0 DO 9 HL-LENS 90 + I + C! LOOP
  \ Lit/len 256-279: 7 bits
  18 0 DO 7 HL-LENS 100 + I + C! LOOP
  \ Lit/len 280-287: 8 bits
  8 0 DO 8 HL-LENS 118 + I + C! LOOP
  \ Distance 0-31: 5 bits
  20 0 DO 5 HD-LENS I + C! LOOP
  HL-BUILD HD-BUILD ;

\ ========================================
\ Dynamic Huffman (RFC 1951 sec 3.2.7)
\ ========================================

\ Code-length code order per RFC
CREATE CL-ORD
  10 C, 11 C, 12 C, 0 C,
  8 C, 7 C, 9 C, 6 C,
  A C, 5 C, B C, 4 C,
  C C, 3 C, D C, 2 C,
  E C, 1 C, F C,

\ Combined code lengths (max 320=140h)
CREATE DY-CL 140 ALLOT

VARIABLE DY-HLIT
VARIABLE DY-HDIST
VARIABLE DY-POS
VARIABLE DY-PREV

: DY-STORE ( val -- )
  DY-CL DY-POS @ + C!
  1 DY-POS +! ;

: DY-REPEAT ( val cnt -- )
  DUP 0> IF
    0 DO DUP DY-STORE LOOP
  ELSE DROP THEN
  DROP ;

\ Split combined lengths into HL/HD
: DY-SPLIT ( -- )
  DY-HLIT @ 0 DO
    DY-CL I + C@ HL-LENS I + C!
  LOOP
  120 DY-HLIT @ DO
    0 HL-LENS I + C!
  LOOP
  DY-HDIST @ 0 DO
    DY-CL DY-HLIT @ + I + C@
    HD-LENS I + C!
  LOOP
  20 DY-HDIST @ DO
    0 HD-LENS I + C!
  LOOP ;

: DFL-DYNAMIC ( -- )
  \ Read header fields
  5 DFL-BITS 101 + DY-HLIT !
  5 DFL-BITS 1+ DY-HDIST !
  4 DFL-BITS 4 +
  \ Clear code-length lengths
  13 0 DO 0 HC-LENS I + C! LOOP
  \ Read HCLEN code-length lengths
  DUP 0> IF
    0 DO
      3 DFL-BITS
      HC-LENS CL-ORD I + C@ + C!
    LOOP
  ELSE DROP THEN
  HC-BUILD
  \ Decode lit + dist code lengths
  0 DY-POS ! 0 DY-PREV !
  BEGIN
    DY-POS @
    DY-HLIT @ DY-HDIST @ + <
  WHILE
    CDEC
    DUP 10 < IF
      DUP DY-PREV ! DY-STORE
    ELSE DUP 10 = IF
      DROP
      2 DFL-BITS 3 +
      DY-PREV @ SWAP DY-REPEAT
    ELSE DUP 11 = IF
      DROP
      3 DFL-BITS 3 +
      0 SWAP DY-REPEAT
    ELSE
      \ code 18: repeat 0 for 11+N
      DROP
      7 DFL-BITS B +
      0 SWAP DY-REPEAT
    THEN THEN THEN
  REPEAT
  DY-SPLIT HL-BUILD HD-BUILD ;

\ ========================================
\ Stored block (type 0, no compression)
\ ========================================

: DFL-STORED ( -- )
  \ Align to byte boundary
  0 DFL-BREM !
  \ Read LEN (16-bit LE)
  DFL-SRC @ C@
  DFL-SRC @ 1+ C@ 8 LSHIFT OR
  \ Skip LEN + NLEN (4 bytes)
  4 DFL-SRC +!
  \ Copy LEN bytes to output
  DUP 0> IF
    0 DO
      DFL-SRC @ C@ DFL-OUT
      1 DFL-SRC +!
    LOOP
  ELSE DROP THEN ;

\ ========================================
\ Main decompressor
\ ========================================

VARIABLE DFL-BFIN

: DFL-DECOMPRESS ( src dst -- end )
  DFL-DST ! DUP DFL-DSTA !
  DFL-BINIT
  BEGIN
    DFL-BIT DFL-BFIN !
    2 DFL-BITS
    DUP 0= IF
      DROP DFL-STORED
    ELSE DUP 1 = IF
      DROP DFL-FIXED DFL-HBLOCK
    ELSE
      DROP DFL-DYNAMIC DFL-HBLOCK
    THEN THEN
    DFL-BFIN @
  UNTIL
  DFL-DST @ ;

ONLY FORTH DEFINITIONS
DECIMAL
