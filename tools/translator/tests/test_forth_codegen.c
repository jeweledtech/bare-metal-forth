/* ============================================================================
 * Forth Code Generator Tests
 * ============================================================================
 *
 * Tests that the Forth codegen produces correct vocabulary source files
 * matching the catalog header format and vocabulary pattern from
 * forth/dict/serial-16550.fth.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../include/forth_codegen.h"

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) do { \
    tests_run++; \
    printf("  TEST: %-50s ", #name); \
} while(0)

#define PASS() do { tests_passed++; printf("PASS\n"); } while(0)
#define FAIL(msg) do { printf("FAIL: %s\n", msg); return; } while(0)

/* ---- Test: generate minimal vocabulary ---- */
static void test_minimal_vocabulary(void) {
    TEST(minimal_vocabulary);

    const char* hw_words[] = {"C@-PORT", "C!-PORT", NULL};
    forth_dependency_t deps[] = {
        {"HARDWARE", hw_words},
        {NULL, NULL}
    };

    forth_codegen_opts_t opts;
    forth_codegen_opts_init(&opts);
    opts.vocab_name = "TEST-DEVICE";
    opts.category = "test";
    opts.source_type = "extracted";
    opts.source_binary = "test.sys";
    opts.vendor_id = "none";
    opts.device_id = "none";
    opts.ports_desc = "0x100-0x107";
    opts.mmio_desc = "none";
    opts.confidence = "medium";
    opts.requires = deps;

    forth_codegen_input_t input;
    memset(&input, 0, sizeof(input));
    input.opts = opts;

    char* output = forth_generate(&input);
    if (!output) FAIL("forth_generate returned NULL");

    /* Check catalog header */
    if (!strstr(output, "\\ CATALOG: TEST-DEVICE")) FAIL("missing CATALOG");
    if (!strstr(output, "\\ CATEGORY: test")) FAIL("missing CATEGORY");
    if (!strstr(output, "\\ SOURCE: extracted")) FAIL("missing SOURCE");
    if (!strstr(output, "\\ SOURCE-BINARY: test.sys")) FAIL("missing SOURCE-BINARY");
    if (!strstr(output, "\\ CONFIDENCE: medium")) FAIL("missing CONFIDENCE");
    if (!strstr(output, "\\ REQUIRES: HARDWARE ( C@-PORT C!-PORT )")) FAIL("missing REQUIRES");

    /* Check vocabulary declaration */
    if (!strstr(output, "VOCABULARY TEST-DEVICE")) FAIL("missing VOCABULARY");
    if (!strstr(output, "TEST-DEVICE DEFINITIONS")) FAIL("missing DEFINITIONS");
    if (!strstr(output, "HEX")) FAIL("missing HEX");

    /* Check footer */
    if (!strstr(output, "FORTH DEFINITIONS")) FAIL("missing FORTH DEFINITIONS");
    if (!strstr(output, "DECIMAL")) FAIL("missing DECIMAL");

    free(output);
    PASS();
}

/* ---- Test: generate with port constants ---- */
static void test_port_constants(void) {
    TEST(port_constants);

    forth_codegen_opts_t opts;
    forth_codegen_opts_init(&opts);
    opts.vocab_name = "SERIAL-TEST";
    opts.category = "serial";
    opts.source_type = "extracted";
    opts.source_binary = "serial.sys";
    opts.confidence = "low";

    uint16_t offsets[] = {0x00, 0x01, 0x03, 0x05};

    forth_codegen_input_t input;
    memset(&input, 0, sizeof(input));
    input.opts = opts;
    input.port_offsets = offsets;
    input.port_offset_count = 4;

    char* output = forth_generate(&input);
    if (!output) FAIL("forth_generate returned NULL");

    /* Should have register offset constants */
    if (!strstr(output, "00 CONSTANT REG-00")) FAIL("missing REG-00 constant");
    if (!strstr(output, "01 CONSTANT REG-01")) FAIL("missing REG-01 constant");
    if (!strstr(output, "03 CONSTANT REG-03")) FAIL("missing REG-03 constant");
    if (!strstr(output, "05 CONSTANT REG-05")) FAIL("missing REG-05 constant");

    /* Should have base variable and accessor */
    if (!strstr(output, "VARIABLE")) FAIL("missing VARIABLE");

    free(output);
    PASS();
}

