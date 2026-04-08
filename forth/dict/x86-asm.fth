\ ============================================
\ CATALOG: X86-ASM
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ ============================================
\
\ Minimal x86 assembler for metacompiler.
\ Emits machine code to target buffer.
\
\ Usage:
\   USING X86-ASM
\   %EAX PUSH,
\   %ESI %EAX MOV,
\
\ ============================================

VOCABULARY X86-ASM
X86-ASM DEFINITIONS
HEX

\ ---- Target memory pointer ----
VARIABLE T-HERE-VAR
: T-HERE T-HERE-VAR ;
: T-C, ( byte -- )
    T-HERE @ C! 1 T-HERE +!
;
: T-, ( cell -- )
    T-HERE @ ! 4 T-HERE +!
;
: T-W, ( word -- )
    T-HERE @ W! 2 T-HERE +!
;

\ ---- Register encoding ----
0 CONSTANT %EAX
1 CONSTANT %ECX
2 CONSTANT %EDX
3 CONSTANT %EBX
4 CONSTANT %ESP
5 CONSTANT %EBP
6 CONSTANT %ESI
7 CONSTANT %EDI

\ ---- Single-byte instructions ----
: NOP, ( -- )    90 T-C, ;
: RET, ( -- )    C3 T-C, ;
: LODSD, ( -- )  AD T-C, ;
: STOSD, ( -- )  AB T-C, ;
: CLD, ( -- )    FC T-C, ;
: STD, ( -- )    FD T-C, ;
: CLI, ( -- )    FA T-C, ;
: STI, ( -- )    FB T-C, ;
: PUSHAD, ( -- ) 60 T-C, ;
: POPAD, ( -- )  61 T-C, ;
: PUSHFD, ( -- ) 9C T-C, ;
: POPFD, ( -- )  9D T-C, ;
: IRET, ( -- )   CF T-C, ;
: CDQ, ( -- )    99 T-C, ;

\ ---- PUSH/POP register ----
: PUSH, ( reg -- ) 50 + T-C, ;
: POP, ( reg -- )  58 + T-C, ;

\ ---- ModR/M byte ----
: MODRM ( mod reg rm -- byte )
    SWAP 3 LSHIFT OR
    SWAP 6 LSHIFT OR
;

\ ---- MOV reg, reg ----
: MOV, ( src dst -- )
    89 T-C, 3 -ROT MODRM T-C,
;

\ ---- MOV reg, [reg] ----
: MOV[], ( [src] dst -- )
    8B T-C, 0 -ROT SWAP MODRM T-C,
;

\ ---- MOV [reg], reg ----
: []MOV, ( src [dest] -- )
    89 T-C, 0 -ROT MODRM T-C,
;

\ ---- MOV reg, imm32 ----
: MOV-IMM, ( imm32 reg -- )
    B8 + T-C, T-,
;

\ ---- ALU reg, reg ----
: ADD, ( src dst -- )
    01 T-C, 3 -ROT MODRM T-C,
;
: SUB, ( src dst -- )
    29 T-C, 3 -ROT MODRM T-C,
;
: XOR, ( src dst -- )
    31 T-C, 3 -ROT MODRM T-C,
;
: AND, ( src dst -- )
    21 T-C, 3 -ROT MODRM T-C,
;
: OR, ( src dst -- )
    09 T-C, 3 -ROT MODRM T-C,
;
: CMP, ( src dst -- )
    39 T-C, 3 -ROT MODRM T-C,
;
: TEST, ( src dst -- )
    85 T-C, 3 -ROT MODRM T-C,
;

\ ---- ALU reg, imm32 ----
: ADD-IMM, ( imm32 reg -- )
    81 T-C, 3 0 ROT MODRM T-C, T-,
;
: SUB-IMM, ( imm32 reg -- )
    81 T-C, 3 5 ROT MODRM T-C, T-,
;

\ ---- INC/DEC reg ----
: INC, ( reg -- ) 40 + T-C, ;
: DEC, ( reg -- ) 48 + T-C, ;

\ ---- JMP [reg] (indirect) ----
: JMP[], ( reg -- )
    FF T-C, 0 4 ROT MODRM T-C,
;

\ ---- JMP rel32 ----
: JMP, ( -- fixup )
    E9 T-C, T-HERE @ 0 T-,
;
: >RESOLVE ( fixup -- )
    T-HERE @ OVER - 4 - SWAP !
;

