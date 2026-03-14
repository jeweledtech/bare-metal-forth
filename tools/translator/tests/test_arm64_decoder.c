/* ============================================================================
 * ARM64 Decoder Tests
 * ============================================================================
 *
 * Tests ARM64 fixed-width instruction decoding: data processing, branches,
 * loads/stores, system instructions (MRS/MSR), and barriers.
 *
 * All test instruction words are hand-assembled from the ARMv8-A spec.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../include/arm64_decoder.h"

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) do { \
    tests_run++; \
    printf("  TEST: %-45s ", #name); \
} while(0)

#define PASS() do { tests_passed++; printf("PASS\n"); } while(0)
#define FAIL(msg) do { printf("FAIL: %s\n", msg); return; } while(0)

/* Helper: decode a single 32-bit instruction word */
static a64_decoded_t decode_word(uint32_t word, uint64_t addr) {
    uint8_t buf[4];
    buf[0] = word & 0xFF;
    buf[1] = (word >> 8) & 0xFF;
    buf[2] = (word >> 16) & 0xFF;
    buf[3] = (word >> 24) & 0xFF;
    a64_decoder_t dec;
    a64_decoder_init(&dec, buf, 4, addr);
    a64_decoded_t d;
    a64_decode_one(&dec, &d);
    return d;
}

/* ---- Tests ---- */

static void test_nop(void) {
    TEST(NOP);
    /* NOP = 0xD503201F */
    a64_decoded_t d = decode_word(0xD503201F, 0);
    if (d.instruction != A64_INS_NOP) FAIL("wrong instruction");
    if (d.operand_count != 0) FAIL("should have no operands");
    PASS();
}

static void test_ret(void) {
    TEST(RET);
    /* RET (X30) = 0xD65F03C0 */
    a64_decoded_t d = decode_word(0xD65F03C0, 0);
    if (d.instruction != A64_INS_RET) FAIL("wrong instruction");
    if (d.operands[0].reg != A64_REG_X30) FAIL("should be X30");
    PASS();
}

static void test_add_imm(void) {
    TEST(ADD_X0_X1_42);
    /* ADD X0, X1, #42  → sf=1 op=0 S=0 100010 sh=0 imm12=42 Rn=1 Rd=0
     * = 1 00 10001 0 0 000000101010 00001 00000
     * = 0x91 00 A8 20
     * Let me compute: 1|00|100010|0|000000101010|00001|00000
     * bit31=1, bits30-29=00, bits28-23=100010, bit22=0
     * bits21-10=000000101010=0x02A, bits9-5=00001, bits4-0=00000
     * = 0b1_00_100010_0_000000101010_00001_00000
     * = 0x9100A820 */
    a64_decoded_t d = decode_word(0x9100A820, 0);
    if (d.instruction != A64_INS_ADD) FAIL("wrong instruction");
    if (d.operands[0].reg != A64_REG_X0) FAIL("wrong Rd");
    if (d.operands[1].reg != A64_REG_X1) FAIL("wrong Rn");
    if (d.operands[2].imm != 42) FAIL("wrong immediate");
    if (!d.is_64bit) FAIL("should be 64-bit");
    PASS();
}

static void test_sub_imm(void) {
    TEST(SUB_W0_W1_10);
    /* SUB W0, W1, #10  → sf=0 op=1 S=0 100010 sh=0 imm12=10 Rn=1 Rd=0
     * = 0|10|100010|0|000000001010|00001|00000
     * = 0x51002820 */
    a64_decoded_t d = decode_word(0x51002820, 0);
    if (d.instruction != A64_INS_SUB) FAIL("wrong instruction");
    if (d.operands[2].imm != 10) FAIL("wrong immediate");
    if (d.is_64bit) FAIL("should be 32-bit");
    PASS();
}

