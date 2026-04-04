\ ============================================
\ CATALOG: TARGET-X86
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ REQUIRES: X86-ASM META-COMPILER
\ ============================================
\
\ x86 target architecture for metacompiler.
\ Provides runtime emitters and the Phase B1
\ build driver (META-COMPILE-X86).
\
\ Usage:
\   USING META-COMPILER
\   USING TARGET-X86
\   META-COMPILE-X86
\   META-STATUS
\
\ ============================================

VOCABULARY TARGET-X86
ALSO TARGET-X86 DEFINITIONS
ALSO META-COMPILER
ALSO X86-ASM
HEX

\ ============================================
\ Runtime emitters
\ ============================================
\ Compose X86-ASM mnemonics into the target
\ runtime patterns from forth.asm.

\ NEXT: lodsd; jmp [eax]
: EMIT-NEXT ( -- )
    LODSD, %EAX JMP[],
;

\ PUSHRSP: sub ebp,4; mov [ebp],reg
: EMIT-PUSHRSP ( reg -- )
    4 %EBP SUB-I8,
    %EBP 0 MOV-DISP!,
;

\ POPRSP: mov reg,[ebp]; add ebp,4
: EMIT-POPRSP ( reg -- )
    %EBP SWAP 0 MOV-DISP@,
    4 %EBP ADD-I8,
;

\ DOCOL: pushrsp esi; add eax,4;
\        mov esi,eax; NEXT
: EMIT-DOCOL ( -- )
    %ESI EMIT-PUSHRSP
    4 %EAX ADD-I8,
    %EAX %ESI MOV,
    EMIT-NEXT
;

\ DOCON: push [eax+4]; NEXT
: EMIT-DOCON ( -- )
    %EAX 4 PUSH-D8,
    EMIT-NEXT
;

\ DOCREATE: lea eax,[eax+4]; push eax
: EMIT-DOCREATE ( -- )
    %EAX %EAX 4 LEA-D8,
    %EAX PUSH,
    EMIT-NEXT
;

\ EXIT: poprsp esi; NEXT
: EMIT-EXIT ( -- )
    %ESI EMIT-POPRSP
    EMIT-NEXT
;

\ LIT: lodsd; push eax; NEXT
: EMIT-LIT ( -- )
    LODSD,
    %EAX PUSH,
    EMIT-NEXT
;

\ ============================================
\ Target symbol table
\ ============================================
\ Tracks (CFA, name) for each target word.
\ TX-CODE auto-registers; T-COMPILE-NAME
\ looks up CFA by name for T-COLON defs.
\ Entry: CFA(4) + len(1) + name(1F) = 24h

DECIMAL 36 CONSTANT TSYM-SZ HEX
CREATE TSYM-TBL 1000 ALLOT
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

\ Compile target word by name into T-IMAGE
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

\ TX-CONST: like T-CONSTANT, auto-registers
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

\ TX-COLON: like T-COLON, auto-registers
: TX-COLON ( addr len -- )
    2DUP TX-L ! TX-A !
    T-COLON
    T-ADDR 4 -
    TX-A @ TX-L @ TSYM-REG
;

\ Reset symbol table
: TSYM-INIT 0 TSYM-N ! ;

\ ============================================
\ Build driver: META-COMPILE-X86
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

    \ BRANCH: add esi,[esi]; NEXT
    S" BRANCH" TX-CODE
    T-ADDR 4 - DOBRANCH-ADDR !
    T-ADDR BRANCH-CODE !
    %ESI %ESI ADD[],
    END-CODE

    \ 0BRANCH: pop; test; jz BRANCH;
    \          add esi,4; NEXT
    S" 0BRANCH" TX-CODE
    T-ADDR 4 - DO0BRANCH-ADDR !
    %EAX POP,
    %EAX %EAX TEST,
    \ jz to BRANCH code
    0F T-C, 84 T-C,
    BRANCH-CODE @ T-ADDR - 4 - T-,
    4 %ESI ADD-I8,
    END-CODE

    \ DOCON
    S" DOCON" TX-CODE
    T-ADDR DOCON-ADDR !
    EMIT-DOCON

    \ DOCREATE
    S" DOCREATE" TX-CODE
    T-ADDR DOCREATE-ADDR !
    EMIT-DOCREATE

    \ EXECUTE: pop eax; jmp [eax]
    S" EXECUTE" TX-CODE
    %EAX POP,
    %EAX JMP[],
;

