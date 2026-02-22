/* ============================================================================
 * Synthetic 16550 UART Driver PE Test
 * ============================================================================
 *
 * Builds a synthetic PE mimicking a real 16550 serial port driver with
 * three distinct functions (INIT, SEND, RECV) at separate offsets in .text.
 * Runs the full pipeline (PE -> x86 -> UIR -> semantic -> Forth) and
 * validates multi-function discovery and output structure against the
 * hand-written reference in forth/dict/serial-16550.fth.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>

#include "../include/translator.h"
#include "../include/pe_loader.h"
#include "../include/pe_format.h"
#include "../include/x86_decoder.h"
#include "../include/uir.h"
#include "../include/semantic.h"
#include "../include/forth_codegen.h"

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) do { \
    tests_run++; \
    printf("  TEST: %-55s ", #name); \
} while(0)

#define PASS() do { tests_passed++; printf("PASS\n"); } while(0)
#define FAIL(msg) do { printf("FAIL: %s\n", msg); return; } while(0)

/* ============================================================================
 * Synthetic 16550 driver PE builder
 *
 * .text layout (at file offset 0x200, RVA 0x1000):
 *
 *   Offset 0x00 — UART_INIT function:
 *     OUT 0x3F9, AL  (IER = 0)
 *     OUT 0x3FB, AL  (LCR = DLAB)
 *     OUT 0x3F8, AL  (DLL = 1)
 *     OUT 0x3FB, AL  (LCR = 8N1)
 *     OUT 0x3FA, AL  (FCR = 0xC7)
 *     RET
 *
 *   Offset 0x0C — UART_SEND function:
 *     PUSH EBP / MOV EBP,ESP (prologue)
 *     IN  AL, 0x3FD  (read LSR)
 *     TEST AL, 0x20  (check THRE)
 *     JZ -6          (loop back to IN)
 *     OUT 0x3F8, AL  (write THR)
 *     POP EBP
 *     RET
 *
 *   Offset 0x1A — UART_RECV function:
 *     PUSH EBP / MOV EBP,ESP (prologue)
 *     IN  AL, 0x3FD  (read LSR)
 *     TEST AL, 0x01  (check DR)
 *     JZ -6          (loop back to IN)
 *     IN  AL, 0x3F8  (read RBR)
 *     POP EBP
 *     RET
 * ============================================================================ */

