/* ============================================================================
 * RISC-V (RV64) Code Generation for Floored Division (Forth-83 Semantics)
 * ============================================================================
 * 
 * RISC-V M extension provides DIV/REM which use symmetric (truncated) division.
 * We apply the same correction algorithm as x86 and ARM64.
 * 
 * Input:  a0 = dividend, a1 = divisor
 * Output: a0 = quotient (FDIV) or remainder (FMOD)
 * 
 * Register usage:
 *   a0 (x10) - dividend, then result
 *   a1 (x11) - divisor (preserved)
 *   t0 (x5)  - quotient
 *   t1 (x6)  - remainder
 *   t2 (x7)  - sign comparison scratch
 * ============================================================================ */

#include "floored_div.h"
#include <stdio.h>

/* RISC-V instruction encoding helpers */
#define RV_EMIT32(code, pos, max, insn) do { \
    if (code && (pos) + 4 <= (max)) { \
        uint32_t _i = (insn); \
        (code)[(pos)++] = _i & 0xFF; \
        (code)[(pos)++] = (_i >> 8) & 0xFF; \
        (code)[(pos)++] = (_i >> 16) & 0xFF; \
        (code)[(pos)++] = (_i >> 24) & 0xFF; \
    } else { \
        (pos) += 4; \
    } \
} while(0)

/* RISC-V register numbers */
#define RV_ZERO  0
#define RV_RA    1
#define RV_SP    2
#define RV_T0    5
#define RV_T1    6
#define RV_T2    7
#define RV_A0    10
#define RV_A1    11
#define RV_A2    12

/* RISC-V instruction encodings (RV64I + M extension) */

/* R-type: funct7[31:25] | rs2[24:20] | rs1[19:15] | funct3[14:12] | rd[11:7] | opcode[6:0] */
#define RV_R_TYPE(funct7, rs2, rs1, funct3, rd, opcode) \
    (((funct7) << 25) | ((rs2) << 20) | ((rs1) << 15) | ((funct3) << 12) | ((rd) << 7) | (opcode))

/* DIV rd, rs1, rs2 (signed division, RV64M) */
#define RV_DIV(rd, rs1, rs2) \
    RV_R_TYPE(0x01, rs2, rs1, 0x4, rd, 0x33)

/* DIVW rd, rs1, rs2 (32-bit signed division, RV64M) */
#define RV_DIVW(rd, rs1, rs2) \
    RV_R_TYPE(0x01, rs2, rs1, 0x4, rd, 0x3B)

/* REM rd, rs1, rs2 (signed remainder, RV64M) */
#define RV_REM(rd, rs1, rs2) \
    RV_R_TYPE(0x01, rs2, rs1, 0x6, rd, 0x33)

/* MUL rd, rs1, rs2 (multiply low bits) */
#define RV_MUL(rd, rs1, rs2) \
    RV_R_TYPE(0x01, rs2, rs1, 0x0, rd, 0x33)

/* ADD rd, rs1, rs2 */
#define RV_ADD(rd, rs1, rs2) \
    RV_R_TYPE(0x00, rs2, rs1, 0x0, rd, 0x33)

/* SUB rd, rs1, rs2 */
#define RV_SUB(rd, rs1, rs2) \
    RV_R_TYPE(0x20, rs2, rs1, 0x0, rd, 0x33)

/* XOR rd, rs1, rs2 */
#define RV_XOR(rd, rs1, rs2) \
    RV_R_TYPE(0x00, rs2, rs1, 0x4, rd, 0x33)

/* I-type: imm[31:20] | rs1[19:15] | funct3[14:12] | rd[11:7] | opcode[6:0] */
#define RV_I_TYPE(imm12, rs1, funct3, rd, opcode) \
    (((imm12) << 20) | ((rs1) << 15) | ((funct3) << 12) | ((rd) << 7) | (opcode))

/* ADDI rd, rs1, imm */
#define RV_ADDI(rd, rs1, imm) \
    RV_I_TYPE((imm) & 0xFFF, rs1, 0x0, rd, 0x13)

/* MV rd, rs1 (pseudo: ADDI rd, rs1, 0) */
#define RV_MV(rd, rs1) RV_ADDI(rd, rs1, 0)

/* B-type: imm[12|10:5] | rs2 | rs1 | funct3 | imm[4:1|11] | opcode */
#define RV_B_TYPE(imm, rs2, rs1, funct3, opcode) \
    ((((imm) & 0x1000) << 19) | (((imm) & 0x7E0) << 20) | ((rs2) << 20) | \
     ((rs1) << 15) | ((funct3) << 12) | (((imm) & 0x1E) << 7) | \
     (((imm) & 0x800) >> 4) | (opcode))

/* BEQ rs1, rs2, offset (branch if equal) */
#define RV_BEQ(rs1, rs2, imm) \
    RV_B_TYPE(imm, rs2, rs1, 0x0, 0x63)