\ ---- CALL rel32 ----
: CALL, ( -- fixup )
    E8 T-C, T-HERE @ 0 T-,
;

\ ---- Jcc rel32 (conditional jumps) ----
: JZ, ( -- fixup )
    0F T-C, 84 T-C, T-HERE @ 0 T-,
;
: JNZ, ( -- fixup )
    0F T-C, 85 T-C, T-HERE @ 0 T-,
;
: JL, ( -- fixup )
    0F T-C, 8C T-C, T-HERE @ 0 T-,
;
: JGE, ( -- fixup )
    0F T-C, 8D T-C, T-HERE @ 0 T-,
;
: JNS, ( -- fixup )
    0F T-C, 89 T-C, T-HERE @ 0 T-,
;
: JS, ( -- fixup )
    0F T-C, 88 T-C, T-HERE @ 0 T-,
;
: JG, ( -- fixup )
    0F T-C, 8F T-C, T-HERE @ 0 T-,
;
: JLE, ( -- fixup )
    0F T-C, 8E T-C, T-HERE @ 0 T-,
;

\ ---- MOV [reg+disp8], reg ----
VARIABLE DISP-TMP
: MOV-DISP!, ( src [base] disp -- )
    DISP-TMP !
    89 T-C,
    1 -ROT MODRM T-C,
    DISP-TMP @ T-C,
;

\ ---- MOV reg, [reg+disp8] ----
: MOV-DISP@, ( [base] dst disp -- )
    DISP-TMP !
    8B T-C,
    1 -ROT SWAP MODRM T-C,
    DISP-TMP @ T-C,
;

\ ---- IN/OUT ----
: IN-AL-DX, ( -- )  EC T-C, ;
: IN-AX-DX, ( -- )  66 T-C, ED T-C, ;
: IN-EAX-DX, ( -- ) ED T-C, ;
: OUT-DX-AL, ( -- )  EE T-C, ;
: OUT-DX-AX, ( -- )  66 T-C, EF T-C, ;
: OUT-DX-EAX, ( -- ) EF T-C, ;

\ ---- REP string ops ----
: REP-INSW, ( -- )
    F3 T-C, 66 T-C, 6D T-C,
;
: REP-OUTSW, ( -- )
    F3 T-C, 66 T-C, 6F T-C,
;
: REP-STOSD, ( -- )
    F3 T-C, AB T-C,
;

\ ---- IDIV reg ----
: IDIV, ( reg -- )
    F7 T-C, 3 7 ROT MODRM T-C,
;

\ ---- NOT/NEG reg ----
: NOT, ( reg -- )
    F7 T-C, 3 2 ROT MODRM T-C,
;
: NEG, ( reg -- )
    F7 T-C, 3 3 ROT MODRM T-C,
;

\ ---- SHL/SHR by CL ----
: SHL-CL, ( reg -- )
    D3 T-C, 3 4 ROT MODRM T-C,
;
: SHR-CL, ( reg -- )
    D3 T-C, 3 5 ROT MODRM T-C,
;
: SAR-CL, ( reg -- )
    D3 T-C, 3 7 ROT MODRM T-C,
;

\ ---- Imm8 ALU forms (compact) ----
: ADD-I8, ( imm8 reg -- )
    83 T-C, 3 0 ROT MODRM T-C, T-C,
;
: SUB-I8, ( imm8 reg -- )
    83 T-C, 3 5 ROT MODRM T-C, T-C,
;
: CMP-I8, ( imm8 reg -- )
    83 T-C, 3 7 ROT MODRM T-C, T-C,
;

\ ---- [ESP] ops (need SIB byte 24) ----
: ADD[ESP], ( reg -- )
    01 T-C, 0 SWAP 4 MODRM T-C,
    24 T-C,
;
: SUB[ESP], ( reg -- )
    29 T-C, 0 SWAP 4 MODRM T-C,
    24 T-C,
;
: AND[ESP], ( reg -- )
    21 T-C, 0 SWAP 4 MODRM T-C,
    24 T-C,
;
: OR[ESP], ( reg -- )
    09 T-C, 0 SWAP 4 MODRM T-C,
    24 T-C,
;
: XOR[ESP], ( reg -- )
    31 T-C, 0 SWAP 4 MODRM T-C,
    24 T-C,
;
: CMP[ESP], ( reg -- )
    39 T-C, 0 SWAP 4 MODRM T-C,
    24 T-C,
