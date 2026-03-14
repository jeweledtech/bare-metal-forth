/* ============================================================================
 * ARM64 (A64) Instruction Decoder Implementation
 * ============================================================================
 *
 * Fixed-width 4-byte instruction decoding via hierarchical bit-field dispatch.
 * Top-level group is bits [28:25], then sub-group decoders handle specifics.
 *
 * Key: MRS/MSR carry the 16-bit system register encoding (op0:op1:CRn:CRm:op2)
 * which identifies the hardware register being accessed — the ARM64 equivalent
 * of x86 port numbers for driver extraction.
 *
 * Encoding reference: Arm Architecture Reference Manual (ARMv8-A, DDI 0487)
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "arm64_decoder.h"

/* ---- Bit extraction helpers ---- */

static inline uint32_t bits(uint32_t insn, int hi, int lo) {
    return (insn >> lo) & ((1u << (hi - lo + 1)) - 1);
}

static inline uint32_t bit(uint32_t insn, int pos) {
    return (insn >> pos) & 1;
}

/* Sign-extend a value of given bit width to int64_t */
static inline int64_t sign_extend(uint64_t val, int width) {
    uint64_t sign_bit = 1ULL << (width - 1);
    return (int64_t)((val ^ sign_bit) - sign_bit);
}

/* ---- Name tables ---- */

static const char* const ins_names[] = {
    [A64_INS_UNKNOWN] = "unknown",
    [A64_INS_MOV]     = "mov",
    [A64_INS_MOVZ]    = "movz",
    [A64_INS_MOVK]    = "movk",
    [A64_INS_MOVN]    = "movn",
    [A64_INS_ADD]     = "add",
    [A64_INS_SUB]     = "sub",
    [A64_INS_ADC]     = "adc",
    [A64_INS_SBC]     = "sbc",
    [A64_INS_NEG]     = "neg",
    [A64_INS_AND]     = "and",
    [A64_INS_ORR]     = "orr",
    [A64_INS_EOR]     = "eor",
    [A64_INS_BIC]     = "bic",
    [A64_INS_ORN]     = "orn",
    [A64_INS_LSL]     = "lsl",
    [A64_INS_LSR]     = "lsr",
    [A64_INS_ASR]     = "asr",
    [A64_INS_ROR]     = "ror",
    [A64_INS_CMP]     = "cmp",
    [A64_INS_CMN]     = "cmn",
    [A64_INS_TST]     = "tst",
    [A64_INS_MUL]     = "mul",
    [A64_INS_MADD]    = "madd",
    [A64_INS_MSUB]    = "msub",
    [A64_INS_SDIV]    = "sdiv",
    [A64_INS_UDIV]    = "udiv",
    [A64_INS_BFM]     = "bfm",
    [A64_INS_SBFM]    = "sbfm",
    [A64_INS_UBFM]    = "ubfm",
    [A64_INS_EXTR]    = "extr",
    [A64_INS_ADR]     = "adr",
    [A64_INS_ADRP]    = "adrp",
    [A64_INS_LDR]     = "ldr",
    [A64_INS_STR]     = "str",
    [A64_INS_LDRB]    = "ldrb",
    [A64_INS_STRB]    = "strb",
    [A64_INS_LDRH]    = "ldrh",
    [A64_INS_STRH]    = "strh",
    [A64_INS_LDRSB]   = "ldrsb",
    [A64_INS_LDRSH]   = "ldrsh",
    [A64_INS_LDRSW]   = "ldrsw",
    [A64_INS_LDP]     = "ldp",
    [A64_INS_STP]     = "stp",
    [A64_INS_LDR_LITERAL] = "ldr",
    [A64_INS_CSEL]    = "csel",
    [A64_INS_CSINC]   = "csinc",
    [A64_INS_CSINV]   = "csinv",
    [A64_INS_CSNEG]   = "csneg",
    [A64_INS_B]       = "b",
    [A64_INS_BL]      = "bl",
    [A64_INS_BR]      = "br",
    [A64_INS_BLR]     = "blr",
    [A64_INS_RET]     = "ret",
    [A64_INS_B_COND]  = "b.cond",
    [A64_INS_CBZ]     = "cbz",
    [A64_INS_CBNZ]    = "cbnz",
    [A64_INS_TBZ]     = "tbz",
    [A64_INS_TBNZ]    = "tbnz",
    [A64_INS_MRS]     = "mrs",
    [A64_INS_MSR]     = "msr",
    [A64_INS_SVC]     = "svc",
    [A64_INS_HVC]     = "hvc",
    [A64_INS_SMC]     = "smc",
    [A64_INS_NOP]     = "nop",
    [A64_INS_WFI]     = "wfi",
    [A64_INS_WFE]     = "wfe",
    [A64_INS_SEV]     = "sev",
    [A64_INS_DMB]     = "dmb",
    [A64_INS_DSB]     = "dsb",
    [A64_INS_ISB]     = "isb",
};

