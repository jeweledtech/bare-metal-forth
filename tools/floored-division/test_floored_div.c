/* ============================================================================
 * Test Harness for Floored Division Implementation
 * ============================================================================
 * 
 * This validates that our floored division matches Forth-83 semantics.
 * Run on your development machine before integrating into the kernel.
 * 
 * Build: gcc -o test_floored_div test_floored_div.c -Wall -Wextra
 * Run:   ./test_floored_div
 * ============================================================================ */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "floored_div.h"

/* Test case structure */
typedef struct {
    int64_t dividend;
    int64_t divisor;
    int64_t expected_quotient;
    int64_t expected_remainder;
    const char* description;
} test_case_t;

/* Color output for terminal */
#define RED     "\033[31m"
#define GREEN   "\033[32m"
#define YELLOW  "\033[33m"
#define RESET   "\033[0m"

/* ============================================================================
 * Test Cases - Comprehensive coverage of edge cases
 * ============================================================================ */

static test_case_t test_cases[] = {
    /* Basic positive cases */
    { 7, 3, 2, 1, "7 / 3 = 2 rem 1 (both positive)" },
    { 10, 5, 2, 0, "10 / 5 = 2 rem 0 (exact division)" },
    { 1, 1, 1, 0, "1 / 1 = 1 rem 0 (identity)" },
    { 0, 5, 0, 0, "0 / 5 = 0 rem 0 (zero dividend)" },
    
    /* Both negative (no correction needed - same signs) */
    { -7, -3, 2, -1, "-7 / -3 = 2 rem -1 (both negative)" },
    { -10, -5, 2, 0, "-10 / -5 = 2 rem 0 (exact, both negative)" },
    
    /* CRITICAL: Different signs - where floored differs from symmetric */
    { -7, 3, -3, 2, "-7 / 3 = -3 rem 2 (FLOORED: different from symmetric -2,-1)" },
    { 7, -3, -3, -2, "7 / -3 = -3 rem -2 (FLOORED: different from symmetric -2,1)" },
    { -1, 3, -1, 2, "-1 / 3 = -1 rem 2 (small negative dividend)" },
    { 1, -3, -1, -2, "1 / -3 = -1 rem -2 (small positive dividend, neg divisor)" },
    
    /* Edge cases with exact division (no remainder) */
    { -6, 3, -2, 0, "-6 / 3 = -2 rem 0 (exact, different signs)" },
    { 6, -3, -2, 0, "6 / -3 = -2 rem 0 (exact, different signs)" },
    { -6, -3, 2, 0, "-6 / -3 = 2 rem 0 (exact, both negative)" },
    
    /* Larger numbers */
    { 1000000, 7, 142857, 1, "1000000 / 7 = 142857 rem 1" },
    { -1000000, 7, -142858, 6, "-1000000 / 7 = -142858 rem 6 (FLOORED)" },
    { 1000000, -7, -142858, -6, "1000000 / -7 = -142858 rem -6 (FLOORED)" },
    
    /* Powers of 2 */
    { 17, 4, 4, 1, "17 / 4 = 4 rem 1" },
    { -17, 4, -5, 3, "-17 / 4 = -5 rem 3 (FLOORED)" },
    { 17, -4, -5, -3, "17 / -4 = -5 rem -3 (FLOORED)" },
    { -17, -4, 4, -1, "-17 / -4 = 4 rem -1" },
    
    /* Near boundaries */
    { 127, 10, 12, 7, "127 / 10" },
    { -128, 10, -13, 2, "-128 / 10 (FLOORED)" },
    
    /* Divisor larger than dividend */
    { 3, 7, 0, 3, "3 / 7 = 0 rem 3" },
    { -3, 7, -1, 4, "-3 / 7 = -1 rem 4 (FLOORED)" },
    { 3, -7, -1, -4, "3 / -7 = -1 rem -4 (FLOORED)" },
    { -3, -7, 0, -3, "-3 / -7 = 0 rem -3" },
    
    /* The Facebook response example */
    { -7, 3, -3, 2, "FB Example: -7 / 3 floored gives q=-3, r=2" },
    
    /* 64-bit values */
    { 9223372036854775807LL, 2, 4611686018427387903LL, 1, "INT64_MAX / 2" },
    { -9223372036854775807LL, 2, -4611686018427387904LL, 1, "-INT64_MAX / 2 (FLOORED)" },
};

#define NUM_TESTS (sizeof(test_cases) / sizeof(test_cases[0]))

/* ============================================================================
 * Symmetric (truncated) division for comparison
 * ============================================================================ */

static int64_t symmetric_div(int64_t a, int64_t b) {
    return a / b;
}

static int64_t symmetric_mod(int64_t a, int64_t b) {
    return a % b;
}

/* ============================================================================
 * Test Functions
 * ============================================================================ */

