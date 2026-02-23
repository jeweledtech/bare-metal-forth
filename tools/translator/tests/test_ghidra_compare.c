/* ============================================================================
 * Ghidra Comparison Test — Semantic Validation
 * ============================================================================
 *
 * Loads a cached Ghidra JSON fixture and the same .sys binary, runs the
 * translator pipeline, and compares results at the semantic level.
 *
 * Asymmetric comparison: the translator must find everything Ghidra found
 * (no false negatives), but MAY find more (extra ports, extra functions).
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
 * Ghidra report structures
 * ============================================================================ */

#define MAX_PORT_OPS 64
#define MAX_HW_FUNCS 16
#define MAX_IMPORTS 32
#define MAX_SCAFFOLDING 16

typedef struct {
    char port[16];       /* "0xF8" */
    char direction[8];   /* "read" or "write" */
    char function[64];   /* "UART_INIT" */
} ghidra_port_op_t;

typedef struct {
    char name[64];
    char ports_accessed[8][16];
    int port_count;
} ghidra_hw_func_t;

typedef struct {
    char dll[64];
    char function[64];
    char category[32];
} ghidra_import_t;

typedef struct {
    int schema_version;
    ghidra_port_op_t port_ops[MAX_PORT_OPS];
    int port_op_count;
    ghidra_hw_func_t hw_funcs[MAX_HW_FUNCS];
    int hw_func_count;
    ghidra_import_t imports[MAX_IMPORTS];
    int import_count;
    char scaffolding_names[MAX_SCAFFOLDING][64];
    int scaffolding_count;
} ghidra_report_t;

/* ============================================================================
 * Minimal JSON parser — only handles the known fixture schema
 * ============================================================================ */

/* Extract a quoted string value after a key. Returns pointer past the closing
 * quote, or NULL on failure. Copies at most max_len-1 chars into out. */
static const char* extract_string(const char* p, const char* key,
                                  char* out, size_t max_len) {
    char pattern[128];
    snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    const char* found = strstr(p, pattern);
    if (!found) return NULL;

    /* Skip past key and find the colon, then the opening quote of the value */
    found += strlen(pattern);
    found = strchr(found, ':');
    if (!found) return NULL;
    found = strchr(found, '"');
    if (!found) return NULL;
    found++; /* skip opening quote */

    size_t i = 0;
    while (*found && *found != '"' && i < max_len - 1) {
        out[i++] = *found++;
    }
    out[i] = '\0';
    if (*found == '"') found++;
    return found;
}

/* Find the start of a JSON array by name. Returns pointer to the '['. */
static const char* find_array(const char* json, const char* name) {
    char pattern[128];
    snprintf(pattern, sizeof(pattern), "\"%s\"", name);
    const char* found = strstr(json, pattern);
    if (!found) return NULL;
    found = strchr(found, '[');
    return found;
}

/* Find the end of a JSON array starting at '['. Returns pointer to ']'. */
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

/* Parse a single port_operations entry from within '{' ... '}' */
static const char* parse_port_op(const char* p, ghidra_port_op_t* op) {
    const char* obj_start = strchr(p, '{');
    if (!obj_start) return NULL;
    const char* obj_end = strchr(obj_start, '}');
    if (!obj_end) return NULL;

    /* Work within this object */
    char buf[256];
    size_t len = (size_t)(obj_end - obj_start + 1);
    if (len >= sizeof(buf)) len = sizeof(buf) - 1;
    memcpy(buf, obj_start, len);
    buf[len] = '\0';

    extract_string(buf, "port", op->port, sizeof(op->port));
    extract_string(buf, "direction", op->direction, sizeof(op->direction));
    extract_string(buf, "function", op->function, sizeof(op->function));

    return obj_end + 1;
}

