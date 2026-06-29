\ ============================================
\ CATALOG: ASM-VOCAB
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ ============================================
\
\ Inline x86-32 assembler vocabulary.
\ MINIMUM TESTABLE SLICE: CODE, END-CODE,
\ NEXT,, PUSH,, POP,, ADD, only.
\ Expand after DUMP-verification in QEMU.
\
\ ============================================

VOCABULARY ASM-VOCAB
ASM-VOCAB DEFINITIONS
HEX

\ ---- Emit to HERE (not T-HERE) ----------
\ C, and , are kernel words (use VAR_HERE
\ directly, so they work correctly).
\ HERE is a VARIABLE in this kernel: it
\ pushes the ADDRESS of the dict pointer
\ (0x28004), not the value. Use HERE @ to
\ get the actual dictionary pointer.
\ W, is net-new: uses HERE @ for address.
: W, ( w -- ) HERE @ W! 2 ALLOT ;

\ ---- Register encoding -------------------
\ Values 0-7, same as x86-asm.fth:37-44.
0 CONSTANT %EAX    1 CONSTANT %ECX
2 CONSTANT %EDX    3 CONSTANT %EBX
4 CONSTANT %ESP    5 CONSTANT %EBP
6 CONSTANT %ESI    7 CONSTANT %EDI

\ ---- ModR/M byte -------------------------
\ ( mod reg rm -- byte )
\ x86-asm.fth:67-70.
: MODRM
    SWAP 3 LSHIFT OR
    SWAP 6 LSHIFT OR
;

