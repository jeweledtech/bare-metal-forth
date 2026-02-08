/*
 * Universal Intermediate Representation - Stub Header
 *
 * This provides the type definitions needed by driver_extract.h.
 * Full implementation lives in tools/translator/src/ir/uir.c
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 */

#ifndef UIR_H
#define UIR_H

#include <stdint.h>
#include <stddef.h>

/* UIR instruction opcodes */
typedef enum {
    UIR_NOP = 0,
    UIR_LOAD,
    UIR_STORE,
    UIR_ADD,
    UIR_SUB,
    UIR_MUL,
    UIR_DIV,
    UIR_MOD,
    UIR_AND,
    UIR_OR,
    UIR_XOR,
    UIR_SHL,
    UIR_SHR,
    UIR_CALL,
    UIR_RET,
    UIR_JMP,
    UIR_JZ,
    UIR_JNZ,
    UIR_PORT_IN,
    UIR_PORT_OUT,
    UIR_MMIO_READ,
    UIR_MMIO_WRITE,
} uir_opcode_t;

/* UIR instruction */
typedef struct {
    uir_opcode_t    opcode;
    uint64_t        operand1;
    uint64_t        operand2;
    uint64_t        result;
    uint8_t         size;       /* operand size in bytes */
} uir_instruction_t;

/* UIR basic block */
typedef struct uir_block {
    uint64_t            address;        /* Original address */
    uir_instruction_t*  instructions;
    size_t              instruction_count;
    struct uir_block*   next;           /* Fall-through */
    struct uir_block*   branch;         /* Branch target */
} uir_block_t;

#endif /* UIR_H */