/* Parse a ports_accessed array like ["0xF8", "0xF9"] */
static void parse_ports_accessed(const char* obj, ghidra_hw_func_t* func) {
    const char* arr = strstr(obj, "\"ports_accessed\"");
    if (!arr) return;
    arr = strchr(arr, '[');
    if (!arr) return;
    arr++; /* skip '[' */

    func->port_count = 0;
    while (*arr && *arr != ']' && func->port_count < 8) {
        const char* q = strchr(arr, '"');
        if (!q || q > strchr(arr, ']')) break;
        q++;
        size_t i = 0;
        while (*q && *q != '"' && i < 15) {
            func->ports_accessed[func->port_count][i++] = *q++;
        }
        func->ports_accessed[func->port_count][i] = '\0';
        func->port_count++;
        if (*q == '"') q++;
        arr = q;
    }
}

/* Parse a single hardware_functions entry */
static const char* parse_hw_func(const char* p, ghidra_hw_func_t* func) {
    const char* obj_start = strchr(p, '{');
    if (!obj_start) return NULL;

    /* Find matching '}' accounting for nested arrays */
    int depth = 0;
    const char* q = obj_start;
    const char* obj_end = NULL;
    while (*q) {
        if (*q == '{') depth++;
        else if (*q == '}') { depth--; if (depth == 0) { obj_end = q; break; } }
        else if (*q == '"') { q++; while (*q && *q != '"') { if (*q == '\\') q++; q++; } }
        q++;
    }
    if (!obj_end) return NULL;

    /* Copy object to buffer */
    size_t len = (size_t)(obj_end - obj_start + 1);
    char* buf = malloc(len + 1);
    memcpy(buf, obj_start, len);
    buf[len] = '\0';

    extract_string(buf, "name", func->name, sizeof(func->name));
    parse_ports_accessed(buf, func);

    free(buf);
    return obj_end + 1;
}

/* Parse a single imports entry */
static const char* parse_import(const char* p, ghidra_import_t* imp) {
    const char* obj_start = strchr(p, '{');
    if (!obj_start) return NULL;
    const char* obj_end = strchr(obj_start, '}');
    if (!obj_end) return NULL;

    char buf[256];
    size_t len = (size_t)(obj_end - obj_start + 1);
    if (len >= sizeof(buf)) len = sizeof(buf) - 1;
    memcpy(buf, obj_start, len);
    buf[len] = '\0';

    extract_string(buf, "dll", imp->dll, sizeof(imp->dll));
    extract_string(buf, "function", imp->function, sizeof(imp->function));
    extract_string(buf, "category", imp->category, sizeof(imp->category));

    return obj_end + 1;
}

/* Parse a single scaffolding_functions entry — we only need the name */
static const char* parse_scaffolding(const char* p, char* name, size_t name_size) {
    const char* obj_start = strchr(p, '{');
    if (!obj_start) return NULL;
    const char* obj_end = strchr(obj_start, '}');
    if (!obj_end) return NULL;

    char buf[256];
    size_t len = (size_t)(obj_end - obj_start + 1);
    if (len >= sizeof(buf)) len = sizeof(buf) - 1;
    memcpy(buf, obj_start, len);
    buf[len] = '\0';

    extract_string(buf, "name", name, name_size);

    return obj_end + 1;
}

