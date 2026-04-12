\ ============================================
\ CATALOG: ARM64-ASM
\ CATEGORY: system
\ PLATFORM: arm64
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ REQUIRES: X86-ASM ( T-, T-C, T-HERE )
\ ============================================
\
\ ARM64 (AArch64) assembler for metacompiler.
\ Emits 32-bit fixed-width instructions to
\ target buffer via T-, from X86-ASM.
\
\ All ARM64 instructions are 4 bytes.
\ Register fields are 5 bits (0-30, 31=ZR/SP)
\
\ Usage:
\   USING ARM64-ASM
\   W1 W0 W2 A64-ADD,
\   4 X27 W0 A64-LDR-POST,
\
\ ============================================

VOCABULARY ARM64-ASM
ARM64-ASM DEFINITIONS
ALSO X86-ASM
HEX

\ ============================================
\ Register constants
\ ============================================
\ W regs (32-bit data) and X regs (64-bit
\ addr) share encoding. Names for clarity.

0 CONSTANT W0    1 CONSTANT W1
2 CONSTANT W2    3 CONSTANT W3
4 CONSTANT W4

19 CONSTANT W25   1A CONSTANT W26
1B CONSTANT W27   1F CONSTANT WZR

0 CONSTANT X0    1 CONSTANT X1
2 CONSTANT X2    3 CONSTANT X3

19 CONSTANT X25   1A CONSTANT X26
1B CONSTANT X27   1E CONSTANT X30
1F CONSTANT XZR   1F CONSTANT XSP

\ Named roles
1B CONSTANT IP-REG
1A CONSTANT RSP-REG
19 CONSTANT PSP-REG

\ ============================================
\ Condition codes (4-bit)
\ ============================================
0 CONSTANT COND-EQ   1 CONSTANT COND-NE
2 CONSTANT COND-CS   3 CONSTANT COND-CC
4 CONSTANT COND-MI   5 CONSTANT COND-PL
8 CONSTANT COND-HI   9 CONSTANT COND-LS
0A CONSTANT COND-GE  0B CONSTANT COND-LT
0C CONSTANT COND-GT  0D CONSTANT COND-LE

\ ============================================
\ Encoding helpers
\ ============================================
\ Base opcode passed via variable to avoid
\ complex stack gymnastics (like DISP-TMP
\ in x86-asm.fth).

VARIABLE A64-OP

\ 3-operand: OP|(Rm<<16)|(Rn<<5)|Rd
: A64-3R ( Rm Rn Rd -- )
    SWAP 5 LSHIFT OR
    SWAP 10 LSHIFT OR
    A64-OP @ OR T-,
;

\ 2-operand with WZR as Rn (bits[9:5]=31):
\ OP|(Rm<<16)|(31<<5)|Rd
: A64-2R ( Rm Rd -- )
    1F 5 LSHIFT OR
    SWAP 10 LSHIFT OR
    A64-OP @ OR T-,
;

\ Compare-reg: OP|(Rm<<16)|(Rn<<5)|WZR
: A64-CR ( Rm Rn -- )
    5 LSHIFT 1F OR
    SWAP 10 LSHIFT OR
    A64-OP @ OR T-,
;

\ Immediate12: OP|(imm12<<10)|(Rn<<5)|Rd
: A64-I12 ( imm12 Rn Rd -- )
    SWAP 5 LSHIFT OR
    SWAP FFF AND 0A LSHIFT OR
    A64-OP @ OR T-,
;

\ Compare-imm12: OP|(imm12<<10)|(Rn<<5)|31
: A64-CI12 ( imm12 Rn -- )
    5 LSHIFT 1F OR
    SWAP FFF AND 0A LSHIFT OR
    A64-OP @ OR T-,
;

\ Load/Store simm9: OP|(s9<<12)|(Rn<<5)|Rt
: A64-LS9 ( simm9 Rn Rt -- )
    SWAP 5 LSHIFT OR
    SWAP 1FF AND 0C LSHIFT OR
    A64-OP @ OR T-,
;

\ Load/Store unsigned word:
\ OP|((uimm/4)<<10)|(Rn<<5)|Rt
: A64-LSUW ( uimm Rn Rt -- )
    SWAP 5 LSHIFT OR
    SWAP 2 RSHIFT FFF AND
    0A LSHIFT OR
    A64-OP @ OR T-,
;

\ Load/Store unsigned byte (no scale):
\ OP|(uimm<<10)|(Rn<<5)|Rt
: A64-LSUB ( uimm Rn Rt -- )
    SWAP 5 LSHIFT OR
    SWAP FFF AND 0A LSHIFT OR
    A64-OP @ OR T-,
;

