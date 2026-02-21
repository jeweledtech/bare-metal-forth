/* ============================================================================
 * x86 Decoder Tests
 * ============================================================================
 *
 * Tests basic x86 instruction decoding: one-byte opcodes, ModR/M, SIB,
 * two-byte opcodes, and I/O instructions critical for driver extraction.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../include/x86_decoder.h"

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) do { \
    tests_run++; \
    printf("  TEST: %-45s ", #name); \
} while(0)

#define PASS() do { tests_passed++; printf("PASS\n"); } while(0)
#define FAIL(msg) do { printf("FAIL: %s\n", msg); return; } while(0)

/* Helper: decode a single instruction from a byte array */
static int decode_one(const uint8_t* code, size_t len, x86_decoded_t* out) {
    x86_decoder_t dec;
    x86_decoder_init(&dec, X86_MODE_32, code, len, 0x1000);
    return x86_decode_one(&dec, out);
}

/* ---- Simple one-byte opcodes ---- */

static void test_nop(void) {
    TEST(NOP);
    uint8_t code[] = { 0x90 };
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 1) FAIL("wrong length");
    if (d.instruction != X86_INS_NOP) FAIL("wrong instruction");
    if (d.operand_count != 0) FAIL("should have 0 operands");
    PASS();
}

static void test_ret(void) {
    TEST(RET);
    uint8_t code[] = { 0xC3 };
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 1) FAIL("wrong length");
    if (d.instruction != X86_INS_RET) FAIL("wrong instruction");
    PASS();
}

static void test_push_reg(void) {
    TEST(PUSH_EAX);
    uint8_t code[] = { 0x50 };  /* PUSH EAX */
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 1) FAIL("wrong length");
    if (d.instruction != X86_INS_PUSH) FAIL("wrong instruction");
    if (d.operand_count != 1) FAIL("should have 1 operand");
    if (d.operands[0].type != X86_OP_REG) FAIL("operand should be REG");
    if (d.operands[0].reg != X86_REG_EAX) FAIL("should be EAX");
    PASS();
}

static void test_pop_reg(void) {
    TEST(POP_EBX);
    uint8_t code[] = { 0x5B };  /* POP EBX */
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 1) FAIL("wrong length");
    if (d.instruction != X86_INS_POP) FAIL("wrong instruction");
    if (d.operands[0].reg != X86_REG_EBX) FAIL("should be EBX");
    PASS();
}

/* ---- MOV with immediates ---- */

static void test_mov_reg_imm32(void) {
    TEST(MOV_EAX_imm32);
    uint8_t code[] = { 0xB8, 0x78, 0x56, 0x34, 0x12 };  /* MOV EAX, 0x12345678 */
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 5) FAIL("wrong length");
    if (d.instruction != X86_INS_MOV) FAIL("wrong instruction");
    if (d.operands[0].type != X86_OP_REG) FAIL("dst should be REG");
    if (d.operands[0].reg != X86_REG_EAX) FAIL("dst should be EAX");
    if (d.operands[1].type != X86_OP_IMM) FAIL("src should be IMM");
    if (d.operands[1].imm != 0x12345678) FAIL("wrong immediate value");
    PASS();
}

static void test_mov_reg8_imm8(void) {
    TEST(MOV_AL_imm8);
    uint8_t code[] = { 0xB0, 0x42 };  /* MOV AL, 0x42 */
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 2) FAIL("wrong length");
    if (d.instruction != X86_INS_MOV) FAIL("wrong instruction");
    if (d.operands[0].size != 1) FAIL("should be 8-bit");
    if (d.operands[1].imm != 0x42) FAIL("wrong immediate");
    PASS();
}

/* ---- I/O instructions (critical for driver extraction) ---- */

static void test_in_al_imm8(void) {
    TEST(IN_AL_imm8);
    uint8_t code[] = { 0xE4, 0x60 };  /* IN AL, 0x60 */
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 2) FAIL("wrong length");
    if (d.instruction != X86_INS_IN) FAIL("wrong instruction");
    if (d.operands[0].type != X86_OP_REG) FAIL("dst should be REG");
    if (d.operands[0].size != 1) FAIL("should be 8-bit");
    if (d.operands[1].type != X86_OP_IMM) FAIL("src should be IMM");
    if (d.operands[1].imm != 0x60) FAIL("wrong port number");
    PASS();
}