static void test_cmp_imm(void) {
    TEST(CMP_X1_0);
    /* CMP X1, #0 = SUBS XZR, X1, #0
     * sf=1 op=1 S=1 100010 sh=0 imm12=0 Rn=1 Rd=31
     * = 1|11|100010|0|000000000000|00001|11111
     * = 0xF100003F */
    a64_decoded_t d = decode_word(0xF100003F, 0);
    if (d.instruction != A64_INS_CMP) FAIL("wrong instruction");
    if (d.operands[0].reg != A64_REG_X1) FAIL("wrong Rn");
    if (d.operands[1].imm != 0) FAIL("wrong immediate");
    if (!d.sets_flags) FAIL("should set flags");
    PASS();
}

static void test_movz(void) {
    TEST(MOVZ_X0_0x1234);
    /* MOVZ X0, #0x1234
     * sf=1 opc=10 100101 hw=00 imm16=0x1234 Rd=0
     * = 1|10|100101|00|0001001000110100|00000
     * = 0xD2824680 */
    a64_decoded_t d = decode_word(0xD2824680, 0);
    if (d.instruction != A64_INS_MOVZ) FAIL("wrong instruction");
    if (d.operands[0].reg != A64_REG_X0) FAIL("wrong Rd");
    if (d.operands[1].imm != 0x1234) FAIL("wrong immediate");
    if (d.operands[1].shift != 0) FAIL("wrong shift");
    PASS();
}

static void test_movk_shifted(void) {
    TEST(MOVK_X0_0x5678_LSL16);
    /* MOVK X0, #0x5678, LSL #16
     * sf=1 opc=11 100101 hw=01 imm16=0x5678 Rd=0
     * = 1|11|100101|01|0101011001111000|00000
     * = 0xF2AACF00 */
    a64_decoded_t d = decode_word(0xF2AACF00, 0);
    if (d.instruction != A64_INS_MOVK) FAIL("wrong instruction");
    if (d.operands[1].imm != 0x5678) FAIL("wrong immediate");
    if (d.operands[1].shift != 16) FAIL("wrong shift");
    PASS();
}

static void test_b_unconditional(void) {
    TEST(B_offset_0x100);
    /* B +0x100 (64 instructions forward)
     * op=0 00101 imm26=64
     * = 0|00101|00000000000000000001000000
     * = 0x14000040 */
    a64_decoded_t d = decode_word(0x14000040, 0x1000);
    if (d.instruction != A64_INS_B) FAIL("wrong instruction");
    /* target = 0x1000 + 64*4 = 0x1000 + 0x100 = 0x1100 */
    if (d.operands[0].imm != 0x1100) FAIL("wrong target");
    PASS();
}

static void test_bl(void) {
    TEST(BL_offset_0x200);
    /* BL +0x200 (128 instructions forward)
     * op=1 00101 imm26=128
     * = 1|00101|00000000000000000010000000
     * = 0x94000080 */
    a64_decoded_t d = decode_word(0x94000080, 0x2000);
    if (d.instruction != A64_INS_BL) FAIL("wrong instruction");
    /* target = 0x2000 + 128*4 = 0x2200 */
    if (d.operands[0].imm != 0x2200) FAIL("wrong target");
    PASS();
}

static void test_b_cond(void) {
    TEST(B_EQ_target);
    /* B.EQ +0x10 (4 instructions forward)
     * 01010100 imm19=4 0 cond=0000
     * = 0|1010100|0000000000000000100|0|0000
     * = 0x54000080 */
    a64_decoded_t d = decode_word(0x54000080, 0x3000);
    if (d.instruction != A64_INS_B_COND) FAIL("wrong instruction");
    if (d.cc != A64_CC_EQ) FAIL("wrong condition");
    /* target = 0x3000 + 4*4 = 0x3010 */
    if (d.operands[0].imm != 0x3010) FAIL("wrong target");
    PASS();
}

static void test_cbz(void) {
    TEST(CBZ_X0_target);
    /* CBZ X0, +0x20 (8 instructions forward)
     * sf=1 0110100 imm19=8 Rt=0
     * = 1|0110100|0000000000000001000|00000
     * = 0xB4000100 */
    a64_decoded_t d = decode_word(0xB4000100, 0x4000);
    if (d.instruction != A64_INS_CBZ) FAIL("wrong instruction");
    if (d.operands[0].reg != A64_REG_X0) FAIL("wrong Rt");
    /* target = 0x4000 + 8*4 = 0x4020 */
    if (d.operands[1].imm != 0x4020) FAIL("wrong target");
    PASS();
}

