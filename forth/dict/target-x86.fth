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
\ Phase B6: DO/LOOP runtimes
\ ============================================
\ Additional fixup variables for complex
\ control flow with many forward jumps

VARIABLE FX6 VARIABLE FX7
VARIABLE FX8 VARIABLE FX9
VARIABLE FX10

: MC-LOOP-RT ( -- )
    \ (DO): pop index+limit, push to rstack
    S" (DO)" TX-CODE
    T-ADDR 4 - DODO-ADDR !
    %EAX POP, %EBX POP,
    %EBX EMIT-PUSHRSP
    %EAX EMIT-PUSHRSP
    END-CODE

    \ (LOOP): inc index, cmp limit, branch
    S" (LOOP)" TX-CODE
    T-ADDR 4 - DOLOOP-ADDR !
    %EBP %EAX 0 MOV-DISP@,
    %EAX INC,
    %EAX %EBP 0 MOV-DISP!,
    %EBP %EBX 4 MOV-DISP@,
    %EBX %EAX CMP,
    JGE, FX6 !
    LODSD,
    %EAX %ESI ADD,
    EMIT-NEXT
    FX6 @ >RESOLVE
    8 %EBP ADD-I8,
    LODSD,
    EMIT-NEXT

    \ (+LOOP): add increment, check crossing
    S" (+LOOP)" TX-CODE
    T-ADDR 4 - DOPLOOP-ADDR !
    %ECX POP,
    %EBP %EAX 0 MOV-DISP@,
    %ECX %EAX ADD,
    %EAX %EBP 0 MOV-DISP!,
    %EBP %EBX 4 MOV-DISP@,
    %ECX %ECX TEST,
    JS, FX6 !
    %EBX %EAX CMP,
    JGE, FX7 !
    JMP, FX8 !
    FX6 @ >RESOLVE
    %EBX %EAX CMP,
    JL, FX9 !
    FX8 @ >RESOLVE
    LODSD,
    %EAX %ESI ADD,
    EMIT-NEXT
    FX7 @ >RESOLVE
    FX9 @ >RESOLVE
    8 %EBP ADD-I8,
    LODSD,
    EMIT-NEXT

    \ I: push index from return stack
    S" I" TX-CODE
    %EBP %EAX 0 MOV-DISP@,
    %EAX PUSH, END-CODE

    \ J: push outer loop index
    S" J" TX-CODE
    %EBP %EAX 8 MOV-DISP@,
    %EAX PUSH, END-CODE

    \ UNLOOP: remove loop params
    S" UNLOOP" TX-CODE
    8 %EBP ADD-I8, END-CODE

    \ LEAVE: set index = limit
    S" LEAVE" TX-CODE
    %EBP %EAX 4 MOV-DISP@,
    %EAX %EBP 0 MOV-DISP!,
    END-CODE
;

\ ============================================
\ Phase B5: I/O words (need helper calls)
\ ============================================

: MC-IO ( -- )
    S" KEY" TX-CODE
    ADDR-READ-KEY CALL-ABS,
    %EAX PUSH, END-CODE

    S" EMIT" TX-CODE
    %EAX POP,
    ADDR-PRINT-CHAR CALL-ABS,
    END-CODE

    S" CR" TX-CODE
    0D %EAX MOV-IMM,
    ADDR-PRINT-CHAR CALL-ABS,
    0A %EAX MOV-IMM,
    ADDR-PRINT-CHAR CALL-ABS,
    END-CODE

    S" SPACE" TX-CODE
    20 %EAX MOV-IMM,
    ADDR-PRINT-CHAR CALL-ABS,
    END-CODE

    S" TYPE" TX-CODE
    %ECX POP,
    %ESI EMIT-PUSHRSP
    %ESI POP,
    %ECX %ECX TEST,
    JZ,
    \ .loop: lodsb; call print_char; loop
    AC T-C,
    ADDR-PRINT-CHAR CALL-ABS,
    E2 T-C, F8 T-C,
    >RESOLVE
    %ESI EMIT-POPRSP
    END-CODE
;

\ ============================================
\ Phase B5: Number display
\ ============================================

