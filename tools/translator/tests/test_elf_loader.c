/* ============================================================================
 * ELF Loader Tests
 * ============================================================================
 *
 * Validates the ELF32 and ELF64 parser using synthetic ELF binaries built
 * in-memory.  No external files needed.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "../include/elf_loader.h"

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) do { \
    tests_run++; \
    printf("  TEST: %-50s ", #name); \
} while(0)

#define PASS() do { tests_passed++; printf("PASS\n"); } while(0)
#define FAIL(msg) do { printf("FAIL: %s\n", msg); return; } while(0)

/* ============================================================================
 * Synthetic ELF builder helpers
 *
 * Layout for our minimal test ELFs:
 *
 *   [ELF header]         at offset 0
 *   [.text section]      at offset text_off
 *   [.symtab]            at offset symtab_off (optional)
 *   [.strtab]            at offset strtab_off (optional)
 *   [.dynamic]           at offset dynamic_off (optional)
 *   [.dynstr]            at offset dynstr_off (optional)
 *   [.shstrtab]          at offset shstrtab_off
 *   [section headers]    at offset shdr_off
 * ============================================================================ */

/* Write a little-endian uint16 at buf+off */
static void w16(uint8_t* buf, size_t off, uint16_t val) {
    buf[off]   = (uint8_t)(val & 0xFF);
    buf[off+1] = (uint8_t)(val >> 8);
}

/* Write a little-endian uint32 at buf+off */
static void w32(uint8_t* buf, size_t off, uint32_t val) {
    buf[off]   = (uint8_t)(val & 0xFF);
    buf[off+1] = (uint8_t)((val >> 8) & 0xFF);
    buf[off+2] = (uint8_t)((val >> 16) & 0xFF);
    buf[off+3] = (uint8_t)((val >> 24) & 0xFF);
}

/* Write a little-endian uint64 at buf+off */
static void w64(uint8_t* buf, size_t off, uint64_t val) {
    w32(buf, off, (uint32_t)(val & 0xFFFFFFFF));
    w32(buf, off + 4, (uint32_t)(val >> 32));
}

/* Section header string table content for our test ELFs.
 * Index 0: '\0'
 * Index 1: ".text\0"     (6 bytes)
 * Index 7: ".shstrtab\0" (10 bytes)
 * Index 17: ".symtab\0"  (8 bytes)
 * Index 25: ".strtab\0"  (8 bytes)
 * Index 33: ".dynamic\0" (9 bytes)
 * Index 42: ".dynstr\0"  (8 bytes)
 * Total: 50 bytes */
static const char shstrtab_data[] =
    "\0.text\0.shstrtab\0.symtab\0.strtab\0.dynamic\0.dynstr";
#define SHSTRTAB_SIZE 50
#define SHSTR_TEXT     1
#define SHSTR_SHSTRTAB 7
#define SHSTR_SYMTAB   17
#define SHSTR_STRTAB   25
#define SHSTR_DYNAMIC  33
#define SHSTR_DYNSTR   42

/* Build a minimal ELF32 with just .text + .shstrtab.
 * Returns allocated buffer, sets *out_size. Caller frees. */
