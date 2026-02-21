/* ============================================================================
 * x86 Instruction Decoder
 * ============================================================================
 *
 * Table-driven decoder for x86-32 instructions. Handles one-byte and
 * two-byte (0x0F) opcodes, ModR/M byte, SIB byte, and displacements.
 *
 * Focus: instructions commonly found in Windows kernel drivers, especially
 * IN/OUT for port I/O.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "x86_decoder.h"

/* ---- Internal helpers ---- */

static inline uint8_t peek(const x86_decoder_t* dec) {
    return dec->code[dec->offset];
}

static inline uint8_t eat(x86_decoder_t* dec) {
    return dec->code[dec->offset++];
}

static inline bool has_bytes(const x86_decoder_t* dec, size_t n) {
    return dec->offset + n <= dec->code_size;
}

static inline int8_t read_i8(x86_decoder_t* dec) {
    return (int8_t)eat(dec);
}

static inline uint16_t read_u16(x86_decoder_t* dec) {
    uint16_t v = dec->code[dec->offset] | ((uint16_t)dec->code[dec->offset+1] << 8);
    dec->offset += 2;
    return v;
}

static inline int32_t read_i32(x86_decoder_t* dec) {
    int32_t v = (int32_t)(
        (uint32_t)dec->code[dec->offset] |
        ((uint32_t)dec->code[dec->offset+1] << 8) |
        ((uint32_t)dec->code[dec->offset+2] << 16) |
        ((uint32_t)dec->code[dec->offset+3] << 24));
    dec->offset += 4;
    return v;
}

static inline uint32_t read_u32(x86_decoder_t* dec) {
    return (uint32_t)read_i32(dec);
}

/* ---- ModR/M + SIB decoding ---- */

/*
 * ModR/M byte: [mod(2)][reg(3)][rm(3)]
 * mod=00: [rm], no disp (except rm=101: disp32, rm=100: SIB)
 * mod=01: [rm + disp8]
 * mod=10: [rm + disp32]
 * mod=11: register direct
 *
 * SIB byte: [scale(2)][index(3)][base(3)]
 */

static void decode_modrm(x86_decoder_t* dec, x86_operand_t* rm_op,
                         int* reg_out, uint8_t op_size) {
    uint8_t modrm = eat(dec);
    int mod = (modrm >> 6) & 3;
    int reg = (modrm >> 3) & 7;
    int rm  = modrm & 7;

    if (reg_out) *reg_out = reg;

    if (mod == 3) {
        /* Register direct */
        rm_op->type = X86_OP_REG;
        rm_op->reg = rm;
        rm_op->size = op_size;
        return;
    }

    /* Memory operand */
    rm_op->type = X86_OP_MEM;
    rm_op->size = op_size;
    rm_op->base = -1;
    rm_op->index = -1;
    rm_op->scale = 1;
    rm_op->disp = 0;

    if (rm == 4) {
        /* SIB follows */
        uint8_t sib = eat(dec);
        int scale = (sib >> 6) & 3;
        int index = (sib >> 3) & 7;
        int base  = sib & 7;

        rm_op->scale = 1 << scale;

        if (index != 4) {  /* index=4 means no index */
            rm_op->index = index;
        }

        if (base == 5 && mod == 0) {
            /* disp32 only, no base */
            rm_op->disp = read_i32(dec);
        } else {
            rm_op->base = base;
        }
    } else if (rm == 5 && mod == 0) {
        /* disp32 only, no base register */
        rm_op->disp = read_i32(dec);
    } else {
        rm_op->base = rm;
    }

    /* Read displacement */
    if (mod == 1) {
        rm_op->disp = read_i8(dec);
    } else if (mod == 2) {
        rm_op->disp = read_i32(dec);
    }
}

/* ---- Opcode handlers ---- */

/* Group 1 ALU: 0x80-0x83 */
static const x86_instruction_t group1_ops[8] = {
    X86_INS_ADD, X86_INS_OR, X86_INS_ADC, X86_INS_SBB,
    X86_INS_AND, X86_INS_SUB, X86_INS_XOR, X86_INS_CMP,
};

/* Group 3: 0xF6-0xF7 */
static const x86_instruction_t group3_ops[8] = {
    X86_INS_TEST, X86_INS_TEST, X86_INS_NOT, X86_INS_NEG,
    X86_INS_MUL, X86_INS_IMUL, X86_INS_DIV, X86_INS_IDIV,
};

/* Group 5: 0xFF */
static const x86_instruction_t group5_ops[8] = {
    X86_INS_INC, X86_INS_DEC, X86_INS_CALL, X86_INS_CALL,
    X86_INS_JMP, X86_INS_JMP, X86_INS_PUSH, X86_INS_UNKNOWN,
};

/* Shift group: 0xC0, 0xC1, 0xD0-0xD3 */
static const x86_instruction_t shift_ops[8] = {
    X86_INS_ROL, X86_INS_ROR, X86_INS_UNKNOWN, X86_INS_UNKNOWN,
    X86_INS_SHL, X86_INS_SHR, X86_INS_UNKNOWN, X86_INS_SAR,
};

/* ---- Main decode function ---- */