static const char* const cc_names[] = {
    [A64_CC_EQ] = "eq", [A64_CC_NE] = "ne",
    [A64_CC_CS] = "cs", [A64_CC_CC] = "cc",
    [A64_CC_MI] = "mi", [A64_CC_PL] = "pl",
    [A64_CC_VS] = "vs", [A64_CC_VC] = "vc",
    [A64_CC_HI] = "hi", [A64_CC_LS] = "ls",
    [A64_CC_GE] = "ge", [A64_CC_LT] = "lt",
    [A64_CC_GT] = "gt", [A64_CC_LE] = "le",
    [A64_CC_AL] = "al", [A64_CC_NV] = "nv",
};

const char* a64_ins_name(a64_instruction_t ins) {
    if (ins < 0 || ins >= A64_INS_COUNT) return "?";
    return ins_names[ins] ? ins_names[ins] : "?";
}

const char* a64_cc_name(a64_cc_t cc) {
    if (cc > A64_CC_NV) return "?";
    return cc_names[cc];
}

const char* a64_reg_name(int8_t reg, bool is_64bit) {
    static const char* const x_names[] = {
        "x0","x1","x2","x3","x4","x5","x6","x7",
        "x8","x9","x10","x11","x12","x13","x14","x15",
        "x16","x17","x18","x19","x20","x21","x22","x23",
        "x24","x25","x26","x27","x28","x29","x30","sp"
    };
    static const char* const w_names[] = {
        "w0","w1","w2","w3","w4","w5","w6","w7",
        "w8","w9","w10","w11","w12","w13","w14","w15",
        "w16","w17","w18","w19","w20","w21","w22","w23",
        "w24","w25","w26","w27","w28","w29","w30","wsp"
    };
    if (reg < 0 || reg > 31) return "?";
    return is_64bit ? x_names[reg] : w_names[reg];
}

/* ---- Decoder init ---- */

void a64_decoder_init(a64_decoder_t* dec, const uint8_t* code,
                      size_t code_size, uint64_t base_address) {
    dec->code = code;
    dec->code_size = code_size;
    dec->base_address = base_address;
    dec->offset = 0;
}

/* ---- Operand construction helpers ---- */

static a64_operand_t op_reg(int8_t reg, bool is_64bit) {
    a64_operand_t op;
    memset(&op, 0, sizeof(op));
    op.type = A64_OP_REG;
    op.reg = reg;
    op.size = is_64bit ? 8 : 4;
    return op;
}

static a64_operand_t op_imm(int64_t val) {
    a64_operand_t op;
    memset(&op, 0, sizeof(op));
    op.type = A64_OP_IMM;
    op.imm = val;
    return op;
}

static a64_operand_t op_addr(int64_t target) {
    a64_operand_t op;
    memset(&op, 0, sizeof(op));
    op.type = A64_OP_ADDR;
    op.imm = target;
    return op;
}

static a64_operand_t op_mem(int8_t base, int64_t offset, uint8_t size) {
    a64_operand_t op;
    memset(&op, 0, sizeof(op));
    op.type = A64_OP_MEM;
    op.reg = base;
    op.imm = offset;
    op.size = size;
    return op;
}

static a64_operand_t op_sysreg(uint32_t insn) {
    a64_operand_t op;
    memset(&op, 0, sizeof(op));
    op.type = A64_OP_SYSREG;
    op.sysreg.op0 = bits(insn, 20, 19);
    op.sysreg.op1 = bits(insn, 18, 16);
    op.sysreg.crn = bits(insn, 15, 12);
    op.sysreg.crm = bits(insn, 11, 8);
    op.sysreg.op2 = bits(insn, 7, 5);
    op.sysreg.encoding = a64_sysreg_encode(
        op.sysreg.op0, op.sysreg.op1,
        op.sysreg.crn, op.sysreg.crm, op.sysreg.op2);
    return op;
}

/* ---- Sub-decoders ---- */

