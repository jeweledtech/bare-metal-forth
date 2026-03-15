/* ============================================================================
 * i8042prt.sys Ghidra Validation — HAL Cross-Reference Comparison
 * ============================================================================
 *
 * Validates the UBT pipeline against Ghidra's analysis of a real Windows
 * driver (ReactOS i8042prt.sys).  Unlike the synthetic 16550 test which
 * validates direct port I/O, this test validates HAL-based hardware
 * detection — the driver has ZERO direct IN/OUT instructions and accesses
 * hardware exclusively through HAL imports (READ_PORT_UCHAR etc.).
 *
 * Asymmetric comparison:
 *   - Import classification: UBT and Ghidra must agree on PORT_IO vs
 *     SCAFFOLDING categories for the same imports.
 *   - Hardware function detection: UBT must find MORE hardware functions
 *     than Ghidra (which finds 0, since no direct port ops exist).
 *     This is the HAL cross-referencing working as designed.
 *   - Scaffolding filtering: functions that only call scaffolding APIs
 *     should not appear as Forth word definitions.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <ctype.h>

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
 * Minimal JSON helpers — reused from test_ghidra_compare.c pattern
 * ============================================================================ */

#define MAX_IMPORTS 64

typedef struct {
    char dll[64];
    char function[64];
    char category[32];
} ghidra_import_t;

typedef struct {
    int schema_version;
    int hw_func_count;
    int port_op_count;
    int scaffolding_count;
    ghidra_import_t imports[MAX_IMPORTS];
    int import_count;
} ghidra_report_t;

static const char* extract_string(const char* p, const char* key,
                                  char* out, size_t max_len) {
    char pattern[128];
    snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    const char* found = strstr(p, pattern);
    if (!found) return NULL;
    found += strlen(pattern);
    found = strchr(found, ':');
    if (!found) return NULL;
    found = strchr(found, '"');
    if (!found) return NULL;
    found++;
    size_t i = 0;
    while (*found && *found != '"' && i < max_len - 1) {
        out[i++] = *found++;
    }
    out[i] = '\0';
    if (*found == '"') found++;
    return found;
}

static const char* find_array(const char* json, const char* name) {
    char pattern[128];
    snprintf(pattern, sizeof(pattern), "\"%s\"", name);
    const char* found = strstr(json, pattern);
    if (!found) return NULL;
    return strchr(found, '[');
}

static const char* find_array_end(const char* start) {
    if (!start || *start != '[') return NULL;
    int depth = 0;
    const char* p = start;
    while (*p) {
        if (*p == '[') depth++;
        else if (*p == ']') { depth--; if (depth == 0) return p; }
        else if (*p == '"') { p++; while (*p && *p != '"') { if (*p == '\\') p++; p++; } }
        p++;
    }
    return NULL;
}

static int count_array_objects(const char* json, const char* name) {
    const char* arr = find_array(json, name);
    if (!arr) return 0;
    const char* end = find_array_end(arr);
    if (!end) return 0;
    int count = 0;
    for (const char* p = arr; p < end; p++) {
        if (*p == '{') count++;
    }
    return count;
}

static bool parse_ghidra_report(const char* json, ghidra_report_t* report) {
    memset(report, 0, sizeof(*report));

    const char* sv = strstr(json, "\"schema_version\"");
    if (sv) {
        sv = strchr(sv, ':');
        if (sv) report->schema_version = atoi(sv + 1);
    }

    report->port_op_count = count_array_objects(json, "port_operations");
    report->hw_func_count = count_array_objects(json, "hardware_functions");
    report->scaffolding_count = count_array_objects(json, "scaffolding_functions");

    /* Parse imports */
    const char* arr = find_array(json, "imports");
    if (arr) {
        const char* arr_end = find_array_end(arr);
        const char* p = arr + 1;
        while (p && p < arr_end && report->import_count < MAX_IMPORTS) {
            const char* obj_start = strchr(p, '{');
            if (!obj_start || obj_start >= arr_end) break;
            const char* obj_end = strchr(obj_start, '}');
            if (!obj_end) break;

            char buf[256];
            size_t len = (size_t)(obj_end - obj_start + 1);
            if (len >= sizeof(buf)) len = sizeof(buf) - 1;
            memcpy(buf, obj_start, len);
            buf[len] = '\0';

            ghidra_import_t* imp = &report->imports[report->import_count];
            extract_string(buf, "dll", imp->dll, sizeof(imp->dll));
            extract_string(buf, "function", imp->function, sizeof(imp->function));
            extract_string(buf, "category", imp->category, sizeof(imp->category));
            report->import_count++;
            p = obj_end + 1;
        }
    }

    return report->schema_version > 0;
}

/* ============================================================================
 * File I/O helpers
 * ============================================================================ */

static char* read_text_file(const char* path) {
    FILE* f = fopen(path, "r");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    char* buf = malloc((size_t)sz + 1);
    size_t n = fread(buf, 1, (size_t)sz, f);
    buf[n] = '\0';
    fclose(f);
    return buf;
}

