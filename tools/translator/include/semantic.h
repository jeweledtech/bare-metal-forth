/* ============================================================================
 * Semantic Analyzer — Function Classification for Driver Extraction
 * ============================================================================
 *
 * Walks UIR basic blocks and uses the PE import table to classify functions
 * as hardware-relevant or Windows scaffolding. Functions containing port I/O
 * instructions or calls to hardware-access APIs (READ_PORT_UCHAR, etc.)
 * are kept. Functions that only use scaffolding APIs (IRP handling, PnP,
 * power management) are filtered out.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#ifndef SEMANTIC_H
#define SEMANTIC_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* Category enum from driver_extract.h — duplicated here to avoid
 * hard dependency on the driver-extract directory. */
typedef enum {
    SEM_CAT_UNKNOWN     = 0,

    /* Hardware Access — KEEP */
    SEM_CAT_PORT_IO     = 0x10,
    SEM_CAT_MMIO        = 0x11,
    SEM_CAT_DMA         = 0x12,
    SEM_CAT_INTERRUPT   = 0x13,
    SEM_CAT_TIMING      = 0x14,
    SEM_CAT_PCI_CONFIG  = 0x15,

    /* Windows Scaffolding — FILTER */
    SEM_CAT_IRP         = 0x80,
    SEM_CAT_PNP         = 0x81,
    SEM_CAT_POWER       = 0x82,
    SEM_CAT_WMI         = 0x83,
    SEM_CAT_REGISTRY    = 0x84,
    SEM_CAT_MEMORY_MGR  = 0x85,
    SEM_CAT_SYNC        = 0x86,
    SEM_CAT_STRING      = 0x87,

    /* Hybrid */
    SEM_CAT_OBJECT      = 0xC0,
    SEM_CAT_IO_MGR      = 0xC1,
} sem_category_t;

/* ---- API recognition entry ---- */

typedef struct {
    const char*     name;           /* Windows API function name */
    sem_category_t  category;
    const char*     forth_equiv;    /* Forth equivalent (NULL if filtered) */
    const char*     description;
} sem_api_entry_t;

/* The built-in API table (defined in semantic.c) */
extern const sem_api_entry_t SEM_API_TABLE[];
extern const size_t SEM_API_TABLE_SIZE;

/* ---- Classified import ---- */

typedef struct {
    char*           dll_name;
    char*           func_name;
    sem_category_t  category;
    const char*     forth_equiv;    /* points into SEM_API_TABLE, not allocated */
    uint32_t        iat_rva;
} sem_import_t;

/* ---- Analyzed function ---- */

typedef struct {
    uint64_t        address;
    char*           name;           /* from exports, or "func_XXXX" */
    sem_category_t  primary_category;
    bool            has_port_io;
    bool            has_mmio;
    bool            has_timing;
    bool            has_pci;
    bool            has_scaffolding;
    bool            is_hardware;    /* true if any hw signal found */
    size_t          hw_call_count;
    size_t          scaf_call_count;

    /* Ports used by this function */
    uint16_t*       ports;
    size_t          port_count;
} sem_function_t;

/* ---- Analysis result ---- */

typedef struct {
    /* Classified imports */
    sem_import_t*   imports;
    size_t          import_count;

    /* Analyzed functions */
    sem_function_t* functions;
    size_t          function_count;

    /* Summary */
    size_t          hw_function_count;
    size_t          filtered_count;
} sem_result_t;

/* ---- API ---- */

/* Classify a single import name against the API table.
 * Returns the category and sets *forth_equiv if there's a Forth equivalent. */
sem_category_t sem_classify_import(const char* func_name,
                                    const char** forth_equiv);

/* Check if a category is hardware-relevant (< 0x80) */
static inline bool sem_is_hardware(sem_category_t cat) {
    return cat >= SEM_CAT_PORT_IO && cat <= SEM_CAT_PCI_CONFIG;
}

/* Check if a category is scaffolding (>= 0x80) */
static inline bool sem_is_scaffolding(sem_category_t cat) {
    return cat >= SEM_CAT_IRP && cat <= SEM_CAT_STRING;
}

/* Classify imports from a PE context.
 * pe_imports: array of {dll_name, func_name, iat_rva} from PE loader.
 * Fills result->imports. */
typedef struct {
    const char* dll_name;
    const char* func_name;
    uint32_t    iat_rva;
} sem_pe_import_t;

int sem_classify_imports(const sem_pe_import_t* pe_imports, size_t pe_import_count,
                          sem_result_t* result);

/* Analyze UIR functions and classify them.
 * uir_functions: array of uir_function_t* from the lifter.
 * Requires imports to be classified first (result->imports populated). */
struct uir_function;  /* forward declaration */

typedef struct {
    void*       func;           /* uir_function_t* */
    uint64_t    entry_address;
    const char* name;           /* export name or NULL */
    bool        has_port_io;
    uint16_t*   ports_read;
    size_t      ports_read_count;
    uint16_t*   ports_written;
    size_t      ports_written_count;
} sem_uir_input_t;

int sem_analyze_functions(const sem_uir_input_t* uir_funcs, size_t uir_func_count,
                           sem_result_t* result);

/* Print analysis report. */
void sem_print_report(const sem_result_t* result, FILE* out);

/* Free all allocated memory in result. */
void sem_cleanup(sem_result_t* result);

#endif /* SEMANTIC_H */