static uint8_t* build_elf32_minimal(size_t* out_size,
                                      uint32_t entry,
                                      const uint8_t* text_code,
                                      size_t text_code_size) {
    /* Layout:
     *   0x00: ELF32 header (52 bytes)
     *   0x34: .text section data
     *   text_end: .shstrtab data
     *   shstrtab_end: section headers (3 sections: NULL, .text, .shstrtab)
     */
    size_t ehdr_size = 52;
    size_t text_off = ehdr_size;
    size_t shstrtab_off = text_off + text_code_size;
    size_t shdr_off = shstrtab_off + SHSTRTAB_SIZE;
    /* Align section headers to 4 bytes */
    shdr_off = (shdr_off + 3) & ~(size_t)3;
    size_t shdr_entry_size = 40;  /* ELF32 section header */
    size_t total = shdr_off + 3 * shdr_entry_size;

    uint8_t* buf = calloc(1, total);
    if (!buf) return NULL;

    /* ELF header */
    buf[0] = 0x7F; buf[1] = 'E'; buf[2] = 'L'; buf[3] = 'F';
    buf[4] = 1;    /* EI_CLASS: ELFCLASS32 */
    buf[5] = 1;    /* EI_DATA: ELFDATA2LSB */
    buf[6] = 1;    /* EI_VERSION: EV_CURRENT */
    w16(buf, 16, 2);     /* e_type: ET_EXEC */
    w16(buf, 18, 3);     /* e_machine: EM_386 */
    w32(buf, 20, 1);     /* e_version */
    w32(buf, 24, entry); /* e_entry */
    w32(buf, 28, 0);     /* e_phoff (no program headers) */
    w32(buf, 32, (uint32_t)shdr_off);  /* e_shoff */
    w32(buf, 36, 0);     /* e_flags */
    w16(buf, 40, (uint16_t)ehdr_size); /* e_ehsize */
    w16(buf, 42, 0);     /* e_phentsize */
    w16(buf, 44, 0);     /* e_phnum */
    w16(buf, 46, (uint16_t)shdr_entry_size); /* e_shentsize */
    w16(buf, 48, 3);     /* e_shnum */
    w16(buf, 50, 2);     /* e_shstrndx = section 2 */

    /* .text section data */
    memcpy(buf + text_off, text_code, text_code_size);

    /* .shstrtab data */
    memcpy(buf + shstrtab_off, shstrtab_data, SHSTRTAB_SIZE);

    /* Section headers */
    /* [0] SHN_UNDEF — all zeros (already zeroed) */

    /* [1] .text */
    size_t sh1 = shdr_off + shdr_entry_size;
    w32(buf, sh1 + 0, SHSTR_TEXT);  /* sh_name */
    w32(buf, sh1 + 4, 1);           /* sh_type = SHT_PROGBITS */
    w32(buf, sh1 + 8, 4 | 2);       /* sh_flags = SHF_EXECINSTR | SHF_ALLOC */
    w32(buf, sh1 + 12, 0x08048000); /* sh_addr */
    w32(buf, sh1 + 16, (uint32_t)text_off);  /* sh_offset */
    w32(buf, sh1 + 20, (uint32_t)text_code_size); /* sh_size */

    /* [2] .shstrtab */
    size_t sh2 = shdr_off + 2 * shdr_entry_size;
    w32(buf, sh2 + 0, SHSTR_SHSTRTAB); /* sh_name */
    w32(buf, sh2 + 4, 3);              /* sh_type = SHT_STRTAB */
    w32(buf, sh2 + 16, (uint32_t)shstrtab_off); /* sh_offset */
    w32(buf, sh2 + 20, SHSTRTAB_SIZE); /* sh_size */

    *out_size = total;
    return buf;
}