\ Load/Store unsigned halfword:
\ OP|((uimm/2)<<10)|(Rn<<5)|Rt
: A64-LSUH ( uimm Rn Rt -- )
    SWAP 5 LSHIFT OR
    SWAP 1 RSHIFT FFF AND
    0A LSHIFT OR
    A64-OP @ OR T-,
;

\ ============================================
\ Data processing — register (32-bit W)
\ ============================================

: A64-ADD, ( Rm Rn Rd -- )
    0B000000 A64-OP ! A64-3R ;
: A64-SUB, ( Rm Rn Rd -- )
    4B000000 A64-OP ! A64-3R ;
: A64-AND, ( Rm Rn Rd -- )
    0A000000 A64-OP ! A64-3R ;
: A64-ORR, ( Rm Rn Rd -- )
    2A000000 A64-OP ! A64-3R ;
: A64-EOR, ( Rm Rn Rd -- )
    4A000000 A64-OP ! A64-3R ;

\ MUL Wd,Wn,Wm = MADD Wd,Wn,Wm,WZR
: A64-MUL, ( Rm Rn Rd -- )
    1B007C00 A64-OP ! A64-3R ;

: A64-SDIV, ( Rm Rn Rd -- )
    1AC00C00 A64-OP ! A64-3R ;
: A64-UDIV, ( Rm Rn Rd -- )
    1AC00800 A64-OP ! A64-3R ;

\ Shift by register
: A64-LSLV, ( Rm Rn Rd -- )
    1AC02000 A64-OP ! A64-3R ;
: A64-LSRV, ( Rm Rn Rd -- )
    1AC02400 A64-OP ! A64-3R ;
: A64-ASRV, ( Rm Rn Rd -- )
    1AC02800 A64-OP ! A64-3R ;

\ ============================================
\ Data processing — 2 operand (Rm, Rd)
\ ============================================
\ NEG Wd,Wm = SUB Wd,WZR,Wm
: A64-NEG, ( Rm Rd -- )
    4B000000 A64-OP ! A64-2R ;

\ MVN Wd,Wm = ORN Wd,WZR,Wm
: A64-MVN, ( Rm Rd -- )
    2A200000 A64-OP ! A64-2R ;

\ MOV Wd,Wm = ORR Wd,WZR,Wm
: A64-MOV, ( Rm Rd -- )
    2A000000 A64-OP ! A64-2R ;

\ ============================================
\ Compare — register (set flags, Rd=WZR)
\ ============================================
\ CMP Wn,Wm = SUBS WZR,Wn,Wm
: A64-CMP, ( Rm Rn -- )
    6B000000 A64-OP ! A64-CR ;

\ TST Wn,Wm = ANDS WZR,Wn,Wm
: A64-TST, ( Rm Rn -- )
    6A000000 A64-OP ! A64-CR ;

\ ============================================
\ Data processing — immediate (12-bit)
\ ============================================
\ ADD Wd, Wn, #imm12 (32-bit)
: A64-ADD#, ( imm12 Rn Rd -- )
    11000000 A64-OP ! A64-I12 ;

\ ADD Xd, Xn, #imm12 (64-bit, for addrs)
: A64-ADD#X, ( imm12 Rn Rd -- )
    91000000 A64-OP ! A64-I12 ;

\ SUB Wd, Wn, #imm12
: A64-SUB#, ( imm12 Rn Rd -- )
    51000000 A64-OP ! A64-I12 ;

\ SUB Xd, Xn, #imm12 (64-bit)
: A64-SUB#X, ( imm12 Rn Rd -- )
    D1000000 A64-OP ! A64-I12 ;

\ CMP Wn, #imm12 = SUBS WZR, Wn, #imm12
: A64-CMP#, ( imm12 Rn -- )
    71000000 A64-OP ! A64-CI12 ;

\ ============================================
\ Move wide immediate (16-bit)
\ ============================================
\ MOVZ Wd, #imm16 (zero other bits)
: A64-MOVZ, ( imm16 Rd -- )
    SWAP FFFF AND 5 LSHIFT OR
    52800000 OR T-,
;

\ MOVK Wd, #imm16, LSL #(hw*16)
\ hw=0: bits[15:0], hw=1: bits[31:16]
: A64-MOVK, ( imm16 hw Rd -- )
    SWAP 15 LSHIFT SWAP OR
    SWAP FFFF AND 5 LSHIFT OR
    72800000 OR T-,
;

\ MOVN Wd, #imm16 (move NOT)
: A64-MOVN, ( imm16 Rd -- )
    SWAP FFFF AND 5 LSHIFT OR
    12800000 OR T-,
;

\ ============================================
\ Load/Store — post-index (NEXT, POP)
\ ============================================
\ LDR Wt, [Xn], #simm9
: A64-LDR-POST, ( simm9 Rn Rt -- )
    B8400400 A64-OP ! A64-LS9 ;