: MC-DISPLAY ( -- )
    S" ." TX-CODE
    %EAX POP,
    ADDR-PRINT-NUM CALL-ABS,
    20 %EAX MOV-IMM,
    ADDR-PRINT-CHAR CALL-ABS,
    END-CODE

    \ HEX: mov dword [VAR_BASE], 16
    S" HEX" TX-CODE
    C7 T-C, 05 T-C, 2800C T-, 10 T-,
    END-CODE

    \ DECIMAL: mov dword [VAR_BASE], 10
    S" DECIMAL" TX-CODE
    C7 T-C, 05 T-C, 2800C T-, 0A T-,
    END-CODE
;

\ ============================================
\ Phase B5: System variables and constants
\ ============================================

: MC-SYSVAR ( -- )
    \ Variables (push address, like DEFVAR)
    28000 S" STATE" TX-CONST
    28004 S" HERE" TX-CONST
    28008 S" LATEST" TX-CONST
    2800C S" BASE" TX-CONST
    \ Constants
    1 S" VERSION" TX-CONST
    4 S" CELL" TX-CONST
;

\ ============================================
\ Phase B5: Dictionary/compiler words
\ ============================================

: MC-DICT ( -- )
    \ WORD: call word_; push result
    S" WORD" TX-CODE
    ADDR-WORD CALL-ABS,
    %EAX PUSH, END-CODE

    \ NUMBER: pop dummy; call number_; push
    S" NUMBER" TX-CODE
    %EAX POP,
    ADDR-NUMBER CALL-ABS,
    %EAX PUSH, END-CODE

    \ FIND: call find_; push xt
    S" FIND" TX-CODE
    ADDR-FIND CALL-ABS,
    %EAX PUSH, END-CODE

    \ , (comma): pop eax; call comma_
    S" ," TX-CODE
    %EAX POP,
    ADDR-COMMA CALL-ABS,
    END-CODE

    \ C, : pop eax; mov edi,[HERE]; stosb;
    \      mov [HERE],edi
    S" C," TX-CODE
    %EAX POP,
    28004 %EDI MOV-ABS[],
    AA T-C,
    %EDI 28004 []ABS-MOV,
    END-CODE

    \ ALLOT: pop eax; add [HERE],eax
    S" ALLOT" TX-CODE
    %EAX POP,
    \ add [0x28004], eax = 01 05 04800200
    01 T-C, 05 T-C, 28004 T-,
    END-CODE

    \ CREATE: word_; create_; write CFA
    S" CREATE" TX-CODE
    ADDR-WORD CALL-ABS,
    ADDR-CREATE CALL-ABS,
    28004 %EAX MOV-ABS[],
    \ mov dword [eax], DOCREATE code addr
    C7 T-C, 00 T-C,
    DOCREATE-ADDR @ T-,
    \ add dword [0x28004], 4
    83 T-C, 05 T-C, 28004 T-,
    04 T-C,
    END-CODE
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

