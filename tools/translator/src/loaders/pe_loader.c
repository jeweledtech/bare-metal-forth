/* ============================================================================
 * PE Loader Implementation
 * ============================================================================
 *
 * Parses PE (Portable Executable) files: DOS header, COFF header, optional
 * header (PE32/PE32+), sections, imports, and exports.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pe_loader.h"
#include "pe_format.h"

/* Safe read helpers - check bounds before accessing raw data */

static inline bool bounds_check(size_t data_size,
                                size_t offset, size_t read_size) {
    return (offset + read_size <= data_size) && (offset + read_size >= offset);
}

static inline uint16_t read16(const uint8_t* p) {
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static inline uint32_t read32(const uint8_t* p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static inline uint64_t read64(const uint8_t* p) {
    return (uint64_t)read32(p) | ((uint64_t)read32(p + 4) << 32);
}

/* ---- RVA to file pointer conversion ---- */

const uint8_t* pe_rva_to_ptr(const pe_context_t* ctx, uint32_t rva) {
    for (size_t i = 0; i < ctx->section_count; i++) {
        const pe_section_t* s = &ctx->sections[i];
        if (rva >= s->virtual_address &&
            rva < s->virtual_address + s->raw_data_size) {
            uint32_t file_offset = s->raw_data_offset + (rva - s->virtual_address);
            if (file_offset < ctx->data_size) {
                return ctx->data + file_offset;
            }
        }
    }
    return NULL;
}

/* ---- Section lookup ---- */

const pe_section_t* pe_find_section(const pe_context_t* ctx, const char* name) {
    for (size_t i = 0; i < ctx->section_count; i++) {
        if (strncmp(ctx->sections[i].name, name, 8) == 0) {
            return &ctx->sections[i];
        }
    }
    return NULL;
}

/* ---- Import lookup ---- */

const pe_import_t* pe_find_import(const pe_context_t* ctx, const char* func_name) {
    for (size_t i = 0; i < ctx->import_count; i++) {
        if (ctx->imports[i].func_name &&
            strcmp(ctx->imports[i].func_name, func_name) == 0) {
            return &ctx->imports[i];
        }
    }
    return NULL;
}

/* ---- Parse sections ---- */

static int parse_sections(pe_context_t* ctx, size_t section_table_offset,
                          uint16_t count) {
    ctx->section_count = count;
    ctx->sections = calloc(count, sizeof(pe_section_t));
    if (!ctx->sections) return -1;

    for (uint16_t i = 0; i < count; i++) {
        size_t off = section_table_offset + (size_t)i * 40;
        if (!bounds_check(ctx->data_size, off, 40)) {
            return -1;
        }

        const section_header_t* sh = (const section_header_t*)(ctx->data + off);
        pe_section_t* s = &ctx->sections[i];

        memcpy(s->name, sh->name, 8);
        s->name[8] = '\0';
        s->virtual_size = sh->virtual_size;
        s->virtual_address = sh->virtual_address;
        s->raw_data_size = sh->size_of_raw_data;
        s->raw_data_offset = sh->pointer_to_raw_data;
        s->characteristics = sh->characteristics;

        /* Identify .text section */
        if ((sh->characteristics & SECTION_CNT_CODE) &&
            (sh->characteristics & SECTION_MEM_EXECUTE)) {
            if (!ctx->text_data) {
                uint32_t text_size = sh->virtual_size;
                if (text_size == 0 || text_size > sh->size_of_raw_data)
                    text_size = sh->size_of_raw_data;
                if (bounds_check(ctx->data_size,
                                 sh->pointer_to_raw_data, text_size)) {
                    ctx->text_data = ctx->data + sh->pointer_to_raw_data;
                    ctx->text_size = text_size;
                    ctx->text_rva = sh->virtual_address;
                }
            }
        }
    }
    return 0;
}

/* ---- Parse imports ---- */

static int parse_imports(pe_context_t* ctx, uint32_t import_dir_rva,
                         uint32_t import_dir_size) {
    if (import_dir_rva == 0 || import_dir_size == 0) return 0;

    /* Count import descriptors first */
    size_t desc_count = 0;
    for (size_t i = 0; ; i++) {
        const uint8_t* dp = pe_rva_to_ptr(ctx,
            import_dir_rva + (uint32_t)(i * sizeof(import_descriptor_t)));
        if (!dp) break;

        const import_descriptor_t* desc = (const import_descriptor_t*)dp;
        /* Terminator: all-zero entry */
        if (desc->name_rva == 0 && desc->import_lookup_table_rva == 0)
            break;
        desc_count++;
        if (desc_count > 1000) break; /* sanity limit */
    }

    if (desc_count == 0) return 0;

    /* Temporary: collect all imports with dynamic growth */
    size_t cap = 64;
    size_t count = 0;
    pe_import_t* imports = calloc(cap, sizeof(pe_import_t));
    if (!imports) return -1;

    for (size_t d = 0; d < desc_count; d++) {
        const uint8_t* dp = pe_rva_to_ptr(ctx,
            import_dir_rva + (uint32_t)(d * sizeof(import_descriptor_t)));
        const import_descriptor_t* desc = (const import_descriptor_t*)dp;

        /* Get DLL name */
        const uint8_t* dll_name_ptr = pe_rva_to_ptr(ctx, desc->name_rva);
        if (!dll_name_ptr) continue;
        const char* dll_name = (const char*)dll_name_ptr;

        /* Walk Import Lookup Table (or IAT if ILT is zero) */
        uint32_t ilt_rva = desc->import_lookup_table_rva;
        if (ilt_rva == 0) ilt_rva = desc->import_address_table_rva;
        if (ilt_rva == 0) continue;

        uint32_t iat_rva = desc->import_address_table_rva;

        for (uint32_t j = 0; ; j++) {
            uint32_t entry_size = ctx->is_64bit ? 8 : 4;
            const uint8_t* ep = pe_rva_to_ptr(ctx, ilt_rva + j * entry_size);
            if (!ep) break;

            uint64_t entry;
            if (ctx->is_64bit) {
                entry = read64(ep);
            } else {
                entry = read32(ep);
            }
            if (entry == 0) break;

            /* Grow array if needed */
            if (count >= cap) {
                cap *= 2;
                pe_import_t* tmp = realloc(imports, cap * sizeof(pe_import_t));
                if (!tmp) { free(imports); return -1; }
                imports = tmp;
            }

            pe_import_t* imp = &imports[count];
            memset(imp, 0, sizeof(*imp));
            imp->dll_name = strdup(dll_name);
            imp->iat_rva = iat_rva + j * entry_size;

            /* Check ordinal flag */
            uint64_t ordinal_flag = ctx->is_64bit ?
                IMPORT_ORDINAL_FLAG_64 : IMPORT_ORDINAL_FLAG_32;

            if (entry & ordinal_flag) {
                imp->ordinal = (uint16_t)(entry & 0xFFFF);
                imp->func_name = NULL;
            } else {
                uint32_t hint_rva = (uint32_t)(entry & 0x7FFFFFFF);
                const uint8_t* hn = pe_rva_to_ptr(ctx, hint_rva);
                if (hn) {
                    imp->ordinal = read16(hn);
                    imp->func_name = strdup((const char*)(hn + 2));
                }
            }
            count++;
            if (count > 10000) break; /* sanity */
        }
    }

    ctx->imports = imports;
    ctx->import_count = count;
    return 0;
}

/* ---- Parse exports ---- */

static int parse_exports(pe_context_t* ctx, uint32_t export_dir_rva,
                         uint32_t export_dir_size) {
    if (export_dir_rva == 0 || export_dir_size == 0) return 0;

    const uint8_t* ep = pe_rva_to_ptr(ctx, export_dir_rva);
    if (!ep) return 0;

    const export_directory_t* edir = (const export_directory_t*)ep;
    uint32_t num_names = edir->number_of_names;
    uint32_t num_funcs = edir->number_of_functions;

    if (num_names == 0 && num_funcs == 0) return 0;
    if (num_names > 10000 || num_funcs > 10000) return 0; /* sanity */

    ctx->exports = calloc(num_names > 0 ? num_names : num_funcs,
                          sizeof(pe_export_t));
    if (!ctx->exports) return -1;

    if (num_names > 0) {
        const uint8_t* names_ptr = pe_rva_to_ptr(ctx, edir->address_of_names_rva);
        const uint8_t* ords_ptr = pe_rva_to_ptr(ctx, edir->address_of_name_ordinals_rva);
        const uint8_t* funcs_ptr = pe_rva_to_ptr(ctx, edir->address_of_functions_rva);
        if (!names_ptr || !ords_ptr || !funcs_ptr) return 0;

        for (uint32_t i = 0; i < num_names; i++) {
            uint32_t name_rva = read32(names_ptr + i * 4);
            uint16_t ord_idx = read16(ords_ptr + i * 2);
            uint32_t func_rva = read32(funcs_ptr + (uint32_t)ord_idx * 4);

            const uint8_t* np = pe_rva_to_ptr(ctx, name_rva);
            if (!np) continue;

            pe_export_t* ex = &ctx->exports[ctx->export_count];
            ex->name = strdup((const char*)np);
            ex->ordinal = edir->ordinal_base + ord_idx;
            ex->rva = func_rva;
            ctx->export_count++;
        }
    }

    return 0;
}

/* ---- Main loader ---- */

int pe_load(pe_context_t* ctx, const uint8_t* data, size_t size) {
    memset(ctx, 0, sizeof(*ctx));
    ctx->data = data;
    ctx->data_size = size;

    /* Check minimum size for DOS header */
    if (size < sizeof(dos_header_t)) return -1;

    /* Validate DOS magic */
    if (read16(data) != DOS_MAGIC) return -1;

    /* Get PE header offset */
    uint32_t pe_offset = read32(data + 60); /* e_lfanew */
    if (!bounds_check(size, pe_offset, 4 + 20)) return -1;

    /* Validate PE signature */
    if (read32(data + pe_offset) != PE_SIGNATURE) return -1;

    /* Parse COFF header */
    const uint8_t* coff = data + pe_offset + 4;
    ctx->machine = read16(coff);
    uint16_t num_sections = read16(coff + 2);
    uint16_t opt_header_size = read16(coff + 16);

    /* Parse optional header */
    size_t opt_offset = pe_offset + 4 + 20;
    if (!bounds_check(size, opt_offset, 2)) return -1;

    uint16_t opt_magic = read16(data + opt_offset);

    if (opt_magic == PE_OPT_MAGIC_PE32) {
        if (!bounds_check(size, opt_offset, sizeof(pe32_optional_header_t)))
            return -1;
        const pe32_optional_header_t* opt =
            (const pe32_optional_header_t*)(data + opt_offset);
        ctx->is_64bit = false;
        ctx->image_base = opt->image_base;
        ctx->entry_point_rva = opt->address_of_entry_point;

        /* Parse data directories */
        uint32_t num_dirs = opt->number_of_rva_and_sizes;
        if (num_dirs > 16) num_dirs = 16;
        const data_directory_t* dirs = (const data_directory_t*)(
            data + opt_offset + sizeof(pe32_optional_header_t));

        /* Parse sections first (needed for RVA resolution) */
        size_t sec_offset = opt_offset + opt_header_size;
        if (parse_sections(ctx, sec_offset, num_sections) != 0) return -1;

        /* Now parse imports/exports using RVA resolution */
        if (num_dirs > DATA_DIR_IMPORT) {
            parse_imports(ctx, dirs[DATA_DIR_IMPORT].virtual_address,
                         dirs[DATA_DIR_IMPORT].size);
        }
        if (num_dirs > DATA_DIR_EXPORT) {
            parse_exports(ctx, dirs[DATA_DIR_EXPORT].virtual_address,
                         dirs[DATA_DIR_EXPORT].size);
        }

    } else if (opt_magic == PE_OPT_MAGIC_PE32PLUS) {
        if (!bounds_check(size, opt_offset,
                          sizeof(pe32plus_optional_header_t)))
            return -1;
        const pe32plus_optional_header_t* opt =
            (const pe32plus_optional_header_t*)(data + opt_offset);
        ctx->is_64bit = true;
        ctx->image_base = opt->image_base;
        ctx->entry_point_rva = opt->address_of_entry_point;

        uint32_t num_dirs = opt->number_of_rva_and_sizes;
        if (num_dirs > 16) num_dirs = 16;
        const data_directory_t* dirs = (const data_directory_t*)(
            data + opt_offset + sizeof(pe32plus_optional_header_t));

        size_t sec_offset = opt_offset + opt_header_size;
        if (parse_sections(ctx, sec_offset, num_sections) != 0) return -1;

        if (num_dirs > DATA_DIR_IMPORT) {
            parse_imports(ctx, dirs[DATA_DIR_IMPORT].virtual_address,
                         dirs[DATA_DIR_IMPORT].size);
        }
        if (num_dirs > DATA_DIR_EXPORT) {
            parse_exports(ctx, dirs[DATA_DIR_EXPORT].virtual_address,
                         dirs[DATA_DIR_EXPORT].size);
        }

    } else {
        return -1; /* Unknown optional header magic */
    }

    return 0;
}

/* ---- Cleanup ---- */

void pe_cleanup(pe_context_t* ctx) {
    if (ctx->sections) {
        free(ctx->sections);
        ctx->sections = NULL;
    }
    if (ctx->imports) {
        for (size_t i = 0; i < ctx->import_count; i++) {
            free(ctx->imports[i].dll_name);
            free(ctx->imports[i].func_name);
        }
        free(ctx->imports);
        ctx->imports = NULL;
    }
    if (ctx->exports) {
        for (size_t i = 0; i < ctx->export_count; i++) {
            free(ctx->exports[i].name);
        }
        free(ctx->exports);
        ctx->exports = NULL;
    }
    ctx->text_data = NULL;
    ctx->text_size = 0;
    ctx->import_count = 0;
    ctx->export_count = 0;
    ctx->section_count = 0;
}

/* ---- Debug output ---- */

void pe_print_info(const pe_context_t* ctx, FILE* out) {
    fprintf(out, "PE Image Info\n");
    fprintf(out, "=============\n");
    fprintf(out, "Machine:     0x%04X (%s)\n", ctx->machine,
            ctx->machine == COFF_MACHINE_I386 ? "i386" :
            ctx->machine == COFF_MACHINE_AMD64 ? "AMD64" : "unknown");
    fprintf(out, "Format:      %s\n", ctx->is_64bit ? "PE32+" : "PE32");
    fprintf(out, "Image Base:  0x%08llX\n", (unsigned long long)ctx->image_base);
    fprintf(out, "Entry Point: 0x%08X (RVA)\n", ctx->entry_point_rva);
    fprintf(out, "\n");

    fprintf(out, "Sections (%zu):\n", ctx->section_count);
    for (size_t i = 0; i < ctx->section_count; i++) {
        const pe_section_t* s = &ctx->sections[i];
        fprintf(out, "  %-8s  VirtAddr=0x%08X  VirtSize=0x%08X  "
                "RawOff=0x%08X  RawSize=0x%08X  Flags=0x%08X\n",
                s->name, s->virtual_address, s->virtual_size,
                s->raw_data_offset, s->raw_data_size, s->characteristics);
    }
    fprintf(out, "\n");

    if (ctx->import_count > 0) {
        fprintf(out, "Imports (%zu):\n", ctx->import_count);
        const char* prev_dll = "";
        for (size_t i = 0; i < ctx->import_count; i++) {
            const pe_import_t* imp = &ctx->imports[i];
            if (strcmp(imp->dll_name, prev_dll) != 0) {
                fprintf(out, "  %s:\n", imp->dll_name);
                prev_dll = imp->dll_name;
            }
            if (imp->func_name) {
                fprintf(out, "    %s (ordinal %u)\n", imp->func_name, imp->ordinal);
            } else {
                fprintf(out, "    ordinal %u\n", imp->ordinal);
            }
        }
        fprintf(out, "\n");
    }

    if (ctx->export_count > 0) {
        fprintf(out, "Exports (%zu):\n", ctx->export_count);
        for (size_t i = 0; i < ctx->export_count; i++) {
            const pe_export_t* ex = &ctx->exports[i];
            fprintf(out, "  %s  ordinal=%u  RVA=0x%08X\n",
                    ex->name, ex->ordinal, ex->rva);
        }
        fprintf(out, "\n");
    }
}