/* BNE rs1, rs2, offset (branch if not equal) */
#define RV_BNE(rs1, rs2, imm) \
    RV_B_TYPE(imm, rs2, rs1, 0x1, 0x63)

/* BGE rs1, rs2, offset (branch if greater/equal signed) */
#define RV_BGE(rs1, rs2, imm) \
    RV_B_TYPE(imm, rs2, rs1, 0x5, 0x63)

/* BLT rs1, rs2, offset (branch if less than signed) */
#define RV_BLT(rs1, rs2, imm) \
    RV_B_TYPE(imm, rs2, rs1, 0x4, 0x63)

/* SRAI rd, rs1, shamt (arithmetic shift right) */
#define RV_SRAI(rd, rs1, shamt) \
    RV_I_TYPE(0x400 | ((shamt) & 0x3F), rs1, 0x5, rd, 0x13)

/*
 * emit_floored_div_riscv64 - Generate RV64 code for Forth-83 floored division
 * 
 * Input:  a0 = dividend, a1 = divisor
 * Output: a0 = floored quotient
 * Clobbers: t0, t1, t2
 */
size_t emit_floored_div_riscv64(uint8_t* code, size_t max_size) {
    size_t pos = 0;
    
    /*
     * Algorithm:
     * t0 = a0 / a1      (symmetric quotient)
     * t1 = a0 % a1      (symmetric remainder)
     * if (t1 == 0) goto done
     * t2 = a0 ^ a1      (sign comparison)
     * if (t2 >= 0) goto done  (same signs)
     * t0 = t0 - 1       (correct quotient)
     * done:
     * a0 = t0
     */
    
    /* div t0, a0, a1  ; t0 = quotient */
    RV_EMIT32(code, pos, max_size, RV_DIV(RV_T0, RV_A0, RV_A1));
    
    /* rem t1, a0, a1  ; t1 = remainder */
    RV_EMIT32(code, pos, max_size, RV_REM(RV_T1, RV_A0, RV_A1));
    
    /* beq t1, zero, .done  ; if remainder == 0, skip (offset = 5 instructions = 20 bytes) */
    size_t beq_offset = pos;
    RV_EMIT32(code, pos, max_size, RV_BEQ(RV_T1, RV_ZERO, 0)); /* placeholder */
    
    /* xor t2, a0, a1  ; t2 = dividend ^ divisor */
    RV_EMIT32(code, pos, max_size, RV_XOR(RV_T2, RV_A0, RV_A1));
    
    /* bge t2, zero, .done  ; if sign bit clear (same signs), skip */
    size_t bge_offset = pos;
    RV_EMIT32(code, pos, max_size, RV_BGE(RV_T2, RV_ZERO, 0)); /* placeholder */
    
    /* addi t0, t0, -1  ; quotient -= 1 */
    RV_EMIT32(code, pos, max_size, RV_ADDI(RV_T0, RV_T0, -1));
    
    /* .done: */
    size_t done_offset = pos;
    
    /* mv a0, t0  ; return quotient */
    RV_EMIT32(code, pos, max_size, RV_MV(RV_A0, RV_T0));
    
    /* Patch branch offsets */
    if (code) {
        /* BEQ: jump from beq_offset to done_offset */
        int32_t beq_imm = done_offset - beq_offset;
        uint32_t beq_insn = RV_BEQ(RV_T1, RV_ZERO, beq_imm);
        code[beq_offset] = beq_insn & 0xFF;
        code[beq_offset+1] = (beq_insn >> 8) & 0xFF;
        code[beq_offset+2] = (beq_insn >> 16) & 0xFF;
        code[beq_offset+3] = (beq_insn >> 24) & 0xFF;
        
        /* BGE: jump from bge_offset to done_offset */
        int32_t bge_imm = done_offset - bge_offset;
        uint32_t bge_insn = RV_BGE(RV_T2, RV_ZERO, bge_imm);
        code[bge_offset] = bge_insn & 0xFF;
        code[bge_offset+1] = (bge_insn >> 8) & 0xFF;
        code[bge_offset+2] = (bge_insn >> 16) & 0xFF;
        code[bge_offset+3] = (bge_insn >> 24) & 0xFF;
    }
    
    return pos;
}

/*
 * emit_floored_mod_riscv64 - Generate RV64 code for Forth-83 floored modulo
 */
