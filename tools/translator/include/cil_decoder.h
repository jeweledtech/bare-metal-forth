/* ============================================================================
 * CIL/MSIL Instruction Decoder - Public API
 * ============================================================================
 *
 * Decodes Common Intermediate Language bytecode from .NET managed assemblies.
 * Parses CLR metadata (MethodDef/TypeDef tables) and decodes MSIL method
 * bodies for the driver extraction pipeline.
 *
 * CIL is a stack-based bytecode (similar in spirit to Forth):
 *   ldc.i4 42    → push 42
 *   add          → pop two, push sum
 *   call Token   → call method identified by metadata token
 *
 * The decoder identifies scaffolding patterns (security checks, CAS demands)
 * vs hardware-relevant payload code, enabling .NET DLL stripping.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#ifndef CIL_DECODER_H
#define CIL_DECODER_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* ---- CIL Opcodes ---- */

typedef enum {
    CIL_UNKNOWN = 0,

    /* No-ops */
    CIL_NOP,
    CIL_BREAK,

    /* Argument loads */
    CIL_LDARG_0,
    CIL_LDARG_1,
    CIL_LDARG_2,
    CIL_LDARG_3,
    CIL_LDARG_S,
    CIL_LDARG,

    /* Argument stores */
    CIL_STARG_S,
    CIL_STARG,

    /* Argument address */
    CIL_LDARGA_S,
    CIL_LDARGA,

    /* Local variable loads */
    CIL_LDLOC_0,
    CIL_LDLOC_1,
    CIL_LDLOC_2,
    CIL_LDLOC_3,
    CIL_LDLOC_S,
    CIL_LDLOC,

    /* Local variable stores */
    CIL_STLOC_0,
    CIL_STLOC_1,
    CIL_STLOC_2,
    CIL_STLOC_3,
    CIL_STLOC_S,
    CIL_STLOC,

    /* Local variable address */
    CIL_LDLOCA_S,
    CIL_LDLOCA,

    /* Constants */
    CIL_LDNULL,
    CIL_LDC_I4_M1,
    CIL_LDC_I4_0,
    CIL_LDC_I4_1,
    CIL_LDC_I4_2,
    CIL_LDC_I4_3,
    CIL_LDC_I4_4,
    CIL_LDC_I4_5,
    CIL_LDC_I4_6,
    CIL_LDC_I4_7,
    CIL_LDC_I4_8,
    CIL_LDC_I4_S,
    CIL_LDC_I4,
    CIL_LDC_I8,
    CIL_LDC_R4,
    CIL_LDC_R8,

    /* Stack manipulation */
    CIL_DUP,
    CIL_POP,

    /* Calls */
    CIL_CALL,
    CIL_CALLVIRT,
    CIL_CALLI,
    CIL_RET,
    CIL_JMP,

    /* Unconditional branches */
    CIL_BR_S,
    CIL_BR,

    /* Conditional branches (boolean) */
    CIL_BRFALSE_S,
    CIL_BRTRUE_S,
    CIL_BRFALSE,
    CIL_BRTRUE,

    /* Conditional branches (comparison) — short form */
    CIL_BEQ_S,
    CIL_BGE_S,
    CIL_BGT_S,
    CIL_BLE_S,
    CIL_BLT_S,
    CIL_BNE_UN_S,
    CIL_BGE_UN_S,
    CIL_BGT_UN_S,
    CIL_BLE_UN_S,
    CIL_BLT_UN_S,

    /* Conditional branches (comparison) — long form */
    CIL_BEQ,
    CIL_BGE,
    CIL_BGT,
    CIL_BLE,
    CIL_BLT,
    CIL_BNE_UN,
    CIL_BGE_UN,
    CIL_BGT_UN,
    CIL_BLE_UN,
    CIL_BLT_UN,

    /* Switch */
    CIL_SWITCH,

    /* Indirect loads */
    CIL_LDIND_I1,
    CIL_LDIND_U1,
    CIL_LDIND_I2,
    CIL_LDIND_U2,
    CIL_LDIND_I4,
    CIL_LDIND_U4,
    CIL_LDIND_I8,
    CIL_LDIND_I,
    CIL_LDIND_R4,
    CIL_LDIND_R8,
    CIL_LDIND_REF,

    /* Indirect stores */
    CIL_STIND_REF,
    CIL_STIND_I1,
    CIL_STIND_I2,
    CIL_STIND_I4,
    CIL_STIND_I8,
    CIL_STIND_R4,
    CIL_STIND_R8,
    CIL_STIND_I,

    /* Arithmetic */
    CIL_ADD,
    CIL_SUB,
    CIL_MUL,
    CIL_DIV,
    CIL_DIV_UN,
    CIL_REM,
    CIL_REM_UN,
    CIL_NEG,

    /* Overflow-checking arithmetic */
    CIL_ADD_OVF,
    CIL_ADD_OVF_UN,
    CIL_SUB_OVF,
    CIL_SUB_OVF_UN,
    CIL_MUL_OVF,
    CIL_MUL_OVF_UN,

    /* Logic */
    CIL_AND,
    CIL_OR,
    CIL_XOR,
    CIL_NOT,
    CIL_SHL,
    CIL_SHR,
    CIL_SHR_UN,

    /* Conversions */
    CIL_CONV_I1,
    CIL_CONV_I2,
    CIL_CONV_I4,
    CIL_CONV_I8,
    CIL_CONV_R4,
    CIL_CONV_R8,
    CIL_CONV_U4,
    CIL_CONV_U8,
    CIL_CONV_R_UN,
    CIL_CONV_U2,
    CIL_CONV_U1,
    CIL_CONV_I,
    CIL_CONV_U,
    CIL_CONV_OVF_I1,
    CIL_CONV_OVF_I2,
    CIL_CONV_OVF_I4,
    CIL_CONV_OVF_I8,
    CIL_CONV_OVF_U1,
    CIL_CONV_OVF_U2,
    CIL_CONV_OVF_U4,
    CIL_CONV_OVF_U8,
    CIL_CONV_OVF_I,
    CIL_CONV_OVF_U,
    CIL_CONV_OVF_I1_UN,
    CIL_CONV_OVF_I2_UN,
    CIL_CONV_OVF_I4_UN,
    CIL_CONV_OVF_I8_UN,
    CIL_CONV_OVF_U1_UN,
    CIL_CONV_OVF_U2_UN,
    CIL_CONV_OVF_U4_UN,
    CIL_CONV_OVF_U8_UN,
    CIL_CONV_OVF_I_UN,
    CIL_CONV_OVF_U_UN,

    /* Comparison */
    CIL_CEQ,
    CIL_CGT,
    CIL_CGT_UN,
    CIL_CLT,
    CIL_CLT_UN,

    /* Object model */
    CIL_LDSTR,
    CIL_NEWOBJ,
    CIL_CASTCLASS,
    CIL_ISINST,
    CIL_UNBOX,
    CIL_UNBOX_ANY,
    CIL_BOX,
    CIL_LDTOKEN,

    /* Field access */
    CIL_LDFLD,
    CIL_LDFLDA,
    CIL_STFLD,
    CIL_LDSFLD,
    CIL_LDSFLDA,
    CIL_STSFLD,

    /* Method references */
    CIL_LDFTN,
    CIL_LDVIRTFTN,

    /* Array operations */
    CIL_NEWARR,
    CIL_LDLEN,
    CIL_LDELEMA,
    CIL_LDELEM_I1,
    CIL_LDELEM_U1,
    CIL_LDELEM_I2,
    CIL_LDELEM_U2,
    CIL_LDELEM_I4,
    CIL_LDELEM_U4,
    CIL_LDELEM_I8,
    CIL_LDELEM_I,
    CIL_LDELEM_R4,
    CIL_LDELEM_R8,
    CIL_LDELEM_REF,
    CIL_LDELEM,
    CIL_STELEM_I,
    CIL_STELEM_I1,
    CIL_STELEM_I2,
    CIL_STELEM_I4,
    CIL_STELEM_I8,
    CIL_STELEM_R4,
    CIL_STELEM_R8,
    CIL_STELEM_REF,
    CIL_STELEM,

    /* Object copy/init */
    CIL_CPOBJ,
    CIL_LDOBJ,
    CIL_STOBJ,
    CIL_CPBLK,
    CIL_INITBLK,
    CIL_INITOBJ,
    CIL_SIZEOF,

    /* Exception handling */
    CIL_THROW,
    CIL_RETHROW,
    CIL_LEAVE,
    CIL_LEAVE_S,
    CIL_ENDFINALLY,
    CIL_ENDFILTER,

    /* Prefix instructions */
    CIL_VOLATILE,
    CIL_UNALIGNED,
    CIL_TAIL,
    CIL_CONSTRAINED,
    CIL_READONLY,

    /* Miscellaneous */
    CIL_LOCALLOC,
    CIL_ARGLIST,
    CIL_REFANYTYPE,
    CIL_REFANYVAL,
    CIL_MKREFANY,
    CIL_CKFINITE,

    CIL_OPCODE_COUNT
} cil_opcode_t;

