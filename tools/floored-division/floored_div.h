/* ============================================================================
 * Floored Division Implementation for Forth-83 Semantics
 * ============================================================================
 * 
 * Forth-83 Standard Division Semantics:
 *   - Quotient is rounded toward negative infinity (floored)
 *   - Remainder takes the sign of the divisor
 * 
 * This differs from most CPU hardware (x86 IDIV, ARM SDIV, RISC-V DIV) which
 * use symmetric (truncated) division where quotient rounds toward zero.
 * 
 * Example: -7 / 3
 *   Symmetric:  quotient = -2, remainder = -1  (because -2 * 3 + (-1) = -7)
 *   Floored:    quotient = -3, remainder =  2  (because -3 * 3 +   2  = -7)
 * 
 * Correction Algorithm:
 *   After symmetric division producing (q, r):
 *   If r != 0 AND sign(dividend) != sign(divisor):
 *     q = q - 1
 *     r = r + divisor
 * 
 * Copyright (c) 2026 Jolly Genius Inc.
 * Ship's Systems Software - Built for reliability, not convenience.
 * ============================================================================ */

#ifndef FLOORED_DIV_H
#define FLOORED_DIV_H

#include <stdint.h>
#include <stdbool.h>

/* ============================================================================
 * Pure C Reference Implementation
 * ============================================================================ */

/* 32-bit floored division */
static inline int32_t floored_div32(int32_t dividend, int32_t divisor) {
    int32_t q = dividend / divisor;  /* Symmetric (truncated) division */
    int32_t r = dividend % divisor;
    
    /* Correction: if remainder nonzero and signs differ, adjust */
    if (r != 0 && ((dividend ^ divisor) < 0)) {
        q -= 1;
    }
    return q;
}

static inline int32_t floored_mod32(int32_t dividend, int32_t divisor) {
    int32_t r = dividend % divisor;
    
    /* Correction: if remainder nonzero and signs differ, adjust */
    if (r != 0 && ((dividend ^ divisor) < 0)) {
        r += divisor;
    }
    return r;
}

/* 64-bit floored division */
static inline int64_t floored_div64(int64_t dividend, int64_t divisor) {
    int64_t q = dividend / divisor;
    int64_t r = dividend % divisor;
    
    if (r != 0 && ((dividend ^ divisor) < 0)) {
        q -= 1;
    }
    return q;
}

static inline int64_t floored_mod64(int64_t dividend, int64_t divisor) {
    int64_t r = dividend % divisor;
    
    if (r != 0 && ((dividend ^ divisor) < 0)) {
        r += divisor;
    }
    return r;
}

/* Combined divmod for efficiency (single division operation) */
typedef struct {
    int64_t quotient;
    int64_t remainder;
} divmod_result_t;

static inline divmod_result_t floored_divmod64(int64_t dividend, int64_t divisor) {
    divmod_result_t result;
    result.quotient = dividend / divisor;
    result.remainder = dividend % divisor;
    
    if (result.remainder != 0 && ((dividend ^ divisor) < 0)) {
        result.quotient -= 1;
        result.remainder += divisor;
    }
    return result;
}

/* ============================================================================
 * UIR Opcode Definitions for Floored Division
 * ============================================================================ */

/* Add these to your uir.h enum if not present */
#ifndef UIR_FDIV
#define UIR_FDIV      0x40   /* Floored division (Forth-83 semantics) */
#define UIR_FMOD      0x41   /* Floored modulo (Forth-83 semantics) */
#define UIR_FDIVMOD   0x42   /* Combined floored div/mod */
#endif

/* ============================================================================
 * Architecture-Specific Code Generation Sizes
 * ============================================================================ */

/* Estimated code sizes for planning buffer allocation */
#define FLOORED_DIV_X64_SIZE    64   /* x86-64: ~40-60 bytes */
#define FLOORED_DIV_ARM64_SIZE  48   /* ARM64:  ~32-44 bytes */
#define FLOORED_DIV_RV64_SIZE   56   /* RISC-V: ~40-52 bytes */

#endif /* FLOORED_DIV_H */
