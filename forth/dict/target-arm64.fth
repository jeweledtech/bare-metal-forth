\ ============================================
\ CATALOG: TARGET-ARM64
\ CATEGORY: system
\ PLATFORM: arm64
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ REQUIRES: X86-ASM META-COMPILER ARM64-ASM
\ ============================================
\
\ ARM64 target for metacompiler.
\ Cross-compiles ARM64 code from x86 host.
\ Structurally parallel to target-x86.fth.
\
\ Usage:
\   USING META-COMPILER
\   USING TARGET-ARM64
\   META-COMPILE-ARM64
\   META-STATUS
\
\ ============================================

VOCABULARY TARGET-ARM64
ALSO TARGET-ARM64 DEFINITIONS
ALSO META-COMPILER
ALSO ARM64-ASM
ALSO X86-ASM
HEX

\ ============================================
\ ARM64 register conventions (32-bit cells)
\ ============================================
\ X27/W27 = IP (Forth instruction pointer)
\ X26/W26 = RSP (return stack pointer)
\ X25/W25 = PSP (data stack pointer)
\ X0-X3   = working registers
\ X30     = link register (BL/BLR/RET)
\
\ NEXT: LDR W0,[X27],#4; LDR W1,[X0]; BR X1
\ PUSH: STR Wt,[X25,#-4]!
\ POP:  LDR Wt,[X25],#4
\
\ Cell size = 4 bytes (32-bit).
\ All addresses below 4GB on Pi 3B.
\ W writes auto zero-extend to X on AArch64.

\ simm9 for -4 (pre-decrement by 4)
1FC CONSTANT S9-NEG4

\ ============================================
\ Runtime emitters
\ ============================================
\ Emit ARM64 instruction sequences for the
\ Forth inner interpreter and runtime words.

\ NEXT: load XT, load code field, dispatch
: EMIT-NEXT ( -- )
    4 X27 W0 A64-LDR-POST,
    0 X0 W1 A64-LDR-UOFF,
    X1 A64-BR,
;

\ PUSH Wt to data stack
: EMIT-PUSH ( reg -- )
    S9-NEG4 X25 ROT A64-STR-PRE,
;

\ POP Wt from data stack
: EMIT-POP ( reg -- )
    4 X25 ROT A64-LDR-POST,
;

\ PUSH Wt to return stack
: EMIT-PUSHRSP ( reg -- )
    S9-NEG4 X26 ROT A64-STR-PRE,
;

\ POP Wt from return stack
: EMIT-POPRSP ( reg -- )
    4 X26 ROT A64-LDR-POST,
;

\ DOCOL: enter colon definition
\ Save IP to return stack, set IP to body
: EMIT-DOCOL ( -- )
    W27 EMIT-PUSHRSP
    4 X0 X27 A64-ADD#X,
    EMIT-NEXT
;

\ EXIT: restore IP from return stack
: EMIT-EXIT ( -- )
    W27 EMIT-POPRSP
    EMIT-NEXT
;

\ LIT: push inline literal from code stream
: EMIT-LIT ( -- )
    4 X27 W0 A64-LDR-POST,
    W0 EMIT-PUSH
    EMIT-NEXT
;

\ DOCON: push constant at [CFA+4]
: EMIT-DOCON ( -- )
    4 X0 W0 A64-LDR-UOFF,
    W0 EMIT-PUSH
    EMIT-NEXT
;

\ DOCREATE: push address of body (CFA+4)
: EMIT-DOCREATE ( -- )
    4 W0 W0 A64-ADD#,
    W0 EMIT-PUSH
    EMIT-NEXT
;

\ ============================================
\ END-CODE: shadows META-COMPILER's x86 ver
\ ============================================
: END-CODE ( -- ) EMIT-NEXT ;

\ ============================================
\ Target symbol table
\ ============================================
\ Tracks (CFA, name) for each target word.
\ Copied from target-x86.fth since these live
\ in TARGET-*, not META-COMPILER.
\ Entry: CFA(4) + len(1) + name(1F) = 24h

DECIMAL 36 CONSTANT TSYM-SZ HEX
CREATE TSYM-TBL 2000 ALLOT
VARIABLE TSYM-N

: TSYM-E ( i -- addr )
    TSYM-SZ * TSYM-TBL + ;

\ Register a target symbol
VARIABLE TR-A VARIABLE TR-L
: TSYM-REG ( cfa addr len -- )
    TR-L ! TR-A !
    TSYM-N @ TSYM-E !
    TR-L @ TSYM-N @ TSYM-E 4 + C!
    TR-A @ TSYM-N @ TSYM-E 5 +
    TR-L @ CMOVE
    1 TSYM-N +!
;

\ Compare name with symbol entry
: TSYM-EQ ( addr len i -- flag )
    TSYM-E 4 + DUP C@
    2 PICK <> IF
        DROP DROP DROP 0 EXIT
    THEN
    1+
    SWAP 0 DO
        OVER I + C@
        OVER I + C@
        <> IF
            DROP DROP 0
            UNLOOP EXIT
        THEN
    LOOP
    DROP DROP -1
;

\ Find CFA by name
: T-FIND-SYM ( addr len -- cfa | 0 )
    TSYM-N @ 0 DO
        2DUP I TSYM-EQ IF
            DROP DROP
            I TSYM-E @
            UNLOOP EXIT
        THEN
    LOOP
    DROP DROP 0
;

\ Compile target word by name
: T-COMPILE-NAME ( addr len -- )
    T-FIND-SYM
    DUP 0= IF
        DROP ." T? "
    ELSE
        T-,
    THEN
;

\ TX-CODE: like T-CODE but auto-registers
VARIABLE TX-A VARIABLE TX-L
: TX-CODE ( addr len -- )
    2DUP TX-L ! TX-A !
    T-CODE
    T-ADDR 4 -
    TX-A @ TX-L @ TSYM-REG
;

\ TX-CONST: T-CONSTANT + auto-register
VARIABLE TXC-V
: TX-CONST ( n addr len -- )
    2DUP TX-L ! TX-A !
    ROT TXC-V !
    0 T-HEADER
    DOCON-ADDR @ T-,
    TXC-V @ T-,
    T-ADDR 8 -
    TX-A @ TX-L @ TSYM-REG
;

\ TX-COLON: T-COLON + auto-register
: TX-COLON ( addr len -- )
    2DUP TX-L ! TX-A !
    T-COLON
    T-ADDR 4 -
    TX-A @ TX-L @ TSYM-REG
;

\ Reset symbol table
: TSYM-INIT 0 TSYM-N ! ;

\ ============================================
\ Build driver: MC-RUNTIMES
\ ============================================

VARIABLE BRANCH-CODE

: MC-RUNTIMES ( -- )
    \ DOCOL (raw code, no dict entry)
    T-ALIGN
    T-ADDR DOCOL-ADDR !
    EMIT-DOCOL

    \ EXIT
    S" EXIT" TX-CODE
    T-ADDR 4 - DOEXIT-ADDR !
    EMIT-EXIT

    \ LIT
    S" LIT" TX-CODE
    T-ADDR 4 - DOLIT-ADDR !
    EMIT-LIT

    \ BRANCH: IP += offset at [IP]
    \ LDR W0,[X27]; ADD X27,X27,W0,SXTW; NEXT
    S" BRANCH" TX-CODE
    T-ADDR 4 - DOBRANCH-ADDR !
    T-ADDR BRANCH-CODE !
    0 X27 W0 A64-LDR-UOFF,
    W0 X27 X27 A64-SXTW-ADD,
    END-CODE

    \ 0BRANCH: pop; if zero, do BRANCH
    \          else skip offset cell
    S" 0BRANCH" TX-CODE
    T-ADDR 4 - DO0BRANCH-ADDR !
    W0 EMIT-POP
    W0 A64-CBZ,
    \ not zero: skip offset, continue
    4 X27 X27 A64-ADD#X,
    EMIT-NEXT
    \ zero: jump to BRANCH code
    A64-CB>RES
    0 X27 W0 A64-LDR-UOFF,
    W0 X27 X27 A64-SXTW-ADD,
    END-CODE

    \ DOCON
    S" DOCON" TX-CODE
    T-ADDR DOCON-ADDR !
    EMIT-DOCON

    \ DOCREATE
    S" DOCREATE" TX-CODE
    T-ADDR DOCREATE-ADDR !
    EMIT-DOCREATE

    \ EXECUTE: pop XT, dispatch
    S" EXECUTE" TX-CODE
    W0 EMIT-POP
    0 X0 W1 A64-LDR-UOFF,
    X1 A64-BR,
;

\ ============================================
\ Build driver: MC-STACK
\ ============================================

: MC-STACK ( -- )
    S" DROP" TX-CODE
    W0 EMIT-POP END-CODE

    S" DUP" TX-CODE
    0 X25 W0 A64-LDR-UOFF,
    W0 EMIT-PUSH END-CODE

    S" SWAP" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W0 EMIT-PUSH W1 EMIT-PUSH
    END-CODE

    S" OVER" TX-CODE
    4 X25 W0 A64-LDR-UOFF,
    W0 EMIT-PUSH END-CODE

    S" ROT" TX-CODE
    W0 EMIT-POP W1 EMIT-POP W2 EMIT-POP
    W1 EMIT-PUSH W0 EMIT-PUSH
    W2 EMIT-PUSH END-CODE

    S" -ROT" TX-CODE
    W0 EMIT-POP W1 EMIT-POP W2 EMIT-POP
    W0 EMIT-PUSH W2 EMIT-PUSH
    W1 EMIT-PUSH END-CODE

    S" 2DROP" TX-CODE
    W0 EMIT-POP W0 EMIT-POP END-CODE

    S" 2DUP" TX-CODE
    0 X25 W0 A64-LDR-UOFF,
    4 X25 W1 A64-LDR-UOFF,
    W1 EMIT-PUSH W0 EMIT-PUSH
    END-CODE

    S" ?DUP" TX-CODE
    0 X25 W0 A64-LDR-UOFF,
    W0 W0 A64-CMP,
    COND-EQ A64-BCOND,
    W0 EMIT-PUSH
    A64-BC>RES
    END-CODE

    S" NIP" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W0 EMIT-PUSH END-CODE

    S" TUCK" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W0 EMIT-PUSH W1 EMIT-PUSH
    W0 EMIT-PUSH END-CODE

    \ >R
    S" >R" TX-CODE
    W0 EMIT-POP
    W0 EMIT-PUSHRSP END-CODE

    \ R>
    S" R>" TX-CODE
    W0 EMIT-POPRSP
    W0 EMIT-PUSH END-CODE

    \ R@
    S" R@" TX-CODE
    0 X26 W0 A64-LDR-UOFF,
    W0 EMIT-PUSH END-CODE

    \ RDROP
    S" RDROP" TX-CODE
    4 X26 X26 A64-ADD#X, END-CODE
;

\ ============================================
\ Build driver: MC-ARITH
\ ============================================

: MC-ARITH ( -- )
    \ +
    S" +" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W0 W1 W0 A64-ADD,
    W0 EMIT-PUSH END-CODE

    \ -  ( a b -- a-b ) pop b, pop a, a-b
    S" -" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W0 W1 W0 A64-SUB,
    W0 EMIT-PUSH END-CODE

    \ *
    S" *" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W1 W0 W0 A64-MUL,
    W0 EMIT-PUSH END-CODE

    \ 1+
    S" 1+" TX-CODE
    W0 EMIT-POP
    1 W0 W0 A64-ADD#,
    W0 EMIT-PUSH END-CODE

    \ 1-
    S" 1-" TX-CODE
    W0 EMIT-POP
    1 W0 W0 A64-SUB#,
    W0 EMIT-PUSH END-CODE

    \ 2+
    S" 2+" TX-CODE
    W0 EMIT-POP
    2 W0 W0 A64-ADD#,
    W0 EMIT-PUSH END-CODE

    \ 2-
    S" 2-" TX-CODE
    W0 EMIT-POP
    2 W0 W0 A64-SUB#,
    W0 EMIT-PUSH END-CODE

    \ NEGATE
    S" NEGATE" TX-CODE
    W0 EMIT-POP
    W0 W0 A64-NEG,
    W0 EMIT-PUSH END-CODE

    \ ABS
    S" ABS" TX-CODE
    W0 EMIT-POP
    0 W0 A64-CMP#,
    COND-GE A64-BCOND,
    W0 W0 A64-NEG,
    A64-BC>RES
    W0 EMIT-PUSH END-CODE
;

\ ============================================
\ Build driver: MC-LOGIC
\ ============================================

: MC-LOGIC ( -- )
    S" AND" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W0 W1 W0 A64-AND,
    W0 EMIT-PUSH END-CODE

    S" OR" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W0 W1 W0 A64-ORR,
    W0 EMIT-PUSH END-CODE

    S" XOR" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W0 W1 W0 A64-EOR,
    W0 EMIT-PUSH END-CODE

    S" INVERT" TX-CODE
    W0 EMIT-POP
    W0 W0 A64-MVN,
    W0 EMIT-PUSH END-CODE

    S" LSHIFT" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W0 W1 W0 A64-LSLV,
    W0 EMIT-PUSH END-CODE

    S" RSHIFT" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W0 W1 W0 A64-LSRV,
    W0 EMIT-PUSH END-CODE
;

\ ============================================
\ Build driver: MC-COMPARE
\ ============================================

: MC-COMPARE ( -- )
    \ = : Forth TRUE = -1 (all bits set)
    S" =" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W0 W1 A64-CMP,
    COND-EQ W0 A64-CSET,
    W0 W0 A64-NEG,
    W0 EMIT-PUSH END-CODE

    S" <>" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W0 W1 A64-CMP,
    COND-NE W0 A64-CSET,
    W0 W0 A64-NEG,
    W0 EMIT-PUSH END-CODE

    S" <" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W0 W1 A64-CMP,
    COND-LT W0 A64-CSET,
    W0 W0 A64-NEG,
    W0 EMIT-PUSH END-CODE

    S" >" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W0 W1 A64-CMP,
    COND-GT W0 A64-CSET,
    W0 W0 A64-NEG,
    W0 EMIT-PUSH END-CODE

    S" 0=" TX-CODE
    W0 EMIT-POP
    0 W0 A64-CMP#,
    COND-EQ W0 A64-CSET,
    W0 W0 A64-NEG,
    W0 EMIT-PUSH END-CODE

    S" 0<>" TX-CODE
    W0 EMIT-POP
    0 W0 A64-CMP#,
    COND-NE W0 A64-CSET,
    W0 W0 A64-NEG,
    W0 EMIT-PUSH END-CODE

    S" 0<" TX-CODE
    W0 EMIT-POP
    0 W0 A64-CMP#,
    COND-LT W0 A64-CSET,
    W0 W0 A64-NEG,
    W0 EMIT-PUSH END-CODE

    S" 0>" TX-CODE
    W0 EMIT-POP
    0 W0 A64-CMP#,
    COND-GT W0 A64-CSET,
    W0 W0 A64-NEG,
    W0 EMIT-PUSH END-CODE
;

\ ============================================
\ Build driver: MC-MEMORY
\ ============================================

: MC-MEMORY ( -- )
    \ @ ( addr -- val )
    S" @" TX-CODE
    W0 EMIT-POP
    0 X0 W0 A64-LDR-UOFF,
    W0 EMIT-PUSH END-CODE

    \ ! ( val addr -- )
    S" !" TX-CODE
    W1 EMIT-POP W0 EMIT-POP
    0 X1 W0 A64-STR-UOFF,
    END-CODE

    \ C@ ( addr -- byte )
    S" C@" TX-CODE
    W0 EMIT-POP
    0 X0 W0 A64-LDRB-UOFF,
    W0 EMIT-PUSH END-CODE

    \ C! ( byte addr -- )
    S" C!" TX-CODE
    W1 EMIT-POP W0 EMIT-POP
    0 X1 W0 A64-STRB-UOFF,
    END-CODE

    \ +! ( n addr -- )
    S" +!" TX-CODE
    W1 EMIT-POP W0 EMIT-POP
    0 X1 W2 A64-LDR-UOFF,
    W0 W2 W2 A64-ADD,
    0 X1 W2 A64-STR-UOFF,
    END-CODE

    \ -! ( n addr -- )
    S" -!" TX-CODE
    W1 EMIT-POP W0 EMIT-POP
    0 X1 W2 A64-LDR-UOFF,
    W0 W2 W2 A64-SUB,
    0 X1 W2 A64-STR-UOFF,
    END-CODE
;

\ ============================================
\ Build driver: MC-DIVISION
\ ============================================
\ ARM64 has SDIV — much simpler than x86.
\ Floored division: if remainder != 0 and
\ signs differ, subtract 1 from quotient.

VARIABLE FX1 VARIABLE FX2

: MC-DIVISION ( -- )
    \ / (floored division)
    S" /" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    \ W2 = W1 / W0 (truncated toward zero)
    W0 W1 W2 A64-SDIV,
    \ W3 = W2 * W0 (quotient * divisor)
    W0 W2 W3 A64-MUL,
    \ W3 = W1 - W3 (remainder)
    W3 W1 W3 A64-SUB,
    \ if remainder == 0, done
    W3 A64-CBZ, FX1 !
    \ Check signs: (rem XOR divisor) < 0?
    W0 W3 W3 A64-EOR,
    0 W3 A64-CMP#,
    COND-GE A64-BCOND, FX2 !
    \ Floor correction: quotient -= 1
    1 W2 W2 A64-SUB#,
    FX2 @ A64-BC>RES
    FX1 @ A64-CB>RES
    W2 EMIT-PUSH END-CODE

    \ MOD (floored modulo)
    S" MOD" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W0 W1 W2 A64-SDIV,
    W0 W2 W3 A64-MUL,
    W3 W1 W3 A64-SUB,
    \ if rem == 0, done
    W3 A64-CBZ, FX1 !
    \ if (rem XOR divisor) < 0, add divisor
    W0 W3 W4 A64-EOR,
    0 W4 A64-CMP#,
    COND-GE A64-BCOND, FX2 !
    W0 W3 W3 A64-ADD,
    FX2 @ A64-BC>RES
    FX1 @ A64-CB>RES
    W3 EMIT-PUSH END-CODE

    \ /MOD ( a b -- rem quot )
    S" /MOD" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W0 W1 W2 A64-SDIV,
    W0 W2 W3 A64-MUL,
    W3 W1 W3 A64-SUB,
    W3 A64-CBZ, FX1 !
    W0 W3 W4 A64-EOR,
    0 W4 A64-CMP#,
    COND-GE A64-BCOND, FX2 !
    1 W2 W2 A64-SUB#,
    W0 W3 W3 A64-ADD,
    FX2 @ A64-BC>RES
    FX1 @ A64-CB>RES
    W3 EMIT-PUSH W2 EMIT-PUSH
    END-CODE

    \ MIN
    S" MIN" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W0 W1 A64-CMP,
    COND-LT A64-BCOND, FX1 !
    W0 EMIT-PUSH END-CODE
    FX1 @ A64-BC>RES
    W1 EMIT-PUSH END-CODE

    \ MAX
    S" MAX" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W0 W1 A64-CMP,
    COND-GT A64-BCOND, FX1 !
    W0 EMIT-PUSH END-CODE
    FX1 @ A64-BC>RES
    W1 EMIT-PUSH END-CODE
;

\ ============================================
\ Build driver: MC-STACK2
\ ============================================

: MC-STACK2 ( -- )
    S" 2SWAP" TX-CODE
    W0 EMIT-POP W1 EMIT-POP
    W2 EMIT-POP W3 EMIT-POP
    W1 EMIT-PUSH W0 EMIT-PUSH
    W3 EMIT-PUSH W2 EMIT-PUSH
    END-CODE

    S" 2OVER" TX-CODE
    0C X25 W0 A64-LDR-UOFF,
    8 X25 W1 A64-LDR-UOFF,
    W1 EMIT-PUSH W0 EMIT-PUSH
    END-CODE
;

\ ============================================
\ Build driver: MC-MMIO (replaces MC-PORTIO)
\ ============================================
\ ARM64 has no IN/OUT. All I/O is MMIO.

: MC-MMIO ( -- )
    \ MMIO@ ( addr -- val )
    S" MMIO@" TX-CODE
    W0 EMIT-POP
    0 X0 W0 A64-LDR-UOFF,
    A64-DMB,
    W0 EMIT-PUSH END-CODE

    \ MMIO! ( val addr -- )
    S" MMIO!" TX-CODE
    W1 EMIT-POP W0 EMIT-POP
    A64-DMB-ST,
    0 X1 W0 A64-STR-UOFF,
    A64-DMB,
    END-CODE

    \ MMIOB@ ( addr -- byte )
    S" MMIOB@" TX-CODE
    W0 EMIT-POP
    0 X0 W0 A64-LDRB-UOFF,
    A64-DMB,
    W0 EMIT-PUSH END-CODE

    \ MMIOB! ( byte addr -- )
    S" MMIOB!" TX-CODE
    W1 EMIT-POP W0 EMIT-POP
    A64-DMB-ST,
    0 X1 W0 A64-STRB-UOFF,
    A64-DMB,
    END-CODE
;

\ ============================================
\ Build driver: MC-MEMORY2
\ ============================================

: MC-MEMORY2 ( -- )
    \ W@ ( addr -- u16 )
    S" W@" TX-CODE
    W0 EMIT-POP
    0 X0 W0 A64-LDRH-UOFF,
    W0 EMIT-PUSH END-CODE

    \ W! ( u16 addr -- )
    S" W!" TX-CODE
    W1 EMIT-POP W0 EMIT-POP
    0 X1 W0 A64-STRH-UOFF,
    END-CODE
;

\ ============================================
\ Build driver: MC-UTILITY
\ ============================================

: MC-UTILITY ( -- )
    \ SP@ — push data stack pointer
    S" SP@" TX-CODE
    X25 W0 A64-MOV,
    W0 EMIT-PUSH END-CODE

    \ >BODY ( xt -- pfa )
    S" >BODY" TX-CODE
    W0 EMIT-POP
    4 W0 W0 A64-ADD#,
    W0 EMIT-PUSH END-CODE

    \ CELLS ( n -- n*4 )
    S" CELLS" TX-CODE
    W0 EMIT-POP
    \ LSL #2
    2 W0 W0 A64-LSLV,
    W0 EMIT-PUSH END-CODE

    \ CELL+ ( a -- a+4 )
    S" CELL+" TX-CODE
    W0 EMIT-POP
    4 W0 W0 A64-ADD#,
    W0 EMIT-PUSH END-CODE

    \ Constants
    -1 S" TRUE" TX-CONST
    0 S" FALSE" TX-CONST
;

\ ============================================
\ Build driver: MC-LOOP-RT
\ ============================================

VARIABLE FX6

: MC-LOOP-RT ( -- )
    \ (DO): pop index+limit, push to rstack
    S" (DO)" TX-CODE
    T-ADDR 4 - DODO-ADDR !
    W0 EMIT-POP W1 EMIT-POP
    W1 EMIT-PUSHRSP
    W0 EMIT-PUSHRSP
    END-CODE

    \ (LOOP): inc, cmp limit, branch/exit
    S" (LOOP)" TX-CODE
    T-ADDR 4 - DOLOOP-ADDR !
    \ load index from [RSP]
    0 X26 W0 A64-LDR-UOFF,
    1 W0 W0 A64-ADD#,
    0 X26 W0 A64-STR-UOFF,
    \ load limit from [RSP+4]
    4 X26 W1 A64-LDR-UOFF,
    W1 W0 A64-CMP,
    COND-GE A64-BCOND, FX6 !
    \ not done: branch backward
    4 X27 W0 A64-LDR-POST,
    W0 X27 X27 A64-SXTW-ADD,
    EMIT-NEXT
    \ done: drop loop params, skip offset
    FX6 @ A64-BC>RES
    8 X26 X26 A64-ADD#X,
    4 X27 X27 A64-ADD#X,
    EMIT-NEXT

    \ I: push index from return stack
    S" I" TX-CODE
    0 X26 W0 A64-LDR-UOFF,
    W0 EMIT-PUSH END-CODE

    \ J: push outer loop index
    S" J" TX-CODE
    8 X26 W0 A64-LDR-UOFF,
    W0 EMIT-PUSH END-CODE

    \ UNLOOP: drop loop params
    S" UNLOOP" TX-CODE
    8 X26 X26 A64-ADD#X, END-CODE

    \ LEAVE: set index = limit
    S" LEAVE" TX-CODE
    4 X26 W0 A64-LDR-UOFF,
    0 X26 W0 A64-STR-UOFF,
    END-CODE
;

\ ============================================
\ Build driver: MC-COLON (T-COLON defs)
\ ============================================
\ Proves metacompiler builds high-level words.

: MC-COLON ( -- )
    \ : SQUARE ( n -- n*n ) DUP * ;
    S" SQUARE" TX-COLON
    S" DUP" T-COMPILE-NAME
    S" *" T-COMPILE-NAME
    T-;

    \ : CUBE ( n -- n^3 ) DUP SQUARE * ;
    S" CUBE" TX-COLON
    S" DUP" T-COMPILE-NAME
    S" SQUARE" T-COMPILE-NAME
    S" *" T-COMPILE-NAME
    T-;

    \ : NOOP ( -- ) ;
    S" NOOP" TX-COLON T-;
;

\ ============================================
\ Build driver: META-COMPILE-ARM64
\ ============================================
\ Phase B core: runtimes + primitives.
\ I/O, compiler, control flow deferred to
\ Phase C (needs ARM64 boot stub).

: META-COMPILE-ARM64 ( -- )
    META-INIT TSYM-INIT HEX
    80000 T-ORG !
    MC-RUNTIMES
    MC-LOOP-RT
    MC-STACK
    MC-ARITH
    MC-LOGIC
    MC-COMPARE
    MC-MEMORY
    MC-DIVISION
    MC-STACK2
    MC-MMIO
    MC-MEMORY2
    MC-UTILITY
    MC-COLON
    META-CHECK
    T-HERE @ T-IMAGE - T-SIZE !
    1 META-OK !
    DECIMAL
    ." ARM64 compile: "
    META-SIZE . ." bytes, "
    TSYM-N @ . ." syms" CR
;

PREVIOUS PREVIOUS PREVIOUS PREVIOUS
FORTH DEFINITIONS
DECIMAL
