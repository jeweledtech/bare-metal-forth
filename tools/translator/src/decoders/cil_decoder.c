/* ============================================================================
 * CIL/MSIL Instruction Decoder Implementation
 * ============================================================================
 *
 * Two-tier opcode table: primary (single-byte 0x00-0xFE) and extended
 * (prefix 0xFE followed by 0x00-0x1E). Table-driven decode with special
 * handling for SWITCH (variable-length jump table).
 *
 * CLR metadata parsing: locates #~ stream, reads MethodDef/TypeDef tables
 * to extract method RVAs and type namespace/name strings.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cil_decoder.h"
#include "pe_loader.h"

/* ---- Opcode table entry ---- */

typedef struct {
    cil_opcode_t        opcode;
    cil_operand_type_t  operand_type;
    uint8_t             operand_size;   /* 0,1,2,4,8; 0xFF = SWITCH */
} cil_opcode_info_t;

/* Shorthand for table entries */
#define E(op, ot, sz)  { op, ot, sz }
#define N(op)          { op, CIL_OPERAND_NONE, 0 }
#define UNK            { CIL_UNKNOWN, CIL_OPERAND_NONE, 0 }

/* ---- Primary opcode table (indexed by byte 0x00-0xFF) ---- */

static const cil_opcode_info_t primary_table[256] = {
    /* 0x00 */ N(CIL_NOP),
    /* 0x01 */ N(CIL_BREAK),
    /* 0x02 */ N(CIL_LDARG_0),
    /* 0x03 */ N(CIL_LDARG_1),
    /* 0x04 */ N(CIL_LDARG_2),
    /* 0x05 */ N(CIL_LDARG_3),
    /* 0x06 */ N(CIL_LDLOC_0),
    /* 0x07 */ N(CIL_LDLOC_1),
    /* 0x08 */ N(CIL_LDLOC_2),
    /* 0x09 */ N(CIL_LDLOC_3),
    /* 0x0A */ N(CIL_STLOC_0),
    /* 0x0B */ N(CIL_STLOC_1),
    /* 0x0C */ N(CIL_STLOC_2),
    /* 0x0D */ N(CIL_STLOC_3),
    /* 0x0E */ E(CIL_LDARG_S,   CIL_OPERAND_UINT8, 1),
    /* 0x0F */ E(CIL_LDARGA_S,  CIL_OPERAND_UINT8, 1),
    /* 0x10 */ E(CIL_STARG_S,   CIL_OPERAND_UINT8, 1),
    /* 0x11 */ E(CIL_LDLOC_S,   CIL_OPERAND_UINT8, 1),
    /* 0x12 */ E(CIL_LDLOCA_S,  CIL_OPERAND_UINT8, 1),
    /* 0x13 */ E(CIL_STLOC_S,   CIL_OPERAND_UINT8, 1),
    /* 0x14 */ N(CIL_LDNULL),
    /* 0x15 */ N(CIL_LDC_I4_M1),
    /* 0x16 */ N(CIL_LDC_I4_0),
    /* 0x17 */ N(CIL_LDC_I4_1),
    /* 0x18 */ N(CIL_LDC_I4_2),
    /* 0x19 */ N(CIL_LDC_I4_3),
    /* 0x1A */ N(CIL_LDC_I4_4),
    /* 0x1B */ N(CIL_LDC_I4_5),
    /* 0x1C */ N(CIL_LDC_I4_6),
    /* 0x1D */ N(CIL_LDC_I4_7),
    /* 0x1E */ N(CIL_LDC_I4_8),
    /* 0x1F */ E(CIL_LDC_I4_S,  CIL_OPERAND_INT8, 1),
    /* 0x20 */ E(CIL_LDC_I4,    CIL_OPERAND_INT32, 4),
    /* 0x21 */ E(CIL_LDC_I8,    CIL_OPERAND_INT64, 8),
    /* 0x22 */ E(CIL_LDC_R4,    CIL_OPERAND_FLOAT32, 4),
    /* 0x23 */ E(CIL_LDC_R8,    CIL_OPERAND_FLOAT64, 8),
    /* 0x24 */ UNK,
    /* 0x25 */ N(CIL_DUP),
    /* 0x26 */ N(CIL_POP),
    /* 0x27 */ E(CIL_JMP,       CIL_OPERAND_TOKEN, 4),
    /* 0x28 */ E(CIL_CALL,      CIL_OPERAND_TOKEN, 4),
    /* 0x29 */ E(CIL_CALLI,     CIL_OPERAND_TOKEN, 4),
    /* 0x2A */ N(CIL_RET),
    /* 0x2B */ E(CIL_BR_S,      CIL_OPERAND_BRANCH8, 1),
    /* 0x2C */ E(CIL_BRFALSE_S, CIL_OPERAND_BRANCH8, 1),
    /* 0x2D */ E(CIL_BRTRUE_S,  CIL_OPERAND_BRANCH8, 1),
    /* 0x2E */ E(CIL_BEQ_S,     CIL_OPERAND_BRANCH8, 1),
    /* 0x2F */ E(CIL_BGE_S,     CIL_OPERAND_BRANCH8, 1),
    /* 0x30 */ E(CIL_BGT_S,     CIL_OPERAND_BRANCH8, 1),
    /* 0x31 */ E(CIL_BLE_S,     CIL_OPERAND_BRANCH8, 1),
    /* 0x32 */ E(CIL_BLT_S,     CIL_OPERAND_BRANCH8, 1),
    /* 0x33 */ E(CIL_BNE_UN_S,  CIL_OPERAND_BRANCH8, 1),
    /* 0x34 */ E(CIL_BGE_UN_S,  CIL_OPERAND_BRANCH8, 1),
    /* 0x35 */ E(CIL_BGT_UN_S,  CIL_OPERAND_BRANCH8, 1),
    /* 0x36 */ E(CIL_BLE_UN_S,  CIL_OPERAND_BRANCH8, 1),
    /* 0x37 */ E(CIL_BLT_UN_S,  CIL_OPERAND_BRANCH8, 1),
    /* 0x38 */ E(CIL_BR,        CIL_OPERAND_BRANCH32, 4),
    /* 0x39 */ E(CIL_BRFALSE,   CIL_OPERAND_BRANCH32, 4),
    /* 0x3A */ E(CIL_BRTRUE,    CIL_OPERAND_BRANCH32, 4),
    /* 0x3B */ E(CIL_BEQ,       CIL_OPERAND_BRANCH32, 4),
    /* 0x3C */ E(CIL_BGE,       CIL_OPERAND_BRANCH32, 4),
    /* 0x3D */ E(CIL_BGT,       CIL_OPERAND_BRANCH32, 4),
    /* 0x3E */ E(CIL_BLE,       CIL_OPERAND_BRANCH32, 4),
    /* 0x3F */ E(CIL_BLT,       CIL_OPERAND_BRANCH32, 4),
    /* 0x40 */ E(CIL_BNE_UN,    CIL_OPERAND_BRANCH32, 4),
    /* 0x41 */ E(CIL_BGE_UN,    CIL_OPERAND_BRANCH32, 4),
    /* 0x42 */ E(CIL_BGT_UN,    CIL_OPERAND_BRANCH32, 4),
    /* 0x43 */ E(CIL_BLE_UN,    CIL_OPERAND_BRANCH32, 4),
    /* 0x44 */ E(CIL_BLT_UN,    CIL_OPERAND_BRANCH32, 4),
    /* 0x45 */ E(CIL_SWITCH,    CIL_OPERAND_SWITCH, 0xFF),
    /* 0x46 */ N(CIL_LDIND_I1),
    /* 0x47 */ N(CIL_LDIND_U1),
    /* 0x48 */ N(CIL_LDIND_I2),
    /* 0x49 */ N(CIL_LDIND_U2),
    /* 0x4A */ N(CIL_LDIND_I4),
    /* 0x4B */ N(CIL_LDIND_U4),
    /* 0x4C */ N(CIL_LDIND_I8),
    /* 0x4D */ N(CIL_LDIND_I),
    /* 0x4E */ N(CIL_LDIND_R4),
    /* 0x4F */ N(CIL_LDIND_R8),
    /* 0x50 */ N(CIL_LDIND_REF),
    /* 0x51 */ N(CIL_STIND_REF),
    /* 0x52 */ N(CIL_STIND_I1),
    /* 0x53 */ N(CIL_STIND_I2),
    /* 0x54 */ N(CIL_STIND_I4),
    /* 0x55 */ N(CIL_STIND_I8),
    /* 0x56 */ N(CIL_STIND_R4),
    /* 0x57 */ N(CIL_STIND_R8),
    /* 0x58 */ N(CIL_ADD),
    /* 0x59 */ N(CIL_SUB),
    /* 0x5A */ N(CIL_MUL),
    /* 0x5B */ N(CIL_DIV),
    /* 0x5C */ N(CIL_DIV_UN),
    /* 0x5D */ N(CIL_REM),
    /* 0x5E */ N(CIL_REM_UN),
    /* 0x5F */ N(CIL_AND),
    /* 0x60 */ N(CIL_OR),
    /* 0x61 */ N(CIL_XOR),
    /* 0x62 */ N(CIL_SHL),
    /* 0x63 */ N(CIL_SHR),
    /* 0x64 */ N(CIL_SHR_UN),
    /* 0x65 */ N(CIL_NEG),
    /* 0x66 */ N(CIL_NOT),
    /* 0x67 */ N(CIL_CONV_I1),
    /* 0x68 */ N(CIL_CONV_I2),
    /* 0x69 */ N(CIL_CONV_I4),
    /* 0x6A */ N(CIL_CONV_I8),
    /* 0x6B */ N(CIL_CONV_R4),
    /* 0x6C */ N(CIL_CONV_R8),
    /* 0x6D */ N(CIL_CONV_U4),
    /* 0x6E */ N(CIL_CONV_U8),
    /* 0x6F */ E(CIL_CALLVIRT,  CIL_OPERAND_TOKEN, 4),
    /* 0x70 */ E(CIL_CPOBJ,     CIL_OPERAND_TOKEN, 4),
    /* 0x71 */ E(CIL_LDOBJ,     CIL_OPERAND_TOKEN, 4),
    /* 0x72 */ E(CIL_LDSTR,     CIL_OPERAND_STRING, 4),
    /* 0x73 */ E(CIL_NEWOBJ,    CIL_OPERAND_TOKEN, 4),
    /* 0x74 */ E(CIL_CASTCLASS, CIL_OPERAND_TOKEN, 4),
    /* 0x75 */ E(CIL_ISINST,    CIL_OPERAND_TOKEN, 4),
    /* 0x76 */ N(CIL_CONV_R_UN),
    /* 0x77-0x78 */ UNK, UNK,
    /* 0x79 */ E(CIL_UNBOX,     CIL_OPERAND_TOKEN, 4),
    /* 0x7A */ N(CIL_THROW),
    /* 0x7B */ E(CIL_LDFLD,     CIL_OPERAND_TOKEN, 4),
    /* 0x7C */ E(CIL_LDFLDA,    CIL_OPERAND_TOKEN, 4),
    /* 0x7D */ E(CIL_STFLD,     CIL_OPERAND_TOKEN, 4),
    /* 0x7E */ E(CIL_LDSFLD,    CIL_OPERAND_TOKEN, 4),
    /* 0x7F */ E(CIL_LDSFLDA,   CIL_OPERAND_TOKEN, 4),
    /* 0x80 */ E(CIL_STSFLD,    CIL_OPERAND_TOKEN, 4),
    /* 0x81 */ E(CIL_STOBJ,     CIL_OPERAND_TOKEN, 4),
    /* 0x82 */ N(CIL_CONV_OVF_I1_UN),
    /* 0x83 */ N(CIL_CONV_OVF_I2_UN),
    /* 0x84 */ N(CIL_CONV_OVF_I4_UN),
    /* 0x85 */ N(CIL_CONV_OVF_I8_UN),
    /* 0x86 */ N(CIL_CONV_OVF_U1_UN),
    /* 0x87 */ N(CIL_CONV_OVF_U2_UN),
    /* 0x88 */ N(CIL_CONV_OVF_U4_UN),
    /* 0x89 */ N(CIL_CONV_OVF_U8_UN),
    /* 0x8A */ N(CIL_CONV_OVF_I_UN),
    /* 0x8B */ N(CIL_CONV_OVF_U_UN),
    /* 0x8C */ E(CIL_BOX,       CIL_OPERAND_TOKEN, 4),
    /* 0x8D */ E(CIL_NEWARR,    CIL_OPERAND_TOKEN, 4),
    /* 0x8E */ N(CIL_LDLEN),
    /* 0x8F */ E(CIL_LDELEMA,   CIL_OPERAND_TOKEN, 4),
    /* 0x90 */ N(CIL_LDELEM_I1),
    /* 0x91 */ N(CIL_LDELEM_U1),
    /* 0x92 */ N(CIL_LDELEM_I2),
    /* 0x93 */ N(CIL_LDELEM_U2),
    /* 0x94 */ N(CIL_LDELEM_I4),
    /* 0x95 */ N(CIL_LDELEM_U4),
    /* 0x96 */ N(CIL_LDELEM_I8),
    /* 0x97 */ N(CIL_LDELEM_I),
    /* 0x98 */ N(CIL_LDELEM_R4),
    /* 0x99 */ N(CIL_LDELEM_R8),
    /* 0x9A */ N(CIL_LDELEM_REF),
    /* 0x9B */ N(CIL_STELEM_I),
    /* 0x9C */ N(CIL_STELEM_I1),
    /* 0x9D */ N(CIL_STELEM_I2),
    /* 0x9E */ N(CIL_STELEM_I4),
    /* 0x9F */ N(CIL_STELEM_I8),
    /* 0xA0 */ N(CIL_STELEM_R4),
    /* 0xA1 */ N(CIL_STELEM_R8),
    /* 0xA2 */ N(CIL_STELEM_REF),
    /* 0xA3 */ E(CIL_LDELEM,    CIL_OPERAND_TOKEN, 4),
    /* 0xA4 */ E(CIL_STELEM,    CIL_OPERAND_TOKEN, 4),
    /* 0xA5 */ E(CIL_UNBOX_ANY, CIL_OPERAND_TOKEN, 4),
    /* 0xA6-0xB2 */ UNK, UNK, UNK, UNK, UNK, UNK, UNK, UNK, UNK, UNK, UNK, UNK, UNK,
    /* 0xB3 */ N(CIL_CONV_OVF_I1),
    /* 0xB4 */ N(CIL_CONV_OVF_U1),
    /* 0xB5 */ N(CIL_CONV_OVF_I2),
    /* 0xB6 */ N(CIL_CONV_OVF_U2),
    /* 0xB7 */ N(CIL_CONV_OVF_I4),
    /* 0xB8 */ N(CIL_CONV_OVF_U4),
    /* 0xB9 */ N(CIL_CONV_OVF_I8),
    /* 0xBA */ N(CIL_CONV_OVF_U8),
    /* 0xBB-0xC1 */ UNK, UNK, UNK, UNK, UNK, UNK, UNK,
    /* 0xC2 */ E(CIL_REFANYVAL,  CIL_OPERAND_TOKEN, 4),
    /* 0xC3 */ N(CIL_CKFINITE),
    /* 0xC4-0xC5 */ UNK, UNK,
    /* 0xC6 */ E(CIL_MKREFANY,   CIL_OPERAND_TOKEN, 4),
    /* 0xC7-0xCF */ UNK, UNK, UNK, UNK, UNK, UNK, UNK, UNK, UNK,
    /* 0xD0 */ E(CIL_LDTOKEN,    CIL_OPERAND_TOKEN, 4),
    /* 0xD1 */ N(CIL_CONV_U2),
    /* 0xD2 */ N(CIL_CONV_U1),
    /* 0xD3 */ N(CIL_CONV_I),
    /* 0xD4 */ N(CIL_CONV_OVF_I),
    /* 0xD5 */ N(CIL_CONV_OVF_U),
    /* 0xD6 */ N(CIL_ADD_OVF),
    /* 0xD7 */ N(CIL_ADD_OVF_UN),
    /* 0xD8 */ N(CIL_MUL_OVF),
    /* 0xD9 */ N(CIL_MUL_OVF_UN),
    /* 0xDA */ N(CIL_SUB_OVF),
    /* 0xDB */ N(CIL_SUB_OVF_UN),
    /* 0xDC */ N(CIL_ENDFINALLY),
    /* 0xDD */ E(CIL_LEAVE,      CIL_OPERAND_BRANCH32, 4),
    /* 0xDE */ E(CIL_LEAVE_S,    CIL_OPERAND_BRANCH8, 1),
    /* 0xDF */ N(CIL_STIND_I),
    /* 0xE0 */ N(CIL_CONV_U),
    /* 0xE1-0xFD */ UNK, UNK, UNK, UNK, UNK, UNK, UNK,
                    UNK, UNK, UNK, UNK, UNK, UNK, UNK,
                    UNK, UNK, UNK, UNK, UNK, UNK, UNK,
                    UNK, UNK, UNK, UNK, UNK, UNK, UNK, UNK,
    /* 0xFE */ E(CIL_UNKNOWN, CIL_OPERAND_NONE, 0),  /* prefix — handled specially */
    /* 0xFF */ UNK,
};

