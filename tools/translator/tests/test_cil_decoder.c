/* ============================================================================
 * CIL Decoder Tests
 * ============================================================================
 *
 * Tests CIL/MSIL instruction decoding: single-byte opcodes, extended opcodes,
 * operand parsing, method headers (tiny/fat), and switch tables.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../include/cil_decoder.h"

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) do { \
    tests_run++; \
    printf("  TEST: %-45s ", #name); \
} while(0)

#define PASS() do { tests_passed++; printf("PASS\n"); } while(0)
#define FAIL(msg) do { printf("FAIL: %s\n", msg); return; } while(0)

/* ---- Opcode decoding tests ---- */

static void test_decode_nop(void) {
    TEST(decode_nop);
    uint8_t code[] = { 0x00 };
    cil_decoder_t dec;
    cil_decoder_init(&dec, code, sizeof(code));
    cil_decoded_t d;
    int n = cil_decode_one(&dec, &d);
    if (n != 1) FAIL("wrong length");
    if (d.opcode != CIL_NOP) FAIL("wrong opcode");
    if (d.operand_type != CIL_OPERAND_NONE) FAIL("should have no operand");
    if (d.length != 1) FAIL("wrong stored length");
    PASS();
}

static void test_decode_ret(void) {
    TEST(decode_ret);
    uint8_t code[] = { 0x2A };
    cil_decoder_t dec;
    cil_decoder_init(&dec, code, sizeof(code));
    cil_decoded_t d;
    int n = cil_decode_one(&dec, &d);
    if (n != 1) FAIL("wrong length");
    if (d.opcode != CIL_RET) FAIL("wrong opcode");
    PASS();
}

static void test_decode_ldloc_0(void) {
    TEST(decode_ldloc_0);
    uint8_t code[] = { 0x06 };
    cil_decoder_t dec;
    cil_decoder_init(&dec, code, sizeof(code));
    cil_decoded_t d;
    int n = cil_decode_one(&dec, &d);
    if (n != 1) FAIL("wrong length");
    if (d.opcode != CIL_LDLOC_0) FAIL("wrong opcode");
    if (d.operand_type != CIL_OPERAND_NONE) FAIL("should have no operand");
    PASS();
}

static void test_decode_ldc_i4_s(void) {
    TEST(decode_ldc_i4_s);
    uint8_t code[] = { 0x1F, 0x2A };  /* ldc.i4.s 42 */
    cil_decoder_t dec;
    cil_decoder_init(&dec, code, sizeof(code));
    cil_decoded_t d;
    int n = cil_decode_one(&dec, &d);
    if (n != 2) FAIL("wrong length");
    if (d.opcode != CIL_LDC_I4_S) FAIL("wrong opcode");
    if (d.operand_type != CIL_OPERAND_INT8) FAIL("wrong operand type");
    if (d.operand.i8 != 42) FAIL("wrong operand value");
    PASS();
}

static void test_decode_ldc_i4(void) {
    TEST(decode_ldc_i4);
    uint8_t code[] = { 0x20, 0x78, 0x56, 0x34, 0x12 };  /* ldc.i4 0x12345678 */
    cil_decoder_t dec;
    cil_decoder_init(&dec, code, sizeof(code));
    cil_decoded_t d;
    int n = cil_decode_one(&dec, &d);
    if (n != 5) FAIL("wrong length");
    if (d.opcode != CIL_LDC_I4) FAIL("wrong opcode");
    if (d.operand_type != CIL_OPERAND_INT32) FAIL("wrong operand type");
    if (d.operand.i32 != 0x12345678) FAIL("wrong operand value");
    PASS();
}

static void test_decode_call(void) {
    TEST(decode_call);
    /* call MethodRef token 0x0A000006 */
    uint8_t code[] = { 0x28, 0x06, 0x00, 0x00, 0x0A };
    cil_decoder_t dec;
    cil_decoder_init(&dec, code, sizeof(code));
    cil_decoded_t d;
    int n = cil_decode_one(&dec, &d);
    if (n != 5) FAIL("wrong length");
    if (d.opcode != CIL_CALL) FAIL("wrong opcode");
    if (d.operand_type != CIL_OPERAND_TOKEN) FAIL("wrong operand type");
    if (d.operand.token != 0x0A000006) FAIL("wrong token value");
    PASS();
}

