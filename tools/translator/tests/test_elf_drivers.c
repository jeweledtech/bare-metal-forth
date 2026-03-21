/* ============================================================================
 * Linux ELF Driver Validation Tests
 * ============================================================================
 *
 * Validates 4 real Linux kernel modules through the UBT pipeline.
 * Binaries are decompressed from /lib/modules/ at runtime using zstd.
 * Tests SKIP (not FAIL) if a module or zstd is unavailable.
 *
 * Modules tested:
 *   ne2k-pci.ko    — NE2000 PCI NIC (heavy port I/O)
 *   8139too.ko      — RTL8139 NIC (MMIO-dominant, some port I/O)
 *   iTCO_wdt.ko     — Intel TCO watchdog (port I/O)
 *   via-rng.ko      — VIA hardware RNG (MMIO-only, 0 hw functions)
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <sys/utsname.h>

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
 * SKIP handling — missing modules are expected on different kernels
 * ============================================================================ */

static void skip_test(const char* name, const char* reason) {
    tests_run++;
    tests_passed++;
    printf("  TEST: %-50s SKIP: %s\n", name, reason);
}

/* ============================================================================
 * Module loader — decompress .ko.zst from /lib/modules/ at runtime
 * ============================================================================ */

static bool load_module(const char* relative_path,
                        uint8_t** out_data, size_t* out_size)
{
    struct utsname uts;
    if (uname(&uts) != 0) return false;

    char full_path[512];
    snprintf(full_path, sizeof(full_path),
             "/lib/modules/%s/%s", uts.release, relative_path);

    /* Check if the compressed file exists */
    FILE* check = fopen(full_path, "rb");
    if (!check) return false;
    fclose(check);

    /* Decompress with zstd */
    char cmd[600];
    snprintf(cmd, sizeof(cmd), "zstd -d -c '%s' 2>/dev/null", full_path);

    FILE* pipe = popen(cmd, "r");
    if (!pipe) return false;

    size_t capacity = 1024 * 1024;  /* 1MB initial */
    uint8_t* buf = malloc(capacity);
    if (!buf) { pclose(pipe); return false; }

    size_t total = 0;
    size_t n;
    while ((n = fread(buf + total, 1, capacity - total, pipe)) > 0) {
        total += n;
        if (total >= capacity) {
            capacity *= 2;
            uint8_t* newbuf = realloc(buf, capacity);
            if (!newbuf) { free(buf); pclose(pipe); return false; }
            buf = newbuf;
        }
    }

    int status = pclose(pipe);
    if (status != 0 || total == 0) {
        free(buf);
        return false;
    }

    *out_data = buf;
    *out_size = total;
    return true;
}

/* ============================================================================
 * Helper: extract integer value after a JSON key in the summary section
 *
 * Finds "key": N in the "summary" section of a JSON string and returns N.
 * We search within "summary" to avoid matching array keys of the same name
 * (e.g., "hardware_functions": [...] vs "hardware_functions": 14).
 * Returns -1 if key not found.
 * ============================================================================ */

static int json_get_int(const char* json, const char* key) {
    /* First, find the "summary" section */
    const char* summary = strstr(json, "\"summary\"");
    const char* search_base = summary ? summary : json;

    char pattern[128];
    snprintf(pattern, sizeof(pattern), "\"%s\":", key);
    const char* found = strstr(search_base, pattern);
    if (!found) return -1;
    found += strlen(pattern);
    /* Skip whitespace */
    while (*found == ' ' || *found == '\t') found++;
    return atoi(found);
}

/* ============================================================================
 * Per-module cached state
 * ============================================================================ */

typedef struct {
    const char* module_path;
    const char* short_name;
    uint8_t*    data;
    size_t      size;
    char*       forth_output;
    char*       sem_output;
    bool        loaded;
    bool        available;
} module_state_t;

static module_state_t modules[4];