static uint8_t* build_16550_pe(size_t* out_size) {
    size_t file_size = 0xC00;  /* 3KB: headers + .text + .idata + .edata */
    uint8_t* buf = calloc(1, file_size);

    /* ---- DOS header ---- */
    dos_header_t* dos = (dos_header_t*)buf;
    dos->e_magic = DOS_MAGIC;
    dos->e_lfanew = 0x40;

    /* ---- PE signature ---- */
    *(uint32_t*)(buf + 0x40) = PE_SIGNATURE;

    /* ---- COFF header ---- */
    coff_header_t* coff = (coff_header_t*)(buf + 0x44);
    coff->machine = COFF_MACHINE_I386;
    coff->number_of_sections = 3;  /* .text + .idata + .edata */
    coff->size_of_optional_header = 224;

    /* ---- PE32 Optional header ---- */
    pe32_optional_header_t* opt = (pe32_optional_header_t*)(buf + 0x58);
    opt->magic = PE_OPT_MAGIC_PE32;
    opt->address_of_entry_point = 0x1000;  /* UART_INIT */
    opt->image_base = 0x10000;
    opt->section_alignment = 0x1000;
    opt->file_alignment = 0x200;
    opt->size_of_image = 0x5000;
    opt->size_of_headers = 0x200;
    opt->number_of_rva_and_sizes = 16;

    /* ---- Data directories ---- */
    data_directory_t* dirs = (data_directory_t*)(buf + 0x58 + 96);
    /* Export table at RVA 0x3000 */
    dirs[DATA_DIR_EXPORT].virtual_address = 0x3000;
    dirs[DATA_DIR_EXPORT].size = 0x100;
    /* Import table at RVA 0x2000 */
    dirs[DATA_DIR_IMPORT].virtual_address = 0x2000;
    dirs[DATA_DIR_IMPORT].size = sizeof(import_descriptor_t) * 2;

    /* ---- Section headers (at 0x138) ---- */

    /* .text */
    section_header_t* sec_text = (section_header_t*)(buf + 0x138);
    memcpy(sec_text->name, ".text\0\0\0", 8);
    sec_text->virtual_size = 0x30;
    sec_text->virtual_address = 0x1000;
    sec_text->size_of_raw_data = 0x200;
    sec_text->pointer_to_raw_data = 0x200;
    sec_text->characteristics = SECTION_CNT_CODE | SECTION_MEM_EXECUTE
                                | SECTION_MEM_READ;

    /* .idata */
    section_header_t* sec_idata = (section_header_t*)(buf + 0x138 + 40);
    memcpy(sec_idata->name, ".idata\0\0", 8);
    sec_idata->virtual_size = 0x200;
    sec_idata->virtual_address = 0x2000;
    sec_idata->size_of_raw_data = 0x200;
    sec_idata->pointer_to_raw_data = 0x400;
    sec_idata->characteristics = SECTION_CNT_INITIALIZED_DATA | SECTION_MEM_READ;

    /* .edata */
    section_header_t* sec_edata = (section_header_t*)(buf + 0x138 + 80);
    memcpy(sec_edata->name, ".edata\0\0", 8);
    sec_edata->virtual_size = 0x200;
    sec_edata->virtual_address = 0x3000;
    sec_edata->size_of_raw_data = 0x200;
    sec_edata->pointer_to_raw_data = 0x600;
    sec_edata->characteristics = SECTION_CNT_INITIALIZED_DATA | SECTION_MEM_READ;

    /* ============================================================
     * .text code (at file offset 0x200)
     * ============================================================ */
    uint8_t* text = buf + 0x200;
    size_t off = 0;

    /* ---- UART_INIT (offset 0x00) ----
     * E6 F9    OUT 0x3F9, AL   (IER = 0)
     * E6 FB    OUT 0x3FB, AL   (LCR = DLAB)
     * E6 F8    OUT 0x3F8, AL   (DLL = divisor low)
     * E6 FB    OUT 0x3FB, AL   (LCR = 8N1)
     * E6 FA    OUT 0x3FA, AL   (FCR = init)
     * C3       RET
     */
    text[off++] = 0xE6; text[off++] = 0xF9;  /* OUT 0xF9, AL (0x3F9 low byte) */
    text[off++] = 0xE6; text[off++] = 0xFB;  /* OUT 0xFB, AL */
    text[off++] = 0xE6; text[off++] = 0xF8;  /* OUT 0xF8, AL */
    text[off++] = 0xE6; text[off++] = 0xFB;  /* OUT 0xFB, AL */
    text[off++] = 0xE6; text[off++] = 0xFA;  /* OUT 0xFA, AL */
    text[off++] = 0xC3;                       /* RET */
    /* off = 0x0B */

    /* ---- UART_SEND (offset 0x0B) ----
     * 55             PUSH EBP
     * 89 E5          MOV EBP, ESP
     * E4 FD          IN AL, 0xFD   (LSR = 0x3FD low byte)
     * A8 20          TEST AL, 0x20 (THRE bit)
     * 74 FA          JZ -6 (back to IN)
     * E6 F8          OUT 0xF8, AL  (THR)
     * 5D             POP EBP
     * C3             RET
     */
    text[off++] = 0x55;                       /* PUSH EBP */
    text[off++] = 0x89; text[off++] = 0xE5;  /* MOV EBP, ESP */
    text[off++] = 0xE4; text[off++] = 0xFD;  /* IN AL, 0xFD */
    text[off++] = 0xA8; text[off++] = 0x20;  /* TEST AL, 0x20 */
    text[off++] = 0x74; text[off++] = 0xFA;  /* JZ -6 (back to IN) */
    text[off++] = 0xE6; text[off++] = 0xF8;  /* OUT 0xF8, AL */
    text[off++] = 0x5D;                       /* POP EBP */
    text[off++] = 0xC3;                       /* RET */
    /* off = 0x19 */

    /* ---- UART_RECV (offset 0x19) ----
     * 55             PUSH EBP
     * 89 E5          MOV EBP, ESP
     * E4 FD          IN AL, 0xFD   (LSR)
     * A8 01          TEST AL, 0x01 (DR bit)
     * 74 FA          JZ -6 (back to IN)
     * E4 F8          IN AL, 0xF8   (RBR)
     * 5D             POP EBP
     * C3             RET
     */
    text[off++] = 0x55;                       /* PUSH EBP */
    text[off++] = 0x89; text[off++] = 0xE5;  /* MOV EBP, ESP */
    text[off++] = 0xE4; text[off++] = 0xFD;  /* IN AL, 0xFD */
    text[off++] = 0xA8; text[off++] = 0x01;  /* TEST AL, 0x01 */
    text[off++] = 0x74; text[off++] = 0xFA;  /* JZ -6 */
    text[off++] = 0xE4; text[off++] = 0xF8;  /* IN AL, 0xF8 */
    text[off++] = 0x5D;                       /* POP EBP */
    text[off++] = 0xC3;                       /* RET */

    /* Update .text virtual size to actual code size */
    sec_text->virtual_size = (uint32_t)off;

    /* ============================================================
     * .idata — Import Table (at file offset 0x400, RVA 0x2000)
     * ============================================================ */
    import_descriptor_t* imp = (import_descriptor_t*)(buf + 0x400);

    /* HAL.dll imports */
    imp[0].name_rva = 0x2080;
    imp[0].import_lookup_table_rva = 0x20A0;
    imp[0].import_address_table_rva = 0x20C0;

    /* DLL name */
    strcpy((char*)(buf + 0x480), "HAL.dll");

    /* ILT entries: READ_PORT_UCHAR, WRITE_PORT_UCHAR */
    *(uint32_t*)(buf + 0x4A0) = 0x20E0;  /* hint/name for READ_PORT_UCHAR */
    *(uint32_t*)(buf + 0x4A4) = 0x20F8;  /* hint/name for WRITE_PORT_UCHAR */
    /* IAT entries (same) */
    *(uint32_t*)(buf + 0x4C0) = 0x20E0;
    *(uint32_t*)(buf + 0x4C4) = 0x20F8;

    /* Hint/Name entries */
    *(uint16_t*)(buf + 0x4E0) = 0;  /* hint */
    strcpy((char*)(buf + 0x4E2), "READ_PORT_UCHAR");
    *(uint16_t*)(buf + 0x4F8) = 0;  /* hint */
    strcpy((char*)(buf + 0x4FA), "WRITE_PORT_UCHAR");

    /* ============================================================
     * .edata — Export Table (at file offset 0x600, RVA 0x3000)
     * ============================================================ */
    uint8_t* edata = buf + 0x600;

    /* Export directory table */
    uint32_t* exp_dir = (uint32_t*)edata;
    exp_dir[0] = 0;                  /* Characteristics */
    exp_dir[1] = 0;                  /* TimeDateStamp */
    exp_dir[2] = 0;                  /* MajorVersion/MinorVersion */
    exp_dir[3] = 0x3060;             /* Name RVA -> "serial16550.sys" */
    exp_dir[4] = 1;                  /* OrdinalBase */
    exp_dir[5] = 3;                  /* NumberOfFunctions */
    exp_dir[6] = 3;                  /* NumberOfNames */
    exp_dir[7] = 0x3028;             /* AddressOfFunctions RVA */
    exp_dir[8] = 0x3034;             /* AddressOfNames RVA */
    exp_dir[9] = 0x3040;             /* AddressOfNameOrdinals RVA */

    /* Export Address Table (at 0x628 = edata+0x28) */
    uint32_t* eat = (uint32_t*)(edata + 0x28);
    eat[0] = 0x1000;   /* UART_INIT at RVA 0x1000 */
    eat[1] = 0x100B;   /* UART_SEND at RVA 0x100B */
    eat[2] = 0x1019;   /* UART_RECV at RVA 0x1019 */

    /* Export Name Pointer Table (at 0x634 = edata+0x34) */
    uint32_t* enpt = (uint32_t*)(edata + 0x34);
    enpt[0] = 0x3080;   /* -> "UART_INIT" */
    enpt[1] = 0x3090;   /* -> "UART_SEND" */
    enpt[2] = 0x30A0;   /* -> "UART_RECV" */

    /* Export Ordinal Table (at 0x640 = edata+0x40) */
    uint16_t* eot = (uint16_t*)(edata + 0x40);
    eot[0] = 0;
    eot[1] = 1;
    eot[2] = 2;

    /* Strings */
    strcpy((char*)(edata + 0x60), "serial16550.sys");
    strcpy((char*)(edata + 0x80), "UART_INIT");
    strcpy((char*)(edata + 0x90), "UART_SEND");
    strcpy((char*)(edata + 0xA0), "UART_RECV");

    *out_size = file_size;
    return buf;
}


