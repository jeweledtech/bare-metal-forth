/* ============================================================================
 * PE Loader - Public API
 * ============================================================================
 *
 * Parses PE (Portable Executable) files and provides access to headers,
 * sections, imports, and exports.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#ifndef PE_LOADER_H
#define PE_LOADER_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* Section info */
typedef struct {
    char        name[9];        /* null-terminated */
    uint32_t    virtual_size;
    uint32_t    virtual_address;
    uint32_t    raw_data_size;
    uint32_t    raw_data_offset;
    uint32_t    characteristics;
} pe_section_t;

/* Import entry */
typedef struct {
    char*       dll_name;       /* allocated string */
    char*       func_name;      /* allocated string (NULL if by ordinal) */
    uint16_t    ordinal;
    uint32_t    iat_rva;        /* RVA in Import Address Table */
} pe_import_t;

/* Export entry */
typedef struct {
    char*       name;           /* allocated string */
    uint32_t    ordinal;
    uint32_t    rva;            /* RVA of exported function */
} pe_export_t;

/* PE context - result of loading */
typedef struct {
    /* Raw file data (caller-owned, must outlive context) */
    const uint8_t*  data;
    size_t          data_size;

    /* PE headers */
    uint16_t    machine;        /* COFF_MACHINE_I386 or COFF_MACHINE_AMD64 */
    bool        is_64bit;       /* PE32+ flag */
    uint64_t    image_base;
    uint32_t    entry_point_rva;

    /* Sections */
    pe_section_t*   sections;
    size_t          section_count;

    /* Convenience: code section */
    const uint8_t*  text_data;      /* pointer into raw data */
    size_t          text_size;
    uint32_t        text_rva;

    /* Imports */
    pe_import_t*    imports;
    size_t          import_count;

    /* Exports */
    pe_export_t*    exports;
    size_t          export_count;
} pe_context_t;

/* Load PE from memory buffer. Returns 0 on success, -1 on error. */
int pe_load(pe_context_t* ctx, const uint8_t* data, size_t size);

/* Free all allocated memory in context. */
void pe_cleanup(pe_context_t* ctx);

/* Convert RVA to pointer within raw data. Returns NULL if out of bounds. */
const uint8_t* pe_rva_to_ptr(const pe_context_t* ctx, uint32_t rva);

/* Find a section by name (e.g. ".text"). Returns NULL if not found. */
const pe_section_t* pe_find_section(const pe_context_t* ctx, const char* name);

/* Find an import by function name. Returns NULL if not found. */
const pe_import_t* pe_find_import(const pe_context_t* ctx, const char* func_name);

/* Print PE summary to FILE (for debugging). */
void pe_print_info(const pe_context_t* ctx, FILE* out);

#endif /* PE_LOADER_H */