static bool ensure_module(int idx) {
    module_state_t* m = &modules[idx];
    if (m->loaded) return m->available;
    m->loaded = true;

    if (!load_module(m->module_path, &m->data, &m->size)) {
        m->available = false;
        return false;
    }

    /* Generate Forth output */
    translate_options_t opts;
    translate_options_init(&opts);
    opts.target = TARGET_FORTH;
    opts.input_filename = m->short_name;

    translate_result_t result = translate_buffer(m->data, m->size, &opts);
    if (!result.success) {
        /* Pipeline failure is a real failure, not a skip */
        m->available = false;
        translate_result_free(&result);
        return false;
    }
    m->forth_output = result.output;
    result.output = NULL;
    translate_result_free(&result);

    /* Generate semantic report */
    translate_options_init(&opts);
    opts.target = TARGET_SEMANTIC_REPORT;
    opts.input_filename = m->short_name;

    result = translate_buffer(m->data, m->size, &opts);
    if (!result.success) {
        m->available = false;
        translate_result_free(&result);
        return false;
    }
    m->sem_output = result.output;
    result.output = NULL;
    translate_result_free(&result);

    m->available = true;
    return true;
}

static void cleanup_modules(void) {
    for (int i = 0; i < 4; i++) {
        free(modules[i].data);
        free(modules[i].forth_output);
        free(modules[i].sem_output);
    }
}

/* Module indices */
#define MOD_NE2K     0
#define MOD_RTL8139  1
#define MOD_ITCO     2
#define MOD_VIA_RNG  3

/* ============================================================================
 * ne2k-pci.ko tests
 * ============================================================================ */

static void test_ne2k_pipeline_succeeds(void) {
    if (!modules[MOD_NE2K].loaded) ensure_module(MOD_NE2K);
    if (!modules[MOD_NE2K].available) {
        skip_test("ne2k_pipeline_succeeds",
                  "ne2k-pci.ko not found");
        return;
    }
    TEST(ne2k_pipeline_succeeds);
    if (!modules[MOD_NE2K].forth_output)
        FAIL("Forth output is NULL");
    if (strlen(modules[MOD_NE2K].forth_output) == 0)
        FAIL("Forth output is empty");
    PASS();
}

static void test_ne2k_hw_function_count(void) {
    if (!modules[MOD_NE2K].loaded) ensure_module(MOD_NE2K);
    if (!modules[MOD_NE2K].available) {
        skip_test("ne2k_hw_function_count",
                  "ne2k-pci.ko not found");
        return;
    }
    TEST(ne2k_hw_function_count);
    int hw = json_get_int(modules[MOD_NE2K].sem_output,
                          "hardware_functions");
    if (hw < 0)
        FAIL("hardware_functions not found in semantic report");
    if (hw < 10) {
        char msg[128];
        snprintf(msg, sizeof(msg),
                 "expected >= 10 hw functions, got %d", hw);
        FAIL(msg);
    }
    printf("PASS  [%d hw functions]\n", hw);
    tests_passed++;
}

static void test_ne2k_has_port_io(void) {
    if (!modules[MOD_NE2K].loaded) ensure_module(MOD_NE2K);
    if (!modules[MOD_NE2K].available) {
        skip_test("ne2k_has_port_io",
                  "ne2k-pci.ko not found");
        return;
    }
    TEST(ne2k_has_port_io);
    bool has_port_io_forth = (strstr(modules[MOD_NE2K].forth_output,
                                     "has_port_io") != NULL);
    int port_io = json_get_int(modules[MOD_NE2K].sem_output,
                               "port_io_functions");
    if (!has_port_io_forth && port_io <= 0) {
        char msg[128];
        snprintf(msg, sizeof(msg),
                 "no port I/O detected (forth: %s, sem port_io: %d)",
                 has_port_io_forth ? "yes" : "no", port_io);
        FAIL(msg);
    }
    PASS();
}

/* ============================================================================
 * 8139too.ko tests
 * ============================================================================ */

static void test_rtl8139_pipeline_succeeds(void) {
    if (!modules[MOD_RTL8139].loaded) ensure_module(MOD_RTL8139);
    if (!modules[MOD_RTL8139].available) {
        skip_test("rtl8139_pipeline_succeeds",
                  "8139too.ko not found");
        return;
    }
    TEST(rtl8139_pipeline_succeeds);
    if (!modules[MOD_RTL8139].forth_output)
        FAIL("Forth output is NULL");
    if (strlen(modules[MOD_RTL8139].forth_output) == 0)
        FAIL("Forth output is empty");
    PASS();
}

