\ ============================================
\ CATALOG: DISASM
\ CATEGORY: tools
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ ============================================
\
\ In-system disassembler for ForthOS.
\ Examines live memory from the Forth prompt.
\ Decompiles colon definitions (threaded
\ word lists) and native CODE words (x86).
\
\ Inspired by the LMI UR/Forth DISASM
\ architecture (Ray Duncan, DDJ Feb 1982).
\
\ Usage:
\   USING DISASM
\   DIS SQUARE       \ decompile a colon def
\   DIS DUP          \ disassemble CODE word
\   DIS BASE         \ show variable body
\   DIS TRUE         \ show constant value
\   DIS FORTH        \ identify vocabulary
\
\ ============================================

VOCABULARY DISASM
DISASM DEFINITIONS
HEX

\ Quote char (22h) — can't use \" in ."
DECIMAL 34 CONSTANT QC HEX
: .QC  QC EMIT ;

\ ============================================
\ Section A: Runtime Address Detection
\ ============================================
\ Capture CFA contents from throwaway words
\ to identify word types at runtime.

: _D ;
VARIABLE DCOL-A
' _D @ DCOL-A !

DECIMAL 42 CONSTANT _DC HEX
VARIABLE DCON-A
' _DC @ DCON-A !

VARIABLE _DCV
VARIABLE DCRE-A
' _DCV @ DCRE-A !

VOCABULARY _DV
VARIABLE DVOC-A
' _DV @ DVOC-A !

\ ---- Type predicates ----
: COLON?   ( xt -- flag )  @ DCOL-A @ = ;
: CONST?   ( xt -- flag )  @ DCON-A @ = ;
: CREATE?  ( xt -- flag )  @ DCRE-A @ = ;
: VOCAB?   ( xt -- flag )  @ DVOC-A @ = ;

\ ============================================
\ Section B: Dictionary Navigation
\ ============================================

\ System addresses
28008 CONSTANT V-LAT
28004 CONSTANT V-HR

\ LINK>CFA: from link addr to code field
\ Layout: [link(4)][flags+len(1)][name][pad]
\ Skip link, read len, add, align to 4
: LINK>CFA  ( link -- cfa )
    4 + DUP C@ 3F AND + 1+ 3 + -4 AND
;

\ >NAME: find link addr whose CFA matches
\ Walk dictionary from LATEST backward
VARIABLE NM-TMP
: >NAME  ( cfa -- link | 0 )
    NM-TMP !
    V-LAT @
    BEGIN
        DUP 0<> WHILE
        DUP LINK>CFA NM-TMP @ = IF
            EXIT
        THEN
        @
    REPEAT
;

\ ID.: print the name of a word given link
\ Skip link(4), read flags byte for length
: ID.  ( link -- )
    DUP 0= IF DROP EXIT THEN
    4 + DUP C@ 3F AND
    SWAP 1+ SWAP TYPE
;

\ ============================================
\ Section C: Threaded Code Decompiler
\ ============================================

\ Capture XTs for special compile words
VARIABLE XT-LIT
VARIABLE XT-BRAN
VARIABLE XT-0BR
VARIABLE XT-EXIT
VARIABLE XT-SQ
VARIABLE XT-LOOP
VARIABLE XT-PLOOP

' LIT    XT-LIT   !
' BRANCH XT-BRAN  !
' 0BRANCH XT-0BR  !
' EXIT   XT-EXIT  !
' (S")   XT-SQ    !
' (LOOP) XT-LOOP  !
' (+LOOP) XT-PLOOP !