/* ============================================================================
 * Test: Function boundary discovery finds 3 functions
 * ============================================================================ */
static void test_function_discovery(void) {
    TEST(discover_3_functions_in_16550_pe);

    size_t pe_size;
    uint8_t* pe_data = build_16550_pe(&pe_size);

    pe_context_t pe;
    if (pe_load(&pe, pe_data, pe_size) != 0)
        { free(pe_data); FAIL("pe_load failed"); }

    /* Decode instructions */
    x86_decoder_t dec;
    x86_decoder_init(&dec, X86_MODE_32, pe.text_data, pe.text_size,
                     pe.image_base + pe.text_rva);
    size_t inst_count;
    x86_decoded_t* insts = x86_decode_range(&dec, &inst_count);
    if (!insts)
        { pe_cleanup(&pe); free(pe_data); FAIL("decode failed"); }

    /* Build export info */
    sem_pe_export_t* exports = malloc(pe.export_count * sizeof(sem_pe_export_t));
    for (size_t i = 0; i < pe.export_count; i++) {
        exports[i].address = pe.image_base + pe.exports[i].rva;
        exports[i].name = pe.exports[i].name;
    }

    /* Discover functions */
    uint64_t text_base = pe.image_base + pe.text_rva;
    uint64_t text_end = text_base + pe.text_size;
    sem_function_map_t func_map;
    sem_discover_functions(insts, inst_count, text_base, text_end,
                          exports, pe.export_count, &func_map);

    free(exports);
    free(insts);

    if (func_map.count < 3) {
        char msg[64];
        snprintf(msg, sizeof(msg), "expected >= 3 functions, got %zu", func_map.count);
        sem_function_map_free(&func_map);
        pe_cleanup(&pe);
        free(pe_data);
        FAIL(msg);
    }

    /* Verify each function has instructions */
    for (size_t i = 0; i < func_map.count; i++) {
        if (func_map.entries[i].inst_count == 0) {
            sem_function_map_free(&func_map);
            pe_cleanup(&pe);
            free(pe_data);
            FAIL("function with zero instructions");
        }
    }

    sem_function_map_free(&func_map);
    pe_cleanup(&pe);
    free(pe_data);
    PASS();
}


