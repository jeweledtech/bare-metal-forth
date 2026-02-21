/* ============================================================================
 * PE Loader Tests
 * ============================================================================
 *
 * Builds synthetic PE files in memory and validates the parser.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include "../include/pe_loader.h"
#include "../include/pe_format.h"

/* Build a minimal valid PE32 file in memory for testing.
 * Contains: DOS header, PE signature, COFF header, optional header,
 * one .text section with a single RET instruction. */
static uint8_t* build_test_pe(size_t* out_size) {
    /* Layout:
     * 0x000: DOS header (64 bytes, e_lfanew = 0x40)
     * 0x040: PE signature (4 bytes)
     * 0x044: COFF header (20 bytes)
     * 0x058: Optional header PE32 (96 bytes + 16 data dir entries * 8 = 224)
     * 0x138: Section table: 1 entry (40 bytes)
     * 0x160: Padding to 0x200 (file alignment)
     * 0x200: .text section data: C3 (RET)
     */
    size_t file_size = 0x400;
    uint8_t* buf = calloc(1, file_size);

    /* DOS header */
    dos_header_t* dos = (dos_header_t*)buf;
    dos->e_magic = DOS_MAGIC;
    dos->e_lfanew = 0x40;

    /* PE signature */
    *(uint32_t*)(buf + 0x40) = PE_SIGNATURE;

    /* COFF header */
    coff_header_t* coff = (coff_header_t*)(buf + 0x44);
    coff->machine = COFF_MACHINE_I386;
    coff->number_of_sections = 1;
    coff->size_of_optional_header = 224;  /* 96 + 16*8 */

    /* PE32 Optional header */
    pe32_optional_header_t* opt = (pe32_optional_header_t*)(buf + 0x58);
    opt->magic = PE_OPT_MAGIC_PE32;
    opt->address_of_entry_point = 0x1000;
    opt->image_base = 0x10000;
    opt->section_alignment = 0x1000;
    opt->file_alignment = 0x200;
    opt->size_of_image = 0x3000;
    opt->size_of_headers = 0x200;
    opt->number_of_rva_and_sizes = 16;

    /* Section header for .text at offset 0x138
     * (0x58 + 224 = 0x58 + 0xE0 = 0x138) */
    section_header_t* sec = (section_header_t*)(buf + 0x138);
    memcpy(sec->name, ".text\0\0\0", 8);
    sec->virtual_size = 1;
    sec->virtual_address = 0x1000;
    sec->size_of_raw_data = 0x200;
    sec->pointer_to_raw_data = 0x200;
    sec->characteristics = SECTION_CNT_CODE | SECTION_MEM_EXECUTE | SECTION_MEM_READ;

    /* .text data: single RET instruction */
    buf[0x200] = 0xC3;

    *out_size = file_size;
    return buf;
}