/* Data Processing — Immediate group */
static void decode_dp_imm(uint32_t insn, uint64_t addr, a64_decoded_t* out) {
    uint32_t op0 = bits(insn, 25, 23);
    bool sf = bit(insn, 31); /* 1 = 64-bit */
    out->is_64bit = sf;

    switch (op0) {
    case 0: case 1: {
        /* PC-relative addressing: ADR (op0=0), ADRP (op0=1) */
        bool is_adrp = bit(insn, 31);
        int64_t immhi = sign_extend(bits(insn, 23, 5), 19);
        uint32_t immlo = bits(insn, 30, 29);
        int64_t imm = (immhi << 2) | immlo;
        int64_t target;
        if (is_adrp) {
            out->instruction = A64_INS_ADRP;
            target = (int64_t)(addr & ~0xFFFULL) + (imm << 12);
        } else {
            out->instruction = A64_INS_ADR;
            target = (int64_t)addr + imm;
        }
        out->operands[0] = op_reg(bits(insn, 4, 0), true);
        out->operands[1] = op_addr(target);
        out->operand_count = 2;
        out->is_64bit = true;
        return;
    }
    case 2: case 3: {
        /* Add/subtract immediate */
        bool is_sub = bit(insn, 30);
        bool set_flags = bit(insn, 29);
        uint32_t imm12 = bits(insn, 21, 10);
        uint32_t sh = bit(insn, 22);
        int64_t imm_val = sh ? ((int64_t)imm12 << 12) : (int64_t)imm12;
        uint32_t rd = bits(insn, 4, 0);
        uint32_t rn = bits(insn, 9, 5);

        if (set_flags && rd == 31) {
            out->instruction = is_sub ? A64_INS_CMP : A64_INS_CMN;
            out->operands[0] = op_reg(rn, sf);
            out->operands[1] = op_imm(imm_val);
            out->operand_count = 2;
        } else {
            out->instruction = is_sub ? A64_INS_SUB : A64_INS_ADD;
            out->operands[0] = op_reg(rd, sf);
            out->operands[1] = op_reg(rn, sf);
            out->operands[2] = op_imm(imm_val);
            out->operand_count = 3;
        }
        out->sets_flags = set_flags;
        return;
    }
    case 4: {
        /* Logical immediate */
        uint32_t opc = bits(insn, 30, 29);
        uint32_t rd = bits(insn, 4, 0);
        uint32_t rn = bits(insn, 9, 5);
        /* Decode bitmask immediate (simplified: store raw immr:imms) */
        uint32_t immr = bits(insn, 21, 16);
        uint32_t imms = bits(insn, 15, 10);
        uint32_t N = bit(insn, 22);
        int64_t imm_val = (int64_t)((N << 12) | (immr << 6) | imms);

        bool sets = (opc == 3); /* ANDS */
        if (sets && rd == 31) {
            out->instruction = A64_INS_TST;
            out->operands[0] = op_reg(rn, sf);
            out->operands[1] = op_imm(imm_val);
            out->operand_count = 2;
        } else {
            static const a64_instruction_t logic_ops[] = {
                A64_INS_AND, A64_INS_ORR, A64_INS_EOR, A64_INS_AND
            };
            out->instruction = logic_ops[opc];
            out->operands[0] = op_reg(rd, sf);
            out->operands[1] = op_reg(rn, sf);
            out->operands[2] = op_imm(imm_val);
            out->operand_count = 3;
        }
        out->sets_flags = sets;
        return;
    }
    case 5: {
        /* Move wide immediate */
        uint32_t opc = bits(insn, 30, 29);
        uint32_t hw = bits(insn, 22, 21);
        uint32_t imm16 = bits(insn, 20, 5);
        uint32_t rd = bits(insn, 4, 0);

        static const a64_instruction_t movw_ops[] = {
            A64_INS_MOVN, A64_INS_UNKNOWN, A64_INS_MOVZ, A64_INS_MOVK
        };
        out->instruction = movw_ops[opc];
        out->operands[0] = op_reg(rd, sf);
        out->operands[1] = op_imm((int64_t)imm16);
        out->operands[1].shift = hw * 16;
        out->operand_count = 2;
        return;
    }
    case 6: {
        /* Bitfield */
        uint32_t opc = bits(insn, 30, 29);
        uint32_t rd = bits(insn, 4, 0);
        uint32_t rn = bits(insn, 9, 5);
        uint32_t immr = bits(insn, 21, 16);
        uint32_t imms = bits(insn, 15, 10);

        static const a64_instruction_t bfm_ops[] = {
            A64_INS_SBFM, A64_INS_BFM, A64_INS_UBFM, A64_INS_UNKNOWN
        };
        out->instruction = bfm_ops[opc];
        out->operands[0] = op_reg(rd, sf);
        out->operands[1] = op_reg(rn, sf);
        out->operands[2] = op_imm((int64_t)immr);
        out->operands[3] = op_imm((int64_t)imms);
        out->operand_count = 4;
        return;
    }
    case 7: {
        /* Extract */
        uint32_t rd = bits(insn, 4, 0);
        uint32_t rn = bits(insn, 9, 5);
        uint32_t rm = bits(insn, 20, 16);
        uint32_t imms = bits(insn, 15, 10);
        out->instruction = A64_INS_EXTR;
        out->operands[0] = op_reg(rd, sf);
        out->operands[1] = op_reg(rn, sf);
        out->operands[2] = op_reg(rm, sf);
        out->operands[3] = op_imm((int64_t)imms);
        out->operand_count = 4;
        return;
    }
    }
}