/* ---- CIL Operand Types ---- */

typedef enum {
    CIL_OPERAND_NONE = 0,
    CIL_OPERAND_INT8,       /* sbyte immediate (ldc.i4.s) */
    CIL_OPERAND_UINT8,      /* unsigned byte (stloc.s, ldarg.s) */
    CIL_OPERAND_INT32,      /* int32 immediate */
    CIL_OPERAND_INT64,      /* int64 immediate (ldc.i8) */
    CIL_OPERAND_FLOAT32,    /* float32 immediate */
    CIL_OPERAND_FLOAT64,    /* float64 immediate */
    CIL_OPERAND_TOKEN,      /* metadata token (4 bytes, type in bits 24-31) */
    CIL_OPERAND_STRING,     /* user string token (#US heap index) */
    CIL_OPERAND_BRANCH8,    /* sbyte relative branch offset */
    CIL_OPERAND_BRANCH32,   /* int32 relative branch offset */
    CIL_OPERAND_SWITCH,     /* uint32 count + count*int32 offsets */
    CIL_OPERAND_VAR8,       /* uint8 local/arg index (short form) */
    CIL_OPERAND_VAR16,      /* uint16 local/arg index (long form) */
} cil_operand_type_t;

/* ---- Decoded CIL Instruction ---- */