\ ---- CODE / END-CODE ---------------------
\ CODE: build header, override CFA to
\ point at HERE (self-ref, like DEFCODE).
\ Then make ASM-VOCAB words findable.
: CODE ( "name" -- )
    CREATE
    HERE @ HERE @ 4 - !
    ALSO
    ['] ASM-VOCAB EXECUTE
;

\ END-CODE: restore search order.
: END-CODE ( -- )
    PREVIOUS
;

\ ---- NEXT, (inline Forth NEXT) -----------
\ forth.asm:166-168: lodsd; jmp [eax]
\ 3 bytes: AD FF 20
: NEXT, ( -- )
    AD C,
    FF C, 20 C,
;

\ ---- PUSH/POP register -------------------
\ x86-asm.fth:63-64.
: PUSH, ( reg -- ) 50 + C, ;
: POP, ( reg -- )  58 + C, ;

\ ---- Single-byte instructions ------------
\ x86-asm.fth:47-61.
: NOP, ( -- )    90 C, ;
: RET, ( -- )    C3 C, ;
: LODSD, ( -- )  AD C, ;
: STOSD, ( -- )  AB C, ;
: CLD, ( -- )    FC C, ;
: STD, ( -- )    FD C, ;
: CLI, ( -- )    FA C, ;
: STI, ( -- )    FB C, ;
: PUSHAD, ( -- ) 60 C, ;
: POPAD, ( -- )  61 C, ;
: PUSHFD, ( -- ) 9C C, ;
: POPFD, ( -- )  9D C, ;
: IRET, ( -- )   CF C, ;
: CDQ, ( -- )    99 C, ;

\ ---- Two-operand reg-reg ALU -------------
\ All: opcode C, MODRM(3,src,dst) C,
\ Same pattern as ADD, (verified C8).
\ x86-asm.fth:73-113.
: ADD, ( src dst -- )
    01 C, 3 -ROT MODRM C,
;
: MOV, ( src dst -- )
    89 C, 3 -ROT MODRM C,
;
: SUB, ( src dst -- )
    29 C, 3 -ROT MODRM C,
;
: XOR, ( src dst -- )
    31 C, 3 -ROT MODRM C,
;
: AND, ( src dst -- )
    21 C, 3 -ROT MODRM C,
;
: OR, ( src dst -- )
    09 C, 3 -ROT MODRM C,
;
: CMP, ( src dst -- )
    39 C, 3 -ROT MODRM C,
;
: TEST, ( src dst -- )
    85 C, 3 -ROT MODRM C,
;

\ ---- MOV reg, imm32 ----------------------
\ x86-asm.fth:88-90.
: MOV-IMM, ( imm32 reg -- )
    B8 + C, ,
;

\ ---- INC/DEC register --------------------
\ x86-asm.fth:124-125.
: INC, ( reg -- ) 40 + C, ;
: DEC, ( reg -- ) 48 + C, ;

\ ---- PUSH immediate ----------------------
\ x86-asm.fth:366.
: PUSH-IMM, ( imm32 -- ) 68 C, , ;

\ ---- NOT/NEG register --------------------
\ Opcode-extension forms: fixed /N in reg
\ field, NOT /2, NEG /3.
\ x86-asm.fth:213-218.
: NOT, ( reg -- )
    F7 C, 3 2 ROT MODRM C,
;
: NEG, ( reg -- )
    F7 C, 3 3 ROT MODRM C,
;

\ ---- Shift by CL -------------------------
\ SHL /4, SHR /5, SAR /7.
\ x86-asm.fth:221-229.
: SHL-CL, ( reg -- )
    D3 C, 3 4 ROT MODRM C,
;
: SHR-CL, ( reg -- )
    D3 C, 3 5 ROT MODRM C,
;
: SAR-CL, ( reg -- )
    D3 C, 3 7 ROT MODRM C,
;

\ ---- ALU reg, imm32 ----------------------
\ ADD-IMM /0, SUB-IMM /5, CMP-IMM /7.
\ x86-asm.fth:116-121.
: ADD-IMM, ( imm32 reg -- )
    81 C, 3 0 ROT MODRM C, ,
;
: SUB-IMM, ( imm32 reg -- )
    81 C, 3 5 ROT MODRM C, ,
;
: CMP-IMM, ( imm32 reg -- )
    81 C, 3 7 ROT MODRM C, ,
;

\ ---- Memory addressing -------------------
\ mod=0 forms: [reg] not reg.
\ x86-asm.fth:78-85.
: MOV[], ( [src] dst -- )
    8B C, 0 -ROT SWAP MODRM C,
;
: []MOV, ( src [dest] -- )
    89 C, 0 -ROT MODRM C,
;

\ ---- IN/OUT (DX-form) --------------------
\ x86-asm.fth:189-194.
: IN-AL-DX, ( -- )  EC C, ;
: IN-EAX-DX, ( -- ) ED C, ;
: OUT-DX-AL, ( -- )  EE C, ;
: OUT-DX-EAX, ( -- ) EF C, ;

\ ---- Condition codes (short Jcc) ---------
\ Short = near second byte - 10h.
\ Cited: x86-asm.fth:146-169 near forms.
74 CONSTANT #JZ     75 CONSTANT #JNZ
72 CONSTANT #JC     73 CONSTANT #JNC
7C CONSTANT #JL     7D CONSTANT #JGE
7E CONSTANT #JLE    7F CONSTANT #JG

\ ---- Structured control flow (rel8) ------
\ rel8 = target - (addr_of_rel8 + 1)
\ Short branches only. No range check for
\ +/-127 limit (known limitation).

\ IF, : emit Jcc opcode + placeholder.
\ Leave fixup = addr of rel8 byte.
: IF, ( cc -- fixup ) C, HERE @ 0 C, ;

\ THEN, : resolve forward fixup.
\ rel8 = HERE@ - fixup - 1
: THEN, ( fixup -- )
    HERE @ OVER - 1 - SWAP C!
;

\ ELSE, : JMP(EB) + new fixup, resolve old.
: ELSE, ( f1 -- f2 )
    EB C, HERE @ 0 C, SWAP THEN,
;

\ BEGIN, : save backward target.
: BEGIN, ( -- dest ) HERE @ ;

\ UNTIL, : Jcc backward to dest.
\ Arrival: BEGIN, pushed dest, cc on top.
\ rel8 = dest - (HERE@ + 1) after opcode.
: UNTIL, ( dest cc -- )
    C, HERE @ 1 + - C,
;

\ WHILE, : IF, with dest preserved.
\ Arrival: ( dest cc ), cc on top.
: WHILE, ( dest cc -- fixup dest )
    IF, SWAP
;

\ REPEAT, : JMP backward + resolve WHILE.
: REPEAT, ( fixup dest -- )
    EB C, HERE @ 1 + - C, THEN,
;

\ ---- DEFERRED INSTRUCTIONS ----------------
\ Not in MVP. Add when a CODE word actually
\ needs it, with a test that exercises it.
\ Do not pre-add unused instructions.
\
\ ALU-IMM (81 /N, same pattern as above):
\   AND-IMM /4, OR-IMM /1, XOR-IMM /6
\ rel32 jumps (fixup-based):
\   JMP, (E9), CALL, (E8), Jcc-near (0F 8x)
\ [ESP] / memory-disp forms:
\   ADD[ESP], SUB[ESP], AND[ESP], CMP[ESP],
\   MOV[ESP], MOV-ESP+, NEG[ESP], INC[ESP]
\ Register+disp8:
\   MOV-DISP!, MOV-DISP@
\ Byte/word ops:
\   MOVZXB[], MOVZXW[], []MOV-B, []MOV-W
\ Multiply/divide:
\   IMUL1, IDIV, UDIV1
\ REP string:
\   REP-MOVSB, REP-STOSB, REP-STOSD
\ SETcc:
\   SETE, SETNE, SETL, SETG, SETLE, SETGE
\ Absolute addressing:
\   []ABS-MOV, MOV-ABS[]

FORTH DEFINITIONS
DECIMAL