static void test_decode_br_s(void) {
    TEST(decode_br_s);
    uint8_t code[] = { 0x2B, 0x05 };  /* br.s +5 */
    cil_decoder_t dec;
    cil_decoder_init(&dec, code, sizeof(code));
    cil_decoded_t d;
    int n = cil_decode_one(&dec, &d);
    if (n != 2) FAIL("wrong length");
    if (d.opcode != CIL_BR_S) FAIL("wrong opcode");
    if (d.operand_type != CIL_OPERAND_BRANCH8) FAIL("wrong operand type");
    if (d.operand.branch != 5) FAIL("wrong branch offset");
    PASS();
}

static void test_decode_ceq(void) {
    TEST(decode_ceq_extended);
    uint8_t code[] = { 0xFE, 0x01 };  /* ceq */
    cil_decoder_t dec;
    cil_decoder_init(&dec, code, sizeof(code));
    cil_decoded_t d;
    int n = cil_decode_one(&dec, &d);
    if (n != 2) FAIL("wrong length");
    if (d.opcode != CIL_CEQ) FAIL("wrong opcode");
    if (d.operand_type != CIL_OPERAND_NONE) FAIL("should have no operand");
    PASS();
}

static void test_decode_switch(void) {
    TEST(decode_switch);
    /* switch (2 targets: +4, +8) */
    uint8_t code[] = {
        0x45,                           /* switch */
        0x02, 0x00, 0x00, 0x00,        /* count = 2 */
        0x04, 0x00, 0x00, 0x00,        /* target[0] = +4 */
        0x08, 0x00, 0x00, 0x00,        /* target[1] = +8 */
    };
    cil_decoder_t dec;
    cil_decoder_init(&dec, code, sizeof(code));
    cil_decoded_t d;
    int n = cil_decode_one(&dec, &d);
    if (n != 13) FAIL("wrong length");
    if (d.opcode != CIL_SWITCH) FAIL("wrong opcode");
    if (d.switch_count != 2) FAIL("wrong switch count");
    if (!d.switch_targets) FAIL("null switch targets");
    if (d.switch_targets[0] != 4) FAIL("wrong target[0]");
    if (d.switch_targets[1] != 8) FAIL("wrong target[1]");
    cil_free_decoded(&d);
    PASS();
}

static void test_decode_unknown(void) {
    TEST(decode_unknown);
    uint8_t code[] = { 0xFF };
    cil_decoder_t dec;
    cil_decoder_init(&dec, code, sizeof(code));
    cil_decoded_t d;
    int n = cil_decode_one(&dec, &d);
    if (n != -1) FAIL("should return -1 for unknown opcode");
    if (d.opcode != CIL_UNKNOWN) FAIL("should be CIL_UNKNOWN");
    PASS();
}

/* ---- Method header tests ---- */

static void test_tiny_method_header(void) {
    TEST(tiny_method_header);
    /* Tiny header: code_size = 3, format bits = 0x02 → byte = (3<<2)|0x02 = 0x0E */
    uint8_t code[] = { 0x0E, 0x00, 0x00, 0x2A };  /* nop, nop, ret */
    cil_method_t m;
    int rc = cil_decode_method(code, sizeof(code), &m);
    if (rc != 0) FAIL("decode_method failed");
    if (m.code_size != 3) FAIL("wrong code_size");
    if (m.instruction_count != 3) FAIL("wrong instruction count");
    if (m.instructions[0].opcode != CIL_NOP) FAIL("insn[0] not NOP");
    if (m.instructions[1].opcode != CIL_NOP) FAIL("insn[1] not NOP");
    if (m.instructions[2].opcode != CIL_RET) FAIL("insn[2] not RET");
    cil_free_method(&m);
    PASS();
}

