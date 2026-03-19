/* ============================================================================
 * ELF Loader — Parses ELF32 and ELF64 binaries
 * ============================================================================
 *
 * Parses ELF executables and shared libraries into an elf_context_t.
 * Supports both 32-bit and 64-bit ELF, little-endian x86/x86-64 only.
 * All struct layouts are defined manually — no #include <elf.h>.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#include "elf_loader.h"
#include <stdlib.h>
#include <string.h>

/* ============================================================================
 * Byte-order helpers (little-endian only)
 * ============================================================================ */

static uint16_t read_u16(const uint8_t* p) {
    return (uint16_t)(p[0] | (p[1] << 8));
}

static uint32_t read_u32(const uint8_t* p) {
    return (uint32_t)(p[0] | (p[1] << 8) | (p[2] << 16) | (p[3] << 24));
}

static uint64_t read_u64(const uint8_t* p) {
    return (uint64_t)read_u32(p) | ((uint64_t)read_u32(p + 4) << 32);
}

/* ============================================================================
 * ELF header offsets
 *
 * ELF header layout (both 32 and 64-bit share e_ident[0..15]):
 *   [0..3]   e_ident: magic 0x7F 'E' 'L' 'F'
 *   [4]      EI_CLASS: 1=32-bit, 2=64-bit
 *   [5]      EI_DATA: 1=little-endian, 2=big-endian
 *   [6]      EI_VERSION: must be 1
 *   [16..17] e_type: ET_REL=1, ET_EXEC=2, ET_DYN=3
 *   [18..19] e_machine: EM_386=3, EM_X86_64=62
 *
 * After e_ident, field sizes diverge between ELF32 and ELF64.
 * ============================================================================ */

/* ELF32 header field offsets */
#define ELF32_E_ENTRY    24   /* uint32_t */
#define ELF32_E_SHOFF    32   /* uint32_t */
#define ELF32_E_SHENTSIZE 46  /* uint16_t */
#define ELF32_E_SHNUM    48   /* uint16_t */
#define ELF32_E_SHSTRNDX 50   /* uint16_t */
#define ELF32_EHDR_SIZE  52

/* ELF64 header field offsets */
#define ELF64_E_ENTRY    24   /* uint64_t */
#define ELF64_E_SHOFF    40   /* uint64_t */
#define ELF64_E_SHENTSIZE 58  /* uint16_t */
#define ELF64_E_SHNUM    60   /* uint16_t */
#define ELF64_E_SHSTRNDX 62   /* uint16_t */
#define ELF64_EHDR_SIZE  64

/* ELF32 section header (40 bytes) */
#define SH32_NAME     0    /* uint32_t */
#define SH32_TYPE     4    /* uint32_t */
#define SH32_FLAGS    8    /* uint32_t */
#define SH32_ADDR     12   /* uint32_t */
#define SH32_OFFSET   16   /* uint32_t */
#define SH32_SIZE     20   /* uint32_t */
#define SH32_LINK     24   /* uint32_t */
#define SH32_ENTSIZE  36   /* uint32_t */

/* ELF64 section header (64 bytes) */
#define SH64_NAME     0    /* uint32_t */
#define SH64_TYPE     4    /* uint32_t */
#define SH64_FLAGS    8    /* uint64_t */
#define SH64_ADDR     16   /* uint64_t */
#define SH64_OFFSET   24   /* uint64_t */
#define SH64_SIZE     32   /* uint64_t */
#define SH64_LINK     40   /* uint32_t */
#define SH64_ENTSIZE  56   /* uint64_t */

/* ELF32 symbol (16 bytes) */
#define SYM32_NAME    0    /* uint32_t */
#define SYM32_VALUE   4    /* uint32_t */
#define SYM32_SIZE    8    /* uint32_t */
#define SYM32_INFO    12   /* uint8_t */
#define SYM32_SHNDX   14   /* uint16_t */
#define SYM32_ENTRY_SIZE 16

/* ELF64 symbol (24 bytes) */
#define SYM64_NAME    0    /* uint32_t */
#define SYM64_INFO    4    /* uint8_t */
#define SYM64_SHNDX   6    /* uint16_t */
#define SYM64_VALUE   8    /* uint64_t */
#define SYM64_SIZE    16   /* uint64_t */
#define SYM64_ENTRY_SIZE 24

