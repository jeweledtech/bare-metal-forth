/* ============================================================================
 * UIR Lifter Tests
 * ============================================================================
 *
 * Tests that x86 decoded instructions lift correctly to UIR representation.
 * Uses the same byte sequences from the x86 decoder tests as input.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include "../include/uir.h"
#include "../include/x86_decoder.h"

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) do { \
    tests_run++; \
    printf("  TEST: %-50s ", #name); \
} while(0)

#define PASS() do { tests_passed++; printf("PASS\n"); } while(0)
#define FAIL(msg) do { printf("FAIL: %s\n", msg); return; } while(0)

/* Helper: decode x86 bytes, then lift to UIR */
static uir_function_t* decode_and_lift(const uint8_t* code, size_t code_size,
                                        uint64_t base_addr) {
    x86_decoder_t dec;
    x86_decoder_init(&dec, X86_MODE_32, code, code_size, base_addr);

    size_t count;
    x86_decoded_t* insts = x86_decode_range(&dec, &count);
    if (!insts || count == 0) return NULL;

    /* Convert x86_decoded_t to uir_x86_input_t (same layout, just cast) */
    uir_x86_input_t* inputs = (uir_x86_input_t*)insts;

    uir_function_t* func = uir_lift_function(inputs, count, base_addr);
    free(insts);
    return func;
}

/* ---- Test: IN AL, 0x60 should produce UIR_PORT_IN ---- */
static void test_port_in_immediate(void) {
    TEST(port_in_immediate);
    uint8_t code[] = { 0xE4, 0x60, 0xC3 };  /* IN AL, 0x60; RET */
    uir_function_t* func = decode_and_lift(code, sizeof(code), 0x1000);
    if (!func) FAIL("lift returned NULL");
    if (func->block_count < 1) FAIL("no blocks");
    if (func->blocks[0].count < 1) FAIL("no instructions in block");

    uir_instruction_t* ins = &func->blocks[0].instructions[0];
    if (ins->opcode != UIR_PORT_IN) FAIL("expected UIR_PORT_IN");
    if (ins->src1.imm != 0x60) FAIL("port should be 0x60");
    if (ins->size != 1) FAIL("size should be 1 (byte)");
    if (!func->has_port_io) FAIL("has_port_io should be true");

    uir_free_function(func);
    PASS();
}

/* ---- Test: OUT 0x60, AL should produce UIR_PORT_OUT ---- */
static void test_port_out_immediate(void) {
    TEST(port_out_immediate);
    uint8_t code[] = { 0xE6, 0x60, 0xC3 };  /* OUT 0x60, AL; RET */
    uir_function_t* func = decode_and_lift(code, sizeof(code), 0x1000);
    if (!func) FAIL("lift returned NULL");

    uir_instruction_t* ins = &func->blocks[0].instructions[0];
    if (ins->opcode != UIR_PORT_OUT) FAIL("expected UIR_PORT_OUT");
    if (ins->dest.imm != 0x60) FAIL("port should be 0x60");
    if (ins->size != 1) FAIL("size should be 1 (byte)");

    uir_free_function(func);
    PASS();
}

/* ---- Test: IN AL, DX should produce UIR_PORT_IN with DX source ---- */
static void test_port_in_dx(void) {
    TEST(port_in_dx);
    uint8_t code[] = { 0xEC, 0xC3 };  /* IN AL, DX; RET */
    uir_function_t* func = decode_and_lift(code, sizeof(code), 0x1000);
    if (!func) FAIL("lift returned NULL");

    uir_instruction_t* ins = &func->blocks[0].instructions[0];
    if (ins->opcode != UIR_PORT_IN) FAIL("expected UIR_PORT_IN");
    if (ins->src1.type != UIR_OPERAND_REG) FAIL("port should be register (DX)");
    if (ins->size != 1) FAIL("size should be 1");
    if (!func->uses_dx_port) FAIL("uses_dx_port should be true");

    uir_free_function(func);
    PASS();
}

/* ---- Test: OUT DX, AL should produce UIR_PORT_OUT with DX dest ---- */
static void test_port_out_dx(void) {
    TEST(port_out_dx);
    uint8_t code[] = { 0xEE, 0xC3 };  /* OUT DX, AL; RET */
    uir_function_t* func = decode_and_lift(code, sizeof(code), 0x1000);
    if (!func) FAIL("lift returned NULL");

    uir_instruction_t* ins = &func->blocks[0].instructions[0];
    if (ins->opcode != UIR_PORT_OUT) FAIL("expected UIR_PORT_OUT");
    if (ins->dest.type != UIR_OPERAND_REG) FAIL("port should be register (DX)");

    uir_free_function(func);
    PASS();
}

