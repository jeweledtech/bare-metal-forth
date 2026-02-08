/* ============================================================================
 * x86-64 Code Generation for Floored Division (Forth-83 Semantics)
 * ============================================================================
 * 
 * Input:  dividend in RAX, divisor on stack (popped to R10)
 * Output: quotient in RAX (for FDIV), remainder in RAX (for FMOD)
 * 
 * Algorithm (post-IDIV correction):
 *   1. Perform symmetric IDIV (quotient in RAX, remainder in RDX)
 *   2. Test if remainder is zero -> done
 *   3. Test if signs of dividend and divisor differ
 *   4. If both conditions: q -= 1, r += divisor
 * 
 * Register usage:
 *   RAX - dividend, then quotient
 *   R10 - divisor (preserved for correction)
 *   RDX - sign extension, then remainder
 *   R11 - scratch for XOR sign test
 * ============================================================================ */

#include "floored_div.h"
#include <stdio.h>

/* Emit single byte */
#define EMIT(b) do { if (code && pos < max_size) code[pos] = (b); pos++; } while(0)

/* Emit 32-bit immediate (little-endian) */
#define EMIT32(v) do { \
    uint32_t _v = (uint32_t)(v); \
    EMIT(_v & 0xFF); EMIT((_v >> 8) & 0xFF); \
    EMIT((_v >> 16) & 0xFF); EMIT((_v >> 24) & 0xFF); \
} while(0)

/*
 * emit_floored_div_x64 - Generate x64 machine code for Forth-83 floored division
 * 
 * Assumes: dividend in RAX, divisor in R10
 * Result:  quotient in RAX
 * Clobbers: RDX, R11
 */
size_t emit_floored_div_x64(uint8_t* code, size_t max_size) {
    size_t pos = 0;
    
    /* 
     * Save original dividend sign for later comparison
     * mov r11, rax
     */
    EMIT(0x49); EMIT(0x89); EMIT(0xC3);  /* mov r11, rax */
    
    /*
     * Sign-extend RAX into RDX:RAX
     * cqo
     */
    EMIT(0x48); EMIT(0x99);              /* cqo */
    
    /*
     * Signed divide RDX:RAX by R10
     * idiv r10
     * Result: RAX = quotient, RDX = remainder
     */
    EMIT(0x49); EMIT(0xF7); EMIT(0xFA); /* idiv r10 */
    
    /*
     * If remainder is zero, no correction needed
     * test rdx, rdx
     * jz .done
     */
    EMIT(0x48); EMIT(0x85); EMIT(0xD2); /* test rdx, rdx */
    EMIT(0x74);                          /* jz rel8 */
    size_t jz_done_offset = pos;
    EMIT(0x00);                          /* placeholder */
    
    /*
     * Check if signs differ: XOR dividend with divisor
     * xor r11, r10      ; r11 = original_dividend ^ divisor  
     * jns .done         ; if sign bit clear, same signs, no correction
     */
    EMIT(0x4D); EMIT(0x31); EMIT(0xD3); /* xor r11, r10 */
    EMIT(0x79);                          /* jns rel8 */
    size_t jns_done_offset = pos;
    EMIT(0x00);                          /* placeholder */
    
    /*
     * Signs differ and remainder nonzero: apply correction
     * dec rax           ; quotient -= 1
     * add rdx, r10      ; remainder += divisor
     */
    EMIT(0x48); EMIT(0xFF); EMIT(0xC8); /* dec rax */
    EMIT(0x49); EMIT(0x01); EMIT(0xD2); /* add rdx, r10 (if we need remainder) */
    
    /* .done: */
    size_t done_label = pos;
    
    /* Patch jump offsets */
    if (code) {
        code[jz_done_offset] = (uint8_t)(done_label - jz_done_offset - 1);
        code[jns_done_offset] = (uint8_t)(done_label - jns_done_offset - 1);
    }
    
    return pos;
}

/*
 * emit_floored_mod_x64 - Generate x64 machine code for Forth-83 floored modulo
 * 
 * Same as div, but moves remainder to RAX at end
 */