/* Build a minimal ELF64 with just .text + .shstrtab. */
static uint8_t* build_elf64_minimal(size_t* out_size,
                                      uint64_t entry,
                                      const uint8_t* text_code,
                                      size_t text_code_size) {
    size_t ehdr_size = 64;
    size_t text_off = ehdr_size;
    size_t shstrtab_off = text_off + text_code_size;
    size_t shdr_off = shstrtab_off + SHSTRTAB_SIZE;
    shdr_off = (shdr_off + 7) & ~(size_t)7;
    size_t shdr_entry_size = 64;  /* ELF64 section header */
    size_t total = shdr_off + 3 * shdr_entry_size;

    uint8_t* buf = calloc(1, total);
    if (!buf) return NULL;

    /* ELF header */
    buf[0] = 0x7F; buf[1] = 'E'; buf[2] = 'L'; buf[3] = 'F';
    buf[4] = 2;    /* EI_CLASS: ELFCLASS64 */
    buf[5] = 1;    /* EI_DATA: ELFDATA2LSB */
    buf[6] = 1;    /* EI_VERSION */
    w16(buf, 16, 3);      /* e_type: ET_DYN (shared lib) */
    w16(buf, 18, 62);     /* e_machine: EM_X86_64 */
    w32(buf, 20, 1);      /* e_version */
    w64(buf, 24, entry);  /* e_entry */
    w64(buf, 32, 0);      /* e_phoff */
    w64(buf, 40, (uint64_t)shdr_off);  /* e_shoff */
    w32(buf, 48, 0);      /* e_flags */
    w16(buf, 52, (uint16_t)ehdr_size); /* e_ehsize */
    w16(buf, 54, 0);      /* e_phentsize */
    w16(buf, 56, 0);      /* e_phnum */
    w16(buf, 58, (uint16_t)shdr_entry_size); /* e_shentsize */
    w16(buf, 60, 3);      /* e_shnum */
    w16(buf, 62, 2);      /* e_shstrndx = section 2 */

    /* .text data */
    memcpy(buf + text_off, text_code, text_code_size);

    /* .shstrtab data */
    memcpy(buf + shstrtab_off, shstrtab_data, SHSTRTAB_SIZE);

    /* Section headers */
    /* [0] SHN_UNDEF — all zeros */

    /* [1] .text */
    size_t sh1 = shdr_off + shdr_entry_size;
    w32(buf, sh1 + 0, SHSTR_TEXT);    /* sh_name */
    w32(buf, sh1 + 4, 1);             /* sh_type = SHT_PROGBITS */
    w64(buf, sh1 + 8, 4 | 2);         /* sh_flags = SHF_EXECINSTR | SHF_ALLOC */
    w64(buf, sh1 + 16, 0x400000);     /* sh_addr */
    w64(buf, sh1 + 24, (uint64_t)text_off);  /* sh_offset */
    w64(buf, sh1 + 32, (uint64_t)text_code_size); /* sh_size */

    /* [2] .shstrtab */
    size_t sh2 = shdr_off + 2 * shdr_entry_size;
    w32(buf, sh2 + 0, SHSTR_SHSTRTAB);
    w32(buf, sh2 + 4, 3);             /* SHT_STRTAB */
    w64(buf, sh2 + 24, (uint64_t)shstrtab_off);
    w64(buf, sh2 + 32, SHSTRTAB_SIZE);

    *out_size = total;
    return buf;
}

/* Build an ELF32 with .text + .symtab + .strtab + .shstrtab (5 sections).
 * Includes two symbols: _start (FUNC) and data_val (OBJECT/GLOBAL). */
