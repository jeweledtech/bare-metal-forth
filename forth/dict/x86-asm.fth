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
    81 T-C, 3 SWAP 0 MODRM T-C, T-,
;
: SUB-IMM, ( imm32 reg -- )
    81 T-C, 3 SWAP 5 MODRM T-C, T-,
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

\ ---- MOV [reg+disp8], reg ----
VARIABLE DISP-TMP
: MOV-DISP!, ( src [base] disp -- )
    DISP-TMP !
    89 T-C,
    DUP 5 = IF
        2 -ROT MODRM T-C,
    ELSE
        1 -ROT MODRM T-C,
    THEN
    DISP-TMP @ T-C,
;

\ ---- MOV reg, [reg+disp8] ----
: MOV-DISP@, ( [base] dst disp -- )
    DISP-TMP !
    8B T-C,
    OVER 5 = IF
        2 -ROT SWAP MODRM T-C,
    ELSE
        1 -ROT SWAP MODRM T-C,
    THEN
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
    F7 T-C, 3 SWAP 7 MODRM T-C,
;

\ ---- NOT/NEG reg ----
: NOT, ( reg -- )
    F7 T-C, 3 SWAP 2 MODRM T-C,
;
: NEG, ( reg -- )
    F7 T-C, 3 SWAP 3 MODRM T-C,
;

\ ---- SHL/SHR by CL ----
: SHL-CL, ( reg -- )
    D3 T-C, 3 SWAP 4 MODRM T-C,
;
: SHR-CL, ( reg -- )
    D3 T-C, 3 SWAP 5 MODRM T-C,
;
: SAR-CL, ( reg -- )
    D3 T-C, 3 SWAP 7 MODRM T-C,
;

FORTH DEFINITIONS
DECIMAL
