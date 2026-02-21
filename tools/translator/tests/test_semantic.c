/* ============================================================================
 * Semantic Analyzer Tests
 * ============================================================================
 *
 * Tests import classification and function analysis.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../include/semantic.h"

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) do { \
    tests_run++; \
    printf("  TEST: %-50s ", #name); \
} while(0)

#define PASS() do { tests_passed++; printf("PASS\n"); } while(0)
#define FAIL(msg) do { printf("FAIL: %s\n", msg); return; } while(0)

/* ---- Test: classify hardware API ---- */
static void test_classify_port_io(void) {
    TEST(classify_port_io);
    const char* forth;
    sem_category_t cat = sem_classify_import("READ_PORT_UCHAR", &forth);
    if (cat != SEM_CAT_PORT_IO) FAIL("expected SEM_CAT_PORT_IO");
    if (!forth || strcmp(forth, "C@-PORT") != 0) FAIL("forth equiv should be C@-PORT");
    PASS();
}

static void test_classify_write_port(void) {
    TEST(classify_write_port);
    const char* forth;
    sem_category_t cat = sem_classify_import("WRITE_PORT_UCHAR", &forth);
    if (cat != SEM_CAT_PORT_IO) FAIL("expected SEM_CAT_PORT_IO");
    if (!forth || strcmp(forth, "C!-PORT") != 0) FAIL("forth equiv should be C!-PORT");
    PASS();
}

static void test_classify_mmio(void) {
    TEST(classify_mmio);
    const char* forth;
    sem_category_t cat = sem_classify_import("MmMapIoSpace", &forth);
    if (cat != SEM_CAT_MMIO) FAIL("expected SEM_CAT_MMIO");
    PASS();
}

static void test_classify_timing(void) {
    TEST(classify_timing);
    const char* forth;
    sem_category_t cat = sem_classify_import("KeStallExecutionProcessor", &forth);
    if (cat != SEM_CAT_TIMING) FAIL("expected SEM_CAT_TIMING");
    if (!forth || strcmp(forth, "US-DELAY") != 0) FAIL("forth equiv should be US-DELAY");
    PASS();
}

/* ---- Test: classify scaffolding APIs ---- */
static void test_classify_irp(void) {
    TEST(classify_irp_scaffolding);
    const char* forth;
    sem_category_t cat = sem_classify_import("IoCompleteRequest", &forth);
    if (cat != SEM_CAT_IRP) FAIL("expected SEM_CAT_IRP");
    if (forth != NULL) FAIL("scaffolding should have NULL forth equiv");
    PASS();
}

static void test_classify_pnp(void) {
    TEST(classify_pnp_scaffolding);
    const char* forth;
    sem_category_t cat = sem_classify_import("IoRegisterDeviceInterface", &forth);
    if (cat != SEM_CAT_PNP) FAIL("expected SEM_CAT_PNP");
    PASS();
}

static void test_classify_unknown(void) {
    TEST(classify_unknown_api);
    const char* forth;
    sem_category_t cat = sem_classify_import("SomeRandomFunction", &forth);
    if (cat != SEM_CAT_UNKNOWN) FAIL("expected SEM_CAT_UNKNOWN");
    if (forth != NULL) FAIL("unknown should have NULL forth equiv");
    PASS();
}

/* ---- Test: sem_is_hardware / sem_is_scaffolding ---- */
static void test_category_checks(void) {
    TEST(category_classification_helpers);
    if (!sem_is_hardware(SEM_CAT_PORT_IO)) FAIL("PORT_IO should be hardware");
    if (!sem_is_hardware(SEM_CAT_MMIO)) FAIL("MMIO should be hardware");
    if (!sem_is_hardware(SEM_CAT_TIMING)) FAIL("TIMING should be hardware");
    if (sem_is_hardware(SEM_CAT_IRP)) FAIL("IRP should NOT be hardware");
    if (!sem_is_scaffolding(SEM_CAT_IRP)) FAIL("IRP should be scaffolding");
    if (!sem_is_scaffolding(SEM_CAT_PNP)) FAIL("PNP should be scaffolding");
    if (sem_is_scaffolding(SEM_CAT_PORT_IO)) FAIL("PORT_IO should NOT be scaffolding");
    PASS();
}

