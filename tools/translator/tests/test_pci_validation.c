/* ============================================================================
 * pci.sys ReactOS Validation Tests
 * ============================================================================
 *
 * Validates the UBT pipeline against ReactOS pci.sys — a PCI bus driver
 * that uses HalGetBusData / HalSetBusData for PCI configuration space
 * access instead of direct port I/O (no IN/OUT instructions).
 *
 * Key differences from serial.sys:
 *   - No direct port I/O — uses PCI config access HAL calls
 *   - 7 hardware functions extracted via IAT cross-referencing
 *   - HAL words: PCI-READ, PCI-READ@, PCI-WRITE@
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
    uint8_t* sys_data = read_binary_file("tests/data/pci.sys", &sys_size);
    if (!sys_data) {
        fprintf(stderr, "ERROR: Cannot read pci.sys\n");
        return false;
    }

    /* Generate Forth output */
    translate_options_t opts;
    translate_options_init(&opts);
    opts.target = TARGET_FORTH;
    opts.input_filename = "pci.sys";

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
    opts.input_filename = "pci.sys";

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
    if (!load_test_data()) FAIL("could not load test data");

    if (!forth_output || strlen(forth_output) == 0)
        FAIL("Forth output is empty");
    if (!sem_output || strlen(sem_output) == 0)
        FAIL("semantic report is empty");

    PASS();
}

/* ============================================================================
 * Test 2: Hardware function count — semantic report shows 7 hw functions
 * ============================================================================ */
static void test_hardware_function_count(void) {
    TEST(hardware_function_count);
    if (!load_test_data()) FAIL("could not load test data");

    if (!strstr(sem_output, "\"hardware_functions\": 7")) {
        char msg[256];
        /* Extract actual count for diagnostic */
        const char* p = strstr(sem_output, "\"hardware_functions\":");
        if (p) {
            p += strlen("\"hardware_functions\":");
            while (*p == ' ') p++;
            int actual = atoi(p);
            snprintf(msg, sizeof(msg),
                     "expected 7 hardware functions, got %d", actual);
        } else {
            snprintf(msg, sizeof(msg),
                     "hardware_functions field not found in semantic report");
        }
        FAIL(msg);
    }

    PASS();
}

/* ============================================================================
 * Test 3: PCI config words — PCI-READ, PCI-READ@, PCI-WRITE@ present
 * ============================================================================ */
static void test_pci_config_words(void) {
    TEST(pci_config_words);
    if (!load_test_data()) FAIL("could not load test data");

    if (!strstr(forth_output, "PCI-READ"))
        FAIL("PCI-READ not found in Forth output");
    if (!strstr(forth_output, "PCI-READ@"))
        FAIL("PCI-READ@ not found in Forth output");
    if (!strstr(forth_output, "PCI-WRITE@"))
        FAIL("PCI-WRITE@ not found in Forth output");

    PASS();
}

/* ============================================================================
 * Test 4: No port I/O words — no INB or OUTB (PCI config, not port I/O)
 * ============================================================================ */
static void test_no_port_io_words(void) {
    TEST(no_port_io_words);
    if (!load_test_data()) FAIL("could not load test data");

    if (strstr(forth_output, "INB"))
        FAIL("INB found — pci.sys should not use direct port I/O");
    if (strstr(forth_output, "OUTB"))
        FAIL("OUTB found — pci.sys should not use direct port I/O");

    PASS();
}

/* ============================================================================
 * Test 5: Vocabulary structure — VOCABULARY PCI, DEFINITIONS, etc.
 * ============================================================================ */
static void test_vocabulary_structure(void) {
    TEST(vocabulary_structure);
    if (!load_test_data()) FAIL("could not load test data");

    if (!strstr(forth_output, "VOCABULARY PCI"))
        FAIL("missing VOCABULARY PCI declaration");
    if (!strstr(forth_output, "PCI DEFINITIONS"))
        FAIL("missing PCI DEFINITIONS");
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
    printf("pci.sys ReactOS Validation Tests\n");
    printf("================================\n");

    test_pipeline_succeeds();
    test_hardware_function_count();
    test_pci_config_words();
    test_no_port_io_words();
    test_vocabulary_structure();
    test_line_length_block_safe();
    test_driver_entry_filtered();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);

    free(forth_output);
    free(sem_output);
    return tests_passed == tests_run ? 0 : 1;
}