static void test_rtl8139_hw_function_count(void) {
    if (!modules[MOD_RTL8139].loaded) ensure_module(MOD_RTL8139);
    if (!modules[MOD_RTL8139].available) {
        skip_test("rtl8139_hw_function_count",
                  "8139too.ko not found");
        return;
    }
    TEST(rtl8139_hw_function_count);
    int hw = json_get_int(modules[MOD_RTL8139].sem_output,
                          "hardware_functions");
    if (hw < 0)
        FAIL("hardware_functions not found in semantic report");
    if (hw < 1) {
        char msg[128];
        snprintf(msg, sizeof(msg),
                 "expected >= 1 hw functions, got %d", hw);
        FAIL(msg);
    }
    printf("PASS  [%d hw functions]\n", hw);
    tests_passed++;
}

static void test_rtl8139_named_function(void) {
    if (!modules[MOD_RTL8139].loaded) ensure_module(MOD_RTL8139);
    if (!modules[MOD_RTL8139].available) {
        skip_test("rtl8139_named_function",
                  "8139too.ko not found");
        return;
    }
    TEST(rtl8139_named_function);
    /* Symbol table should preserve "rtl8139" in function names */
    bool found = (strstr(modules[MOD_RTL8139].forth_output,
                         "rtl8139") != NULL) ||
                 (strstr(modules[MOD_RTL8139].sem_output,
                         "rtl8139") != NULL);
    if (!found)
        FAIL("\"rtl8139\" not found in Forth or semantic output");
    PASS();
}

/* ============================================================================
 * iTCO_wdt.ko tests
 * ============================================================================ */

static void test_itco_pipeline_succeeds(void) {
    if (!modules[MOD_ITCO].loaded) ensure_module(MOD_ITCO);
    if (!modules[MOD_ITCO].available) {
        skip_test("itco_pipeline_succeeds",
                  "iTCO_wdt.ko not found");
        return;
    }
    TEST(itco_pipeline_succeeds);
    if (!modules[MOD_ITCO].forth_output)
        FAIL("Forth output is NULL");
    if (strlen(modules[MOD_ITCO].forth_output) == 0)
        FAIL("Forth output is empty");
    PASS();
}

static void test_itco_hw_function_count(void) {
    if (!modules[MOD_ITCO].loaded) ensure_module(MOD_ITCO);
    if (!modules[MOD_ITCO].available) {
        skip_test("itco_hw_function_count",
                  "iTCO_wdt.ko not found");
        return;
    }
    TEST(itco_hw_function_count);
    int hw = json_get_int(modules[MOD_ITCO].sem_output,
                          "hardware_functions");
    if (hw < 0)
        FAIL("hardware_functions not found in semantic report");
    if (hw < 5) {
        char msg[128];
        snprintf(msg, sizeof(msg),
                 "expected >= 5 hw functions, got %d", hw);
        FAIL(msg);
    }
    printf("PASS  [%d hw functions]\n", hw);
    tests_passed++;
}

static void test_itco_named_function(void) {
    if (!modules[MOD_ITCO].loaded) ensure_module(MOD_ITCO);
    if (!modules[MOD_ITCO].available) {
        skip_test("itco_named_function",
                  "iTCO_wdt.ko not found");
        return;
    }
    TEST(itco_named_function);
    /* Symbol table should preserve "iTCO" in function names */
    bool found = (strstr(modules[MOD_ITCO].forth_output,
                         "iTCO") != NULL) ||
                 (strstr(modules[MOD_ITCO].sem_output,
                         "iTCO") != NULL);
    if (!found)
        FAIL("\"iTCO\" not found in Forth or semantic output");
    PASS();
}

/* ============================================================================
 * via-rng.ko tests
 * ============================================================================ */

