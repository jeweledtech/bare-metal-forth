/*
 * x86 Instruction Decoder - Stub Header
 *
 * This provides the type definitions needed by driver_extract.h.
 * Full implementation is planned for tools/translator/src/decoders/x86_decoder.c
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 */

#ifndef X86_DECODER_H
#define X86_DECODER_H

#include <stdint.h>
#include <stddef.h>

/* Decoder mode */
typedef enum {
    X86_MODE_16 = 16,
    X86_MODE_32 = 32,
    X86_MODE_64 = 64,
} x86_mode_t;

/* x86 instruction IDs (subset relevant to driver extraction) */
typedef enum {
    X86_INS_UNKNOWN = 0,
    X86_INS_IN,
    X86_INS_OUT,
    X86_INS_INS,
    X86_INS_OUTS,
    X86_INS_CLI,
    X86_INS_STI,
    X86_INS_HLT,
    X86_INS_MOV,
    X86_INS_CALL,
    X86_INS_RET,
    X86_INS_JMP,
    X86_INS_JCC,
    X86_INS_PUSH,
    X86_INS_POP,
    /* ... more to be added */
} x86_instruction_t;

/* Decoded instruction */
typedef struct {
    uint64_t            address;
    uint8_t             length;
    x86_instruction_t   instruction;
    uint8_t             operand_count;
    uint64_t            operands[4];
    uint8_t             operand_sizes[4];
} x86_decoded_t;

/* Decoder context */
typedef struct {
    x86_mode_t          mode;
    const uint8_t*      code;
    size_t              code_size;
    uint64_t            base_address;
    size_t              offset;
} x86_decoder_t;

/* Initialize decoder */
static inline void x86_decoder_init(x86_decoder_t* dec, x86_mode_t mode) {
    dec->mode = mode;
    dec->code = NULL;
    dec->code_size = 0;
    dec->base_address = 0;
    dec->offset = 0;
}

#endif /* X86_DECODER_H */
