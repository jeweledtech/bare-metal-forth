/* ============================================================================
 * Semantic Report Tests
 * ============================================================================
 *
 * Validates the -t report (TARGET_SEMANTIC_REPORT) JSON output against
 * known test binaries.  Uses string matching on the JSON — no JSON parser
 * dependency needed.
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

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) do { \
    tests_run++; \
    printf("  TEST: %-50s ", #name); \
} while(0)

#define PASS() do { tests_passed++; printf("PASS\n"); } while(0)
#define FAIL(msg) do { printf("FAIL: %s\n", msg); return; } while(0)

/* ============================================================================
 * Helper: run translator on a file with -t report
 * ============================================================================ */

static translate_result_t run_report(const char* filename) {
    translate_options_t opts;
    translate_options_init(&opts);
    opts.target = TARGET_SEMANTIC_REPORT;
    opts.input_filename = filename;
    return translate_file(filename, &opts);
}

/* Check if a string contains a substring */
static bool has(const char* haystack, const char* needle) {
    return haystack && needle && strstr(haystack, needle) != NULL;
}

/* ============================================================================
 * Tests
 * ============================================================================ */

static void test_pe_report_valid_json(void) {
    TEST(pe_report_valid_json);
    translate_result_t r = run_report("tests/data/serial16550_synth.sys");
    if (!r.success) FAIL(r.error_message ? r.error_message : "failed");
    if (!has(r.output, "\"schema_version\": 1"))
        { translate_result_free(&r); FAIL("missing schema_version"); }
    if (!has(r.output, "\"generator\": \"ubt\""))
        { translate_result_free(&r); FAIL("missing generator"); }
    translate_result_free(&r);
    PASS();
}

static void test_pe_report_binary_info(void) {
    TEST(pe_report_binary_info);
    translate_result_t r = run_report("tests/data/serial16550_synth.sys");
    if (!r.success) FAIL(r.error_message ? r.error_message : "failed");
    if (!has(r.output, "\"format\": \"PE32\""))
        { translate_result_free(&r); FAIL("wrong format"); }
    if (!has(r.output, "\"machine\": \"x86\""))
        { translate_result_free(&r); FAIL("wrong machine"); }
    if (!has(r.output, "\"image_base\": \"0x10000\""))
        { translate_result_free(&r); FAIL("wrong image_base"); }
    translate_result_free(&r);
    PASS();
}

static void test_pe_report_port_ops(void) {
    TEST(pe_report_port_ops);
    translate_result_t r = run_report("tests/data/serial16550_synth.sys");
    if (!r.success) FAIL(r.error_message ? r.error_message : "failed");
    if (!has(r.output, "\"port_operations\""))
        { translate_result_free(&r); FAIL("missing port_operations"); }
    /* 16550 should have ports in 0xF8-0xFD range */
    if (!has(r.output, "\"port\": \"0xF8\""))
        { translate_result_free(&r); FAIL("missing port 0xF8"); }
    if (!has(r.output, "\"port\": \"0xFD\""))
        { translate_result_free(&r); FAIL("missing port 0xFD"); }
    translate_result_free(&r);
    PASS();
}

static void test_pe_report_hw_functions(void) {
    TEST(pe_report_hw_functions);
    translate_result_t r = run_report("tests/data/serial16550_synth.sys");
    if (!r.success) FAIL(r.error_message ? r.error_message : "failed");
    if (!has(r.output, "\"hardware_functions\""))
        { translate_result_free(&r); FAIL("missing hardware_functions"); }
    if (!has(r.output, "UART_INIT"))
        { translate_result_free(&r); FAIL("missing UART_INIT"); }
    if (!has(r.output, "UART_SEND"))
        { translate_result_free(&r); FAIL("missing UART_SEND"); }
    if (!has(r.output, "UART_RECV"))
        { translate_result_free(&r); FAIL("missing UART_RECV"); }
    translate_result_free(&r);
    PASS();
}

static void test_pe_report_summary(void) {
    TEST(pe_report_summary);
    translate_result_t r = run_report("tests/data/serial16550_synth.sys");
    if (!r.success) FAIL(r.error_message ? r.error_message : "failed");
    if (!has(r.output, "\"hardware_functions\": 3"))
        { translate_result_free(&r); FAIL("wrong hw function count"); }
    if (!has(r.output, "\"port_io_functions\": 3"))
        { translate_result_free(&r); FAIL("wrong port_io count"); }
    translate_result_free(&r);
    PASS();
}

