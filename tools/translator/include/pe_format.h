/* ============================================================================
 * PE/COFF Structure Definitions
 * ============================================================================
 *
 * Raw PE/COFF structure definitions matching the on-disk format byte-for-byte.
 * All fields are little-endian as specified by the PE format.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#ifndef PE_FORMAT_H
#define PE_FORMAT_H

#include <stdint.h>

/* DOS Header (64 bytes) */
typedef struct {
    uint16_t e_magic;       /* 0x5A4D = "MZ" */
    uint16_t e_cblp;
    uint16_t e_cp;
    uint16_t e_crlc;
    uint16_t e_cparhdr;
    uint16_t e_minalloc;
    uint16_t e_maxalloc;
    uint16_t e_ss;
    uint16_t e_sp;
    uint16_t e_csum;
    uint16_t e_ip;
    uint16_t e_cs;
    uint16_t e_lfarlc;
    uint16_t e_ovno;
    uint16_t e_res[4];
    uint16_t e_oemid;
    uint16_t e_oeminfo;
    uint16_t e_res2[10];
    uint32_t e_lfanew;      /* Offset to PE signature */
} dos_header_t;

#define DOS_MAGIC 0x5A4D

/* COFF File Header (20 bytes) */
typedef struct {
    uint16_t machine;
    uint16_t number_of_sections;
    uint32_t time_date_stamp;
    uint32_t pointer_to_symbol_table;
    uint32_t number_of_symbols;
    uint16_t size_of_optional_header;
    uint16_t characteristics;
} coff_header_t;

#define COFF_MACHINE_I386   0x014C
#define COFF_MACHINE_AMD64  0x8664

/* Data Directory Entry */
typedef struct {
    uint32_t virtual_address;
    uint32_t size;
} data_directory_t;

#define DATA_DIR_EXPORT     0
#define DATA_DIR_IMPORT     1
#define DATA_DIR_RESOURCE   2
#define DATA_DIR_EXCEPTION  3
#define DATA_DIR_SECURITY   4
#define DATA_DIR_BASERELOC  5
#define DATA_DIR_DEBUG      6

/* PE32 Optional Header */
typedef struct {
    uint16_t magic;             /* 0x10B = PE32, 0x20B = PE32+ */
    uint8_t  major_linker_version;
    uint8_t  minor_linker_version;
    uint32_t size_of_code;
    uint32_t size_of_initialized_data;
    uint32_t size_of_uninitialized_data;
    uint32_t address_of_entry_point;
    uint32_t base_of_code;
    uint32_t base_of_data;      /* PE32 only */
    uint32_t image_base;
    uint32_t section_alignment;
    uint32_t file_alignment;
    uint16_t major_os_version;
    uint16_t minor_os_version;
    uint16_t major_image_version;
    uint16_t minor_image_version;
    uint16_t major_subsystem_version;
    uint16_t minor_subsystem_version;
    uint32_t win32_version_value;
    uint32_t size_of_image;
    uint32_t size_of_headers;
    uint32_t checksum;
    uint16_t subsystem;
    uint16_t dll_characteristics;
    uint32_t size_of_stack_reserve;
    uint32_t size_of_stack_commit;
    uint32_t size_of_heap_reserve;
    uint32_t size_of_heap_commit;
    uint32_t loader_flags;
    uint32_t number_of_rva_and_sizes;
    /* data_directory_t entries follow */
} pe32_optional_header_t;

/* PE32+ Optional Header (64-bit) */
typedef struct {
    uint16_t magic;             /* 0x20B */
    uint8_t  major_linker_version;
    uint8_t  minor_linker_version;
    uint32_t size_of_code;
    uint32_t size_of_initialized_data;
    uint32_t size_of_uninitialized_data;
    uint32_t address_of_entry_point;
    uint32_t base_of_code;
    /* No base_of_data in PE32+ */
    uint64_t image_base;
    uint32_t section_alignment;
    uint32_t file_alignment;
    uint16_t major_os_version;
    uint16_t minor_os_version;
    uint16_t major_image_version;
    uint16_t minor_image_version;
    uint16_t major_subsystem_version;
    uint16_t minor_subsystem_version;
    uint32_t win32_version_value;
    uint32_t size_of_image;
    uint32_t size_of_headers;
    uint32_t checksum;
    uint16_t subsystem;
    uint16_t dll_characteristics;
    uint64_t size_of_stack_reserve;
    uint64_t size_of_stack_commit;
    uint64_t size_of_heap_reserve;
    uint64_t size_of_heap_commit;
    uint32_t loader_flags;
    uint32_t number_of_rva_and_sizes;
    /* data_directory_t entries follow */
} pe32plus_optional_header_t;

#define PE_OPT_MAGIC_PE32      0x10B
#define PE_OPT_MAGIC_PE32PLUS  0x20B

/* Section Header (40 bytes) */
typedef struct {
    char     name[8];
    uint32_t virtual_size;
    uint32_t virtual_address;
    uint32_t size_of_raw_data;
    uint32_t pointer_to_raw_data;
    uint32_t pointer_to_relocations;
    uint32_t pointer_to_linenumbers;
    uint16_t number_of_relocations;
    uint16_t number_of_linenumbers;
    uint32_t characteristics;
} section_header_t;

#define SECTION_CNT_CODE                0x00000020
#define SECTION_CNT_INITIALIZED_DATA    0x00000040
#define SECTION_MEM_EXECUTE             0x20000000
#define SECTION_MEM_READ                0x40000000
#define SECTION_MEM_WRITE               0x80000000

/* Import Directory Entry */
typedef struct {
    uint32_t import_lookup_table_rva;   /* aka OriginalFirstThunk */
    uint32_t time_date_stamp;
    uint32_t forwarder_chain;
    uint32_t name_rva;                  /* RVA to DLL name string */
    uint32_t import_address_table_rva;  /* aka FirstThunk */
} import_descriptor_t;

/* Import Lookup Table Entry (PE32) */
#define IMPORT_ORDINAL_FLAG_32  0x80000000
#define IMPORT_ORDINAL_FLAG_64  0x8000000000000000ULL

/* Hint/Name Entry */
typedef struct {
    uint16_t hint;
    /* char name[] follows - null-terminated */
} hint_name_t;

/* Export Directory */
typedef struct {
    uint32_t characteristics;
    uint32_t time_date_stamp;
    uint16_t major_version;
    uint16_t minor_version;
    uint32_t name_rva;
    uint32_t ordinal_base;
    uint32_t number_of_functions;
    uint32_t number_of_names;
    uint32_t address_of_functions_rva;
    uint32_t address_of_names_rva;
    uint32_t address_of_name_ordinals_rva;
} export_directory_t;

#define PE_SIGNATURE 0x00004550  /* "PE\0\0" */

#endif /* PE_FORMAT_H */