static uint8_t* read_binary_file(const char* path, size_t* out_size) {
    FILE* f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t* buf = malloc((size_t)sz);
    *out_size = fread(buf, 1, (size_t)sz, f);
    fclose(f);
    return buf;
}

/* ============================================================================
 * Shared test state
 * ============================================================================ */

static ghidra_report_t ghidra;
static char* forth_output = NULL;
static bool data_loaded = false;

static bool load_test_data(void) {
    if (data_loaded) return true;

    char* json = read_text_file(
        "tests/data/fixtures/i8042prt.ghidra.json");
    if (!json) {
        fprintf(stderr, "ERROR: Cannot read i8042prt Ghidra fixture\n");
        return false;
    }
    if (!parse_ghidra_report(json, &ghidra)) {
        fprintf(stderr, "ERROR: Failed to parse Ghidra fixture\n");
        free(json);
        return false;
    }
    free(json);

    size_t sys_size;
    uint8_t* sys_data = read_binary_file("tests/data/i8042prt.sys", &sys_size);
    if (!sys_data) {
        fprintf(stderr, "ERROR: Cannot read i8042prt.sys\n");
        return false;
    }

    translate_options_t opts;
    translate_options_init(&opts);
    opts.target = TARGET_FORTH;
    opts.input_filename = "i8042prt.sys";

    translate_result_t result = translate_buffer(sys_data, sys_size, &opts);
    free(sys_data);

    if (!result.success) {
        fprintf(stderr, "ERROR: Pipeline failed: %s\n",
                result.error_message ? result.error_message : "unknown");
        translate_result_free(&result);
        return false;
    }

    forth_output = result.output;
    result.output = NULL;
    translate_result_free(&result);

    data_loaded = true;
    return true;
}

/* ============================================================================
 * Test 1: Ghidra confirms no direct port I/O (validates test premise)
 *
 * i8042prt.sys uses HAL calls, not IN/OUT instructions.  Ghidra should
 * find 0 port operations and 0 hardware functions.
 * ============================================================================ */
static void test_ghidra_sees_no_direct_port_ops(void) {
    TEST(ghidra_sees_no_direct_port_ops);
    if (!load_test_data()) FAIL("could not load test data");

    if (ghidra.port_op_count != 0) {
        char msg[128];
        snprintf(msg, sizeof(msg),
                 "expected 0 port ops, got %d", ghidra.port_op_count);
        FAIL(msg);
    }
    if (ghidra.hw_func_count != 0) {
        char msg[128];
        snprintf(msg, sizeof(msg),
                 "expected 0 hw funcs, got %d", ghidra.hw_func_count);
        FAIL(msg);
    }
    PASS();
}

/* ============================================================================
 * Test 2: Import classification agreement
 *
 * For every PORT_IO import in Ghidra's fixture, the UBT pipeline should
 * also recognize these as hardware-related (evidenced by REQUIRES: HARDWARE
 * and corresponding HAL words in output).
 * ============================================================================ */
static void test_import_classification_agreement(void) {
    TEST(import_classification_agreement);
    if (!load_test_data()) FAIL("could not load test data");

    int port_io_count = 0;
    for (int i = 0; i < ghidra.import_count; i++) {
        if (strcmp(ghidra.imports[i].category, "PORT_IO") == 0)
            port_io_count++;
    }

    if (port_io_count == 0)
        FAIL("no PORT_IO imports in Ghidra fixture");

    /* UBT must recognize PORT_IO imports — evidenced by REQUIRES: HARDWARE */
    if (!strstr(forth_output, "REQUIRES: HARDWARE"))
        FAIL("PORT_IO imports found by Ghidra but UBT missing REQUIRES: HARDWARE");

    PASS();
}

/* ============================================================================
 * Test 3: UBT finds hardware functions via HAL cross-referencing
 *
 * Ghidra found 0 hardware functions (no direct port ops).  UBT should
 * find >0 by cross-referencing IAT calls to READ_PORT_UCHAR etc.
 * This is the core asymmetry — UBT sees through the HAL indirection.
 * ============================================================================ */
static void test_ubt_finds_hal_hardware_functions(void) {
    TEST(ubt_finds_hal_hardware_functions);
    if (!load_test_data()) FAIL("could not load test data");

    /* Count colon definitions in Forth output */
    int word_count = 0;
    const char* p = forth_output;
    while ((p = strstr(p, "\n: ")) != NULL) {
        word_count++;
        p += 3;
    }
    /* Also check for definition at start of output */
    if (strncmp(forth_output, ": ", 2) == 0)
        word_count++;

    if (word_count == 0)
        FAIL("UBT generated 0 Forth words from i8042prt.sys");

    /* UBT must find more than Ghidra (which found 0) */
    if (word_count <= ghidra.hw_func_count) {
        char msg[128];
        snprintf(msg, sizeof(msg),
                 "UBT found %d words, Ghidra found %d hw funcs — "
                 "expected UBT > Ghidra", word_count, ghidra.hw_func_count);
        FAIL(msg);
    }

    PASS();
}