\ ============================================
\ Phase B6: Compiler words
\ ============================================
\ : ; [ ] LITERAL IMMEDIATE COMPILE, ['] '

VARIABLE COMPILEC-CFA

: MC-COMPILER ( -- )
    \ : (COLON) — define new word
    S" :" TX-CODE
    ADDR-WORD CALL-ABS,
    ADDR-CREATE CALL-ABS,
    \ mov eax, [HERE]
    28004 %EAX MOV-ABS[],
    \ mov dword [eax], DOCOL
    C7 T-C, 00 T-C, DOCOL-ADDR @ T-,
    \ add dword [HERE], 4
    83 T-C, 05 T-C, 28004 T-, 04 T-C,
    \ hide: mov eax,[LATEST]; or [eax+4],40
    28008 %EAX MOV-ABS[],
    80 T-C, 48 T-C, 04 T-C, 40 T-C,
    \ mov dword [STATE], 1
    C7 T-C, 05 T-C, 28000 T-, 1 T-,
    END-CODE

    \ ; (SEMICOLON) — end definition
    S" ;" TX-CODE
    \ mov eax, [HERE]
    28004 %EAX MOV-ABS[],
    \ mov dword [eax], EXIT-CFA
    C7 T-C, 00 T-C, DOEXIT-ADDR @ T-,
    \ add dword [HERE], 4
    83 T-C, 05 T-C, 28004 T-, 04 T-C,
    \ unhide: mov eax,[LATEST]
    28008 %EAX MOV-ABS[],
    \ and byte [eax+4], 0xBF
    80 T-C, 60 T-C, 04 T-C, 0BF T-C,
    \ mov dword [STATE], 0
    C7 T-C, 05 T-C, 28000 T-, 0 T-,
    END-CODE
    T-IMMEDIATE

    \ [ — enter interpret mode (IMMEDIATE)
    S" [" TX-CODE
    C7 T-C, 05 T-C, 28000 T-, 0 T-,
    END-CODE
    T-IMMEDIATE

    \ ] — enter compile mode
    S" ]" TX-CODE
    C7 T-C, 05 T-C, 28000 T-, 1 T-,
    END-CODE

    \ LITERAL — compile LIT + n (IMMEDIATE)
    S" LITERAL" TX-CODE
    28004 %EAX MOV-ABS[],
    \ mov dword [eax], LIT-CFA
    C7 T-C, 00 T-C, DOLIT-ADDR @ T-,
    %EBX POP,
    \ mov [eax+4], ebx
    89 T-C, 58 T-C, 04 T-C,
    \ add dword [HERE], 8
    83 T-C, 05 T-C, 28004 T-, 08 T-C,
    END-CODE
    T-IMMEDIATE

    \ IMMEDIATE — toggle flag on LATEST
    S" IMMEDIATE" TX-CODE
    28008 %EAX MOV-ABS[],
    \ xor byte [eax+4], 0x80
    80 T-C, 70 T-C, 04 T-C, 80 T-C,
    END-CODE

    \ COMPILE, — store XT at HERE
    S" COMPILE," TX-CODE
    %EBX POP,
    28004 %EAX MOV-ABS[],
    \ mov [eax], ebx
    89 T-C, 18 T-C,
    \ add dword [HERE], 4
    83 T-C, 05 T-C, 28004 T-, 04 T-C,
    END-CODE
    S" COMPILE," T-FIND-SYM COMPILEC-CFA !

    \ ' (TICK) -- find word, push XT
    S" '" TX-CODE
    ADDR-WORD CALL-ABS,
    ADDR-FIND CALL-ABS,
    %EAX PUSH, END-CODE

    \ ['] -- compile LIT + XT (IMMEDIATE)
    S" [']" TX-CODE
    ADDR-WORD CALL-ABS,
    ADDR-FIND CALL-ABS,
    %EBX %EAX MOV,
    28004 %EAX MOV-ABS[],
    C7 T-C, 00 T-C, DOLIT-ADDR @ T-,
    89 T-C, 58 T-C, 04 T-C,
    83 T-C, 05 T-C, 28004 T-, 08 T-C,
    END-CODE
    T-IMMEDIATE

    \ POSTPONE (IMMEDIATE)
    S" POSTPONE" TX-CODE
    ADDR-WORD CALL-ABS,
    ADDR-FIND CALL-ABS,
    %EAX %EBX MOV,
    F6 T-C, C1 T-C, 80 T-C,
    JNZ, FX6 !
    28004 %EAX MOV-ABS[],
    C7 T-C, 00 T-C, DOLIT-ADDR @ T-,
    89 T-C, 58 T-C, 04 T-C,
    C7 T-C, 40 T-C, 08 T-C,
    COMPILEC-CFA @ T-,
    83 T-C, 05 T-C, 28004 T-, 0C T-C,
    EMIT-NEXT
    FX6 @ >RESOLVE
    28004 %EAX MOV-ABS[],
    89 T-C, 18 T-C,
    83 T-C, 05 T-C, 28004 T-, 04 T-C,
    END-CODE
    T-IMMEDIATE
;

\ ============================================
\ Phase B6: Control flow (compile-time)
\ ============================================
\ IF THEN ELSE BEGIN UNTIL AGAIN
\ WHILE REPEAT DO LOOP +LOOP
\ All are IMMEDIATE — they execute at compile
\ time to compile branch patterns.

: MC-CONTROLFLOW ( -- )
    \ IF — compile 0BRANCH + placeholder
    S" IF" TX-CODE
    28004 %EAX MOV-ABS[],
    C7 T-C, 00 T-C,
    DO0BRANCH-ADDR @ T-,
    \ push addr of placeholder
    \ lea ebx,[eax+4]
    8D T-C, 58 T-C, 04 T-C,
    %EBX PUSH,
    \ zero the placeholder; HERE += 8
    C7 T-C, 40 T-C, 04 T-C, 0 T-,
    83 T-C, 05 T-C, 28004 T-, 08 T-C,
    END-CODE
    T-IMMEDIATE

    \ THEN — patch placeholder
    S" THEN" TX-CODE
    %EBX POP,
    28004 %EAX MOV-ABS[],
    \ offset = HERE - patch_addr
    %EBX %EAX SUB,
    \ mov [ebx], eax
    89 T-C, 03 T-C,
    END-CODE
    T-IMMEDIATE

    \ ELSE — BRANCH + placeholder, patch IF
    S" ELSE" TX-CODE
    \ compile BRANCH + placeholder
    28004 %EAX MOV-ABS[],
    C7 T-C, 00 T-C,
    DOBRANCH-ADDR @ T-,
    \ push new placeholder addr
    8D T-C, 58 T-C, 04 T-C,
    \ zero placeholder; HERE += 8
    C7 T-C, 40 T-C, 04 T-C, 0 T-,
    83 T-C, 05 T-C, 28004 T-, 08 T-C,
    \ patch IF: pop old, calc offset
    %ECX POP,
    28004 %EAX MOV-ABS[],
    %ECX %EAX SUB,
    89 T-C, 01 T-C,
    \ push new placeholder
    %EBX PUSH,
    END-CODE
    T-IMMEDIATE

    \ BEGIN — push HERE
    S" BEGIN" TX-CODE
    28004 %EAX MOV-ABS[],
    %EAX PUSH, END-CODE
    T-IMMEDIATE

    \ UNTIL — compile 0BRANCH + backward off
    S" UNTIL" TX-CODE
    28004 %EAX MOV-ABS[],
    C7 T-C, 00 T-C,
    DO0BRANCH-ADDR @ T-,
    \ offset = dest - (HERE+4)
    %EBX POP,
    \ lea ecx,[eax+4]  (patch addr)
    8D T-C, 48 T-C, 04 T-C,
    %ECX %EBX SUB,
    \ mov [ecx], ebx
    89 T-C, 19 T-C,
    83 T-C, 05 T-C, 28004 T-, 08 T-C,
    END-CODE
    T-IMMEDIATE

    \ AGAIN — compile BRANCH + backward off
    S" AGAIN" TX-CODE
    28004 %EAX MOV-ABS[],
    C7 T-C, 00 T-C,
    DOBRANCH-ADDR @ T-,
    %EBX POP,
    8D T-C, 48 T-C, 04 T-C,
    %ECX %EBX SUB,
    89 T-C, 19 T-C,
    83 T-C, 05 T-C, 28004 T-, 08 T-C,
    END-CODE
    T-IMMEDIATE

    \ WHILE — 0BRANCH + placeholder, swap
    S" WHILE" TX-CODE
    28004 %EAX MOV-ABS[],
    C7 T-C, 00 T-C,
    DO0BRANCH-ADDR @ T-,
    8D T-C, 58 T-C, 04 T-C,
    C7 T-C, 40 T-C, 04 T-C, 0 T-,
    83 T-C, 05 T-C, 28004 T-, 08 T-C,
    \ swap: pop dest, push orig, push dest
    %EAX POP, %EBX PUSH, %EAX PUSH,
    END-CODE
    T-IMMEDIATE

    \ REPEAT — BRANCH back + patch WHILE
    S" REPEAT" TX-CODE
    \ BRANCH backward to dest
    28004 %EAX MOV-ABS[],
    C7 T-C, 00 T-C,
    DOBRANCH-ADDR @ T-,
    %EBX POP,
    8D T-C, 48 T-C, 04 T-C,
    %ECX %EBX SUB,
    89 T-C, 19 T-C,
    83 T-C, 05 T-C, 28004 T-, 08 T-C,
    \ patch WHILE placeholder
    %ECX POP,
    28004 %EAX MOV-ABS[],
    %ECX %EAX SUB,
    89 T-C, 01 T-C,
    END-CODE
    T-IMMEDIATE

    \ DO — compile (DO), push HERE
    S" DO" TX-CODE
    28004 %EAX MOV-ABS[],
    C7 T-C, 00 T-C, DODO-ADDR @ T-,
    83 T-C, 05 T-C, 28004 T-, 04 T-C,
    \ push body address for LOOP
    28004 %EAX MOV-ABS[],
    %EAX PUSH, END-CODE
    T-IMMEDIATE

    \ LOOP — compile (LOOP) + backward off
    S" LOOP" TX-CODE
    28004 %EAX MOV-ABS[],
    C7 T-C, 00 T-C,
    DOLOOP-ADDR @ T-,
    %EBX POP,
    \ offset = dest - (HERE+4) - 4
    8D T-C, 48 T-C, 04 T-C,
    %ECX %EBX SUB,
    4 %EBX SUB-I8,
    89 T-C, 19 T-C,
    83 T-C, 05 T-C, 28004 T-, 08 T-C,
    END-CODE
    T-IMMEDIATE

    \ +LOOP — compile (+LOOP) + backward off
    S" +LOOP" TX-CODE
    28004 %EAX MOV-ABS[],
    C7 T-C, 00 T-C,
    DOPLOOP-ADDR @ T-,
    %EBX POP,
    8D T-C, 48 T-C, 04 T-C,
    %ECX %EBX SUB,
    4 %EBX SUB-I8,
    89 T-C, 19 T-C,
    83 T-C, 05 T-C, 28004 T-, 08 T-C,
    END-CODE
    T-IMMEDIATE
;

\ ============================================
\ Phase B6: INTERPRET (simplified)
\ ============================================
\ Interactive only: no BLK, no Ctrl+C.
\ Uses CALL-ABS for all kernel helpers.

: MC-INTERPRET ( -- )
    S" INTERPRET" TX-CODE

    \ Check TOIN: if > 0, have input
    28014 %EAX MOV-ABS[],
    %EAX %EAX TEST,
    JNZ, FX1 !

    \ Interactive: print "ok "
    6F %EAX MOV-IMM,
    ADDR-PRINT-CHAR CALL-ABS,
    6B %EAX MOV-IMM,
    ADDR-PRINT-CHAR CALL-ABS,
    20 %EAX MOV-IMM,
    ADDR-PRINT-CHAR CALL-ABS,

    \ Read line of input
    ADDR-READ-LINE CALL-ABS,

    \ Set TOIN = 0
    C7 T-C, 05 T-C, 28014 T-, 0 T-,

    \ .have_input:
    FX1 @ >RESOLVE

    \ Parse next word
    ADDR-WORD CALL-ABS,
    %EAX %EAX TEST,
    JZ, FX2 !

    \ Look up in dictionary
    ADDR-FIND CALL-ABS,
    %EAX %EAX TEST,
    JZ, FX3 !

    \ Found: save XT in EBX
    %EAX %EBX MOV,

    \ Check STATE
    28000 %EDX MOV-ABS[],
    %EDX %EDX TEST,
    JZ, FX4 !

    \ Check IMMEDIATE (test cl, 0x80)
    F6 T-C, C1 T-C, 80 T-C,
    JNZ, FX5 !

    \ Compile: call comma_(ebx)
    %EBX %EAX MOV,
    ADDR-COMMA CALL-ABS,
    EMIT-NEXT

    \ .execute_word:
    FX4 @ >RESOLVE
    FX5 @ >RESOLVE
    %EBX %EAX MOV,
    %EAX JMP[],

    \ .try_number:
    FX3 @ >RESOLVE
    ADDR-NUMBER CALL-ABS,
    %EDX %EDX TEST,
    JNZ, FX6 !

    \ Got number: check STATE
    28000 %EDX MOV-ABS[],
    %EDX %EDX TEST,
    JNZ, FX7 !

    \ Interpreting: push number
    %EAX PUSH,
    EMIT-NEXT

    \ .compile_number:
    FX7 @ >RESOLVE
    %EAX PUSH,
    DOLIT-ADDR @ %EAX MOV-IMM,
    ADDR-COMMA CALL-ABS,
    %EAX POP,
    ADDR-COMMA CALL-ABS,
    EMIT-NEXT

    \ .undefined:
    FX6 @ >RESOLVE
    %ESI PUSH,
    ADDR-WORD-BUF %ESI MOV-IMM,
    ADDR-PRINT-STR CALL-ABS,
    ADDR-MSG-UNDEF %ESI MOV-IMM,
    ADDR-PRINT-STR CALL-ABS,
    %ESI POP,
    \ Reset STATE = 0
    C7 T-C, 05 T-C, 28000 T-, 0 T-,
    EMIT-NEXT

    \ .end_of_line:
    FX2 @ >RESOLVE
    END-CODE
;

\ ============================================
\ Phase B6: Cold start + transfer
\ ============================================

: MC-COLDSTART ( -- )
    S" COLD" TX-COLON
    S" INTERPRET" T-COMPILE-NAME
    S" BRANCH" T-COMPILE-NAME
    FFFFFFF8 T-,
    \ No T-; — loops forever
;

\ ============================================
\ Phase B6b: Standalone bootable kernel
\ ============================================
\ Build a disk-bootable metacompiled kernel.
\ Copies the running kernel into T-IMAGE at
\ T-ORG=7E00, overlays metacompiled dictionary
\ in the free space, patches kernel_start init.

\ Scan T-IMAGE for C7 05 <addr32 LE>, patch
\ the following imm32 with new-val.
\ Used to patch mov [VAR_LATEST],X etc.
VARIABLE SP-NEW VARIABLE SP-TGT
: MC-SCAN-PATCH6 ( new-val addr32 -- f )
    SP-TGT ! SP-NEW !
    T-HERE @ T-IMAGE - 6 - 0 DO
        T-IMAGE I + C@ C7 = IF
        T-IMAGE I + 1+ C@ 05 = IF
        T-IMAGE I + 2 + @
        SP-TGT @ = IF
            SP-NEW @
            T-IMAGE I + 6 + !
            -1 UNLOOP EXIT
        THEN THEN THEN
    LOOP 0
;

: MC-PATCH-LATEST ( -- )
    T-LINK-VAR @ 28008
    MC-SCAN-PATCH6
    0= IF ." WARN: LATEST patch fail"
    CR THEN
    T-LINK-VAR @ 28048
    MC-SCAN-PATCH6
    0= IF ." WARN: FORTH_LATEST fail"
    CR THEN
;

: MC-PATCH-COLDSTART ( -- )
    S" INTERPRET" T-FIND-SYM
    DUP 0= IF
        ." WARN: no INTERPRET" CR
        DROP EXIT
    THEN
    ADDR-COLD-START T-!
;

: MC-PATCH-EMBED ( -- )
    0 ADDR-EMBED-SIZE T-!
;

: META-COMPILE-X86-BOOT ( -- )
    META-INIT TSYM-INIT HEX
    \ T-ORG stays 7E00 from META-INIT
    7E00 10000 T-BINARY,
    \ Rewind past kernel code (~B8CD)
    T-IMAGE C000 + T-HERE !
    T-ALIGN
    MC-RUNTIMES MC-LOOP-RT
    MC-STACK MC-ARITH MC-LOGIC
    MC-COMPARE MC-MEMORY MC-DIVISION
    MC-STACK2 MC-PORTIO MC-MEMORY2
    MC-UTILITY MC-IO MC-DISPLAY
    MC-SYSVAR MC-DICT MC-COMPILER
    MC-CONTROLFLOW MC-INTERPRET
    MC-COLDSTART MC-COLON
    META-CHECK
    MC-PATCH-LATEST
    MC-PATCH-COLDSTART
    MC-PATCH-EMBED
    10000 T-SIZE !
    1 META-OK !
    DECIMAL
    ." Phase B6b complete: "
    T-HERE @ T-IMAGE - . ." used, "
    TSYM-N @ . ." syms" CR
;

\ META-TRANSFER: set vars + transfer ctrl
\ No CMOVE needed: T-ORG = T-IMAGE, so code
\ is already at the correct address.
: META-TRANSFER ( -- does not return )
    T-LINK-VAR @ DUP 28048 ! 28008 !
    T-ADDR 28004 !
    0 28000 ! 0 28014 !
    0A 2800C !
    28048 28020 !
    1 28040 !
    28048 28044 !
    S" COLD" T-FIND-SYM EXECUTE
;

\ ---- Top-level build driver ----
: META-COMPILE-X86 ( -- )
    META-INIT TSYM-INIT HEX
    T-IMAGE T-ORG !
    MC-RUNTIMES
    MC-LOOP-RT
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
    MC-IO
    MC-DISPLAY
    MC-SYSVAR
    MC-DICT
    MC-COMPILER
    MC-CONTROLFLOW
    MC-INTERPRET
    MC-COLDSTART
    MC-COLON
    META-CHECK
    T-HERE @ T-IMAGE - T-SIZE !
    1 META-OK !
    DECIMAL
    ." Phase B6 complete: "
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
