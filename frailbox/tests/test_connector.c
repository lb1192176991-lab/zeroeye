#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <setjmp.h>
#include <time.h>

#include "../connector/api.h"
#include "../connector/protocol.h"

/* ================================================================== */
/* MINIMAL TEST FRAMEWORK                                             */
/* ================================================================== */

#define MAX_TESTS 256
#define TEST_NAME_MAX 128

typedef void (*test_func_t)(void);

typedef struct {
    char name[TEST_NAME_MAX];
    test_func_t func;
} test_case_t;

static test_case_t g_tests[MAX_TESTS];
static int g_test_count = 0;

static jmp_buf g_env;
static const char* g_current_test = NULL;
static int g_assertions_failed = 0;
static int g_assertions_passed = 0;

#define REGISTER_TEST(name) \
    void name(void); \
    __attribute__((constructor)) static void _reg_##name(void) { \
        if (g_test_count < MAX_TESTS) { \
            strncpy(g_tests[g_test_count].name, #name, TEST_NAME_MAX - 1); \
            g_tests[g_test_count].func = name; \
            g_test_count++; \
        } \
    }

#define ASSERT(condition) do { \
    if (!(condition)) { \
        printf("    ASSERTION FAILED: %s\n", #condition); \
        printf("      at %s:%d\n", __FILE__, __LINE__); \
        g_assertions_failed++; \
        longjmp(g_env, 1); \
    } else { \
        g_assertions_passed++; \
    } \
} while(0)

#define ASSERT_EQ(expected, actual) do { \
    long long exp_val = (long long)(expected); \
    long long act_val = (long long)(actual); \
    if (exp_val != act_val) { \
        printf("    ASSERTION FAILED: %s == %s (expected %lld, got %lld)\n", \
               #expected, #actual, exp_val, act_val); \
        printf("      at %s:%d\n", __FILE__, __LINE__); \
        g_assertions_failed++; \
        longjmp(g_env, 1); \
    } else { \
        g_assertions_passed++; \
    } \
} while(0)

#define ASSERT_STR_EQ(expected, actual) do { \
    const char* exp_str = (expected); \
    const char* act_str = (actual); \
    if (exp_str == NULL || act_str == NULL || strcmp(exp_str, act_str) != 0) { \
        printf("    ASSERTION FAILED: strcmp(%s, %s) == 0 (expected \"%s\", got \"%s\")\n", \
               #expected, #actual, exp_str ? exp_str : "NULL", act_str ? act_str : "NULL"); \
        printf("      at %s:%d\n", __FILE__, __LINE__); \
        g_assertions_failed++; \
        longjmp(g_env, 1); \
    } else { \
        g_assertions_passed++; \
    } \
} while(0)

/* ================================================================== */
/* CONNECTOR TESTS - ISSUE #2: DETERMINISTIC DATA SEED VERIFICATION   */
/* ================================================================== */

void test_connector_seed_initialization_default(void) {
    /* Verify that default connector configuration initializes with standard seed (42) */
    ConnectorConfig config;
    int rc = connector_config_init_default(&config);
    ASSERT_EQ(0, rc);
    ASSERT_EQ(42, config.data_seed);
}

void test_connector_seed_custom(void) {
    /* Verify that setting a custom seed persists correctly in the connector context */
    ConnectorContext* ctx = connector_create();
    ASSERT(ctx != NULL);

    int rc = connector_set_data_seed(ctx, 1337);
    ASSERT_EQ(0, rc);
    ASSERT_EQ(1337, connector_get_data_seed(ctx));

    connector_destroy(ctx);
}

void test_connector_deterministic_payload_generation(void) {
    /* Verify that identical seeds generate identical output buffers (Issue #2 fix) */
    ConnectorContext* ctx1 = connector_create();
    ConnectorContext* ctx2 = connector_create();
    ASSERT(ctx1 != NULL);
    ASSERT(ctx2 != NULL);

    connector_set_data_seed(ctx1, 9999);
    connector_set_data_seed(ctx2, 9999);

    uint8_t buffer1[64];
    uint8_t buffer2[64];
    memset(buffer1, 0, sizeof(buffer1));
    memset(buffer2, 0, sizeof(buffer2));

    int len1 = connector_generate_seeded_payload(ctx1, buffer1, sizeof(buffer1));
    int len2 = connector_generate_seeded_payload(ctx2, buffer2, sizeof(buffer2));

    ASSERT_EQ(len1, len2);
    ASSERT(len1 > 0);
    ASSERT_EQ(0, memcmp(buffer1, buffer2, len1));

    connector_destroy(ctx1);
    connector_destroy(ctx2);
}

void test_connector_nondeterministic_different_seeds(void) {
    /* Verify that different seeds produce different outputs */
    ConnectorContext* ctx1 = connector_create();
    ConnectorContext* ctx2 = connector_create();
    ASSERT(ctx1 != NULL);
    ASSERT(ctx2 != NULL);

    connector_set_data_seed(ctx1, 1111);
    connector_set_data_seed(ctx2, 2222);

    uint8_t buffer1[64];
    uint8_t buffer2[64];
    memset(buffer1, 0, sizeof(buffer1));
    memset(buffer2, 0, sizeof(buffer2));

    int len1 = connector_generate_seeded_payload(ctx1, buffer1, sizeof(buffer1));
    int len2 = connector_generate_seeded_payload(ctx2, buffer2, sizeof(buffer2));

    ASSERT_EQ(len1, len2);
    ASSERT(len1 > 0);
    
    /* Highly improbable to collide on cryptographic/pseudo-random generation */
    int diff = memcmp(buffer1, buffer2, len1);
    ASSERT(diff != 0);

    connector_destroy(ctx1);
    connector_destroy(ctx2);
}

REGISTER_TEST(test_connector_seed_initialization_default);
REGISTER_TEST(test_connector_seed_custom);
REGISTER_TEST(test_connector_deterministic_payload_generation);
REGISTER_TEST(test_connector_nondeterministic_different_seeds);

/* ================================================================== */
/* TEST RUNNER MAIN                                                   */
/* ================================================================== */

int main(int argc, char** argv) {
    (void)argc;
    (void)argv;

    printf("==================================================\n");
    printf("Running Frailbox Connector Tests (Issue #2 Fix)\n");
    printf("Total tests registered: %d\n", g_test_count);
    printf("==================================================\n");

    int failed_tests = 0;
    clock_t total_start = clock();

    for (int i = 0; i < g_test_count; i++) {
        g_current_test = g_tests[i].name;
        printf("[RUN   ] %s\n", g_current_test);

        g_assertions_failed = 0;
        g_assertions_passed = 0;

        clock_t test_start = clock();
        if (setjmp(g_env) == 0) {
            g_tests[i].func();
        } else {
            failed_tests++;
            printf("[FAILED] %s\n", g_current_test);
            continue;
        }
        clock_t test_end = clock();

        double elapsed = (double)(test_end - test_start) / CLOCKS_PER_SEC * 1000.0;
        printf("[OK    ] %s (%.2f ms, %d assertions passed)\n",
               g_current_test, elapsed, g_assertions_passed);
    }

    clock_t total_end = clock();
    double total_elapsed = (double)(total_end - total_start) / CLOCKS_PER_SEC * 1000.0;

    printf("==================================================\n");
    printf("Test run complete in %.2f ms\n", total_elapsed);
    printf("  Total tests: %d\n", g_test_count);
    printf("  Passed:      %d\n", g_test_count - failed_tests);
    printf("  Failed:      %d\n", failed_tests);
    printf("==================================================\n");

    return failed_tests > 0 ? 1 : 0;
}