/* Dynamic entry sizes */
#define DYN32_ENTRY_SIZE 8   /* d_tag(4) + d_val(4) */
#define DYN64_ENTRY_SIZE 16  /* d_tag(8) + d_val(8) */

/* ============================================================================
 * Internal section header reader (abstracted over 32/64-bit)
 * ============================================================================ */

typedef struct {
    uint32_t sh_name;
    uint32_t sh_type;
    uint64_t sh_flags;
    uint64_t sh_addr;
    uint64_t sh_offset;
    uint64_t sh_size;
    uint32_t sh_link;
    uint64_t sh_entsize;
} elf_shdr_t;

static void read_shdr32(elf_shdr_t* out, const uint8_t* p) {
    out->sh_name    = read_u32(p + SH32_NAME);
    out->sh_type    = read_u32(p + SH32_TYPE);
    out->sh_flags   = read_u32(p + SH32_FLAGS);
    out->sh_addr    = read_u32(p + SH32_ADDR);
    out->sh_offset  = read_u32(p + SH32_OFFSET);
    out->sh_size    = read_u32(p + SH32_SIZE);
    out->sh_link    = read_u32(p + SH32_LINK);
    out->sh_entsize = read_u32(p + SH32_ENTSIZE);
}

static void read_shdr64(elf_shdr_t* out, const uint8_t* p) {
    out->sh_name    = read_u32(p + SH64_NAME);
    out->sh_type    = read_u32(p + SH64_TYPE);
    out->sh_flags   = read_u64(p + SH64_FLAGS);
    out->sh_addr    = read_u64(p + SH64_ADDR);
    out->sh_offset  = read_u64(p + SH64_OFFSET);
    out->sh_size    = read_u64(p + SH64_SIZE);
    out->sh_link    = read_u32(p + SH64_LINK);
    out->sh_entsize = read_u64(p + SH64_ENTSIZE);
}

/* ============================================================================
 * String table helper
 * ============================================================================ */

static const char* strtab_get(const uint8_t* data, size_t data_size,
                               uint64_t strtab_offset, uint64_t strtab_size,
                               uint32_t name_index) {
    if (name_index >= strtab_size)
        return NULL;
    uint64_t off = strtab_offset + name_index;
    if (off >= data_size)
        return NULL;
    return (const char*)(data + off);
}

/* ============================================================================
 * Symbol table parsing
 * ============================================================================ */

static int parse_symbols(elf_context_t* ctx, const uint8_t* data, size_t data_size,
                          const elf_shdr_t* symtab, const elf_shdr_t* strtab,
                          bool is_64bit) {
    size_t entry_size = is_64bit ? SYM64_ENTRY_SIZE : SYM32_ENTRY_SIZE;
    if (symtab->sh_entsize > 0)
        entry_size = (size_t)symtab->sh_entsize;

    if (entry_size == 0 || symtab->sh_size == 0)
        return 0;

    size_t count = (size_t)(symtab->sh_size / entry_size);
    if (count == 0)
        return 0;

    /* Skip entry 0 (STN_UNDEF) — it's always null */
    size_t real_count = 0;
    for (size_t i = 1; i < count; i++) {
        uint64_t off = symtab->sh_offset + i * entry_size;
        if (off + entry_size > data_size)
            break;

        const uint8_t* sp = data + off;
        uint8_t info = is_64bit ? sp[SYM64_INFO] : sp[SYM32_INFO];
        uint8_t type = info & 0x0F;
        uint8_t bind = info >> 4;

        /* Only keep functions and global/local bindings */
        if (type == STT_FUNC || bind == STB_GLOBAL)
            real_count++;
    }

    if (real_count == 0)
        return 0;

    ctx->symbols = calloc(real_count, sizeof(elf_symbol_t));
    if (!ctx->symbols)
        return -1;

    size_t idx = 0;
    for (size_t i = 1; i < count && idx < real_count; i++) {
        uint64_t off = symtab->sh_offset + i * entry_size;
        if (off + entry_size > data_size)
            break;

        const uint8_t* sp = data + off;
        uint8_t info;
        uint32_t name_idx;
        uint64_t value;
        uint32_t sym_size;

        if (is_64bit) {
            name_idx = read_u32(sp + SYM64_NAME);
            info     = sp[SYM64_INFO];
            value    = read_u64(sp + SYM64_VALUE);
            sym_size = (uint32_t)read_u64(sp + SYM64_SIZE);
        } else {
            name_idx = read_u32(sp + SYM32_NAME);
            info     = sp[SYM32_INFO];
            value    = read_u32(sp + SYM32_VALUE);
            sym_size = read_u32(sp + SYM32_SIZE);
        }

        uint8_t type = info & 0x0F;
        uint8_t bind = info >> 4;

        if (type != STT_FUNC && bind != STB_GLOBAL)
            continue;

        ctx->symbols[idx].value = value;
        ctx->symbols[idx].size  = sym_size;
        ctx->symbols[idx].type  = type;
        ctx->symbols[idx].bind  = bind;
        ctx->symbols[idx].name  = strtab_get(data, data_size,
                                              strtab->sh_offset, strtab->sh_size,
                                              name_idx);
        idx++;
    }
    ctx->symbol_count = idx;
    return 0;
}

