\ ============================================
\ CATALOG: TARGET-CORTEX-M
\ CATEGORY: system
\ PLATFORM: cortex-m
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ REQUIRES: X86-ASM META-COMPILER THUMB2-ASM
\ ============================================
\
\ Cortex-M33 target for metacompiler.
\ Cross-compiles Thumb-2 code from x86 host.
\ Structurally parallel to target-arm64.fth.
\
\ Target: MPS2-AN505 board
\   SSRAM at 0x00000000
\   UART0 at 0x40004000 (CMSDK APB)
\
\ Usage:
\   USING META-COMPILER
\   USING TARGET-CORTEX-M
\   META-COMPILE-CORTEXM
\   META-STATUS
\
\ ============================================

VOCABULARY TARGET-CORTEX-M
ALSO META-COMPILER
ALSO THUMB2-ASM
ALSO X86-ASM
ALSO TARGET-CORTEX-M DEFINITIONS
HEX

\ ============================================
\ Cortex-M33 register conventions (32-bit)
\ ============================================
\ R8  = IP (Forth instruction pointer)
\ R9  = RSP (return stack pointer)
\ R10 = PSP (data stack pointer)
\ R0-R3 = working registers
\
\ NEXT:
\   LDR R0,[R8],#4  (load XT, advance IP)
\   LDR R1,[R0]     (load code field)
\   BX R1           (dispatch via Thumb bit)
\
\ PUSH: STR Rt,[R10,#-4]!  (pre-dec)
\ POP:  LDR Rt,[R10],#4    (post-inc)
\
\ Cell size = 4 bytes (32-bit).
\ All CFA addrs must have bit 0 set
\ for Thumb mode.

\ ============================================
\ Branch fixup helpers
\ ============================================
\ T2W-BCC-FWD, returns a host-memory fixup
\ address. We must resolve it by patching
\ the 32-bit instruction at that address.

: T2-BCC-RESOLVE, ( fixup -- )
    T-HERE @ OVER - 4 -
    1 RSHIFT
    DUP 3FF AND
    SWAP 0A RSHIFT 3F AND
    10 LSHIFT OR
    OVER @
    FFFFF000 AND OR
    SWAP !
;

\ Unconditional B.W forward resolve
: T2-B-RESOLVE, ( fixup -- )
    T-HERE @ OVER - 4 -
    1 RSHIFT
    DUP 3FF AND
    SWAP 0A RSHIFT 7FF AND
    10 LSHIFT OR
    F000B800 OR
    SWAP !
;

\ Conditional backward branch (B<cc>.W)
\ target = T-HERE @ saved at loop top
\ Encoding: S:J2:J1:imm6:imm11:0 = 21-bit
: T2-BCC-BACK, ( target cc -- )
    6 LSHIFT 16 LSHIFT
    F0008000 OR SWAP
    \ byte_off = target - (HERE + 4), neg
    T-HERE @ 4 + -
    \ Extract fields from signed offset
    DUP 1 RSHIFT 7FF AND
    OVER 0C RSHIFT 3F AND
    10 LSHIFT OR
    OVER 12 RSHIFT 1 AND
    0D LSHIFT OR
    OVER 13 RSHIFT 1 AND
    0B LSHIFT OR
    SWAP 14 RSHIFT 1 AND
    1A LSHIFT OR
    OR T2-32,
;

\ ============================================
\ Runtime emitters
\ ============================================

\ NEXT: load XT, load code field, dispatch
: EMIT-NEXT ( -- )
    4 R8 R0 T2W-LDR-POST,
    0 R0 R1 T2W-LDR,
    R1 T2-BX,
;

\ PUSH Rt to data stack (pre-decrement)
: EMIT-PUSH ( reg -- )
    4 R10 ROT T2W-STR-PRE,
;

\ POP Rt from data stack (post-increment)
: EMIT-POP ( reg -- )
    4 R10 ROT T2W-LDR-POST,
;

\ PUSH Rt to return stack
: EMIT-PUSHRSP ( reg -- )
    4 R9 ROT T2W-STR-PRE,
;

\ POP Rt from return stack
: EMIT-POPRSP ( reg -- )
    4 R9 ROT T2W-LDR-POST,
;

\ DOCOL: enter colon definition
\ Save IP to RSP, set IP = CFA+4, NEXT
: EMIT-DOCOL ( -- )
    R8 EMIT-PUSHRSP
    4 R0 R8 T2W-ADD-I,
    EMIT-NEXT
;

\ EXIT: restore IP from return stack
: EMIT-EXIT ( -- )
    R8 EMIT-POPRSP
    EMIT-NEXT
;

\ LIT: push inline literal from thread
: EMIT-LIT ( -- )
    4 R8 R0 T2W-LDR-POST,
    R0 EMIT-PUSH
    EMIT-NEXT
;

\ DOCON: push constant value at [CFA+4]
: EMIT-DOCON ( -- )
    4 R0 R0 T2W-LDR,
    R0 EMIT-PUSH
    EMIT-NEXT
;

\ DOCREATE: push address of body (CFA+4)
: EMIT-DOCREATE ( -- )
    4 R0 R0 T2W-ADD-I,
    R0 EMIT-PUSH
    EMIT-NEXT
;

\ ============================================
\ END-CODE: emit NEXT for CODE words
\ ============================================
: END-CODE ( -- ) EMIT-NEXT ;

\ ============================================
\ Thumb bit helper
\ ============================================
: T-THUMB ( addr -- addr|1 ) 1 OR ;

\ ============================================
\ Target symbol table
\ ============================================
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

\ TX-CODE: T-CODE + Thumb bit + register
VARIABLE TX-A VARIABLE TX-L
: TX-CODE ( addr len -- )
    2DUP TX-L ! TX-A !
    T-CODE
    \ Patch CFA cell: set Thumb bit
    T-HERE @ 4 -
    DUP @ 1 OR SWAP !
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
    T-ADDR T-THUMB DOCOL-ADDR !
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
    S" BRANCH" TX-CODE
    T-ADDR 4 - DOBRANCH-ADDR !
    T-ADDR BRANCH-CODE !
    0 R8 R0 T2W-LDR,
    R0 R8 R8 T2W-ADD,
    END-CODE

    \ 0BRANCH: pop; if zero, do BRANCH
    \          else skip offset cell
    S" 0BRANCH" TX-CODE
    T-ADDR 4 - DO0BRANCH-ADDR !
    R0 EMIT-POP
    0 R0 T2-CMP-I,
    CC-NE T2W-BCC-FWD,
    \ zero: do BRANCH
    0 R8 R0 T2W-LDR,
    R0 R8 R8 T2W-ADD,
    EMIT-NEXT
    \ not zero: skip offset, continue
    T2-BCC-RESOLVE,
    4 R8 R8 T2W-ADD-I,
    END-CODE

    \ DOCON
    S" DOCON" TX-CODE
    T-ADDR T-THUMB DOCON-ADDR !
    EMIT-DOCON

    \ DOCREATE
    S" DOCREATE" TX-CODE
    T-ADDR T-THUMB DOCREATE-ADDR !
    EMIT-DOCREATE

    \ EXECUTE: pop XT, dispatch
    S" EXECUTE" TX-CODE
    R0 EMIT-POP
    0 R0 R1 T2W-LDR,
    R1 T2-BX,
;

\ ============================================
\ Build driver: MC-LOOP-RT
\ ============================================

: MC-LOOP-RT ( -- )
    \ (DO): pop index+limit, push to rstack
    S" (DO)" TX-CODE
    T-ADDR 4 - DODO-ADDR !
    R0 EMIT-POP R1 EMIT-POP
    R1 EMIT-PUSHRSP
    R0 EMIT-PUSHRSP
    END-CODE

    \ (LOOP): inc index, cmp limit
    S" (LOOP)" TX-CODE
    T-ADDR 4 - DOLOOP-ADDR !
    \ load index from [RSP]
    0 R9 R0 T2W-LDR,
    1 R0 R0 T2W-ADD-I,
    0 R9 R0 T2W-STR,
    \ load limit from [RSP+4]
    4 R9 R1 T2W-LDR,
    R1 R0 T2W-CMP,
    CC-GE T2W-BCC-FWD,
    \ not done: branch backward
    4 R8 R0 T2W-LDR-POST,
    R0 R8 R8 T2W-ADD,
    EMIT-NEXT
    \ done: drop loop params, skip offset
    T2-BCC-RESOLVE,
    8 R9 R9 T2W-ADD-I,
    4 R8 R8 T2W-ADD-I,
    EMIT-NEXT

    \ I: push index from return stack
    S" I" TX-CODE
    0 R9 R0 T2W-LDR,
    R0 EMIT-PUSH END-CODE

    \ J: push outer loop index
    S" J" TX-CODE
    8 R9 R0 T2W-LDR,
    R0 EMIT-PUSH END-CODE

    \ UNLOOP: drop loop params
    S" UNLOOP" TX-CODE
    8 R9 R9 T2W-ADD-I, END-CODE

    \ LEAVE: set index = limit
    S" LEAVE" TX-CODE
    4 R9 R0 T2W-LDR,
    0 R9 R0 T2W-STR,
    END-CODE
;

\ ============================================
\ Build driver: MC-STACK
\ ============================================

: MC-STACK ( -- )
    S" DROP" TX-CODE
    R0 EMIT-POP END-CODE

    S" DUP" TX-CODE
    0 R10 R0 T2W-LDR,
    R0 EMIT-PUSH END-CODE

    S" SWAP" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    R0 EMIT-PUSH R1 EMIT-PUSH
    END-CODE

    S" OVER" TX-CODE
    4 R10 R0 T2W-LDR,
    R0 EMIT-PUSH END-CODE

    S" ROT" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    R2 EMIT-POP
    R1 EMIT-PUSH R0 EMIT-PUSH
    R2 EMIT-PUSH END-CODE

    S" -ROT" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    R2 EMIT-POP
    R0 EMIT-PUSH R2 EMIT-PUSH
    R1 EMIT-PUSH END-CODE

    S" 2DROP" TX-CODE
    R0 EMIT-POP R0 EMIT-POP
    END-CODE

    S" 2DUP" TX-CODE
    0 R10 R0 T2W-LDR,
    4 R10 R1 T2W-LDR,
    R1 EMIT-PUSH R0 EMIT-PUSH
    END-CODE

    S" ?DUP" TX-CODE
    0 R10 R0 T2W-LDR,
    0 R0 T2-CMP-I,
    CC-EQ T2W-BCC-FWD,
    R0 EMIT-PUSH
    T2-BCC-RESOLVE,
    END-CODE

    S" NIP" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    R0 EMIT-PUSH END-CODE

    S" TUCK" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    R0 EMIT-PUSH R1 EMIT-PUSH
    R0 EMIT-PUSH END-CODE

    \ >R
    S" >R" TX-CODE
    R0 EMIT-POP
    R0 EMIT-PUSHRSP END-CODE

    \ R>
    S" R>" TX-CODE
    R0 EMIT-POPRSP
    R0 EMIT-PUSH END-CODE

    \ R@
    S" R@" TX-CODE
    0 R9 R0 T2W-LDR,
    R0 EMIT-PUSH END-CODE

    \ RDROP
    S" RDROP" TX-CODE
    4 R9 R9 T2W-ADD-I, END-CODE
;

\ ============================================
\ Build driver: MC-ARITH
\ ============================================

: MC-ARITH ( -- )
    \ +
    S" +" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    R0 R1 R0 T2W-ADD,
    R0 EMIT-PUSH END-CODE

    \ - ( a b -- a-b )
    S" -" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    R0 R1 R0 T2W-SUB,
    R0 EMIT-PUSH END-CODE

    \ *
    S" *" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    R1 R0 R0 T2W-MUL,
    R0 EMIT-PUSH END-CODE

    \ 1+
    S" 1+" TX-CODE
    R0 EMIT-POP
    1 R0 R0 T2W-ADD-I,
    R0 EMIT-PUSH END-CODE

    \ 1-
    S" 1-" TX-CODE
    R0 EMIT-POP
    1 R0 R0 T2W-SUB-I,
    R0 EMIT-PUSH END-CODE

    \ NEGATE: 0 - n
    S" NEGATE" TX-CODE
    R0 EMIT-POP
    0 R1 T2-MOVS-I,
    R0 R1 R0 T2W-SUB,
    R0 EMIT-PUSH END-CODE

    \ ABS
    S" ABS" TX-CODE
    R0 EMIT-POP
    0 R0 T2-CMP-I,
    CC-GE T2W-BCC-FWD,
    0 R1 T2-MOVS-I,
    R0 R1 R0 T2W-SUB,
    T2-BCC-RESOLVE,
    R0 EMIT-PUSH END-CODE
;

\ ============================================
\ Build driver: MC-LOGIC
\ ============================================

: MC-LOGIC ( -- )
    S" AND" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    R0 R1 R0 T2W-AND,
    R0 EMIT-PUSH END-CODE

    S" OR" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    R0 R1 R0 T2W-ORR,
    R0 EMIT-PUSH END-CODE

    S" XOR" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    R0 R1 R0 T2W-EOR,
    R0 EMIT-PUSH END-CODE

    S" INVERT" TX-CODE
    R0 EMIT-POP
    R0 R0 T2-MVNS,
    R0 EMIT-PUSH END-CODE

    S" LSHIFT" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    R0 R1 T2-LSLS,
    R1 EMIT-PUSH END-CODE

    S" RSHIFT" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    R0 R1 T2-LSRS,
    R1 EMIT-PUSH END-CODE
;

\ ============================================
\ Build driver: MC-COMPARE
\ ============================================
\ Thumb-2 has no CSET. Use conditional
\ branch to skip over the TRUE case.

: EMIT-CMP-TRUE ( cc -- )
    T2W-BCC-FWD,
    \ condition NOT met: push FALSE
    0 R0 T2-MOVS-I,
    T2W-B-FWD,
    SWAP T2-BCC-RESOLVE,
    \ condition met: push TRUE (-1)
    0 R0 T2-MOVS-I,
    R0 R0 T2-MVNS,
    T2-B-RESOLVE,
;

: MC-COMPARE ( -- )
    S" =" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    R0 R1 T2W-CMP,
    CC-EQ EMIT-CMP-TRUE
    R0 EMIT-PUSH END-CODE

    S" <>" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    R0 R1 T2W-CMP,
    CC-NE EMIT-CMP-TRUE
    R0 EMIT-PUSH END-CODE

    S" <" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    R0 R1 T2W-CMP,
    CC-LT EMIT-CMP-TRUE
    R0 EMIT-PUSH END-CODE

    S" >" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    R0 R1 T2W-CMP,
    CC-GT EMIT-CMP-TRUE
    R0 EMIT-PUSH END-CODE

    S" 0=" TX-CODE
    R0 EMIT-POP
    0 R0 T2-CMP-I,
    CC-EQ EMIT-CMP-TRUE
    R0 EMIT-PUSH END-CODE

    S" 0<>" TX-CODE
    R0 EMIT-POP
    0 R0 T2-CMP-I,
    CC-NE EMIT-CMP-TRUE
    R0 EMIT-PUSH END-CODE

    S" 0<" TX-CODE
    R0 EMIT-POP
    0 R0 T2-CMP-I,
    CC-LT EMIT-CMP-TRUE
    R0 EMIT-PUSH END-CODE

    S" 0>" TX-CODE
    R0 EMIT-POP
    0 R0 T2-CMP-I,
    CC-GT EMIT-CMP-TRUE
    R0 EMIT-PUSH END-CODE
;

\ ============================================
\ Build driver: MC-MEMORY
\ ============================================

: MC-MEMORY ( -- )
    \ @ ( addr -- val )
    S" @" TX-CODE
    R0 EMIT-POP
    0 R0 R0 T2W-LDR,
    R0 EMIT-PUSH END-CODE

    \ ! ( val addr -- )
    S" !" TX-CODE
    R1 EMIT-POP R0 EMIT-POP
    0 R1 R0 T2W-STR,
    END-CODE

    \ C@ ( addr -- byte )
    S" C@" TX-CODE
    R0 EMIT-POP
    0 R0 R0 T2W-LDRB,
    R0 EMIT-PUSH END-CODE

    \ C! ( byte addr -- )
    S" C!" TX-CODE
    R1 EMIT-POP R0 EMIT-POP
    0 R1 R0 T2W-STRB,
    END-CODE

    \ +! ( n addr -- )
    S" +!" TX-CODE
    R1 EMIT-POP R0 EMIT-POP
    0 R1 R2 T2W-LDR,
    R0 R2 R2 T2W-ADD,
    0 R1 R2 T2W-STR,
    END-CODE
;

\ ============================================
\ Build driver: MC-DIVISION
\ ============================================
\ Cortex-M33 has SDIV. Floored division.

VARIABLE FX1 VARIABLE FX2

: MC-DIVISION ( -- )
    \ / (floored division)
    S" /" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    \ R2 = R1 / R0 (truncated)
    R0 R1 R2 T2W-SDIV,
    \ R3 = R2 * R0
    R0 R2 R3 T2W-MUL,
    \ R3 = R1 - R3 (remainder)
    R3 R1 R3 T2W-SUB,
    \ if remainder == 0, done
    0 R3 T2-CMP-I,
    CC-EQ T2W-BCC-FWD, FX1 !
    \ (rem XOR divisor) < 0 ?
    R0 R3 R3 T2W-EOR,
    0 R3 T2-CMP-I,
    CC-GE T2W-BCC-FWD, FX2 !
    \ Floor: quotient -= 1
    1 R2 R2 T2W-SUB-I,
    FX2 @ T2-BCC-RESOLVE,
    FX1 @ T2-BCC-RESOLVE,
    R2 EMIT-PUSH END-CODE

    \ MOD (floored modulo)
    S" MOD" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    R0 R1 R2 T2W-SDIV,
    R0 R2 R3 T2W-MUL,
    R3 R1 R3 T2W-SUB,
    0 R3 T2-CMP-I,
    CC-EQ T2W-BCC-FWD, FX1 !
    R0 R3 R4 T2W-EOR,
    0 R4 T2-CMP-I,
    CC-GE T2W-BCC-FWD, FX2 !
    R0 R3 R3 T2W-ADD,
    FX2 @ T2-BCC-RESOLVE,
    FX1 @ T2-BCC-RESOLVE,
    R3 EMIT-PUSH END-CODE

    \ /MOD ( a b -- rem quot )
    S" /MOD" TX-CODE
    R0 EMIT-POP R1 EMIT-POP
    R0 R1 R2 T2W-SDIV,
    R0 R2 R3 T2W-MUL,
    R3 R1 R3 T2W-SUB,
    0 R3 T2-CMP-I,
    CC-EQ T2W-BCC-FWD, FX1 !
    R0 R3 R4 T2W-EOR,
    0 R4 T2-CMP-I,
    CC-GE T2W-BCC-FWD, FX2 !
    1 R2 R2 T2W-SUB-I,
    R0 R3 R3 T2W-ADD,
    FX2 @ T2-BCC-RESOLVE,
    FX1 @ T2-BCC-RESOLVE,
    R3 EMIT-PUSH R2 EMIT-PUSH
    END-CODE
;

\ ============================================
\ Build driver: MC-STACK2
\ ============================================

: MC-STACK2 ( -- )
    \ DEPTH: push PSP value
    S" DEPTH" TX-CODE
    R10 R0 T2-MOV,
    R0 EMIT-PUSH END-CODE

    \ PICK ( ... n -- ... xn )
    S" PICK" TX-CODE
    R0 EMIT-POP
    \ addr = PSP + n*4
    R0 R0 R0 T2W-ADD,
    R0 R0 R0 T2W-ADD,
    R0 R10 R0 T2W-ADD,
    0 R0 R0 T2W-LDR,
    R0 EMIT-PUSH END-CODE
;

\ ============================================
\ Build driver: MC-MMIO
\ ============================================
\ Cortex-M: all I/O is memory-mapped.

: MC-MMIO ( -- )
    \ MMIO@ ( addr -- val )
    S" MMIO@" TX-CODE
    R0 EMIT-POP
    0 R0 R0 T2W-LDR,
    T2-DMB,
    R0 EMIT-PUSH END-CODE

    \ MMIO! ( val addr -- )
    S" MMIO!" TX-CODE
    R1 EMIT-POP R0 EMIT-POP
    T2-DMB-ST,
    0 R1 R0 T2W-STR,
    T2-DMB,
    END-CODE
;

\ ============================================
\ Build driver: MC-MEMORY2
\ ============================================

VARIABLE CM-FX

: MC-MEMORY2 ( -- )
    \ FILL ( addr len byte -- )
    S" FILL" TX-CODE
    R2 EMIT-POP R1 EMIT-POP
    R0 EMIT-POP
    0 R1 T2-CMP-I,
    CC-EQ T2W-BCC-FWD, CM-FX !
    T-HERE @
    0 R0 R2 T2W-STRB,
    1 R0 R0 T2W-ADD-I,
    1 R1 R1 T2W-SUB-I,
    CC-NE T2-BCC-BACK,
    CM-FX @ T2-BCC-RESOLVE,
    END-CODE

    \ CMOVE ( src dst n -- )
    S" CMOVE" TX-CODE
    R2 EMIT-POP R1 EMIT-POP
    R0 EMIT-POP
    0 R2 T2-CMP-I,
    CC-EQ T2W-BCC-FWD, CM-FX !
    T-HERE @
    0 R0 R3 T2W-LDRB,
    0 R1 R3 T2W-STRB,
    1 R0 R0 T2W-ADD-I,
    1 R1 R1 T2W-ADD-I,
    1 R2 R2 T2W-SUB-I,
    CC-NE T2-BCC-BACK,
    CM-FX @ T2-BCC-RESOLVE,
    END-CODE

    \ ALIGN ( -- ) align HERE to 4
    S" ALIGN" TX-COLON
    T-BEGIN
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 3 T-,
    S" AND" T-COMPILE-NAME
    T-WHILE
    S" LIT" T-COMPILE-NAME 0 T-,
    S" C," T-COMPILE-NAME
    T-REPEAT
    T-;

    \ ALIGNED ( addr -- addr' )
    S" ALIGNED" TX-COLON
    S" LIT" T-COMPILE-NAME 3 T-,
    S" +" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME -4 T-,
    S" AND" T-COMPILE-NAME
    T-;
;

\ ============================================
\ Build driver: MC-IO-CORTEXM
\ ============================================
\ CMSDK APB UART at 0x40004000
\ DATA +0, STATE +4, CTRL +8
\ STATE bit0=TX full, bit1=RX full

: MC-IO-CORTEXM ( -- )
    \ KEY ( -- char )
    \ Poll STATE bit1 (RX has data)
    S" KEY" TX-CODE
    40004000 R3 T2-MOV32,
    2 R1 T2-MOVS-I,
    T-HERE @
    4 R3 R0 T2W-LDR,
    R1 R0 T2-ANDS,
    CC-EQ T2-BCC-BACK,
    0 R3 R0 T2W-LDR,
    FF R1 T2-MOVS-I,
    R1 R0 T2-ANDS,
    R0 EMIT-PUSH
    END-CODE

    \ EMIT ( char -- )
    \ Poll STATE bit0 (TX full)
    S" EMIT" TX-CODE
    R0 EMIT-POP
    40004000 R3 T2-MOV32,
    1 R1 T2-MOVS-I,
    T-HERE @
    4 R3 R2 T2W-LDR,
    R1 R2 T2-ANDS,
    CC-NE T2-BCC-BACK,
    0 R3 R0 T2W-STR,
    END-CODE

    \ CR ( -- )
    S" CR" TX-COLON
    S" LIT" T-COMPILE-NAME 0D T-,
    S" EMIT" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 0A T-,
    S" EMIT" T-COMPILE-NAME
    T-;

    \ SPACE ( -- )
    S" SPACE" TX-COLON
    S" LIT" T-COMPILE-NAME 20 T-,
    S" EMIT" T-COMPILE-NAME
    T-;

    \ TYPE ( addr len -- )
    S" TYPE" TX-COLON
    T-BEGIN
    S" DUP" T-COMPILE-NAME
    S" 0>" T-COMPILE-NAME
    T-WHILE
    S" OVER" T-COMPILE-NAME
    S" C@" T-COMPILE-NAME
    S" EMIT" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" 1+" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" 1-" T-COMPILE-NAME
    T-REPEAT
    S" 2DROP" T-COMPILE-NAME
    T-;

    \ BL -- blank space constant
    20 S" BL" TX-CONST

    \ SPACES ( n -- )
    S" SPACES" TX-COLON
    T-BEGIN
    S" DUP" T-COMPILE-NAME
    S" 0>" T-COMPILE-NAME
    T-WHILE
    S" SPACE" T-COMPILE-NAME
    S" 1-" T-COMPILE-NAME
    T-REPEAT
    S" DROP" T-COMPILE-NAME
    T-;
;

\ ============================================
\ Build driver: MC-SYSVAR-CORTEXM
\ ============================================
\ System variables at 0x20000000 (SRAM).

: MC-SYSVAR-CORTEXM ( -- )
    20000000 S" STATE" TX-CONST
    20000004 S" HERE" TX-CONST
    20000008 S" LATEST" TX-CONST
    2000000C S" BASE" TX-CONST
    20000010 S" >IN" TX-CONST
    20000014 S" #TIB" TX-CONST
    20000100 S" TIB-BUF" TX-CONST
    20000200 S" WORD-BUF" TX-CONST
;

\ ============================================
\ Build driver: MC-DISPLAY-CORTEXM
\ ============================================

: MC-DISPLAY-CORTEXM ( -- )
    \ (DIGIT) ( n -- ) print single digit
    S" (DIGIT)" TX-COLON
    S" DUP" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 0A T-,
    S" <" T-COMPILE-NAME
    T-IF
    S" LIT" T-COMPILE-NAME 30 T-,
    S" +" T-COMPILE-NAME
    T-ELSE
    S" LIT" T-COMPILE-NAME 37 T-,
    S" +" T-COMPILE-NAME
    T-THEN
    S" EMIT" T-COMPILE-NAME
    T-;

    \ (DOTR) ( u -- ) recursive print
    S" (DOTR)" TX-COLON
    S" BASE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" /MOD" T-COMPILE-NAME
    S" ?DUP" T-COMPILE-NAME
    T-IF
    S" (DOTR)" T-COMPILE-NAME
    T-THEN
    S" (DIGIT)" T-COMPILE-NAME
    T-;

    \ . ( n -- ) print signed number
    S" ." TX-COLON
    S" DUP" T-COMPILE-NAME
    S" 0<" T-COMPILE-NAME
    T-IF
    S" LIT" T-COMPILE-NAME 2D T-,
    S" EMIT" T-COMPILE-NAME
    S" NEGATE" T-COMPILE-NAME
    T-THEN
    S" (DOTR)" T-COMPILE-NAME
    S" SPACE" T-COMPILE-NAME
    T-;

    \ .S ( -- ) print stack marker
    S" .S" TX-COLON
    S" LIT" T-COMPILE-NAME 3C T-,
    S" EMIT" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 3E T-,
    S" EMIT" T-COMPILE-NAME
    S" SPACE" T-COMPILE-NAME
    T-;

    \ HEX ( -- )
    S" HEX" TX-COLON
    S" LIT" T-COMPILE-NAME 10 T-,
    S" BASE" T-COMPILE-NAME
    S" !" T-COMPILE-NAME
    T-;

    \ DECIMAL ( -- )
    S" DECIMAL" TX-COLON
    S" LIT" T-COMPILE-NAME 0A T-,
    S" BASE" T-COMPILE-NAME
    S" !" T-COMPILE-NAME
    T-;

    \ WORDS ( -- ) walk dict, print names
    S" WORDS" TX-COLON
    S" LATEST" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    T-BEGIN
    S" DUP" T-COMPILE-NAME
    T-WHILE
    S" DUP" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 4 T-,
    S" +" T-COMPILE-NAME
    S" DUP" T-COMPILE-NAME
    S" C@" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 7F T-,
    S" AND" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" 1+" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" TYPE" T-COMPILE-NAME
    S" SPACE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    T-REPEAT
    S" DROP" T-COMPILE-NAME
    S" CR" T-COMPILE-NAME
    T-;
;

\ ============================================
\ Build driver: MC-COMPILER-CORTEXM
\ ============================================

: MC-COMPILER-CORTEXM ( -- )
    \ [ -- switch to interpret mode
    S" [" TX-COLON
    S" LIT" T-COMPILE-NAME 0 T-,
    S" STATE" T-COMPILE-NAME
    S" !" T-COMPILE-NAME
    T-;
    T-IMMEDIATE

    \ ] -- switch to compile mode
    S" ]" TX-COLON
    S" LIT" T-COMPILE-NAME -1 T-,
    S" STATE" T-COMPILE-NAME
    S" !" T-COMPILE-NAME
    T-;

    \ Runtime CFA addresses as constants
    DOBRANCH-ADDR @
        S" 'BRANCH" TX-CONST
    DO0BRANCH-ADDR @
        S" '0BRANCH" TX-CONST
    DOLIT-ADDR @
        S" 'LIT" TX-CONST
    DOEXIT-ADDR @
        S" 'EXIT" TX-CONST
    DOCOL-ADDR @
        S" 'DOCOL" TX-CONST
    DOCON-ADDR @
        S" 'DOCON" TX-CONST
    DOCREATE-ADDR @
        S" 'DOCREATE" TX-CONST
    DODO-ADDR @
        S" '(DO)" TX-CONST
    DOLOOP-ADDR @
        S" '(LOOP)" TX-CONST

    \ LITERAL -- compile inline literal
    S" LITERAL" TX-COLON
    S" 'LIT" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    T-;
    T-IMMEDIATE

    \ CREATE ( -- ) parse name, header
    S" CREATE" TX-COLON
    S" WORD" T-COMPILE-NAME
    S" DUP" T-COMPILE-NAME
    S" 0=" T-COMPILE-NAME
    T-IF
    S" 2DROP" T-COMPILE-NAME
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" LATEST" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 4 T-,
    S" -" T-COMPILE-NAME
    S" LATEST" T-COMPILE-NAME
    S" !" T-COMPILE-NAME
    S" DUP" T-COMPILE-NAME
    S" C," T-COMPILE-NAME
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" CMOVE" T-COMPILE-NAME
    S" ALIGN" T-COMPILE-NAME
    S" 'DOCREATE" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    T-;

    \ : -- start colon definition
    S" :" TX-COLON
    S" WORD" T-COMPILE-NAME
    S" DUP" T-COMPILE-NAME
    S" 0=" T-COMPILE-NAME
    T-IF
    S" 2DROP" T-COMPILE-NAME
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" LATEST" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 4 T-,
    S" -" T-COMPILE-NAME
    S" LATEST" T-COMPILE-NAME
    S" !" T-COMPILE-NAME
    S" DUP" T-COMPILE-NAME
    S" C," T-COMPILE-NAME
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" CMOVE" T-COMPILE-NAME
    S" ALIGN" T-COMPILE-NAME
    S" 'DOCOL" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    S" ]" T-COMPILE-NAME
    T-;

    \ ; -- end colon definition
    S" ;" TX-COLON
    S" 'EXIT" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    S" [" T-COMPILE-NAME
    T-;
    T-IMMEDIATE

    \ IMMEDIATE -- set flag on latest
    S" IMMEDIATE" TX-COLON
    S" LATEST" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 4 T-,
    S" +" T-COMPILE-NAME
    S" DUP" T-COMPILE-NAME
    S" C@" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 80 T-,
    S" OR" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" C!" T-COMPILE-NAME
    T-;

    \ VARIABLE -- CREATE + allot cell
    S" VARIABLE" TX-COLON
    S" CREATE" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 0 T-,
    S" ," T-COMPILE-NAME
    T-;

    \ CONSTANT ( n -- )
    S" CONSTANT" TX-COLON
    S" WORD" T-COMPILE-NAME
    S" DUP" T-COMPILE-NAME
    S" 0=" T-COMPILE-NAME
    T-IF
    S" 2DROP" T-COMPILE-NAME
    S" DROP" T-COMPILE-NAME
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" LATEST" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 4 T-,
    S" -" T-COMPILE-NAME
    S" LATEST" T-COMPILE-NAME
    S" !" T-COMPILE-NAME
    S" DUP" T-COMPILE-NAME
    S" C," T-COMPILE-NAME
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" CMOVE" T-COMPILE-NAME
    S" ALIGN" T-COMPILE-NAME
    S" 'DOCON" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    T-;
;

\ ============================================
\ MC-CONTROLFLOW-CORTEXM
\ ============================================

: MC-CONTROLFLOW-CORTEXM ( -- )
    \ IF -- compile 0BRANCH + placeholder
    S" IF" TX-COLON
    S" '0BRANCH" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 0 T-,
    S" ," T-COMPILE-NAME
    T-;
    T-IMMEDIATE

    \ THEN -- patch IF/ELSE placeholder
    S" THEN" TX-COLON
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" OVER" T-COMPILE-NAME
    S" -" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" !" T-COMPILE-NAME
    T-;
    T-IMMEDIATE

    \ ELSE -- BRANCH + patch IF
    S" ELSE" TX-COLON
    S" 'BRANCH" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 0 T-,
    S" ," T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" OVER" T-COMPILE-NAME
    S" -" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" !" T-COMPILE-NAME
    T-;
    T-IMMEDIATE

    \ BEGIN -- push HERE
    S" BEGIN" TX-COLON
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    T-;
    T-IMMEDIATE

    \ UNTIL -- 0BRANCH backward
    S" UNTIL" TX-COLON
    S" '0BRANCH" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" -" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    T-;
    T-IMMEDIATE

    \ AGAIN -- BRANCH backward
    S" AGAIN" TX-COLON
    S" 'BRANCH" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" -" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    T-;
    T-IMMEDIATE

    \ WHILE -- like IF, rearrange
    S" WHILE" TX-COLON
    S" '0BRANCH" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 0 T-,
    S" ," T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    T-;
    T-IMMEDIATE

    \ REPEAT -- AGAIN + patch WHILE
    S" REPEAT" TX-COLON
    S" 'BRANCH" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" -" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" OVER" T-COMPILE-NAME
    S" -" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" !" T-COMPILE-NAME
    T-;
    T-IMMEDIATE

    \ DO -- compile (DO), push HERE
    S" DO" TX-COLON
    S" '(DO)" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    T-;
    T-IMMEDIATE

    \ LOOP -- compile (LOOP) + offset
    S" LOOP" TX-COLON
    S" '(LOOP)" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" -" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 4 T-,
    S" -" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    T-;
    T-IMMEDIATE

    \ +LOOP -- same structure as LOOP
    S" +LOOP" TX-COLON
    S" '(LOOP)" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" -" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 4 T-,
    S" -" T-COMPILE-NAME
    S" ," T-COMPILE-NAME
    T-;
    T-IMMEDIATE
;

\ ============================================
\ MC-DICT-CORTEXM: dict + string helpers
\ ============================================

: MC-DICT-CORTEXM ( -- )
    \ , ( n -- ) store cell, advance HERE
    S" ," TX-COLON
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" !" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 4 T-,
    S" HERE" T-COMPILE-NAME
    S" +!" T-COMPILE-NAME
    T-;

    \ C, ( c -- )
    S" C," TX-COLON
    S" HERE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" C!" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 1 T-,
    S" HERE" T-COMPILE-NAME
    S" +!" T-COMPILE-NAME
    T-;

    \ ALLOT ( n -- )
    S" ALLOT" TX-COLON
    S" HERE" T-COMPILE-NAME
    S" +!" T-COMPILE-NAME
    T-;

    \ TOUPPER ( c -- c' )
    S" TOUPPER" TX-COLON
    S" DUP" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 61 T-,
    S" <" T-COMPILE-NAME
    T-IF
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" DUP" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 7A T-,
    S" >" T-COMPILE-NAME
    T-IF
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" LIT" T-COMPILE-NAME 20 T-,
    S" -" T-COMPILE-NAME
    T-;

    \ (SKIP) -- skip spaces in TIB
    S" (SKIP)" TX-COLON
    T-BEGIN
    S" >IN" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" #TIB" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" >=" T-COMPILE-NAME
    T-IF
    S" FALSE" T-COMPILE-NAME
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" TIB-BUF" T-COMPILE-NAME
    S" >IN" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" +" T-COMPILE-NAME
    S" C@" T-COMPILE-NAME
    S" BL" T-COMPILE-NAME
    S" >" T-COMPILE-NAME
    T-IF
    S" TRUE" T-COMPILE-NAME
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" LIT" T-COMPILE-NAME 1 T-,
    S" >IN" T-COMPILE-NAME
    S" +!" T-COMPILE-NAME
    T-AGAIN
    T-;

    \ WORD ( -- addr len )
    S" WORD" TX-COLON
    S" (SKIP)" T-COMPILE-NAME
    S" 0=" T-COMPILE-NAME
    T-IF
    S" WORD-BUF" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 0 T-,
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" LIT" T-COMPILE-NAME 0 T-,
    T-BEGIN
    S" >IN" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" #TIB" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" <" T-COMPILE-NAME
    T-WHILE
    S" TIB-BUF" T-COMPILE-NAME
    S" >IN" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" +" T-COMPILE-NAME
    S" C@" T-COMPILE-NAME
    S" DUP" T-COMPILE-NAME
    S" BL" T-COMPILE-NAME
    S" <=" T-COMPILE-NAME
    T-IF
    S" DROP" T-COMPILE-NAME
    S" WORD-BUF" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" TOUPPER" T-COMPILE-NAME
    S" OVER" T-COMPILE-NAME
    S" WORD-BUF" T-COMPILE-NAME
    S" +" T-COMPILE-NAME
    S" C!" T-COMPILE-NAME
    S" 1+" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 1 T-,
    S" >IN" T-COMPILE-NAME
    S" +!" T-COMPILE-NAME
    T-REPEAT
    S" WORD-BUF" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    T-;

    \ NAME= ( addr len entry -- flag )
    S" NAME=" TX-COLON
    S" LIT" T-COMPILE-NAME 4 T-,
    S" +" T-COMPILE-NAME
    S" DUP" T-COMPILE-NAME
    S" C@" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 7F T-,
    S" AND" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 2 T-,
    S" PICK" T-COMPILE-NAME
    S" <>" T-COMPILE-NAME
    T-IF
    S" DROP" T-COMPILE-NAME
    S" 2DROP" T-COMPILE-NAME
    S" FALSE" T-COMPILE-NAME
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" 1+" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 0 T-,
    T-DO
    S" OVER" T-COMPILE-NAME
    S" I" T-COMPILE-NAME
    S" +" T-COMPILE-NAME
    S" C@" T-COMPILE-NAME
    S" OVER" T-COMPILE-NAME
    S" I" T-COMPILE-NAME
    S" +" T-COMPILE-NAME
    S" C@" T-COMPILE-NAME
    S" <>" T-COMPILE-NAME
    T-IF
    S" 2DROP" T-COMPILE-NAME
    S" FALSE" T-COMPILE-NAME
    S" UNLOOP" T-COMPILE-NAME
    S" EXIT" T-COMPILE-NAME
    T-THEN
    T-LOOP
    S" 2DROP" T-COMPILE-NAME
    S" TRUE" T-COMPILE-NAME
    T-;

    \ >CFA ( entry -- cfa )
    S" >CFA" TX-COLON
    S" DUP" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 4 T-,
    S" +" T-COMPILE-NAME
    S" C@" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 7F T-,
    S" AND" T-COMPILE-NAME
    S" +" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 5 T-,
    S" +" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 3 T-,
    S" +" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME -4 T-,
    S" AND" T-COMPILE-NAME
    T-;

    \ FIND ( a l -- xt flg T | a l F )
    S" FIND" TX-COLON
    S" LATEST" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    T-BEGIN
    S" DUP" T-COMPILE-NAME
    T-WHILE
    S" >R" T-COMPILE-NAME
    S" 2DUP" T-COMPILE-NAME
    S" R@" T-COMPILE-NAME
    S" NAME=" T-COMPILE-NAME
    T-IF
    S" 2DROP" T-COMPILE-NAME
    S" R>" T-COMPILE-NAME
    S" DUP" T-COMPILE-NAME
    S" >CFA" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 4 T-,
    S" +" T-COMPILE-NAME
    S" C@" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 80 T-,
    S" AND" T-COMPILE-NAME
    T-IF
    S" LIT" T-COMPILE-NAME -1 T-,
    T-ELSE
    S" LIT" T-COMPILE-NAME 1 T-,
    T-THEN
    S" TRUE" T-COMPILE-NAME
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" R>" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    T-REPEAT
    S" DROP" T-COMPILE-NAME
    S" FALSE" T-COMPILE-NAME
    T-;

    \ DIGIT ( c -- n T | F )
    S" DIGIT" TX-COLON
    S" DUP" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 30 T-,
    S" <" T-COMPILE-NAME
    T-IF
    S" DROP" T-COMPILE-NAME
    S" FALSE" T-COMPILE-NAME
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" DUP" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 39 T-,
    S" <=" T-COMPILE-NAME
    T-IF
    S" LIT" T-COMPILE-NAME 30 T-,
    S" -" T-COMPILE-NAME
    S" DUP" T-COMPILE-NAME
    S" BASE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" <" T-COMPILE-NAME
    T-IF
    S" TRUE" T-COMPILE-NAME
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" DROP" T-COMPILE-NAME
    S" FALSE" T-COMPILE-NAME
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" DUP" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 41 T-,
    S" <" T-COMPILE-NAME
    T-IF
    S" DROP" T-COMPILE-NAME
    S" FALSE" T-COMPILE-NAME
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" LIT" T-COMPILE-NAME 41 T-,
    S" -" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 0A T-,
    S" +" T-COMPILE-NAME
    S" DUP" T-COMPILE-NAME
    S" BASE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" <" T-COMPILE-NAME
    T-IF
    S" TRUE" T-COMPILE-NAME
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" DROP" T-COMPILE-NAME
    S" FALSE" T-COMPILE-NAME
    T-;

    \ NUMBER ( addr len -- n T | F )
    S" NUMBER" TX-COLON
    S" DUP" T-COMPILE-NAME
    S" 0=" T-COMPILE-NAME
    T-IF
    S" 2DROP" T-COMPILE-NAME
    S" FALSE" T-COMPILE-NAME
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" LIT" T-COMPILE-NAME 0 T-,
    S" >R" T-COMPILE-NAME
    S" OVER" T-COMPILE-NAME
    S" C@" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 2D T-,
    S" =" T-COMPILE-NAME
    T-IF
    S" LIT" T-COMPILE-NAME 1 T-,
    S" -" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" 1+" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" RDROP" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 1 T-,
    S" >R" T-COMPILE-NAME
    T-THEN
    S" DUP" T-COMPILE-NAME
    S" 0=" T-COMPILE-NAME
    T-IF
    S" 2DROP" T-COMPILE-NAME
    S" RDROP" T-COMPILE-NAME
    S" FALSE" T-COMPILE-NAME
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" LIT" T-COMPILE-NAME 0 T-,
    S" -ROT" T-COMPILE-NAME
    T-BEGIN
    S" DUP" T-COMPILE-NAME
    S" 0>" T-COMPILE-NAME
    T-WHILE
    S" OVER" T-COMPILE-NAME
    S" C@" T-COMPILE-NAME
    S" DIGIT" T-COMPILE-NAME
    S" 0=" T-COMPILE-NAME
    T-IF
    S" 2DROP" T-COMPILE-NAME
    S" DROP" T-COMPILE-NAME
    S" RDROP" T-COMPILE-NAME
    S" FALSE" T-COMPILE-NAME
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" ROT" T-COMPILE-NAME
    S" BASE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" *" T-COMPILE-NAME
    S" +" T-COMPILE-NAME
    S" -ROT" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" 1+" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" 1-" T-COMPILE-NAME
    T-REPEAT
    S" 2DROP" T-COMPILE-NAME
    S" R>" T-COMPILE-NAME
    T-IF
    S" NEGATE" T-COMPILE-NAME
    T-THEN
    S" TRUE" T-COMPILE-NAME
    T-;

    \ >= and <= as colon defs
    S" >=" TX-COLON
    S" <" T-COMPILE-NAME
    S" 0=" T-COMPILE-NAME
    T-;

    S" <=" TX-COLON
    S" >" T-COMPILE-NAME
    S" 0=" T-COMPILE-NAME
    T-;

    \ Constants
    -1 S" TRUE" TX-CONST
    0 S" FALSE" TX-CONST
;

\ ============================================
\ MC-INTERPRET-CORTEXM
\ ============================================

: MC-INTERPRET-CORTEXM ( -- )
    \ READ-LINE ( -- )
    S" READ-LINE" TX-COLON
    S" LIT" T-COMPILE-NAME 0 T-,
    T-BEGIN
    S" KEY" T-COMPILE-NAME
    S" DUP" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 0D T-,
    S" =" T-COMPILE-NAME
    S" OVER" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 0A T-,
    S" =" T-COMPILE-NAME
    S" OR" T-COMPILE-NAME
    T-IF
    S" DROP" T-COMPILE-NAME
    S" #TIB" T-COMPILE-NAME
    S" !" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 0 T-,
    S" >IN" T-COMPILE-NAME
    S" !" T-COMPILE-NAME
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" DUP" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 8 T-,
    S" =" T-COMPILE-NAME
    S" OVER" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 7F T-,
    S" =" T-COMPILE-NAME
    S" OR" T-COMPILE-NAME
    T-IF
    S" DROP" T-COMPILE-NAME
    S" DUP" T-COMPILE-NAME
    S" 0>" T-COMPILE-NAME
    T-IF
    S" 1-" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 8 T-,
    S" EMIT" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 20 T-,
    S" EMIT" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 8 T-,
    S" EMIT" T-COMPILE-NAME
    T-THEN
    T-ELSE
    S" DUP" T-COMPILE-NAME
    S" EMIT" T-COMPILE-NAME
    S" OVER" T-COMPILE-NAME
    S" TIB-BUF" T-COMPILE-NAME
    S" +" T-COMPILE-NAME
    S" C!" T-COMPILE-NAME
    S" 1+" T-COMPILE-NAME
    T-THEN
    T-AGAIN
    T-;

    \ INTERPRET ( -- )
    S" INTERPRET" TX-COLON
    S" WORD" T-COMPILE-NAME
    S" DUP" T-COMPILE-NAME
    S" 0=" T-COMPILE-NAME
    T-IF
    S" 2DROP" T-COMPILE-NAME
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" 2DUP" T-COMPILE-NAME
    S" FIND" T-COMPILE-NAME
    S" DUP" T-COMPILE-NAME
    T-IF
    S" >R" T-COMPILE-NAME
    S" -ROT" T-COMPILE-NAME
    S" 2DROP" T-COMPILE-NAME
    S" R>" T-COMPILE-NAME
    S" SWAP" T-COMPILE-NAME
    S" STATE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    T-IF
    S" LIT" T-COMPILE-NAME -1 T-,
    S" =" T-COMPILE-NAME
    T-IF
    S" EXECUTE" T-COMPILE-NAME
    T-ELSE
    S" ," T-COMPILE-NAME
    T-THEN
    T-ELSE
    S" DROP" T-COMPILE-NAME
    S" EXECUTE" T-COMPILE-NAME
    T-THEN
    S" EXIT" T-COMPILE-NAME
    T-THEN
    S" DROP" T-COMPILE-NAME
    S" 2DUP" T-COMPILE-NAME
    S" NUMBER" T-COMPILE-NAME
    T-IF
    S" -ROT" T-COMPILE-NAME
    S" 2DROP" T-COMPILE-NAME
    S" STATE" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    T-IF
    S" LITERAL" T-COMPILE-NAME
    T-THEN
    T-ELSE
    S" TYPE" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 20 T-,
    S" EMIT" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 3F T-,
    S" EMIT" T-COMPILE-NAME
    S" CR" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 0 T-,
    S" STATE" T-COMPILE-NAME
    S" !" T-COMPILE-NAME
    T-THEN
    T-;

    \ QUIT ( -- ) alternate entry
    S" QUIT" TX-COLON
    T-BEGIN
    S" >IN" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" #TIB" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" <" T-COMPILE-NAME
    T-WHILE
    S" INTERPRET" T-COMPILE-NAME
    T-REPEAT
    T-;

    \ COLD ( -- ) main entry point
    S" COLD" TX-COLON
    T-BEGIN
    S" LIT" T-COMPILE-NAME 6F T-,
    S" EMIT" T-COMPILE-NAME
    S" LIT" T-COMPILE-NAME 6B T-,
    S" EMIT" T-COMPILE-NAME
    S" SPACE" T-COMPILE-NAME
    S" READ-LINE" T-COMPILE-NAME
    T-BEGIN
    S" >IN" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" #TIB" T-COMPILE-NAME
    S" @" T-COMPILE-NAME
    S" <" T-COMPILE-NAME
    T-WHILE
    S" INTERPRET" T-COMPILE-NAME
    T-REPEAT
    S" CR" T-COMPILE-NAME
    T-AGAIN
    T-;
;

\ ============================================
\ MC-COLON: proof colon definitions
\ ============================================

: MC-COLON ( -- )
    S" SQUARE" TX-COLON
    S" DUP" T-COMPILE-NAME
    S" *" T-COMPILE-NAME
    T-;

    S" CUBE" TX-COLON
    S" DUP" T-COMPILE-NAME
    S" SQUARE" T-COMPILE-NAME
    S" *" T-COMPILE-NAME
    T-;

    S" NOOP" TX-COLON T-;
;

\ ============================================
\ MC-BOOT-STUB-CORTEXM
\ ============================================
\ Vector table + init. Called LAST.
\ Vector table at 0x00000000:
\   [0] = initial SP
\   [1] = reset handler + 1 (Thumb)

VARIABLE BOOT-SAVE

: MC-BOOT-STUB-CORTEXM ( -- )
    BOOT-SAVE @ T-HERE !
    T-IMAGE T-HERE !

    \ --- Vector table (8 bytes) ---
    \ [0] Initial SP (top of SRAM)
    20040000 T-,
    \ [1] Reset vector (Thumb: addr|1)
    T-ORG @ 8 + 1 OR T-,

    \ --- Reset handler ---
    \ Data stack pointer (R10)
    20030000 R10 T2-MOV32,
    \ Return stack pointer (R9)
    20038000 R9 T2-MOV32,

    \ --- UART init (CMSDK APB) ---
    \ CTRL = 3 (TX + RX enable)
    40004000 R3 T2-MOV32,
    3 R0 T2-MOVS-I,
    8 R3 R0 T2W-STR,

    \ --- System variables ---
    20000000 R3 T2-MOV32,
    \ STATE = 0
    0 R0 T2-MOVS-I,
    0 R3 R0 T2W-STR,
    \ HERE = end of compiled image
    BOOT-SAVE @
    T-IMAGE - T-ORG @ +
    R0 T2-MOV32,
    4 R3 R0 T2W-STR,
    \ LATEST = last dict entry
    T-LINK-VAR @
    R0 T2-MOV32,
    8 R3 R0 T2W-STR,
    \ BASE = 10 (decimal)
    0A R0 T2-MOVS-I,
    0C R3 R0 T2W-STR,
    \ >IN = 0
    0 R0 T2-MOVS-I,
    10 R3 R0 T2W-STR,
    \ #TIB = 0
    14 R3 R0 T2W-STR,

    \ --- Start Forth interpreter ---
    \ IP (R8) = COLD body (CFA + 4)
    S" COLD" T-FIND-SYM
    DUP 0= IF
        ." COLD not found!" CR
    THEN
    4 +
    R8 T2-MOV32,

    \ NEXT: dispatch first word
    EMIT-NEXT

    BOOT-SAVE @ T-HERE !
;

\ ============================================
\ META-COMPILE-CORTEXM (phase A core)
\ ============================================

: META-COMPILE-CORTEXM ( -- )
    META-INIT TSYM-INIT HEX
    0 T-ORG !
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
    MC-IO-CORTEXM
    MC-SYSVAR-CORTEXM
    MC-COLON
    META-CHECK
    T-HERE @ T-IMAGE - T-SIZE !
    1 META-OK !
    DECIMAL
    ." CM33 compile: "
    META-SIZE . ." bytes, "
    TSYM-N @ . ." syms" CR
;

\ ============================================
\ META-COMPILE-CORTEXM-BOOT (full image)
\ ============================================

: META-COMPILE-CORTEXM-BOOT ( -- )
    META-INIT TSYM-INIT HEX
    0 T-ORG !
    200 T-ALLOT
    T-HERE @ BOOT-SAVE !
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
    MC-IO-CORTEXM
    MC-SYSVAR-CORTEXM
    MC-DICT-CORTEXM
    MC-DISPLAY-CORTEXM
    MC-COMPILER-CORTEXM
    MC-CONTROLFLOW-CORTEXM
    MC-INTERPRET-CORTEXM
    MC-COLON
    META-CHECK
    MC-BOOT-STUB-CORTEXM
    T-HERE @ T-IMAGE - T-SIZE !
    1 META-OK !
    DECIMAL
    ." CM33 boot: "
    META-SIZE . ." bytes, "
    TSYM-N @ . ." syms" CR
;

PREVIOUS PREVIOUS PREVIOUS PREVIOUS
FORTH DEFINITIONS
DECIMAL