/* ---- Test: MOV EAX, [EBX+4] should produce UIR_LOAD ---- */
static void test_load(void) {
    TEST(load_from_memory);
    uint8_t code[] = { 0x8B, 0x43, 0x04, 0xC3 };  /* MOV EAX, [EBX+4]; RET */
    uir_function_t* func = decode_and_lift(code, sizeof(code), 0x1000);
    if (!func) FAIL("lift returned NULL");

    uir_instruction_t* ins = &func->blocks[0].instructions[0];
    if (ins->opcode != UIR_LOAD) FAIL("expected UIR_LOAD");
    if (ins->dest.reg != 0) FAIL("dest should be EAX (reg 0)");

    uir_free_function(func);
    PASS();
}

/* ---- Test: MOV [EBX], EAX should produce UIR_STORE ---- */
static void test_store(void) {
    TEST(store_to_memory);
    uint8_t code[] = { 0x89, 0x03, 0xC3 };  /* MOV [EBX], EAX; RET */
    uir_function_t* func = decode_and_lift(code, sizeof(code), 0x1000);
    if (!func) FAIL("lift returned NULL");

    uir_instruction_t* ins = &func->blocks[0].instructions[0];
    if (ins->opcode != UIR_STORE) FAIL("expected UIR_STORE");

    uir_free_function(func);
    PASS();
}

/* ---- Test: CALL rel32 should produce UIR_CALL ---- */
static void test_call(void) {
    TEST(call_relative);
    uint8_t code[] = { 0xE8, 0x10, 0x00, 0x00, 0x00, 0xC3 };
    uir_function_t* func = decode_and_lift(code, sizeof(code), 0x1000);
    if (!func) FAIL("lift returned NULL");

    uir_instruction_t* ins = &func->blocks[0].instructions[0];
    if (ins->opcode != UIR_CALL) FAIL("expected UIR_CALL");

    uir_free_function(func);
    PASS();
}

/* ---- Test: RET should produce UIR_RET ---- */
static void test_ret(void) {
    TEST(ret);
    uint8_t code[] = { 0xC3 };
    uir_function_t* func = decode_and_lift(code, sizeof(code), 0x1000);
    if (!func) FAIL("lift returned NULL");
    if (func->blocks[0].count < 1) FAIL("no instructions");

    uir_instruction_t* ins = &func->blocks[0].instructions[0];
    if (ins->opcode != UIR_RET) FAIL("expected UIR_RET");

    uir_free_function(func);
    PASS();
}

/* ---- Test: ADD EAX, imm should produce UIR_ADD ---- */
static void test_add(void) {
    TEST(add_immediate);
    uint8_t code[] = { 0x83, 0xC0, 0x05, 0xC3 };  /* ADD EAX, 5; RET */
    uir_function_t* func = decode_and_lift(code, sizeof(code), 0x1000);
    if (!func) FAIL("lift returned NULL");

    uir_instruction_t* ins = &func->blocks[0].instructions[0];
    if (ins->opcode != UIR_ADD) FAIL("expected UIR_ADD");

    uir_free_function(func);
    PASS();
}

/* ---- Test: XOR EAX, EAX should produce UIR_XOR ---- */
static void test_xor(void) {
    TEST(xor_reg_reg);
    uint8_t code[] = { 0x31, 0xC0, 0xC3 };  /* XOR EAX, EAX; RET */
    uir_function_t* func = decode_and_lift(code, sizeof(code), 0x1000);
    if (!func) FAIL("lift returned NULL");

    uir_instruction_t* ins = &func->blocks[0].instructions[0];
    if (ins->opcode != UIR_XOR) FAIL("expected UIR_XOR");

    uir_free_function(func);
    PASS();
}

/* ---- Test: JE should split into two basic blocks ---- */
static void test_conditional_branch_splits_blocks(void) {
    TEST(conditional_branch_splits_blocks);
    /* CMP EAX, 0; JE +2; NOP; NOP; RET */
    uint8_t code[] = {
        0x83, 0xF8, 0x00,   /* CMP EAX, 0 */
        0x74, 0x01,          /* JE +1 (skip one NOP) */
        0x90,                /* NOP (fall-through path) */
        0x90,                /* NOP (branch target) */
        0xC3,                /* RET */
    };
    uir_function_t* func = decode_and_lift(code, sizeof(code), 0x1000);
    if (!func) FAIL("lift returned NULL");

    /* Should have more than 1 block due to the branch */
    if (func->block_count < 2) {
        char msg[64];
        snprintf(msg, sizeof(msg), "expected >=2 blocks, got %zu", func->block_count);
        FAIL(msg);
    }

    uir_free_function(func);
    PASS();
}