static void test_out_imm8_al(void) {
    TEST(OUT_imm8_AL);
    uint8_t code[] = { 0xE6, 0x60 };  /* OUT 0x60, AL */
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 2) FAIL("wrong length");
    if (d.instruction != X86_INS_OUT) FAIL("wrong instruction");
    if (d.operands[0].type != X86_OP_IMM) FAIL("dst should be IMM (port)");
    if (d.operands[0].imm != 0x60) FAIL("wrong port number");
    if (d.operands[1].type != X86_OP_REG) FAIL("src should be REG");
    PASS();
}

static void test_in_eax_dx(void) {
    TEST(IN_EAX_DX);
    uint8_t code[] = { 0xED };  /* IN EAX, DX */
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 1) FAIL("wrong length");
    if (d.instruction != X86_INS_IN) FAIL("wrong instruction");
    if (d.operands[0].size != 4) FAIL("should be 32-bit");
    if (d.operands[1].type != X86_OP_REG) FAIL("src should be REG (DX)");
    if (d.operands[1].reg != X86_REG_EDX) FAIL("should be DX");
    PASS();
}

static void test_out_dx_al(void) {
    TEST(OUT_DX_AL);
    uint8_t code[] = { 0xEE };  /* OUT DX, AL */
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 1) FAIL("wrong length");
    if (d.instruction != X86_INS_OUT) FAIL("wrong instruction");
    if (d.operands[0].type != X86_OP_REG) FAIL("dst should be REG (DX)");
    if (d.operands[1].size != 1) FAIL("should be 8-bit");
    PASS();
}

/* ---- Control flow ---- */

static void test_call_rel32(void) {
    TEST(CALL_rel32);
    uint8_t code[] = { 0xE8, 0x10, 0x00, 0x00, 0x00 };  /* CALL +0x10 */
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 5) FAIL("wrong length");
    if (d.instruction != X86_INS_CALL) FAIL("wrong instruction");
    if (d.operands[0].type != X86_OP_REL) FAIL("should be REL operand");
    /* Target = address + length + offset = 0x1000 + 5 + 0x10 = 0x1015 */
    if (d.operands[0].imm != 0x1015) FAIL("wrong target address");
    PASS();
}

static void test_jmp_short(void) {
    TEST(JMP_short);
    uint8_t code[] = { 0xEB, 0x10 };  /* JMP short +0x10 */
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 2) FAIL("wrong length");
    if (d.instruction != X86_INS_JMP) FAIL("wrong instruction");
    /* Target = 0x1000 + 2 + 0x10 = 0x1012 */
    if (d.operands[0].imm != 0x1012) FAIL("wrong target");
    PASS();
}

static void test_jmp_rel32(void) {
    TEST(JMP_rel32);
    uint8_t code[] = { 0xE9, 0x00, 0x01, 0x00, 0x00 };  /* JMP +0x100 */
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 5) FAIL("wrong length");
    if (d.instruction != X86_INS_JMP) FAIL("wrong instruction");
    /* Target = 0x1000 + 5 + 0x100 = 0x1105 */
    if (d.operands[0].imm != 0x1105) FAIL("wrong target");
    PASS();
}

static void test_jcc_short(void) {
    TEST(JE_short);
    uint8_t code[] = { 0x74, 0x08 };  /* JE short +8 */
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 2) FAIL("wrong length");
    if (d.instruction != X86_INS_JCC) FAIL("wrong instruction");
    if (d.cc != X86_CC_E) FAIL("wrong condition code");
    /* Target = 0x1000 + 2 + 8 = 0x100A */
    if (d.operands[0].imm != 0x100A) FAIL("wrong target");
    PASS();
}

/* ---- ModR/M addressing ---- */

static void test_mov_mem_reg(void) {
    TEST(MOV_mem_EAX_to_EBX);
    /* MOV [EBX], EAX  → 89 03  (ModR/M: mod=00 reg=000 rm=011) */
    uint8_t code[] = { 0x89, 0x03 };
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 2) FAIL("wrong length");
    if (d.instruction != X86_INS_MOV) FAIL("wrong instruction");
    if (d.operands[0].type != X86_OP_MEM) FAIL("dst should be MEM");
    if (d.operands[0].base != X86_REG_EBX) FAIL("base should be EBX");
    if (d.operands[1].type != X86_OP_REG) FAIL("src should be REG");
    if (d.operands[1].reg != X86_REG_EAX) FAIL("src should be EAX");
    PASS();
}