size_t emit_floored_mod_x64(uint8_t* code, size_t max_size) {
    size_t pos = 0;
    
    /* Save original dividend sign */
    EMIT(0x49); EMIT(0x89); EMIT(0xC3);  /* mov r11, rax */
    
    /* Sign-extend and divide */
    EMIT(0x48); EMIT(0x99);              /* cqo */
    EMIT(0x49); EMIT(0xF7); EMIT(0xFA); /* idiv r10 */
    
    /* If remainder is zero, no correction needed */
    EMIT(0x48); EMIT(0x85); EMIT(0xD2); /* test rdx, rdx */
    EMIT(0x74);
    size_t jz_done_offset = pos;
    EMIT(0x00);
    
    /* Check if signs differ */
    EMIT(0x4D); EMIT(0x31); EMIT(0xD3); /* xor r11, r10 */
    EMIT(0x79);
    size_t jns_done_offset = pos;
    EMIT(0x00);
    
    /* Apply correction: remainder += divisor */
    EMIT(0x4C); EMIT(0x01); EMIT(0xD2); /* add rdx, r10 */
    
    /* .done: move remainder to rax */
    size_t done_label = pos;
    EMIT(0x48); EMIT(0x89); EMIT(0xD0); /* mov rax, rdx */
    
    /* Patch jumps to point AFTER the mov */
    if (code) {
        /* jz and jns should skip correction but still do the mov */
        code[jz_done_offset] = (uint8_t)(done_label - jz_done_offset - 1);
        code[jns_done_offset] = (uint8_t)(done_label - jns_done_offset - 1);
    }
    
    return pos;
}

/*
 * emit_floored_divmod_x64 - Combined div/mod, quotient in RAX, remainder in RDX
 * 
 * Forth's /MOD word needs both values
 */
size_t emit_floored_divmod_x64(uint8_t* code, size_t max_size) {
    size_t pos = 0;
    
    /* Save original dividend sign */
    EMIT(0x49); EMIT(0x89); EMIT(0xC3);  /* mov r11, rax */
    
    /* Sign-extend and divide */
    EMIT(0x48); EMIT(0x99);              /* cqo */
    EMIT(0x49); EMIT(0xF7); EMIT(0xFA); /* idiv r10 */
    
    /* If remainder is zero, no correction needed */
    EMIT(0x48); EMIT(0x85); EMIT(0xD2); /* test rdx, rdx */
    EMIT(0x74);
    size_t jz_done_offset = pos;
    EMIT(0x00);
    
    /* Check if signs differ */
    EMIT(0x4D); EMIT(0x31); EMIT(0xD3); /* xor r11, r10 */
    EMIT(0x79);
    size_t jns_done_offset = pos;
    EMIT(0x00);
    
    /* Apply full correction */
    EMIT(0x48); EMIT(0xFF); EMIT(0xC8); /* dec rax (quotient -= 1) */
    EMIT(0x4C); EMIT(0x01); EMIT(0xD2); /* add rdx, r10 (remainder += divisor) */
    
    /* .done: */
    size_t done_label = pos;
    
    if (code) {
        code[jz_done_offset] = (uint8_t)(done_label - jz_done_offset - 1);
        code[jns_done_offset] = (uint8_t)(done_label - jns_done_offset - 1);
    }
    
    /* Result: quotient in RAX, remainder in RDX */
    return pos;
}

/* ============================================================================
 * Integration with Universal Binary Translator
 * ============================================================================ */

/*
 * This function shows how to integrate floored division into the existing
 * codegen.c switch statement. Add this to your UIR case handling:
 */
void codegen_emit_floored_div_example(void* cg_ptr /* codegen_t* */) {
    /* 
     * In your actual codegen.c, replace the simple IDIV emission with:
     * 
     * case UIR_FDIV:
     *     if (cg->target == CODEGEN_TARGET_X64) {
     *         // Pop divisor to R10
     *         x86_emit_mov_reg_reg(&cg->code, X64_R10, X64_RAX);
     *         x86_emit_pop(&cg->code, X64_RAX);  // dividend
     *         
     *         // Emit floored division code
     *         size_t needed = emit_floored_div_x64(NULL, 0);
     *         ensure_code_space(&cg->code, needed);
     *         cg->code.size += emit_floored_div_x64(
     *             cg->code.data + cg->code.size, 
     *             cg->code.capacity - cg->code.size);
     *     }
     *     break;
     */
}

#undef EMIT
#undef EMIT32