/* ---- Test: generate with port read function ---- */
static void test_port_read_function(void) {
    TEST(port_read_function);

    const char* hw_words[] = {"C@-PORT", NULL};
    forth_dependency_t deps[] = {
        {"HARDWARE", hw_words},
        {NULL, NULL}
    };

    forth_codegen_opts_t opts;
    forth_codegen_opts_init(&opts);
    opts.vocab_name = "KBD-TEST";
    opts.category = "input";
    opts.source_type = "extracted";
    opts.source_binary = "kbd.sys";
    opts.confidence = "medium";
    opts.requires = deps;

    forth_port_op_t port_ops[] = {
        {0x00, 1, false, NULL},  /* read byte at offset 0 */
    };

    forth_gen_function_t funcs[] = {
        {
            .name = "READ-DATA",
            .address = 0x1000,
            .port_ops = port_ops,
            .port_op_count = 1,
            .is_init = false,
            .is_poll = false,
        },
    };

    forth_codegen_input_t input;
    memset(&input, 0, sizeof(input));
    input.opts = opts;
    input.functions = funcs;
    input.function_count = 1;

    char* output = forth_generate(&input);
    if (!output) FAIL("forth_generate returned NULL");

    /* Should have the word definition */
    if (!strstr(output, ": READ-DATA")) FAIL("missing READ-DATA word");
    if (!strstr(output, "C@-PORT")) FAIL("missing C@-PORT in word body");

    free(output);
    PASS();
}

/* ---- Test: generate with port write function ---- */
static void test_port_write_function(void) {
    TEST(port_write_function);

    forth_codegen_opts_t opts;
    forth_codegen_opts_init(&opts);
    opts.vocab_name = "OUT-TEST";
    opts.category = "io";
    opts.source_type = "extracted";
    opts.source_binary = "out.sys";
    opts.confidence = "medium";

    forth_port_op_t port_ops[] = {
        {0x00, 1, true, NULL},  /* write byte at offset 0 */
    };

    forth_gen_function_t funcs[] = {
        {
            .name = "WRITE-DATA",
            .address = 0x2000,
            .port_ops = port_ops,
            .port_op_count = 1,
            .is_init = false,
            .is_poll = false,
        },
    };

    forth_codegen_input_t input;
    memset(&input, 0, sizeof(input));
    input.opts = opts;
    input.functions = funcs;
    input.function_count = 1;

    char* output = forth_generate(&input);
    if (!output) FAIL("forth_generate returned NULL");

    if (!strstr(output, ": WRITE-DATA")) FAIL("missing WRITE-DATA word");
    if (!strstr(output, "C!-PORT")) FAIL("missing C!-PORT in word body");

    free(output);
    PASS();
}

/* ---- Test: multiple REQUIRES lines ---- */
static void test_multiple_requires(void) {
    TEST(multiple_requires);

    const char* hw_words[] = {"C@-PORT", "C!-PORT", NULL};
    const char* timing_words[] = {"MS-DELAY", NULL};
    forth_dependency_t deps[] = {
        {"HARDWARE", hw_words},
        {"TIMING", timing_words},
        {NULL, NULL}
    };

    forth_codegen_opts_t opts;
    forth_codegen_opts_init(&opts);
    opts.vocab_name = "MULTI-DEP";
    opts.category = "test";
    opts.source_type = "extracted";
    opts.source_binary = "multi.sys";
    opts.confidence = "low";
    opts.requires = deps;

    forth_codegen_input_t input;
    memset(&input, 0, sizeof(input));
    input.opts = opts;

    char* output = forth_generate(&input);
    if (!output) FAIL("forth_generate returned NULL");

    if (!strstr(output, "\\ REQUIRES: HARDWARE ( C@-PORT C!-PORT )"))
        FAIL("missing HARDWARE REQUIRES");
    if (!strstr(output, "\\ REQUIRES: TIMING ( MS-DELAY )"))
        FAIL("missing TIMING REQUIRES");

    free(output);
    PASS();
}

