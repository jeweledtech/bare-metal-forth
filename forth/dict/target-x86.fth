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
\ Build driver: META-COMPILE-X86
\ ============================================
\ Emits ~40 CODE words into T-IMAGE.
\ Phase B1: stack, arith, logic, memory,
\ comparison, control-flow runtimes.

VARIABLE BRANCH-CODE

: MC-RUNTIMES ( -- )
    \ DOCOL (raw code, no dict entry)
    T-ALIGN
    T-ADDR DOCOL-ADDR !
    EMIT-DOCOL

    \ EXIT
    S" EXIT" T-CODE
    T-ADDR 4 - DOEXIT-ADDR !
    EMIT-EXIT

    \ LIT
    S" LIT" T-CODE
    T-ADDR 4 - DOLIT-ADDR !
    EMIT-LIT

    \ BRANCH: add esi,[esi]; NEXT
    S" BRANCH" T-CODE
    T-ADDR 4 - DOBRANCH-ADDR !
    T-ADDR BRANCH-CODE !
    %ESI %ESI ADD[],
    END-CODE

    \ 0BRANCH: pop; test; jz BRANCH;
    \          add esi,4; NEXT
    S" 0BRANCH" T-CODE
    T-ADDR 4 - DO0BRANCH-ADDR !
    %EAX POP,
    %EAX %EAX TEST,
    \ jz to BRANCH code
    0F T-C, 84 T-C,
    BRANCH-CODE @ T-ADDR - 4 - T-,
    4 %ESI ADD-I8,
    END-CODE

    \ DOCON
    S" DOCON" T-CODE
    T-ADDR DOCON-ADDR !
    EMIT-DOCON

    \ DOCREATE
    S" DOCREATE" T-CODE
    T-ADDR DOCREATE-ADDR !
    EMIT-DOCREATE

    \ EXECUTE: pop eax; jmp [eax]
    S" EXECUTE" T-CODE
    %EAX POP,
    %EAX JMP[],
;

: MC-STACK ( -- )
    S" DROP" T-CODE
    %EAX POP, END-CODE

    S" DUP" T-CODE
    %EAX MOV[ESP],
    %EAX PUSH, END-CODE

    S" SWAP" T-CODE
    %EAX POP, %EBX POP,
    %EAX PUSH, %EBX PUSH,
    END-CODE

    S" OVER" T-CODE
    %EAX 4 MOV-ESP+,
    %EAX PUSH, END-CODE

    S" ROT" T-CODE
    %EAX POP, %EBX POP, %ECX POP,
    %EBX PUSH, %EAX PUSH,
    %ECX PUSH, END-CODE

    S" -ROT" T-CODE
    %EAX POP, %EBX POP, %ECX POP,
    %EAX PUSH, %ECX PUSH,
    %EBX PUSH, END-CODE

    S" 2DROP" T-CODE
    %EAX POP, %EAX POP, END-CODE

    S" 2DUP" T-CODE
    %EAX MOV[ESP],
    %EBX 4 MOV-ESP+,
    %EBX PUSH, %EAX PUSH,
    END-CODE

    S" ?DUP" T-CODE
    %EAX MOV[ESP],
    %EAX %EAX TEST,
    JZ, %EAX PUSH, SWAP >RESOLVE
    END-CODE

    S" NIP" T-CODE
    %EAX POP, %EBX POP,
    %EAX PUSH, END-CODE

    S" TUCK" T-CODE
    %EAX POP, %EBX POP,
    %EAX PUSH, %EBX PUSH,
    %EAX PUSH, END-CODE

    S" DEPTH" T-CODE
    7C00 %EAX MOV-IMM,
    %ESP %EAX SUB,
    \ shr eax, 2 (C1 E8 02)
    C1 T-C, E8 T-C, 2 T-C,
    %EAX PUSH, END-CODE

    \ Return stack
    S" >R" T-CODE
    %EAX POP,
    %EAX EMIT-PUSHRSP
    END-CODE

    S" R>" T-CODE
    %EAX EMIT-POPRSP
    %EAX PUSH, END-CODE

    S" R@" T-CODE
    %EBP %EAX 0 MOV-DISP@,
    %EAX PUSH, END-CODE

    S" RDROP" T-CODE
    4 %EBP ADD-I8, END-CODE
;

