/* ============================================================================
 * Format Detector Tests
 * ============================================================================
 *
 * Builds synthetic binary headers and validates format classification.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "../include/format_detect.h"
#include "../include/pe_format.h"

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) do { \
    tests_run++; \
    printf("  TEST: %-50s ", #name); \
} while(0)

#define PASS() do { tests_passed++; printf("PASS\n"); } while(0)
#define FAIL(msg) do { printf("FAIL: %s\n", msg); return; } while(0)

/* ============================================================================
 * Helper: build a minimal PE header in a buffer
 * ============================================================================ */

static uint8_t* build_pe_header(size_t* out_size, uint16_t characteristics,
                                 bool set_clr) {
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
    coff->size_of_optional_header = 224;
    coff->characteristics = characteristics;

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

    /* CLR data directory (entry 14) at opt_hdr + 96 + 14*8 = opt_hdr + 208 */
    if (set_clr) {
        uint8_t* clr_dir = (uint8_t*)opt + 96 + 14 * 8;
        /* CLR RVA = 0x2000, size = 72 */
        clr_dir[0] = 0x00; clr_dir[1] = 0x20; clr_dir[2] = 0x00; clr_dir[3] = 0x00;
        clr_dir[4] = 0x48; clr_dir[5] = 0x00; clr_dir[6] = 0x00; clr_dir[7] = 0x00;
    }

    /* .text section header */
    section_header_t* sec = (section_header_t*)(buf + 0x138);
    memcpy(sec->name, ".text\0\0\0", 8);
    sec->virtual_size = 0x100;
    sec->virtual_address = 0x1000;
    sec->size_of_raw_data = 0x200;
    sec->pointer_to_raw_data = 0x200;
    sec->characteristics = SECTION_CNT_CODE | SECTION_MEM_EXECUTE | SECTION_MEM_READ;

    /* .text content: single RET */
    buf[0x200] = 0xC3;

    *out_size = file_size;
    return buf;
}

/* ============================================================================
 * Tests
 * ============================================================================ */

static void test_detect_com(void) {
    TEST(detect_com);
    /* A small file without MZ or ELF header → DOS COM */
    uint8_t com[] = {0xE4, 0x60, 0xE6, 0x61, 0xC3};  /* IN AL,0x60; OUT 0x61,AL; RET */
    format_info_t info = detect_format(com, sizeof(com), "test.com");

    if (info.format != BINFMT_DOS_COM) {
        char msg[128];
        snprintf(msg, sizeof(msg), "expected BINFMT_DOS_COM, got %d", info.format);
        FAIL(msg);
    }
    PASS();
}

static void test_detect_com_no_extension(void) {
    TEST(detect_com_no_extension);
    /* COM detection should work even without .com extension */
    uint8_t com[] = {0xE4, 0x60, 0xC3};
    format_info_t info = detect_format(com, sizeof(com), NULL);

    if (info.format != BINFMT_DOS_COM)
        FAIL("expected BINFMT_DOS_COM without filename");
    PASS();
}

static void test_detect_pe_sys(void) {
    TEST(detect_pe_sys);
    size_t size;
    uint8_t* pe = build_pe_header(&size, 0x1000, false);  /* IMAGE_FILE_SYSTEM */
    format_info_t info = detect_format(pe, size, "driver.sys");

    if (info.format != BINFMT_PE_DRIVER) {
        char msg[128];
        snprintf(msg, sizeof(msg), "expected BINFMT_PE_DRIVER, got %d", info.format);
        free(pe);
        FAIL(msg);
    }
    free(pe);
    PASS();
}

static void test_detect_pe_sys_by_extension(void) {
    TEST(detect_pe_sys_by_extension);
    /* PE without IMAGE_FILE_SYSTEM but with .sys extension → driver */
    size_t size;
    uint8_t* pe = build_pe_header(&size, 0, false);  /* no special flags */
    format_info_t info = detect_format(pe, size, "i8042prt.sys");

    if (info.format != BINFMT_PE_DRIVER) {
        free(pe);
        FAIL("expected BINFMT_PE_DRIVER from .sys extension");
    }
    free(pe);
    PASS();
}