/* ---- Test: no REQUIRES line when deps are NULL ---- */
static void test_no_requires(void) {
    TEST(no_requires_when_null);

    forth_codegen_opts_t opts;
    forth_codegen_opts_init(&opts);
    opts.vocab_name = "NO-DEPS";
    opts.category = "test";
    opts.source_type = "extracted";
    opts.source_binary = "nodeps.sys";
    opts.confidence = "high";
    opts.requires = NULL;

    forth_codegen_input_t input;
    memset(&input, 0, sizeof(input));
    input.opts = opts;

    char* output = forth_generate(&input);
    if (!output) FAIL("forth_generate returned NULL");

    if (strstr(output, "REQUIRES:")) FAIL("should NOT have REQUIRES line");

    free(output);
    PASS();
}

/* ---- Test: port range description helper ---- */
static void test_port_range_desc(void) {
    TEST(port_range_desc);

    char* desc = forth_port_range_desc(0x3F8, 8);
    if (!desc) FAIL("returned NULL");
    if (strcmp(desc, "0x3F8-0x3FF") != 0) {
        printf("got '%s' ", desc);
        FAIL("expected 0x3F8-0x3FF");
    }
    free(desc);

    desc = forth_port_range_desc(0x60, 1);
    if (!desc) FAIL("returned NULL for single port");
    if (strcmp(desc, "0x60") != 0) {
        printf("got '%s' ", desc);
        FAIL("expected 0x60");
    }
    free(desc);

    PASS();
}

/* ---- Test: dword port operations ---- */
static void test_dword_port_ops(void) {
    TEST(dword_port_operations);

    forth_codegen_opts_t opts;
    forth_codegen_opts_init(&opts);
    opts.vocab_name = "PCI-TEST";
    opts.category = "pci";
    opts.source_type = "extracted";
    opts.source_binary = "pci.sys";
    opts.confidence = "medium";

    forth_port_op_t port_ops[] = {
        {0x00, 4, false, NULL},  /* read dword at offset 0 */
        {0x00, 4, true, NULL},   /* write dword at offset 0 */
    };

    forth_gen_function_t funcs[] = {
        {
            .name = "PCI-READ-CONFIG",
            .address = 0x3000,
            .port_ops = port_ops,
            .port_op_count = 1,
            .is_init = false,
            .is_poll = false,
        },
        {
            .name = "PCI-WRITE-CONFIG",
            .address = 0x3020,
            .port_ops = &port_ops[1],
            .port_op_count = 1,
            .is_init = false,
            .is_poll = false,
        },
    };

    forth_codegen_input_t input;
    memset(&input, 0, sizeof(input));
    input.opts = opts;
    input.functions = funcs;
    input.function_count = 2;

    char* output = forth_generate(&input);
    if (!output) FAIL("forth_generate returned NULL");

    if (!strstr(output, "@-PORT")) FAIL("missing @-PORT for dword read");
    if (!strstr(output, "!-PORT")) FAIL("missing !-PORT for dword write");

    free(output);
    PASS();
}

int main(void) {
    printf("Forth Code Generator Tests\n");
    printf("==========================\n");

    test_minimal_vocabulary();
    test_port_constants();
    test_port_read_function();
    test_port_write_function();
    test_multiple_requires();
    test_no_requires();
    test_port_range_desc();
    test_dword_port_ops();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);
    return tests_passed == tests_run ? 0 : 1;
}