/* ---- Extended opcode table (prefix 0xFE, indexed by second byte) ---- */

static const cil_opcode_info_t extended_table[32] = {
    /* 0xFE 0x00 */ N(CIL_ARGLIST),
    /* 0xFE 0x01 */ N(CIL_CEQ),
    /* 0xFE 0x02 */ N(CIL_CGT),
    /* 0xFE 0x03 */ N(CIL_CGT_UN),
    /* 0xFE 0x04 */ N(CIL_CLT),
    /* 0xFE 0x05 */ N(CIL_CLT_UN),
    /* 0xFE 0x06 */ E(CIL_LDFTN,       CIL_OPERAND_TOKEN, 4),
    /* 0xFE 0x07 */ E(CIL_LDVIRTFTN,   CIL_OPERAND_TOKEN, 4),
    /* 0xFE 0x08 */ UNK,
    /* 0xFE 0x09 */ E(CIL_LDARG,       CIL_OPERAND_VAR16, 2),
    /* 0xFE 0x0A */ E(CIL_LDARGA,      CIL_OPERAND_VAR16, 2),
    /* 0xFE 0x0B */ E(CIL_STARG,       CIL_OPERAND_VAR16, 2),
    /* 0xFE 0x0C */ E(CIL_LDLOC,       CIL_OPERAND_VAR16, 2),
    /* 0xFE 0x0D */ E(CIL_LDLOCA,      CIL_OPERAND_VAR16, 2),
    /* 0xFE 0x0E */ E(CIL_STLOC,       CIL_OPERAND_VAR16, 2),
    /* 0xFE 0x0F */ N(CIL_LOCALLOC),
    /* 0xFE 0x10 */ UNK,
    /* 0xFE 0x11 */ N(CIL_ENDFILTER),
    /* 0xFE 0x12 */ E(CIL_UNALIGNED,   CIL_OPERAND_UINT8, 1),
    /* 0xFE 0x13 */ N(CIL_VOLATILE),
    /* 0xFE 0x14 */ N(CIL_TAIL),
    /* 0xFE 0x15 */ E(CIL_INITOBJ,     CIL_OPERAND_TOKEN, 4),
    /* 0xFE 0x16 */ E(CIL_CONSTRAINED, CIL_OPERAND_TOKEN, 4),
    /* 0xFE 0x17 */ N(CIL_CPBLK),
    /* 0xFE 0x18 */ N(CIL_INITBLK),
    /* 0xFE 0x19 */ UNK,  /* no. prefix — skip for V1 */
    /* 0xFE 0x1A */ N(CIL_RETHROW),
    /* 0xFE 0x1B */ UNK,
    /* 0xFE 0x1C */ E(CIL_SIZEOF,      CIL_OPERAND_TOKEN, 4),
    /* 0xFE 0x1D */ N(CIL_REFANYTYPE),
    /* 0xFE 0x1E */ N(CIL_READONLY),
    /* 0xFE 0x1F */ UNK,
};