static uint8_t* build_elf32_with_symbols(size_t* out_size,
                                           const uint8_t* text_code,
                                           size_t text_code_size) {
    /* Symbol string table: "\0_start\0data_val" + trailing NUL */
    const char sym_strtab[] = "\0_start\0data_val";
    size_t sym_strtab_size = sizeof(sym_strtab);

    /* Symbol table: 3 entries (NULL + _start + data_val), each 16 bytes */
    size_t sym_entry_size = 16;
    size_t sym_count = 3;
    uint8_t symtab[48];  /* 3 * 16 */
    memset(symtab, 0, sizeof(symtab));

    /* entry [1]: _start — FUNC, GLOBAL, value=0x08048000 */
    w32(symtab, 1*16 + 0, 1);          /* st_name: index 1 = "_start" */
    w32(symtab, 1*16 + 4, 0x08048000); /* st_value */
    w32(symtab, 1*16 + 8, (uint32_t)text_code_size); /* st_size */
    symtab[1*16 + 12] = (1 << 4) | 2;  /* st_info: STB_GLOBAL | STT_FUNC */
    w16(symtab, 1*16 + 14, 1);          /* st_shndx: section 1 (.text) */

    /* entry [2]: data_val — OBJECT, GLOBAL, value=0x0804A000 */
    w32(symtab, 2*16 + 0, 8);          /* st_name: index 8 = "data_val" */
    w32(symtab, 2*16 + 4, 0x0804A000); /* st_value */
    w32(symtab, 2*16 + 8, 4);          /* st_size */
    symtab[2*16 + 12] = (1 << 4) | 1;  /* st_info: STB_GLOBAL | STT_OBJECT */
    w16(symtab, 2*16 + 14, 0);          /* st_shndx */

    /* Layout:
     *   0x00: ELF header (52)
     *   0x34: .text
     *   text_end: .symtab (48 bytes)
     *   sym_end: .strtab (18 bytes)
     *   strtab_end: .shstrtab (50 bytes)
     *   (align): section headers (5 * 40)
     */
    size_t ehdr_size = 52;
    size_t text_off = ehdr_size;
    size_t symtab_off = text_off + text_code_size;
    size_t strtab_off = symtab_off + sizeof(symtab);
    size_t shstrtab_off = strtab_off + sym_strtab_size;
    size_t shdr_off = (shstrtab_off + SHSTRTAB_SIZE + 3) & ~(size_t)3;
    size_t shdr_entry_size = 40;
    size_t section_count = 5;  /* NULL, .text, .symtab, .strtab, .shstrtab */
    size_t total = shdr_off + section_count * shdr_entry_size;

    uint8_t* buf = calloc(1, total);
    if (!buf) return NULL;

    /* ELF header */
    buf[0] = 0x7F; buf[1] = 'E'; buf[2] = 'L'; buf[3] = 'F';
    buf[4] = 1; buf[5] = 1; buf[6] = 1;
    w16(buf, 16, 2);     /* ET_EXEC */
    w16(buf, 18, 3);     /* EM_386 */
    w32(buf, 20, 1);
    w32(buf, 24, 0x08048000);
    w32(buf, 32, (uint32_t)shdr_off);
    w16(buf, 40, (uint16_t)ehdr_size);
    w16(buf, 46, (uint16_t)shdr_entry_size);
    w16(buf, 48, (uint16_t)section_count);
    w16(buf, 50, 4);     /* e_shstrndx = section 4 */

    /* Section data */
    memcpy(buf + text_off, text_code, text_code_size);
    memcpy(buf + symtab_off, symtab, sizeof(symtab));
    memcpy(buf + strtab_off, sym_strtab, sym_strtab_size);
    memcpy(buf + shstrtab_off, shstrtab_data, SHSTRTAB_SIZE);

    /* Section headers */
    /* [0] NULL */
    /* [1] .text */
    size_t sh = shdr_off + 1 * shdr_entry_size;
    w32(buf, sh + 0, SHSTR_TEXT);
    w32(buf, sh + 4, 1);            /* SHT_PROGBITS */
    w32(buf, sh + 8, 4 | 2);        /* SHF_EXECINSTR | SHF_ALLOC */
    w32(buf, sh + 12, 0x08048000);
    w32(buf, sh + 16, (uint32_t)text_off);
    w32(buf, sh + 20, (uint32_t)text_code_size);

    /* [2] .symtab */
    sh = shdr_off + 2 * shdr_entry_size;
    w32(buf, sh + 0, SHSTR_SYMTAB);
    w32(buf, sh + 4, 2);            /* SHT_SYMTAB */
    w32(buf, sh + 16, (uint32_t)symtab_off);
    w32(buf, sh + 20, (uint32_t)sizeof(symtab));
    w32(buf, sh + 24, 3);           /* sh_link = section 3 (.strtab) */
    w32(buf, sh + 36, (uint32_t)sym_entry_size); /* sh_entsize */

    /* [3] .strtab */
    sh = shdr_off + 3 * shdr_entry_size;
    w32(buf, sh + 0, SHSTR_STRTAB);
    w32(buf, sh + 4, 3);            /* SHT_STRTAB */
    w32(buf, sh + 16, (uint32_t)strtab_off);
    w32(buf, sh + 20, (uint32_t)sym_strtab_size);

    /* [4] .shstrtab */
    sh = shdr_off + 4 * shdr_entry_size;
    w32(buf, sh + 0, SHSTR_SHSTRTAB);
    w32(buf, sh + 4, 3);            /* SHT_STRTAB */
    w32(buf, sh + 16, (uint32_t)shstrtab_off);
    w32(buf, sh + 20, SHSTRTAB_SIZE);

    *out_size = total;
    (void)sym_count;
    return buf;
}