/* Parse the full Ghidra JSON report */
static bool parse_ghidra_report(const char* json, ghidra_report_t* report) {
    memset(report, 0, sizeof(*report));

    /* schema_version */
    const char* sv = strstr(json, "\"schema_version\"");
    if (sv) {
        sv = strchr(sv, ':');
        if (sv) report->schema_version = atoi(sv + 1);
    }

    /* port_operations */
    const char* arr = find_array(json, "port_operations");
    if (arr) {
        const char* arr_end = find_array_end(arr);
        const char* p = arr + 1;
        while (p && p < arr_end && report->port_op_count < MAX_PORT_OPS) {
            p = parse_port_op(p, &report->port_ops[report->port_op_count]);
            if (p) report->port_op_count++;
        }
    }

    /* hardware_functions */
    arr = find_array(json, "hardware_functions");
    if (arr) {
        const char* arr_end = find_array_end(arr);
        const char* p = arr + 1;
        while (p && p < arr_end && report->hw_func_count < MAX_HW_FUNCS) {
            p = parse_hw_func(p, &report->hw_funcs[report->hw_func_count]);
            if (p) report->hw_func_count++;
        }
    }

    /* imports */
    arr = find_array(json, "imports");
    if (arr) {
        const char* arr_end = find_array_end(arr);
        const char* p = arr + 1;
        while (p && p < arr_end && report->import_count < MAX_IMPORTS) {
            p = parse_import(p, &report->imports[report->import_count]);
            if (p) report->import_count++;
        }
    }

    /* scaffolding_functions */
    arr = find_array(json, "scaffolding_functions");
    if (arr) {
        const char* arr_end = find_array_end(arr);
        const char* p = arr + 1;
        while (p && p < arr_end && report->scaffolding_count < MAX_SCAFFOLDING) {
            p = parse_scaffolding(p,
                    report->scaffolding_names[report->scaffolding_count],
                    sizeof(report->scaffolding_names[0]));
            if (p) report->scaffolding_count++;
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
 * Shared test state — loaded once, used by all tests
 * ============================================================================ */

static ghidra_report_t ghidra_report;
static char* forth_output = NULL;
static bool data_loaded = false;

static bool load_test_data(void) {
    if (data_loaded) return true;

    /* Load Ghidra JSON fixture */
    char* json = read_text_file(
        "tests/data/fixtures/serial16550_synth.ghidra.json");
    if (!json) {
        fprintf(stderr, "ERROR: Cannot read Ghidra JSON fixture\n");
        return false;
    }

    if (!parse_ghidra_report(json, &ghidra_report)) {
        fprintf(stderr, "ERROR: Failed to parse Ghidra JSON\n");
        free(json);
        return false;
    }
    free(json);

    /* Load .sys binary */
    size_t sys_size;
    uint8_t* sys_data = read_binary_file(
        "tests/data/serial16550_synth.sys", &sys_size);
    if (!sys_data) {
        fprintf(stderr, "ERROR: Cannot read .sys binary\n");
        return false;
    }

    /* Run translator pipeline */
    translate_options_t opts;
    translate_options_init(&opts);
    opts.target = TARGET_FORTH;
    opts.vocab_name = "SERIAL-16550";
    opts.input_filename = "serial16550_synth.sys";

    translate_result_t result = translate_buffer(sys_data, sys_size, &opts);
    free(sys_data);

    if (!result.success) {
        fprintf(stderr, "ERROR: Translator pipeline failed: %s\n",
                result.error_message ? result.error_message : "unknown");
        translate_result_free(&result);
        return false;
    }

    /* Keep the output string, free the rest */
    forth_output = result.output;
    result.output = NULL;
    translate_result_free(&result);

    data_loaded = true;
    return true;
}

/* ============================================================================
 * Test 1: All Ghidra ports found in Forth output
 *
 * For each unique port in port_operations, verify the hex value (e.g. "F8")
 * appears in the Forth output as CONSTANT REG-XX.
 * ============================================================================ */
static void test_all_ghidra_ports_found_in_forth(void) {
    TEST(all_ghidra_ports_found_in_forth);

    if (!load_test_data()) FAIL("could not load test data");

    /* Collect unique ports from Ghidra report */
    char unique_ports[MAX_PORT_OPS][16];
    int unique_count = 0;

    for (int i = 0; i < ghidra_report.port_op_count; i++) {
        const char* port = ghidra_report.port_ops[i].port;
        /* Check if already in unique list */
        bool found = false;
        for (int j = 0; j < unique_count; j++) {
            if (strcmp(unique_ports[j], port) == 0) { found = true; break; }
        }
        if (!found && unique_count < MAX_PORT_OPS) {
            strncpy(unique_ports[unique_count], port,
                    sizeof(unique_ports[0]) - 1);
            unique_ports[unique_count][sizeof(unique_ports[0]) - 1] = '\0';
            unique_count++;
        }
    }

    if (unique_count == 0) FAIL("no ports in Ghidra report");

    /* For each unique port, check Forth output contains it */
    for (int i = 0; i < unique_count; i++) {
        /* Convert "0xF8" to uppercase hex without prefix: "F8" */
        const char* port = unique_ports[i];
        const char* hex = port;
        if (hex[0] == '0' && (hex[1] == 'x' || hex[1] == 'X'))
            hex += 2;

        /* Build uppercase version */
        char upper[16];
        size_t k = 0;
        while (hex[k] && k < sizeof(upper) - 1) {
            upper[k] = (char)toupper((unsigned char)hex[k]);
            k++;
        }
        upper[k] = '\0';

        /* Look for REG-XX in the Forth output */
        char pattern[32];
        snprintf(pattern, sizeof(pattern), "REG-%s", upper);

        if (!strstr(forth_output, pattern)) {
            char msg[128];
            snprintf(msg, sizeof(msg),
                     "port %s not found as %s",
                     unique_ports[i], pattern);
            FAIL(msg);
        }
    }

    PASS();
}

/* ============================================================================
 * Test 2: All Ghidra hardware functions found in Forth output
 *
 * For each function in hardware_functions, verify the name appears as
 * ": FUNCNAME" in the Forth output.
 * ============================================================================ */
static void test_all_ghidra_hw_funcs_found_in_forth(void) {
    TEST(all_ghidra_hw_funcs_found_in_forth);

    if (!load_test_data()) FAIL("could not load test data");

    if (ghidra_report.hw_func_count == 0) FAIL("no hardware functions in Ghidra report");

    for (int i = 0; i < ghidra_report.hw_func_count; i++) {
        const char* name = ghidra_report.hw_funcs[i].name;

        /* Check for ": FUNCNAME" pattern (colon definition) */
        char pattern[80];
        snprintf(pattern, sizeof(pattern), ": %s", name);

        if (!strstr(forth_output, pattern)) {
            char msg[128];
            snprintf(msg, sizeof(msg),
                     "hw func '%s' not found as '%s'",
                     name, pattern);
            FAIL(msg);
        }
    }

    PASS();
}

/* ============================================================================
 * Test 3: Scaffolding functions filtered out
 *
 * For each function in scaffolding_functions, verify the name does NOT appear
 * as a word definition (": NAME") in the Forth output.
 * ============================================================================ */
static void test_scaffolding_filtered_out(void) {
    TEST(scaffolding_filtered_out);

    if (!load_test_data()) FAIL("could not load test data");

    if (ghidra_report.scaffolding_count == 0)
        FAIL("no scaffolding functions in Ghidra report");

    for (int i = 0; i < ghidra_report.scaffolding_count; i++) {
        const char* name = ghidra_report.scaffolding_names[i];

        /* Check that ": NAME" does NOT appear */
        char pattern[80];
        snprintf(pattern, sizeof(pattern), ": %s", name);

        if (strstr(forth_output, pattern)) {
            char msg[128];
            snprintf(msg, sizeof(msg),
                     "scaffolding '%s' found as '%s'",
                     name, pattern);
            FAIL(msg);
        }
    }

    PASS();
}

/* ============================================================================
 * Test 4: HAL PORT_IO imports generate REQUIRES: HARDWARE
 *
 * If any import has category "PORT_IO", the Forth output must contain
 * "REQUIRES: HARDWARE".
 * ============================================================================ */
static void test_hal_imports_generate_requires(void) {
    TEST(hal_imports_generate_requires);

    if (!load_test_data()) FAIL("could not load test data");

    /* Check if Ghidra found any PORT_IO imports */
    bool has_port_io = false;
    for (int i = 0; i < ghidra_report.import_count; i++) {
        if (strcmp(ghidra_report.imports[i].category, "PORT_IO") == 0) {
            has_port_io = true;
            break;
        }
    }

    if (!has_port_io) FAIL("no PORT_IO imports in Ghidra report");

    if (!strstr(forth_output, "REQUIRES: HARDWARE")) {
        FAIL("PORT_IO imports found but Forth output missing "
             "'REQUIRES: HARDWARE'");
    }

    PASS();
}

/* ============================================================================
 * Main
 * ============================================================================ */
int main(void) {
    printf("Ghidra Comparison Tests\n");
    printf("=======================\n");

    test_all_ghidra_ports_found_in_forth();
    test_all_ghidra_hw_funcs_found_in_forth();
    test_scaffolding_filtered_out();
    test_hal_imports_generate_requires();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);

    free(forth_output);
    return tests_passed == tests_run ? 0 : 1;
}
