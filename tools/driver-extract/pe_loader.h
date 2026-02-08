/*
 * PE (Portable Executable) Loader - Stub Header
 *
 * This provides the type definitions needed by driver_extract.h.
 * Full implementation is planned for tools/translator/src/loaders/pe_loader.c
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 */

#ifndef PE_LOADER_H
#define PE_LOADER_H

#include <stdint.h>
#include <stddef.h>

/* PE section */
typedef struct {
    char        name[8];
    uint32_t    virtual_size;
    uint32_t    virtual_address;
    uint32_t    raw_data_size;
    uint32_t    raw_data_offset;
    uint32_t    characteristics;
} pe_section_t;

/* PE import entry */
typedef struct {
    const char* dll_name;
    const char* func_name;
    uint64_t    address;
} pe_import_t;

/* PE export entry */
typedef struct {
    const char* name;
    uint32_t    ordinal;
    uint64_t    address;
} pe_export_t;

/* PE loaded image */
typedef struct {
    uint64_t        image_base;
    uint64_t        entry_point;
    uint16_t        machine;        /* IMAGE_FILE_MACHINE_* */

    pe_section_t*   sections;
    size_t          section_count;

    pe_import_t*    imports;
    size_t          import_count;

    pe_export_t*    exports;
    size_t          export_count;

    const uint8_t*  raw_data;
    size_t          raw_size;
} pe_image_t;

#endif /* PE_LOADER_H */