\ (PC): decode one cell from param field
\ Returns next address to decode
VARIABLE PC-TMP
: (PC)  ( addr -- next-addr )
    DUP @ PC-TMP !
    \ Check LIT
    PC-TMP @ XT-LIT @ = IF
        ." LIT "
        4 + DUP @ DECIMAL . HEX
        4 + EXIT
    THEN
    \ Check BRANCH
    PC-TMP @ XT-BRAN @ = IF
        ." BRANCH "
        4 + DUP @ DECIMAL . HEX
        4 + EXIT
    THEN
    \ Check 0BRANCH
    PC-TMP @ XT-0BR @ = IF
        ." 0BRANCH "
        4 + DUP @ DECIMAL . HEX
        4 + EXIT
    THEN
    \ Check (S")
    PC-TMP @ XT-SQ @ = IF
        ." S" .QC ."  "
        4 + DUP @
        OVER 4 + SWAP TYPE
        .QC ."  "
        DUP @ 4 + + 3 + -4 AND
        EXIT
    THEN
    \ Check (LOOP)
    PC-TMP @ XT-LOOP @ = IF
        ." (LOOP) "
        4 + DUP @ DECIMAL . HEX
        4 + EXIT
    THEN
    \ Check (+LOOP)
    PC-TMP @ XT-PLOOP @ = IF
        ." (+LOOP) "
        4 + DUP @ DECIMAL . HEX
        4 + EXIT
    THEN
    \ Check EXIT
    PC-TMP @ XT-EXIT @ = IF
        ." EXIT"
        4 + EXIT
    THEN
    \ General XT: look up name
    PC-TMP @ >NAME DUP IF
        ID. ."  "
    ELSE
        DROP PC-TMP @ ." [" . ." ] "
    THEN
    4 +
;

\ DECOMP: decompile a colon definition
: DECOMP  ( cfa -- )
    ." : "
    DUP >NAME DUP IF
        ID.
    ELSE
        DROP
    THEN
    ."  "
    4 +
    BEGIN
        DUP @ XT-EXIT @ = IF
            ." ;" CR DROP EXIT
        THEN
        (PC)
    AGAIN
;

\ ============================================
\ Section D: x86 Machine Code Decoder
\ ============================================
\ All numeric constants outside colon defs
\ to avoid HEX/DECIMAL parse bug (#20).

\ --- Single-byte opcodes ---
90 CONSTANT OP-NOP
C3 CONSTANT OP-RET
AD CONSTANT OP-LODSB4
FC CONSTANT OP-CLD
FD CONSTANT OP-STD
9C CONSTANT OP-PUSHF
9D CONSTANT OP-POPF
F4 CONSTANT OP-HLT
CC CONSTANT OP-INT3
CF CONSTANT OP-IRET
FB CONSTANT OP-STI
FA CONSTANT OP-CLI

\ --- Prefix/range boundaries ---
50 CONSTANT OP-PUSH-B
58 CONSTANT OP-POP-B
40 CONSTANT OP-INC-B
48 CONSTANT OP-DEC-B

\ --- Two-operand opcodes ---
89 CONSTANT OP-MOV-RM
8B CONSTANT OP-MOV-RRM
8D CONSTANT OP-LEA
01 CONSTANT OP-ADD-RM
29 CONSTANT OP-SUB-RM
21 CONSTANT OP-AND-RM
09 CONSTANT OP-OR-RM
31 CONSTANT OP-XOR-RM
39 CONSTANT OP-CMP-RM
3B CONSTANT OP-CMP-RRM
85 CONSTANT OP-TEST-RM

\ --- Immediate opcodes ---
83 CONSTANT OP-ALU-I8
81 CONSTANT OP-ALU-I32

\ --- Call/Jump ---
E8 CONSTANT OP-CALL
E9 CONSTANT OP-JMP32
EB CONSTANT OP-JMP8
CD CONSTANT OP-INT

\ --- Short conditional jumps ---
74 CONSTANT OP-JZ8
75 CONSTANT OP-JNZ8
72 CONSTANT OP-JB8
73 CONSTANT OP-JAE8
76 CONSTANT OP-JBE8
77 CONSTANT OP-JA8
7C CONSTANT OP-JL8
7D CONSTANT OP-JGE8
7E CONSTANT OP-JLE8
7F CONSTANT OP-JG8

\ --- Unary group (F7) ---
F7 CONSTANT OP-UNARY

\ --- 0F prefix ---
0F CONSTANT OP-0F
84 CONSTANT OP-0F-JZ
85 CONSTANT OP-0F-JNZ
B6 CONSTANT OP-0F-MOVZX8
B7 CONSTANT OP-0F-MOVZX16

\ --- Other ---
FF CONSTANT OP-FF-GRP
C7 CONSTANT OP-MOV-IMM
B8 CONSTANT OP-MOV-EAX-I

\ NEXT pattern: AD FF 20
\ LODSD; JMP [EAX] = AD FF 20
DECIMAL
173 CONSTANT NEXT-AD
255 CONSTANT NEXT-FF
32 CONSTANT NEXT-20
HEX

\ --- Decode state ---
VARIABLE DIS-PC

\ Read byte at DIS-PC, advance
: DIS-B@  ( -- byte )
    DIS-PC @ C@
    1 DIS-PC +!
;

\ Read dword at DIS-PC, advance
: DIS-L@  ( -- dword )
    DIS-PC @ @
    4 DIS-PC +!
;

\ NEXT? : check for AD FF 20 pattern
: NEXT?  ( addr -- flag )
    DUP C@ NEXT-AD = IF
        DUP 1+ C@ NEXT-FF = IF
            2 + C@ NEXT-20 =
            EXIT
        THEN
    THEN
    DROP FALSE
;

\ Register name table (8 regs, 3 chars)
CREATE REG-TBL
DECIMAL
69 C, 97 C, 120 C,
99 C, 120 C, 0 C,
100 C, 120 C, 0 C,
98 C, 120 C, 0 C,
115 C, 112 C, 0 C,
98 C, 112 C, 0 C,
115 C, 105 C, 0 C,
100 C, 105 C, 0 C,
HEX

\ Print register name by index (0-7)
: .REG  ( n -- )
    3 * REG-TBL +
    3 0 DO
        DUP C@ DUP IF EMIT ELSE DROP THEN
        1+
    LOOP
    DROP
;

\ ModR/M field extraction
: MODRM-MOD  ( byte -- mod )
    6 RSHIFT 3 AND ;
: MODRM-REG  ( byte -- reg )
    3 RSHIFT 7 AND ;
: MODRM-RM   ( byte -- rm )
    7 AND ;

\ Print [reg] or reg based on mod field
: .MODRM  ( modrm -- )
    DUP MODRM-MOD
    DUP 3 = IF
        DROP MODRM-RM .REG EXIT
    THEN
    DUP 0 = IF
        DROP
        DUP MODRM-RM
        DUP 5 = IF
            DROP DROP
            ." [" DIS-L@ . ." ]" EXIT
        THEN
        ." [" .REG ." ]"
        DROP EXIT
    THEN
    DUP 1 = IF
        DROP
        ." [" DUP MODRM-RM .REG
        ." +" DIS-B@ DECIMAL . HEX ." ]"
        DROP EXIT
    THEN
    DROP
    ." [" DUP MODRM-RM .REG
    ." +" DIS-L@ . ." ]"
    DROP
;

\ ALU op name from reg field
: .ALU  ( reg-field -- )
    DUP 0 = IF DROP ." ADD" EXIT THEN
    DUP 1 = IF DROP ." OR"  EXIT THEN
    DUP 2 = IF DROP ." ADC" EXIT THEN
    DUP 3 = IF DROP ." SBB" EXIT THEN
    DUP 4 = IF DROP ." AND" EXIT THEN
    DUP 5 = IF DROP ." SUB" EXIT THEN
    DUP 6 = IF DROP ." XOR" EXIT THEN
    DROP ." CMP"
;

\ Unary op name from reg field (F7)
: .UNARY  ( reg-field -- )
    DUP 2 = IF DROP ." NOT" EXIT THEN
    DUP 3 = IF DROP ." NEG" EXIT THEN
    DUP 4 = IF DROP ." MUL" EXIT THEN
    DUP 6 = IF DROP ." DIV" EXIT THEN
    DUP 7 = IF DROP ." IDIV" EXIT THEN
    DROP ." F7/"
;

\ Print hex byte (2 digits, leading zero)
: .H2  ( byte -- )
    DUP F0 AND 4 RSHIFT
    DUP A < IF
        DECIMAL 48 + EMIT HEX
    ELSE
        DECIMAL 55 + EMIT HEX
    THEN
    F AND
    DUP A < IF
        DECIMAL 48 + EMIT HEX
    ELSE
        DECIMAL 55 + EMIT HEX
    THEN
;

\ DIS-1: decode one x86 instruction
\ Returns 0 to continue, 1 to stop
VARIABLE DIS-OP
: DIS-1  ( -- stop-flag )
    \ Print address
    DIS-PC @ . ." : "
    DIS-B@ DIS-OP !
    DIS-OP @

    \ --- NOP ---
    DUP OP-NOP = IF
        DROP ." NOP" CR 0 EXIT
    THEN

    \ --- RET ---
    DUP OP-RET = IF
        DROP ." RET" CR 1 EXIT
    THEN

    \ --- HLT ---
    DUP OP-HLT = IF
        DROP ." HLT" CR 1 EXIT
    THEN

    \ --- INT3 ---
    DUP OP-INT3 = IF
        DROP ." INT3" CR 0 EXIT
    THEN

    \ --- IRET ---
    DUP OP-IRET = IF
        DROP ." IRET" CR 1 EXIT
    THEN

    \ --- STI / CLI ---
    DUP OP-STI = IF
        DROP ." STI" CR 0 EXIT
    THEN
    DUP OP-CLI = IF
        DROP ." CLI" CR 0 EXIT
    THEN

    \ --- LODSD ---
    DUP OP-LODSB4 = IF
        DROP ." LODSD" CR 0 EXIT
    THEN

    \ --- CLD / STD ---
    DUP OP-CLD = IF
        DROP ." CLD" CR 0 EXIT
    THEN
    DUP OP-STD = IF
        DROP ." STD" CR 0 EXIT
    THEN

    \ --- PUSHF / POPF ---
    DUP OP-PUSHF = IF
        DROP ." PUSHF" CR 0 EXIT
    THEN
    DUP OP-POPF = IF
        DROP ." POPF" CR 0 EXIT
    THEN

    \ --- PUSH reg (50-57) ---
    DUP OP-PUSH-B >= OVER OP-POP-B < AND IF
        ." PUSH " OP-PUSH-B - .REG CR
        0 EXIT
    THEN

    \ --- POP reg (58-5F) ---
    DUP OP-POP-B >= OVER
    DECIMAL 96 HEX > INVERT AND IF
        ." POP " OP-POP-B - .REG CR
        0 EXIT
    THEN

    \ --- INC reg (40-47) ---
    DUP OP-INC-B >= OVER OP-DEC-B < AND IF
        ." INC " OP-INC-B - .REG CR
        0 EXIT
    THEN

    \ --- DEC reg (48-4F) ---
    DUP OP-DEC-B >= OVER OP-PUSH-B < AND IF
        ." DEC " OP-DEC-B - .REG CR
        0 EXIT
    THEN

    \ --- MOV r/m, r (89) ---
    DUP OP-MOV-RM = IF
        DROP DIS-B@
        ." MOV "
        DUP .MODRM ." , "
        MODRM-REG .REG CR
        0 EXIT
    THEN

    \ --- MOV r, r/m (8B) ---
    DUP OP-MOV-RRM = IF
        DROP DIS-B@
        ." MOV "
        DUP MODRM-REG .REG ." , "
        .MODRM CR
        0 EXIT
    THEN

    \ --- LEA r, [m] (8D) ---
    DUP OP-LEA = IF
        DROP DIS-B@
        ." LEA "
        DUP MODRM-REG .REG ." , "
        .MODRM CR
        0 EXIT
    THEN

    \ --- ADD/SUB/AND/OR/XOR/CMP r/m,r ---
    DUP OP-ADD-RM = IF
        DROP DIS-B@
        ." ADD "
        DUP .MODRM ." , "
        MODRM-REG .REG CR
        0 EXIT
    THEN
    DUP OP-SUB-RM = IF
        DROP DIS-B@
        ." SUB "
        DUP .MODRM ." , "
        MODRM-REG .REG CR
        0 EXIT
    THEN
    DUP OP-AND-RM = IF
        DROP DIS-B@
        ." AND "
        DUP .MODRM ." , "
        MODRM-REG .REG CR
        0 EXIT
    THEN
    DUP OP-OR-RM = IF
        DROP DIS-B@
        ." OR "
        DUP .MODRM ." , "
        MODRM-REG .REG CR
        0 EXIT
    THEN
    DUP OP-XOR-RM = IF
        DROP DIS-B@
        ." XOR "
        DUP .MODRM ." , "
        MODRM-REG .REG CR
        0 EXIT
    THEN
    DUP OP-CMP-RM = IF
        DROP DIS-B@
        ." CMP "
        DUP .MODRM ." , "
        MODRM-REG .REG CR
        0 EXIT
    THEN
    DUP OP-CMP-RRM = IF
        DROP DIS-B@
        ." CMP "
        DUP MODRM-REG .REG ." , "
        .MODRM CR
        0 EXIT
    THEN
    DUP OP-TEST-RM = IF
        DROP DIS-B@
        ." TEST "
        DUP .MODRM ." , "
        MODRM-REG .REG CR
        0 EXIT
    THEN

    \ --- ALU r/m, imm8 (83) ---
    DUP OP-ALU-I8 = IF
        DROP DIS-B@
        DUP MODRM-REG .ALU ."  "
        .MODRM ." , "
        DIS-B@ .H2 CR
        0 EXIT
    THEN

    \ --- ALU r/m, imm32 (81) ---
    DUP OP-ALU-I32 = IF
        DROP DIS-B@
        DUP MODRM-REG .ALU ."  "
        .MODRM ." , "
        DIS-L@ . CR
        0 EXIT
    THEN

    \ --- CALL rel32 (E8) ---
    DUP OP-CALL = IF
        DROP ." CALL "
        DIS-L@ DIS-PC @ + . CR
        0 EXIT
    THEN

    \ --- JMP rel32 (E9) ---
    DUP OP-JMP32 = IF
        DROP ." JMP "
        DIS-L@ DIS-PC @ + . CR
        0 EXIT
    THEN

    \ --- JMP rel8 (EB) ---
    DUP OP-JMP8 = IF
        DROP ." JMP "
        DIS-B@
        DUP 7F > IF FFFFFF00 OR THEN
        DIS-PC @ + . CR
        0 EXIT
    THEN

    \ --- INT imm8 (CD) ---
    DUP OP-INT = IF
        DROP ." INT "
        DIS-B@ .H2 CR
        0 EXIT
    THEN

    \ --- Short conditional jumps ---
    DUP OP-JZ8 = IF
        DROP ." JZ "
        DIS-B@
        DUP 7F > IF FFFFFF00 OR THEN
        DIS-PC @ + . CR
        0 EXIT
    THEN
    DUP OP-JNZ8 = IF
        DROP ." JNZ "
        DIS-B@
        DUP 7F > IF FFFFFF00 OR THEN
        DIS-PC @ + . CR
        0 EXIT
    THEN
    DUP OP-JB8 = IF
        DROP ." JB "
        DIS-B@
        DUP 7F > IF FFFFFF00 OR THEN
        DIS-PC @ + . CR
        0 EXIT
    THEN
    DUP OP-JAE8 = IF
        DROP ." JAE "
        DIS-B@
        DUP 7F > IF FFFFFF00 OR THEN
        DIS-PC @ + . CR
        0 EXIT
    THEN
    DUP OP-JBE8 = IF
        DROP ." JBE "
        DIS-B@
        DUP 7F > IF FFFFFF00 OR THEN
        DIS-PC @ + . CR
        0 EXIT
    THEN
    DUP OP-JA8 = IF
        DROP ." JA "
        DIS-B@
        DUP 7F > IF FFFFFF00 OR THEN
        DIS-PC @ + . CR
        0 EXIT
    THEN
    DUP OP-JL8 = IF
        DROP ." JL "
        DIS-B@
        DUP 7F > IF FFFFFF00 OR THEN
        DIS-PC @ + . CR
        0 EXIT
    THEN
    DUP OP-JGE8 = IF
        DROP ." JGE "
        DIS-B@
        DUP 7F > IF FFFFFF00 OR THEN
        DIS-PC @ + . CR
        0 EXIT
    THEN
    DUP OP-JLE8 = IF
        DROP ." JLE "
        DIS-B@
        DUP 7F > IF FFFFFF00 OR THEN
        DIS-PC @ + . CR
        0 EXIT
    THEN
    DUP OP-JG8 = IF
        DROP ." JG "
        DIS-B@
        DUP 7F > IF FFFFFF00 OR THEN
        DIS-PC @ + . CR
        0 EXIT
    THEN

    \ --- Unary F7 (NOT/NEG/MUL/DIV/IDIV) ---
    DUP OP-UNARY = IF
        DROP DIS-B@
        DUP MODRM-REG .UNARY ."  "
        .MODRM CR
        0 EXIT
    THEN

    \ --- FF group (JMP [reg], PUSH r/m) ---
    DUP OP-FF-GRP = IF
        DROP DIS-B@
        DUP MODRM-REG
        DUP 4 = IF
            DROP ." JMP "
            .MODRM CR 0 EXIT
        THEN
        DUP 6 = IF
            DROP ." PUSH "
            .MODRM CR 0 EXIT
        THEN
        DUP 2 = IF
            DROP ." CALL "
            .MODRM CR 0 EXIT
        THEN
        DROP
        ." FF/" .MODRM CR
        0 EXIT
    THEN

    \ --- MOV r/m, imm32 (C7) ---
    DUP OP-MOV-IMM = IF
        DROP DIS-B@
        ." MOV "
        .MODRM ." , "
        DIS-L@ . CR
        0 EXIT
    THEN

    \ --- MOV eax,imm (B8-BF) ---
    DUP OP-MOV-EAX-I >=
    OVER DECIMAL 192 HEX < AND IF
        ." MOV "
        OP-MOV-EAX-I - .REG ." , "
        DIS-L@ . CR
        0 EXIT
    THEN

    \ --- 0F prefix ---
    DUP OP-0F = IF
        DROP DIS-B@
        DUP OP-0F-JZ = IF
            DROP ." JZ "
            DIS-L@ DIS-PC @ + . CR
            0 EXIT
        THEN
        DUP OP-0F-JNZ = IF
            DROP ." JNZ "
            DIS-L@ DIS-PC @ + . CR
            0 EXIT
        THEN
        DUP OP-0F-MOVZX8 = IF
            DROP DIS-B@
            ." MOVZX "
            DUP MODRM-REG .REG
            ." , byte "
            .MODRM CR 0 EXIT
        THEN
        DUP OP-0F-MOVZX16 = IF
            DROP DIS-B@
            ." MOVZX "
            DUP MODRM-REG .REG
            ." , word "
            .MODRM CR 0 EXIT
        THEN
        ." 0F " .H2 CR
        0 EXIT
    THEN

    \ --- Unknown opcode ---
    DROP DIS-OP @ .H2 ."  ?" CR
    0
;

\ DIS-X86: decode from CFA until RET or max
DECIMAL 32 CONSTANT DIS-MAX HEX
: DIS-X86  ( cfa -- )
    \ CFA contains ptr to native code.
    \ For DEFCODE, code_ is at CFA+4.
    @ DIS-PC !
    ." Code at " DIS-PC @ . CR
    DIS-MAX 0 DO
        \ Check for NEXT pattern first
        DIS-PC @ NEXT? IF
            DIS-PC @ . ." : NEXT" CR
            LEAVE
        THEN
        DIS-1 IF LEAVE THEN
    LOOP
;

\ ============================================
\ Section E: Top-Level Dispatcher
\ ============================================

: DIS  ( "name" -- )
    '
    DUP COLON? IF
        DECOMP EXIT
    THEN
    DUP CONST? IF
        ." Constant = "
        4 + @ DECIMAL . HEX CR EXIT
    THEN
    DUP CREATE? IF
        ." Variable body at "
        4 + . CR EXIT
    THEN
    DUP VOCAB? IF
        ." Vocabulary" CR DROP EXIT
    THEN
    DIS-X86
;

." DISASM loaded" CR

FORTH DEFINITIONS
DECIMAL