/* Branches, exception generation, and system instructions */
static void decode_branch_sys(uint32_t insn, uint64_t addr,
                               a64_decoded_t* out) {
    uint32_t op0 = bits(insn, 31, 29);
    uint32_t op1 = bits(insn, 25, 22);

    /* Unconditional branch immediate */
    if (bits(insn, 30, 26) == 0x05) {
        /* B / BL */
        bool is_link = bit(insn, 31);
        int64_t imm26 = sign_extend(bits(insn, 25, 0), 26);
        int64_t target = (int64_t)addr + (imm26 << 2);
        out->instruction = is_link ? A64_INS_BL : A64_INS_B;
        out->operands[0] = op_addr(target);
        out->operand_count = 1;
        out->is_64bit = true;
        return;
    }

    /* Compare and branch */
    if (bits(insn, 30, 25) == 0x1A) {
        bool is_nz = bit(insn, 24);
        bool sf = bit(insn, 31);
        int64_t imm19 = sign_extend(bits(insn, 23, 5), 19);
        int64_t target = (int64_t)addr + (imm19 << 2);
        uint32_t rt = bits(insn, 4, 0);
        out->instruction = is_nz ? A64_INS_CBNZ : A64_INS_CBZ;
        out->operands[0] = op_reg(rt, sf);
        out->operands[1] = op_addr(target);
        out->operand_count = 2;
        out->is_64bit = sf;
        return;
    }

    /* Test and branch */
    if (bits(insn, 30, 25) == 0x1B) {
        bool is_nz = bit(insn, 24);
        uint32_t b5 = bit(insn, 31);
        uint32_t b40 = bits(insn, 23, 19);
        uint32_t bit_num = (b5 << 5) | b40;
        int64_t imm14 = sign_extend(bits(insn, 18, 5), 14);
        int64_t target = (int64_t)addr + (imm14 << 2);
        uint32_t rt = bits(insn, 4, 0);
        out->instruction = is_nz ? A64_INS_TBNZ : A64_INS_TBZ;
        out->operands[0] = op_reg(rt, bit_num >= 32);
        out->operands[1] = op_imm(bit_num);
        out->operands[2] = op_addr(target);
        out->operand_count = 3;
        out->is_64bit = (bit_num >= 32);
        return;
    }

    /* Conditional branch */
    if (bits(insn, 31, 25) == 0x2A) {
        uint32_t cond = bits(insn, 3, 0);
        int64_t imm19 = sign_extend(bits(insn, 23, 5), 19);
        int64_t target = (int64_t)addr + (imm19 << 2);
        out->instruction = A64_INS_B_COND;
        out->cc = (a64_cc_t)cond;
        out->operands[0] = op_addr(target);
        out->operand_count = 1;
        out->is_64bit = true;
        return;
    }

    /* Unconditional branch register */
    if (bits(insn, 31, 25) == 0x6B) {
        uint32_t opc = bits(insn, 24, 21);
        uint32_t rn = bits(insn, 9, 5);
        switch (opc) {
        case 0: out->instruction = A64_INS_BR;  break;
        case 1: out->instruction = A64_INS_BLR; break;
        case 2: out->instruction = A64_INS_RET; break;
        default: out->instruction = A64_INS_UNKNOWN; return;
        }
        out->operands[0] = op_reg(rn, true);
        out->operand_count = 1;
        out->is_64bit = true;
        return;
    }

    /* Exception generation */
    if (bits(insn, 31, 24) == 0xD4) {
        uint32_t opc = bits(insn, 23, 21);
        uint32_t imm16 = bits(insn, 20, 5);
        switch (opc) {
        case 0: out->instruction = A64_INS_SVC; break;
        case 1: out->instruction = A64_INS_HVC; break;
        case 2: out->instruction = A64_INS_SMC; break;
        default: out->instruction = A64_INS_UNKNOWN; return;
        }
        out->operands[0] = op_imm(imm16);
        out->operand_count = 1;
        out->is_64bit = true;
        return;
    }

    /* System instructions: MSR/MRS, barriers, hints */
    if (bits(insn, 31, 22) == 0x354) {
        uint32_t l = bit(insn, 21);
        uint32_t rt = bits(insn, 4, 0);
        uint32_t op1_field = bits(insn, 18, 16);
        uint32_t crn = bits(insn, 15, 12);
        uint32_t crm = bits(insn, 11, 8);
        uint32_t op2_field = bits(insn, 7, 5);

        /* MSR/MRS: op0 is bits[20:19], must be >= 2 for system regs */
        uint32_t op0_field = bits(insn, 20, 19);

        if (op0_field >= 2) {
            /* MRS (L=1) or MSR (L=0) */
            if (l) {
                out->instruction = A64_INS_MRS;
                out->operands[0] = op_reg(rt, true);
                out->operands[1] = op_sysreg(insn);
                out->operand_count = 2;
            } else {
                out->instruction = A64_INS_MSR;
                out->operands[0] = op_sysreg(insn);
                out->operands[1] = op_reg(rt, true);
                out->operand_count = 2;
            }
            out->is_sysreg_access = true;
            out->is_64bit = true;
            return;
        }

        /* Hint instructions (CRn=2, op0=0, op1=0) */
        if (crn == 2 && op0_field == 0 && op1_field == 3) {
            /* CRm:op2 selects the hint type */
            uint32_t hint = (crm << 3) | op2_field;
            switch (hint) {
            case 0: out->instruction = A64_INS_NOP; break;
            case 1: out->instruction = A64_INS_WFE; break;
            case 2: out->instruction = A64_INS_WFI; break;
            case 4: out->instruction = A64_INS_SEV; break;
            default: out->instruction = A64_INS_NOP; break;
            }
            out->operand_count = 0;
            out->is_64bit = true;
            return;
        }

        /* Barrier instructions (CRn=3) */
        if (crn == 3 && op0_field == 0 && op1_field == 3) {
            switch (op2_field) {
            case 5: out->instruction = A64_INS_DMB; break;
            case 4: out->instruction = A64_INS_DSB; break;
            case 6: out->instruction = A64_INS_ISB; break;
            default: out->instruction = A64_INS_UNKNOWN; return;
            }
            out->operands[0] = op_imm(crm); /* barrier option */
            out->operand_count = 1;
            out->is_64bit = true;
            return;
        }
    }

    (void)op0;
    (void)op1;
    /* Unrecognized branch/sys encoding */
    out->instruction = A64_INS_UNKNOWN;
}

