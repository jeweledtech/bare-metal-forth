/* ============================================================================
 * ARM64 (A64) Instruction Decoder - Public API
 * ============================================================================
 *
 * Decodes ARM64 fixed-width (4-byte) instructions for the driver extraction
 * pipeline. Covers the instruction subset needed to analyze bare-metal and
 * kernel drivers: data processing, loads/stores, branches, system instructions.
 *
 * Key for driver extraction: MRS/MSR (system register access) is the ARM64
 * equivalent of x86 IN/OUT — it's the signal that says "this code touches
 * hardware registers."
 *
 * Encoding reference: Arm Architecture Reference Manual (ARMv8-A, DDI 0487)
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#ifndef ARM64_DECODER_H
#define ARM64_DECODER_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* ---- Registers ---- */

typedef enum {
    A64_REG_X0  = 0,  A64_REG_X1  = 1,  A64_REG_X2  = 2,  A64_REG_X3  = 3,
    A64_REG_X4  = 4,  A64_REG_X5  = 5,  A64_REG_X6  = 6,  A64_REG_X7  = 7,
    A64_REG_X8  = 8,  A64_REG_X9  = 9,  A64_REG_X10 = 10, A64_REG_X11 = 11,
    A64_REG_X12 = 12, A64_REG_X13 = 13, A64_REG_X14 = 14, A64_REG_X15 = 15,
    A64_REG_X16 = 16, A64_REG_X17 = 17, A64_REG_X18 = 18, A64_REG_X19 = 19,
    A64_REG_X20 = 20, A64_REG_X21 = 21, A64_REG_X22 = 22, A64_REG_X23 = 23,
    A64_REG_X24 = 24, A64_REG_X25 = 25, A64_REG_X26 = 26, A64_REG_X27 = 27,
    A64_REG_X28 = 28, A64_REG_X29 = 29, A64_REG_X30 = 30,
    A64_REG_SP  = 31,  /* stack pointer (context-dependent with XZR) */
    A64_REG_XZR = 31,  /* zero register (context-dependent with SP) */
    A64_REG_NONE = -1,
} a64_register_t;

/* ---- Condition codes ---- */

typedef enum {
    A64_CC_EQ = 0x0, A64_CC_NE = 0x1,
    A64_CC_CS = 0x2, A64_CC_CC = 0x3,  /* HS/LO aliases */
    A64_CC_MI = 0x4, A64_CC_PL = 0x5,
    A64_CC_VS = 0x6, A64_CC_VC = 0x7,
    A64_CC_HI = 0x8, A64_CC_LS = 0x9,
    A64_CC_GE = 0xA, A64_CC_LT = 0xB,
    A64_CC_GT = 0xC, A64_CC_LE = 0xD,
    A64_CC_AL = 0xE, A64_CC_NV = 0xF,
} a64_cc_t;

/* ---- Instruction IDs ---- */

typedef enum {
    A64_INS_UNKNOWN = 0,

    /* Data movement */
    A64_INS_MOV,            /* MOV (register or inverted) */
    A64_INS_MOVZ,           /* MOVZ — move wide with zero */
    A64_INS_MOVK,           /* MOVK — move wide with keep */
    A64_INS_MOVN,           /* MOVN — move wide with NOT */

    /* Arithmetic */
    A64_INS_ADD,
    A64_INS_SUB,
    A64_INS_ADC,            /* add with carry */
    A64_INS_SBC,            /* subtract with carry */
    A64_INS_NEG,

    /* Logic */
    A64_INS_AND,
    A64_INS_ORR,
    A64_INS_EOR,            /* exclusive OR */
    A64_INS_BIC,            /* bit clear */
    A64_INS_ORN,            /* OR NOT */

    /* Shift */
    A64_INS_LSL,
    A64_INS_LSR,
    A64_INS_ASR,
    A64_INS_ROR,

    /* Comparison (flag-setting) */
    A64_INS_CMP,            /* SUBS with Rd=XZR */
    A64_INS_CMN,            /* ADDS with Rd=XZR */
    A64_INS_TST,            /* ANDS with Rd=XZR */

    /* Multiply */
    A64_INS_MUL,
    A64_INS_MADD,
    A64_INS_MSUB,
    A64_INS_SDIV,
    A64_INS_UDIV,

    /* Bitfield */
    A64_INS_BFM,            /* bitfield move */
    A64_INS_SBFM,           /* signed bitfield move */
    A64_INS_UBFM,           /* unsigned bitfield move */
    A64_INS_EXTR,           /* extract */

    /* Address computation */
    A64_INS_ADR,
    A64_INS_ADRP,

    /* Load/Store */
    A64_INS_LDR,            /* load register */
    A64_INS_STR,            /* store register */
    A64_INS_LDRB,           /* load byte */
    A64_INS_STRB,           /* store byte */
    A64_INS_LDRH,           /* load halfword */
    A64_INS_STRH,           /* store halfword */
    A64_INS_LDRSB,          /* load signed byte */
    A64_INS_LDRSH,          /* load signed halfword */
    A64_INS_LDRSW,          /* load signed word */
    A64_INS_LDP,            /* load pair */
    A64_INS_STP,            /* store pair */
    A64_INS_LDR_LITERAL,    /* PC-relative literal load */

    /* Conditional select */
    A64_INS_CSEL,
    A64_INS_CSINC,
    A64_INS_CSINV,
    A64_INS_CSNEG,

    /* Branches */
    A64_INS_B,              /* unconditional branch */
    A64_INS_BL,             /* branch with link (call) */
    A64_INS_BR,             /* branch to register */
    A64_INS_BLR,            /* branch with link to register */
    A64_INS_RET,            /* return (BR X30) */
    A64_INS_B_COND,         /* conditional branch */
    A64_INS_CBZ,            /* compare and branch if zero */
    A64_INS_CBNZ,           /* compare and branch if not zero */
    A64_INS_TBZ,            /* test bit and branch if zero */
    A64_INS_TBNZ,           /* test bit and branch if not zero */

    /* System — critical for driver extraction */
    A64_INS_MRS,            /* move from system register */
    A64_INS_MSR,            /* move to system register */
    A64_INS_SVC,            /* supervisor call */
    A64_INS_HVC,            /* hypervisor call */
    A64_INS_SMC,            /* secure monitor call */
    A64_INS_NOP,
    A64_INS_WFI,            /* wait for interrupt */
    A64_INS_WFE,            /* wait for event */
    A64_INS_SEV,            /* send event */
    A64_INS_DMB,            /* data memory barrier */
    A64_INS_DSB,            /* data synchronization barrier */
    A64_INS_ISB,            /* instruction synchronization barrier */

    A64_INS_COUNT
} a64_instruction_t;

