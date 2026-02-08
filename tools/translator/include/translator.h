/* ============================================================================
 * Universal Binary Translator - Public API
 * ============================================================================
 *
 * This header defines the public interface to the translator.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#ifndef TRANSLATOR_H
#define TRANSLATOR_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

/* Version */
#define TRANSLATOR_VERSION_MAJOR 0
#define TRANSLATOR_VERSION_MINOR 1
#define TRANSLATOR_VERSION_PATCH 0

/* ============================================================================
 * Types
 * ============================================================================ */

/* Target architecture for code generation */
typedef enum {
    TARGET_DISASM,      /* Human-readable disassembly */
    TARGET_UIR,         /* Universal Intermediate Representation */
    TARGET_FORTH,       /* Forth source code */
    TARGET_C,           /* C source code */
    TARGET_X64,         /* Native x86-64 */
    TARGET_ARM64,       /* Native ARM64 */
    TARGET_RISCV64,     /* Native RISC-V 64-bit */
} target_t;

/* Source architecture */
typedef enum {
    ARCH_UNKNOWN,
    ARCH_X86,
    ARCH_X86_64,
    ARCH_ARM64,
    ARCH_RISCV32,
    ARCH_RISCV64,
} arch_t;

/* Binary format */
typedef enum {
    FORMAT_UNKNOWN,
    FORMAT_ELF,
    FORMAT_PE,
    FORMAT_RAW,
} format_t;

/* Translation options */
typedef struct {
    target_t target;            /* Output target */
    arch_t source_arch;         /* Source architecture (for raw binaries) */
    uint64_t base_address;      /* Base address (for raw binaries) */
    int optimize_level;         /* Optimization level (0-3) */
    bool semantic_analysis;     /* Enable semantic analysis */
    bool verbose;               /* Verbose output */
    bool forth83_division;      /* Use Forth-83 floored division */
    const char* function_name;  /* Specific function to extract (NULL = all) */
} translate_options_t;

/* Result structure */
typedef struct {
    bool success;
    char* output;               /* Generated output (caller must free) */
    size_t output_size;
    char* error_message;        /* Error message if !success */
} translate_result_t;

/* ============================================================================
 * API Functions
 * ============================================================================ */

/* Initialize default options */
void translate_options_init(translate_options_t* opts);

/* Translate a binary file */
translate_result_t translate_file(const char* filename, 
                                   const translate_options_t* opts);

/* Translate from memory buffer */
translate_result_t translate_buffer(const uint8_t* data, size_t size,
                                     const translate_options_t* opts);

/* Free result resources */
void translate_result_free(translate_result_t* result);

/* Get version string */
const char* translator_version(void);

#endif /* TRANSLATOR_H */