/* Loads and Stores */
static void decode_load_store(uint32_t insn, uint64_t addr,
                               a64_decoded_t* out) {
    (void)addr;
    uint32_t op0 = bits(insn, 31, 28);

    /* Load/store pair (LDP/STP) */
    if (bits(insn, 29, 27) == 5 && bit(insn, 25) == 0) {
        bool sf = bit(insn, 31);
        bool is_load = bit(insn, 22);
        uint32_t rt1 = bits(insn, 4, 0);
        uint32_t rt2 = bits(insn, 14, 10);
        uint32_t rn = bits(insn, 9, 5);
        int64_t imm7 = sign_extend(bits(insn, 21, 15), 7);
        int64_t offset = imm7 * (sf ? 8 : 4);

        out->instruction = is_load ? A64_INS_LDP : A64_INS_STP;
        out->operands[0] = op_reg(rt1, sf);
        out->operands[0].reg2 = rt2;
        out->operands[1] = op_mem(rn, offset, sf ? 8 : 4);
        out->operand_count = 2;
        out->is_64bit = sf;
        return;
    }

    /* Load register (literal) — PC-relative */
    if (bits(insn, 29, 27) == 3 && bit(insn, 26) == 0 && bit(insn, 25) == 0) {
        bool sf = bit(insn, 30);
        uint32_t rt = bits(insn, 4, 0);
        int64_t imm19 = sign_extend(bits(insn, 23, 5), 19);
        int64_t target = (int64_t)addr + (imm19 << 2);
        out->instruction = A64_INS_LDR_LITERAL;
        out->operands[0] = op_reg(rt, sf);
        out->operands[1] = op_addr(target);
        out->operand_count = 2;
        out->is_64bit = sf;
        return;
    }

    /* Load/store register (unsigned offset, register offset, pre/post-index) */
    uint32_t size_field = bits(insn, 31, 30);
    uint32_t opc = bits(insn, 23, 22);
    uint32_t rt = bits(insn, 4, 0);
    uint32_t rn = bits(insn, 9, 5);

    /* Determine access size and instruction from size_field + opc */
    uint8_t access_size;
    a64_instruction_t ins;
    switch (size_field) {
    case 0:
        access_size = 1;
        if (opc == 0)       { ins = A64_INS_STRB; }
        else if (opc == 1)  { ins = A64_INS_LDRB; }
        else                { ins = A64_INS_LDRSB; }
        break;
    case 1:
        access_size = 2;
        if (opc == 0)       { ins = A64_INS_STRH; }
        else if (opc == 1)  { ins = A64_INS_LDRH; }
        else if (opc == 2)  { ins = A64_INS_LDRSH; }
        else                { ins = A64_INS_LDRSH; }
        break;
    case 2:
        access_size = 4;
        if (opc == 0)       { ins = A64_INS_STR; }
        else if (opc == 1)  { ins = A64_INS_LDR; }
        else if (opc == 2)  { ins = A64_INS_LDRSW; }
        else                { ins = A64_INS_UNKNOWN; }
        break;
    case 3:
        access_size = 8;
        if (opc == 0)       { ins = A64_INS_STR; }
        else                { ins = A64_INS_LDR; }
        break;
    default:
        access_size = 4;
        ins = A64_INS_UNKNOWN;
        break;
    }

    out->instruction = ins;

    /* Unsigned immediate offset: bits [24] = 1, bits [21] = 0 (no reg offset) */
    if (bit(insn, 24)) {
        uint32_t imm12 = bits(insn, 21, 10);
        int64_t offset = (int64_t)imm12 * access_size;
        out->operands[0] = op_reg(rt, size_field == 3);
        out->operands[1] = op_mem(rn, offset, access_size);
        out->operand_count = 2;
        out->is_64bit = (size_field == 3);
    } else {
        /* Pre/post-indexed or register offset */
        int64_t imm9 = sign_extend(bits(insn, 20, 12), 9);
        out->operands[0] = op_reg(rt, size_field == 3);
        out->operands[1] = op_mem(rn, imm9, access_size);
        out->operand_count = 2;
        out->is_64bit = (size_field == 3);
    }
    (void)op0;
}