/* Build an ELF64 shared library with .dynamic + .dynstr sections. */
static uint8_t* build_elf64_with_dynamic(size_t* out_size,
                                           const uint8_t* text_code,
                                           size_t text_code_size) {
    /* Dynamic string table: "\0libc.so.6\0libm.so.6" + trailing NUL */
    const char dyn_strtab[] = "\0libc.so.6\0libm.so.6";
    size_t dyn_strtab_size = sizeof(dyn_strtab);

    /* Dynamic section: DT_NEEDED(1)=1, DT_NEEDED(1)=11, DT_NULL */
    size_t dyn_entry_size = 16;  /* ELF64 */
    uint8_t dynamic[48];  /* 3 entries * 16 */
    memset(dynamic, 0, sizeof(dynamic));
    w64(dynamic, 0, 1);   /* DT_NEEDED */
    w64(dynamic, 8, 1);   /* offset into dynstr: "libc.so.6" */
    w64(dynamic, 16, 1);  /* DT_NEEDED */
    w64(dynamic, 24, 11); /* offset into dynstr: "libm.so.6" */
    /* [2] DT_NULL (all zeros) */

    size_t ehdr_size = 64;
    size_t text_off = ehdr_size;
    size_t dynamic_off = text_off + text_code_size;
    size_t dynstr_off = dynamic_off + sizeof(dynamic);
    size_t shstrtab_off = dynstr_off + dyn_strtab_size;
    size_t shdr_off = (shstrtab_off + SHSTRTAB_SIZE + 7) & ~(size_t)7;
    size_t shdr_entry_size = 64;
    size_t section_count = 5;  /* NULL, .text, .dynamic, .dynstr, .shstrtab */
    size_t total = shdr_off + section_count * shdr_entry_size;

    uint8_t* buf = calloc(1, total);
    if (!buf) return NULL;

    /* ELF header */
    buf[0] = 0x7F; buf[1] = 'E'; buf[2] = 'L'; buf[3] = 'F';
    buf[4] = 2; buf[5] = 1; buf[6] = 1;
    w16(buf, 16, 3);      /* ET_DYN */
    w16(buf, 18, 62);     /* EM_X86_64 */
    w32(buf, 20, 1);
    w64(buf, 24, 0x1000); /* e_entry */
    w64(buf, 40, (uint64_t)shdr_off);
    w16(buf, 52, (uint16_t)ehdr_size);
    w16(buf, 58, (uint16_t)shdr_entry_size);
    w16(buf, 60, (uint16_t)section_count);
    w16(buf, 62, 4);      /* e_shstrndx = section 4 */

    /* Section data */
    memcpy(buf + text_off, text_code, text_code_size);
    memcpy(buf + dynamic_off, dynamic, sizeof(dynamic));
    memcpy(buf + dynstr_off, dyn_strtab, dyn_strtab_size);
    memcpy(buf + shstrtab_off, shstrtab_data, SHSTRTAB_SIZE);

    /* Section headers */
    /* [1] .text */
    size_t sh = shdr_off + 1 * shdr_entry_size;
    w32(buf, sh + 0, SHSTR_TEXT);
    w32(buf, sh + 4, 1);         /* SHT_PROGBITS */
    w64(buf, sh + 8, 4 | 2);
    w64(buf, sh + 16, 0x1000);
    w64(buf, sh + 24, (uint64_t)text_off);
    w64(buf, sh + 32, (uint64_t)text_code_size);

    /* [2] .dynamic */
    sh = shdr_off + 2 * shdr_entry_size;
    w32(buf, sh + 0, SHSTR_DYNAMIC);
    w32(buf, sh + 4, 6);         /* SHT_DYNAMIC */
    w64(buf, sh + 24, (uint64_t)dynamic_off);
    w64(buf, sh + 32, (uint64_t)sizeof(dynamic));
    w32(buf, sh + 40, 3);        /* sh_link = section 3 (.dynstr) */
    w64(buf, sh + 56, dyn_entry_size); /* sh_entsize */

    /* [3] .dynstr */
    sh = shdr_off + 3 * shdr_entry_size;
    w32(buf, sh + 0, SHSTR_DYNSTR);
    w32(buf, sh + 4, 3);         /* SHT_STRTAB */
    w64(buf, sh + 24, (uint64_t)dynstr_off);
    w64(buf, sh + 32, (uint64_t)dyn_strtab_size);

    /* [4] .shstrtab */
    sh = shdr_off + 4 * shdr_entry_size;
    w32(buf, sh + 0, SHSTR_SHSTRTAB);
    w32(buf, sh + 4, 3);
    w64(buf, sh + 24, (uint64_t)shstrtab_off);
    w64(buf, sh + 32, SHSTRTAB_SIZE);

    *out_size = total;
    return buf;
}

/* ============================================================================
 * Tests
 * ============================================================================ */