static void test_mov_reg_mem_disp8(void) {
    TEST(MOV_EAX_from_EBP_plus_8);
    /* MOV EAX, [EBP+8]  → 8B 45 08  (ModR/M: mod=01 reg=000 rm=101) */
    uint8_t code[] = { 0x8B, 0x45, 0x08 };
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 3) FAIL("wrong length");
    if (d.instruction != X86_INS_MOV) FAIL("wrong instruction");
    if (d.operands[0].type != X86_OP_REG) FAIL("dst should be REG");
    if (d.operands[0].reg != X86_REG_EAX) FAIL("dst should be EAX");
    if (d.operands[1].type != X86_OP_MEM) FAIL("src should be MEM");
    if (d.operands[1].base != X86_REG_EBP) FAIL("base should be EBP");
    if (d.operands[1].disp != 8) FAIL("disp should be 8");
    PASS();
}

static void test_mov_reg_mem_disp32(void) {
    TEST(MOV_ECX_from_EDI_plus_0x100);
    /* MOV ECX, [EDI+0x100]  → 8B 8F 00 01 00 00 */
    uint8_t code[] = { 0x8B, 0x8F, 0x00, 0x01, 0x00, 0x00 };
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 6) FAIL("wrong length");
    if (d.operands[0].reg != X86_REG_ECX) FAIL("dst should be ECX");
    if (d.operands[1].base != X86_REG_EDI) FAIL("base should be EDI");
    if (d.operands[1].disp != 0x100) FAIL("disp should be 0x100");
    PASS();
}

/* ---- Two-byte opcodes ---- */

static void test_movzx(void) {
    TEST(MOVZX_EAX_byte_ptr_ECX);
    /* MOVZX EAX, BYTE PTR [ECX]  → 0F B6 01 */
    uint8_t code[] = { 0x0F, 0xB6, 0x01 };
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 3) FAIL("wrong length");
    if (d.instruction != X86_INS_MOVZX) FAIL("wrong instruction");
    if (d.operands[0].type != X86_OP_REG) FAIL("dst should be REG");
    if (d.operands[0].reg != X86_REG_EAX) FAIL("dst should be EAX");
    if (d.operands[1].type != X86_OP_MEM) FAIL("src should be MEM");
    if (d.operands[1].size != 1) FAIL("src should be byte");
    PASS();
}

static void test_jcc_near(void) {
    TEST(JNE_near);
    /* JNE near +0x100  → 0F 85 00 01 00 00 */
    uint8_t code[] = { 0x0F, 0x85, 0x00, 0x01, 0x00, 0x00 };
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 6) FAIL("wrong length");
    if (d.instruction != X86_INS_JCC) FAIL("wrong instruction");
    if (d.cc != X86_CC_NE) FAIL("wrong condition code");
    /* Target = 0x1000 + 6 + 0x100 = 0x1106 */
    if (d.operands[0].imm != 0x1106) FAIL("wrong target");
    PASS();
}

/* ---- ALU ops via Group 1 ---- */

static void test_add_reg_imm8(void) {
    TEST(ADD_EAX_imm8);
    /* ADD EAX, 4  → 83 C0 04 */
    uint8_t code[] = { 0x83, 0xC0, 0x04 };
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 3) FAIL("wrong length");
    if (d.instruction != X86_INS_ADD) FAIL("wrong instruction");
    if (d.operands[0].reg != X86_REG_EAX) FAIL("dst should be EAX");
    if (d.operands[1].imm != 4) FAIL("imm should be 4");
    PASS();
}

static void test_cmp_reg_imm8(void) {
    TEST(CMP_EAX_imm8);
    /* CMP EAX, 0  → 83 F8 00 */
    uint8_t code[] = { 0x83, 0xF8, 0x00 };
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 3) FAIL("wrong length");
    if (d.instruction != X86_INS_CMP) FAIL("wrong instruction");
    PASS();
}

/* ---- Sequence decode ---- */

static void test_decode_range(void) {
    TEST(decode_range);
    /* Small sequence: PUSH EBP; MOV EBP,ESP; POP EBP; RET */
    uint8_t code[] = { 0x55, 0x89, 0xE5, 0x5D, 0xC3 };
    x86_decoder_t dec;
    x86_decoder_init(&dec, X86_MODE_32, code, sizeof(code), 0x1000);

    size_t count = 0;
    x86_decoded_t* insts = x86_decode_range(&dec, &count);
    if (insts == NULL) FAIL("returned NULL");
    if (count != 4) { printf("FAIL: expected 4, got %zu\n", count); free(insts); return; }
    if (insts[0].instruction != X86_INS_PUSH) FAIL("inst[0] should be PUSH");
    if (insts[1].instruction != X86_INS_MOV) FAIL("inst[1] should be MOV");
    if (insts[2].instruction != X86_INS_POP) FAIL("inst[2] should be POP");
    if (insts[3].instruction != X86_INS_RET) FAIL("inst[3] should be RET");
    free(insts);
    PASS();
}

