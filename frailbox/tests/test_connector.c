include <stdio.h>
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

static test_case_t tests[MAX_TESTS];
static int test_count = 0;
static jmp_buf env;
static int tests_run = 0;
static int tests_failed = 0;

#define REGISTER_TEST(name) \
    do { \
        if (test_count < MAX_TESTS) { \
            strncpy(tests[test_count].name, #name, TEST_NAME_MAX - 1); \
            tests[test_count].name[TEST_NAME_MAX - 1] = '\0'; \
            tests[test_count].func = name; \
            test_count++; \
        } \
    } while (0)

#define ASSERT(condition) \
    do { \
        tests_run++; \
        if (!(condition)) { \
            printf("  ASSERTION FAILED: %s:%d: %s\n", __FILE__, __LINE__, #condition); \
            tests_failed++; \
            longjmp(env, 1); \
        } \
    } while (0)

#define ASSERT_EQ(expected, actual) \
    do { \
        tests_run++; \
        if ((expected) != (actual)) { \
            printf("  ASSERTION FAILED: %s:%d: expected %ld, got %ld\n", \
                   __FILE__, __LINE__, (long)(expected), (long)(actual)); \
            tests_failed++; \
            longjmp(env, 1); \
        } \
    } while (0)

/* ================================================================== */
/* MOCK CONNECTOR FUNCTIONS / PROTOCOL HOOKS FOR SEED TESTING         */
/* ================================================================== */

/* 
 * Issue #2: [BOUNTY] Kickama #304 - deterministic data seed
 * We need to verify that the connector layer properly respects and propagates
 * deterministic data seeds for reproducible payload generation and connection parameters.
 */

static void test_connector_deterministic_seed_basic(void) {
    /* Initialize connector with a specific seed and verify predictable stream generation */
    uint64_t seed = 42;
    connector_config_t config;
    connector_status_t status;

    memset(&config, 0, sizeof(config));
    config.seed = seed;
    config.use_deterministic_seed = 1;

    status = connector_init(&config);
    ASSERT_EQ(CONNECTOR_SUCCESS, status);

    uint32_t val1 = connector_generate_seeded_token();
    
    connector_reset_seed(seed);
    uint32_t val2 = connector_generate_seeded_token();

    ASSERT_EQ(val1, val2);
    connector_cleanup();
}

static void test_connector_deterministic_seed_different_seeds(void) {
    /* Different seeds should yield different deterministic sequences */
    connector_config_t config1, config2;

    memset(&config1, 0, sizeof(config1));
    config1.seed = 100;
    config1.use_deterministic_seed = 1;

    memset(&config2, 0, sizeof(config2));
    config2.seed = 200;
    config2.use_deterministic_seed = 1;

    connector_init(&config1);
    uint32_t val1 = connector_generate_seeded_token();
    connector_cleanup();

    connector_init(&config2);
    uint32_t val2 = connector_generate_seeded_token();
    connector_cleanup();

    /* Statistically extremely unlikely to collide */
    ASSERT(val1 != val2);
}

static void test_connector_without_seed_fallback(void) {
    /* When deterministic seed is disabled, behavior should fall back cleanly */
    connector_config_t config;
    memset(&config, 0, sizeof(config));
    config.use_deterministic_seed = 0;

    connector_status_t status = connector_init(&config);
    ASSERT_EQ(CONNECTOR_SUCCESS, status);
    connector_cleanup();
}

/* ================================================================== */
/* MAIN TEST RUNNER                                                   */
/* ================================================================== */

int main(void) {
    printf("Running connector test suite (Issue #2: Deterministic Data Seed)...\n");

    REGISTER_TEST(test_connector_deterministic_seed_basic);
    REGISTER_TEST(test_connector_deterministic_seed_different_seeds);
    REGISTER_TEST(test_connector_without_seed_fallback);

    for (int i = 0; i < test_count; i++) {
        printf("[TEST] %s\n", tests[i].name);
        if (setjmp(env) == 0) {
            tests[i].func();
            printf("  PASS\n");
        } else {
            printf("  FAIL\n");
        }
    }

    printf("\nTest Summary:\n");
    printf("  Total assertions run: %d\n", tests_run);
    printf("  Failed tests: %d / %d\n", tests_failed, test_count);

    return tests_failed > 0 ? 1 : 0;
}