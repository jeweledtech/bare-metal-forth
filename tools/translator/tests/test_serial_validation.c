/* ============================================================================
 * serial.sys Ghidra Validation — ReactOS Real-World UART Driver
 * ============================================================================
 *
 * Validates the UBT pipeline against Ghidra's analysis of a REAL Windows
 * driver: ReactOS serial.sys (GPL, 16550 UART).  This is the "proof of
 * concept" — the first real Windows driver through the complete pipeline.
 *
 * Like i8042prt.sys, this driver uses HAL calls (READ_PORT_UCHAR,
 * WRITE_PORT_UCHAR) instead of direct IN/OUT, so Ghidra finds 0 hardware
 * functions and the translator's IAT cross-referencing is the star.
 *
 * Additional validation beyond i8042:
 *   - 9 hardware functions (vs i8042's 9) — independently verified via
 *     .rossym debug symbols against ReactOS source function names
 *   - UART-specific HAL calls: SerialSetBaudRate, SerialSetLineControl,
 *     SerialSendByte, SerialReceiveByte, SerialInterruptService
 *   - DPC-QUEUE and IRQ-CONNECT used in interrupt handling
 *   - Forth vocabulary line length ≤ 64 chars (block-safe)
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
 * Minimal JSON helpers — same pattern as test_i8042_validation.c
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
static char* sem_output = NULL;
static bool data_loaded = false;

static bool load_test_data(void) {
    if (data_loaded) return true;

    char* json = read_text_file(
        "tests/data/fixtures/serial.ghidra.json");
    if (!json) {
        fprintf(stderr, "ERROR: Cannot read serial.sys Ghidra fixture\n");
        return false;
    }
    if (!parse_ghidra_report(json, &ghidra)) {
        fprintf(stderr, "ERROR: Failed to parse Ghidra fixture\n");
        free(json);
        return false;
    }
    free(json);

    size_t sys_size;
    uint8_t* sys_data = read_binary_file("tests/data/serial.sys", &sys_size);
    if (!sys_data) {
        fprintf(stderr, "ERROR: Cannot read serial.sys\n");
        return false;
    }

    /* Generate Forth output */
    translate_options_t opts;
    translate_options_init(&opts);
    opts.target = TARGET_FORTH;
    opts.input_filename = "serial.sys";

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
    opts.input_filename = "serial.sys";

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
 * Test 1: Ghidra confirms no direct port I/O
 *
 * serial.sys uses HAL calls (READ_PORT_UCHAR / WRITE_PORT_UCHAR), not
 * direct IN/OUT instructions.  Ghidra should find 0 port operations.
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
 * Ghidra classifies READ_PORT_UCHAR and WRITE_PORT_UCHAR as PORT_IO.
 * UBT must also recognize these as hardware-related.
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

    if (port_io_count != 2) {
        char msg[128];
        snprintf(msg, sizeof(msg),
                 "expected 2 PORT_IO imports (READ/WRITE), got %d", port_io_count);
        FAIL(msg);
    }

    if (!strstr(forth_output, "REQUIRES: HARDWARE"))
        FAIL("PORT_IO imports found by Ghidra but UBT missing REQUIRES: HARDWARE");

    PASS();
}

/* ============================================================================
 * Test 3: UBT finds exactly 9 hardware functions
 *
 * Verified independently via .rossym debug symbols:
 *   SerialSetBaudRate, SerialSetLineControl, SerialDeviceControl,
 *   SerialDetectUartType, SerialReceiveByte, SerialSendByte,
 *   SerialInterruptService, SerialPnpStartDevice, SerialRead
 * ============================================================================ */
static void test_ubt_finds_9_hardware_functions(void) {
    TEST(ubt_finds_9_hardware_functions);
    if (!load_test_data()) FAIL("could not load test data");

    /* Count colon definitions in Forth output */
    int word_count = 0;
    const char* p = forth_output;
    while ((p = strstr(p, "\n: ")) != NULL) {
        word_count++;
        p += 3;
    }
    if (strncmp(forth_output, ": ", 2) == 0)
        word_count++;

    if (word_count != 9) {
        char msg[128];
        snprintf(msg, sizeof(msg),
                 "expected 9 hardware functions, got %d", word_count);
        FAIL(msg);
    }

    /* Ghidra found 0 — translator found 9 through HAL cross-referencing */
    if (word_count <= ghidra.hw_func_count) {
        char msg[128];
        snprintf(msg, sizeof(msg),
                 "UBT found %d words, Ghidra found %d — "
                 "expected UBT > Ghidra", word_count, ghidra.hw_func_count);
        FAIL(msg);
    }

    PASS();
}

/* ============================================================================
 * Test 4: HAL word mappings — INB and OUTB present
 *
 * READ_PORT_UCHAR → INB, WRITE_PORT_UCHAR → OUTB
 * ============================================================================ */