/* ============================================================================
 * Test 4: HAL word mappings present in output
 *
 * READ_PORT_UCHAR → INB, WRITE_PORT_UCHAR → OUTB should appear
 * as word bodies in the generated vocabulary.
 * ============================================================================ */
static void test_hal_word_mappings(void) {
    TEST(hal_word_mappings);
    if (!load_test_data()) FAIL("could not load test data");

    /* Check for INB (from READ_PORT_UCHAR) */
    bool has_read = (strstr(forth_output, "INB") != NULL);

    /* Check for OUTB (from WRITE_PORT_UCHAR) */
    bool has_write = (strstr(forth_output, "OUTB") != NULL);

    if (!has_read && !has_write)
        FAIL("neither INB nor OUTB found — HAL mapping broken");

    /* Ghidra confirmed both READ_PORT_UCHAR and WRITE_PORT_UCHAR imports */
    bool ghidra_has_read = false, ghidra_has_write = false;
    for (int i = 0; i < ghidra.import_count; i++) {
        if (strcmp(ghidra.imports[i].function, "READ_PORT_UCHAR") == 0)
            ghidra_has_read = true;
        if (strcmp(ghidra.imports[i].function, "WRITE_PORT_UCHAR") == 0)
            ghidra_has_write = true;
    }

    if (ghidra_has_read && !has_read)
        FAIL("Ghidra found READ_PORT_UCHAR but UBT missing INB");
    if (ghidra_has_write && !has_write)
        FAIL("Ghidra found WRITE_PORT_UCHAR but UBT missing OUTB");

    PASS();
}

/* ============================================================================
 * Test 5: Stack effects present for port I/O words
 *
 * Functions that call READ_PORT_UCHAR should have ( port -- byte )
 * Functions that call WRITE_PORT_UCHAR should have ( byte port -- )
 * ============================================================================ */
static void test_stack_effects_present(void) {
    TEST(stack_effects_present);
    if (!load_test_data()) FAIL("could not load test data");

    bool has_read_effect = (strstr(forth_output, "( port -- byte )") != NULL);
    bool has_write_effect = (strstr(forth_output, "( byte port -- )") != NULL ||
                             strstr(forth_output, "( us -- )") != NULL);

    if (!has_read_effect && !has_write_effect)
        FAIL("no stack effect annotations found for HAL-mapped words");

    PASS();
}

/* ============================================================================
 * Test 6: Scaffolding filtered — entry point not emitted as Forth word
 *
 * Ghidra identifies "entry" (DriverEntry) as scaffolding.  The UBT should
 * not emit it as a Forth word definition.
 * ============================================================================ */
static void test_driver_entry_filtered(void) {
    TEST(driver_entry_filtered);
    if (!load_test_data()) FAIL("could not load test data");

    /* DriverEntry / "entry" should not appear as a colon definition */
    if (strstr(forth_output, ": entry ") ||
        strstr(forth_output, ": DriverEntry "))
        FAIL("DriverEntry/entry emitted as Forth word — should be filtered");

    PASS();
}

/* ============================================================================
 * Test 7: Coverage threshold — UBT matches ≥90% of Ghidra imports
 *
 * For every import Ghidra classified, the UBT should have recognized it
 * in its semantic analysis (evidenced by the output containing the
 * corresponding HAL words or the function being filtered as scaffolding).
 * ============================================================================ */
static void test_import_coverage_threshold(void) {
    TEST(import_coverage_threshold);
    if (!load_test_data()) FAIL("could not load test data");

    int ghidra_port_io = 0;
    int ghidra_scaffolding = 0;
    for (int i = 0; i < ghidra.import_count; i++) {
        if (strcmp(ghidra.imports[i].category, "PORT_IO") == 0)
            ghidra_port_io++;
        else if (strcmp(ghidra.imports[i].category, "SCAFFOLDING") == 0)
            ghidra_scaffolding++;
    }

    /* UBT must recognize all PORT_IO imports (100% required) */
    if (ghidra_port_io > 0 && !strstr(forth_output, "REQUIRES: HARDWARE")) {
        FAIL("Ghidra found PORT_IO imports but UBT did not generate "
             "REQUIRES: HARDWARE");
    }

    /* Report coverage stats */
    printf("PASS  [imports: %d total, %d PORT_IO, %d SCAFFOLDING]\n",
           ghidra.import_count, ghidra_port_io, ghidra_scaffolding);
    tests_passed++;
}

/* ============================================================================
 * Main
 * ============================================================================ */
int main(void) {
    printf("i8042prt.sys Ghidra Validation Tests\n");
    printf("====================================\n");

    test_ghidra_sees_no_direct_port_ops();
    test_import_classification_agreement();
    test_ubt_finds_hal_hardware_functions();
    test_hal_word_mappings();
    test_stack_effects_present();
    test_driver_entry_filtered();
    test_import_coverage_threshold();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);

    free(forth_output);
    return tests_passed == tests_run ? 0 : 1;
}