/* ---- System register encoding ---- */

typedef struct {
    uint8_t  op0;       /* 2 bits */
    uint8_t  op1;       /* 3 bits */
    uint8_t  crn;       /* 4 bits (CRn) */
    uint8_t  crm;       /* 4 bits (CRm) */
    uint8_t  op2;       /* 3 bits */
    uint16_t encoding;  /* full 16-bit encoding: op0:op1:CRn:CRm:op2 */
} a64_sysreg_t;

/* ---- Operand types ---- */

typedef enum {
    A64_OP_NONE = 0,
    A64_OP_REG,         /* register Xn/Wn */
    A64_OP_IMM,         /* immediate value */
    A64_OP_MEM,         /* memory [Xn + offset] */
    A64_OP_ADDR,        /* PC-relative address (branch targets) */
    A64_OP_SYSREG,      /* system register (MRS/MSR) */
} a64_operand_type_t;

/* ---- Operand ---- */

typedef struct {
    a64_operand_type_t  type;
    uint8_t             size;       /* 4 (W) or 8 (X) bytes */
    int8_t              reg;        /* register index */
    int8_t              reg2;       /* second register (LDP/STP Rt2, or index) */
    int64_t             imm;        /* immediate, offset, or target address */
    a64_sysreg_t        sysreg;     /* system register (MRS/MSR) */
    uint8_t             shift;      /* shift amount (for shifted immediates) */
    uint8_t             extend;     /* extend type (for extended reg ops) */
} a64_operand_t;

/* ---- Decoded instruction ---- */

typedef struct {
    uint64_t            address;    /* virtual address */
    uint32_t            raw;        /* raw 32-bit instruction word */
    a64_instruction_t   instruction;
    uint8_t             operand_count;
    a64_operand_t       operands[4];
    a64_cc_t            cc;         /* condition code (B.cond, CSEL, etc.) */
    bool                sets_flags; /* instruction sets NZCV flags */
    bool                is_64bit;   /* true=X registers, false=W registers */
    bool                is_sysreg_access; /* true for MRS/MSR */
} a64_decoded_t;

/* ---- Decoder context ---- */

typedef struct {
    const uint8_t*      code;
    size_t              code_size;
    uint64_t            base_address;
    size_t              offset;
} a64_decoder_t;

/* ---- API ---- */

/* Initialize decoder context */
void a64_decoder_init(a64_decoder_t* dec, const uint8_t* code,
                      size_t code_size, uint64_t base_address);

/* Decode one instruction. Returns 4 on success, 0 at end, -1 on error. */
int a64_decode_one(a64_decoder_t* dec, a64_decoded_t* out);

/* Decode a range of instructions. Caller must free returned array. */
a64_decoded_t* a64_decode_range(a64_decoder_t* dec, size_t* count_out);

/* Print decoded instruction (for debugging). */
void a64_print_decoded(const a64_decoded_t* inst, FILE* out);

/* Get instruction name string. */
const char* a64_ins_name(a64_instruction_t ins);

/* Get register name (Xn/Wn/SP/XZR). */
const char* a64_reg_name(int8_t reg, bool is_64bit);

/* Get condition code name. */
const char* a64_cc_name(a64_cc_t cc);

/* Pack sysreg fields into 16-bit encoding. */
static inline uint16_t a64_sysreg_encode(uint8_t op0, uint8_t op1,
                                          uint8_t crn, uint8_t crm,
                                          uint8_t op2) {
    return ((uint16_t)(op0 & 3) << 14) |
           ((uint16_t)(op1 & 7) << 11) |
           ((uint16_t)(crn & 0xF) << 7) |
           ((uint16_t)(crm & 0xF) << 3) |
           (uint16_t)(op2 & 7);
}

#endif /* ARM64_DECODER_H */