/* ============================================================================
 * Dynamic section parsing (DT_NEEDED entries)
 * ============================================================================ */

static int parse_dynamic(elf_context_t* ctx, const uint8_t* data, size_t data_size,
                          const elf_shdr_t* dynamic, const elf_shdr_t* dynstr,
                          bool is_64bit) {
    size_t entry_size = is_64bit ? DYN64_ENTRY_SIZE : DYN32_ENTRY_SIZE;
    if (dynamic->sh_entsize > 0)
        entry_size = (size_t)dynamic->sh_entsize;

    if (entry_size == 0 || dynamic->sh_size == 0)
        return 0;

    size_t count = (size_t)(dynamic->sh_size / entry_size);

    /* First pass: count DT_NEEDED entries */
    size_t needed_count = 0;
    for (size_t i = 0; i < count; i++) {
        uint64_t off = dynamic->sh_offset + i * entry_size;
        if (off + entry_size > data_size)
            break;
        const uint8_t* dp = data + off;
        int64_t tag = is_64bit ? (int64_t)read_u64(dp) : (int64_t)(int32_t)read_u32(dp);
        if (tag == DT_NULL)
            break;
        if (tag == DT_NEEDED)
            needed_count++;
    }

    if (needed_count == 0)
        return 0;

    ctx->needed = calloc(needed_count, sizeof(elf_needed_t));
    if (!ctx->needed)
        return -1;

    /* Second pass: collect names */
    size_t idx = 0;
    for (size_t i = 0; i < count && idx < needed_count; i++) {
        uint64_t off = dynamic->sh_offset + i * entry_size;
        if (off + entry_size > data_size)
            break;
        const uint8_t* dp = data + off;
        int64_t tag;
        uint64_t val;
        if (is_64bit) {
            tag = (int64_t)read_u64(dp);
            val = read_u64(dp + 8);
        } else {
            tag = (int64_t)(int32_t)read_u32(dp);
            val = read_u32(dp + 4);
        }
        if (tag == DT_NULL)
            break;
        if (tag == DT_NEEDED && dynstr) {
            ctx->needed[idx].lib_name = strtab_get(data, data_size,
                                                    dynstr->sh_offset,
                                                    dynstr->sh_size,
                                                    (uint32_t)val);
            idx++;
        }
    }
    ctx->needed_count = idx;
    return 0;
}

/* ============================================================================
 * Main load function
 * ============================================================================ */