: MC-STACK ( -- )
    S" DROP" TX-CODE
    %EAX POP, END-CODE

    S" DUP" TX-CODE
    %EAX MOV[ESP],
    %EAX PUSH, END-CODE

    S" SWAP" TX-CODE
    %EAX POP, %EBX POP,
    %EAX PUSH, %EBX PUSH,
    END-CODE

    S" OVER" TX-CODE
    %EAX 4 MOV-ESP+,
    %EAX PUSH, END-CODE

    S" ROT" TX-CODE
    %EAX POP, %EBX POP, %ECX POP,
    %EBX PUSH, %EAX PUSH,
    %ECX PUSH, END-CODE

    S" -ROT" TX-CODE
    %EAX POP, %EBX POP, %ECX POP,
    %EAX PUSH, %ECX PUSH,
    %EBX PUSH, END-CODE

    S" 2DROP" TX-CODE
    %EAX POP, %EAX POP, END-CODE

    S" 2DUP" TX-CODE
    %EAX MOV[ESP],
    %EBX 4 MOV-ESP+,
    %EBX PUSH, %EAX PUSH,
    END-CODE

    S" ?DUP" TX-CODE
    %EAX MOV[ESP],
    %EAX %EAX TEST,
    JZ, %EAX PUSH, SWAP >RESOLVE
    END-CODE

    S" NIP" TX-CODE
    %EAX POP, %EBX POP,
    %EAX PUSH, END-CODE

    S" TUCK" TX-CODE
    %EAX POP, %EBX POP,
    %EAX PUSH, %EBX PUSH,
    %EAX PUSH, END-CODE

    S" DEPTH" TX-CODE
    7C00 %EAX MOV-IMM,
    %ESP %EAX SUB,
    \ shr eax, 2 (C1 E8 02)
    C1 T-C, E8 T-C, 2 T-C,
    %EAX PUSH, END-CODE

    \ Return stack
    S" >R" TX-CODE
    %EAX POP,
    %EAX EMIT-PUSHRSP
    END-CODE

    S" R>" TX-CODE
    %EAX EMIT-POPRSP
    %EAX PUSH, END-CODE

    S" R@" TX-CODE
    %EBP %EAX 0 MOV-DISP@,
    %EAX PUSH, END-CODE

    S" RDROP" TX-CODE
    4 %EBP ADD-I8, END-CODE
;

: MC-ARITH ( -- )
    S" +" TX-CODE
    %EAX POP, %EAX ADD[ESP], END-CODE

    S" -" TX-CODE
    %EAX POP, %EAX SUB[ESP], END-CODE

    S" *" TX-CODE
    %EAX POP, %EBX POP,
    %EBX IMUL1,
    %EAX PUSH, END-CODE

    S" 1+" TX-CODE INC[ESP], END-CODE
    S" 1-" TX-CODE DEC[ESP], END-CODE

    S" 2+" TX-CODE
    INC[ESP], INC[ESP], END-CODE

    S" 2-" TX-CODE
    DEC[ESP], DEC[ESP], END-CODE

    S" NEGATE" TX-CODE
    NEG[ESP], END-CODE

    S" ABS" TX-CODE
    %EAX MOV[ESP],
    %EAX %EAX TEST,
    JNS, NEG[ESP], SWAP >RESOLVE
    END-CODE
;

: MC-LOGIC ( -- )
    S" AND" TX-CODE
    %EAX POP, %EAX AND[ESP], END-CODE

    S" OR" TX-CODE
    %EAX POP, %EAX OR[ESP], END-CODE

    S" XOR" TX-CODE
    %EAX POP, %EAX XOR[ESP], END-CODE

    S" INVERT" TX-CODE
    NOT[ESP], END-CODE

    S" LSHIFT" TX-CODE
    %ECX POP, SHL-CL[ESP], END-CODE

    S" RSHIFT" TX-CODE
    %ECX POP, SHR-CL[ESP], END-CODE
;

: MC-COMPARE ( -- )
    S" =" TX-CODE
    %EAX POP, %EBX POP,
    %EAX %EBX CMP,
    SETE, MOVZX-AL, %EAX NEG,
    %EAX PUSH, END-CODE

    S" <>" TX-CODE
    %EAX POP, %EBX POP,
    %EAX %EBX CMP,
    SETNE, MOVZX-AL, %EAX NEG,
    %EAX PUSH, END-CODE

    S" <" TX-CODE
    %EAX POP, %EBX POP,
    %EAX %EBX CMP,
    SETL, MOVZX-AL, %EAX NEG,
    %EAX PUSH, END-CODE

    S" >" TX-CODE
    %EAX POP, %EBX POP,
    %EAX %EBX CMP,
    SETG, MOVZX-AL, %EAX NEG,
    %EAX PUSH, END-CODE

    S" 0=" TX-CODE
    %EAX POP, %EAX %EAX TEST,
    SETE, MOVZX-AL, %EAX NEG,
    %EAX PUSH, END-CODE

    S" 0<>" TX-CODE
    %EAX POP, %EAX %EAX TEST,
    SETNE, MOVZX-AL, %EAX NEG,
    %EAX PUSH, END-CODE

    S" 0<" TX-CODE
    %EAX POP, %EAX %EAX TEST,
    SETS, MOVZX-AL, %EAX NEG,
    %EAX PUSH, END-CODE

    S" 0>" TX-CODE
    %EAX POP, %EAX %EAX TEST,
    SETG, MOVZX-AL, %EAX NEG,
    %EAX PUSH, END-CODE