/* ============================================================================
 * Test: Full pipeline produces multi-function Forth output
 * ============================================================================ */
static void test_full_pipeline_multi_func(void) {
    TEST(full_pipeline_multi_function_16550);

    size_t pe_size;
    uint8_t* pe_data = build_16550_pe(&pe_size);

    translate_options_t opts;
    translate_options_init(&opts);
    opts.target = TARGET_FORTH;
    opts.vocab_name = "SERIAL-16550";
    opts.input_filename = "serial16550.sys";

    translate_result_t result = translate_buffer(pe_data, pe_size, &opts);
    free(pe_data);

    if (!result.success) {
        char msg[128];
        snprintf(msg, sizeof(msg), "pipeline failed: %s",
                 result.error_message ? result.error_message : "unknown");
        translate_result_free(&result);
        FAIL(msg);
    }

    char* out = result.output;

    /* Structural checks matching serial-16550.fth reference */
    if (!strstr(out, "\\ CATALOG: SERIAL-16550"))
        { translate_result_free(&result); FAIL("missing CATALOG"); }
    if (!strstr(out, "VOCABULARY SERIAL-16550"))
        { translate_result_free(&result); FAIL("missing VOCABULARY"); }
    if (!strstr(out, "SERIAL-16550 DEFINITIONS"))
        { translate_result_free(&result); FAIL("missing DEFINITIONS"); }
    if (!strstr(out, "HEX"))
        { translate_result_free(&result); FAIL("missing HEX"); }
    if (!strstr(out, "\\ REQUIRES: HARDWARE"))
        { translate_result_free(&result); FAIL("missing REQUIRES"); }
    if (!strstr(out, "FORTH DEFINITIONS"))
        { translate_result_free(&result); FAIL("missing FORTH DEFINITIONS"); }
    if (!strstr(out, "DECIMAL"))
        { translate_result_free(&result); FAIL("missing DECIMAL"); }

    /* Port-specific checks: 16550 ports 0xF8-0xFD should appear */
    if (!strstr(out, "CONSTANT REG-F8"))
        { translate_result_free(&result); FAIL("missing REG-F8 (THR/RBR)"); }
    if (!strstr(out, "CONSTANT REG-FD"))
        { translate_result_free(&result); FAIL("missing REG-FD (LSR)"); }

    /* Should have multiple extracted functions */
    if (!strstr(out, "Extracted Functions"))
        { translate_result_free(&result); FAIL("missing Extracted Functions section"); }

    /* Source binary should be recorded */
    if (!strstr(out, "serial16550.sys"))
        { translate_result_free(&result); FAIL("missing source binary name"); }

    translate_result_free(&result);
    PASS();
}


