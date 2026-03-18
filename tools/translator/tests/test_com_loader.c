/* ============================================================================
 * COM Loader Tests
 * ============================================================================
 *
 * Validates the DOS .com flat binary loader.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "../include/com_loader.h"
#include "../include/x86_decoder.h"

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) do { \
    tests_run++; \
    printf("  TEST: %-50s ", #name); \
} while(0)

#define PASS() do { tests_passed++; printf("PASS\n"); } while(0)
#define FAIL(msg) do { printf("FAIL: %s\n", msg); return; } while(0)

/* ============================================================================
 * Tests
 * ============================================================================ */

static void test_com_load_minimal(void) {
    TEST(com_load_minimal);
    uint8_t code[] = {0xC3};  /* RET */
    com_context_t com;
    if (com_load(&com, code, sizeof(code)) != 0)
        FAIL("com_load failed on 1-byte file");
    if (com.code_size != 1)
        FAIL("wrong code_size");
    com_cleanup(&com);
    PASS();
}

static void test_com_load_address(void) {
    TEST(com_load_address);
    uint8_t code[] = {0xC3};
    com_context_t com;
    com_load(&com, code, sizeof(code));
    if (com.load_addr != 0x0100) {
        char msg[64];
        snprintf(msg, sizeof(msg), "expected 0x100, got 0x%X", com.load_addr);
        FAIL(msg);
    }
    if (!com.is_16bit)
        FAIL("expected is_16bit = true");
    com_cleanup(&com);
    PASS();
}

static void test_com_load_null(void) {
    TEST(com_load_null);
    com_context_t com;
    if (com_load(&com, NULL, 0) == 0)
        FAIL("should reject NULL data");
    if (com_load(NULL, (uint8_t*)"x", 1) == 0)
        FAIL("should reject NULL ctx");
    PASS();
}

static void test_com_load_empty(void) {
    TEST(com_load_empty);
    uint8_t code[] = {0xC3};
    com_context_t com;
    if (com_load(&com, code, 0) == 0)
        FAIL("should reject zero-length");
    PASS();
}

static void test_com_load_too_large(void) {
    TEST(com_load_too_large);
    uint8_t* big = malloc(70000);
    memset(big, 0x90, 70000);  /* NOP sled */
    com_context_t com;
    if (com_load(&com, big, 70000) == 0) {
        free(big);
        FAIL("should reject >65280 bytes");
    }
    free(big);
    PASS();
}

static void test_com_max_size(void) {
    TEST(com_max_size);
    uint8_t* max = malloc(COM_MAX_SIZE);
    memset(max, 0x90, COM_MAX_SIZE);
    com_context_t com;
    if (com_load(&com, max, COM_MAX_SIZE) != 0) {
        free(max);
        FAIL("should accept exactly 65280 bytes");
    }
    if (com.code_size != COM_MAX_SIZE) {
        free(max);
        FAIL("wrong code_size for max-size file");
    }
    free(max);
    PASS();
}

static void test_com_port_detection(void) {
    TEST(com_port_detection);
    /* IN AL, 0x60; OUT 0x61, AL; IN AL, DX; OUT DX, AL; RET */
    uint8_t code[] = {0xE4, 0x60, 0xE6, 0x61, 0xEC, 0xEE, 0xC3};
    com_context_t com;
    com_load(&com, code, sizeof(code));

    /* Decode the COM content — x86 IN/OUT opcodes work in both 16 and 32 bit mode */
    x86_decoder_t dec;
    x86_decoder_init(&dec, X86_MODE_32, com.code, com.code_size, com.load_addr);
    size_t count = 0;
    x86_decoded_t* insts = x86_decode_range(&dec, &count);

    if (!insts || count == 0)
        FAIL("decoder returned no instructions");

    /* Should find IN/OUT instructions */
    int port_ops = 0;
    for (size_t i = 0; i < count; i++) {
        if (insts[i].instruction == X86_INS_IN || insts[i].instruction == X86_INS_OUT)
            port_ops++;
    }
    free(insts);

    if (port_ops < 4) {
        char msg[64];
        snprintf(msg, sizeof(msg), "expected 4 port ops, got %d", port_ops);
        FAIL(msg);
    }
    com_cleanup(&com);
    PASS();
}

static void test_com_port_addresses(void) {
    TEST(com_port_addresses);
    /* IN AL, 0x60; OUT 0x61, AL; RET */
    uint8_t code[] = {0xE4, 0x60, 0xE6, 0x61, 0xC3};
    com_context_t com;
    com_load(&com, code, sizeof(code));

    x86_decoder_t dec;
    x86_decoder_init(&dec, X86_MODE_32, com.code, com.code_size, com.load_addr);
    size_t count = 0;
    x86_decoded_t* insts = x86_decode_range(&dec, &count);

    bool found_60 = false, found_61 = false;
    for (size_t i = 0; i < count; i++) {
        if (insts[i].instruction == X86_INS_IN || insts[i].instruction == X86_INS_OUT) {
            /* Immediate port is in operands[1].imm for IN, operands[0].imm for OUT */
            for (int j = 0; j < insts[i].operand_count; j++) {
                if (insts[i].operands[j].type == X86_OP_IMM) {
                    if (insts[i].operands[j].imm == 0x60) found_60 = true;
                    if (insts[i].operands[j].imm == 0x61) found_61 = true;
                }
            }
        }
    }
    free(insts);

    if (!found_60) FAIL("port 0x60 not found");
    if (!found_61) FAIL("port 0x61 not found");

    com_cleanup(&com);
    PASS();
}

/* ============================================================================
 * Main
 * ============================================================================ */

int main(void) {
    printf("COM Loader Tests\n");
    printf("================\n");

    test_com_load_minimal();
    test_com_load_address();
    test_com_load_null();
    test_com_load_empty();
    test_com_load_too_large();
    test_com_max_size();
    test_com_port_detection();
    test_com_port_addresses();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);
    return tests_passed == tests_run ? 0 : 1;
}
