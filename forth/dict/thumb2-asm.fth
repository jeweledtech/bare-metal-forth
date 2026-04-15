\ ============================================
\ CATALOG: THUMB2-ASM
\ CATEGORY: system
\ PLATFORM: cortex-m
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ REQUIRES: X86-ASM META-COMPILER
\ ============================================
\
\ Thumb-2 assembler for Cortex-M33 meta-
\ compiler. Emits mixed 16/32-bit Thumb
\ instructions to target buffer.
\
\ 16-bit: T-W, (halfword)
\ 32-bit: two T-W, calls (upper first)
\
\ Register roles:
\   R8 = IP (Forth instruction pointer)
\   R9 = RSP (return stack pointer)
\   R10 = PSP (data stack pointer)
\
\ Usage:
\   USING THUMB2-ASM
\   R1 R0 R2 T2-ADDS,
\   4 R8 R0 T2W-LDR-POST,
\
\ ============================================

VOCABULARY THUMB2-ASM
THUMB2-ASM DEFINITIONS
ALSO META-COMPILER
ALSO X86-ASM
HEX

\ ========================================
\ Register constants (4-bit encoding)
\ ========================================

0 CONSTANT R0    1 CONSTANT R1
2 CONSTANT R2    3 CONSTANT R3
4 CONSTANT R4    5 CONSTANT R5
6 CONSTANT R6    7 CONSTANT R7
8 CONSTANT R8    9 CONSTANT R9
A CONSTANT R10   B CONSTANT R11
C CONSTANT R12   D CONSTANT R13
E CONSTANT R14   F CONSTANT R15
D CONSTANT SP    E CONSTANT LR
F CONSTANT PC

\ Named roles
8 CONSTANT IP-REG
9 CONSTANT RSP-REG
A CONSTANT PSP-REG

\ Condition codes (4-bit)
0 CONSTANT CC-EQ    1 CONSTANT CC-NE
2 CONSTANT CC-CS    3 CONSTANT CC-CC
4 CONSTANT CC-MI    5 CONSTANT CC-PL
8 CONSTANT CC-HI    9 CONSTANT CC-LS
A CONSTANT CC-GE    B CONSTANT CC-LT
C CONSTANT CC-GT    D CONSTANT CC-LE

\ ========================================
\ Emit helpers
\ ========================================

\ Emit 16-bit Thumb instruction
: T2-16, ( hw -- ) T-W, ;

\ Emit 32-bit Thumb-2 (upper halfword first)
: T2-32, ( u32 -- )
  DUP 10 RSHIFT T-W,
  FFFF AND T-W, ;

\ ========================================
\ 16-bit narrow instructions (r0-r7)
\ ========================================

\ ADD r0-r7 (3-reg): 0001100 Rm Rn Rd
: T2-ADDS, ( Rm Rn Rd -- )
  SWAP 3 LSHIFT OR
  SWAP 6 LSHIFT OR
  1800 OR T2-16, ;

\ SUB r0-r7 (3-reg): 0001101 Rm Rn Rd
: T2-SUBS, ( Rm Rn Rd -- )
  SWAP 3 LSHIFT OR
  SWAP 6 LSHIFT OR
  1A00 OR T2-16, ;

\ MOV imm8: 00100 Rd imm8
: T2-MOVS-I, ( imm8 Rd -- )
  8 LSHIFT OR 2000 OR T2-16, ;

\ CMP imm8: 00101 Rn imm8
: T2-CMP-I, ( imm8 Rn -- )
  8 LSHIFT OR 2800 OR T2-16, ;

\ ADD imm3: 0001110 imm3 Rn Rd
: T2-ADDS-I3, ( imm3 Rn Rd -- )
  SWAP 3 LSHIFT OR
  SWAP 6 LSHIFT OR
  1C00 OR T2-16, ;

\ SUB imm3: 0001111 imm3 Rn Rd
: T2-SUBS-I3, ( imm3 Rn Rd -- )
  SWAP 3 LSHIFT OR
  SWAP 6 LSHIFT OR
  1E00 OR T2-16, ;

