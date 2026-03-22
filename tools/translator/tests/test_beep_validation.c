/* ============================================================================
 * beep.sys ReactOS Validation Tests
 * ============================================================================
 *
 * Validates the UBT pipeline against ReactOS beep.sys — a simple driver
 * that uses HalMakeBeep for PIT/speaker access instead of direct port I/O
 * (no IN/OUT instructions).
 *
 * Key differences from serial.sys:
 *   - No direct port I/O — uses HalMakeBeep HAL call
 *   - 3 hardware functions extracted via IAT cross-referencing
 *   - HAL word: BEEP (from HalMakeBeep)
 *   - No INB/OUTB in Forth output
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
static bool skipped = false;

#define TEST(name) do { \
    tests_run++; \
    printf("  TEST: %-50s ", #name); \
} while(0)

#define PASS() do { tests_passed++; printf("PASS\n"); } while(0)
#define FAIL(msg) do { printf("FAIL: %s\n", msg); return; } while(0)

#define SKIP_IF_ABSENT() do { \
    if (skipped) { \
        tests_passed++; \
        printf("SKIP  [beep.sys not found]\n"); \
        return; \
    } \
} while(0)

/* ============================================================================
 * File I/O helpers
 * ============================================================================ */

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

static char* forth_output = NULL;
static char* sem_output = NULL;
static bool data_loaded = false;

static bool load_test_data(void) {
    if (data_loaded) return true;
    if (skipped) return false;

    size_t sys_size;
    uint8_t* sys_data = read_binary_file("tests/data/beep.sys", &sys_size);
    if (!sys_data) {
        skipped = true;
        return false;
    }

    /* Generate Forth output */
    translate_options_t opts;
    translate_options_init(&opts);
    opts.target = TARGET_FORTH;
    opts.input_filename = "beep.sys";

    translate_result_t result = translate_buffer(sys_data, sys_size, &opts);
    if (!result.success) {
        fprintf(stderr, "ERROR: Forth pipeline failed: %s\n",
                result.error_message ? result.error_message : "unknown");
        translate_result_free(&result);
        free(sys_data);
        return false;
    }
    forth_output = result.output;
    result.output = NULL;
    translate_result_free(&result);

    /* Generate semantic report */
    translate_options_init(&opts);
    opts.target = TARGET_SEMANTIC_REPORT;
    opts.input_filename = "beep.sys";

    result = translate_buffer(sys_data, sys_size, &opts);
    free(sys_data);
    if (!result.success) {
        fprintf(stderr, "ERROR: Semantic report failed: %s\n",
                result.error_message ? result.error_message : "unknown");
        translate_result_free(&result);
        return false;
    }
    sem_output = result.output;
    result.output = NULL;
    translate_result_free(&result);

    data_loaded = true;
    return true;
}

/* ============================================================================
 * Test 1: Pipeline succeeds — translate_buffer with TARGET_FORTH succeeds
 * ============================================================================ */
static void test_pipeline_succeeds(void) {
    TEST(pipeline_succeeds);
    SKIP_IF_ABSENT();
    if (!load_test_data()) FAIL("could not load test data");

    if (!forth_output || strlen(forth_output) == 0)
        FAIL("Forth output is empty");
    if (!sem_output || strlen(sem_output) == 0)
        FAIL("semantic report is empty");

    PASS();
}

/* ============================================================================
 * Test 2: Hardware function count — semantic report shows 3 hw functions
 * ============================================================================ */
static void test_hw_function_count(void) {
    TEST(hw_function_count);
    SKIP_IF_ABSENT();
    if (!load_test_data()) FAIL("could not load test data");

    if (!strstr(sem_output, "\"hardware_functions\": 3")) {
        char msg[256];
        /* Extract actual count for diagnostic */
        const char* p = strstr(sem_output, "\"hardware_functions\":");
        if (p) {
            p += strlen("\"hardware_functions\":");
            while (*p == ' ') p++;
            int actual = atoi(p);
            snprintf(msg, sizeof(msg),
                     "expected 3 hardware functions, got %d", actual);
        } else {
            snprintf(msg, sizeof(msg),
                     "hardware_functions field not found in semantic report");
        }
        FAIL(msg);
    }

    PASS();
}

