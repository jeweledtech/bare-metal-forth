/* ============================================================================
 * HP Real Hardware Driver Validation Tests
 * ============================================================================
 *
 * Validates 8 real HP Windows 10/11 x64 drivers through the UBT pipeline.
 * Binaries are loaded from ../../tests/hp_i3/ relative to the translator
 * working directory.  Tests SKIP (not FAIL) if the directory or a specific
 * .sys file is missing.
 *
 * Drivers tested:
 *   ACPI.sys      -- ACPI driver (multi-section, >= 10 HW)
 *   disk.sys      -- Storage class driver (>= 1 HW)
 *   HDAudBus.sys  -- HD Audio bus driver (>= 1 HW, uses MMIO)
 *   i8042prt.sys  -- PS/2 keyboard/mouse (>= 1 HW, uses MMIO)
 *   pci.sys       -- PCI bus driver (>= 1 HW)
 *   serial.sys    -- Serial port driver (>= 20 HW, direct port I/O)
 *   storport.sys  -- Storage port minidriver (>= 20 HW)
 *   usbxhci.sys   -- USB 3.0 xHCI driver (>= 5 HW)
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <sys/stat.h>

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
 * SKIP handling -- missing drivers are expected on machines without hp_i3/
 * ============================================================================ */

static void skip_test(const char* name, const char* reason) {
    tests_run++;
    tests_passed++;
    printf("  TEST: %-50s SKIP: %s\n", name, reason);
}

/* ============================================================================
 * Check whether the hp_i3 directory exists at all
 * ============================================================================ */

#define HP_DRIVER_DIR "../../tests/hp_i3"

static bool hp_dir_exists(void) {
    struct stat st;
    return (stat(HP_DRIVER_DIR, &st) == 0 && S_ISDIR(st.st_mode));
}

/* ============================================================================
 * Driver loader -- read raw .sys file from hp_i3/
 * ============================================================================ */

static bool load_hp_driver(const char* filename,
                           uint8_t** out_data, size_t* out_size)
{
    char path[512];
    snprintf(path, sizeof(path), "%s/%s", HP_DRIVER_DIR, filename);

    FILE* f = fopen(path, "rb");
    if (!f) return false;

    fseek(f, 0, SEEK_END);
    long len = ftell(f);
    if (len <= 0) { fclose(f); return false; }
    fseek(f, 0, SEEK_SET);

    uint8_t* buf = malloc((size_t)len);
    if (!buf) { fclose(f); return false; }

    size_t n = fread(buf, 1, (size_t)len, f);
    fclose(f);

    if (n != (size_t)len) { free(buf); return false; }

    *out_data = buf;
    *out_size = (size_t)len;
    return true;
}

/* ============================================================================
 * Pipeline runner -- translate_buffer with TARGET_SEMANTIC_REPORT
 * Returns allocated JSON string or NULL on failure.
 * ============================================================================ */

static char* run_pipeline(const uint8_t* data, size_t size,
                          const char* filename)
{
    translate_options_t opts;
    translate_options_init(&opts);
    opts.target = TARGET_SEMANTIC_REPORT;
    opts.input_filename = filename;

    translate_result_t result = translate_buffer(data, size, &opts);
    if (!result.success) {
        translate_result_free(&result);
        return NULL;
    }

    char* output = result.output;
    result.output = NULL;   /* prevent free */
    translate_result_free(&result);
    return output;
}

/* ============================================================================
 * JSON helper -- extract integer from "summary" section
 *
 * Searches within the "summary" object to avoid matching array keys of the
 * same name (e.g. "hardware_functions": [...] vs "hardware_functions": 14).
 * Returns -1 if not found.
 * ============================================================================ */

static int json_get_int(const char* json, const char* section,
                        const char* key)
{
    /* Find the section first */
    char sec_pattern[128];
    snprintf(sec_pattern, sizeof(sec_pattern), "\"%s\"", section);
    const char* search_base = strstr(json, sec_pattern);
    if (!search_base) search_base = json;

    char key_pattern[128];
    snprintf(key_pattern, sizeof(key_pattern), "\"%s\":", key);
    const char* found = strstr(search_base, key_pattern);
    if (!found) return -1;
    found += strlen(key_pattern);
    while (*found == ' ' || *found == '\t') found++;
    return atoi(found);
}

/* ============================================================================
 * Per-driver cached state
 * ============================================================================ */

typedef struct {
    const char* filename;       /* e.g. "disk.sys" */
    const char* short_name;     /* same, used for display */
    uint8_t*    data;
    size_t      size;
    char*       sem_output;
    bool        loaded;
    bool        available;
} driver_state_t;

#define NUM_DRIVERS 8

#define DRV_ACPI      0
#define DRV_DISK      1
#define DRV_HDAUDBUS  2
#define DRV_I8042     3
#define DRV_PCI       4
#define DRV_SERIAL    5
#define DRV_STORPORT  6
#define DRV_USBXHCI   7

static driver_state_t drivers[NUM_DRIVERS];

static bool ensure_driver(int idx) {
    driver_state_t* d = &drivers[idx];
    if (d->loaded) return d->available;
    d->loaded = true;

    if (!hp_dir_exists()) {
        d->available = false;
        return false;
    }

    if (!load_hp_driver(d->filename, &d->data, &d->size)) {
        d->available = false;
        return false;
    }

    d->sem_output = run_pipeline(d->data, d->size, d->filename);
    if (!d->sem_output) {
        d->available = false;
        return false;
    }

    d->available = true;
    return true;
}

static void cleanup_drivers(void) {
    for (int i = 0; i < NUM_DRIVERS; i++) {
        free(drivers[i].data);
        free(drivers[i].sem_output);
    }
}

