/* ============================================================================
 * floppy.sys ReactOS Validation — Real-World Floppy Disk Driver
 * ============================================================================
 *
 * Validates the UBT pipeline against ReactOS floppy.sys — a real Windows
 * floppy disk controller driver.  Like serial.sys, this driver uses HAL
 * calls (READ_PORT_UCHAR, WRITE_PORT_UCHAR, etc.) instead of direct IN/OUT
 * instructions.
 *
 * Expected characteristics:
 *   - 13 hardware functions extracted via HAL cross-referencing
 *   - 37 scaffolding functions filtered out (IRP/PNP/POWER handlers)
 *   - 58 total imports, 8 classified as hardware
 *   - HAL words: INB, OUTB, US-DELAY, MS-DELAY, IRQ-CONNECT,
 *     IRQ-DISCONNECT, DPC-QUEUE, MAP-PHYS
 *   - Forth vocabulary line length <= 64 chars (block-safe)
 *
 * No Ghidra fixture is used — validation is purely pipeline-based.
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

    size_t sys_size;
    uint8_t* sys_data = read_binary_file("tests/data/floppy.sys", &sys_size);
    if (!sys_data) {
        fprintf(stderr, "ERROR: Cannot read floppy.sys\n");
        return false;
    }

    /* Generate Forth output */
    translate_options_t opts;
    translate_options_init(&opts);
    opts.target = TARGET_FORTH;
    opts.input_filename = "floppy.sys";

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
    opts.input_filename = "floppy.sys";

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
 * Test 1: Pipeline succeeds — translate_buffer with TARGET_FORTH
 * ============================================================================ */
static void test_pipeline_succeeds(void) {
    TEST(pipeline_succeeds);
    if (!load_test_data()) FAIL("could not load test data");

    if (!forth_output || strlen(forth_output) == 0)
        FAIL("Forth output is empty");
    if (!sem_output || strlen(sem_output) == 0)
        FAIL("semantic report output is empty");

    PASS();
}

/* ============================================================================
 * Test 2: Hardware function count — 13 hardware functions
 *
 * floppy.sys has 13 functions that perform hardware I/O via HAL calls,
 * extracted through IAT cross-referencing.
 * ============================================================================ */
static void test_hardware_function_count(void) {
    TEST(hardware_function_count);
    if (!load_test_data()) FAIL("could not load test data");

    /* Check semantic report for 13 hardware functions */
    if (!strstr(sem_output, "\"hardware_functions\": 13")) {
        char msg[128];
        snprintf(msg, sizeof(msg),
                 "expected 13 hardware functions in semantic report");
        FAIL(msg);
    }

    PASS();
}

/* ============================================================================
 * Test 3: HAL word mappings — INB, OUTB, US-DELAY, IRQ-CONNECT present
 *
 * READ_PORT_UCHAR -> INB, WRITE_PORT_UCHAR -> OUTB,
 * KeStallExecutionProcessor -> US-DELAY,
 * IoConnectInterrupt -> IRQ-CONNECT
 * ============================================================================ */
static void test_hal_word_mappings(void) {
    TEST(hal_word_mappings);
    if (!load_test_data()) FAIL("could not load test data");

    bool has_inb = (strstr(forth_output, "INB") != NULL);
    bool has_outb = (strstr(forth_output, "OUTB") != NULL);
    bool has_us_delay = (strstr(forth_output, "US-DELAY") != NULL);
    bool has_irq_connect = (strstr(forth_output, "IRQ-CONNECT") != NULL);

    if (!has_inb)
        FAIL("INB not found — READ_PORT_UCHAR mapping broken");
    if (!has_outb)
        FAIL("OUTB not found — WRITE_PORT_UCHAR mapping broken");
    if (!has_us_delay)
        FAIL("US-DELAY not found — KeStallExecutionProcessor mapping broken");
    if (!has_irq_connect)
        FAIL("IRQ-CONNECT not found — IoConnectInterrupt mapping broken");

    PASS();
}

/* ============================================================================
 * Test 4: Stack effects present for port I/O words
 * ============================================================================ */
static void test_stack_effects_present(void) {
    TEST(stack_effects_present);
    if (!load_test_data()) FAIL("could not load test data");

    bool has_read_effect = (strstr(forth_output, "( port -- byte )") != NULL);
    bool has_write_effect = (strstr(forth_output, "( byte port -- )") != NULL);

    if (!has_read_effect)
        FAIL("missing ( port -- byte ) stack effect for INB");
    if (!has_write_effect)
        FAIL("missing ( byte port -- ) stack effect for OUTB");

    PASS();
}

/* ============================================================================
 * Test 5: Vocabulary structure — VOCABULARY, DEFINITIONS, PREVIOUS
 * ============================================================================ */
static void test_vocabulary_structure(void) {
    TEST(vocabulary_structure);
    if (!load_test_data()) FAIL("could not load test data");

    if (!strstr(forth_output, "VOCABULARY FLOPPY"))
        FAIL("missing VOCABULARY FLOPPY declaration");
    if (!strstr(forth_output, "FLOPPY DEFINITIONS"))
        FAIL("missing FLOPPY DEFINITIONS");
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
 *
 * Every line in the Forth output must fit in a 64-char block line.
 * ============================================================================ */
static void test_line_length_block_safe(void) {
    TEST(line_length_block_safe);
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
 * Test 7: Semantic report counts — 58 total imports, 8 hardware imports
 * ============================================================================ */
static void test_semantic_report_counts(void) {
    TEST(semantic_report_counts);
    if (!load_test_data()) FAIL("could not load test data");

    bool has_58_imports = (strstr(sem_output, "\"total_imports\": 58") != NULL);
    bool has_8_hw_imports = (strstr(sem_output, "\"hardware_imports\": 8") != NULL);

    if (!has_58_imports)
        FAIL("semantic report missing 58 total imports");
    if (!has_8_hw_imports)
        FAIL("semantic report missing 8 hardware imports");

    PASS();
}

/* ============================================================================
 * Test 8: Scaffolding filtered — DriverEntry not in Forth output
 * ============================================================================ */
static void test_driver_entry_filtered(void) {
    TEST(driver_entry_filtered);
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
    printf("floppy.sys ReactOS Validation Tests\n");
    printf("====================================\n");

    test_pipeline_succeeds();
    test_hardware_function_count();
    test_hal_word_mappings();
    test_stack_effects_present();
    test_vocabulary_structure();
    test_line_length_block_safe();
    test_semantic_report_counts();
    test_driver_entry_filtered();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);

    free(forth_output);
    free(sem_output);
    return tests_passed == tests_run ? 0 : 1;
}