static void test_elf_load_null(void) {
    TEST(elf_load_null);
    elf_context_t ctx;
    if (elf_load(&ctx, NULL, 0) == 0)
        FAIL("should reject NULL data");
    if (elf_load(NULL, (uint8_t*)"x", 1) == 0)
        FAIL("should reject NULL ctx");
    PASS();
}

static void test_elf_load_too_small(void) {
    TEST(elf_load_too_small);
    uint8_t tiny[] = {0x7F, 'E', 'L'};  /* incomplete magic */
    elf_context_t ctx;
    if (elf_load(&ctx, tiny, sizeof(tiny)) == 0)
        FAIL("should reject undersized data");
    PASS();
}

static void test_elf_load_bad_magic(void) {
    TEST(elf_load_bad_magic);
    uint8_t bad[64];
    memset(bad, 0, sizeof(bad));
    bad[0] = 0x7F; bad[1] = 'X'; bad[2] = 'L'; bad[3] = 'F';
    bad[4] = 1; bad[5] = 1; bad[6] = 1;
    elf_context_t ctx;
    if (elf_load(&ctx, bad, sizeof(bad)) == 0)
        FAIL("should reject bad magic");
    PASS();
}

static void test_elf_load_big_endian(void) {
    TEST(elf_load_big_endian);
    uint8_t be[64];
    memset(be, 0, sizeof(be));
    be[0] = 0x7F; be[1] = 'E'; be[2] = 'L'; be[3] = 'F';
    be[4] = 1;  /* 32-bit */
    be[5] = 2;  /* big-endian */
    be[6] = 1;
    elf_context_t ctx;
    if (elf_load(&ctx, be, sizeof(be)) == 0)
        FAIL("should reject big-endian");
    PASS();
}

static void test_elf32_minimal(void) {
    TEST(elf32_minimal);
    /* x86 code: IN AL,0x60; OUT 0x61,AL; RET */
    uint8_t text[] = {0xE4, 0x60, 0xE6, 0x61, 0xC3};
    size_t elf_size;
    uint8_t* elf = build_elf32_minimal(&elf_size, 0x08048000, text, sizeof(text));
    if (!elf) FAIL("build failed");

    elf_context_t ctx;
    if (elf_load(&ctx, elf, elf_size) != 0) {
        free(elf);
        FAIL("elf_load failed");
    }

    if (ctx.is_64bit) { free(elf); FAIL("should be 32-bit"); }
    if (ctx.machine != 3) { free(elf); FAIL("wrong machine"); }
    if (ctx.file_type != 2) { free(elf); FAIL("wrong type"); }
    if (ctx.entry_point != 0x08048000) { free(elf); FAIL("wrong entry"); }
    if (!ctx.text_data) { free(elf); FAIL("no .text data"); }
    if (ctx.text_size != sizeof(text)) { free(elf); FAIL("wrong .text size"); }
    if (memcmp(ctx.text_data, text, sizeof(text)) != 0) {
        free(elf);
        FAIL(".text content mismatch");
    }
    if (ctx.text_vaddr != 0x08048000) { free(elf); FAIL("wrong .text vaddr"); }

    elf_cleanup(&ctx);
    free(elf);
    PASS();
}

static void test_elf64_minimal(void) {
    TEST(elf64_minimal);
    /* x86-64 code: XOR EAX,EAX; RET */
    uint8_t text[] = {0x31, 0xC0, 0xC3};
    size_t elf_size;
    uint8_t* elf = build_elf64_minimal(&elf_size, 0x400000, text, sizeof(text));
    if (!elf) FAIL("build failed");

    elf_context_t ctx;
    if (elf_load(&ctx, elf, elf_size) != 0) {
        free(elf);
        FAIL("elf_load failed");
    }

    if (!ctx.is_64bit) { free(elf); FAIL("should be 64-bit"); }
    if (ctx.machine != 62) { free(elf); FAIL("wrong machine"); }
    if (ctx.file_type != 3) { free(elf); FAIL("should be ET_DYN"); }
    if (ctx.entry_point != 0x400000) { free(elf); FAIL("wrong entry"); }
    if (!ctx.text_data) { free(elf); FAIL("no .text data"); }
    if (ctx.text_size != sizeof(text)) { free(elf); FAIL("wrong .text size"); }
    if (ctx.text_vaddr != 0x400000) { free(elf); FAIL("wrong .text vaddr"); }

    elf_cleanup(&ctx);
    free(elf);
    PASS();
}