/* Data Processing — Register group */
static void decode_dp_reg(uint32_t insn, uint64_t addr,
                           a64_decoded_t* out) {
    (void)addr;
    bool sf = bit(insn, 31);
    out->is_64bit = sf;

    uint32_t op1 = bit(insn, 28);
    uint32_t op2 = bits(insn, 24, 21);

    /* Logical (shifted register): op1=0, bits[24]=0 */
    if (op1 == 0 && !bit(insn, 24)) {
        uint32_t opc = bits(insn, 30, 29);
        bool set_flags = (opc == 3); /* ANDS */
        uint32_t rd = bits(insn, 4, 0);
        uint32_t rn = bits(insn, 9, 5);
        uint32_t rm = bits(insn, 20, 16);
        bool N = bit(insn, 21);

        if (set_flags && rd == 31) {
            out->instruction = A64_INS_TST;
            out->operands[0] = op_reg(rn, sf);
            out->operands[1] = op_reg(rm, sf);
            out->operand_count = 2;
        } else if (opc == 1 && rn == 31 && !N) {
            /* ORR Rd, XZR, Rm → MOV */
            out->instruction = A64_INS_MOV;
            out->operands[0] = op_reg(rd, sf);
            out->operands[1] = op_reg(rm, sf);
            out->operand_count = 2;
        } else {
            static const a64_instruction_t log_ops[4][2] = {
                { A64_INS_AND, A64_INS_BIC },
                { A64_INS_ORR, A64_INS_ORN },
                { A64_INS_EOR, A64_INS_EOR },
                { A64_INS_AND, A64_INS_BIC }, /* ANDS/BICS */
            };
            out->instruction = log_ops[opc][N ? 1 : 0];
            out->operands[0] = op_reg(rd, sf);
            out->operands[1] = op_reg(rn, sf);
            out->operands[2] = op_reg(rm, sf);
            out->operand_count = 3;
        }
        out->sets_flags = set_flags;
        return;
    }

    /* Add/subtract (shifted register): op1=0, bit[24]=1 */
    if (op1 == 0 && bit(insn, 24)) {
        bool is_sub = bit(insn, 30);
        bool set_flags = bit(insn, 29);
        uint32_t rd = bits(insn, 4, 0);
        uint32_t rn = bits(insn, 9, 5);
        uint32_t rm = bits(insn, 20, 16);

        if (set_flags && rd == 31) {
            out->instruction = is_sub ? A64_INS_CMP : A64_INS_CMN;
            out->operands[0] = op_reg(rn, sf);
            out->operands[1] = op_reg(rm, sf);
            out->operand_count = 2;
        } else if (is_sub && rn == 31) {
            out->instruction = A64_INS_NEG;
            out->operands[0] = op_reg(rd, sf);
            out->operands[1] = op_reg(rm, sf);
            out->operand_count = 2;
        } else {
            out->instruction = is_sub ? A64_INS_SUB : A64_INS_ADD;
            out->operands[0] = op_reg(rd, sf);
            out->operands[1] = op_reg(rn, sf);
            out->operands[2] = op_reg(rm, sf);
            out->operand_count = 3;
        }
        out->sets_flags = set_flags;
        return;
    }

    /* Add/subtract with carry: op1=1, bits[24:21]=0000 */
    if (op1 == 1 && op2 == 0) {
        bool is_sub = bit(insn, 30);
        bool set_flags = bit(insn, 29);
        uint32_t rd = bits(insn, 4, 0);
        uint32_t rn = bits(insn, 9, 5);
        uint32_t rm = bits(insn, 20, 16);
        out->instruction = is_sub ? A64_INS_SBC : A64_INS_ADC;
        out->operands[0] = op_reg(rd, sf);
        out->operands[1] = op_reg(rn, sf);
        out->operands[2] = op_reg(rm, sf);
        out->operand_count = 3;
        out->sets_flags = set_flags;
        return;
    }

    /* Conditional select: op1=1, bits[24:21]=0100 */
    if (op1 == 1 && (op2 & 0xE) == 4) {
        uint32_t op_sel = bit(insn, 30);
        uint32_t op2_sel = bit(insn, 10);
        uint32_t rd = bits(insn, 4, 0);
        uint32_t rn = bits(insn, 9, 5);
        uint32_t rm = bits(insn, 20, 16);
        uint32_t cond = bits(insn, 15, 12);

        static const a64_instruction_t csel_ops[4] = {
            A64_INS_CSEL, A64_INS_CSINC, A64_INS_CSINV, A64_INS_CSNEG
        };
        out->instruction = csel_ops[(op_sel << 1) | op2_sel];
        out->cc = (a64_cc_t)cond;
        out->operands[0] = op_reg(rd, sf);
        out->operands[1] = op_reg(rn, sf);
        out->operands[2] = op_reg(rm, sf);
        out->operand_count = 3;
        return;
    }

    /* Data processing (2 source): op1=1, bits[24:21]=0110 */
    if (op1 == 1 && op2 == 6) {
        uint32_t opcode = bits(insn, 15, 10);
        uint32_t rd = bits(insn, 4, 0);
        uint32_t rn = bits(insn, 9, 5);
        uint32_t rm = bits(insn, 20, 16);
        switch (opcode) {
        case 2: out->instruction = A64_INS_UDIV; break;
        case 3: out->instruction = A64_INS_SDIV; break;
        case 8: out->instruction = A64_INS_LSL;  break;
        case 9: out->instruction = A64_INS_LSR;  break;
        case 10: out->instruction = A64_INS_ASR; break;
        case 11: out->instruction = A64_INS_ROR; break;
        default: out->instruction = A64_INS_UNKNOWN; return;
        }
        out->operands[0] = op_reg(rd, sf);
        out->operands[1] = op_reg(rn, sf);
        out->operands[2] = op_reg(rm, sf);
        out->operand_count = 3;
        return;
    }

    /* Data processing (3 source): op1=1, bit[24]=1 */
    if (op1 == 1 && bit(insn, 24)) {
        uint32_t op31 = bits(insn, 23, 21);
        uint32_t o0 = bit(insn, 15);
        uint32_t rd = bits(insn, 4, 0);
        uint32_t rn = bits(insn, 9, 5);
        uint32_t rm = bits(insn, 20, 16);
        uint32_t ra = bits(insn, 14, 10);

        if (op31 == 0 && o0 == 0) {
            if (ra == 31) {
                out->instruction = A64_INS_MUL;
                out->operands[0] = op_reg(rd, sf);
                out->operands[1] = op_reg(rn, sf);
                out->operands[2] = op_reg(rm, sf);
                out->operand_count = 3;
            } else {
                out->instruction = A64_INS_MADD;
                out->operands[0] = op_reg(rd, sf);
                out->operands[1] = op_reg(rn, sf);
                out->operands[2] = op_reg(rm, sf);
                out->operands[3] = op_reg(ra, sf);
                out->operand_count = 4;
            }
        } else if (op31 == 0 && o0 == 1) {
            out->instruction = A64_INS_MSUB;
            out->operands[0] = op_reg(rd, sf);
            out->operands[1] = op_reg(rn, sf);
            out->operands[2] = op_reg(rm, sf);
            out->operands[3] = op_reg(ra, sf);
            out->operand_count = 4;
        } else {
            out->instruction = A64_INS_UNKNOWN;
        }
        return;
    }

    out->instruction = A64_INS_UNKNOWN;
}