\ ADD imm8: 00110 Rdn imm8
: T2-ADDS-I8, ( imm8 Rdn -- )
  8 LSHIFT OR 3000 OR T2-16, ;

\ SUB imm8: 00111 Rdn imm8
: T2-SUBS-I8, ( imm8 Rdn -- )
  8 LSHIFT OR 3800 OR T2-16, ;

\ MOV high reg: 01000110 D Rm Rd
\ D = Rd[3], Rd = Rd[2:0]
: T2-MOV, ( Rm Rd -- )
  DUP 8 AND IF
    7 AND SWAP 3 LSHIFT OR
    80 OR
  ELSE
    SWAP 3 LSHIFT OR
  THEN
  4600 OR T2-16, ;

\ CMP high reg: 01000101 N Rm Rn
: T2-CMP, ( Rm Rn -- )
  DUP 8 AND IF
    7 AND SWAP 3 LSHIFT OR
    80 OR
  ELSE
    SWAP 3 LSHIFT OR
  THEN
  4500 OR T2-16, ;

\ AND r0-r7: 0100000000 Rm Rdn
: T2-ANDS, ( Rm Rdn -- )
  SWAP 3 LSHIFT OR
  4000 OR T2-16, ;

\ ORR r0-r7: 0100001100 Rm Rdn
: T2-ORRS, ( Rm Rdn -- )
  SWAP 3 LSHIFT OR
  4300 OR T2-16, ;

\ EOR r0-r7: 0100000001 Rm Rdn
: T2-EORS, ( Rm Rdn -- )
  SWAP 3 LSHIFT OR
  4040 OR T2-16, ;

\ MVN r0-r7: 0100001111 Rm Rd
: T2-MVNS, ( Rm Rd -- )
  SWAP 3 LSHIFT OR
  43C0 OR T2-16, ;

\ MUL r0-r7: 0100001101 Rn Rdm
: T2-MULS, ( Rn Rdm -- )
  SWAP 3 LSHIFT OR
  4340 OR T2-16, ;

\ LSL imm5: 00000 imm5 Rm Rd
: T2-LSLS-I, ( imm5 Rm Rd -- )
  SWAP 3 LSHIFT OR
  SWAP 6 LSHIFT OR
  T2-16, ;

\ LSR imm5: 00001 imm5 Rm Rd
: T2-LSRS-I, ( imm5 Rm Rd -- )
  SWAP 3 LSHIFT OR
  SWAP 6 LSHIFT OR
  800 OR T2-16, ;

\ ASR imm5: 00010 imm5 Rm Rd
: T2-ASRS-I, ( imm5 Rm Rd -- )
  SWAP 3 LSHIFT OR
  SWAP 6 LSHIFT OR
  1000 OR T2-16, ;

\ LSL register: 0100000010 Rs Rdn
: T2-LSLS, ( Rs Rdn -- )
  SWAP 3 LSHIFT OR
  4080 OR T2-16, ;

\ LSR register: 0100000011 Rs Rdn
: T2-LSRS, ( Rs Rdn -- )
  SWAP 3 LSHIFT OR
  40C0 OR T2-16, ;

\ ========================================
\ 16-bit load/store (r0-r7, SP-relative)
\ ========================================