static int run_tests(void) {
    int passed = 0;
    int failed = 0;
    int floored_diff = 0;  /* Count cases where floored differs from symmetric */
    
    printf("============================================================\n");
    printf("Floored Division Test Suite (Forth-83 Semantics)\n");
    printf("============================================================\n\n");
    
    for (size_t i = 0; i < NUM_TESTS; i++) {
        test_case_t* tc = &test_cases[i];
        
        /* Compute floored results */
        int64_t q = floored_div64(tc->dividend, tc->divisor);
        int64_t r = floored_mod64(tc->dividend, tc->divisor);
        
        /* Also compute symmetric for comparison */
        int64_t sq = symmetric_div(tc->dividend, tc->divisor);
        int64_t sr = symmetric_mod(tc->dividend, tc->divisor);
        
        bool q_match = (q == tc->expected_quotient);
        bool r_match = (r == tc->expected_remainder);
        bool symmetric_differs = (q != sq || r != sr);
        
        /* Verify: dividend == quotient * divisor + remainder */
        int64_t verify = q * tc->divisor + r;
        bool invariant_ok = (verify == tc->dividend);
        
        /* Verify: remainder has same sign as divisor (or is zero) */
        bool sign_ok = (r == 0) || 
                       ((r > 0) == (tc->divisor > 0));
        
        if (q_match && r_match && invariant_ok && sign_ok) {
            printf(GREEN "[PASS]" RESET " %s\n", tc->description);
            if (symmetric_differs) {
                printf("       Symmetric would give: q=%ld, r=%ld\n", sq, sr);
                floored_diff++;
            }
            passed++;
        } else {
            printf(RED "[FAIL]" RESET " %s\n", tc->description);
            printf("       Input:    %ld / %ld\n", tc->dividend, tc->divisor);
            printf("       Expected: q=%ld, r=%ld\n", 
                   tc->expected_quotient, tc->expected_remainder);
            printf("       Got:      q=%ld, r=%ld\n", q, r);
            if (!invariant_ok) {
                printf(RED "       INVARIANT VIOLATION: %ld != %ld\n" RESET,
                       verify, tc->dividend);
            }
            if (!sign_ok) {
                printf(RED "       SIGN VIOLATION: remainder sign doesn't match divisor\n" RESET);
            }
            failed++;
        }
    }
    
    printf("\n============================================================\n");
    printf("Results: " GREEN "%d passed" RESET ", ", passed);
    if (failed > 0) {
        printf(RED "%d failed" RESET "\n", failed);
    } else {
        printf("%d failed\n", failed);
    }
    printf("Cases where floored differs from symmetric: " YELLOW "%d" RESET "\n",
           floored_diff);
    printf("============================================================\n");
    
    return failed;
}

/* Test the combined divmod function */
static int test_divmod(void) {
    printf("\n============================================================\n");
    printf("Testing combined divmod function\n");
    printf("============================================================\n");
    
    int failed = 0;
    
    for (size_t i = 0; i < NUM_TESTS; i++) {
        test_case_t* tc = &test_cases[i];
        
        divmod_result_t result = floored_divmod64(tc->dividend, tc->divisor);
        
        if (result.quotient != tc->expected_quotient ||
            result.remainder != tc->expected_remainder) {
            printf(RED "[FAIL]" RESET " divmod(%ld, %ld)\n",
                   tc->dividend, tc->divisor);
            printf("       Expected: q=%ld, r=%ld\n",
                   tc->expected_quotient, tc->expected_remainder);
            printf("       Got:      q=%ld, r=%ld\n",
                   result.quotient, result.remainder);
            failed++;
        }
    }
    
    if (failed == 0) {
        printf(GREEN "All divmod tests passed!\n" RESET);
    }
    
    return failed;
}

/* Print a comparison table */
static void print_comparison_table(void) {
    printf("\n============================================================\n");
    printf("Symmetric vs Floored Division Comparison\n");
    printf("============================================================\n");
    printf("%-12s | %-16s | %-16s | %-6s\n",
           "Expression", "Symmetric (CPU)", "Floored (F83)", "Diff?");
    printf("-------------|------------------|------------------|-------\n");
    
    int examples[][2] = {
        {7, 3}, {-7, 3}, {7, -3}, {-7, -3},
        {10, 3}, {-10, 3}, {10, -3}, {-10, -3},
        {1, 3}, {-1, 3}, {1, -3}, {-1, -3},
    };
    
    for (size_t i = 0; i < sizeof(examples)/sizeof(examples[0]); i++) {
        int64_t a = examples[i][0];
        int64_t b = examples[i][1];
        
        int64_t sq = symmetric_div(a, b);
        int64_t sr = symmetric_mod(a, b);
        int64_t fq = floored_div64(a, b);
        int64_t fr = floored_mod64(a, b);
        
        bool diff = (sq != fq || sr != fr);
        
        printf("%4ld / %-4ld  | q=%-4ld r=%-4ld    | q=%-4ld r=%-4ld    | %s\n",
               a, b, sq, sr, fq, fr, diff ? YELLOW "YES" RESET : "no");
    }
    
    printf("============================================================\n");
}

/* ============================================================================
 * Main
 * ============================================================================ */

int main(int argc, char* argv[]) {
    (void)argc; (void)argv;
    
    printf("\n");
    printf("╔════════════════════════════════════════════════════════════╗\n");
    printf("║  Forth-83 Floored Division Verification Suite              ║\n");
    printf("║  Jolly Genius Inc. - Ship's Systems Software               ║\n");
    printf("╚════════════════════════════════════════════════════════════╝\n");
    printf("\n");
    
    /* Print comparison table first */
    print_comparison_table();
    
    /* Run main tests */
    int failures = run_tests();
    
    /* Run divmod tests */
    failures += test_divmod();
    
    printf("\n");
    if (failures == 0) {
        printf(GREEN "✓ All tests passed - floored division is correct!\n" RESET);
        printf("  Safe to integrate into Universal Binary Translator and Forth kernel.\n");
    } else {
        printf(RED "✗ %d test(s) failed - review implementation.\n" RESET, failures);
    }
    printf("\n");
    
    return failures > 0 ? 1 : 0;
}