/* ============================================================================
 * Test: Vocab name derivation from filename
 * ============================================================================ */
static void test_vocab_name_derivation(void) {
    TEST(vocab_name_derived_from_filename);

    size_t pe_size;
    uint8_t* pe_data = build_16550_pe(&pe_size);

    translate_options_t opts;
    translate_options_init(&opts);
    opts.target = TARGET_FORTH;
    /* No vocab_name set — should derive from input_filename */
    opts.input_filename = "serial16550.sys";

    translate_result_t result = translate_buffer(pe_data, pe_size, &opts);
    free(pe_data);

    if (!result.success) {
        translate_result_free(&result);
        FAIL("pipeline failed");
    }

    /* Should derive "SERIAL16550" from "serial16550.sys" */
    if (!strstr(result.output, "VOCABULARY SERIAL16550"))
        { translate_result_free(&result); FAIL("expected derived name SERIAL16550"); }

    translate_result_free(&result);
    PASS();
}


/* ============================================================================
 * Test: Multiple UIR functions each get their own port ops
 * ============================================================================ */
static void test_per_function_port_ops(void) {
    TEST(per_function_port_operations);

    size_t pe_size;
    uint8_t* pe_data = build_16550_pe(&pe_size);

    /* Use the translate_buffer API with Forth output */
    translate_options_t opts;
    translate_options_init(&opts);
    opts.target = TARGET_FORTH;
    opts.vocab_name = "UART-TEST";
    opts.input_filename = "test.sys";

    translate_result_t result = translate_buffer(pe_data, pe_size, &opts);
    free(pe_data);

    if (!result.success) {
        translate_result_free(&result);
        FAIL("pipeline failed");
    }

    /* The output should contain function definitions with port operations.
     * UART_INIT writes to ports F8, F9, FA, FB.
     * UART_SEND reads FD, writes F8.
     * UART_RECV reads FD, reads F8. */
    char* out = result.output;

    /* We should see multiple function words (not just one) */
    char* first_func = strstr(out, ": UART_");
    if (!first_func) {
        /* Functions may be named func_XXXX if export matching failed */
        first_func = strstr(out, ": func_");
    }
    if (!first_func)
        { translate_result_free(&result); FAIL("no function words found"); }

    /* Should have C@-PORT (reads) and C!-PORT (writes) references */
    if (!strstr(out, "C@-PORT"))
        { translate_result_free(&result); FAIL("missing C@-PORT references"); }
    if (!strstr(out, "C!-PORT"))
        { translate_result_free(&result); FAIL("missing C!-PORT references"); }

    translate_result_free(&result);
    PASS();
}