int elf_load(elf_context_t* ctx, const uint8_t* data, size_t size) {
    if (!ctx || !data)
        return -1;

    memset(ctx, 0, sizeof(*ctx));

    /* Minimum size: ELF magic (4) + EI_CLASS (1) + EI_DATA (1) + EI_VERSION (1) */
    if (size < 7)
        return -1;

    /* Check ELF magic */
    if (data[0] != 0x7F || data[1] != 'E' || data[2] != 'L' || data[3] != 'F')
        return -1;

    /* EI_CLASS: 1=32-bit, 2=64-bit */
    bool is_64bit = (data[4] == 2);
    ctx->is_64bit = is_64bit;

    /* EI_DATA: we only support little-endian (1) */
    if (data[5] != 1) {
        ctx->is_little_endian = false;
        return -1;
    }
    ctx->is_little_endian = true;

    /* Minimum header sizes */
    size_t min_ehdr = is_64bit ? ELF64_EHDR_SIZE : ELF32_EHDR_SIZE;
    if (size < min_ehdr)
        return -1;

    /* e_type and e_machine (same offset for both 32 and 64-bit) */
    ctx->file_type = read_u16(data + 16);
    ctx->machine   = read_u16(data + 18);

    /* We only handle x86 and x86-64 */
    if (ctx->machine != EM_386 && ctx->machine != EM_X86_64)
        return -1;

    /* Entry point and section header table location */
    uint64_t e_entry, e_shoff;
    uint16_t e_shentsize, e_shnum, e_shstrndx;

    if (is_64bit) {
        e_entry     = read_u64(data + ELF64_E_ENTRY);
        e_shoff     = read_u64(data + ELF64_E_SHOFF);
        e_shentsize = read_u16(data + ELF64_E_SHENTSIZE);
        e_shnum     = read_u16(data + ELF64_E_SHNUM);
        e_shstrndx  = read_u16(data + ELF64_E_SHSTRNDX);
    } else {
        e_entry     = read_u32(data + ELF32_E_ENTRY);
        e_shoff     = read_u32(data + ELF32_E_SHOFF);
        e_shentsize = read_u16(data + ELF32_E_SHENTSIZE);
        e_shnum     = read_u16(data + ELF32_E_SHNUM);
        e_shstrndx  = read_u16(data + ELF32_E_SHSTRNDX);
    }

    ctx->entry_point = e_entry;
    ctx->raw_data = data;
    ctx->raw_size = size;

    /* No section headers — that's valid (stripped binary), just no metadata */
    if (e_shnum == 0 || e_shoff == 0)
        return 0;

    /* Validate section header table fits in file */
    if (e_shoff + (uint64_t)e_shnum * e_shentsize > size)
        return -1;

    /* Read section header string table first (for section names) */
    elf_shdr_t shstrtab = {0};
    if (e_shstrndx < e_shnum) {
        const uint8_t* shstr_p = data + e_shoff + (uint64_t)e_shstrndx * e_shentsize;
        if (is_64bit)
            read_shdr64(&shstrtab, shstr_p);
        else
            read_shdr32(&shstrtab, shstr_p);
    }

    /* Walk all section headers */
    elf_shdr_t text_shdr = {0};
    bool found_text = false;
    elf_shdr_t symtab_shdr = {0}, strtab_shdr = {0};
    bool found_symtab = false, found_strtab = false;
    elf_shdr_t dynsym_shdr = {0}, dynstr_shdr = {0}, dynamic_shdr = {0};
    bool found_dynsym = false, found_dynstr = false, found_dynamic = false;

    for (uint16_t i = 0; i < e_shnum; i++) {
        uint64_t sh_off = e_shoff + (uint64_t)i * e_shentsize;
        if (sh_off + e_shentsize > size)
            break;

        elf_shdr_t shdr;
        if (is_64bit)
            read_shdr64(&shdr, data + sh_off);
        else
            read_shdr32(&shdr, data + sh_off);

        /* Resolve section name from shstrtab */
        const char* sname = NULL;
        if (shstrtab.sh_offset > 0 && shdr.sh_name < shstrtab.sh_size) {
            uint64_t name_off = shstrtab.sh_offset + shdr.sh_name;
            if (name_off < size)
                sname = (const char*)(data + name_off);
        }

        /* Find .text section (by name or by PROGBITS + EXECINSTR) */
        if (!found_text) {
            bool is_text = false;
            if (sname && strcmp(sname, ".text") == 0)
                is_text = true;
            else if (shdr.sh_type == SHT_PROGBITS &&
                     (shdr.sh_flags & SHF_EXECINSTR))
                is_text = true;

            if (is_text) {
                text_shdr = shdr;
                found_text = true;
            }
        }

        /* Find symbol table (.symtab) */
        if (shdr.sh_type == SHT_SYMTAB && !found_symtab) {
            symtab_shdr = shdr;
            found_symtab = true;
            /* sh_link points to the associated string table */
            if (shdr.sh_link < e_shnum) {
                uint64_t link_off = e_shoff + (uint64_t)shdr.sh_link * e_shentsize;
                if (link_off + e_shentsize <= size) {
                    if (is_64bit)
                        read_shdr64(&strtab_shdr, data + link_off);
                    else
                        read_shdr32(&strtab_shdr, data + link_off);
                    found_strtab = true;
                }
            }
        }

        /* Find dynamic symbol table (.dynsym) */
        if (shdr.sh_type == SHT_DYNSYM && !found_dynsym) {
            dynsym_shdr = shdr;
            found_dynsym = true;
            if (shdr.sh_link < e_shnum) {
                uint64_t link_off = e_shoff + (uint64_t)shdr.sh_link * e_shentsize;
                if (link_off + e_shentsize <= size) {
                    if (is_64bit)
                        read_shdr64(&dynstr_shdr, data + link_off);
                    else
                        read_shdr32(&dynstr_shdr, data + link_off);
                    found_dynstr = true;
                }
            }
        }

        /* Find .dynamic section and its linked string table */
        if (shdr.sh_type == SHT_DYNAMIC && !found_dynamic) {
            dynamic_shdr = shdr;
            found_dynamic = true;
            if (!found_dynstr && shdr.sh_link < e_shnum) {
                uint64_t link_off = e_shoff + (uint64_t)shdr.sh_link * e_shentsize;
                if (link_off + e_shentsize <= size) {
                    if (is_64bit)
                        read_shdr64(&dynstr_shdr, data + link_off);
                    else
                        read_shdr32(&dynstr_shdr, data + link_off);
                    found_dynstr = true;
                }
            }
        }
    }

    /* Set .text code pointer */
    if (found_text && text_shdr.sh_offset + text_shdr.sh_size <= size) {
        ctx->text_data  = data + text_shdr.sh_offset;
        ctx->text_size  = (size_t)text_shdr.sh_size;
        ctx->text_vaddr = text_shdr.sh_addr;
    }

    /* Parse symbols: prefer .symtab, fall back to .dynsym */
    if (found_symtab && found_strtab) {
        parse_symbols(ctx, data, size, &symtab_shdr, &strtab_shdr, is_64bit);
    } else if (found_dynsym && found_dynstr) {
        parse_symbols(ctx, data, size, &dynsym_shdr, &dynstr_shdr, is_64bit);
    }

    /* Parse dynamic dependencies (DT_NEEDED) */
    if (found_dynamic) {
        const elf_shdr_t* dstr = found_dynstr ? &dynstr_shdr : NULL;
        parse_dynamic(ctx, data, size, &dynamic_shdr, dstr, is_64bit);
    }

    return 0;
}