/* ---- Main decode function ---- */

int a64_decode_one(a64_decoder_t* dec, a64_decoded_t* out) {
    memset(out, 0, sizeof(*out));

    if (dec->offset + 4 > dec->code_size) return 0;

    const uint8_t* p = dec->code + dec->offset;
    uint32_t insn = (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
                    ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);

    out->address = dec->base_address + dec->offset;
    out->raw = insn;

    /* Top-level dispatch on bits [28:25] */
    uint32_t op0 = bits(insn, 28, 25);

    switch (op0) {
    case 0x0:
        /* Reserved / UNALLOCATED */
        out->instruction = A64_INS_UNKNOWN;
        break;

    case 0x8: case 0x9:
        /* Data Processing — Immediate */
        decode_dp_imm(insn, out->address, out);
        break;

    case 0xA: case 0xB:
        /* Branches, Exception, System */
        decode_branch_sys(insn, out->address, out);
        break;

    case 0x4: case 0x6: case 0xC: case 0xE:
        /* Loads and Stores */
        decode_load_store(insn, out->address, out);
        break;

    case 0x5: case 0xD:
        /* Data Processing — Register */
        decode_dp_reg(insn, out->address, out);
        break;

    case 0x7: case 0xF:
        /* Data Processing — SIMD & FP (not needed for driver extraction) */
        out->instruction = A64_INS_UNKNOWN;
        break;

    default:
        out->instruction = A64_INS_UNKNOWN;
        break;
    }

    dec->offset += 4;
    return 4;
}