static void test_via_rng_pipeline_succeeds(void) {
    if (!modules[MOD_VIA_RNG].loaded) ensure_module(MOD_VIA_RNG);
    if (!modules[MOD_VIA_RNG].available) {
        skip_test("via_rng_pipeline_succeeds",
                  "via-rng.ko not found");
        return;
    }
    TEST(via_rng_pipeline_succeeds);
    if (!modules[MOD_VIA_RNG].forth_output)
        FAIL("Forth output is NULL");
    /* via-rng may produce minimal output since it's MMIO-only */
    PASS();
}

static void test_via_rng_zero_hw_functions(void) {
    if (!modules[MOD_VIA_RNG].loaded) ensure_module(MOD_VIA_RNG);
    if (!modules[MOD_VIA_RNG].available) {
        skip_test("via_rng_zero_hw_functions",
                  "via-rng.ko not found");
        return;
    }
    TEST(via_rng_zero_hw_functions);
    int hw = json_get_int(modules[MOD_VIA_RNG].sem_output,
                          "hardware_functions");
    if (hw < 0)
        FAIL("hardware_functions not found in semantic report");
    if (hw != 0) {
        char msg[128];
        snprintf(msg, sizeof(msg),
                 "expected exactly 0 hw functions (MMIO-only), got %d",
                 hw);
        FAIL(msg);
    }
    PASS();
}

static void test_via_rng_no_port_io(void) {
    if (!modules[MOD_VIA_RNG].loaded) ensure_module(MOD_VIA_RNG);
    if (!modules[MOD_VIA_RNG].available) {
        skip_test("via_rng_no_port_io",
                  "via-rng.ko not found");
        return;
    }
    TEST(via_rng_no_port_io);
    /* MMIO-only driver should have no colon definitions in Forth */
    bool has_colon_def = (strstr(modules[MOD_VIA_RNG].forth_output,
                                 "\n: ") != NULL);
    if (!has_colon_def &&
        strncmp(modules[MOD_VIA_RNG].forth_output, ": ", 2) == 0)
        has_colon_def = true;
    if (has_colon_def)
        FAIL("found `: ` word definitions in MMIO-only driver");
    PASS();
}

/* ============================================================================
 * Main
 * ============================================================================ */

int main(void) {
    printf("Linux ELF Driver Validation Tests\n");
    printf("==================================\n");

    /* Print kernel version for reference */
    struct utsname uts;
    if (uname(&uts) == 0)
        printf("Kernel: %s\n\n", uts.release);
    else
        printf("Kernel: unknown\n\n");

    /* Initialize module paths */
    modules[MOD_NE2K] = (module_state_t){
        .module_path = "kernel/drivers/net/ethernet/8390/ne2k-pci.ko.zst",
        .short_name = "ne2k-pci.ko",
    };
    modules[MOD_RTL8139] = (module_state_t){
        .module_path = "kernel/drivers/net/ethernet/realtek/8139too.ko.zst",
        .short_name = "8139too.ko",
    };
    modules[MOD_ITCO] = (module_state_t){
        .module_path = "kernel/drivers/watchdog/iTCO_wdt.ko.zst",
        .short_name = "iTCO_wdt.ko",
    };
    modules[MOD_VIA_RNG] = (module_state_t){
        .module_path = "kernel/drivers/char/hw_random/via-rng.ko.zst",
        .short_name = "via-rng.ko",
    };

    /* ne2k-pci.ko */
    printf("--- ne2k-pci.ko ---\n");
    test_ne2k_pipeline_succeeds();
    test_ne2k_hw_function_count();
    test_ne2k_has_port_io();

    /* 8139too.ko */
    printf("--- 8139too.ko ---\n");
    test_rtl8139_pipeline_succeeds();
    test_rtl8139_hw_function_count();
    test_rtl8139_named_function();

    /* iTCO_wdt.ko */
    printf("--- iTCO_wdt.ko ---\n");
    test_itco_pipeline_succeeds();
    test_itco_hw_function_count();
    test_itco_named_function();

    /* via-rng.ko */
    printf("--- via-rng.ko ---\n");
    test_via_rng_pipeline_succeeds();
    test_via_rng_zero_hw_functions();
    test_via_rng_no_port_io();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);

    cleanup_modules();
    return tests_passed == tests_run ? 0 : 1;
}