;
\ mov reg,[esp]
: MOV[ESP], ( dst -- )
    8B T-C, 0 SWAP 4 MODRM T-C,
    24 T-C,
;
\ mov reg,[esp+disp8]
: MOV-ESP+, ( dst disp -- )
    SWAP 8B T-C,
    1 SWAP 4 MODRM T-C, 24 T-C, T-C,
;

\ ---- Unary [ESP] ----
: NEG[ESP], ( -- )
    F7 T-C, 1C T-C, 24 T-C, ;
: NOT[ESP], ( -- )
    F7 T-C, 14 T-C, 24 T-C, ;
: INC[ESP], ( -- )
    FF T-C, 04 T-C, 24 T-C, ;
: DEC[ESP], ( -- )
    FF T-C, 0C T-C, 24 T-C, ;

\ ---- push [reg+disp8] (DOCON) ----
: PUSH-D8, ( reg disp -- )
    DISP-TMP !
    FF T-C, 1 6 ROT MODRM T-C,
    DISP-TMP @ T-C,
;

\ ---- lea dst,[src+disp8] (DOCREATE) ----
: LEA-D8, ( src dst disp -- )
    DISP-TMP !
    8D T-C,
    SWAP 1 -ROT MODRM T-C,
    DISP-TMP @ T-C,
;

\ ---- movzx reg,byte [reg] (C@) ----
: MOVZXB[], ( [src] dst -- )
    0F T-C, B6 T-C,
    0 -ROT SWAP MODRM T-C,
;
\ movzx eax,al
: MOVZX-AL, ( -- )
    0F T-C, B6 T-C, C0 T-C, ;

\ ---- add reg,[reg] (BRANCH) ----
: ADD[], ( [src] dst -- )
    03 T-C, 0 -ROT SWAP MODRM T-C,
;

\ ---- mov [reg],reg8 (C!) ----
: []MOV-B, ( src8 [dest] -- )
    88 T-C, 0 -ROT MODRM T-C,
;

\ ---- one-operand imul (*) ----
: IMUL1, ( reg -- )
    F7 T-C, 3 5 ROT MODRM T-C,
;

\ ---- setcc al (comparisons) ----
: SETE, ( -- )
    0F T-C, 94 T-C, C0 T-C, ;
: SETNE, ( -- )
    0F T-C, 95 T-C, C0 T-C, ;
: SETL, ( -- )
    0F T-C, 9C T-C, C0 T-C, ;
: SETG, ( -- )
    0F T-C, 9F T-C, C0 T-C, ;
: SETLE, ( -- )
    0F T-C, 9E T-C, C0 T-C, ;
: SETGE, ( -- )
    0F T-C, 9D T-C, C0 T-C, ;

\ ---- shl/shr [esp],cl (LSHIFT/RSHIFT) ----
: SHL-CL[ESP], ( -- )
    D3 T-C, 24 T-C, 24 T-C, ;
: SHR-CL[ESP], ( -- )
    D3 T-C, 2C T-C, 24 T-C, ;

\ ---- sets al (0<) ----
: SETS, ( -- )
    0F T-C, 98 T-C, C0 T-C, ;

\ ---- absolute addressing ----
\ mov [imm32],reg
: []ABS-MOV, ( reg addr -- )
    89 T-C, 0 ROT 5 MODRM T-C, T-,
;
\ mov reg,[imm32]
: MOV-ABS[], ( addr dst -- )
    8B T-C, 0 SWAP 5 MODRM T-C, T-,
;

\ ---- unsigned div (F7 /6) ----
: UDIV1, ( reg -- )
    F7 T-C, 3 6 ROT MODRM T-C, ;

\ ---- push imm32 ----
: PUSH-IMM, ( imm32 -- ) 68 T-C, T-, ;

\ ---- movzx reg, word [reg] (W@) ----
: MOVZXW[], ( [src] dst -- )
    0F T-C, B7 T-C,
    0 -ROT SWAP MODRM T-C, ;

\ ---- mov [reg], reg16 (W!) ----
: []MOV-W, ( src16 [dest] -- )
    66 T-C, 89 T-C,
    0 -ROT MODRM T-C, ;

\ ---- rep string ops ----
: REP-MOVSB, ( -- ) F3 T-C, A4 T-C, ;
: REP-STOSB, ( -- ) F3 T-C, AA T-C, ;

FORTH DEFINITIONS
DECIMAL
