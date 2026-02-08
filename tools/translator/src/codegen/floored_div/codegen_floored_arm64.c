/* ============================================================================
 * ARM64 Code Generation for Floored Division (Forth-83 Semantics)
 * ============================================================================
 * 
 * ARM64 uses SDIV for signed division which truncates toward zero (symmetric).
 * There is no hardware instruction that gives both quotient and remainder;
 * we compute remainder as: r = dividend - (quotient * divisor)
 * 
 * Input:  X0 = dividend, X1 = divisor
 * Output: X0 = quotient (FDIV) or remainder (FMOD)
 * 
 * Register usage:
 *   X0  - dividend, then quotient/remainder
 *   X1  - divisor (preserved)
 *   X2  - quotient (temporary)
 *   X3  - remainder (temporary)
 *   X4  - sign comparison scratch
 * ============================================================================ */

#include "floored_div.h"
#include <stdio.h>

/* ARM64 instruction encoding helpers */
#define ARM64_EMIT32(code, pos, max, insn) do { \
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

/* ARM64 instruction encodings for 64-bit operations */

/* SDIV Xd, Xn, Xm: Signed divide */
#define ARM64_SDIV(rd, rn, rm) \
    (0x9AC00C00 | ((rm) << 16) | ((rn) << 5) | (rd))

/* MSUB Xd, Xn, Xm, Xa: Xd = Xa - Xn*Xm (for computing remainder) */
#define ARM64_MSUB(rd, rn, rm, ra) \
    (0x9B008000 | ((rm) << 16) | ((ra) << 10) | ((rn) << 5) | (rd))

/* MOV Xd, Xm (ORR Xd, XZR, Xm) */
#define ARM64_MOV(rd, rm) \
    (0xAA0003E0 | ((rm) << 16) | (rd))

/* SUB Xd, Xn, #imm (immediate subtract) */
#define ARM64_SUB_IMM(rd, rn, imm12) \
    (0xD1000000 | ((imm12) << 10) | ((rn) << 5) | (rd))

/* ADD Xd, Xn, Xm (register add) */
#define ARM64_ADD(rd, rn, rm) \
    (0x8B000000 | ((rm) << 16) | ((rn) << 5) | (rd))

/* EOR Xd, Xn, Xm (XOR for sign comparison) */
#define ARM64_EOR(rd, rn, rm) \
    (0xCA000000 | ((rm) << 16) | ((rn) << 5) | (rd))

/* CMP Xn, #0 (SUBS XZR, Xn, #0) */
#define ARM64_CMP_ZERO(rn) \
    (0xF100001F | ((rn) << 5))

/* CBZ Xn, offset: Branch if Xn == 0 */
#define ARM64_CBZ(rn, imm19) \
    (0xB4000000 | (((imm19) & 0x7FFFF) << 5) | (rn))

/* TBZ Xn, #bit, offset: Test bit and branch if zero */
#define ARM64_TBZ(rn, bit, imm14) \
    (0x36000000 | (((bit) & 0x20) << 26) | (((bit) & 0x1F) << 19) | \
     (((imm14) & 0x3FFF) << 5) | (rn))

/* TBNZ Xn, #bit, offset: Test bit and branch if nonzero */
#define ARM64_TBNZ(rn, bit, imm14) \
    (0x37000000 | (((bit) & 0x20) << 26) | (((bit) & 0x1F) << 19) | \
     (((imm14) & 0x3FFF) << 5) | (rn))

/*
 * emit_floored_div_arm64 - Generate ARM64 code for Forth-83 floored division
 * 
 * Input:  X0 = dividend, X1 = divisor
 * Output: X0 = floored quotient
 * Clobbers: X2, X3, X4
 */
