/* ============================================================================
 * x86 Instruction Decoder - Public API
 * ============================================================================
 *
 * Decodes x86-32 instructions for the driver extraction pipeline.
 * Supports the instruction subset needed to analyze Windows kernel drivers.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#ifndef X86_DECODER_H
#define X86_DECODER_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* ---- Decoder mode ---- */

typedef enum {
    X86_MODE_16 = 16,
    X86_MODE_32 = 32,
    X86_MODE_64 = 64,
} x86_mode_t;

/* ---- Registers ---- */

typedef enum {
    X86_REG_NONE = -1,
    /* 32-bit general purpose (also encode 8/16-bit by context) */
    X86_REG_EAX = 0, X86_REG_ECX = 1, X86_REG_EDX = 2, X86_REG_EBX = 3,
    X86_REG_ESP = 4, X86_REG_EBP = 5, X86_REG_ESI = 6, X86_REG_EDI = 7,
    /* 8-bit names (same encoding, context determines size) */
    X86_REG_AL = 0, X86_REG_CL = 1, X86_REG_DL = 2, X86_REG_BL = 3,
    X86_REG_AH = 4, X86_REG_CH = 5, X86_REG_DH = 6, X86_REG_BH = 7,
    /* 16-bit (same encoding) */
    X86_REG_AX = 0, X86_REG_CX = 1, X86_REG_DX = 2, X86_REG_BX = 3,
    X86_REG_SP = 4, X86_REG_BP = 5, X86_REG_SI = 6, X86_REG_DI = 7,
} x86_register_t;

/* ---- Instruction IDs ---- */

typedef enum {
    X86_INS_UNKNOWN = 0,

    /* Data movement */
    X86_INS_MOV,
    X86_INS_MOVZX,
    X86_INS_MOVSX,
    X86_INS_LEA,
    X86_INS_XCHG,
    X86_INS_PUSH,
    X86_INS_POP,
    X86_INS_PUSHAD,
    X86_INS_POPAD,

    /* Arithmetic */
    X86_INS_ADD,
    X86_INS_SUB,
    X86_INS_ADC,
    X86_INS_SBB,
    X86_INS_INC,
    X86_INS_DEC,
    X86_INS_NEG,
    X86_INS_MUL,
    X86_INS_IMUL,
    X86_INS_DIV,
    X86_INS_IDIV,
    X86_INS_CMP,

    /* Logic */
    X86_INS_AND,
    X86_INS_OR,
    X86_INS_XOR,
    X86_INS_NOT,
    X86_INS_TEST,
    X86_INS_SHL,
    X86_INS_SHR,
    X86_INS_SAR,
    X86_INS_ROL,
    X86_INS_ROR,

    /* Control flow */
    X86_INS_JMP,
    X86_INS_JCC,       /* All conditional jumps */
    X86_INS_CALL,
    X86_INS_RET,
    X86_INS_LOOP,
    X86_INS_INT,

    /* I/O - critical for driver extraction */
    X86_INS_IN,
    X86_INS_OUT,
    X86_INS_INS,
    X86_INS_OUTS,

    /* System */
    X86_INS_CLI,
    X86_INS_STI,
    X86_INS_HLT,
    X86_INS_NOP,
    X86_INS_LEAVE,
    X86_INS_CLD,
    X86_INS_STD,
    X86_INS_CDQ,
    X86_INS_CBW,

    /* String ops */
    X86_INS_REP_MOVSB,
    X86_INS_REP_MOVSD,
    X86_INS_REP_STOSB,
    X86_INS_REP_STOSD,

    /* Conditional set */
    X86_INS_SETCC,

    X86_INS_COUNT
} x86_instruction_t;

/* ---- Condition codes (for JCC and SETCC) ---- */

typedef enum {
    X86_CC_O  = 0x0, X86_CC_NO  = 0x1,
    X86_CC_B  = 0x2, X86_CC_AE  = 0x3,
    X86_CC_E  = 0x4, X86_CC_NE  = 0x5,
    X86_CC_BE = 0x6, X86_CC_A   = 0x7,
    X86_CC_S  = 0x8, X86_CC_NS  = 0x9,
    X86_CC_P  = 0xA, X86_CC_NP  = 0xB,
    X86_CC_L  = 0xC, X86_CC_GE  = 0xD,
    X86_CC_LE = 0xE, X86_CC_G   = 0xF,
} x86_cc_t;

/* ---- Operand types ---- */

typedef enum {
    X86_OP_NONE = 0,
    X86_OP_REG,         /* Register */
    X86_OP_MEM,         /* Memory [base + index*scale + disp] */
    X86_OP_IMM,         /* Immediate value */
    X86_OP_REL,         /* Relative offset (for jumps/calls) */
} x86_operand_type_t;

/* ---- Operand ---- */

typedef struct {
    x86_operand_type_t  type;
    uint8_t             size;       /* 1, 2, or 4 bytes */

    /* REG */
    int8_t              reg;        /* x86_register_t */

    /* MEM: [base + index*scale + disp] */
    int8_t              base;       /* base register (-1 = none) */
    int8_t              index;      /* index register (-1 = none) */
    uint8_t             scale;      /* 1, 2, 4, or 8 */
    int32_t             disp;       /* displacement */

    /* IMM / REL */
    int64_t             imm;        /* immediate or relative offset */
} x86_operand_t;

/* ---- Decoded instruction ---- */

typedef struct {
    uint64_t            address;        /* Virtual address */
    uint8_t             length;         /* Instruction length in bytes */
    x86_instruction_t   instruction;
    uint8_t             operand_count;
    x86_operand_t       operands[4];

    /* Prefix state */
    uint8_t             prefixes;       /* Bitmask: REP=1, REPNE=2, LOCK=4, OPSIZE=8, ADDRSIZE=16 */
    x86_cc_t            cc;             /* Condition code for JCC/SETCC */
} x86_decoded_t;

#define X86_PREFIX_REP      0x01
#define X86_PREFIX_REPNE    0x02
#define X86_PREFIX_LOCK     0x04
#define X86_PREFIX_OPSIZE   0x08
#define X86_PREFIX_ADDRSIZE 0x10

/* ---- Decoder context ---- */

typedef struct {
    x86_mode_t          mode;
    const uint8_t*      code;
    size_t              code_size;
    uint64_t            base_address;
    size_t              offset;
} x86_decoder_t;

/* ---- API ---- */

/* Initialize decoder context */
void x86_decoder_init(x86_decoder_t* dec, x86_mode_t mode,
                      const uint8_t* code, size_t code_size,
                      uint64_t base_address);

/* Decode one instruction at current offset. Returns bytes consumed, 0 on error/end. */
int x86_decode_one(x86_decoder_t* dec, x86_decoded_t* out);

/* Decode a range of instructions. Caller must free returned array. */
x86_decoded_t* x86_decode_range(x86_decoder_t* dec, size_t* count_out);

/* Print decoded instruction (for debugging). */
void x86_print_decoded(const x86_decoded_t* inst, FILE* out);

/* Get register name string (for printing). */
const char* x86_reg_name(int8_t reg, uint8_t size);

/* Get instruction name string. */
const char* x86_ins_name(x86_instruction_t ins);

/* Get condition code name string. */
const char* x86_cc_name(x86_cc_t cc);

#endif /* X86_DECODER_H */
