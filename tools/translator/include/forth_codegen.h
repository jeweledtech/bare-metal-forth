/* ============================================================================
 * Forth Code Generator — Vocabulary Generation from Semantic Analysis
 * ============================================================================
 *
 * Generates complete Forth vocabulary source files from semantic analysis
 * results. Output follows the catalog header format and vocabulary pattern
 * established in forth/dict/serial-16550.fth.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#ifndef FORTH_CODEGEN_H
#define FORTH_CODEGEN_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

/* Forward declarations — avoid including full headers */
struct sem_result;
struct pe_context;

/* ---- Dependency entry ---- */

typedef struct {
    const char*     vocab_name;     /* e.g. "HARDWARE" */
    const char**    words_used;     /* NULL-terminated, e.g. {"C@-PORT", "C!-PORT", NULL} */
} forth_dependency_t;

/* ---- Codegen options ---- */

typedef struct {
    const char*     vocab_name;     /* e.g. "SERIAL-16550" */
    const char*     category;       /* e.g. "serial" */
    const char*     source_type;    /* "extracted" or "hand-written" */
    const char*     source_binary;  /* original filename or "none" */
    const char*     vendor_id;      /* hex string or "none" */
    const char*     device_id;      /* hex string or "none" */
    const char*     ports_desc;     /* e.g. "0x3F8-0x3FF" or "none" */
    const char*     mmio_desc;      /* e.g. "none" */
    const char*     confidence;     /* "high", "medium", "low" */
    const forth_dependency_t* requires;  /* NULL-terminated array, or NULL */
} forth_codegen_opts_t;

/* ---- Port operation (extracted from UIR analysis) ---- */

typedef struct {
    uint16_t    port_offset;    /* offset from base */
    uint8_t     size;           /* 1, 2, or 4 bytes */
    bool        is_write;       /* true=write, false=read */
    const char* name;           /* register name if known, else NULL */
} forth_port_op_t;

/* ---- Function to generate ---- */

typedef struct {
    const char*         name;           /* Forth word name */
    uint64_t            address;        /* original address */
    forth_port_op_t*    port_ops;       /* port operations in this function */
    size_t              port_op_count;
    bool                is_init;        /* true if this is an init function */
    bool                is_poll;        /* true if contains a polling loop */
} forth_gen_function_t;

/* ---- Codegen input ---- */

typedef struct {
    forth_codegen_opts_t    opts;
    forth_gen_function_t*   functions;
    size_t                  function_count;

    /* Unique port offsets (consolidated from all functions) */
    uint16_t*       port_offsets;
    size_t          port_offset_count;
} forth_codegen_input_t;

/* ---- API ---- */

/* Generate a complete Forth vocabulary source string.
 * Caller must free the returned string. Returns NULL on error. */
char* forth_generate(const forth_codegen_input_t* input);

/* Helper: build a port range description string like "0x3F8-0x3FF".
 * Caller must free. */
char* forth_port_range_desc(uint16_t base_port, size_t register_count);

/* Helper: initialize default options. */
void forth_codegen_opts_init(forth_codegen_opts_t* opts);

#endif /* FORTH_CODEGEN_H */