/* ---- Test: CLI/STI should produce UIR_CLI/UIR_STI ---- */
static void test_cli_sti(void) {
    TEST(cli_sti);
    uint8_t code[] = { 0xFA, 0xFB, 0xC3 };  /* CLI; STI; RET */
    uir_function_t* func = decode_and_lift(code, sizeof(code), 0x1000);
    if (!func) FAIL("lift returned NULL");
    if (func->blocks[0].count < 2) FAIL("expected at least 2 instructions");

    if (func->blocks[0].instructions[0].opcode != UIR_CLI) FAIL("expected UIR_CLI");
    if (func->blocks[0].instructions[1].opcode != UIR_STI) FAIL("expected UIR_STI");

    uir_free_function(func);
    PASS();
}

/* ---- Test: port summary tracks read ports ---- */
static void test_port_summary(void) {
    TEST(port_summary);
    /* IN AL, 0x60; IN AL, 0x64; OUT 0x60, AL; RET */
    uint8_t code[] = { 0xE4, 0x60, 0xE4, 0x64, 0xE6, 0x60, 0xC3 };
    uir_function_t* func = decode_and_lift(code, sizeof(code), 0x1000);
    if (!func) FAIL("lift returned NULL");
    if (!func->has_port_io) FAIL("has_port_io should be true");
    if (func->ports_read_count < 2) FAIL("should have 2 ports read");
    if (func->ports_written_count < 1) FAIL("should have 1 port written");

    uir_free_function(func);
    PASS();
}

/* ---- Test: PUSH/POP should lift correctly ---- */
static void test_push_pop(void) {
    TEST(push_pop);
    uint8_t code[] = { 0x50, 0x58, 0xC3 };  /* PUSH EAX; POP EAX; RET */
    uir_function_t* func = decode_and_lift(code, sizeof(code), 0x1000);
    if (!func) FAIL("lift returned NULL");

    if (func->blocks[0].instructions[0].opcode != UIR_PUSH) FAIL("expected UIR_PUSH");
    if (func->blocks[0].instructions[1].opcode != UIR_POP) FAIL("expected UIR_POP");

    uir_free_function(func);
    PASS();
}

/* ---- Test: MOV reg, reg should produce UIR_MOV ---- */
static void test_mov_reg_reg(void) {
    TEST(mov_reg_reg);
    uint8_t code[] = { 0x89, 0xC1, 0xC3 };  /* MOV ECX, EAX; RET */
    uir_function_t* func = decode_and_lift(code, sizeof(code), 0x1000);
    if (!func) FAIL("lift returned NULL");

    uir_instruction_t* ins = &func->blocks[0].instructions[0];
    if (ins->opcode != UIR_MOV) FAIL("expected UIR_MOV");

    uir_free_function(func);
    PASS();
}

/* ---- Test: CMP should produce UIR_CMP ---- */
static void test_cmp(void) {
    TEST(cmp);
    uint8_t code[] = { 0x83, 0xF8, 0x00, 0xC3 };  /* CMP EAX, 0; RET */
    uir_function_t* func = decode_and_lift(code, sizeof(code), 0x1000);
    if (!func) FAIL("lift returned NULL");

    if (func->blocks[0].instructions[0].opcode != UIR_CMP) FAIL("expected UIR_CMP");

    uir_free_function(func);
    PASS();
}

/* ---- Test: IN EAX, imm8 (dword port read) ---- */
static void test_port_in_dword(void) {
    TEST(port_in_dword);
    uint8_t code[] = { 0xE5, 0xCF, 0xC3 };  /* IN EAX, 0xCF; RET */
    uir_function_t* func = decode_and_lift(code, sizeof(code), 0x1000);
    if (!func) FAIL("lift returned NULL");

    uir_instruction_t* ins = &func->blocks[0].instructions[0];
    if (ins->opcode != UIR_PORT_IN) FAIL("expected UIR_PORT_IN");
    if (ins->src1.imm != 0xCF) FAIL("port should be 0xCF");
    if (ins->size != 4) FAIL("size should be 4 (dword)");

    uir_free_function(func);
    PASS();
}

int main(void) {
    printf("UIR Lifter Tests\n");
    printf("================\n");

    test_port_in_immediate();
    test_port_out_immediate();
    test_port_in_dx();
    test_port_out_dx();
    test_load();
    test_store();
    test_call();
    test_ret();
    test_add();
    test_xor();
    test_conditional_branch_splits_blocks();
    test_cli_sti();
    test_port_summary();
    test_push_pop();
    test_mov_reg_reg();
    test_cmp();
    test_port_in_dword();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);
    return tests_passed == tests_run ? 0 : 1;
}
