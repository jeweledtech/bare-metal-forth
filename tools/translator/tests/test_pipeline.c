/* ============================================================================
 * End-to-End Pipeline Test
 * ============================================================================
 *
 * Builds a synthetic PE with IN/OUT instructions in .text, pipes it through
 * the full pipeline (PE load -> x86 decode -> UIR lift -> semantic analysis
 * -> Forth codegen), and validates the output.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>

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
    printf("  TEST: %-50s ", #name); \
} while(0)

#define PASS() do { tests_passed++; printf("PASS\n"); } while(0)
#define FAIL(msg) do { printf("FAIL: %s\n", msg); return; } while(0)

/* Build a PE with IN/OUT instructions and a READ_PORT_UCHAR import.
 * .text contains: IN AL, 0x60 ; OUT 0x61, AL ; RET */
static uint8_t* build_driver_pe(size_t* out_size) {
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
    dirs[DATA_DIR_IMPORT].size = sizeof(import_descriptor_t) * 2;

    /* Section headers at 0x138 */
    section_header_t* sec_text = (section_header_t*)(buf + 0x138);
    memcpy(sec_text->name, ".text\0\0\0", 8);
    sec_text->virtual_size = 5;
    sec_text->virtual_address = 0x1000;
    sec_text->size_of_raw_data = 0x200;
    sec_text->pointer_to_raw_data = 0x200;
    sec_text->characteristics = SECTION_CNT_CODE | SECTION_MEM_EXECUTE
                                | SECTION_MEM_READ;

    section_header_t* sec_idata = (section_header_t*)(buf + 0x138 + 40);
    memcpy(sec_idata->name, ".idata\0\0", 8);
    sec_idata->virtual_size = 0x200;
    sec_idata->virtual_address = 0x2000;
    sec_idata->size_of_raw_data = 0x200;
    sec_idata->pointer_to_raw_data = 0x400;
    sec_idata->characteristics = SECTION_CNT_INITIALIZED_DATA | SECTION_MEM_READ;

    /* .text data:
     *   E4 60       IN AL, 0x60
     *   E6 61       OUT 0x61, AL
     *   C3          RET
     */
    buf[0x200] = 0xE4; buf[0x201] = 0x60;  /* IN AL, 0x60 */
    buf[0x202] = 0xE6; buf[0x203] = 0x61;  /* OUT 0x61, AL */
    buf[0x204] = 0xC3;                      /* RET */

    /* .idata: import descriptor for ntoskrnl.exe / READ_PORT_UCHAR */
    import_descriptor_t* imp = (import_descriptor_t*)(buf + 0x400);
    imp->name_rva = 0x2080;
    imp->import_lookup_table_rva = 0x20A0;
    imp->import_address_table_rva = 0x20C0;

    strcpy((char*)(buf + 0x480), "ntoskrnl.exe");
    *(uint32_t*)(buf + 0x4A0) = 0x20E0;    /* ILT entry */
    *(uint32_t*)(buf + 0x4C0) = 0x20E0;    /* IAT entry */
    *(uint16_t*)(buf + 0x4E0) = 0;          /* hint */
    strcpy((char*)(buf + 0x4E2), "READ_PORT_UCHAR");

    *out_size = file_size;
    return buf;
}

/* ---- Test: PE -> x86 decode ---- */
static void test_pe_to_x86(void) {
    TEST(pe_to_x86_decode);

    size_t pe_size;
    uint8_t* pe_data = build_driver_pe(&pe_size);

    pe_context_t pe;
    if (pe_load(&pe, pe_data, pe_size) != 0)
        { free(pe_data); FAIL("pe_load failed"); }

    x86_decoder_t dec;
    x86_decoder_init(&dec, X86_MODE_32, pe.text_data, pe.text_size,
                     pe.image_base + pe.text_rva);
    size_t count;
    x86_decoded_t* insts = x86_decode_range(&dec, &count);

    if (!insts || count == 0)
        { pe_cleanup(&pe); free(pe_data); FAIL("no instructions decoded"); }

    /* Should find IN, OUT, RET */
    bool found_in = false, found_out = false, found_ret = false;
    for (size_t i = 0; i < count; i++) {
        if (insts[i].instruction == X86_INS_IN) found_in = true;
        if (insts[i].instruction == X86_INS_OUT) found_out = true;
        if (insts[i].instruction == X86_INS_RET) found_ret = true;
    }

    free(insts);
    pe_cleanup(&pe);
    free(pe_data);

    if (!found_in) FAIL("missing IN instruction");
    if (!found_out) FAIL("missing OUT instruction");
    if (!found_ret) FAIL("missing RET instruction");
    PASS();
}