/* ---- Test: classify a batch of imports ---- */
static void test_classify_imports_batch(void) {
    TEST(classify_imports_batch);

    sem_pe_import_t pe_imports[] = {
        {"hal.dll", "READ_PORT_UCHAR", 0x2000},
        {"ntoskrnl.exe", "IoCompleteRequest", 0x2004},
        {"hal.dll", "WRITE_PORT_UCHAR", 0x2008},
        {"ntoskrnl.exe", "KeStallExecutionProcessor", 0x200C},
    };

    sem_result_t result;
    memset(&result, 0, sizeof(result));

    int rc = sem_classify_imports(pe_imports, 4, &result);
    if (rc != 0) FAIL("sem_classify_imports returned error");
    if (result.import_count != 4) FAIL("should have 4 classified imports");

    /* Check categories */
    if (result.imports[0].category != SEM_CAT_PORT_IO) FAIL("import 0 should be PORT_IO");
    if (result.imports[1].category != SEM_CAT_IRP) FAIL("import 1 should be IRP");
    if (result.imports[2].category != SEM_CAT_PORT_IO) FAIL("import 2 should be PORT_IO");
    if (result.imports[3].category != SEM_CAT_TIMING) FAIL("import 3 should be TIMING");

    sem_cleanup(&result);
    PASS();
}

/* ---- Test: analyze functions ---- */
static void test_analyze_hw_function(void) {
    TEST(analyze_hw_function);

    /* Set up classified imports first */
    sem_result_t result;
    memset(&result, 0, sizeof(result));

    sem_pe_import_t pe_imports[] = {
        {"hal.dll", "READ_PORT_UCHAR", 0x2000},
        {"ntoskrnl.exe", "IoCompleteRequest", 0x2004},
    };
    sem_classify_imports(pe_imports, 2, &result);

    /* Simulate two UIR functions:
     * func1: has port I/O → hardware
     * func2: no port I/O → not hardware */
    uint16_t ports[] = {0x60, 0x64};
    sem_uir_input_t funcs[] = {
        {
            .func = NULL,
            .entry_address = 0x1000,
            .name = "hw_init",
            .has_port_io = true,
            .ports_read = ports,
            .ports_read_count = 2,
            .ports_written = NULL,
            .ports_written_count = 0,
        },
        {
            .func = NULL,
            .entry_address = 0x2000,
            .name = "irp_handler",
            .has_port_io = false,
            .ports_read = NULL,
            .ports_read_count = 0,
            .ports_written = NULL,
            .ports_written_count = 0,
        },
    };

    int rc = sem_analyze_functions(funcs, 2, &result);
    if (rc != 0) FAIL("sem_analyze_functions returned error");
    if (result.function_count != 2) FAIL("should have 2 functions");

    /* Function with port I/O should be hardware-relevant */
    if (!result.functions[0].is_hardware) FAIL("func1 should be hardware");
    if (!result.functions[0].has_port_io) FAIL("func1 should have port_io");
    if (result.functions[0].port_count != 2) FAIL("func1 should have 2 ports");

    /* Function without port I/O should not be hardware */
    if (result.functions[1].is_hardware) FAIL("func2 should NOT be hardware");

    /* Summary counts */
    if (result.hw_function_count != 1) FAIL("should have 1 hw function");
    if (result.filtered_count != 1) FAIL("should have 1 filtered function");

    sem_cleanup(&result);
    PASS();
}

/* ---- Test: PCI config is hardware ---- */
static void test_classify_pci(void) {
    TEST(classify_pci_config);
    const char* forth;
    sem_category_t cat = sem_classify_import("HalGetBusData", &forth);
    if (cat != SEM_CAT_PCI_CONFIG) FAIL("expected SEM_CAT_PCI_CONFIG");
    if (!forth || strcmp(forth, "PCI-READ") != 0) FAIL("forth equiv should be PCI-READ");
    PASS();
}

/* ---- Test: DMA is hardware ---- */
static void test_classify_dma(void) {
    TEST(classify_dma);
    const char* forth;
    sem_category_t cat = sem_classify_import("MmGetPhysicalAddress", &forth);
    if (cat != SEM_CAT_DMA) FAIL("expected SEM_CAT_DMA");
    PASS();
}

/* ---- Test: sync is scaffolding ---- */
static void test_classify_sync(void) {
    TEST(classify_sync_scaffolding);
    const char* forth;
    sem_category_t cat = sem_classify_import("KeAcquireSpinLock", &forth);
    if (cat != SEM_CAT_SYNC) FAIL("expected SEM_CAT_SYNC");
    if (forth != NULL) FAIL("scaffolding should have NULL forth equiv");
    PASS();
}

int main(void) {
    printf("Semantic Analyzer Tests\n");
    printf("=======================\n");

    test_classify_port_io();
    test_classify_write_port();
    test_classify_mmio();
    test_classify_timing();
    test_classify_irp();
    test_classify_pnp();
    test_classify_unknown();
    test_category_checks();
    test_classify_imports_batch();
    test_analyze_hw_function();
    test_classify_pci();
    test_classify_dma();
    test_classify_sync();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);
    return tests_passed == tests_run ? 0 : 1;
}