int x86_decode_one(x86_decoder_t* dec, x86_decoded_t* out) {
    if (dec->offset >= dec->code_size) return 0;

    memset(out, 0, sizeof(*out));
    out->address = dec->base_address + dec->offset;
    size_t start = dec->offset;

    /* Parse prefixes */
    bool have_prefix = true;
    while (have_prefix && has_bytes(dec, 1)) {
        uint8_t b = peek(dec);
        switch (b) {
            case 0xF3: out->prefixes |= X86_PREFIX_REP; eat(dec); break;
            case 0xF2: out->prefixes |= X86_PREFIX_REPNE; eat(dec); break;
            case 0xF0: out->prefixes |= X86_PREFIX_LOCK; eat(dec); break;
            case 0x66: out->prefixes |= X86_PREFIX_OPSIZE; eat(dec); break;
            case 0x67: out->prefixes |= X86_PREFIX_ADDRSIZE; eat(dec); break;
            /* Segment overrides - consume but ignore */
            case 0x26: case 0x2E: case 0x36: case 0x3E:
            case 0x64: case 0x65:
                eat(dec);
                break;
            default:
                have_prefix = false;
                break;
        }
    }

    if (!has_bytes(dec, 1)) return 0;

    uint8_t opcode = eat(dec);
    int reg;
    uint8_t op_size = (out->prefixes & X86_PREFIX_OPSIZE) ? 2 : 4;

    switch (opcode) {

    /* ---- NOP ---- */
    case 0x90:
        out->instruction = X86_INS_NOP;
        break;

    /* ---- PUSH reg ---- */
    case 0x50: case 0x51: case 0x52: case 0x53:
    case 0x54: case 0x55: case 0x56: case 0x57:
        out->instruction = X86_INS_PUSH;
        out->operand_count = 1;
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = opcode - 0x50;
        out->operands[0].size = 4;
        break;

    /* ---- POP reg ---- */
    case 0x58: case 0x59: case 0x5A: case 0x5B:
    case 0x5C: case 0x5D: case 0x5E: case 0x5F:
        out->instruction = X86_INS_POP;
        out->operand_count = 1;
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = opcode - 0x58;
        out->operands[0].size = 4;
        break;

    /* ---- PUSHAD / POPAD ---- */
    case 0x60: out->instruction = X86_INS_PUSHAD; break;
    case 0x61: out->instruction = X86_INS_POPAD; break;

    /* ---- PUSH imm8 ---- */
    case 0x6A:
        out->instruction = X86_INS_PUSH;
        out->operand_count = 1;
        out->operands[0].type = X86_OP_IMM;
        out->operands[0].imm = read_i8(dec);
        out->operands[0].size = 4;
        break;

    /* ---- PUSH imm32 ---- */
    case 0x68:
        out->instruction = X86_INS_PUSH;
        out->operand_count = 1;
        out->operands[0].type = X86_OP_IMM;
        out->operands[0].imm = read_i32(dec);
        out->operands[0].size = 4;
        break;

    /* ---- Jcc short ---- */
    case 0x70: case 0x71: case 0x72: case 0x73:
    case 0x74: case 0x75: case 0x76: case 0x77:
    case 0x78: case 0x79: case 0x7A: case 0x7B:
    case 0x7C: case 0x7D: case 0x7E: case 0x7F: {
        out->instruction = X86_INS_JCC;
        out->cc = opcode - 0x70;
        int8_t rel = read_i8(dec);
        out->operand_count = 1;
        out->operands[0].type = X86_OP_REL;
        out->operands[0].imm = (int64_t)(dec->base_address + dec->offset) + rel;
        break;
    }

    /* ---- Group 1: ALU r/m, imm ---- */
    case 0x80: { /* r/m8, imm8 */
        decode_modrm(dec, &out->operands[0], &reg, 1);
        out->instruction = group1_ops[reg];
        out->operand_count = 2;
        out->operands[1].type = X86_OP_IMM;
        out->operands[1].imm = (uint8_t)eat(dec);
        out->operands[1].size = 1;
        break;
    }
    case 0x81: { /* r/m32, imm32 */
        decode_modrm(dec, &out->operands[0], &reg, op_size);
        out->instruction = group1_ops[reg];
        out->operand_count = 2;
        out->operands[1].type = X86_OP_IMM;
        out->operands[1].imm = (op_size == 2) ? (int16_t)read_u16(dec) : read_i32(dec);
        out->operands[1].size = op_size;
        break;
    }
    case 0x83: { /* r/m32, imm8 (sign-extended) */
        decode_modrm(dec, &out->operands[0], &reg, op_size);
        out->instruction = group1_ops[reg];
        out->operand_count = 2;
        out->operands[1].type = X86_OP_IMM;
        out->operands[1].imm = read_i8(dec);
        out->operands[1].size = op_size;
        break;
    }

    /* ---- ALU r/m, r and r, r/m ---- */
    /* ADD */
    case 0x00: case 0x01: case 0x02: case 0x03:
    /* OR */
    case 0x08: case 0x09: case 0x0A: case 0x0B:
    /* ADC */
    case 0x10: case 0x11: case 0x12: case 0x13:
    /* SBB */
    case 0x18: case 0x19: case 0x1A: case 0x1B:
    /* AND */
    case 0x20: case 0x21: case 0x22: case 0x23:
    /* SUB */
    case 0x28: case 0x29: case 0x2A: case 0x2B:
    /* XOR */
    case 0x30: case 0x31: case 0x32: case 0x33:
    /* CMP */
    case 0x38: case 0x39: case 0x3A: case 0x3B: {
        static const x86_instruction_t alu_map[] = {
            X86_INS_ADD, X86_INS_OR, X86_INS_ADC, X86_INS_SBB,
            X86_INS_AND, X86_INS_SUB, X86_INS_XOR, X86_INS_CMP,
        };
        int alu_idx = (opcode >> 3) & 7;
        int direction = (opcode >> 1) & 1;  /* 0=r/m,r  1=r,r/m */
        int is_byte = !(opcode & 1);
        uint8_t sz = is_byte ? 1 : op_size;

        out->instruction = alu_map[alu_idx];
        out->operand_count = 2;

        if (direction == 0) {
            /* r/m ← r/m OP reg */
            decode_modrm(dec, &out->operands[0], &reg, sz);
            out->operands[1].type = X86_OP_REG;
            out->operands[1].reg = reg;
            out->operands[1].size = sz;
        } else {
            /* reg ← reg OP r/m */
            decode_modrm(dec, &out->operands[1], &reg, sz);
            out->operands[0].type = X86_OP_REG;
            out->operands[0].reg = reg;
            out->operands[0].size = sz;
        }
        break;
    }

    /* ---- ADD/OR/ADC/SBB/AND/SUB/XOR/CMP AL/EAX, imm ---- */
    case 0x04: /* ADD AL, imm8 */
    case 0x0C: /* OR AL, imm8 */
    case 0x14: /* ADC AL, imm8 */
    case 0x1C: /* SBB AL, imm8 */
    case 0x24: /* AND AL, imm8 */
    case 0x2C: /* SUB AL, imm8 */
    case 0x34: /* XOR AL, imm8 */
    case 0x3C: { /* CMP AL, imm8 */
        static const x86_instruction_t alu_map[] = {
            X86_INS_ADD, X86_INS_OR, X86_INS_ADC, X86_INS_SBB,
            X86_INS_AND, X86_INS_SUB, X86_INS_XOR, X86_INS_CMP,
        };
        out->instruction = alu_map[(opcode >> 3) & 7];
        out->operand_count = 2;
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = X86_REG_EAX;
        out->operands[0].size = 1;
        out->operands[1].type = X86_OP_IMM;
        out->operands[1].imm = (uint8_t)eat(dec);
        out->operands[1].size = 1;
        break;
    }
    case 0x05: /* ADD EAX, imm32 */
    case 0x0D: /* OR EAX, imm32 */
    case 0x15: /* ADC EAX, imm32 */
    case 0x1D: /* SBB EAX, imm32 */
    case 0x25: /* AND EAX, imm32 */
    case 0x2D: /* SUB EAX, imm32 */
    case 0x35: /* XOR EAX, imm32 */
    case 0x3D: { /* CMP EAX, imm32 */
        static const x86_instruction_t alu_map[] = {
            X86_INS_ADD, X86_INS_OR, X86_INS_ADC, X86_INS_SBB,
            X86_INS_AND, X86_INS_SUB, X86_INS_XOR, X86_INS_CMP,
        };
        out->instruction = alu_map[(opcode >> 3) & 7];
        out->operand_count = 2;
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = X86_REG_EAX;
        out->operands[0].size = op_size;
        out->operands[1].type = X86_OP_IMM;
        out->operands[1].imm = (op_size == 2) ? (int16_t)read_u16(dec) : read_i32(dec);
        out->operands[1].size = op_size;
        break;
    }

    /* ---- INC/DEC reg (one-byte encodings) ---- */
    case 0x40: case 0x41: case 0x42: case 0x43:
    case 0x44: case 0x45: case 0x46: case 0x47:
        out->instruction = X86_INS_INC;
        out->operand_count = 1;
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = opcode - 0x40;
        out->operands[0].size = op_size;
        break;
    case 0x48: case 0x49: case 0x4A: case 0x4B:
    case 0x4C: case 0x4D: case 0x4E: case 0x4F:
        out->instruction = X86_INS_DEC;
        out->operand_count = 1;
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = opcode - 0x48;
        out->operands[0].size = op_size;
        break;

    /* ---- TEST ---- */
    case 0x84: { /* TEST r/m8, r8 */
        out->instruction = X86_INS_TEST;
        out->operand_count = 2;
        decode_modrm(dec, &out->operands[0], &reg, 1);
        out->operands[1].type = X86_OP_REG;
        out->operands[1].reg = reg;
        out->operands[1].size = 1;
        break;
    }
    case 0x85: { /* TEST r/m32, r32 */
        out->instruction = X86_INS_TEST;
        out->operand_count = 2;
        decode_modrm(dec, &out->operands[0], &reg, op_size);
        out->operands[1].type = X86_OP_REG;
        out->operands[1].reg = reg;
        out->operands[1].size = op_size;
        break;
    }

    /* ---- XCHG ---- */
    case 0x86: case 0x87: {
        uint8_t sz = (opcode & 1) ? op_size : 1;
        out->instruction = X86_INS_XCHG;
        out->operand_count = 2;
        decode_modrm(dec, &out->operands[0], &reg, sz);
        out->operands[1].type = X86_OP_REG;
        out->operands[1].reg = reg;
        out->operands[1].size = sz;
        break;
    }

    /* ---- MOV r/m, r and MOV r, r/m ---- */
    case 0x88: { /* MOV r/m8, r8 */
        out->instruction = X86_INS_MOV;
        out->operand_count = 2;
        decode_modrm(dec, &out->operands[0], &reg, 1);
        out->operands[1].type = X86_OP_REG;
        out->operands[1].reg = reg;
        out->operands[1].size = 1;
        break;
    }
    case 0x89: { /* MOV r/m32, r32 */
        out->instruction = X86_INS_MOV;
        out->operand_count = 2;
        decode_modrm(dec, &out->operands[0], &reg, op_size);
        out->operands[1].type = X86_OP_REG;
        out->operands[1].reg = reg;
        out->operands[1].size = op_size;
        break;
    }
    case 0x8A: { /* MOV r8, r/m8 */
        out->instruction = X86_INS_MOV;
        out->operand_count = 2;
        decode_modrm(dec, &out->operands[1], &reg, 1);
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = reg;
        out->operands[0].size = 1;
        break;
    }
    case 0x8B: { /* MOV r32, r/m32 */
        out->instruction = X86_INS_MOV;
        out->operand_count = 2;
        decode_modrm(dec, &out->operands[1], &reg, op_size);
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = reg;
        out->operands[0].size = op_size;
        break;
    }

    /* ---- LEA ---- */
    case 0x8D: {
        out->instruction = X86_INS_LEA;
        out->operand_count = 2;
        decode_modrm(dec, &out->operands[1], &reg, op_size);
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = reg;
        out->operands[0].size = op_size;
        break;
    }

    /* ---- MOV moffs ---- */
    case 0xA0: /* MOV AL, moffs8 */
        out->instruction = X86_INS_MOV;
        out->operand_count = 2;
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = X86_REG_EAX;
        out->operands[0].size = 1;
        out->operands[1].type = X86_OP_MEM;
        out->operands[1].size = 1;
        out->operands[1].base = -1;
        out->operands[1].index = -1;
        out->operands[1].disp = read_i32(dec);
        break;
    case 0xA1: /* MOV EAX, moffs32 */
        out->instruction = X86_INS_MOV;
        out->operand_count = 2;
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = X86_REG_EAX;
        out->operands[0].size = op_size;
        out->operands[1].type = X86_OP_MEM;
        out->operands[1].size = op_size;
        out->operands[1].base = -1;
        out->operands[1].index = -1;
        out->operands[1].disp = read_i32(dec);
        break;
    case 0xA2: /* MOV moffs8, AL */
        out->instruction = X86_INS_MOV;
        out->operand_count = 2;
        out->operands[0].type = X86_OP_MEM;
        out->operands[0].size = 1;
        out->operands[0].base = -1;
        out->operands[0].index = -1;
        out->operands[0].disp = read_i32(dec);
        out->operands[1].type = X86_OP_REG;
        out->operands[1].reg = X86_REG_EAX;
        out->operands[1].size = 1;
        break;
    case 0xA3: /* MOV moffs32, EAX */
        out->instruction = X86_INS_MOV;
        out->operand_count = 2;
        out->operands[0].type = X86_OP_MEM;
        out->operands[0].size = op_size;
        out->operands[0].base = -1;
        out->operands[0].index = -1;
        out->operands[0].disp = read_i32(dec);
        out->operands[1].type = X86_OP_REG;
        out->operands[1].reg = X86_REG_EAX;
        out->operands[1].size = op_size;
        break;

    /* ---- TEST AL/EAX, imm ---- */
    case 0xA8:
        out->instruction = X86_INS_TEST;
        out->operand_count = 2;
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = X86_REG_EAX;
        out->operands[0].size = 1;
        out->operands[1].type = X86_OP_IMM;
        out->operands[1].imm = (uint8_t)eat(dec);
        out->operands[1].size = 1;
        break;
    case 0xA9:
        out->instruction = X86_INS_TEST;
        out->operand_count = 2;
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = X86_REG_EAX;
        out->operands[0].size = op_size;
        out->operands[1].type = X86_OP_IMM;
        out->operands[1].imm = read_i32(dec);
        out->operands[1].size = op_size;
        break;

    /* ---- MOV reg, imm ---- */
    case 0xB0: case 0xB1: case 0xB2: case 0xB3:
    case 0xB4: case 0xB5: case 0xB6: case 0xB7:
        out->instruction = X86_INS_MOV;
        out->operand_count = 2;
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = opcode - 0xB0;
        out->operands[0].size = 1;
        out->operands[1].type = X86_OP_IMM;
        out->operands[1].imm = (uint8_t)eat(dec);
        out->operands[1].size = 1;
        break;
    case 0xB8: case 0xB9: case 0xBA: case 0xBB:
    case 0xBC: case 0xBD: case 0xBE: case 0xBF:
        out->instruction = X86_INS_MOV;
        out->operand_count = 2;
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = opcode - 0xB8;
        out->operands[0].size = op_size;
        out->operands[1].type = X86_OP_IMM;
        if (op_size == 2)
            out->operands[1].imm = read_u16(dec);
        else
            out->operands[1].imm = read_u32(dec);
        out->operands[1].size = op_size;
        break;

    /* ---- Shift group: C0, C1 ---- */
    case 0xC0: { /* shift r/m8, imm8 */
        decode_modrm(dec, &out->operands[0], &reg, 1);
        out->instruction = shift_ops[reg];
        if (out->instruction == X86_INS_UNKNOWN) out->instruction = X86_INS_SHL;
        out->operand_count = 2;
        out->operands[1].type = X86_OP_IMM;
        out->operands[1].imm = (uint8_t)eat(dec);
        out->operands[1].size = 1;
        break;
    }
    case 0xC1: { /* shift r/m32, imm8 */
        decode_modrm(dec, &out->operands[0], &reg, op_size);
        out->instruction = shift_ops[reg];
        if (out->instruction == X86_INS_UNKNOWN) out->instruction = X86_INS_SHL;
        out->operand_count = 2;
        out->operands[1].type = X86_OP_IMM;
        out->operands[1].imm = (uint8_t)eat(dec);
        out->operands[1].size = 1;
        break;
    }

    /* ---- RET ---- */
    case 0xC3:
        out->instruction = X86_INS_RET;
        break;

    /* ---- RET imm16 ---- */
    case 0xC2:
        out->instruction = X86_INS_RET;
        out->operand_count = 1;
        out->operands[0].type = X86_OP_IMM;
        out->operands[0].imm = read_u16(dec);
        out->operands[0].size = 2;
        break;

    /* ---- MOV r/m, imm ---- */
    case 0xC6: { /* MOV r/m8, imm8 */
        decode_modrm(dec, &out->operands[0], &reg, 1);
        out->instruction = X86_INS_MOV;
        out->operand_count = 2;
        out->operands[1].type = X86_OP_IMM;
        out->operands[1].imm = (uint8_t)eat(dec);
        out->operands[1].size = 1;
        break;
    }
    case 0xC7: { /* MOV r/m32, imm32 */
        decode_modrm(dec, &out->operands[0], &reg, op_size);
        out->instruction = X86_INS_MOV;
        out->operand_count = 2;
        out->operands[1].type = X86_OP_IMM;
        out->operands[1].imm = (op_size == 2) ? (int16_t)read_u16(dec) : read_i32(dec);
        out->operands[1].size = op_size;
        break;
    }

    /* ---- LEAVE ---- */
    case 0xC9:
        out->instruction = X86_INS_LEAVE;
        break;

    /* ---- INT imm8 ---- */
    case 0xCD:
        out->instruction = X86_INS_INT;
        out->operand_count = 1;
        out->operands[0].type = X86_OP_IMM;
        out->operands[0].imm = (uint8_t)eat(dec);
        out->operands[0].size = 1;
        break;

    /* ---- Shift group: D0-D3 (shift by 1 or CL) ---- */
    case 0xD0: case 0xD2: { /* r/m8 by 1 or CL */
        decode_modrm(dec, &out->operands[0], &reg, 1);
        out->instruction = shift_ops[reg];
        if (out->instruction == X86_INS_UNKNOWN) out->instruction = X86_INS_SHL;
        out->operand_count = 2;
        if (opcode == 0xD0) {
            out->operands[1].type = X86_OP_IMM;
            out->operands[1].imm = 1;
        } else {
            out->operands[1].type = X86_OP_REG;
            out->operands[1].reg = X86_REG_ECX;
        }
        out->operands[1].size = 1;
        break;
    }
    case 0xD1: case 0xD3: { /* r/m32 by 1 or CL */
        decode_modrm(dec, &out->operands[0], &reg, op_size);
        out->instruction = shift_ops[reg];
        if (out->instruction == X86_INS_UNKNOWN) out->instruction = X86_INS_SHL;
        out->operand_count = 2;
        if (opcode == 0xD1) {
            out->operands[1].type = X86_OP_IMM;
            out->operands[1].imm = 1;
        } else {
            out->operands[1].type = X86_OP_REG;
            out->operands[1].reg = X86_REG_ECX;
        }
        out->operands[1].size = 1;
        break;
    }

    /* ---- I/O instructions ---- */
    case 0xE4: /* IN AL, imm8 */
        out->instruction = X86_INS_IN;
        out->operand_count = 2;
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = X86_REG_EAX;
        out->operands[0].size = 1;
        out->operands[1].type = X86_OP_IMM;
        out->operands[1].imm = (uint8_t)eat(dec);
        out->operands[1].size = 1;
        break;
    case 0xE5: /* IN EAX, imm8 */
        out->instruction = X86_INS_IN;
        out->operand_count = 2;
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = X86_REG_EAX;
        out->operands[0].size = op_size;
        out->operands[1].type = X86_OP_IMM;
        out->operands[1].imm = (uint8_t)eat(dec);
        out->operands[1].size = 1;
        break;
    case 0xE6: /* OUT imm8, AL */
        out->instruction = X86_INS_OUT;
        out->operand_count = 2;
        out->operands[0].type = X86_OP_IMM;
        out->operands[0].imm = (uint8_t)eat(dec);
        out->operands[0].size = 1;
        out->operands[1].type = X86_OP_REG;
        out->operands[1].reg = X86_REG_EAX;
        out->operands[1].size = 1;
        break;
    case 0xE7: /* OUT imm8, EAX */
        out->instruction = X86_INS_OUT;
        out->operand_count = 2;
        out->operands[0].type = X86_OP_IMM;
        out->operands[0].imm = (uint8_t)eat(dec);
        out->operands[0].size = 1;
        out->operands[1].type = X86_OP_REG;
        out->operands[1].reg = X86_REG_EAX;
        out->operands[1].size = op_size;
        break;

    /* ---- CALL rel32 ---- */
    case 0xE8: {
        out->instruction = X86_INS_CALL;
        int32_t rel = read_i32(dec);
        out->operand_count = 1;
        out->operands[0].type = X86_OP_REL;
        out->operands[0].imm = (int64_t)(dec->base_address + dec->offset) + rel;
        break;
    }

    /* ---- JMP rel32 ---- */
    case 0xE9: {
        out->instruction = X86_INS_JMP;
        int32_t rel = read_i32(dec);
        out->operand_count = 1;
        out->operands[0].type = X86_OP_REL;
        out->operands[0].imm = (int64_t)(dec->base_address + dec->offset) + rel;
        break;
    }

    /* ---- JMP short ---- */
    case 0xEB: {
        out->instruction = X86_INS_JMP;
        int8_t rel = read_i8(dec);
        out->operand_count = 1;
        out->operands[0].type = X86_OP_REL;
        out->operands[0].imm = (int64_t)(dec->base_address + dec->offset) + rel;
        break;
    }

    /* ---- I/O via DX ---- */
    case 0xEC: /* IN AL, DX */
        out->instruction = X86_INS_IN;
        out->operand_count = 2;
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = X86_REG_EAX;
        out->operands[0].size = 1;
        out->operands[1].type = X86_OP_REG;
        out->operands[1].reg = X86_REG_EDX;
        out->operands[1].size = 2;
        break;
    case 0xED: /* IN EAX, DX */
        out->instruction = X86_INS_IN;
        out->operand_count = 2;
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = X86_REG_EAX;
        out->operands[0].size = op_size;
        out->operands[1].type = X86_OP_REG;
        out->operands[1].reg = X86_REG_EDX;
        out->operands[1].size = 2;
        break;
    case 0xEE: /* OUT DX, AL */
        out->instruction = X86_INS_OUT;
        out->operand_count = 2;
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = X86_REG_EDX;
        out->operands[0].size = 2;
        out->operands[1].type = X86_OP_REG;
        out->operands[1].reg = X86_REG_EAX;
        out->operands[1].size = 1;
        break;
    case 0xEF: /* OUT DX, EAX */
        out->instruction = X86_INS_OUT;
        out->operand_count = 2;
        out->operands[0].type = X86_OP_REG;
        out->operands[0].reg = X86_REG_EDX;
        out->operands[0].size = 2;
        out->operands[1].type = X86_OP_REG;
        out->operands[1].reg = X86_REG_EAX;
        out->operands[1].size = op_size;
        break;

    /* ---- Group 3: F6/F7 ---- */
    case 0xF6: { /* Group 3, r/m8 */
        decode_modrm(dec, &out->operands[0], &reg, 1);
        out->instruction = group3_ops[reg];
        if (reg <= 1) { /* TEST r/m8, imm8 */
            out->operand_count = 2;
            out->operands[1].type = X86_OP_IMM;
            out->operands[1].imm = (uint8_t)eat(dec);
            out->operands[1].size = 1;
        } else {
            out->operand_count = 1;
        }
        break;
    }
    case 0xF7: { /* Group 3, r/m32 */
        decode_modrm(dec, &out->operands[0], &reg, op_size);
        out->instruction = group3_ops[reg];
        if (reg <= 1) { /* TEST r/m32, imm32 */
            out->operand_count = 2;
            out->operands[1].type = X86_OP_IMM;
            out->operands[1].imm = read_i32(dec);
            out->operands[1].size = op_size;
        } else {
            out->operand_count = 1;
        }
        break;
    }

    /* ---- System ---- */
    case 0xF4: out->instruction = X86_INS_HLT; break;
    case 0xFA: out->instruction = X86_INS_CLI; break;
    case 0xFB: out->instruction = X86_INS_STI; break;
    case 0xFC: out->instruction = X86_INS_CLD; break;
    case 0xFD: out->instruction = X86_INS_STD; break;
    case 0x99: out->instruction = X86_INS_CDQ; break;
    case 0x98: out->instruction = X86_INS_CBW; break;

    /* ---- Group 4: FE (INC/DEC r/m8) ---- */
    case 0xFE: {
        decode_modrm(dec, &out->operands[0], &reg, 1);
        out->instruction = (reg == 0) ? X86_INS_INC : X86_INS_DEC;
        out->operand_count = 1;
        break;
    }

    /* ---- Group 5: FF ---- */
    case 0xFF: {
        decode_modrm(dec, &out->operands[0], &reg, op_size);
        out->instruction = group5_ops[reg];
        out->operand_count = 1;
        break;
    }

    /* ---- String ops with REP prefix (already consumed) ---- */
    case 0xA4: /* MOVSB */
        out->instruction = (out->prefixes & X86_PREFIX_REP) ?
            X86_INS_REP_MOVSB : X86_INS_UNKNOWN;
        if (out->instruction == X86_INS_UNKNOWN) out->instruction = X86_INS_NOP; /* bare MOVSB */
        break;
    case 0xA5: /* MOVSD */
        out->instruction = (out->prefixes & X86_PREFIX_REP) ?
            X86_INS_REP_MOVSD : X86_INS_NOP;
        break;
    case 0xAA: /* STOSB */
        out->instruction = (out->prefixes & X86_PREFIX_REP) ?
            X86_INS_REP_STOSB : X86_INS_NOP;
        break;
    case 0xAB: /* STOSD */
        out->instruction = (out->prefixes & X86_PREFIX_REP) ?
            X86_INS_REP_STOSD : X86_INS_NOP;
        break;

    /* ---- Two-byte opcode escape ---- */
    case 0x0F: {
        if (!has_bytes(dec, 1)) { out->instruction = X86_INS_UNKNOWN; break; }
        uint8_t op2 = eat(dec);

        switch (op2) {
        /* Jcc near (0F 80 - 0F 8F) */
        case 0x80: case 0x81: case 0x82: case 0x83:
        case 0x84: case 0x85: case 0x86: case 0x87:
        case 0x88: case 0x89: case 0x8A: case 0x8B:
        case 0x8C: case 0x8D: case 0x8E: case 0x8F: {
            out->instruction = X86_INS_JCC;
            out->cc = op2 - 0x80;
            int32_t rel = read_i32(dec);
            out->operand_count = 1;
            out->operands[0].type = X86_OP_REL;
            out->operands[0].imm = (int64_t)(dec->base_address + dec->offset) + rel;
            break;
        }

        /* SETcc (0F 90 - 0F 9F) */
        case 0x90: case 0x91: case 0x92: case 0x93:
        case 0x94: case 0x95: case 0x96: case 0x97:
        case 0x98: case 0x99: case 0x9A: case 0x9B:
        case 0x9C: case 0x9D: case 0x9E: case 0x9F: {
            out->instruction = X86_INS_SETCC;
            out->cc = op2 - 0x90;
            out->operand_count = 1;
            decode_modrm(dec, &out->operands[0], &reg, 1);
            break;
        }

        /* MOVZX (0F B6/B7) */
        case 0xB6: { /* MOVZX r32, r/m8 */
            out->instruction = X86_INS_MOVZX;
            out->operand_count = 2;
            decode_modrm(dec, &out->operands[1], &reg, 1);
            out->operands[0].type = X86_OP_REG;
            out->operands[0].reg = reg;
            out->operands[0].size = op_size;
            break;
        }
        case 0xB7: { /* MOVZX r32, r/m16 */
            out->instruction = X86_INS_MOVZX;
            out->operand_count = 2;
            decode_modrm(dec, &out->operands[1], &reg, 2);
            out->operands[0].type = X86_OP_REG;
            out->operands[0].reg = reg;
            out->operands[0].size = op_size;
            break;
        }

        /* MOVSX (0F BE/BF) */
        case 0xBE: { /* MOVSX r32, r/m8 */
            out->instruction = X86_INS_MOVSX;
            out->operand_count = 2;
            decode_modrm(dec, &out->operands[1], &reg, 1);
            out->operands[0].type = X86_OP_REG;
            out->operands[0].reg = reg;
            out->operands[0].size = op_size;
            break;
        }
        case 0xBF: { /* MOVSX r32, r/m16 */
            out->instruction = X86_INS_MOVSX;
            out->operand_count = 2;
            decode_modrm(dec, &out->operands[1], &reg, 2);
            out->operands[0].type = X86_OP_REG;
            out->operands[0].reg = reg;
            out->operands[0].size = op_size;
            break;
        }

        /* IMUL r32, r/m32 (0F AF) */
        case 0xAF: {
            out->instruction = X86_INS_IMUL;
            out->operand_count = 2;
            decode_modrm(dec, &out->operands[1], &reg, op_size);
            out->operands[0].type = X86_OP_REG;
            out->operands[0].reg = reg;
            out->operands[0].size = op_size;
            break;
        }

        default:
            out->instruction = X86_INS_UNKNOWN;
            break;
        }
        break;
    }

    /* ---- LOOP ---- */
    case 0xE0: case 0xE1: case 0xE2: {
        out->instruction = X86_INS_LOOP;
        int8_t rel = read_i8(dec);
        out->operand_count = 1;
        out->operands[0].type = X86_OP_REL;
        out->operands[0].imm = (int64_t)(dec->base_address + dec->offset) + rel;
        break;
    }

    default:
        out->instruction = X86_INS_UNKNOWN;
        break;
    }

    out->length = (uint8_t)(dec->offset - start);
    return out->length;
}