: MC-ARITH ( -- )
    S" +" T-CODE
    %EAX POP, %EAX ADD[ESP], END-CODE

    S" -" T-CODE
    %EAX POP, %EAX SUB[ESP], END-CODE

    S" *" T-CODE
    %EAX POP, %EBX POP,
    %EBX IMUL1,
    %EAX PUSH, END-CODE

    S" 1+" T-CODE INC[ESP], END-CODE
    S" 1-" T-CODE DEC[ESP], END-CODE

    S" 2+" T-CODE
    INC[ESP], INC[ESP], END-CODE

    S" 2-" T-CODE
    DEC[ESP], DEC[ESP], END-CODE

    S" NEGATE" T-CODE
    NEG[ESP], END-CODE

    S" ABS" T-CODE
    %EAX MOV[ESP],
    %EAX %EAX TEST,
    JNS, NEG[ESP], SWAP >RESOLVE
    END-CODE
;

: MC-LOGIC ( -- )
    S" AND" T-CODE
    %EAX POP, %EAX AND[ESP], END-CODE

    S" OR" T-CODE
    %EAX POP, %EAX OR[ESP], END-CODE

    S" XOR" T-CODE
    %EAX POP, %EAX XOR[ESP], END-CODE

    S" INVERT" T-CODE
    NOT[ESP], END-CODE

    S" LSHIFT" T-CODE
    %ECX POP, SHL-CL[ESP], END-CODE

    S" RSHIFT" T-CODE
    %ECX POP, SHR-CL[ESP], END-CODE
;

: MC-COMPARE ( -- )
    S" =" T-CODE
    %EAX POP, %EBX POP,
    %EAX %EBX CMP,
    SETE, MOVZX-AL, %EAX NEG,
    %EAX PUSH, END-CODE

    S" <>" T-CODE
    %EAX POP, %EBX POP,
    %EAX %EBX CMP,
    SETNE, MOVZX-AL, %EAX NEG,
    %EAX PUSH, END-CODE

    S" <" T-CODE
    %EAX POP, %EBX POP,
    %EAX %EBX CMP,
    SETL, MOVZX-AL, %EAX NEG,
    %EAX PUSH, END-CODE

    S" >" T-CODE
    %EAX POP, %EBX POP,
    %EAX %EBX CMP,
    SETG, MOVZX-AL, %EAX NEG,
    %EAX PUSH, END-CODE

    S" 0=" T-CODE
    %EAX POP, %EAX %EAX TEST,
    SETE, MOVZX-AL, %EAX NEG,
    %EAX PUSH, END-CODE

    S" 0<>" T-CODE
    %EAX POP, %EAX %EAX TEST,
    SETNE, MOVZX-AL, %EAX NEG,
    %EAX PUSH, END-CODE

    S" 0<" T-CODE
    %EAX POP, %EAX %EAX TEST,
    SETS, MOVZX-AL, %EAX NEG,
    %EAX PUSH, END-CODE

    S" 0>" T-CODE
    %EAX POP, %EAX %EAX TEST,
    SETG, MOVZX-AL, %EAX NEG,
    %EAX PUSH, END-CODE
;

: MC-MEMORY ( -- )
    S" @" T-CODE
    %EAX POP,
    %EAX %EAX MOV[],
    %EAX PUSH, END-CODE

    S" !" T-CODE
    %EBX POP, %EAX POP,
    %EAX %EBX []MOV, END-CODE

    S" C@" T-CODE
    %EAX POP,
    %EAX %EAX MOVZXB[],
    %EAX PUSH, END-CODE

    S" C!" T-CODE
    %EBX POP, %EAX POP,
    %EAX %EBX []MOV-B, END-CODE

    S" +!" T-CODE
    %EBX POP, %EAX POP,
    \ add [ebx],eax (01 03)
    01 T-C, 0 %EAX %EBX MODRM T-C,
    END-CODE

    S" -!" T-CODE
    %EBX POP, %EAX POP,
    \ sub [ebx],eax (29 03)
    29 T-C, 0 %EAX %EBX MODRM T-C,
    END-CODE

    S" CMOVE" T-CODE
    %ESI EMIT-PUSHRSP
    %ECX POP, %EDI POP, %ESI POP,
    REP-MOVSB,
    %ESI EMIT-POPRSP
    END-CODE

    S" FILL" T-CODE
    %EAX POP, %ECX POP, %EDI POP,
    REP-STOSB, END-CODE
;

\ ---- Top-level build driver ----
: META-COMPILE-X86 ( -- )
    META-INIT HEX
    MC-RUNTIMES
    MC-STACK
    MC-ARITH
    MC-LOGIC
    MC-COMPARE
    MC-MEMORY
    META-CHECK
    T-HERE @ T-IMAGE - T-SIZE !
    1 META-OK !
    DECIMAL
    ." Phase B1 complete: "
    META-SIZE . ." bytes" CR
;

PREVIOUS PREVIOUS PREVIOUS
FORTH DEFINITIONS
DECIMAL