;

: MC-MEMORY ( -- )
    S" @" TX-CODE
    %EAX POP,
    %EAX %EAX MOV[],
    %EAX PUSH, END-CODE

    S" !" TX-CODE
    %EBX POP, %EAX POP,
    %EAX %EBX []MOV, END-CODE

    S" C@" TX-CODE
    %EAX POP,
    %EAX %EAX MOVZXB[],
    %EAX PUSH, END-CODE

    S" C!" TX-CODE
    %EBX POP, %EAX POP,
    %EAX %EBX []MOV-B, END-CODE

    S" +!" TX-CODE
    %EBX POP, %EAX POP,
    \ add [ebx],eax (01 03)
    01 T-C, 0 %EAX %EBX MODRM T-C,
    END-CODE

    S" -!" TX-CODE
    %EBX POP, %EAX POP,
    \ sub [ebx],eax (29 03)
    29 T-C, 0 %EAX %EBX MODRM T-C,
    END-CODE

    S" CMOVE" TX-CODE
    %ESI EMIT-PUSHRSP
    %ECX POP, %EDI POP, %ESI POP,
    REP-MOVSB,
    %ESI EMIT-POPRSP
    END-CODE

    S" FILL" TX-CODE
    %EAX POP, %ECX POP, %EDI POP,
    REP-STOSB, END-CODE
;

\ ============================================
\ Phase B1.5: Division, I/O, utility words
\ ============================================

\ Fixup variables for complex control flow
VARIABLE FX1 VARIABLE FX2
VARIABLE FX3 VARIABLE FX4
VARIABLE FX5

: MC-DIVISION ( -- )
    \ / (floored division, Forth-83)
    S" /" TX-CODE
    %EBX POP, %EAX POP,
    %EBX %EBX TEST,
    JZ, FX1 !
    %EAX %ECX MOV,
    %EBX %ECX XOR,
    %EAX %EAX TEST,
    JNS, FX2 !
    %EAX NEG,
    FX2 @ >RESOLVE
    %EBX %EBX TEST,
    JNS, FX3 !
    %EBX NEG,
    FX3 @ >RESOLVE
    %EDX %EDX XOR,
    %EBX UDIV1,
    %ECX %ECX TEST,
    JNS, FX4 !
    %EDX %EDX TEST,
    JZ, FX5 !
    %EAX INC,
    FX5 @ >RESOLVE
    %EAX NEG,
    FX4 @ >RESOLVE
    %EAX PUSH, END-CODE
    \ div_zero: push MAX_INT; NEXT
    FX1 @ >RESOLVE
    7FFFFFFF PUSH-IMM, END-CODE

    \ MOD (floored modulo)
    S" MOD" TX-CODE
    %EBX POP, %EAX POP,
    %EBX %EBX TEST,
    JZ, FX1 !
    CDQ,
    %EBX IDIV,
    %EDX %EDX TEST,
    JZ, FX2 !
    %EDX %ECX MOV,
    %EBX %ECX XOR,
    JNS, FX3 !
    %EBX %EDX ADD,
    FX3 @ >RESOLVE
    FX2 @ >RESOLVE
    %EDX PUSH, END-CODE
    FX1 @ >RESOLVE
    0 PUSH-IMM, END-CODE

    \ /MOD (floored divmod)
    S" /MOD" TX-CODE
    %EBX POP, %EAX POP,
    %EBX %EBX TEST,
    JZ, FX1 !
    CDQ,
    %EBX IDIV,
    %EDX %ECX MOV,
    %EBX %ECX XOR,
    JNS, FX2 !
    %EDX %EDX TEST,
    JZ, FX3 !
    %EAX DEC,
    %EBX %EDX ADD,
    FX3 @ >RESOLVE
    FX2 @ >RESOLVE
    %EDX PUSH, %EAX PUSH, END-CODE
    FX1 @ >RESOLVE
    0 PUSH-IMM,
    7FFFFFFF PUSH-IMM, END-CODE

    \ MIN: pop b a; cmp b,a; jl->pushB
    S" MIN" TX-CODE
    %EAX POP, %EBX POP,
    %EBX %EAX CMP,
    JL,
    %EBX PUSH, END-CODE
    >RESOLVE
    %EAX PUSH, END-CODE

    \ MAX: pop b a; cmp b,a; jg->pushB
    S" MAX" TX-CODE
    %EAX POP, %EBX POP,
    %EBX %EAX CMP,
    JG,
    %EBX PUSH, END-CODE
    >RESOLVE
    %EAX PUSH, END-CODE
