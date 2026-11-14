\ forth83.fth - 33 of test_forth83.py's checks, same labels
\ FORTH83 is loaded at the prompt before the run (L1 is the
\ precondition: without it ALSO FORTH83 aborts the suite).
\ Python printed with . . (top first); here values stay on the
\ stack, so expected values read bottom first.
DECIMAL
SUITE FORTH83
ALSO FORTH83
T{ K1 -1 -1 UM* -> 1 -2 }T
T{ K2 65536 65536 UM* -> 0 1 }T
T{ K3 -2 1 -1 UM/MOD -> 0 2 }T
T{ K4 7 0 2 UM/MOD -> 1 3 }T
\ LV: LEAVE (FORTH83.TXT:2749); I left on the stack, not printed
: TL0 5 0 DO I I 2 = IF LEAVE THEN LOOP ;
: TL1 5 0 DO I 2 = IF LEAVE THEN I LOOP ;
: TL2 3 0 DO 7 LEAVE 8 LOOP ;
: TL3 3 0 DO BEGIN LEAVE 1 UNTIL 9 LOOP ;
: TL4 2 0 DO 10 0 DO I 1 = IF LEAVE THEN I LOOP 100 LOOP ;
: TL5 10 0 DO I 4 = IF LEAVE THEN I 2 +LOOP ;
: TL6 10 0 DO I 3 = IF LEAVE THEN I 7 = IF LEAVE THEN
  I LOOP ;
: TL7 3 0 DO 2 0 DO LOOP I 1 = IF LEAVE THEN I LOOP ;
T{ LV0 TL0 -> 0 1 2 }T
T{ LV1 TL1 -> 0 1 }T
T{ LV2 TL2 -> 7 }T
T{ LV3 TL3 -> }T
T{ LV4 TL4 -> 0 100 0 100 }T
T{ LV5 TL5 -> 0 2 }T
T{ LV6 TL6 -> 0 1 2 }T
T{ LV7 TL7 -> 0 }T
\ LV8: LINE-START past the end stays inside the buffer. AB.CD
\ (FE-SIZE 5), ZZ. planted past the end; answer 5.
ALSO FILE-EDITOR
: T-LV8 ( -- off ) 65 FE-BUF C! 66 FE-BUF 1+ C!
  10 FE-BUF 2 + C! 67 FE-BUF 3 + C! 68 FE-BUF 4 + C!
  90 FE-BUF 5 + C! 90 FE-BUF 6 + C! 10 FE-BUF 7 + C!
  5 FE-SIZE ! 3 LINE-START 0 FE-SIZE ! ;
PREVIOUS
T{ LV8 T-LV8 -> 5 }T
T{ R1 0 NOT 5 NOT -> -1 -6 }T
T{ R2 >IN ADDR-TOIN = -> -1 }T
\ H: COUNT's address and length; ROLL; -TRAILING; PAD
CREATE CS 3 C, 65 C, 66 C, 67 C,
T{ H1 CS COUNT SWAP CS - -> 3 1 }T
: T-H3 1 2 3 4 3 ROLL 1 2 0 ROLL 1 2 3 2 ROLL ;
T{ H3 T-H3 -> 2 3 4 1 1 2 2 3 1 }T
CREATE TS 65 C, 32 C, 32 C,
: T-H4 TS 3 -TRAILING SWAP TS - TS 1+ 2 -TRAILING NIP
  TS 0 -TRAILING NIP ;
T{ H4 T-H4 -> 1 0 0 0 }T
DEFINES T{ H5 PAD HERE@ - PAD 8 ALLOT PAD SWAP - -> 100 8 }T
\ P: the bytes <# .. #> leaves, compared with T-S= (no TYPE)
VARIABLE T-SF
: T-S= ( a1 n1 a2 n2 -- f ) ROT OVER = 0= IF 2DROP DROP 0
  EXIT THEN -1 T-SF ! 0 DO OVER I + C@ OVER I + C@ <> IF
  0 T-SF ! THEN LOOP 2DROP T-SF @ ;
: P1$ S" -123" ;  : P2$ S" 0" ;  : P3$ S" FF" ;
: P4$ S" 18446744073709551615" ;  : P5$ S" 12.34" ;
T{ P1 -123 DUP ABS 0 <# #S ROT SIGN #> P1$ T-S= -> -1 }T
T{ P2 0 0 <# #S #> P2$ T-S= -> -1 }T
T{ P3 HEX FF 0 <# #S #> DECIMAL P3$ T-S= -> -1 }T
T{ P4 -1 -1 <# #S #> P4$ T-S= -> -1 }T
T{ P5 1234 0 <# # # 46 HOLD #S #> P5$ T-S= -> -1 }T
T{ P6 2 BASE ! -1 -1 <# #S #> NIP DECIMAL -> 64 }T
\ C: CONVERT
: C1$ S" x123 " ;  : C2$ S" x18446744073709551615 " ;
: C3$ S" xFF " ;
T{ C1 0 0 C1$ DROP CONVERT C@ -> 123 0 32 }T
T{ C2 0 0 C2$ DROP CONVERT DROP -> -1 -1 }T
T{ C3 HEX 0 0 C3$ DROP CONVERT DROP DECIMAL -> 255 0 }T
\ O: DOES> (from FORTH83)
: MYCONST CREATE , DOES> @ ;
42 MYCONST X42
T{ O1 X42 -> 42 }T
5 MYCONST X5
T{ O2 X42 X5 + -> 47 }T
: ARRAY CREATE CELLS ALLOT DOES> SWAP CELLS + ;
3 ARRAY AR  7 0 AR !  9 2 AR !
T{ O3 0 AR @ 2 AR @ + -> 16 }T
\ A: a child made while DV is CURRENT. FIND searches the
\ last WORD, so T-FIND parses the name itself.
: T-FIND ( "name" -- xt|0 ) WORD DROP FIND ;
VOCABULARY DV ALSO DV DEFINITIONS 11 MYCONST X11
T{ A1 X11 X42 -> 11 42 }T
ONLY FORTH DEFINITIONS ALSO FORTH83
T{ A2 T-FIND X11 ALSO DV T-FIND X11 0= PREVIOUS -> 0 0 }T
END-SUITE
ONLY FORTH DEFINITIONS