size_t emit_floored_mod_riscv64(uint8_t* code, size_t max_size) {
    size_t pos = 0;
    
    /* div t0, a0, a1  ; t0 = quotient (not used, but needed for consistency) */
    RV_EMIT32(code, pos, max_size, RV_DIV(RV_T0, RV_A0, RV_A1));
    
    /* rem t1, a0, a1  ; t1 = remainder */
    RV_EMIT32(code, pos, max_size, RV_REM(RV_T1, RV_A0, RV_A1));
    
    /* beq t1, zero, .done */
    size_t beq_offset = pos;
    RV_EMIT32(code, pos, max_size, RV_BEQ(RV_T1, RV_ZERO, 0));
    
    /* xor t2, a0, a1 */
    RV_EMIT32(code, pos, max_size, RV_XOR(RV_T2, RV_A0, RV_A1));
    
    /* bge t2, zero, .done */
    size_t bge_offset = pos;
    RV_EMIT32(code, pos, max_size, RV_BGE(RV_T2, RV_ZERO, 0));
    
    /* add t1, t1, a1  ; remainder += divisor */
    RV_EMIT32(code, pos, max_size, RV_ADD(RV_T1, RV_T1, RV_A1));
    
    /* .done: */
    size_t done_offset = pos;
    
    /* mv a0, t1  ; return remainder */
    RV_EMIT32(code, pos, max_size, RV_MV(RV_A0, RV_T1));
    
    /* Patch branches */
    if (code) {
        int32_t beq_imm = done_offset - beq_offset;
        uint32_t beq_insn = RV_BEQ(RV_T1, RV_ZERO, beq_imm);
        code[beq_offset] = beq_insn & 0xFF;
        code[beq_offset+1] = (beq_insn >> 8) & 0xFF;
        code[beq_offset+2] = (beq_insn >> 16) & 0xFF;
        code[beq_offset+3] = (beq_insn >> 24) & 0xFF;
        
        int32_t bge_imm = done_offset - bge_offset;
        uint32_t bge_insn = RV_BGE(RV_T2, RV_ZERO, bge_imm);
        code[bge_offset] = bge_insn & 0xFF;
        code[bge_offset+1] = (bge_insn >> 8) & 0xFF;
        code[bge_offset+2] = (bge_insn >> 16) & 0xFF;
        code[bge_offset+3] = (bge_insn >> 24) & 0xFF;
    }
    
    return pos;
}

/*
 * emit_floored_divmod_riscv64 - Combined div/mod for /MOD
 * Output: a0 = quotient, a1 = remainder
 */
size_t emit_floored_divmod_riscv64(uint8_t* code, size_t max_size) {
    size_t pos = 0;
    
    /* Save divisor since we'll overwrite a1 */
    /* mv t3, a1 */
    RV_EMIT32(code, pos, max_size, RV_MV(28, RV_A1));  /* t3 = x28 */
    
    /* div t0, a0, a1 */
    RV_EMIT32(code, pos, max_size, RV_DIV(RV_T0, RV_A0, RV_A1));
    
    /* rem t1, a0, a1 */
    RV_EMIT32(code, pos, max_size, RV_REM(RV_T1, RV_A0, RV_A1));
    
    /* beq t1, zero, .done */
    size_t beq_offset = pos;
    RV_EMIT32(code, pos, max_size, RV_BEQ(RV_T1, RV_ZERO, 0));
    
    /* xor t2, a0, t3  ; compare with original divisor */
    RV_EMIT32(code, pos, max_size, RV_XOR(RV_T2, RV_A0, 28));
    
    /* bge t2, zero, .done */
    size_t bge_offset = pos;
    RV_EMIT32(code, pos, max_size, RV_BGE(RV_T2, RV_ZERO, 0));
    
    /* addi t0, t0, -1  ; quotient -= 1 */
    RV_EMIT32(code, pos, max_size, RV_ADDI(RV_T0, RV_T0, -1));
    
    /* add t1, t1, t3  ; remainder += divisor */
    RV_EMIT32(code, pos, max_size, RV_ADD(RV_T1, RV_T1, 28));
    
    /* .done: */
    size_t done_offset = pos;
    
    /* mv a0, t0  ; quotient */
    RV_EMIT32(code, pos, max_size, RV_MV(RV_A0, RV_T0));
    
    /* mv a1, t1  ; remainder */
    RV_EMIT32(code, pos, max_size, RV_MV(RV_A1, RV_T1));
    
    /* Patch branches */
    if (code) {
        int32_t beq_imm = done_offset - beq_offset;
        uint32_t beq_insn = RV_BEQ(RV_T1, RV_ZERO, beq_imm);
        code[beq_offset] = beq_insn & 0xFF;
        code[beq_offset+1] = (beq_insn >> 8) & 0xFF;
        code[beq_offset+2] = (beq_insn >> 16) & 0xFF;
        code[beq_offset+3] = (beq_insn >> 24) & 0xFF;
        
        int32_t bge_imm = done_offset - bge_offset;
        uint32_t bge_insn = RV_BGE(RV_T2, RV_ZERO, bge_imm);
        code[bge_offset] = bge_insn & 0xFF;
        code[bge_offset+1] = (bge_insn >> 8) & 0xFF;
        code[bge_offset+2] = (bge_insn >> 16) & 0xFF;
        code[bge_offset+3] = (bge_insn >> 24) & 0xFF;
    }
    
    return pos;
}