/* ============================================================================
 * Macro to generate the two tests per driver:
 *   1. <name>_pipeline_succeeds
 *   2. <name>_hw_function_count
 * ============================================================================ */

#define DEFINE_DRIVER_TESTS(label, idx, display, threshold) \
\
static void test_##label##_pipeline_succeeds(void) { \
    if (!drivers[idx].loaded) ensure_driver(idx); \
    if (!drivers[idx].available) { \
        skip_test(#label "_pipeline_succeeds", \
                  display " not found or pipeline failed"); \
        return; \
    } \
    TEST(label##_pipeline_succeeds); \
    if (!drivers[idx].sem_output) \
        FAIL("semantic report is NULL"); \
    if (strlen(drivers[idx].sem_output) == 0) \
        FAIL("semantic report is empty"); \
    PASS(); \
} \
\
static void test_##label##_hw_function_count(void) { \
    if (!drivers[idx].loaded) ensure_driver(idx); \
    if (!drivers[idx].available) { \
        skip_test(#label "_hw_function_count", \
                  display " not found or pipeline failed"); \
        return; \
    } \
    TEST(label##_hw_function_count); \
    int hw = json_get_int(drivers[idx].sem_output, \
                          "summary", "hardware_functions"); \
    if (hw < 0) \
        FAIL("hardware_functions not found in semantic report"); \
    if (hw < (threshold)) { \
        char msg[128]; \
        snprintf(msg, sizeof(msg), \
                 "expected >= %d hw functions, got %d", \
                 (threshold), hw); \
        FAIL(msg); \
    } \
    printf("PASS  [%d hw functions]\n", hw); \
    tests_passed++; \
}

/* ============================================================================
 * Generate tests for each driver
 * ============================================================================ */

DEFINE_DRIVER_TESTS(acpi,      DRV_ACPI,     "ACPI.sys",     10)
DEFINE_DRIVER_TESTS(disk,      DRV_DISK,     "disk.sys",      1)
DEFINE_DRIVER_TESTS(hdaudbus,  DRV_HDAUDBUS, "HDAudBus.sys",  1)
DEFINE_DRIVER_TESTS(i8042prt,  DRV_I8042,    "i8042prt.sys",  1)
DEFINE_DRIVER_TESTS(pci,       DRV_PCI,      "pci.sys",       1)
DEFINE_DRIVER_TESTS(serial,    DRV_SERIAL,   "serial.sys",   20)
DEFINE_DRIVER_TESTS(storport,  DRV_STORPORT, "storport.sys", 20)
DEFINE_DRIVER_TESTS(usbxhci,   DRV_USBXHCI,  "usbxhci.sys",  5)

/* ============================================================================
 * Main
 * ============================================================================ */

int main(void) {
    printf("HP Real Hardware Driver Validation Tests\n");
    printf("=========================================\n");

    if (hp_dir_exists())
        printf("Driver directory: %s (found)\n\n", HP_DRIVER_DIR);
    else
        printf("Driver directory: %s (NOT FOUND -- all tests will SKIP)\n\n",
               HP_DRIVER_DIR);

    /* Initialize driver table */
    drivers[DRV_ACPI] = (driver_state_t){
        .filename = "ACPI.sys",
        .short_name = "ACPI.sys",
    };
    drivers[DRV_DISK] = (driver_state_t){
        .filename = "disk.sys",
        .short_name = "disk.sys",
    };
    drivers[DRV_HDAUDBUS] = (driver_state_t){
        .filename = "HDAudBus.sys",
        .short_name = "HDAudBus.sys",
    };
    drivers[DRV_I8042] = (driver_state_t){
        .filename = "i8042prt.sys",
        .short_name = "i8042prt.sys",
    };
    drivers[DRV_PCI] = (driver_state_t){
        .filename = "pci.sys",
        .short_name = "pci.sys",
    };
    drivers[DRV_SERIAL] = (driver_state_t){
        .filename = "serial.sys",
        .short_name = "serial.sys",
    };
    drivers[DRV_STORPORT] = (driver_state_t){
        .filename = "storport.sys",
        .short_name = "storport.sys",
    };
    drivers[DRV_USBXHCI] = (driver_state_t){
        .filename = "usbxhci.sys",
        .short_name = "usbxhci.sys",
    };

    /* ACPI.sys */
    printf("--- ACPI.sys ---\n");
    test_acpi_pipeline_succeeds();
    test_acpi_hw_function_count();

    /* disk.sys */
    printf("--- disk.sys ---\n");
    test_disk_pipeline_succeeds();
    test_disk_hw_function_count();

    /* HDAudBus.sys */
    printf("--- HDAudBus.sys ---\n");
    test_hdaudbus_pipeline_succeeds();
    test_hdaudbus_hw_function_count();

    /* i8042prt.sys */
    printf("--- i8042prt.sys ---\n");
    test_i8042prt_pipeline_succeeds();
    test_i8042prt_hw_function_count();

    /* pci.sys */
    printf("--- pci.sys ---\n");
    test_pci_pipeline_succeeds();
    test_pci_hw_function_count();

    /* serial.sys */
    printf("--- serial.sys ---\n");
    test_serial_pipeline_succeeds();
    test_serial_hw_function_count();

    /* storport.sys */
    printf("--- storport.sys ---\n");
    test_storport_pipeline_succeeds();
    test_storport_hw_function_count();

    /* usbxhci.sys */
    printf("--- usbxhci.sys ---\n");
    test_usbxhci_pipeline_succeeds();
    test_usbxhci_hw_function_count();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);

    cleanup_drivers();
    return tests_passed == tests_run ? 0 : 1;
}