static void test_ldr_imm(void) {
    TEST(LDR_X0_X1_offset8);
    /* LDR X0, [X1, #8]
     * size=11 111001 opc=01 imm12=1 Rn=1 Rt=0
     * (imm12 is offset/8 for 64-bit = 1)
     * = 11|111001|01|000000000001|00001|00000
     * = 0xF9400420 */
    a64_decoded_t d = decode_word(0xF9400420, 0);
    if (d.instruction != A64_INS_LDR) FAIL("wrong instruction");
    if (d.operands[0].reg != A64_REG_X0) FAIL("wrong Rt");
    if (d.operands[1].reg != A64_REG_X1) FAIL("wrong Rn");
    if (d.operands[1].imm != 8) FAIL("wrong offset");
    if (d.operands[1].type != A64_OP_MEM) FAIL("not memory");
    PASS();
}

static void test_str_imm(void) {
    TEST(STR_W0_X1_offset4);
    /* STR W0, [X1, #4]
     * size=10 111001 opc=00 imm12=1 Rn=1 Rt=0
     * (imm12 is offset/4 for 32-bit = 1)
     * = 10|111001|00|000000000001|00001|00000
     * = 0xB9000420 */
    a64_decoded_t d = decode_word(0xB9000420, 0);
    if (d.instruction != A64_INS_STR) FAIL("wrong instruction");
    if (d.operands[1].imm != 4) FAIL("wrong offset");
    PASS();
}

static void test_mrs(void) {
    TEST(MRS_sysreg);
    /* MRS X0, SCTLR_EL1
     * SCTLR_EL1 = S3_0_C1_C0_0 → op0=3 op1=0 CRn=1 CRm=0 op2=0
     * 1101010100 1 1 op0=11 op1=000 CRn=0001 CRm=0000 op2=000 Rt=00000
     * = 1101010100|1|1|11|000|0001|0000|000|00000
     * = 0xD5381000 */
    a64_decoded_t d = decode_word(0xD5381000, 0);
    if (d.instruction != A64_INS_MRS) FAIL("wrong instruction");
    if (!d.is_sysreg_access) FAIL("should be sysreg access");
    if (d.operands[0].reg != A64_REG_X0) FAIL("wrong Rt");
    if (d.operands[1].type != A64_OP_SYSREG) FAIL("wrong operand type");
    if (d.operands[1].sysreg.op0 != 3) FAIL("wrong op0");
    if (d.operands[1].sysreg.op1 != 0) FAIL("wrong op1");
    if (d.operands[1].sysreg.crn != 1) FAIL("wrong CRn");
    if (d.operands[1].sysreg.crm != 0) FAIL("wrong CRm");
    if (d.operands[1].sysreg.op2 != 0) FAIL("wrong op2");
    PASS();
}

static void test_msr(void) {
    TEST(MSR_sysreg);
    /* MSR SCTLR_EL1, X1
     * Same encoding as MRS but L=0, Rt=1
     * = 1101010100|0|1|11|000|0001|0000|000|00001
     * = 0xD5181001 */
    a64_decoded_t d = decode_word(0xD5181001, 0);
    if (d.instruction != A64_INS_MSR) FAIL("wrong instruction");
    if (!d.is_sysreg_access) FAIL("should be sysreg access");
    if (d.operands[0].type != A64_OP_SYSREG) FAIL("wrong operand 0 type");
    if (d.operands[1].reg != A64_REG_X1) FAIL("wrong Rt");
    PASS();
}

static void test_svc(void) {
    TEST(SVC_0);
    /* SVC #0 = 0xD4000001 */
    a64_decoded_t d = decode_word(0xD4000001, 0);
    if (d.instruction != A64_INS_SVC) FAIL("wrong instruction");
    if (d.operands[0].imm != 0) FAIL("wrong immediate");
    PASS();
}