/* ============================================================================
 * Cleanup
 * ============================================================================ */

void elf_cleanup(elf_context_t* ctx) {
    if (!ctx)
        return;
    /* symbol names point into raw_data (string tables), so don't free them */
    free(ctx->symbols);
    /* needed lib_name pointers also point into raw_data */
    free(ctx->needed);
    memset(ctx, 0, sizeof(*ctx));
}

/* ============================================================================
 * Print info
 * ============================================================================ */

void elf_print_info(const elf_context_t* ctx, FILE* out) {
    if (!ctx || !out)
        return;

    const char* type_str;
    switch (ctx->file_type) {
        case ET_REL:  type_str = "relocatable"; break;
        case ET_EXEC: type_str = "executable";  break;
        case ET_DYN:  type_str = "shared lib";  break;
        default:      type_str = "unknown";     break;
    }

    const char* mach_str;
    switch (ctx->machine) {
        case EM_386:    mach_str = "x86 (i386)";  break;
        case EM_X86_64: mach_str = "x86-64";      break;
        default:        mach_str = "unsupported";  break;
    }

    fprintf(out, "ELF%s %s (%s)\n",
            ctx->is_64bit ? "64" : "32", type_str, mach_str);
    fprintf(out, "  Entry point: 0x%llX\n", (unsigned long long)ctx->entry_point);

    if (ctx->text_data) {
        fprintf(out, "  .text: vaddr=0x%llX size=%zu bytes\n",
                (unsigned long long)ctx->text_vaddr, ctx->text_size);
    }

    if (ctx->symbol_count > 0) {
        fprintf(out, "  Symbols: %zu\n", ctx->symbol_count);
        for (size_t i = 0; i < ctx->symbol_count && i < 20; i++) {
            fprintf(out, "    [%zu] 0x%llX %s%s\n", i,
                    (unsigned long long)ctx->symbols[i].value,
                    ctx->symbols[i].name ? ctx->symbols[i].name : "(null)",
                    ctx->symbols[i].type == STT_FUNC ? " (FUNC)" : "");
        }
        if (ctx->symbol_count > 20)
            fprintf(out, "    ... and %zu more\n", ctx->symbol_count - 20);
    }

    if (ctx->needed_count > 0) {
        fprintf(out, "  Dependencies:\n");
        for (size_t i = 0; i < ctx->needed_count; i++) {
            fprintf(out, "    %s\n",
                    ctx->needed[i].lib_name ? ctx->needed[i].lib_name : "(null)");
        }
    }
}