/* Build a PE32 with imports for testing import parsing */
static uint8_t* build_test_pe_with_imports(size_t* out_size) {
    size_t file_size = 0x800;
    uint8_t* buf = calloc(1, file_size);

    /* DOS header */
    dos_header_t* dos = (dos_header_t*)buf;
    dos->e_magic = DOS_MAGIC;
    dos->e_lfanew = 0x40;

    /* PE signature */
    *(uint32_t*)(buf + 0x40) = PE_SIGNATURE;

    /* COFF header */
    coff_header_t* coff = (coff_header_t*)(buf + 0x44);
    coff->machine = COFF_MACHINE_I386;
    coff->number_of_sections = 2;
    coff->size_of_optional_header = 224;

    /* PE32 Optional header */
    pe32_optional_header_t* opt = (pe32_optional_header_t*)(buf + 0x58);
    opt->magic = PE_OPT_MAGIC_PE32;
    opt->address_of_entry_point = 0x1000;
    opt->image_base = 0x10000;
    opt->section_alignment = 0x1000;
    opt->file_alignment = 0x200;
    opt->size_of_image = 0x4000;
    opt->size_of_headers = 0x200;
    opt->number_of_rva_and_sizes = 16;

    /* Data directory: import table at RVA 0x2000 */
    data_directory_t* dirs = (data_directory_t*)(buf + 0x58 + 96);
    dirs[DATA_DIR_IMPORT].virtual_address = 0x2000;
    dirs[DATA_DIR_IMPORT].size = sizeof(import_descriptor_t) * 2; /* 1 DLL + terminator */

    /* Section headers at 0x138 */
    section_header_t* sec_text = (section_header_t*)(buf + 0x138);
    memcpy(sec_text->name, ".text\0\0\0", 8);
    sec_text->virtual_size = 1;
    sec_text->virtual_address = 0x1000;
    sec_text->size_of_raw_data = 0x200;
    sec_text->pointer_to_raw_data = 0x200;
    sec_text->characteristics = SECTION_CNT_CODE | SECTION_MEM_EXECUTE | SECTION_MEM_READ;

    section_header_t* sec_idata = (section_header_t*)(buf + 0x138 + 40);
    memcpy(sec_idata->name, ".idata\0\0", 8);
    sec_idata->virtual_size = 0x200;
    sec_idata->virtual_address = 0x2000;
    sec_idata->size_of_raw_data = 0x200;
    sec_idata->pointer_to_raw_data = 0x400;
    sec_idata->characteristics = SECTION_CNT_INITIALIZED_DATA | SECTION_MEM_READ;

    /* .text data */
    buf[0x200] = 0xC3;

    /* .idata section at file offset 0x400, RVA 0x2000 */
    /* Import descriptor for "ntoskrnl.exe" */
    import_descriptor_t* imp = (import_descriptor_t*)(buf + 0x400);
    imp->name_rva = 0x2080;                    /* DLL name string */
    imp->import_lookup_table_rva = 0x20A0;     /* ILT */
    imp->import_address_table_rva = 0x20C0;    /* IAT */

    /* Terminator (all zeros) - already zeroed by calloc */

    /* DLL name at RVA 0x2080 = file offset 0x480 */
    strcpy((char*)(buf + 0x480), "ntoskrnl.exe");

    /* ILT at RVA 0x20A0 = file offset 0x4A0 */
    /* Entry 0: points to hint/name at RVA 0x20E0 */
    *(uint32_t*)(buf + 0x4A0) = 0x20E0;
    /* Entry 1: terminator (zero) - already zeroed */

    /* IAT at RVA 0x20C0 = file offset 0x4C0 */
    *(uint32_t*)(buf + 0x4C0) = 0x20E0;

    /* Hint/Name at RVA 0x20E0 = file offset 0x4E0 */
    *(uint16_t*)(buf + 0x4E0) = 0;  /* hint */
    strcpy((char*)(buf + 0x4E2), "READ_PORT_UCHAR");

    *out_size = file_size;
    return buf;
}

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) do { \
    tests_run++; \
    printf("  TEST: %-40s ", #name); \
} while(0)

#define PASS() do { tests_passed++; printf("PASS\n"); } while(0)
#define FAIL(msg) do { printf("FAIL: %s\n", msg); } while(0)

static void test_load_minimal_pe(void) {
    TEST(load_minimal_pe);
    size_t size;
    uint8_t* data = build_test_pe(&size);

    pe_context_t ctx;
    int rc = pe_load(&ctx, data, size);
    if (rc != 0) { FAIL("pe_load returned error"); free(data); return; }
    if (ctx.machine != COFF_MACHINE_I386) { FAIL("wrong machine type"); goto out; }
    if (ctx.image_base != 0x10000) { FAIL("wrong image base"); goto out; }
    if (ctx.entry_point_rva != 0x1000) { FAIL("wrong entry point"); goto out; }
    if (ctx.section_count != 1) { FAIL("wrong section count"); goto out; }
    if (ctx.is_64bit) { FAIL("should be 32-bit"); goto out; }
    PASS();
out:
    pe_cleanup(&ctx);
    free(data);
}

static void test_find_text_section(void) {
    TEST(find_text_section);
    size_t size;
    uint8_t* data = build_test_pe(&size);

    pe_context_t ctx;
    pe_load(&ctx, data, size);

    if (ctx.text_data == NULL) { FAIL("text_data is NULL"); goto out; }
    if (ctx.text_size == 0) { FAIL("text_size is 0"); goto out; }
    if (ctx.text_data[0] != 0xC3) { FAIL("first byte should be RET (0xC3)"); goto out; }

    const pe_section_t* sec = pe_find_section(&ctx, ".text");
    if (sec == NULL) { FAIL("pe_find_section returned NULL"); goto out; }
    PASS();
out:
    pe_cleanup(&ctx);
    free(data);
}

static void test_rva_to_ptr(void) {
    TEST(rva_to_ptr);
    size_t size;
    uint8_t* data = build_test_pe(&size);

    pe_context_t ctx;
    pe_load(&ctx, data, size);

    const uint8_t* ptr = pe_rva_to_ptr(&ctx, 0x1000);
    if (ptr == NULL) { FAIL("rva_to_ptr returned NULL for .text RVA"); goto out; }
    if (*ptr != 0xC3) { FAIL("rva_to_ptr content wrong"); goto out; }

    const uint8_t* bad = pe_rva_to_ptr(&ctx, 0xFFFFFF);
    if (bad != NULL) { FAIL("rva_to_ptr should return NULL for bad RVA"); goto out; }
    PASS();
out:
    pe_cleanup(&ctx);
    free(data);
}

static void test_reject_invalid(void) {
    TEST(reject_invalid_data);
    pe_context_t ctx;

    /* Too small */
    uint8_t tiny[] = {0x4D, 0x5A};
    if (pe_load(&ctx, tiny, sizeof(tiny)) == 0) { FAIL("accepted too-small data"); return; }

    /* Wrong magic */
    uint8_t bad[256] = {0};
    bad[0] = 0xEE;
    if (pe_load(&ctx, bad, sizeof(bad)) == 0) { FAIL("accepted bad magic"); return; }

    PASS();
}

static void test_import_parsing(void) {
    TEST(import_parsing);
    size_t size;
    uint8_t* data = build_test_pe_with_imports(&size);

    pe_context_t ctx;
    int rc = pe_load(&ctx, data, size);
    if (rc != 0) { FAIL("pe_load returned error"); free(data); return; }
    if (ctx.import_count == 0) { FAIL("no imports found"); goto out; }

    const pe_import_t* imp = pe_find_import(&ctx, "READ_PORT_UCHAR");
    if (imp == NULL) { FAIL("READ_PORT_UCHAR not found"); goto out; }
    if (strcmp(imp->dll_name, "ntoskrnl.exe") != 0) { FAIL("wrong DLL name"); goto out; }
    PASS();
out:
    pe_cleanup(&ctx);
    free(data);
}

int main(void) {
    printf("PE Loader Tests\n");
    printf("===============\n");

    test_load_minimal_pe();
    test_find_text_section();
    test_rva_to_ptr();
    test_reject_invalid();
    test_import_parsing();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);
    return tests_passed == tests_run ? 0 : 1;
}