/* ---- Read helpers ---- */

static inline uint8_t read_u8(const uint8_t* p) { return p[0]; }
static inline int8_t  read_i8(const uint8_t* p) { return (int8_t)p[0]; }

static inline uint16_t read_u16(const uint8_t* p) {
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static inline int32_t read_i32(const uint8_t* p) {
    return (int32_t)((uint32_t)p[0] | ((uint32_t)p[1] << 8) |
                     ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24));
}

static inline uint32_t read_u32(const uint8_t* p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static inline int64_t read_i64(const uint8_t* p) {
    return (int64_t)((uint64_t)read_u32(p) |
                     ((uint64_t)read_u32(p + 4) << 32));
}

static inline float read_f32(const uint8_t* p) {
    float f;
    memcpy(&f, p, 4);
    return f;
}

static inline double read_f64(const uint8_t* p) {
    double d;
    memcpy(&d, p, 8);
    return d;
}

/* ---- Opcode name table ---- */

static const char* opcode_names[] = {
    [CIL_UNKNOWN]     = "UNKNOWN",
    [CIL_NOP]         = "nop",
    [CIL_BREAK]       = "break",
    [CIL_LDARG_0]     = "ldarg.0",
    [CIL_LDARG_1]     = "ldarg.1",
    [CIL_LDARG_2]     = "ldarg.2",
    [CIL_LDARG_3]     = "ldarg.3",
    [CIL_LDARG_S]     = "ldarg.s",
    [CIL_LDARG]       = "ldarg",
    [CIL_STARG_S]     = "starg.s",
    [CIL_STARG]       = "starg",
    [CIL_LDARGA_S]    = "ldarga.s",
    [CIL_LDARGA]      = "ldarga",
    [CIL_LDLOC_0]     = "ldloc.0",
    [CIL_LDLOC_1]     = "ldloc.1",
    [CIL_LDLOC_2]     = "ldloc.2",
    [CIL_LDLOC_3]     = "ldloc.3",
    [CIL_LDLOC_S]     = "ldloc.s",
    [CIL_LDLOC]       = "ldloc",
    [CIL_STLOC_0]     = "stloc.0",
    [CIL_STLOC_1]     = "stloc.1",
    [CIL_STLOC_2]     = "stloc.2",
    [CIL_STLOC_3]     = "stloc.3",
    [CIL_STLOC_S]     = "stloc.s",
    [CIL_STLOC]       = "stloc",
    [CIL_LDLOCA_S]    = "ldloca.s",
    [CIL_LDLOCA]      = "ldloca",
    [CIL_LDNULL]      = "ldnull",
    [CIL_LDC_I4_M1]   = "ldc.i4.m1",
    [CIL_LDC_I4_0]    = "ldc.i4.0",
    [CIL_LDC_I4_1]    = "ldc.i4.1",
    [CIL_LDC_I4_2]    = "ldc.i4.2",
    [CIL_LDC_I4_3]    = "ldc.i4.3",
    [CIL_LDC_I4_4]    = "ldc.i4.4",
    [CIL_LDC_I4_5]    = "ldc.i4.5",
    [CIL_LDC_I4_6]    = "ldc.i4.6",
    [CIL_LDC_I4_7]    = "ldc.i4.7",
    [CIL_LDC_I4_8]    = "ldc.i4.8",
    [CIL_LDC_I4_S]    = "ldc.i4.s",
    [CIL_LDC_I4]      = "ldc.i4",
    [CIL_LDC_I8]      = "ldc.i8",
    [CIL_LDC_R4]      = "ldc.r4",
    [CIL_LDC_R8]      = "ldc.r8",
    [CIL_DUP]         = "dup",
    [CIL_POP]         = "pop",
    [CIL_CALL]        = "call",
    [CIL_CALLVIRT]    = "callvirt",
    [CIL_CALLI]       = "calli",
    [CIL_RET]         = "ret",
    [CIL_JMP]         = "jmp",
    [CIL_BR_S]        = "br.s",
    [CIL_BR]          = "br",
    [CIL_BRFALSE_S]   = "brfalse.s",
    [CIL_BRTRUE_S]    = "brtrue.s",
    [CIL_BRFALSE]     = "brfalse",
    [CIL_BRTRUE]      = "brtrue",
    [CIL_BEQ_S]       = "beq.s",
    [CIL_BGE_S]       = "bge.s",
    [CIL_BGT_S]       = "bgt.s",
    [CIL_BLE_S]       = "ble.s",
    [CIL_BLT_S]       = "blt.s",
    [CIL_BNE_UN_S]    = "bne.un.s",
    [CIL_BGE_UN_S]    = "bge.un.s",
    [CIL_BGT_UN_S]    = "bgt.un.s",
    [CIL_BLE_UN_S]    = "ble.un.s",
    [CIL_BLT_UN_S]    = "blt.un.s",
    [CIL_BEQ]         = "beq",
    [CIL_BGE]         = "bge",
    [CIL_BGT]         = "bgt",
    [CIL_BLE]         = "ble",
    [CIL_BLT]         = "blt",
    [CIL_BNE_UN]      = "bne.un",
    [CIL_BGE_UN]      = "bge.un",
    [CIL_BGT_UN]      = "bgt.un",
    [CIL_BLE_UN]      = "ble.un",
    [CIL_BLT_UN]      = "blt.un",
    [CIL_SWITCH]      = "switch",
    [CIL_LDIND_I1]    = "ldind.i1",
    [CIL_LDIND_U1]    = "ldind.u1",
    [CIL_LDIND_I2]    = "ldind.i2",
    [CIL_LDIND_U2]    = "ldind.u2",
    [CIL_LDIND_I4]    = "ldind.i4",
    [CIL_LDIND_U4]    = "ldind.u4",
    [CIL_LDIND_I8]    = "ldind.i8",
    [CIL_LDIND_I]     = "ldind.i",
    [CIL_LDIND_R4]    = "ldind.r4",
    [CIL_LDIND_R8]    = "ldind.r8",
    [CIL_LDIND_REF]   = "ldind.ref",
    [CIL_STIND_REF]   = "stind.ref",
    [CIL_STIND_I1]    = "stind.i1",
    [CIL_STIND_I2]    = "stind.i2",
    [CIL_STIND_I4]    = "stind.i4",
    [CIL_STIND_I8]    = "stind.i8",
    [CIL_STIND_R4]    = "stind.r4",
    [CIL_STIND_R8]    = "stind.r8",
    [CIL_STIND_I]     = "stind.i",
    [CIL_ADD]         = "add",
    [CIL_SUB]         = "sub",
    [CIL_MUL]         = "mul",
    [CIL_DIV]         = "div",
    [CIL_DIV_UN]      = "div.un",
    [CIL_REM]         = "rem",
    [CIL_REM_UN]      = "rem.un",
    [CIL_NEG]         = "neg",
    [CIL_ADD_OVF]     = "add.ovf",
    [CIL_ADD_OVF_UN]  = "add.ovf.un",
    [CIL_SUB_OVF]     = "sub.ovf",
    [CIL_SUB_OVF_UN]  = "sub.ovf.un",
    [CIL_MUL_OVF]     = "mul.ovf",
    [CIL_MUL_OVF_UN]  = "mul.ovf.un",
    [CIL_AND]         = "and",
    [CIL_OR]          = "or",
    [CIL_XOR]         = "xor",
    [CIL_NOT]         = "not",
    [CIL_SHL]         = "shl",
    [CIL_SHR]         = "shr",
    [CIL_SHR_UN]      = "shr.un",
    [CIL_CONV_I1]     = "conv.i1",
    [CIL_CONV_I2]     = "conv.i2",
    [CIL_CONV_I4]     = "conv.i4",
    [CIL_CONV_I8]     = "conv.i8",
    [CIL_CONV_R4]     = "conv.r4",
    [CIL_CONV_R8]     = "conv.r8",
    [CIL_CONV_U4]     = "conv.u4",
    [CIL_CONV_U8]     = "conv.u8",
    [CIL_CONV_R_UN]   = "conv.r.un",
    [CIL_CONV_U2]     = "conv.u2",
    [CIL_CONV_U1]     = "conv.u1",
    [CIL_CONV_I]      = "conv.i",
    [CIL_CONV_U]      = "conv.u",
    [CIL_CONV_OVF_I1] = "conv.ovf.i1",
    [CIL_CONV_OVF_I2] = "conv.ovf.i2",
    [CIL_CONV_OVF_I4] = "conv.ovf.i4",
    [CIL_CONV_OVF_I8] = "conv.ovf.i8",
    [CIL_CONV_OVF_U1] = "conv.ovf.u1",
    [CIL_CONV_OVF_U2] = "conv.ovf.u2",
    [CIL_CONV_OVF_U4] = "conv.ovf.u4",
    [CIL_CONV_OVF_U8] = "conv.ovf.u8",
    [CIL_CONV_OVF_I]  = "conv.ovf.i",
    [CIL_CONV_OVF_U]  = "conv.ovf.u",
    [CIL_CONV_OVF_I1_UN] = "conv.ovf.i1.un",
    [CIL_CONV_OVF_I2_UN] = "conv.ovf.i2.un",
    [CIL_CONV_OVF_I4_UN] = "conv.ovf.i4.un",
    [CIL_CONV_OVF_I8_UN] = "conv.ovf.i8.un",
    [CIL_CONV_OVF_U1_UN] = "conv.ovf.u1.un",
    [CIL_CONV_OVF_U2_UN] = "conv.ovf.u2.un",
    [CIL_CONV_OVF_U4_UN] = "conv.ovf.u4.un",
    [CIL_CONV_OVF_U8_UN] = "conv.ovf.u8.un",
    [CIL_CONV_OVF_I_UN]  = "conv.ovf.i.un",
    [CIL_CONV_OVF_U_UN]  = "conv.ovf.u.un",
    [CIL_CEQ]         = "ceq",
    [CIL_CGT]         = "cgt",
    [CIL_CGT_UN]      = "cgt.un",
    [CIL_CLT]         = "clt",
    [CIL_CLT_UN]      = "clt.un",
    [CIL_LDSTR]       = "ldstr",
    [CIL_NEWOBJ]      = "newobj",
    [CIL_CASTCLASS]   = "castclass",
    [CIL_ISINST]      = "isinst",
    [CIL_UNBOX]       = "unbox",
    [CIL_UNBOX_ANY]   = "unbox.any",
    [CIL_BOX]         = "box",
    [CIL_LDTOKEN]     = "ldtoken",
    [CIL_LDFLD]       = "ldfld",
    [CIL_LDFLDA]      = "ldflda",
    [CIL_STFLD]       = "stfld",
    [CIL_LDSFLD]      = "ldsfld",
    [CIL_LDSFLDA]     = "ldsflda",
    [CIL_STSFLD]      = "stsfld",
    [CIL_LDFTN]       = "ldftn",
    [CIL_LDVIRTFTN]   = "ldvirtftn",
    [CIL_NEWARR]      = "newarr",
    [CIL_LDLEN]       = "ldlen",
    [CIL_LDELEMA]     = "ldelema",
    [CIL_LDELEM_I1]   = "ldelem.i1",
    [CIL_LDELEM_U1]   = "ldelem.u1",
    [CIL_LDELEM_I2]   = "ldelem.i2",
    [CIL_LDELEM_U2]   = "ldelem.u2",
    [CIL_LDELEM_I4]   = "ldelem.i4",
    [CIL_LDELEM_U4]   = "ldelem.u4",
    [CIL_LDELEM_I8]   = "ldelem.i8",
    [CIL_LDELEM_I]    = "ldelem.i",
    [CIL_LDELEM_R4]   = "ldelem.r4",
    [CIL_LDELEM_R8]   = "ldelem.r8",
    [CIL_LDELEM_REF]  = "ldelem.ref",
    [CIL_LDELEM]      = "ldelem",
    [CIL_STELEM_I]    = "stelem.i",
    [CIL_STELEM_I1]   = "stelem.i1",
    [CIL_STELEM_I2]   = "stelem.i2",
    [CIL_STELEM_I4]   = "stelem.i4",
    [CIL_STELEM_I8]   = "stelem.i8",
    [CIL_STELEM_R4]   = "stelem.r4",
    [CIL_STELEM_R8]   = "stelem.r8",
    [CIL_STELEM_REF]  = "stelem.ref",
    [CIL_STELEM]      = "stelem",
    [CIL_CPOBJ]       = "cpobj",
    [CIL_LDOBJ]       = "ldobj",
    [CIL_STOBJ]       = "stobj",
    [CIL_CPBLK]       = "cpblk",
    [CIL_INITBLK]     = "initblk",
    [CIL_INITOBJ]     = "initobj",
    [CIL_SIZEOF]      = "sizeof",
    [CIL_THROW]       = "throw",
    [CIL_RETHROW]     = "rethrow",
    [CIL_LEAVE]       = "leave",
    [CIL_LEAVE_S]     = "leave.s",
    [CIL_ENDFINALLY]  = "endfinally",
    [CIL_ENDFILTER]   = "endfilter",
    [CIL_VOLATILE]    = "volatile.",
    [CIL_UNALIGNED]   = "unaligned.",
    [CIL_TAIL]        = "tail.",
    [CIL_CONSTRAINED] = "constrained.",
    [CIL_READONLY]    = "readonly.",
    [CIL_LOCALLOC]    = "localloc",
    [CIL_ARGLIST]     = "arglist",
    [CIL_REFANYTYPE]  = "refanytype",
    [CIL_REFANYVAL]   = "refanyval",
    [CIL_MKREFANY]    = "mkrefany",
    [CIL_CKFINITE]    = "ckfinite",
};

/* ============================================================================
 * CIL Decoder Core
 * ============================================================================ */

void cil_decoder_init(cil_decoder_t* dec,
                      const uint8_t* code, size_t code_size) {
    dec->code = code;
    dec->code_size = code_size;
    dec->offset = 0;
}

int cil_decode_one(cil_decoder_t* dec, cil_decoded_t* out) {
    if (dec->offset >= dec->code_size) return 0;

    memset(out, 0, sizeof(*out));
    out->offset = (uint32_t)dec->offset;

    size_t start = dec->offset;
    uint8_t byte0 = dec->code[dec->offset++];
    const cil_opcode_info_t* info;

    if (byte0 == 0xFE) {
        /* Extended opcode */
        if (dec->offset >= dec->code_size) return -1;
        uint8_t byte1 = dec->code[dec->offset++];
        if (byte1 >= 32) {
            out->opcode = CIL_UNKNOWN;
            out->length = (uint8_t)(dec->offset - start);
            return -1;
        }
        info = &extended_table[byte1];
    } else {
        info = &primary_table[byte0];
    }

    if (info->opcode == CIL_UNKNOWN) {
        out->opcode = CIL_UNKNOWN;
        out->length = (uint8_t)(dec->offset - start);
        return -1;
    }

    out->opcode = info->opcode;
    out->operand_type = info->operand_type;

    /* Read operand */
    switch (info->operand_type) {
    case CIL_OPERAND_NONE:
        break;
    case CIL_OPERAND_INT8:
        if (dec->offset + 1 > dec->code_size) return -1;
        out->operand.i8 = read_i8(dec->code + dec->offset);
        dec->offset += 1;
        break;
    case CIL_OPERAND_UINT8:
    case CIL_OPERAND_VAR8:
        if (dec->offset + 1 > dec->code_size) return -1;
        out->operand.u8 = read_u8(dec->code + dec->offset);
        dec->offset += 1;
        break;
    case CIL_OPERAND_INT32:
        if (dec->offset + 4 > dec->code_size) return -1;
        out->operand.i32 = read_i32(dec->code + dec->offset);
        dec->offset += 4;
        break;
    case CIL_OPERAND_INT64:
        if (dec->offset + 8 > dec->code_size) return -1;
        out->operand.i64 = read_i64(dec->code + dec->offset);
        dec->offset += 8;
        break;
    case CIL_OPERAND_FLOAT32:
        if (dec->offset + 4 > dec->code_size) return -1;
        out->operand.f32 = read_f32(dec->code + dec->offset);
        dec->offset += 4;
        break;
    case CIL_OPERAND_FLOAT64:
        if (dec->offset + 8 > dec->code_size) return -1;
        out->operand.f64 = read_f64(dec->code + dec->offset);
        dec->offset += 8;
        break;
    case CIL_OPERAND_TOKEN:
    case CIL_OPERAND_STRING:
        if (dec->offset + 4 > dec->code_size) return -1;
        out->operand.token = read_u32(dec->code + dec->offset);
        dec->offset += 4;
        break;
    case CIL_OPERAND_BRANCH8:
        if (dec->offset + 1 > dec->code_size) return -1;
        out->operand.branch = read_i8(dec->code + dec->offset);
        dec->offset += 1;
        break;
    case CIL_OPERAND_BRANCH32:
        if (dec->offset + 4 > dec->code_size) return -1;
        out->operand.branch = read_i32(dec->code + dec->offset);
        dec->offset += 4;
        break;
    case CIL_OPERAND_VAR16:
        if (dec->offset + 2 > dec->code_size) return -1;
        out->operand.var_index = read_u16(dec->code + dec->offset);
        dec->offset += 2;
        break;
    case CIL_OPERAND_SWITCH: {
        if (dec->offset + 4 > dec->code_size) return -1;
        uint32_t count = read_u32(dec->code + dec->offset);
        dec->offset += 4;
        if (count > 10000) return -1; /* sanity */
        if (dec->offset + (size_t)count * 4 > dec->code_size) return -1;
        out->switch_count = count;
        out->operand.i32 = (int32_t)count;
        if (count > 0) {
            out->switch_targets = malloc(count * sizeof(int32_t));
            if (!out->switch_targets) return -1;
            for (uint32_t i = 0; i < count; i++) {
                out->switch_targets[i] = read_i32(dec->code + dec->offset);
                dec->offset += 4;
            }
        }
        break;
    }
    }

    out->length = (uint8_t)(dec->offset - start);

    /* Copy raw bytes for diagnostics (max 6 for non-switch) */
    size_t raw_len = dec->offset - start;
    if (raw_len > 7) raw_len = 7;
    /* raw_bytes is already zeroed by memset */

    return (int)(dec->offset - start);
}

/* ============================================================================
 * Method Body Decoder
 * ============================================================================ */

int cil_decode_method(const uint8_t* code, size_t available,
                      cil_method_t* out) {
    if (available < 1) return -1;
    memset(out, 0, sizeof(*out));

    uint8_t header_byte = code[0];
    uint32_t code_offset;

    if ((header_byte & 0x03) == 0x02) {
        /* Tiny format: code_size in bits [7:2] */
        out->code_size = header_byte >> 2;
        out->max_stack = 8;  /* tiny methods default to max_stack = 8 */
        out->flags = CIL_METHOD_TINY;
        code_offset = 1;
    } else if ((header_byte & 0x03) == 0x03) {
        /* Fat format: 12-byte header */
        if (available < 12) return -1;
        uint16_t flags_and_size = read_u16(code);
        out->flags = flags_and_size & 0x0FFF;
        uint8_t header_size_dwords = (flags_and_size >> 12) & 0x0F;
        out->max_stack = read_u16(code + 2);
        out->code_size = read_u32(code + 4);
        out->local_var_sig_token = read_u32(code + 8);
        code_offset = (uint32_t)header_size_dwords * 4;
        if (code_offset < 12) code_offset = 12;
    } else {
        return -1; /* malformed */
    }

    if (code_offset + out->code_size > available) return -1;
    if (out->code_size == 0) return 0;

    /* Decode instructions */
    cil_decoder_t dec;
    cil_decoder_init(&dec, code + code_offset, out->code_size);

    size_t cap = 32;
    out->instructions = malloc(cap * sizeof(cil_decoded_t));
    if (!out->instructions) return -1;
    out->instruction_count = 0;

    while (dec.offset < dec.code_size) {
        if (out->instruction_count >= cap) {
            cap *= 2;
            cil_decoded_t* tmp = realloc(out->instructions,
                                          cap * sizeof(cil_decoded_t));
            if (!tmp) return -1;
            out->instructions = tmp;
        }
        int n = cil_decode_one(&dec, &out->instructions[out->instruction_count]);
        if (n <= 0) break;
        out->instruction_count++;
    }

    return 0;
}

/* ============================================================================
 * CLR Metadata Parser
 * ============================================================================ */

int cil_parse_metadata(const uint8_t* data, size_t data_size,
                       const void* pe_ctx_void,
                       cil_metadata_t* out) {
    (void)data;
    (void)data_size;
    const pe_context_t* pe = (const pe_context_t*)pe_ctx_void;
    memset(out, 0, sizeof(*out));

    if (!pe->is_managed) return -1;

    /* Locate metadata root via RVA */
    const uint8_t* meta_root = pe_rva_to_ptr(pe, pe->clr_metadata_rva);
    if (!meta_root) return -1;
    size_t meta_size = pe->clr_metadata_size;

    /* Check BSJB magic */
    if (meta_size < 16) return -1;
    if (meta_root[0] != 'B' || meta_root[1] != 'S' ||
        meta_root[2] != 'J' || meta_root[3] != 'B') return -1;

    /* Skip version string: length at offset 12, string follows */
    uint32_t version_len = read_u32(meta_root + 12);
    /* Round up to 4-byte boundary */
    uint32_t version_padded = (version_len + 3) & ~3u;

    size_t stream_header_offset = 16 + version_padded;
    if (stream_header_offset + 4 > meta_size) return -1;

    /* Skip flags (2 bytes) and read stream count */
    uint16_t stream_count = read_u16(meta_root + stream_header_offset + 2);
    stream_header_offset += 4;

    /* Walk stream headers to find #~, #Strings, #US, #Blob */
    for (uint16_t i = 0; i < stream_count; i++) {
        if (stream_header_offset + 8 > meta_size) break;
        uint32_t s_offset = read_u32(meta_root + stream_header_offset);
        uint32_t s_size = read_u32(meta_root + stream_header_offset + 4);
        const char* s_name = (const char*)(meta_root + stream_header_offset + 8);

        /* Find end of name (null-terminated, padded to 4 bytes) */
        size_t name_start = stream_header_offset + 8;
        size_t name_end = name_start;
        while (name_end < meta_size && meta_root[name_end] != '\0') name_end++;
        name_end++; /* skip null */
        name_end = (name_end + 3) & ~(size_t)3; /* pad to 4 bytes */

        if (s_offset + s_size <= meta_size) {
            if (strcmp(s_name, "#~") == 0 || strcmp(s_name, "#-") == 0) {
                out->tables_data = meta_root + s_offset;
                out->tables_size = s_size;
            } else if (strcmp(s_name, "#Strings") == 0) {
                out->strings_heap = meta_root + s_offset;
                out->strings_size = s_size;
            } else if (strcmp(s_name, "#US") == 0) {
                out->us_heap = meta_root + s_offset;
                out->us_size = s_size;
            } else if (strcmp(s_name, "#Blob") == 0) {
                out->blob_heap = meta_root + s_offset;
                out->blob_size = s_size;
            }
        }

        stream_header_offset = name_end;
    }

    if (!out->tables_data || !out->strings_heap) return -1;

    /* Parse #~ stream header */
    if (out->tables_size < 24) return -1;
    const uint8_t* th = out->tables_data;
    /* Byte 6: HeapSizes */
    uint8_t heap_sizes = th[6];
    out->string_heap_wide = (heap_sizes & 0x01) != 0;
    out->guid_heap_wide   = (heap_sizes & 0x02) != 0;
    out->blob_heap_wide   = (heap_sizes & 0x04) != 0;

    /* Bytes 8-15: Valid bitmask (which tables are present) */
    uint64_t valid = (uint64_t)read_u32(th + 8) |
                     ((uint64_t)read_u32(th + 12) << 32);

    /* Row counts follow at offset 24, one uint32 per set bit in valid */
    size_t row_offset = 24;
    uint32_t row_counts[64];
    memset(row_counts, 0, sizeof(row_counts));
    int table_count = 0;
    for (int t = 0; t < 64; t++) {
        if (valid & ((uint64_t)1 << t)) {
            if (row_offset + 4 > out->tables_size) return -1;
            row_counts[t] = read_u32(th + row_offset);
            row_offset += 4;
            table_count++;
        }
    }

    /* Extract counts for tables we care about */
    out->typedef_rows   = row_counts[0x02];
    out->typeref_rows   = row_counts[0x01];
    out->methoddef_rows = row_counts[0x06];
    out->memberref_rows = row_counts[0x0A];

    /* Compute row sizes and offsets.
     * String/Blob/GUID heap index widths depend on HeapSizes byte.
     * Table index widths depend on row counts. */
    uint8_t str_idx_size = out->string_heap_wide ? 4 : 2;
    uint8_t blob_idx_size = out->blob_heap_wide ? 4 : 2;
    (void)blob_idx_size; /* used in full implementation */

    /* TypeDef (table 0x02): Flags(4) + Name(str) + Namespace(str) +
     * Extends(coded idx 2 or 4) + FieldList(2 or 4) + MethodList(2 or 4) */
    /* Coded index TypeDefOrRef: 2 bits tag, refs TypeDef/TypeRef/TypeSpec */
    uint32_t max_tdrs = row_counts[0x02];
    if (row_counts[0x01] > max_tdrs) max_tdrs = row_counts[0x01];
    if (row_counts[0x1B] > max_tdrs) max_tdrs = row_counts[0x1B];
    uint8_t tdrs_idx_size = (max_tdrs < (1u << 14)) ? 2 : 4;

    uint8_t field_idx_size = (row_counts[0x04] < (1u << 16)) ? 2 : 4;
    uint8_t method_idx_size = (row_counts[0x06] < (1u << 16)) ? 2 : 4;

    out->typedef_row_size = 4 + str_idx_size + str_idx_size +
                            tdrs_idx_size + field_idx_size + method_idx_size;

    /* MethodDef (table 0x06): RVA(4) + ImplFlags(2) + Flags(2) +
     * Name(str) + Signature(blob) + ParamList(idx) */
    uint8_t param_idx_size = (row_counts[0x08] < (1u << 16)) ? 2 : 4;
    out->methoddef_row_size = 4 + 2 + 2 + str_idx_size +
                              blob_idx_size + param_idx_size;

    /* MemberRef (table 0x0A): Class(coded MemberRefParent) + Name(str) + Signature(blob) */
    uint32_t max_mrp = row_counts[0x02]; /* TypeDef */
    if (row_counts[0x01] > max_mrp) max_mrp = row_counts[0x01]; /* TypeRef */
    if (row_counts[0x06] > max_mrp) max_mrp = row_counts[0x06]; /* MethodDef */
    if (row_counts[0x1A] > max_mrp) max_mrp = row_counts[0x1A]; /* ModuleRef */
    if (row_counts[0x1B] > max_mrp) max_mrp = row_counts[0x1B]; /* TypeSpec */
    uint8_t mrp_idx_size = (max_mrp < (1u << 13)) ? 2 : 4; /* 3-bit tag */
    out->memberref_row_size = mrp_idx_size + str_idx_size + blob_idx_size;

    /* TypeRef (table 0x01): ResolutionScope(coded) + Name(str) + Namespace(str) */
    uint32_t max_rs = row_counts[0x00]; /* Module */
    if (row_counts[0x1A] > max_rs) max_rs = row_counts[0x1A]; /* ModuleRef */
    if (row_counts[0x23] > max_rs) max_rs = row_counts[0x23]; /* AssemblyRef */
    if (row_counts[0x01] > max_rs) max_rs = row_counts[0x01]; /* TypeRef */
    uint8_t rs_idx_size = (max_rs < (1u << 14)) ? 2 : 4; /* 2-bit tag */
    out->typeref_row_size = rs_idx_size + str_idx_size + str_idx_size;

    /* Compute table offsets: tables appear in order of table number,
     * but only for tables present in the valid bitmask */
    size_t data_offset = row_offset; /* past row counts */
    for (int t = 0; t < 64; t++) {
        if (!(valid & ((uint64_t)1 << t))) continue;

        uint8_t row_size = 0;
        switch (t) {
        case 0x00: /* Module: Generation(2)+Name(str)+Mvid(guid)+EncId(guid)+EncBaseId(guid) */
            row_size = 2 + str_idx_size +
                       (out->guid_heap_wide ? 4 : 2) * 3;
            break;
        case 0x01: /* TypeRef */
            out->typeref_offset = data_offset;
            row_size = out->typeref_row_size;
            break;
        case 0x02: /* TypeDef */
            out->typedef_offset = data_offset;
            row_size = out->typedef_row_size;
            break;
        case 0x04: /* Field: Flags(2)+Name(str)+Signature(blob) */
            row_size = 2 + str_idx_size + blob_idx_size;
            break;
        case 0x06: /* MethodDef */
            out->methoddef_offset = data_offset;
            row_size = out->methoddef_row_size;
            break;
        case 0x08: /* Param: Flags(2)+Sequence(2)+Name(str) */
            row_size = 2 + 2 + str_idx_size;
            break;
        case 0x09: /* InterfaceImpl: Class(TypeDef idx)+Interface(TypeDefOrRef coded) */
            row_size = (row_counts[0x02] < (1u << 16) ? 2 : 4) + tdrs_idx_size;
            break;
        case 0x0A: /* MemberRef */
            out->memberref_offset = data_offset;
            row_size = out->memberref_row_size;
            break;
        case 0x0B: /* Constant: Type(2)+Parent(coded HasConstant)+Value(blob) */
            row_size = 2 + 2 + blob_idx_size; /* simplified */
            break;
        default:
            /* For tables we don't care about, skip using a conservative
             * estimate. In a full implementation each table's row size
             * would be computed. For now, we stop tracking offsets past
             * the tables we need. */
            row_size = 0;
            break;
        }

        if (row_size == 0) {
            /* Unknown table — we can't compute sizes past here.
             * But we may already have the offsets we need. */
            break;
        }
        data_offset += (size_t)row_size * row_counts[t];
    }

    return 0;
}

/* ---- String heap lookup ---- */

static const char* strings_lookup(const cil_metadata_t* meta, uint32_t index) {
    if (!meta->strings_heap || index >= meta->strings_size) return NULL;
    return (const char*)(meta->strings_heap + index);
}

static uint32_t read_str_index(const uint8_t* p, bool wide) {
    return wide ? read_u32(p) : read_u16(p);
}

/* ---- Token resolution ---- */

const char* cil_resolve_type_namespace(const cil_metadata_t* meta,
                                       uint32_t token) {
    uint8_t table = (token >> 24) & 0xFF;
    uint32_t row = (token & 0x00FFFFFF) - 1; /* 1-based to 0-based */

    if (table == 0x02 && row < meta->typedef_rows) {
        /* TypeDef: skip Flags(4) + Name(str) to get Namespace(str) */
        uint8_t str_size = meta->string_heap_wide ? 4 : 2;
        size_t off = meta->typedef_offset +
                     (size_t)row * meta->typedef_row_size +
                     4 + str_size; /* skip Flags + Name */
        uint32_t ns_idx = read_str_index(meta->tables_data + off,
                                          meta->string_heap_wide);
        return strings_lookup(meta, ns_idx);
    }
    if (table == 0x01 && row < meta->typeref_rows) {
        /* TypeRef: skip ResolutionScope to get Name, then Namespace */
        uint8_t str_size = meta->string_heap_wide ? 4 : 2;
        uint8_t rs_size = meta->typeref_row_size - 2 * str_size;
        size_t off = meta->typeref_offset +
                     (size_t)row * meta->typeref_row_size +
                     rs_size + str_size; /* skip ResScope + Name */
        uint32_t ns_idx = read_str_index(meta->tables_data + off,
                                          meta->string_heap_wide);
        return strings_lookup(meta, ns_idx);
    }
    return NULL;
}

const char* cil_resolve_type_name(const cil_metadata_t* meta,
                                   uint32_t token) {
    uint8_t table = (token >> 24) & 0xFF;
    uint32_t row = (token & 0x00FFFFFF) - 1;

    if (table == 0x02 && row < meta->typedef_rows) {
        size_t off = meta->typedef_offset +
                     (size_t)row * meta->typedef_row_size + 4;
        uint32_t name_idx = read_str_index(meta->tables_data + off,
                                            meta->string_heap_wide);
        return strings_lookup(meta, name_idx);
    }
    if (table == 0x01 && row < meta->typeref_rows) {
        uint8_t str_size = meta->string_heap_wide ? 4 : 2;
        uint8_t rs_size = meta->typeref_row_size - 2 * str_size;
        size_t off = meta->typeref_offset +
                     (size_t)row * meta->typeref_row_size + rs_size;
        uint32_t name_idx = read_str_index(meta->tables_data + off,
                                            meta->string_heap_wide);
        return strings_lookup(meta, name_idx);
    }
    return NULL;
}

/* ============================================================================
 * Decode All Methods from PE
 * ============================================================================ */

cil_method_t* cil_decode_pe_methods(const uint8_t* data, size_t data_size,
                                     const void* pe_ctx_void,
                                     size_t* count_out) {
    const pe_context_t* pe = (const pe_context_t*)pe_ctx_void;
    *count_out = 0;

    cil_metadata_t meta;
    if (cil_parse_metadata(data, data_size, pe, &meta) != 0) return NULL;
    if (meta.methoddef_rows == 0) return NULL;

    cil_method_t* methods = calloc(meta.methoddef_rows, sizeof(cil_method_t));
    if (!methods) return NULL;

    uint8_t str_size = meta.string_heap_wide ? 4 : 2;
    size_t valid = 0;

    for (uint32_t i = 0; i < meta.methoddef_rows; i++) {
        size_t row_off = meta.methoddef_offset +
                         (size_t)i * meta.methoddef_row_size;
        if (row_off + meta.methoddef_row_size > meta.tables_size) break;

        const uint8_t* row = meta.tables_data + row_off;
        uint32_t rva = read_u32(row);
        /* uint16_t impl_flags = read_u16(row + 4); */
        /* uint16_t flags = read_u16(row + 6); */
        uint32_t name_idx = read_str_index(row + 8, meta.string_heap_wide);

        if (rva == 0) continue; /* abstract/extern method */

        /* Find method body in raw PE data via RVA */
        const uint8_t* body = pe_rva_to_ptr(pe, rva);
        if (!body) continue;
        size_t body_available = data_size - (size_t)(body - data);

        cil_method_t* m = &methods[valid];
        if (cil_decode_method(body, body_available, m) != 0) continue;

        m->rva = rva;
        m->method_def_token = 0x06000001 + i;
        const char* name = strings_lookup(&meta, name_idx);
        m->name = name ? strdup(name) : NULL;

        /* Find parent TypeDef — walk TypeDef.MethodList to find
         * which TypeDef owns this MethodDef row */
        uint8_t method_list_offset_in_typedef =
            4 + str_size + str_size +
            (meta.typedef_row_size - 4 - str_size - str_size -
             ((meta.methoddef_rows < (1u << 16)) ? 2 : 4) -
             ((meta.methoddef_rows < (1u << 16)) ? 2 : 4))
            + ((meta.methoddef_rows < (1u << 16)) ? 2 : 4); /* after FieldList */
        /* Simplified: just scan TypeDefs */
        for (uint32_t td = 0; td < meta.typedef_rows; td++) {
            size_t td_off = meta.typedef_offset +
                            (size_t)td * meta.typedef_row_size;
            if (td_off + meta.typedef_row_size > meta.tables_size) break;
            const uint8_t* td_row = meta.tables_data + td_off;

            /* MethodList is at the end of the row */
            size_t ml_off = meta.typedef_row_size -
                            ((meta.methoddef_rows < (1u << 16)) ? 2 : 4);
            uint32_t method_list;
            if (meta.methoddef_rows < (1u << 16))
                method_list = read_u16(td_row + ml_off);
            else
                method_list = read_u32(td_row + ml_off);

            uint32_t next_method_list;
            if (td + 1 < meta.typedef_rows) {
                size_t next_td_off = meta.typedef_offset +
                                     (size_t)(td + 1) * meta.typedef_row_size;
                const uint8_t* next_row = meta.tables_data + next_td_off;
                if (meta.methoddef_rows < (1u << 16))
                    next_method_list = read_u16(next_row + ml_off);
                else
                    next_method_list = read_u32(next_row + ml_off);
            } else {
                next_method_list = meta.methoddef_rows + 1;
            }

            /* MethodDef rows are 1-based; i is 0-based */
            if ((i + 1) >= method_list && (i + 1) < next_method_list) {
                uint32_t ns_idx = read_str_index(td_row + 4 + str_size,
                                                  meta.string_heap_wide);
                uint32_t tn_idx = read_str_index(td_row + 4,
                                                  meta.string_heap_wide);
                const char* ns = strings_lookup(&meta, ns_idx);
                const char* tn = strings_lookup(&meta, tn_idx);
                m->type_namespace = ns ? strdup(ns) : NULL;
                m->type_name = tn ? strdup(tn) : NULL;
                break;
            }
        }
        (void)method_list_offset_in_typedef;
        valid++;
    }

    *count_out = valid;
    return methods;
}

/* ============================================================================
 * Cleanup and Utility
 * ============================================================================ */

void cil_free_decoded(cil_decoded_t* inst) {
    if (inst && inst->switch_targets) {
        free(inst->switch_targets);
        inst->switch_targets = NULL;
    }
}

void cil_free_method(cil_method_t* method) {
    if (!method) return;
    if (method->instructions) {
        for (size_t i = 0; i < method->instruction_count; i++) {
            cil_free_decoded(&method->instructions[i]);
        }
        free(method->instructions);
        method->instructions = NULL;
    }
    free(method->name);
    free(method->type_namespace);
    free(method->type_name);
    method->name = NULL;
    method->type_namespace = NULL;
    method->type_name = NULL;
}

const char* cil_opcode_name(cil_opcode_t op) {
    if (op >= 0 && op < CIL_OPCODE_COUNT &&
        (size_t)op < sizeof(opcode_names) / sizeof(opcode_names[0]) &&
        opcode_names[op]) {
        return opcode_names[op];
    }
    return "UNKNOWN";
}

const char* cil_operand_type_name(cil_operand_type_t ot) {
    switch (ot) {
    case CIL_OPERAND_NONE:     return "none";
    case CIL_OPERAND_INT8:     return "int8";
    case CIL_OPERAND_UINT8:    return "uint8";
    case CIL_OPERAND_INT32:    return "int32";
    case CIL_OPERAND_INT64:    return "int64";
    case CIL_OPERAND_FLOAT32:  return "float32";
    case CIL_OPERAND_FLOAT64:  return "float64";
    case CIL_OPERAND_TOKEN:    return "token";
    case CIL_OPERAND_STRING:   return "string";
    case CIL_OPERAND_BRANCH8:  return "branch8";
    case CIL_OPERAND_BRANCH32: return "branch32";
    case CIL_OPERAND_SWITCH:   return "switch";
    case CIL_OPERAND_VAR8:     return "var8";
    case CIL_OPERAND_VAR16:    return "var16";
    }
    return "unknown";
}

void cil_print_decoded(const cil_decoded_t* inst, FILE* out) {
    fprintf(out, "IL_%04X: %-16s", inst->offset, cil_opcode_name(inst->opcode));
    switch (inst->operand_type) {
    case CIL_OPERAND_NONE:
        break;
    case CIL_OPERAND_INT8:
        fprintf(out, " %d", inst->operand.i8);
        break;
    case CIL_OPERAND_UINT8:
    case CIL_OPERAND_VAR8:
        fprintf(out, " %u", inst->operand.u8);
        break;
    case CIL_OPERAND_INT32:
        fprintf(out, " 0x%08X", (uint32_t)inst->operand.i32);
        break;
    case CIL_OPERAND_INT64:
        fprintf(out, " 0x%016llX", (unsigned long long)inst->operand.i64);
        break;
    case CIL_OPERAND_FLOAT32:
        fprintf(out, " %g", inst->operand.f32);
        break;
    case CIL_OPERAND_FLOAT64:
        fprintf(out, " %g", inst->operand.f64);
        break;
    case CIL_OPERAND_TOKEN:
    case CIL_OPERAND_STRING:
        fprintf(out, " (0x%08X)", inst->operand.token);
        break;
    case CIL_OPERAND_BRANCH8:
    case CIL_OPERAND_BRANCH32:
        fprintf(out, " IL_%04X",
                inst->offset + inst->length + inst->operand.branch);
        break;
    case CIL_OPERAND_VAR16:
        fprintf(out, " %u", inst->operand.var_index);
        break;
    case CIL_OPERAND_SWITCH:
        fprintf(out, " (%u targets)", inst->switch_count);
        break;
    }
    fprintf(out, "\n");
}