typedef struct {
    uint32_t            offset;         /* byte offset within method body */
    uint8_t             length;         /* total bytes consumed */
    cil_opcode_t        opcode;
    cil_operand_type_t  operand_type;

    /* Operand value */
    union {
        int8_t      i8;
        uint8_t     u8;
        int32_t     i32;
        int64_t     i64;
        float       f32;
        double      f64;
        uint32_t    token;      /* metadata token */
        int32_t     branch;     /* branch target offset (relative to end of insn) */
        uint16_t    var_index;  /* local/argument index */
    } operand;

    /* Switch table (only valid when operand_type == CIL_OPERAND_SWITCH) */
    int32_t*    switch_targets;     /* heap-allocated; caller must free */
    uint32_t    switch_count;       /* number of entries */

    /* CIL type token — carries type info for ldind/stind/conv instructions.
     * Useful for Forth emitter to determine cell width (int32 vs int64). */
    uint32_t    type_token;
} cil_decoded_t;

/* ---- CIL Method ---- */

typedef struct {
    uint32_t    rva;                /* RVA of the method header */
    uint32_t    code_rva;           /* RVA of first CIL instruction */
    uint32_t    code_size;          /* byte length of CIL body */
    uint16_t    max_stack;
    uint32_t    local_var_sig_token;
    uint32_t    flags;

    cil_decoded_t*  instructions;   /* heap-allocated array */
    size_t          instruction_count;

    /* Source metadata — filled by cil_decode_pe_methods() */
    uint32_t    method_def_token;   /* 0x06xxxxxx */
    char*       name;               /* strdup'd from #Strings heap */
    char*       type_namespace;     /* strdup'd from parent TypeDef */
    char*       type_name;          /* strdup'd from parent TypeDef */
} cil_method_t;