static void test_i8042_report_hw_count(void) {
    TEST(i8042_report_hw_count);
    translate_result_t r = run_report("tests/data/i8042prt.sys");
    if (!r.success) FAIL(r.error_message ? r.error_message : "failed");
    /* i8042prt has 9 hardware functions */
    if (!has(r.output, "\"hardware_functions\": 9"))
        { translate_result_free(&r); FAIL("expected 9 hw functions"); }
    translate_result_free(&r);
    PASS();
}

static void test_i8042_report_imports(void) {
    TEST(i8042_report_imports);
    translate_result_t r = run_report("tests/data/i8042prt.sys");
    if (!r.success) FAIL(r.error_message ? r.error_message : "failed");
    if (!has(r.output, "\"imports\""))
        { translate_result_free(&r); FAIL("missing imports array"); }
    /* Should have READ_PORT_UCHAR in imports */
    if (!has(r.output, "READ_PORT_UCHAR"))
        { translate_result_free(&r); FAIL("missing READ_PORT_UCHAR"); }
    translate_result_free(&r);
    PASS();
}

static void test_i8042_report_hal_calls(void) {
    TEST(i8042_report_hal_calls);
    translate_result_t r = run_report("tests/data/i8042prt.sys");
    if (!r.success) FAIL(r.error_message ? r.error_message : "failed");
    if (!has(r.output, "\"hal_calls\""))
        { translate_result_free(&r); FAIL("missing hal_calls"); }
    translate_result_free(&r);
    PASS();
}

static void test_dotnet_report(void) {
    TEST(dotnet_report);
    /* The .NET fixture is in the Forth OS tests/fixtures/ directory.
     * Makefile runs from tools/translator/, so path is relative to there. */
    translate_result_t r = run_report("../../tests/fixtures/test_dotnet.dll");
    if (!r.success) FAIL(r.error_message ? r.error_message : "failed");
    if (!has(r.output, "\"schema_version\": 1"))
        { translate_result_free(&r); FAIL("missing schema_version"); }
    if (!has(r.output, "\".NET assembly\""))
        { translate_result_free(&r); FAIL("wrong format for .NET"); }
    if (!has(r.output, "\"hardware_functions\": 0"))
        { translate_result_free(&r); FAIL("should have 0 hw functions"); }
    translate_result_free(&r);
    PASS();
}

static void test_report_parseable(void) {
    TEST(report_parseable_braces);
    translate_result_t r = run_report("tests/data/serial16550_synth.sys");
    if (!r.success) FAIL(r.error_message ? r.error_message : "failed");
    /* Count opening/closing braces — should match for valid JSON */
    int opens = 0, closes = 0;
    for (size_t i = 0; i < r.output_size; i++) {
        if (r.output[i] == '{') opens++;
        if (r.output[i] == '}') closes++;
    }
    if (opens != closes) {
        char msg[64];
        snprintf(msg, sizeof(msg), "unbalanced braces: %d open, %d close",
                 opens, closes);
        translate_result_free(&r);
        FAIL(msg);
    }
    /* Also check brackets */
    opens = closes = 0;
    for (size_t i = 0; i < r.output_size; i++) {
        if (r.output[i] == '[') opens++;
        if (r.output[i] == ']') closes++;
    }
    if (opens != closes) {
        translate_result_free(&r);
        FAIL("unbalanced brackets");
    }
    translate_result_free(&r);
    PASS();
}

/* ============================================================================
 * Main
 * ============================================================================ */

int main(void) {
    printf("Semantic Report Tests\n");
    printf("=====================\n");

    test_pe_report_valid_json();
    test_pe_report_binary_info();
    test_pe_report_port_ops();
    test_pe_report_hw_functions();
    test_pe_report_summary();
    test_i8042_report_hw_count();
    test_i8042_report_imports();
    test_i8042_report_hal_calls();
    test_dotnet_report();
    test_report_parseable();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);
    return tests_passed == tests_run ? 0 : 1;
}