/* ---- Decode range ---- */

a64_decoded_t* a64_decode_range(a64_decoder_t* dec, size_t* count_out) {
    size_t capacity = 64;
    size_t count = 0;
    a64_decoded_t* arr = malloc(capacity * sizeof(a64_decoded_t));
    if (!arr) { *count_out = 0; return NULL; }

    a64_decoded_t d;
    while (a64_decode_one(dec, &d) > 0) {
        if (count >= capacity) {
            capacity *= 2;
            a64_decoded_t* tmp = realloc(arr, capacity * sizeof(a64_decoded_t));
            if (!tmp) break;
            arr = tmp;
        }
        arr[count++] = d;
    }

    *count_out = count;
    return arr;
}

/* ---- Print ---- */

void a64_print_decoded(const a64_decoded_t* inst, FILE* out) {
    fprintf(out, "  %08lx:  %08x  ", (unsigned long)inst->address, inst->raw);

    if (inst->instruction == A64_INS_B_COND) {
        fprintf(out, "b.%s", a64_cc_name(inst->cc));
    } else {
        fprintf(out, "%s", a64_ins_name(inst->instruction));
    }
    if (inst->sets_flags && inst->instruction != A64_INS_CMP &&
        inst->instruction != A64_INS_CMN && inst->instruction != A64_INS_TST) {
        fprintf(out, "s");
    }

    for (int i = 0; i < inst->operand_count; i++) {
        fprintf(out, "%s", i == 0 ? " " : ", ");
        const a64_operand_t* op = &inst->operands[i];
        switch (op->type) {
        case A64_OP_REG:
            fprintf(out, "%s", a64_reg_name(op->reg, inst->is_64bit));
            break;
        case A64_OP_IMM:
            fprintf(out, "#%ld", (long)op->imm);
            if (op->shift) fprintf(out, ", lsl #%u", op->shift);
            break;
        case A64_OP_MEM:
            fprintf(out, "[%s", a64_reg_name(op->reg, true));
            if (op->imm) fprintf(out, ", #%ld", (long)op->imm);
            fprintf(out, "]");
            break;
        case A64_OP_ADDR:
            fprintf(out, "0x%lx", (unsigned long)op->imm);
            break;
        case A64_OP_SYSREG:
            fprintf(out, "s%u_%u_c%u_c%u_%u",
                    op->sysreg.op0, op->sysreg.op1,
                    op->sysreg.crn, op->sysreg.crm, op->sysreg.op2);
            break;
        case A64_OP_NONE:
            break;
        }
    }
    fprintf(out, "\n");
}