/* ---- LEA ---- */

static void test_lea(void) {
    TEST(LEA_EAX_EBP_plus_8);
    /* LEA EAX, [EBP+8]  → 8D 45 08 */
    uint8_t code[] = { 0x8D, 0x45, 0x08 };
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 3) FAIL("wrong length");
    if (d.instruction != X86_INS_LEA) FAIL("wrong instruction");
    if (d.operands[0].type != X86_OP_REG) FAIL("dst should be REG");
    if (d.operands[1].type != X86_OP_MEM) FAIL("src should be MEM");
    if (d.operands[1].base != X86_REG_EBP) FAIL("base should be EBP");
    if (d.operands[1].disp != 8) FAIL("disp should be 8");
    PASS();
}

/* ---- SIB byte ---- */

static void test_sib(void) {
    TEST(MOV_EAX_ESI_plus_EDI_x4);
    /* MOV EAX, [ESI+EDI*4]  → 8B 04 BE */
    /* ModR/M: mod=00 reg=000 rm=100 (SIB follows) */
    /* SIB: scale=10 index=111 base=110 → 4*EDI+ESI */
    uint8_t code[] = { 0x8B, 0x04, 0xBE };
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 3) FAIL("wrong length");
    if (d.instruction != X86_INS_MOV) FAIL("wrong instruction");
    if (d.operands[1].type != X86_OP_MEM) FAIL("src should be MEM");
    if (d.operands[1].base != X86_REG_ESI) FAIL("base should be ESI");
    if (d.operands[1].index != X86_REG_EDI) FAIL("index should be EDI");
    if (d.operands[1].scale != 4) FAIL("scale should be 4");
    PASS();
}

/* ---- System instructions ---- */

static void test_cli_sti(void) {
    TEST(CLI_STI);
    uint8_t code_cli[] = { 0xFA };
    uint8_t code_sti[] = { 0xFB };
    x86_decoded_t d;

    decode_one(code_cli, sizeof(code_cli), &d);
    if (d.instruction != X86_INS_CLI) FAIL("should be CLI");

    decode_one(code_sti, sizeof(code_sti), &d);
    if (d.instruction != X86_INS_STI) FAIL("should be STI");
    PASS();
}

static void test_leave(void) {
    TEST(LEAVE);
    uint8_t code[] = { 0xC9 };
    x86_decoded_t d;
    decode_one(code, sizeof(code), &d);
    if (d.instruction != X86_INS_LEAVE) FAIL("should be LEAVE");
    PASS();
}

/* ---- XOR reg,reg (common zero idiom) ---- */

static void test_xor_reg_reg(void) {
    TEST(XOR_EAX_EAX);
    /* XOR EAX, EAX  → 31 C0  (or 33 C0) */
    uint8_t code[] = { 0x31, 0xC0 };
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 2) FAIL("wrong length");
    if (d.instruction != X86_INS_XOR) FAIL("wrong instruction");
    if (d.operands[0].reg != X86_REG_EAX) FAIL("dst should be EAX");
    if (d.operands[1].reg != X86_REG_EAX) FAIL("src should be EAX");
    PASS();
}

/* ---- TEST ---- */

static void test_test_al_imm(void) {
    TEST(TEST_AL_imm8);
    /* TEST AL, 0x20  → A8 20 */
    uint8_t code[] = { 0xA8, 0x20 };
    x86_decoded_t d;
    int n = decode_one(code, sizeof(code), &d);
    if (n != 2) FAIL("wrong length");
    if (d.instruction != X86_INS_TEST) FAIL("wrong instruction");
    PASS();
}

int main(void) {
    printf("x86 Decoder Tests\n");
    printf("=================\n");

    test_nop();
    test_ret();
    test_push_reg();
    test_pop_reg();
    test_mov_reg_imm32();
    test_mov_reg8_imm8();
    test_in_al_imm8();
    test_out_imm8_al();
    test_in_eax_dx();
    test_out_dx_al();
    test_call_rel32();
    test_jmp_short();
    test_jmp_rel32();
    test_jcc_short();
    test_mov_mem_reg();
    test_mov_reg_mem_disp8();
    test_mov_reg_mem_disp32();
    test_movzx();
    test_jcc_near();
    test_add_reg_imm8();
    test_cmp_reg_imm8();
    test_decode_range();
    test_lea();
    test_sib();
    test_cli_sti();
    test_leave();
    test_xor_reg_reg();
    test_test_al_imm();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);
    return tests_passed == tests_run ? 0 : 1;
}