size_t emit_floored_div_arm64(uint8_t* code, size_t max_size) {
    size_t pos = 0;
    
    /*
     * Algorithm:
     * 1. q = dividend / divisor  (SDIV - symmetric)
     * 2. r = dividend - q * divisor (MSUB)
     * 3. if r != 0 and signs differ: q -= 1
     */
    
    /* sdiv x2, x0, x1  ; x2 = quotient (symmetric) */
    ARM64_EMIT32(code, pos, max_size, ARM64_SDIV(2, 0, 1));
    
    /* msub x3, x2, x1, x0  ; x3 = x0 - x2*x1 = remainder */
    ARM64_EMIT32(code, pos, max_size, ARM64_MSUB(3, 2, 1, 0));
    
    /* cbz x3, .done  ; if remainder == 0, no correction */
    size_t cbz_offset = pos;
    ARM64_EMIT32(code, pos, max_size, ARM64_CBZ(3, 0)); /* placeholder */
    
    /* eor x4, x0, x1  ; x4 = dividend ^ divisor */
    ARM64_EMIT32(code, pos, max_size, ARM64_EOR(4, 0, 1));
    
    /* tbz x4, #63, .done  ; if sign bit clear, same signs, skip */
    size_t tbz_offset = pos;
    ARM64_EMIT32(code, pos, max_size, ARM64_TBZ(4, 63, 0)); /* placeholder */
    
    /* sub x2, x2, #1  ; quotient -= 1 */
    ARM64_EMIT32(code, pos, max_size, ARM64_SUB_IMM(2, 2, 1));
    
    /* .done: */
    size_t done_offset = pos;
    
    /* mov x0, x2  ; return quotient in x0 */
    ARM64_EMIT32(code, pos, max_size, ARM64_MOV(0, 2));
    
    /* Patch branch offsets (in instructions, not bytes) */
    if (code) {
        int32_t cbz_target = (done_offset - cbz_offset) / 4;
        int32_t tbz_target = (done_offset - tbz_offset) / 4;
        
        /* Repatch CBZ */
        uint32_t cbz_insn = ARM64_CBZ(3, cbz_target);
        code[cbz_offset] = cbz_insn & 0xFF;
        code[cbz_offset+1] = (cbz_insn >> 8) & 0xFF;
        code[cbz_offset+2] = (cbz_insn >> 16) & 0xFF;
        code[cbz_offset+3] = (cbz_insn >> 24) & 0xFF;
        
        /* Repatch TBZ */
        uint32_t tbz_insn = ARM64_TBZ(4, 63, tbz_target);
        code[tbz_offset] = tbz_insn & 0xFF;
        code[tbz_offset+1] = (tbz_insn >> 8) & 0xFF;
        code[tbz_offset+2] = (tbz_insn >> 16) & 0xFF;
        code[tbz_offset+3] = (tbz_insn >> 24) & 0xFF;
    }
    
    return pos;
}

/*
 * emit_floored_mod_arm64 - Generate ARM64 code for Forth-83 floored modulo
 */
size_t emit_floored_mod_arm64(uint8_t* code, size_t max_size) {
    size_t pos = 0;
    
    /* sdiv x2, x0, x1  ; x2 = quotient (symmetric) */
    ARM64_EMIT32(code, pos, max_size, ARM64_SDIV(2, 0, 1));
    
    /* msub x3, x2, x1, x0  ; x3 = remainder */
    ARM64_EMIT32(code, pos, max_size, ARM64_MSUB(3, 2, 1, 0));
    
    /* cbz x3, .done  ; if remainder == 0, no correction */
    size_t cbz_offset = pos;
    ARM64_EMIT32(code, pos, max_size, ARM64_CBZ(3, 0));
    
    /* eor x4, x0, x1  ; x4 = dividend ^ divisor */
    ARM64_EMIT32(code, pos, max_size, ARM64_EOR(4, 0, 1));
    
    /* tbz x4, #63, .done  ; if same signs, skip */
    size_t tbz_offset = pos;
    ARM64_EMIT32(code, pos, max_size, ARM64_TBZ(4, 63, 0));
    
    /* add x3, x3, x1  ; remainder += divisor */
    ARM64_EMIT32(code, pos, max_size, ARM64_ADD(3, 3, 1));
    
    /* .done: */
    size_t done_offset = pos;
    
    /* mov x0, x3  ; return remainder in x0 */
    ARM64_EMIT32(code, pos, max_size, ARM64_MOV(0, 3));
    
    /* Patch branches */
    if (code) {
        int32_t cbz_target = (done_offset - cbz_offset) / 4;
        int32_t tbz_target = (done_offset - tbz_offset) / 4;
        
        uint32_t cbz_insn = ARM64_CBZ(3, cbz_target);
        code[cbz_offset] = cbz_insn & 0xFF;
        code[cbz_offset+1] = (cbz_insn >> 8) & 0xFF;
        code[cbz_offset+2] = (cbz_insn >> 16) & 0xFF;
        code[cbz_offset+3] = (cbz_insn >> 24) & 0xFF;
        
        uint32_t tbz_insn = ARM64_TBZ(4, 63, tbz_target);
        code[tbz_offset] = tbz_insn & 0xFF;
        code[tbz_offset+1] = (tbz_insn >> 8) & 0xFF;
        code[tbz_offset+2] = (tbz_insn >> 16) & 0xFF;
        code[tbz_offset+3] = (tbz_insn >> 24) & 0xFF;
    }
    
    return pos;
}