/* ---- Decode a range ---- */

x86_decoded_t* x86_decode_range(x86_decoder_t* dec, size_t* count_out) {
    size_t cap = 256;
    size_t count = 0;
    x86_decoded_t* insts = malloc(cap * sizeof(x86_decoded_t));
    if (!insts) return NULL;

    while (dec->offset < dec->code_size) {
        if (count >= cap) {
            cap *= 2;
            x86_decoded_t* tmp = realloc(insts, cap * sizeof(x86_decoded_t));
            if (!tmp) { free(insts); return NULL; }
            insts = tmp;
        }

        int n = x86_decode_one(dec, &insts[count]);
        if (n <= 0) break;
        count++;
    }

    *count_out = count;
    return insts;
}

/* ---- Init ---- */

void x86_decoder_init(x86_decoder_t* dec, x86_mode_t mode,
                      const uint8_t* code, size_t code_size,
                      uint64_t base_address) {
    dec->mode = mode;
    dec->code = code;
    dec->code_size = code_size;
    dec->base_address = base_address;
    dec->offset = 0;
}

/* ---- Name tables ---- */

const char* x86_reg_name(int8_t reg, uint8_t size) {
    static const char* names32[] = {
        "eax","ecx","edx","ebx","esp","ebp","esi","edi"
    };
    static const char* names16[] = {
        "ax","cx","dx","bx","sp","bp","si","di"
    };
    static const char* names8[] = {
        "al","cl","dl","bl","ah","ch","dh","bh"
    };
    if (reg < 0 || reg > 7) return "???";
    if (size == 1) return names8[reg];
    if (size == 2) return names16[reg];
    return names32[reg];
}