static void test_detect_pe_dll(void) {
    TEST(detect_pe_dll);
    size_t size;
    uint8_t* pe = build_pe_header(&size, 0x2000, false);  /* IMAGE_FILE_DLL */
    format_info_t info = detect_format(pe, size, "kernel32.dll");

    if (info.format != BINFMT_PE_DLL) {
        char msg[128];
        snprintf(msg, sizeof(msg), "expected BINFMT_PE_DLL, got %d", info.format);
        free(pe);
        FAIL(msg);
    }
    free(pe);
    PASS();
}

static void test_detect_pe_exe(void) {
    TEST(detect_pe_exe);
    size_t size;
    uint8_t* pe = build_pe_header(&size, 0, false);  /* no DLL or SYSTEM flag */
    format_info_t info = detect_format(pe, size, "program.exe");

    if (info.format != BINFMT_PE_EXE) {
        char msg[128];
        snprintf(msg, sizeof(msg), "expected BINFMT_PE_EXE, got %d", info.format);
        free(pe);
        FAIL(msg);
    }
    free(pe);
    PASS();
}

static void test_detect_dotnet(void) {
    TEST(detect_dotnet);
    size_t size;
    uint8_t* pe = build_pe_header(&size, 0x2000, true);  /* DLL + CLR */
    format_info_t info = detect_format(pe, size, "managed.dll");

    if (info.format != BINFMT_DOTNET) {
        char msg[128];
        snprintf(msg, sizeof(msg), "expected BINFMT_DOTNET, got %d", info.format);
        free(pe);
        FAIL(msg);
    }
    if (!info.is_dotnet) {
        free(pe);
        FAIL("is_dotnet should be true");
    }
    free(pe);
    PASS();
}

static void test_detect_elf(void) {
    TEST(detect_elf);
    uint8_t elf[] = {0x7F, 'E', 'L', 'F', 1, 0};  /* ELF32 */
    format_info_t info = detect_format(elf, sizeof(elf), "binary");

    if (info.format != BINFMT_ELF)
        FAIL("expected BINFMT_ELF");
    if (info.is_64bit)
        FAIL("expected 32-bit ELF");
    PASS();
}

static void test_detect_elf64(void) {
    TEST(detect_elf64);
    uint8_t elf[] = {0x7F, 'E', 'L', 'F', 2, 0};  /* ELF64 */
    format_info_t info = detect_format(elf, sizeof(elf), NULL);

    if (info.format != BINFMT_ELF)
        FAIL("expected BINFMT_ELF");
    if (!info.is_64bit)
        FAIL("expected 64-bit ELF");
    PASS();
}

static void test_detect_unknown(void) {
    TEST(detect_unknown);
    /* Large random-ish data: too big for COM, no valid header */
    uint8_t* big = calloc(1, 70000);
    big[0] = 0xFF;
    big[1] = 0xFF;
    format_info_t info = detect_format(big, 70000, NULL);
    free(big);

    if (info.format != BINFMT_UNKNOWN)
        FAIL("expected BINFMT_UNKNOWN for large non-header data");
    PASS();
}

static void test_detect_null(void) {
    TEST(detect_null);
    format_info_t info = detect_format(NULL, 0, NULL);
    if (info.format != BINFMT_UNKNOWN)
        FAIL("expected BINFMT_UNKNOWN for NULL data");
    PASS();
}

static void test_binfmt_name(void) {
    TEST(binfmt_name);
    if (strcmp(binfmt_name(BINFMT_PE_DRIVER), "PE driver") != 0)
        FAIL("BINFMT_PE_DRIVER name wrong");
    if (strcmp(binfmt_name(BINFMT_DOS_COM), "DOS COM") != 0)
        FAIL("BINFMT_DOS_COM name wrong");
    if (strcmp(binfmt_name(BINFMT_DOTNET), ".NET") != 0)
        FAIL("BINFMT_DOTNET name wrong");
    PASS();
}

/* ============================================================================
 * Main
 * ============================================================================ */

int main(void) {
    printf("Format Detector Tests\n");
    printf("=====================\n");

    test_detect_com();
    test_detect_com_no_extension();
    test_detect_pe_sys();
    test_detect_pe_sys_by_extension();
    test_detect_pe_dll();
    test_detect_pe_exe();
    test_detect_dotnet();
    test_detect_elf();
    test_detect_elf64();
    test_detect_unknown();
    test_detect_null();
    test_binfmt_name();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);
    return tests_passed == tests_run ? 0 : 1;
}