#define CIL_METHOD_TINY         0x0002
#define CIL_METHOD_FAT          0x0003
#define CIL_METHOD_INIT_LOCALS  0x0010
#define CIL_METHOD_MORE_SECTS   0x0008

/* ---- Decoder Context ---- */

typedef struct {
    const uint8_t*  code;       /* pointer to CIL bytecode */
    size_t          code_size;  /* length of bytecode */
    size_t          offset;     /* current read position */
} cil_decoder_t;

/* ---- CLR Metadata (internal, but exposed for testing) ---- */

typedef struct {
    const uint8_t*  strings_heap;
    size_t          strings_size;
    const uint8_t*  us_heap;
    size_t          us_size;
    const uint8_t*  blob_heap;
    size_t          blob_size;
    const uint8_t*  tables_data;
    size_t          tables_size;

    uint32_t    typedef_rows;
    uint32_t    methoddef_rows;
    uint32_t    memberref_rows;
    uint32_t    typeref_rows;

    uint8_t     typedef_row_size;
    uint8_t     methoddef_row_size;
    uint8_t     memberref_row_size;
    uint8_t     typeref_row_size;

    size_t      typedef_offset;
    size_t      methoddef_offset;
    size_t      memberref_offset;
    size_t      typeref_offset;

    bool        string_heap_wide;   /* 4-byte indices if true */
    bool        guid_heap_wide;
    bool        blob_heap_wide;
} cil_metadata_t;

/* ---- API ---- */

/* Initialize decoder context for a CIL method body */
void cil_decoder_init(cil_decoder_t* dec,
                      const uint8_t* code, size_t code_size);

/* Decode one CIL instruction at current offset.
 * Returns bytes consumed (>=1), 0 on end, -1 on error. */
int cil_decode_one(cil_decoder_t* dec, cil_decoded_t* out);

/* Decode a complete method body (header + instructions).
 * code points to the method header byte.
 * Returns 0 on success, -1 on error. */
int cil_decode_method(const uint8_t* code, size_t available,
                      cil_method_t* out);

/* Parse CLR metadata from a PE context.
 * data = raw PE file buffer, metadata_rva/size from pe_context_t.
 * Returns 0 on success, -1 on error. */
int cil_parse_metadata(const uint8_t* data, size_t data_size,
                       const void* pe_ctx,
                       cil_metadata_t* out);

/* Decode all methods from a PE with CLR metadata.
 * Returns heap-allocated array of cil_method_t; caller must free each
 * with cil_free_method() and then free the array.
 * Sets *count_out to the number of methods. */
cil_method_t* cil_decode_pe_methods(const uint8_t* data, size_t data_size,
                                     const void* pe_ctx,
                                     size_t* count_out);

/* Free resources owned by a cil_method_t */
void cil_free_method(cil_method_t* method);

/* Free a single decoded instruction's heap data (switch_targets) */
void cil_free_decoded(cil_decoded_t* inst);

/* Print a decoded CIL instruction */
void cil_print_decoded(const cil_decoded_t* inst, FILE* out);

/* Get opcode name string */
const char* cil_opcode_name(cil_opcode_t op);

/* Get operand type name string */
const char* cil_operand_type_name(cil_operand_type_t ot);

/* Resolve a metadata token to a type namespace string.
 * Returns pointer into strings_heap (not allocated). NULL if unresolvable. */
const char* cil_resolve_type_namespace(const cil_metadata_t* meta,
                                       uint32_t token);

/* Resolve a metadata token to a type name string. */
const char* cil_resolve_type_name(const cil_metadata_t* meta,
                                   uint32_t token);

#endif /* CIL_DECODER_H */