static void test_fat_method_header(void) {
    TEST(fat_method_header);
    /* Fat header: 12 bytes
     * Byte 0-1: flags=0x3003 (fat format, init_locals)
     *   low 12 bits = 0x003 (fat format flag)
     *   high 4 bits = 3 (header size = 3 dwords = 12 bytes)
     *   Actually: flags_and_size = (3 << 12) | 0x0013 = 0x3013
     */
    uint8_t code[16];
    memset(code, 0, sizeof(code));
    /* flags(2): low nibble = 0x3 (fat), bit 4 = initlocals; high nibble=3 (size) */
    code[0] = 0x13; /* 0x0013 low byte: fat(0x03) | init_locals(0x10) */
    code[1] = 0x30; /* high byte: header_size=3 in top nibble */
    /* max_stack(2) */
    code[2] = 0x08; code[3] = 0x00; /* max_stack = 8 */
    /* code_size(4) */
    code[4] = 0x02; code[5] = 0x00; code[6] = 0x00; code[7] = 0x00; /* code_size = 2 */
    /* local_var_sig_token(4) */
    code[8] = 0x00; code[9] = 0x00; code[10] = 0x00; code[11] = 0x00;
    /* CIL code: nop, ret */
    code[12] = 0x00; /* nop */
    code[13] = 0x2A; /* ret */

    cil_method_t m;
    int rc = cil_decode_method(code, sizeof(code), &m);
    if (rc != 0) FAIL("decode_method failed");
    if (m.code_size != 2) FAIL("wrong code_size");
    if (m.max_stack != 8) FAIL("wrong max_stack");
    if (m.instruction_count != 2) FAIL("wrong instruction count");
    if (m.instructions[0].opcode != CIL_NOP) FAIL("insn[0] not NOP");
    if (m.instructions[1].opcode != CIL_RET) FAIL("insn[1] not RET");
    cil_free_method(&m);
    PASS();
}

/* ---- Opcode name test ---- */

static void test_opcode_names(void) {
    TEST(opcode_names);
    if (strcmp(cil_opcode_name(CIL_NOP), "nop") != 0) FAIL("NOP name wrong");
    if (strcmp(cil_opcode_name(CIL_RET), "ret") != 0) FAIL("RET name wrong");
    if (strcmp(cil_opcode_name(CIL_ADD), "add") != 0) FAIL("ADD name wrong");
    if (strcmp(cil_opcode_name(CIL_CEQ), "ceq") != 0) FAIL("CEQ name wrong");
    if (strcmp(cil_opcode_name(CIL_UNKNOWN), "UNKNOWN") != 0) FAIL("UNKNOWN name wrong");
    PASS();
}

/* ---- Multi-instruction sequence test ---- */

static void test_instruction_sequence(void) {
    TEST(instruction_sequence);
    /* ldc.i4.1, ldc.i4.2, add, ret */
    uint8_t code[] = { 0x17, 0x18, 0x58, 0x2A };
    cil_decoder_t dec;
    cil_decoder_init(&dec, code, sizeof(code));
    cil_decoded_t d;

    if (cil_decode_one(&dec, &d) != 1 || d.opcode != CIL_LDC_I4_1) FAIL("insn 0");
    if (cil_decode_one(&dec, &d) != 1 || d.opcode != CIL_LDC_I4_2) FAIL("insn 1");
    if (cil_decode_one(&dec, &d) != 1 || d.opcode != CIL_ADD)      FAIL("insn 2");
    if (cil_decode_one(&dec, &d) != 1 || d.opcode != CIL_RET)      FAIL("insn 3");
    if (cil_decode_one(&dec, &d) != 0) FAIL("should return 0 at end");
    PASS();
}

/* ---- Main ---- */

int main(void) {
    printf("CIL Decoder Tests\n");
    printf("=================\n");

    test_decode_nop();
    test_decode_ret();
    test_decode_ldloc_0();
    test_decode_ldc_i4_s();
    test_decode_ldc_i4();
    test_decode_call();
    test_decode_br_s();
    test_decode_ceq();
    test_decode_switch();
    test_decode_unknown();
    test_tiny_method_header();
    test_fat_method_header();
    test_opcode_names();
    test_instruction_sequence();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);
    return tests_passed == tests_run ? 0 : 1;
}
