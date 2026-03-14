/* ============================================================================
 * CIL Semantic Classifier Tests
 * ============================================================================
 *
 * Tests namespace-prefix classification, payload ratio computation,
 * and threshold-based filtering.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "../include/cil_semantic.h"

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) do { \
    tests_run++; \
    printf("  TEST: %-45s ", #name); \
} while(0)

#define PASS() do { tests_passed++; printf("PASS\n"); } while(0)
#define FAIL(msg) do { printf("FAIL: %s\n", msg); return; } while(0)

/* Helper: build a method with given namespace and instructions */
static cil_method_t make_method(const char* ns, const char* name,
                                 cil_decoded_t* insns, size_t count) {
    cil_method_t m;
    memset(&m, 0, sizeof(m));
    m.type_namespace = ns ? strdup(ns) : NULL;
    m.type_name = name ? strdup(name) : NULL;
    m.name = name ? strdup(name) : NULL;
    m.instructions = insns;
    m.instruction_count = count;
    return m;
}

static void free_method_strings(cil_method_t* m) {
    free(m->type_namespace);
    free(m->type_name);
    free(m->name);
    m->type_namespace = NULL;
    m->type_name = NULL;
    m->name = NULL;
}

/* ---- Tests ---- */

static void test_classify_security_namespace(void) {
    TEST(classify_security_namespace);
    /* Method in System.Security.Permissions → SECURITY */
    cil_decoded_t insns[] = {
        { .opcode = CIL_NOP },
        { .opcode = CIL_RET },
    };
    cil_method_t m = make_method("System.Security.Permissions",
                                  "Demand", insns, 2);
    cil_method_analysis_t a;
    cil_classify_method(&m, NULL, NULL, &a);
    if (a.classification != CIL_CLASS_SECURITY) FAIL("should be SECURITY");
    if (!cil_is_scaffolding(a.classification)) FAIL("should be scaffolding");
    free_method_strings(&m);
    PASS();
}

static void test_classify_payload(void) {
    TEST(classify_payload);
    /* Method in Hardware.Serial namespace with no scaffolding calls → PAYLOAD */
    cil_decoded_t insns[] = {
        { .opcode = CIL_LDC_I4_1 },
        { .opcode = CIL_LDC_I4_2 },
        { .opcode = CIL_ADD },
        { .opcode = CIL_RET },
    };
    cil_method_t m = make_method("Hardware.Serial", "Init", insns, 4);
    cil_method_analysis_t a;
    cil_classify_method(&m, NULL, NULL, &a);
    if (a.classification != CIL_CLASS_PAYLOAD) FAIL("should be PAYLOAD");
    if (a.payload_ratio < 0.99f) FAIL("ratio should be ~1.0");
    if (cil_is_scaffolding(a.classification)) FAIL("should not be scaffolding");
    free_method_strings(&m);
    PASS();
}

/* Resolver that classifies certain tokens as scaffolding */
static const char* test_resolver(uint32_t token, void* userdata) {
    (void)userdata;
    /* Token 0x0A000001 = System.Security.CodeAccessPermission.Demand */
    if (token == 0x0A000001) return "System.Security";
    /* Token 0x0A000002 = System.Security.PermissionSet.Assert */
    if (token == 0x0A000002) return "System.Security";
    return "SomeOther.Namespace";
}

static void test_classify_mixed_payload_ratio(void) {
    TEST(classify_mixed_payload_ratio);
    /* Method with 2 scaffolding calls + 8 arithmetic = 10 total
     * Scaffold calls resolved by test_resolver */
    cil_decoded_t insns[10];
    memset(insns, 0, sizeof(insns));
    /* 8 arithmetic instructions (payload) */
    for (int i = 0; i < 8; i++) {
        insns[i].opcode = CIL_ADD;
        insns[i].operand_type = CIL_OPERAND_NONE;
    }
    /* 2 call instructions to scaffolding */
    insns[8].opcode = CIL_CALL;
    insns[8].operand_type = CIL_OPERAND_TOKEN;
    insns[8].operand.token = 0x0A000001;

    insns[9].opcode = CIL_CALLVIRT;
    insns[9].operand_type = CIL_OPERAND_TOKEN;
    insns[9].operand.token = 0x0A000002;

    cil_method_t m = make_method("MyApp.Core", "Process", insns, 10);
    cil_method_analysis_t a;
    cil_classify_method(&m, test_resolver, NULL, &a);

    if (a.total_insn_count != 10) FAIL("wrong total");
    if (a.scaffold_insn_count != 2) FAIL("wrong scaffold count");
    if (a.payload_insn_count != 8) FAIL("wrong payload count");
    /* ratio = 8/10 = 0.8 */
    if (fabsf(a.payload_ratio - 0.8f) > 0.01f) FAIL("wrong ratio");
    if (a.classification != CIL_CLASS_PAYLOAD) FAIL("should be PAYLOAD (ratio > 0.5)");
    free_method_strings(&m);
    PASS();
}

static void test_classify_empty_method(void) {
    TEST(classify_empty_method);
    cil_method_t m = make_method("MyApp", "Empty", NULL, 0);
    cil_method_analysis_t a;
    cil_classify_method(&m, NULL, NULL, &a);
    if (a.total_insn_count != 0) FAIL("should be 0 total");
    if (a.payload_ratio < 0.99f) FAIL("empty method should have ratio 1.0");
    free_method_strings(&m);
    PASS();
}

static void test_threshold_filter(void) {
    TEST(threshold_filter);
    /* Method with mostly scaffolding calls — ratio < 0.5 */
    cil_decoded_t insns[10];
    memset(insns, 0, sizeof(insns));
    /* 3 payload instructions */
    insns[0].opcode = CIL_LDC_I4_0;
    insns[1].opcode = CIL_LDC_I4_1;
    insns[2].opcode = CIL_ADD;
    /* 7 scaffolding calls */
    for (int i = 3; i < 10; i++) {
        insns[i].opcode = CIL_CALL;
        insns[i].operand_type = CIL_OPERAND_TOKEN;
        insns[i].operand.token = 0x0A000001; /* resolved as scaffolding */
    }

    cil_method_t m = make_method("MyApp.Security", "CheckAll", insns, 10);
    cil_method_analysis_t a;
    cil_classify_method(&m, test_resolver, NULL, &a);

    /* ratio = 3/10 = 0.3 — below default threshold 0.5 */
    if (a.payload_ratio > CIL_DEFAULT_PAYLOAD_THRESHOLD) FAIL("ratio should be < 0.5");
    if (a.classification != CIL_CLASS_SECURITY) FAIL("should be classified as scaffolding");
    free_method_strings(&m);
    PASS();
}

static void test_ldsfld_detection(void) {
    TEST(ldsfld_detection);
    cil_decoded_t insns[] = {
        { .opcode = CIL_LDSFLD, .operand_type = CIL_OPERAND_TOKEN, .operand.token = 0x04000001 },
        { .opcode = CIL_RET },
    };
    cil_method_t m = make_method("SomeLib", "GetField", insns, 2);
    cil_method_analysis_t a;
    cil_classify_method(&m, NULL, NULL, &a);
    if (!a.has_ldsfld) FAIL("should detect ldsfld");
    free_method_strings(&m);
    PASS();
}

/* ---- Main ---- */

int main(void) {
    printf("CIL Semantic Classifier Tests\n");
    printf("=============================\n");

    test_classify_security_namespace();
    test_classify_payload();
    test_classify_mixed_payload_ratio();
    test_classify_empty_method();
    test_threshold_filter();
    test_ldsfld_detection();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);
    return tests_passed == tests_run ? 0 : 1;
}