/*
 * emit_floored_divmod_arm64 - Combined div/mod
 * Output: X0 = quotient, X1 = remainder (for Forth's /MOD)
 */
size_t emit_floored_divmod_arm64(uint8_t* code, size_t max_size) {
    size_t pos = 0;
    
    /* Save divisor to X5 since we'll overwrite X1 */
    ARM64_EMIT32(code, pos, max_size, ARM64_MOV(5, 1));
    
    /* sdiv x2, x0, x1 */
    ARM64_EMIT32(code, pos, max_size, ARM64_SDIV(2, 0, 1));
    
    /* msub x3, x2, x1, x0 */
    ARM64_EMIT32(code, pos, max_size, ARM64_MSUB(3, 2, 1, 0));
    
    /* cbz x3, .done */
    size_t cbz_offset = pos;
    ARM64_EMIT32(code, pos, max_size, ARM64_CBZ(3, 0));
    
    /* eor x4, x0, x5 */
    ARM64_EMIT32(code, pos, max_size, ARM64_EOR(4, 0, 5));
    
    /* tbz x4, #63, .done */
    size_t tbz_offset = pos;
    ARM64_EMIT32(code, pos, max_size, ARM64_TBZ(4, 63, 0));
    
    /* sub x2, x2, #1 */
    ARM64_EMIT32(code, pos, max_size, ARM64_SUB_IMM(2, 2, 1));
    
    /* add x3, x3, x5 */
    ARM64_EMIT32(code, pos, max_size, ARM64_ADD(3, 3, 5));
    
    /* .done: */
    size_t done_offset = pos;
    
    /* mov x0, x2  ; quotient */
    ARM64_EMIT32(code, pos, max_size, ARM64_MOV(0, 2));
    
    /* mov x1, x3  ; remainder */
    ARM64_EMIT32(code, pos, max_size, ARM64_MOV(1, 3));
    
    /* Patch branches */
    if (code) {
        int32_t cbz_target = (done_offset - cbz_offset) / 4;
        int32_t tbz_target = (done_offset - tbz_offset) / 4;
        
        uint32_t cbz_insn = ARM64_CBZ(3, cbz_target);
        code[cbz_offset] = cbz_insn & 0xFF;
        code[cbz_offset+1] = (cbz_insn >> 8) & 0xFF;
        code[cbz_offset+2] = (cbz_insn >> 16) & 0xFF;
        code[cbz_offset+3] = (cbz_insn >> 24) & 0xFF;
        
        uint32_t tbz_insn = ARM64_TBZ(4, 63, tbz_target);
        code[tbz_offset] = tbz_insn & 0xFF;
        code[tbz_offset+1] = (tbz_insn >> 8) & 0xFF;
        code[tbz_offset+2] = (tbz_insn >> 16) & 0xFF;
        code[tbz_offset+3] = (tbz_insn >> 24) & 0xFF;
    }
    
    return pos;
}