static const char* ins_names[] = {
    [X86_INS_UNKNOWN] = "???",
    [X86_INS_MOV] = "mov", [X86_INS_MOVZX] = "movzx", [X86_INS_MOVSX] = "movsx",
    [X86_INS_LEA] = "lea", [X86_INS_XCHG] = "xchg",
    [X86_INS_PUSH] = "push", [X86_INS_POP] = "pop",
    [X86_INS_PUSHAD] = "pushad", [X86_INS_POPAD] = "popad",
    [X86_INS_ADD] = "add", [X86_INS_SUB] = "sub",
    [X86_INS_ADC] = "adc", [X86_INS_SBB] = "sbb",
    [X86_INS_INC] = "inc", [X86_INS_DEC] = "dec",
    [X86_INS_NEG] = "neg", [X86_INS_MUL] = "mul",
    [X86_INS_IMUL] = "imul", [X86_INS_DIV] = "div", [X86_INS_IDIV] = "idiv",
    [X86_INS_CMP] = "cmp",
    [X86_INS_AND] = "and", [X86_INS_OR] = "or", [X86_INS_XOR] = "xor",
    [X86_INS_NOT] = "not", [X86_INS_TEST] = "test",
    [X86_INS_SHL] = "shl", [X86_INS_SHR] = "shr", [X86_INS_SAR] = "sar",
    [X86_INS_ROL] = "rol", [X86_INS_ROR] = "ror",
    [X86_INS_JMP] = "jmp", [X86_INS_JCC] = "jcc",
    [X86_INS_CALL] = "call", [X86_INS_RET] = "ret",
    [X86_INS_LOOP] = "loop", [X86_INS_INT] = "int",
    [X86_INS_IN] = "in", [X86_INS_OUT] = "out",
    [X86_INS_INS] = "ins", [X86_INS_OUTS] = "outs",
    [X86_INS_CLI] = "cli", [X86_INS_STI] = "sti",
    [X86_INS_HLT] = "hlt", [X86_INS_NOP] = "nop",
    [X86_INS_LEAVE] = "leave",
    [X86_INS_CLD] = "cld", [X86_INS_STD] = "std",
    [X86_INS_CDQ] = "cdq", [X86_INS_CBW] = "cbw",
    [X86_INS_REP_MOVSB] = "rep movsb", [X86_INS_REP_MOVSD] = "rep movsd",
    [X86_INS_REP_STOSB] = "rep stosb", [X86_INS_REP_STOSD] = "rep stosd",
    [X86_INS_SETCC] = "setcc",
};