static void test_add_reg(void) {
    TEST(ADD_X0_X1_X2);
    /* ADD X0, X1, X2 (shifted register, shift=LSL #0)
     * sf=1 op=0 S=0 01011 shift=00 0 Rm=2 imm6=0 Rn=1 Rd=0
     * = 1|0|0|01011|00|0|00010|000000|00001|00000
     * = 0x8B020020 */
    a64_decoded_t d = decode_word(0x8B020020, 0);
    if (d.instruction != A64_INS_ADD) FAIL("wrong instruction");
    if (d.operands[0].reg != A64_REG_X0) FAIL("wrong Rd");
    if (d.operands[1].reg != A64_REG_X1) FAIL("wrong Rn");
    if (d.operands[2].reg != A64_REG_X2) FAIL("wrong Rm");
    PASS();
}

static void test_mov_reg(void) {
    TEST(MOV_X0_X1);
    /* MOV X0, X1 = ORR X0, XZR, X1
     * sf=1 opc=01 01010 shift=00 N=0 Rm=1 imm6=0 Rn=31 Rd=0
     * = 1|01|01010|00|0|00001|000000|11111|00000
     * = 0xAA0103E0 */
    a64_decoded_t d = decode_word(0xAA0103E0, 0);
    if (d.instruction != A64_INS_MOV) FAIL("wrong instruction");
    if (d.operands[0].reg != A64_REG_X0) FAIL("wrong Rd");
    if (d.operands[1].reg != A64_REG_X1) FAIL("wrong Rm");
    if (d.operand_count != 2) FAIL("wrong operand count");
    PASS();
}

static void test_dmb(void) {
    TEST(DMB_ISH);
    /* DMB ISH = 0xD5033BBF
     * 1101010100 0 00 op1=011 CRn=0011 CRm=1011 op2=101 Rt=11111
     * = 0xD5033BBF */
    a64_decoded_t d = decode_word(0xD5033BBF, 0);
    if (d.instruction != A64_INS_DMB) FAIL("wrong instruction");
    PASS();
}

static void test_decode_range(void) {
    TEST(decode_range_sequence);
    /* NOP, RET */
    uint8_t code[] = {
        0x1F, 0x20, 0x03, 0xD5,  /* NOP */
        0xC0, 0x03, 0x5F, 0xD6,  /* RET */
    };
    a64_decoder_t dec;
    a64_decoder_init(&dec, code, sizeof(code), 0x1000);
    size_t count;
    a64_decoded_t* arr = a64_decode_range(&dec, &count);
    if (!arr) FAIL("null array");
    if (count != 2) FAIL("wrong count");
    if (arr[0].instruction != A64_INS_NOP) FAIL("insn 0 not NOP");
    if (arr[1].instruction != A64_INS_RET) FAIL("insn 1 not RET");
    if (arr[0].address != 0x1000) FAIL("wrong addr 0");
    if (arr[1].address != 0x1004) FAIL("wrong addr 1");
    free(arr);
    PASS();
}

static void test_sysreg_encoding(void) {
    TEST(sysreg_encoding);
    /* Verify a64_sysreg_encode packs correctly.
     * SCTLR_EL1 = S3_0_C1_C0_0 → op0=3 op1=0 CRn=1 CRm=0 op2=0
     * encoding = (3<<14)|(0<<11)|(1<<7)|(0<<3)|(0)
     *          = 0xC000 | 0 | 0x80 | 0 | 0 = 0xC080 */
    uint16_t enc = a64_sysreg_encode(3, 0, 1, 0, 0);
    if (enc != 0xC080) FAIL("wrong encoding");
    PASS();
}

/* ---- Main ---- */

int main(void) {
    printf("ARM64 Decoder Tests\n");
    printf("===================\n");

    test_nop();
    test_ret();
    test_add_imm();
    test_sub_imm();
    test_cmp_imm();
    test_movz();
    test_movk_shifted();
    test_b_unconditional();
    test_bl();
    test_b_cond();
    test_cbz();
    test_ldr_imm();
    test_str_imm();
    test_mrs();
    test_msr();
    test_svc();
    test_add_reg();
    test_mov_reg();
    test_dmb();
    test_decode_range();
    test_sysreg_encoding();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);
    return tests_passed == tests_run ? 0 : 1;
}