\ STR Wt, [Xn], #simm9 (post-index store)
: A64-STR-POST, ( simm9 Rn Rt -- )
    B8000400 A64-OP ! A64-LS9 ;

\ ============================================
\ Load/Store — pre-index (PUSH)
\ ============================================
\ STR Wt, [Xn, #simm9]!
: A64-STR-PRE, ( simm9 Rn Rt -- )
    B8000C00 A64-OP ! A64-LS9 ;

\ LDR Wt, [Xn, #simm9]! (pre-index load)
: A64-LDR-PRE, ( simm9 Rn Rt -- )
    B8400C00 A64-OP ! A64-LS9 ;

\ ============================================
\ Load/Store — unsigned offset
\ ============================================
\ LDR Wt, [Xn, #uimm] (word aligned)
: A64-LDR-UOFF, ( uimm Rn Rt -- )
    B9400000 A64-OP ! A64-LSUW ;

\ STR Wt, [Xn, #uimm]
: A64-STR-UOFF, ( uimm Rn Rt -- )
    B9000000 A64-OP ! A64-LSUW ;

\ LDRB Wt, [Xn, #uimm] (byte, no scale)
: A64-LDRB-UOFF, ( uimm Rn Rt -- )
    39400000 A64-OP ! A64-LSUB ;

\ STRB Wt, [Xn, #uimm]
: A64-STRB-UOFF, ( uimm Rn Rt -- )
    39000000 A64-OP ! A64-LSUB ;

\ LDRH Wt, [Xn, #uimm] (halfword)
: A64-LDRH-UOFF, ( uimm Rn Rt -- )
    79400000 A64-OP ! A64-LSUH ;

\ STRH Wt, [Xn, #uimm]
: A64-STRH-UOFF, ( uimm Rn Rt -- )
    79000000 A64-OP ! A64-LSUH ;

\ ============================================
\ Branch instructions
\ ============================================

\ B imm26 — forward with fixup
: A64-B, ( -- fixup )
    T-HERE @ 14000000 T-,
;

\ Resolve forward B
\ fixup is host addr from T-HERE @
: A64-B>RES ( fixup -- )
    T-HERE @ OVER -
    2 RSHIFT 3FFFFFF AND
    OVER @
    FC000000 AND OR
    SWAP !
;

\ B.cond — conditional branch forward
: A64-BCOND, ( cond -- fixup )
    54000000 OR
    T-HERE @ SWAP T-,
;

\ Resolve forward B.cond
\ fixup is host addr from T-HERE @
: A64-BC>RES ( fixup -- )
    T-HERE @ OVER -
    2 RSHIFT 7FFFF AND 5 LSHIFT
    OVER @
    FF00001F AND OR
    SWAP !
;

\ CBZ Wt — compare-branch-zero forward
: A64-CBZ, ( Rt -- fixup )
    34000000 OR
    T-HERE @ SWAP T-,
;

\ CBNZ Wt — compare-branch-nonzero
: A64-CBNZ, ( Rt -- fixup )
    35000000 OR
    T-HERE @ SWAP T-,
;

\ Resolve CBZ/CBNZ forward (same layout as
\ B.cond: imm19 at [23:5])
: A64-CB>RES ( fixup -- )
    A64-BC>RES ;

\ BL imm26 — branch with link (call)
: A64-BL, ( -- fixup )
    T-HERE @ 94000000 T-,
;

\ Resolve BL (same as B)
: A64-BL>RES ( fixup -- ) A64-B>RES ;

\ BR Xn — branch register
: A64-BR, ( Rn -- )
    5 LSHIFT D61F0000 OR T-,
;

\ BLR Xn — branch-link register
: A64-BLR, ( Rn -- )
    5 LSHIFT D63F0000 OR T-,
;

\ RET — return via X30
: A64-RET, ( -- ) D65F03C0 T-, ;

\ ============================================
\ Conditional set
\ ============================================
\ CSET Wd, cond
\ = CSINC Wd,WZR,WZR,invert(cond)
: A64-CSET, ( cond Rd -- )
    SWAP 1 XOR 0C LSHIFT OR
    1A9F07E0 OR T-,
;

\ ============================================
\ Special instructions
\ ============================================
: A64-NOP, ( -- ) D503201F T-, ;

\ ADD Xd,Xn,Wm,SXTW (sign-extend W->X)
\ Used for BRANCH: IP += signed_offset
: A64-SXTW-ADD, ( Rm Rn Rd -- )
    8B20C000 A64-OP ! A64-3R ;

\ DMB SY — data memory barrier (full)
: A64-DMB, ( -- ) D5033FBF T-, ;

\ DMB ST — store barrier
: A64-DMB-ST, ( -- ) D5033EBF T-, ;

\ Raw instruction emit (escape hatch)
: A64-RAW, ( inst -- ) T-, ;

FORTH DEFINITIONS
DECIMAL