/* ============================================================================
 * Test 3: BEEP word present — from HalMakeBeep HAL function
 * ============================================================================ */
static void test_beep_word_present(void) {
    TEST(beep_word_present);
    SKIP_IF_ABSENT();
    if (!load_test_data()) FAIL("could not load test data");

    if (!strstr(forth_output, "BEEP"))
        FAIL("BEEP not found in Forth output");

    PASS();
}

/* ============================================================================
 * Test 4: REQUIRES HARDWARE — dependency on HARDWARE vocabulary
 * ============================================================================ */
static void test_requires_hardware(void) {
    TEST(requires_hardware);
    SKIP_IF_ABSENT();
    if (!load_test_data()) FAIL("could not load test data");

    if (!strstr(forth_output, "REQUIRES: HARDWARE"))
        FAIL("REQUIRES: HARDWARE not found in Forth output");

    PASS();
}

/* ============================================================================
 * Test 5: Vocabulary structure — VOCABULARY BEEP, DEFINITIONS, etc.
 * ============================================================================ */
static void test_vocabulary_structure(void) {
    TEST(vocabulary_structure);
    SKIP_IF_ABSENT();
    if (!load_test_data()) FAIL("could not load test data");

    if (!strstr(forth_output, "VOCABULARY BEEP"))
        FAIL("missing VOCABULARY BEEP declaration");
    if (!strstr(forth_output, "BEEP DEFINITIONS"))
        FAIL("missing BEEP DEFINITIONS");
    if (!strstr(forth_output, "ALSO HARDWARE"))
        FAIL("missing ALSO HARDWARE");
    if (!strstr(forth_output, "PREVIOUS"))
        FAIL("missing PREVIOUS");
    if (!strstr(forth_output, "FORTH DEFINITIONS"))
        FAIL("missing FORTH DEFINITIONS");

    PASS();
}

/* ============================================================================
 * Test 6: Line length <= 64 chars (block-safe)
 * ============================================================================ */
static void test_line_length_block_safe(void) {
    TEST(line_length_block_safe);
    SKIP_IF_ABSENT();
    if (!load_test_data()) FAIL("could not load test data");

    const char* p = forth_output;
    int line_num = 1;
    while (*p) {
        const char* eol = strchr(p, '\n');
        size_t len;
        if (eol)
            len = (size_t)(eol - p);
        else
            len = strlen(p);

        if (len > 64) {
            char msg[128];
            snprintf(msg, sizeof(msg),
                     "line %d is %zu chars (max 64): %.40s...",
                     line_num, len, p);
            FAIL(msg);
        }

        if (eol)
            p = eol + 1;
        else
            break;
        line_num++;
    }

    printf("PASS  [%d lines, all <= 64 chars]\n", line_num);
    tests_passed++;
}

/* ============================================================================
 * Test 7: Scaffolding filtered — no DriverEntry in Forth output
 * ============================================================================ */
static void test_driver_entry_filtered(void) {
    TEST(driver_entry_filtered);
    SKIP_IF_ABSENT();
    if (!load_test_data()) FAIL("could not load test data");

    if (strstr(forth_output, ": entry ") ||
        strstr(forth_output, ": DriverEntry "))
        FAIL("DriverEntry emitted as Forth word — should be filtered");

    PASS();
}

/* ============================================================================
 * Main
 * ============================================================================ */
int main(void) {
    printf("beep.sys ReactOS Validation Tests\n");
    printf("=================================\n");

    /* Attempt to load — sets skipped=true if beep.sys absent */
    load_test_data();

    test_pipeline_succeeds();
    test_hw_function_count();
    test_beep_word_present();
    test_requires_hardware();
    test_vocabulary_structure();
    test_line_length_block_safe();
    test_driver_entry_filtered();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);

    free(forth_output);
    free(sem_output);
    return tests_passed == tests_run ? 0 : 1;
}