static void test_elf32_symbols(void) {
    TEST(elf32_symbols);
    uint8_t text[] = {0xC3};
    size_t elf_size;
    uint8_t* elf = build_elf32_with_symbols(&elf_size, text, sizeof(text));
    if (!elf) FAIL("build failed");

    elf_context_t ctx;
    if (elf_load(&ctx, elf, elf_size) != 0) {
        free(elf);
        FAIL("elf_load failed");
    }

    if (ctx.symbol_count < 2) {
        char msg[64];
        snprintf(msg, sizeof(msg), "expected 2 symbols, got %zu", ctx.symbol_count);
        free(elf);
        FAIL(msg);
    }

    /* Find _start */
    bool found_start = false;
    bool found_data = false;
    for (size_t i = 0; i < ctx.symbol_count; i++) {
        if (ctx.symbols[i].name && strcmp(ctx.symbols[i].name, "_start") == 0) {
            found_start = true;
            if (ctx.symbols[i].type != STT_FUNC) {
                free(elf); FAIL("_start should be STT_FUNC");
            }
            if (ctx.symbols[i].value != 0x08048000) {
                free(elf); FAIL("_start wrong value");
            }
        }
        if (ctx.symbols[i].name && strcmp(ctx.symbols[i].name, "data_val") == 0) {
            found_data = true;
            if (ctx.symbols[i].bind != STB_GLOBAL) {
                free(elf); FAIL("data_val should be STB_GLOBAL");
            }
        }
    }

    if (!found_start) { free(elf); FAIL("_start not found"); }
    if (!found_data) { free(elf); FAIL("data_val not found"); }

    elf_cleanup(&ctx);
    free(elf);
    PASS();
}

static void test_elf64_dynamic(void) {
    TEST(elf64_dynamic);
    uint8_t text[] = {0xC3};
    size_t elf_size;
    uint8_t* elf = build_elf64_with_dynamic(&elf_size, text, sizeof(text));
    if (!elf) FAIL("build failed");

    elf_context_t ctx;
    if (elf_load(&ctx, elf, elf_size) != 0) {
        free(elf);
        FAIL("elf_load failed");
    }

    if (ctx.needed_count != 2) {
        char msg[64];
        snprintf(msg, sizeof(msg), "expected 2 needed, got %zu", ctx.needed_count);
        free(elf);
        FAIL(msg);
    }

    bool found_libc = false, found_libm = false;
    for (size_t i = 0; i < ctx.needed_count; i++) {
        if (ctx.needed[i].lib_name) {
            if (strcmp(ctx.needed[i].lib_name, "libc.so.6") == 0) found_libc = true;
            if (strcmp(ctx.needed[i].lib_name, "libm.so.6") == 0) found_libm = true;
        }
    }

    if (!found_libc) { free(elf); FAIL("libc.so.6 not found"); }
    if (!found_libm) { free(elf); FAIL("libm.so.6 not found"); }

    elf_cleanup(&ctx);
    free(elf);
    PASS();
}

static void test_elf_cleanup_idempotent(void) {
    TEST(elf_cleanup_idempotent);
    uint8_t text[] = {0xC3};
    size_t elf_size;
    uint8_t* elf = build_elf32_minimal(&elf_size, 0x08048000, text, sizeof(text));
    if (!elf) FAIL("build failed");

    elf_context_t ctx;
    elf_load(&ctx, elf, elf_size);
    elf_cleanup(&ctx);
    elf_cleanup(&ctx);  /* double-free should not crash */
    elf_cleanup(NULL);   /* NULL should not crash */
    free(elf);
    PASS();
}

static void test_elf_print_info(void) {
    TEST(elf_print_info);
    uint8_t text[] = {0xC3};
    size_t elf_size;
    uint8_t* elf = build_elf32_with_symbols(&elf_size, text, sizeof(text));
    if (!elf) FAIL("build failed");

    elf_context_t ctx;
    elf_load(&ctx, elf, elf_size);

    /* Print to /dev/null — just verify no crash */
    FILE* null_f = fopen("/dev/null", "w");
    if (null_f) {
        elf_print_info(&ctx, null_f);
        fclose(null_f);
    }
    elf_print_info(NULL, stderr);  /* NULL ctx */
    elf_print_info(&ctx, NULL);    /* NULL out */

    elf_cleanup(&ctx);
    free(elf);
    PASS();
}