\ LDR Rt,[SP,#imm8*4]: 10011 Rt imm8
: T2-LDR-SP, ( imm8x4 Rt -- )
  8 LSHIFT SWAP 2 RSHIFT FF AND OR
  9800 OR T2-16, ;

\ STR Rt,[SP,#imm8*4]: 10010 Rt imm8
: T2-STR-SP, ( imm8x4 Rt -- )
  8 LSHIFT SWAP 2 RSHIFT FF AND OR
  9000 OR T2-16, ;

\ LDR Rt,[Rn,#imm5*4]: 01101 imm5 Rn Rt
: T2-LDR-I5, ( imm5x4 Rn Rt -- )
  SWAP 3 LSHIFT OR
  SWAP 2 RSHIFT 6 LSHIFT OR
  6800 OR T2-16, ;

\ STR Rt,[Rn,#imm5*4]: 01100 imm5 Rn Rt
: T2-STR-I5, ( imm5x4 Rn Rt -- )
  SWAP 3 LSHIFT OR
  SWAP 2 RSHIFT 6 LSHIFT OR
  6000 OR T2-16, ;

\ LDRB Rt,[Rn,#imm5]: 01111 imm5 Rn Rt
: T2-LDRB-I5, ( imm5 Rn Rt -- )
  SWAP 3 LSHIFT OR
  SWAP 6 LSHIFT OR
  7800 OR T2-16, ;

\ STRB Rt,[Rn,#imm5]: 01110 imm5 Rn Rt
: T2-STRB-I5, ( imm5 Rn Rt -- )
  SWAP 3 LSHIFT OR
  SWAP 6 LSHIFT OR
  7000 OR T2-16, ;

\ ========================================
\ 16-bit PUSH/POP (register list)
\ ========================================

\ PUSH {reg-list}: 1011010 M rlist
\ M=1 includes LR
: T2-PUSH, ( rlist -- )
  B400 OR T2-16, ;

\ POP {reg-list}: 1011110 P rlist
\ P=1 includes PC
: T2-POP, ( rlist -- )
  BC00 OR T2-16, ;

\ ========================================
\ 16-bit branch
\ ========================================

\ BX Rm: 010001110 Rm 000
: T2-BX, ( Rm -- )
  3 LSHIFT 4700 OR T2-16, ;

\ BLX Rm: 010001111 Rm 000
: T2-BLX, ( Rm -- )
  3 LSHIFT 4780 OR T2-16, ;

\ NOP: 10111111 00000000
: T2-NOP, ( -- ) BF00 T2-16, ;

\ ========================================
\ 32-bit wide instructions (any register)
\ ========================================

\ ADD.W Rd,Rn,Rm: EB00 0000 | Rm Rd Rn
: T2W-ADD, ( Rm Rn Rd -- )
  SWAP
  \ Build: hi16=EB00|Rn, lo16=Rm|(Rd<<8)
  F AND 0 LSHIFT EB000000 OR
  ROT F AND 8 LSHIFT OR
  ROT F AND OR
  T2-32, ;

\ SUB.W Rd,Rn,Rm: EBA0 0000
: T2W-SUB, ( Rm Rn Rd -- )
  SWAP
  F AND 0 LSHIFT EBA00000 OR
  ROT F AND 8 LSHIFT OR
  ROT F AND OR
  T2-32, ;

\ AND.W Rd,Rn,Rm: EA00 0000
: T2W-AND, ( Rm Rn Rd -- )
  SWAP
  F AND EA000000 OR
  ROT F AND 8 LSHIFT OR
  ROT F AND OR
  T2-32, ;

\ ORR.W Rd,Rn,Rm: EA40 0000
: T2W-ORR, ( Rm Rn Rd -- )
  SWAP
  F AND EA400000 OR
  ROT F AND 8 LSHIFT OR
  ROT F AND OR
  T2-32, ;

\ EOR.W Rd,Rn,Rm: EA80 0000
: T2W-EOR, ( Rm Rn Rd -- )
  SWAP
  F AND EA800000 OR
  ROT F AND 8 LSHIFT OR
  ROT F AND OR
  T2-32, ;

\ CMP.W Rn,Rm: EBB0 0F00
: T2W-CMP, ( Rm Rn -- )
  F AND EBB00000 OR
  SWAP F AND OR
  F00 OR
  T2-32, ;

\ ADD.W Rd,Rn,#imm12: F200 0000
: T2W-ADD-I, ( imm12 Rn Rd -- )
  SWAP
  F AND F2000000 OR
  ROT F AND 8 LSHIFT OR
  ROT
  DUP FF AND OR
  SWAP DUP 700 AND 4 LSHIFT OR
  SWAP 800 AND A LSHIFT OR
  T2-32, ;

\ SUB.W Rd,Rn,#imm12: F2A0 0000
: T2W-SUB-I, ( imm12 Rn Rd -- )
  SWAP
  F AND F2A00000 OR
  ROT F AND 8 LSHIFT OR
  ROT
  DUP FF AND OR
  SWAP DUP 700 AND 4 LSHIFT OR
  SWAP 800 AND A LSHIFT OR
  T2-32, ;

\ SDIV Rd,Rn,Rm: FB90 F0x0
: T2W-SDIV, ( Rm Rn Rd -- )
  SWAP
  F AND FB900000 OR
  ROT F AND 8 LSHIFT OR
  ROT F AND OR
  F000 OR
  T2-32, ;

\ UDIV Rd,Rn,Rm: FBB0 F0x0
: T2W-UDIV, ( Rm Rn Rd -- )
  SWAP
  F AND FBB00000 OR
  ROT F AND 8 LSHIFT OR
  ROT F AND OR
  F000 OR
  T2-32, ;

\ MUL Rd,Rn,Rm: FB00 F000
: T2W-MUL, ( Rm Rn Rd -- )
  SWAP
  F AND FB000000 OR
  ROT F AND 8 LSHIFT OR
  ROT F AND OR
  F000 OR
  T2-32, ;

\ ========================================
\ 32-bit wide load/store
\ ========================================

\ LDR.W Rt,[Rn,#imm12]: F8D0 0000
: T2W-LDR, ( imm12 Rn Rt -- )
  SWAP
  F AND F8D00000 OR
  ROT F AND C LSHIFT OR
  ROT FFF AND OR
  T2-32, ;

\ STR.W Rt,[Rn,#imm12]: F8C0 0000
: T2W-STR, ( imm12 Rn Rt -- )
  SWAP
  F AND F8C00000 OR
  ROT F AND C LSHIFT OR
  ROT FFF AND OR
  T2-32, ;

\ LDR.W Rt,[Rn],#imm8 (post-index)
\ F850 0B00 | imm8
: T2W-LDR-POST, ( imm8 Rn Rt -- )
  SWAP
  F AND F8500000 OR
  ROT F AND C LSHIFT OR
  ROT FF AND OR
  B00 OR
  T2-32, ;

\ STR.W Rt,[Rn,#-imm8]! (pre-index)
\ F840 0D00 | imm8
: T2W-STR-PRE, ( imm8 Rn Rt -- )
  SWAP
  F AND F8400000 OR
  ROT F AND C LSHIFT OR
  ROT FF AND OR
  D00 OR
  T2-32, ;

\ LDR.W Rt,[Rn,#-imm8]! (pre-index)
\ F850 0D00 | imm8
: T2W-LDR-PRE, ( imm8 Rn Rt -- )
  SWAP
  F AND F8500000 OR
  ROT F AND C LSHIFT OR
  ROT FF AND OR
  D00 OR
  T2-32, ;

\ LDRB.W Rt,[Rn,#imm12]: F890 0000
: T2W-LDRB, ( imm12 Rn Rt -- )
  SWAP
  F AND F8900000 OR
  ROT F AND C LSHIFT OR
  ROT FFF AND OR
  T2-32, ;

\ STRB.W Rt,[Rn,#imm12]: F880 0000
: T2W-STRB, ( imm12 Rn Rt -- )
  SWAP
  F AND F8800000 OR
  ROT F AND C LSHIFT OR
  ROT FFF AND OR
  T2-32, ;

\ LDRH.W Rt,[Rn,#imm12]: F8B0 0000
: T2W-LDRH, ( imm12 Rn Rt -- )
  SWAP
  F AND F8B00000 OR
  ROT F AND C LSHIFT OR
  ROT FFF AND OR
  T2-32, ;

\ STRH.W Rt,[Rn,#imm12]: F8A0 0000
: T2W-STRH, ( imm12 Rn Rt -- )
  SWAP
  F AND F8A00000 OR
  ROT F AND C LSHIFT OR
  ROT FFF AND OR
  T2-32, ;

\ ========================================
\ 32-bit move wide (16-bit immediate)
\ ========================================

\ MOVW Rd,#imm16: F240 0000
\ imm16 split: i(26) imm3(14:12) imm8(7:0)
\              Rd(11:8) Rn=imm4(19:16)
: T2W-MOVW, ( imm16 Rd -- )
  F AND 8 LSHIFT F2400000 OR
  SWAP
  DUP FF AND OR
  DUP 700 AND 4 LSHIFT OR
  DUP 800 AND E LSHIFT OR
  F000 AND C LSHIFT OR
  T2-32, ;

\ MOVT Rd,#imm16: F2C0 0000
: T2W-MOVT, ( imm16 Rd -- )
  F AND 8 LSHIFT F2C00000 OR
  SWAP
  DUP FF AND OR
  DUP 700 AND 4 LSHIFT OR
  DUP 800 AND E LSHIFT OR
  F000 AND C LSHIFT OR
  T2-32, ;

\ Load 32-bit constant via MOVW+MOVT
: T2-MOV32, ( u32 Rd -- )
  OVER FFFF AND OVER T2W-MOVW,
  SWAP 10 RSHIFT FFFF AND
  DUP 0<> IF
    SWAP T2W-MOVT,
  ELSE DROP DROP THEN ;

\ ========================================
\ 32-bit branch
\ ========================================

\ B.W target (unconditional wide branch)
\ Encode: F000 B800 with signed offset
\ For forward fixup: emit placeholder
: T2W-B-FWD, ( -- fixup-addr )
  T-HERE @
  F000B800 T2-32, ;

\ Resolve forward B.W
: T2W-B-RESOLVE, ( fixup -- )
  T-HERE @ OVER - 4 -
  1 RSHIFT
  DUP 3FF AND
  OVER 0A RSHIFT 7FF AND
  10 LSHIFT OR
  F000B800 OR
  SWAP T-! ;

\ Backward B.W ( target -- )
: T2W-B-BACK, ( target -- )
  T-HERE @ - 4 -
  1 RSHIFT
  DUP 3FF AND
  OVER 0A RSHIFT 7FF AND
  10 LSHIFT OR
  F000B800 OR
  T2-32, ;

\ BL imm (branch with link)
\ F000 D000 with 22-bit offset
: T2W-BL-FWD, ( -- fixup-addr )
  T-HERE @
  F000D000 T2-32, ;

\ Conditional B.W: F000 8000 | cond
: T2W-BCC-FWD, ( cond -- fixup )
  6 LSHIFT 16 LSHIFT
  F0008000 OR
  T-HERE @ SWAP
  T2-32, ;

\ DMB (data memory barrier): F3BF 8F50
: T2-DMB, ( -- ) F3BF8F50 T2-32, ;

\ DMB ST: F3BF 8F5E
: T2-DMB-ST, ( -- ) F3BF8F5E T2-32, ;

\ ========================================
\ Special
\ ========================================

\ SVC #imm8 (supervisor call)
: T2-SVC, ( imm8 -- )
  FF AND DF00 OR T2-16, ;

\ CPSID i (disable interrupts)
: T2-CPSID, ( -- ) B672 T2-16, ;

\ CPSIE i (enable interrupts)
: T2-CPSIE, ( -- ) B662 T2-16, ;

\ MSR BASEPRI,Rn: F380 8811
: T2-MSR-BASEPRI, ( Rn -- )
  F AND 10 LSHIFT
  F3800000 OR 8811 OR
  T2-32, ;

\ MRS Rd,BASEPRI: F3EF 8011
: T2-MRS-BASEPRI, ( Rd -- )
  F AND 8 LSHIFT
  F3EF0000 OR 8011 OR
  T2-32, ;

ONLY FORTH DEFINITIONS
DECIMAL
