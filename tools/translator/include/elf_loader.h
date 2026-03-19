/* ============================================================================
 * ELF Loader — Parses ELF32 and ELF64 binaries
 * ============================================================================
 *
 * Loads ELF executables and shared libraries (.so) into an elf_context_t for
 * analysis by the translator pipeline.  Supports both 32-bit and 64-bit ELF,
 * little-endian x86/x86-64 only.
 *
 * Structs are defined manually (no #include <elf.h>) to avoid host system
 * dependencies.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#ifndef ELF_LOADER_H
#define ELF_LOADER_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>

/* ELF machine types we handle */
#define EM_386      3
#define EM_X86_64   62

/* ELF file types */
#define ET_REL      1   /* Relocatable object */
#define ET_EXEC     2   /* Executable */
#define ET_DYN      3   /* Shared library */

/* Section types */
#define SHT_NULL        0
#define SHT_PROGBITS    1
#define SHT_SYMTAB      2
#define SHT_STRTAB      3
#define SHT_DYNAMIC     6
#define SHT_DYNSYM      11

/* Section flags */
#define SHF_EXECINSTR   4

/* Symbol types (low 4 bits of st_info) */
#define STT_FUNC    2

/* Symbol bindings (high 4 bits of st_info) */
#define STB_LOCAL   0
#define STB_GLOBAL  1

/* Dynamic tags */
#define DT_NULL     0
#define DT_NEEDED   1

typedef struct {
    const char* name;   /* symbol name (points into string table) */
    uint64_t    value;  /* virtual address */
    uint32_t    size;
    uint8_t     type;   /* STT_FUNC=2, STT_OBJECT=1 */
    uint8_t     bind;   /* STB_GLOBAL=1, STB_LOCAL=0 */
} elf_symbol_t;

typedef struct {
    const char* lib_name;   /* e.g., "libc.so.6" */
} elf_needed_t;

typedef struct {
    /* Binary classification */
    bool        is_64bit;
    bool        is_little_endian;
    int         machine;        /* EM_386 or EM_X86_64 */
    int         file_type;      /* ET_EXEC, ET_DYN, ET_REL */

    /* Code section */
    const uint8_t* text_data;   /* points into raw data */
    size_t         text_size;
    uint64_t       text_vaddr;  /* virtual address of .text */

    /* Entry point */
    uint64_t    entry_point;

    /* Symbols */
    elf_symbol_t*  symbols;
    size_t         symbol_count;

    /* Dynamic dependencies */
    elf_needed_t*  needed;
    size_t         needed_count;

    /* Raw data (do not free — caller owns) */
    const uint8_t* raw_data;
    size_t         raw_size;
} elf_context_t;

/* Load an ELF file from a memory buffer.
 * Returns 0 on success, -1 on error. */
int  elf_load(elf_context_t* ctx, const uint8_t* data, size_t size);

/* Free allocated memory (symbols, needed arrays). */
void elf_cleanup(elf_context_t* ctx);

/* Print ELF info summary to a stream. */
void elf_print_info(const elf_context_t* ctx, FILE* out);

#endif /* ELF_LOADER_H */