const char* x86_ins_name(x86_instruction_t ins) {
    if (ins >= 0 && ins < X86_INS_COUNT) return ins_names[ins];
    return "???";
}

static const char* cc_names[] = {
    "o","no","b","ae","e","ne","be","a",
    "s","ns","p","np","l","ge","le","g"
};

const char* x86_cc_name(x86_cc_t cc) {
    if (cc <= 0xF) return cc_names[cc];
    return "??";
}

/* ---- Print ---- */

static void print_operand(const x86_operand_t* op, FILE* out) {
    switch (op->type) {
    case X86_OP_REG:
        fprintf(out, "%s", x86_reg_name(op->reg, op->size));
        break;
    case X86_OP_IMM:
        fprintf(out, "0x%llx", (unsigned long long)op->imm);
        break;
    case X86_OP_REL:
        fprintf(out, "0x%llx", (unsigned long long)op->imm);
        break;
    case X86_OP_MEM: {
        const char* sz = op->size == 1 ? "byte" :
                         op->size == 2 ? "word" : "dword";
        fprintf(out, "%s [", sz);
        bool need_plus = false;
        if (op->base >= 0) {
            fprintf(out, "%s", x86_reg_name(op->base, 4));
            need_plus = true;
        }
        if (op->index >= 0) {
            if (need_plus) fprintf(out, "+");
            fprintf(out, "%s*%d", x86_reg_name(op->index, 4), op->scale);
            need_plus = true;
        }
        if (op->disp != 0 || (!need_plus)) {
            if (need_plus && op->disp >= 0) fprintf(out, "+");
            fprintf(out, "0x%x", op->disp);
        }
        fprintf(out, "]");
        break;
    }
    case X86_OP_NONE:
        break;
    }
}

void x86_print_decoded(const x86_decoded_t* inst, FILE* out) {
    fprintf(out, "%08llx:  ", (unsigned long long)inst->address);

    if (inst->instruction == X86_INS_JCC) {
        fprintf(out, "j%-5s ", x86_cc_name(inst->cc));
    } else if (inst->instruction == X86_INS_SETCC) {
        fprintf(out, "set%-3s ", x86_cc_name(inst->cc));
    } else {
        fprintf(out, "%-7s", x86_ins_name(inst->instruction));
    }

    for (int i = 0; i < inst->operand_count; i++) {
        if (i > 0) fprintf(out, ", ");
        print_operand(&inst->operands[i], out);
    }
    fprintf(out, "\n");
}
