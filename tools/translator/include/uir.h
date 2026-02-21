/* ============================================================================
 * UIR — Universal Intermediate Representation
 * ============================================================================
 *
 * Platform-independent IR for the driver extraction pipeline.
 * x86 decoded instructions are "lifted" to UIR, which captures the semantic
 * meaning of each operation without architecture-specific encoding details.
 *
 * Key design: IN/OUT instructions lift to UIR_PORT_IN/UIR_PORT_OUT with the
 * port number preserved. This is the most important instruction mapping for
 * driver extraction — it's the signal that says "this code talks to hardware."
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#ifndef UIR_H
#define UIR_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* ---- UIR Opcodes ---- */

typedef enum {
    UIR_NOP = 0,

    /* Data movement */
    UIR_MOV,            /* dest = src */
    UIR_LOAD,           /* dest = [addr] */
    UIR_STORE,          /* [addr] = src */
    UIR_PUSH,
    UIR_POP,
    UIR_LEA,            /* dest = addr (no dereference) */
    UIR_MOVZX,          /* zero-extend */
    UIR_MOVSX,          /* sign-extend */

    /* Arithmetic */
    UIR_ADD,
    UIR_SUB,
    UIR_MUL,
    UIR_IMUL,
    UIR_DIV,
    UIR_IDIV,
    UIR_NEG,
    UIR_INC,
    UIR_DEC,

    /* Logic */
    UIR_AND,
    UIR_OR,
    UIR_XOR,
    UIR_NOT,
    UIR_SHL,
    UIR_SHR,
    UIR_SAR,

    /* Comparison */
    UIR_CMP,
    UIR_TEST,

    /* Control flow */
    UIR_JMP,            /* unconditional jump */
    UIR_JCC,            /* conditional jump (cc in aux field) */
    UIR_CALL,           /* function call */
    UIR_RET,            /* return */

    /* Port I/O — the golden signal for driver extraction */
    UIR_PORT_IN,        /* dest = port_read(port, size) */
    UIR_PORT_OUT,       /* port_write(port, value, size) */

    /* System */
    UIR_CLI,
    UIR_STI,
    UIR_HLT,

    /* Sentinel */
    UIR_OPCODE_COUNT
} uir_opcode_t;

/* ---- UIR Operand ---- */

typedef enum {
    UIR_OPERAND_NONE = 0,
    UIR_OPERAND_REG,        /* abstract register (maps from x86 reg) */
    UIR_OPERAND_IMM,        /* immediate constant */
    UIR_OPERAND_MEM,        /* memory reference: [base + index*scale + disp] */
    UIR_OPERAND_ADDR,       /* absolute address (for call/jump targets) */
} uir_operand_type_t;

typedef struct {
    uir_operand_type_t type;
    uint8_t         size;       /* operand size in bytes (1, 2, 4) */
    int8_t          reg;        /* register index (if REG or MEM base) */
    int8_t          index;      /* index register (MEM only, -1 = none) */
    uint8_t         scale;      /* scale factor (MEM only) */
    int32_t         disp;       /* displacement (MEM) or port number (PORT_IN/OUT) */
    int64_t         imm;        /* immediate value or target address */
} uir_operand_t;

/* ---- UIR Instruction ---- */

typedef struct {
    uir_opcode_t    opcode;
    uir_operand_t   dest;       /* destination operand */
    uir_operand_t   src1;       /* first source operand */
    uir_operand_t   src2;       /* second source (rarely used) */
    uint8_t         size;       /* operation size in bytes */
    uint64_t        original_address;   /* address in original binary */
    uint8_t         cc;         /* condition code for JCC (x86_cc_t) */
} uir_instruction_t;

/* ---- UIR Basic Block ---- */

typedef struct uir_block {
    uint64_t            address;        /* start address of this block */
    uir_instruction_t*  instructions;   /* array of UIR instructions */
    size_t              count;          /* number of instructions */
    size_t              capacity;       /* allocated capacity */

    /* Control flow edges (indices into the block array, -1 = none) */
    int                 fall_through;   /* index of fall-through successor */
    int                 branch_target;  /* index of branch target (for JCC/JMP) */

    bool                is_entry;       /* true if function entry point */
} uir_block_t;

/* ---- UIR Function (collection of basic blocks) ---- */

typedef struct {
    uir_block_t*    blocks;         /* array of basic blocks */
    size_t          block_count;
    uint64_t        entry_address;  /* function start address */

    /* Port I/O summary (populated during lifting) */
    uint16_t*       ports_read;     /* ports read from (IN) */
    size_t          ports_read_count;
    uint16_t*       ports_written;  /* ports written to (OUT) */
    size_t          ports_written_count;
    bool            has_port_io;    /* quick check: any IN/OUT? */
    bool            uses_dx_port;   /* true if port comes from DX register */
} uir_function_t;

/* ---- API ---- */

/* Lift a sequence of x86 decoded instructions into UIR basic blocks.
 * The x86_decoded_t type is forward-declared here; include x86_decoder.h
 * for the full definition. Returns NULL on error. */
struct x86_decoded;  /* forward declaration */
typedef struct {
    uint64_t    address;
    uint8_t     length;
    int         instruction;    /* x86_instruction_t */
    uint8_t     operand_count;
    struct {
        int         type;       /* x86_operand_type_t */
        uint8_t     size;
        int8_t      reg;
        int8_t      base;
        int8_t      index;
        uint8_t     scale;
        int32_t     disp;
        int64_t     imm;
    } operands[4];
    uint8_t     prefixes;
    int         cc;             /* x86_cc_t */
} uir_x86_input_t;

/* Lift x86 instructions to a UIR function. Caller must free with uir_free_function(). */
uir_function_t* uir_lift_function(const uir_x86_input_t* insts, size_t count,
                                   uint64_t entry_address);

/* Free a UIR function and all its blocks. */
void uir_free_function(uir_function_t* func);

/* Print a UIR basic block (for debugging). */
void uir_print_block(const uir_block_t* block, FILE* out);

/* Print all blocks in a function. */
void uir_print_function(const uir_function_t* func, FILE* out);

/* Get opcode name string. */
const char* uir_opcode_name(uir_opcode_t op);

#endif /* UIR_H */
