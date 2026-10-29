\ ============================================
\ CATALOG: FORTH83
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ ============================================
\
\ Forth-83 Required words the kernel lacks,
\ in Forth (private TASK_FORTH83_VOCAB).
\ Renames: NOT >IN TIB. High level: COUNT
\ SPACES ROLL -TRAILING PAD <# # #S #>
\ HOLD SIGN CONVERT (on the kernel's UM*
\ and UM/MOD). And DOES>.
\ Not FORTH-83: that word claims a standard
\ system, which this kernel is not.
\
\ Usage:
\   S" FORTH83" LOAD-VOCAB  ALSO FORTH83
\
\ ============================================

VOCABULARY FORTH83
FORTH83 DEFINITIONS
DECIMAL

\ ---- Renames ----
\ 83's NOT is the one's complement.
: NOT ( w -- w' ) INVERT ;
\ ADDR-TOIN: the kernel's offset cell.
: >IN ( -- addr ) ADDR-TOIN ;
\ The terminal buffer, TIB_START. Not
\ ADDR-TIB @: under LOAD that is the block.
HEX 28100 CONSTANT TIB DECIMAL

\ ---- Strings and the stack ----
: COUNT ( addr -- addr+1 n ) DUP 1+ SWAP C@ ;
: SPACES ( n -- )
  DUP 0> IF 0 DO SPACE LOOP ELSE DROP THEN ;
: ROLL ( xn .. x0 n -- xn-1 .. x0 xn )
  DUP 0> IF SWAP >R 1- RECURSE R> SWAP
  ELSE DROP THEN ;
: -TRAILING ( addr n -- addr n' )
  BEGIN DUP IF 2DUP + 1- C@ 32 = ELSE 0 THEN
  WHILE 1- REPEAT ;
\ HERE@ is 83's HERE (the kernel's HERE is
\ the cell). Pictured output grows down
\ from PAD; 100 bytes hold 64 binary digits.
: PAD ( -- addr ) HERE@ 100 + ;

\ ---- Pictured output, unsigned double ----
VARIABLE HLD
: <# ( -- ) PAD HLD ! ;
: HOLD ( char -- ) -1 HLD +! HLD @ C! ;
: SIGN ( n -- ) 0< IF 45 HOLD THEN ;
: #> ( ud -- addr n ) 2DROP HLD @ PAD OVER - ;
\ ud / u, high cell first; r1 < u, so the
\ second UM/MOD cannot overflow.
: MU/MOD ( ud u -- r udq )
  >R 0 R@ UM/MOD R> SWAP >R UM/MOD R> ;
: DIGIT ( n -- char ) DUP 9 > IF 7 + THEN 48 + ;
: # ( ud -- ud' ) BASE @ MU/MOD ROT DIGIT HOLD ;
: #S ( ud -- 0 0 ) BEGIN # 2DUP OR 0= UNTIL ;

\ ---- CONVERT: +d1 addr1 -- +d2 addr2 ----
\ ud + n, 0 <= n < 2^31, with the carry (D+
\ is deferred to the kernel): the low cell
\ wrapped if, unsigned, it is now below n.
: UD+N ( lo hi n -- lo' hi' )
  ROT OVER + SWAP OVER DUP 0< 0= ROT ROT
  SWAP < AND IF SWAP 1+ ELSE SWAP THEN ;
\ ud * base + n: hi*base (low cell), then
\ lo*base as a double, then + n.
: D*B+ ( ud n -- ud' )
  >R BASE @ UM* DROP SWAP BASE @ UM* ROT +
  R> UD+N ;
: DIGIT? ( char -- n flag )
  48 - DUP 9 > IF 7 - DUP 10 < IF DROP -1 THEN
  THEN DUP 0< 0= OVER BASE @ < AND ;
: CONVERT ( +d1 addr1 -- +d2 addr2 )
  BEGIN 1+ DUP >R C@ DIGIT?
  WHILE D*B+ R> REPEAT DROP R> ;

\ ---- DOES> ----
\ A child's code field gets the address of
\ an 8-byte stub, CALL DODOES + 3 pad bytes,
\ laid in the parent after (DOES>); the
\ does-body follows, cell-aligned. DODOES:
\ the body is the return address + 3; push
\ the child's PFA (EAX = its CFA, from NEXT);
\ PUSHRSP ESI; ESI = body; NEXT. Assembled
\ with nasm (evidence: dodoes.asm), 19 bytes.
HEX
CREATE DODOES
5B C, 83 C, C3 C, 03 C, 8D C, 40 C, 04 C,
50 C, 83 C, ED C, 04 C, 89 C, 75 C, 00 C,
89 C, DE C, AD C, FF C, 20 C,
DECIMAL
: HEADER>CFA ( header -- cfa )
  DUP 4 + C@ 63 AND + 5 + 3 + -4 AND ;
\ R> is the stub; leaving with it popped
\ returns from the parent, as 83 requires.
: (DOES>) ( -- ) R> LATEST @ HEADER>CFA ! ;
: DOES> ( -- )
  ['] (DOES>) ,
  232 C, DODOES HERE@ 4 + - ,
  0 C, 0 C, 0 C, ; IMMEDIATE

ONLY FORTH DEFINITIONS
DECIMAL