static void test_elf_no_section_headers(void) {
    TEST(elf_no_section_headers);
    /* Minimal ELF32 header with e_shnum=0 — stripped binary */
    uint8_t hdr[52];
    memset(hdr, 0, sizeof(hdr));
    hdr[0] = 0x7F; hdr[1] = 'E'; hdr[2] = 'L'; hdr[3] = 'F';
    hdr[4] = 1; hdr[5] = 1; hdr[6] = 1;
    w16(hdr, 16, 2);  /* ET_EXEC */
    w16(hdr, 18, 3);  /* EM_386 */
    w32(hdr, 20, 1);
    w32(hdr, 24, 0x08048000); /* e_entry */
    /* e_shoff=0, e_shnum=0 — no sections */

    elf_context_t ctx;
    if (elf_load(&ctx, hdr, sizeof(hdr)) != 0)
        FAIL("should accept ELF with no section headers");
    if (ctx.text_data != NULL)
        FAIL("should have no .text");
    if (ctx.symbol_count != 0)
        FAIL("should have no symbols");
    if (ctx.entry_point != 0x08048000)
        FAIL("wrong entry point");

    elf_cleanup(&ctx);
    PASS();
}

static void test_elf32_port_io_code(void) {
    TEST(elf32_port_io_code);
    /* IN AL, 0x3F8; OUT 0x3F8, AL; IN AX, DX; OUT DX, AL; HLT */
    uint8_t text[] = {
        0xE4, 0xF8,       /* IN AL, 0xF8 (only low byte: port 0xF8) */
        0xE6, 0xF8,       /* OUT 0xF8, AL */
        0xEC,             /* IN AL, DX */
        0xEE,             /* OUT DX, AL */
        0xF4              /* HLT */
    };
    size_t elf_size;
    uint8_t* elf = build_elf32_minimal(&elf_size, 0x08048000, text, sizeof(text));
    if (!elf) FAIL("build failed");

    elf_context_t ctx;
    if (elf_load(&ctx, elf, elf_size) != 0) {
        free(elf);
        FAIL("elf_load failed");
    }

    if (ctx.text_size != sizeof(text)) {
        free(elf);
        FAIL("wrong .text size");
    }

    /* Verify the code content — we'll decode it downstream */
    if (ctx.text_data[0] != 0xE4 || ctx.text_data[1] != 0xF8) {
        free(elf);
        FAIL("port I/O code content mismatch");
    }

    elf_cleanup(&ctx);
    free(elf);
    PASS();
}

static void test_elf_unsupported_machine(void) {
    TEST(elf_unsupported_machine);
    uint8_t hdr[52];
    memset(hdr, 0, sizeof(hdr));
    hdr[0] = 0x7F; hdr[1] = 'E'; hdr[2] = 'L'; hdr[3] = 'F';
    hdr[4] = 1; hdr[5] = 1; hdr[6] = 1;
    w16(hdr, 16, 2);   /* ET_EXEC */
    w16(hdr, 18, 183);  /* EM_AARCH64 (not supported) */
    w32(hdr, 20, 1);

    elf_context_t ctx;
    if (elf_load(&ctx, hdr, sizeof(hdr)) == 0)
        FAIL("should reject non-x86 machine");
    PASS();
}

/* ============================================================================
 * Main
 * ============================================================================ */

int main(void) {
    printf("ELF Loader Tests\n");
    printf("================\n");

    test_elf_load_null();
    test_elf_load_too_small();
    test_elf_load_bad_magic();
    test_elf_load_big_endian();
    test_elf32_minimal();
    test_elf64_minimal();
    test_elf32_symbols();
    test_elf64_dynamic();
    test_elf_cleanup_idempotent();
    test_elf_print_info();
    test_elf_no_section_headers();
    test_elf32_port_io_code();
    test_elf_unsupported_machine();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);
    return tests_passed == tests_run ? 0 : 1;
}