/* ---- Test: x86 -> UIR lift ---- */
static void test_x86_to_uir(void) {
    TEST(x86_to_uir_lift);

    size_t pe_size;
    uint8_t* pe_data = build_driver_pe(&pe_size);

    pe_context_t pe;
    pe_load(&pe, pe_data, pe_size);

    x86_decoder_t dec;
    x86_decoder_init(&dec, X86_MODE_32, pe.text_data, pe.text_size,
                     pe.image_base + pe.text_rva);
    size_t count;
    x86_decoded_t* insts = x86_decode_range(&dec, &count);

    /* Convert to UIR bridge format */
    uir_x86_input_t* uir_input = malloc(count * sizeof(uir_x86_input_t));
    for (size_t i = 0; i < count; i++) {
        uir_input[i].address = insts[i].address;
        uir_input[i].length = insts[i].length;
        uir_input[i].instruction = (int)insts[i].instruction;
        uir_input[i].operand_count = insts[i].operand_count;
        for (int j = 0; j < 4; j++) {
            uir_input[i].operands[j].type  = (int)insts[i].operands[j].type;
            uir_input[i].operands[j].size  = insts[i].operands[j].size;
            uir_input[i].operands[j].reg   = insts[i].operands[j].reg;
            uir_input[i].operands[j].base  = insts[i].operands[j].base;
            uir_input[i].operands[j].index = insts[i].operands[j].index;
            uir_input[i].operands[j].scale = insts[i].operands[j].scale;
            uir_input[i].operands[j].disp  = insts[i].operands[j].disp;
            uir_input[i].operands[j].imm   = insts[i].operands[j].imm;
        }
        uir_input[i].prefixes = insts[i].prefixes;
        uir_input[i].cc = (int)insts[i].cc;
    }

    uir_function_t* func = uir_lift_function(uir_input, count,
                                              pe.image_base + pe.entry_point_rva);
    free(uir_input);
    free(insts);

    if (!func) { pe_cleanup(&pe); free(pe_data); FAIL("uir_lift_function returned NULL"); }
    if (!func->has_port_io) { uir_free_function(func); pe_cleanup(&pe); free(pe_data); FAIL("has_port_io should be true"); }
    if (func->ports_read_count == 0) { uir_free_function(func); pe_cleanup(&pe); free(pe_data); FAIL("should have ports_read"); }
    if (func->ports_written_count == 0) { uir_free_function(func); pe_cleanup(&pe); free(pe_data); FAIL("should have ports_written"); }

    uir_free_function(func);
    pe_cleanup(&pe);
    free(pe_data);
    PASS();
}

/* ---- Test: semantic classification of imports ---- */
static void test_semantic_classification(void) {
    TEST(semantic_import_classification);

    size_t pe_size;
    uint8_t* pe_data = build_driver_pe(&pe_size);

    pe_context_t pe;
    pe_load(&pe, pe_data, pe_size);

    /* Classify imports */
    sem_pe_import_t* sem_imports = malloc(pe.import_count * sizeof(sem_pe_import_t));
    for (size_t i = 0; i < pe.import_count; i++) {
        sem_imports[i].dll_name = pe.imports[i].dll_name;
        sem_imports[i].func_name = pe.imports[i].func_name;
        sem_imports[i].iat_rva = pe.imports[i].iat_rva;
    }

    sem_result_t sem;
    memset(&sem, 0, sizeof(sem));
    sem_classify_imports(sem_imports, pe.import_count, &sem);
    free(sem_imports);

    if (sem.import_count == 0)
        { pe_cleanup(&pe); free(pe_data); FAIL("no imports classified"); }

    /* READ_PORT_UCHAR should be classified as hardware / port I/O */
    bool found_hw = false;
    for (size_t i = 0; i < sem.import_count; i++) {
        if (sem_is_hardware(sem.imports[i].category))
            found_hw = true;
    }

    sem_cleanup(&sem);
    pe_cleanup(&pe);
    free(pe_data);

    if (!found_hw) FAIL("READ_PORT_UCHAR should be classified as hardware");
    PASS();
}