;

: MC-STACK2 ( -- )
    S" 2SWAP" TX-CODE
    %EAX POP, %EBX POP,
    %ECX POP, %EDX POP,
    %EBX PUSH, %EAX PUSH,
    %EDX PUSH, %ECX PUSH,
    END-CODE

    S" 2OVER" TX-CODE
    %EAX C MOV-ESP+,
    %EBX 8 MOV-ESP+,
    %EBX PUSH, %EAX PUSH,
    END-CODE

    S" PICK" TX-CODE
    %EAX POP,
    \ mov eax,[esp+eax*4] = 8B 04 84
    8B T-C, 04 T-C, 84 T-C,
    %EAX PUSH, END-CODE
;

: MC-PORTIO ( -- )
    S" INB" TX-CODE
    %EDX POP, %EAX %EAX XOR,
    IN-AL-DX, %EAX PUSH, END-CODE

    S" INW" TX-CODE
    %EDX POP, %EAX %EAX XOR,
    IN-AX-DX, %EAX PUSH, END-CODE

    S" INL" TX-CODE
    %EDX POP,
    IN-EAX-DX, %EAX PUSH, END-CODE

    S" OUTB" TX-CODE
    %EDX POP, %EAX POP,
    OUT-DX-AL, END-CODE

    S" OUTW" TX-CODE
    %EDX POP, %EAX POP,
    OUT-DX-AX, END-CODE

    S" OUTL" TX-CODE
    %EDX POP, %EAX POP,
    OUT-DX-EAX, END-CODE
;

: MC-MEMORY2 ( -- )
    S" W@" TX-CODE
    %EAX POP,
    %EAX %EAX MOVZXW[],
    %EAX PUSH, END-CODE

    S" W!" TX-CODE
    %EBX POP, %EAX POP,
    %EAX %EBX []MOV-W, END-CODE

    S" CMOVE>" TX-CODE
    %ESI EMIT-PUSHRSP
    %ECX POP, %EDI POP, %ESI POP,
    %ECX %ESI ADD, %ESI DEC,
    %ECX %EDI ADD, %EDI DEC,
    STD, REP-MOVSB, CLD,
    %ESI EMIT-POPRSP
    END-CODE
;

: MC-UTILITY ( -- )
    S" SP@" TX-CODE
    %ESP PUSH, END-CODE

    S" SP!" TX-CODE
    %ESP POP, END-CODE

    S" >BODY" TX-CODE
    %EAX POP,
    4 %EAX ADD-I8,
    %EAX PUSH, END-CODE

    S" CELLS" TX-CODE
    %EAX POP,
    \ shl eax, 2  (C1 E0 02)
    C1 T-C, E0 T-C, 2 T-C,
    %EAX PUSH, END-CODE

    S" CELL+" TX-CODE
    \ add dword [esp], 4
    83 T-C, 04 T-C, 24 T-C, 4 T-C,
    END-CODE

    \ Constants via T-CONSTANT
    -1 S" TRUE" TX-CONST
    0 S" FALSE" TX-CONST
;

\ ============================================
\ T-COLON definitions (threaded code)
\ ============================================
\ These prove the metacompiler can build
\ high-level Forth words from primitives.

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

    \ : ABS2 ( n -- |n| ) DUP 0< IF NEGATE
    S" ABS2" TX-COLON
    S" DUP" T-COMPILE-NAME
    S" 0<" T-COMPILE-NAME
    T-IF
    S" NEGATE" T-COMPILE-NAME
    T-THEN
    T-;
;

\ ---- Top-level build driver ----
: META-COMPILE-X86 ( -- )
    META-INIT TSYM-INIT HEX
    MC-RUNTIMES
    MC-STACK
    MC-ARITH
    MC-LOGIC
    MC-COMPARE
    MC-MEMORY
    MC-DIVISION
    MC-STACK2
    MC-PORTIO
    MC-MEMORY2
    MC-UTILITY
    MC-COLON
    META-CHECK
    T-HERE @ T-IMAGE - T-SIZE !
    1 META-OK !
    DECIMAL
    ." Phase B complete: "
    META-SIZE . ." bytes, "
    TSYM-N @ . ." syms" CR
;

\ ============================================
\ Phase B3: Full kernel copy for boot test
\ ============================================
\ Copies the running kernel binary (64KB at
\ 0x7E00) into T-IMAGE. This is a 1:1 copy
\ that should boot identically.

: META-COPY-KERNEL ( -- )
    META-INIT HEX
    7E00 10000 T-BINARY,
    T-HERE @ T-IMAGE - T-SIZE !
    1 META-OK !
    DECIMAL
    ." Kernel copy: "
    META-SIZE . ." bytes" CR
;

PREVIOUS PREVIOUS PREVIOUS
FORTH DEFINITIONS
DECIMAL