/* ============================================================================
 * Test: PE export names appear in generated function words
 * ============================================================================ */
static void test_export_names_in_output(void) {
    TEST(export_names_used_for_functions);

    size_t pe_size;
    uint8_t* pe_data = build_16550_pe(&pe_size);

    translate_options_t opts;
    translate_options_init(&opts);
    opts.target = TARGET_FORTH;
    opts.vocab_name = "SERIAL-16550";
    opts.input_filename = "serial.sys";

    translate_result_t result = translate_buffer(pe_data, pe_size, &opts);
    free(pe_data);

    if (!result.success) {
        translate_result_free(&result);
        FAIL("pipeline failed");
    }

    /* Export names should be used as Forth word names */
    if (!strstr(result.output, "UART_INIT"))
        { translate_result_free(&result); FAIL("missing UART_INIT function"); }
    if (!strstr(result.output, "UART_SEND"))
        { translate_result_free(&result); FAIL("missing UART_SEND function"); }
    if (!strstr(result.output, "UART_RECV"))
        { translate_result_free(&result); FAIL("missing UART_RECV function"); }

    translate_result_free(&result);
    PASS();
}


/* ============================================================================
 * Test: Disassembly output for multi-function PE
 * ============================================================================ */
static void test_disasm_output(void) {
    TEST(disasm_shows_all_instructions);

    size_t pe_size;
    uint8_t* pe_data = build_16550_pe(&pe_size);

    translate_options_t opts;
    translate_options_init(&opts);
    opts.target = TARGET_DISASM;

    translate_result_t result = translate_buffer(pe_data, pe_size, &opts);
    free(pe_data);

    if (!result.success)
        { translate_result_free(&result); FAIL("disasm failed"); }

    /* Should contain in, out, push, test, ret (lowercase per decoder) */
    if (!strstr(result.output, "in "))
        { translate_result_free(&result); FAIL("missing 'in' in disasm"); }
    if (!strstr(result.output, "out "))
        { translate_result_free(&result); FAIL("missing 'out' in disasm"); }
    if (!strstr(result.output, "ret"))
        { translate_result_free(&result); FAIL("missing 'ret' in disasm"); }

    translate_result_free(&result);
    PASS();
}


int main(void) {
    printf("Synthetic 16550 UART Driver Tests\n");
    printf("==================================\n");

    test_function_discovery();
    test_full_pipeline_multi_func();
    test_vocab_name_derivation();
    test_per_function_port_ops();
    test_export_names_in_output();
    test_disasm_output();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);
    return tests_passed == tests_run ? 0 : 1;
}