static void test_hal_word_mappings(void) {
    TEST(hal_word_mappings);
    if (!load_test_data()) FAIL("could not load test data");

    bool has_inb = (strstr(forth_output, "INB") != NULL);
    bool has_outb = (strstr(forth_output, "OUTB") != NULL);

    if (!has_inb)
        FAIL("INB not found — READ_PORT_UCHAR mapping broken");
    if (!has_outb)
        FAIL("OUTB not found — WRITE_PORT_UCHAR mapping broken");

    PASS();
}

/* ============================================================================
 * Test 5: Stack effects present for port I/O words
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
 * Test 6: Interrupt infrastructure — DPC-QUEUE and IRQ-CONNECT
 *
 * SerialInterruptService uses KeInsertQueueDpc (→ DPC-QUEUE).
 * SerialPnpStartDevice uses IoConnectInterrupt (→ IRQ-CONNECT).
 * ============================================================================ */
static void test_interrupt_infrastructure(void) {
    TEST(interrupt_infrastructure);
    if (!load_test_data()) FAIL("could not load test data");

    bool has_dpc = (strstr(forth_output, "DPC-QUEUE") != NULL);
    bool has_irq = (strstr(forth_output, "IRQ-CONNECT") != NULL);

    if (!has_dpc)
        FAIL("DPC-QUEUE not found — ISR DPC dispatch missing");
    if (!has_irq)
        FAIL("IRQ-CONNECT not found — interrupt hookup missing");

    PASS();
}

/* ============================================================================
 * Test 7: Scaffolding filtered — DriverEntry not in Forth output
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
 * Test 8: Line length ≤ 64 chars (block-safe)
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

    printf("PASS  [%d lines, all ≤ 64 chars]\n", line_num);
    tests_passed++;
}

/* ============================================================================
 * Test 9: Semantic report structure — 47 imports, 9 hw functions
 * ============================================================================ */
static void test_semantic_report_structure(void) {
    TEST(semantic_report_structure);
    if (!load_test_data()) FAIL("could not load test data");

    /* Check semantic report has expected counts */
    bool has_47_imports = (strstr(sem_output, "\"total_imports\": 47") != NULL);
    bool has_9_hw = (strstr(sem_output, "\"hardware_functions\": 9") != NULL);
    bool has_6_hw_imports = (strstr(sem_output, "\"hardware_imports\": 6") != NULL);

    if (!has_47_imports)
        FAIL("semantic report missing 47 total imports");
    if (!has_9_hw)
        FAIL("semantic report missing 9 hardware functions");
    if (!has_6_hw_imports)
        FAIL("semantic report missing 6 hardware imports");

    PASS();
}

/* ============================================================================
 * Test 10: Import count agreement between Ghidra and UBT
 * ============================================================================ */
static void test_import_count_agreement(void) {
    TEST(import_count_agreement);
    if (!load_test_data()) FAIL("could not load test data");

    /* Ghidra found 47 imports, UBT semantic report should match */
    if (ghidra.import_count != 47) {
        char msg[128];
        snprintf(msg, sizeof(msg),
                 "Ghidra fixture has %d imports, expected 47",
                 ghidra.import_count);
        FAIL(msg);
    }

    bool ubt_has_47 = (strstr(sem_output, "\"total_imports\": 47") != NULL);
    if (!ubt_has_47)
        FAIL("UBT reports different import count than Ghidra");

    PASS();
}

/* ============================================================================
 * Test 11: Vocabulary structure — VOCABULARY, DEFINITIONS, PREVIOUS
 * ============================================================================ */
static void test_vocabulary_structure(void) {
    TEST(vocabulary_structure);
    if (!load_test_data()) FAIL("could not load test data");

    if (!strstr(forth_output, "VOCABULARY SERIAL"))
        FAIL("missing VOCABULARY declaration");
    if (!strstr(forth_output, "SERIAL DEFINITIONS"))
        FAIL("missing DEFINITIONS");
    if (!strstr(forth_output, "ALSO HARDWARE"))
        FAIL("missing ALSO HARDWARE");
    if (!strstr(forth_output, "PREVIOUS"))
        FAIL("missing PREVIOUS");
    if (!strstr(forth_output, "FORTH DEFINITIONS"))
        FAIL("missing FORTH DEFINITIONS");

    PASS();
}

/* ============================================================================
 * Main
 * ============================================================================ */
int main(void) {
    printf("serial.sys ReactOS Validation Tests\n");
    printf("====================================\n");

    test_ghidra_sees_no_direct_port_ops();
    test_import_classification_agreement();
    test_ubt_finds_9_hardware_functions();
    test_hal_word_mappings();
    test_stack_effects_present();
    test_interrupt_infrastructure();
    test_driver_entry_filtered();
    test_line_length_block_safe();
    test_semantic_report_structure();
    test_import_count_agreement();
    test_vocabulary_structure();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);

    free(forth_output);
    free(sem_output);
    return tests_passed == tests_run ? 0 : 1;
}