/* ---- Test: full pipeline PE -> Forth ---- */
static void test_full_pipeline(void) {
    TEST(full_pipeline_pe_to_forth);

    size_t pe_size;
    uint8_t* pe_data = build_driver_pe(&pe_size);

    /* Stage 1: PE load */
    pe_context_t pe;
    if (pe_load(&pe, pe_data, pe_size) != 0)
        { free(pe_data); FAIL("pe_load failed"); }

    /* Stage 2: x86 decode */
    x86_decoder_t dec;
    x86_decoder_init(&dec, X86_MODE_32, pe.text_data, pe.text_size,
                     pe.image_base + pe.text_rva);
    size_t inst_count;
    x86_decoded_t* insts = x86_decode_range(&dec, &inst_count);
    if (!insts) { pe_cleanup(&pe); free(pe_data); FAIL("decode failed"); }

    /* Stage 3: UIR lift */
    uir_x86_input_t* uir_input = malloc(inst_count * sizeof(uir_x86_input_t));
    for (size_t i = 0; i < inst_count; i++) {
        uir_input[i].address = insts[i].address;
        uir_input[i].length = insts[i].length;
        uir_input[i].instruction = (int)insts[i].instruction;
        uir_input[i].operand_count = insts[i].operand_count;
        for (int j = 0; j < 4; j++) {
            uir_input[i].operands[j].type  = (int)insts[i].operands[j].type;
            uir_input[i].operands[j].size  = insts[i].operands[j].size;
            uir_input[i].operands[j].reg   = insts[i].operands[j].reg;
            uir_input[i].operands[j].base  = insts[i].operands[j].base;
            uir_input[i].operands[j].index = insts[i].operands[j].index;
            uir_input[i].operands[j].scale = insts[i].operands[j].scale;
            uir_input[i].operands[j].disp  = insts[i].operands[j].disp;
            uir_input[i].operands[j].imm   = insts[i].operands[j].imm;
        }
        uir_input[i].prefixes = insts[i].prefixes;
        uir_input[i].cc = (int)insts[i].cc;
    }
    free(insts);

    uir_function_t* uir_func = uir_lift_function(uir_input, inst_count,
                                                   pe.image_base + pe.entry_point_rva);
    free(uir_input);
    if (!uir_func) { pe_cleanup(&pe); free(pe_data); FAIL("UIR lift failed"); }

    /* Stage 4: Semantic analysis */
    sem_pe_import_t* sem_imports = NULL;
    if (pe.import_count > 0) {
        sem_imports = malloc(pe.import_count * sizeof(sem_pe_import_t));
        for (size_t i = 0; i < pe.import_count; i++) {
            sem_imports[i].dll_name = pe.imports[i].dll_name;
            sem_imports[i].func_name = pe.imports[i].func_name;
            sem_imports[i].iat_rva = pe.imports[i].iat_rva;
        }
    }

    sem_result_t sem;
    memset(&sem, 0, sizeof(sem));
    if (pe.import_count > 0)
        sem_classify_imports(sem_imports, pe.import_count, &sem);
    free(sem_imports);

    sem_uir_input_t sem_func;
    memset(&sem_func, 0, sizeof(sem_func));
    sem_func.func = uir_func;
    sem_func.entry_address = uir_func->entry_address;
    sem_func.has_port_io = uir_func->has_port_io;
    sem_func.ports_read = uir_func->ports_read;
    sem_func.ports_read_count = uir_func->ports_read_count;
    sem_func.ports_written = uir_func->ports_written;
    sem_func.ports_written_count = uir_func->ports_written_count;
    sem_analyze_functions(&sem_func, 1, &sem);

    /* Stage 5: Forth codegen */
    forth_codegen_opts_t cg_opts;
    forth_codegen_opts_init(&cg_opts);
    cg_opts.vocab_name = "PIPELINE-TEST";
    cg_opts.category = "test";
    cg_opts.source_type = "extracted";
    cg_opts.confidence = "medium";

    static const char* port_words[] = {"C@-PORT", "C!-PORT", NULL};
    forth_dependency_t deps[] = {{"HARDWARE", port_words}, {NULL, NULL}};
    cg_opts.requires = deps;

    /* Build port offsets from UIR */
    uint16_t port_offsets[16];
    size_t port_offset_count = 0;
    for (size_t i = 0; i < uir_func->ports_read_count && port_offset_count < 16; i++)
        port_offsets[port_offset_count++] = uir_func->ports_read[i];
    for (size_t i = 0; i < uir_func->ports_written_count && port_offset_count < 16; i++) {
        bool found = false;
        for (size_t j = 0; j < port_offset_count; j++)
            if (port_offsets[j] == uir_func->ports_written[i]) { found = true; break; }
        if (!found) port_offsets[port_offset_count++] = uir_func->ports_written[i];
    }

    forth_codegen_input_t cg_input;
    memset(&cg_input, 0, sizeof(cg_input));
    cg_input.opts = cg_opts;
    cg_input.port_offsets = port_offsets;
    cg_input.port_offset_count = port_offset_count;

    char* output = forth_generate(&cg_input);

    sem_cleanup(&sem);
    uir_free_function(uir_func);
    pe_cleanup(&pe);
    free(pe_data);

    if (!output) FAIL("forth_generate returned NULL");

    /* Validate the generated Forth vocabulary */
    if (!strstr(output, "\\ CATALOG: PIPELINE-TEST"))
        { free(output); FAIL("missing CATALOG header"); }
    if (!strstr(output, "VOCABULARY PIPELINE-TEST"))
        { free(output); FAIL("missing VOCABULARY declaration"); }
    if (!strstr(output, "PIPELINE-TEST DEFINITIONS"))
        { free(output); FAIL("missing DEFINITIONS"); }
    if (!strstr(output, "HEX"))
        { free(output); FAIL("missing HEX"); }
    if (!strstr(output, "\\ REQUIRES: HARDWARE ( C@-PORT C!-PORT )"))
        { free(output); FAIL("missing REQUIRES"); }
    if (!strstr(output, "VARIABLE"))
        { free(output); FAIL("missing base VARIABLE"); }
    if (!strstr(output, "FORTH DEFINITIONS"))
        { free(output); FAIL("missing FORTH DEFINITIONS footer"); }
    if (!strstr(output, "DECIMAL"))
        { free(output); FAIL("missing DECIMAL footer"); }

    /* Port offsets should appear as register constants (0x60 and 0x61) */
    if (!strstr(output, "CONSTANT REG-60"))
        { free(output); FAIL("missing REG-60 constant"); }
    if (!strstr(output, "CONSTANT REG-61"))
        { free(output); FAIL("missing REG-61 constant"); }

    free(output);
    PASS();
}

/* ---- Test: pipeline detects non-PE gracefully ---- */
static void test_reject_non_pe(void) {
    TEST(reject_non_pe_data);

    uint8_t garbage[] = { 0x00, 0x01, 0x02, 0x03, 0x04 };
    pe_context_t pe;
    int rc = pe_load(&pe, garbage, sizeof(garbage));
    if (rc == 0) FAIL("should have rejected non-PE data");
    PASS();
}

int main(void) {
    printf("End-to-End Pipeline Tests\n");
    printf("=========================\n");

    test_pe_to_x86();
    test_x86_to_uir();
    test_semantic_classification();
    test_full_pipeline();
    test_reject_non_pe();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);
    return tests_passed == tests_run ? 0 : 1;
}
