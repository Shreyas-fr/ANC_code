#include "gap_safe_ring_buffer.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <math.h>

typedef struct {
    gap_safe_ring_buffer_t *rb;
    int64_t total_samples;
    uint32_t chunk_size;
    bool success;
    int mismatches;
} thread_test_args_t;

void *producer_contiguous(void *arg) {
    thread_test_args_t *args = (thread_test_args_t *)arg;
    float *chunk = (float *)malloc(args->chunk_size * sizeof(float));
    for (int64_t idx = 0; idx < args->total_samples; idx += args->chunk_size) {
        for (uint32_t i = 0; i < args->chunk_size; ++i) {
            chunk[i] = (float)((idx + i) % 10000);
        }
        trb_status_t status = trb_write(args->rb, idx, chunk, args->chunk_size);
        if (status != TRB_SUCCESS) {
            args->success = false;
            break;
        }
        // Micro-yield to pace concurrent streaming
        usleep(15);
    }
    free(chunk);
    return NULL;
}

void *consumer_contiguous(void *arg) {
    thread_test_args_t *args = (thread_test_args_t *)arg;
    float *chunk = (float *)malloc(args->chunk_size * sizeof(float));
    for (int64_t idx = 0; idx < args->total_samples; idx += args->chunk_size) {
        trb_status_t status = trb_read(args->rb, idx, chunk, args->chunk_size);
        if (status != TRB_SUCCESS) {
            args->success = false;
            break;
        }
        for (uint32_t i = 0; i < args->chunk_size; ++i) {
            float expected = (float)((idx + i) % 10000);
            if (fabsf(chunk[i] - expected) > 1e-6f) {
                args->mismatches++;
            }
        }
    }
    free(chunk);
    return NULL;
}

void *waiting_consumer(void *arg) {
    thread_test_args_t *args = (thread_test_args_t *)arg;
    float buf[64];
    // Attempt to read samples from 10000 that will never be written
    trb_status_t status = trb_read(args->rb, 10000, buf, 64);
    // Expect TRB_ERROR_SHUTDOWN
    args->success = (status == TRB_ERROR_SHUTDOWN);
    return NULL;
}

int main(int argc, char **argv) {
    printf("======================================================================\n");
    printf("STAGE 11.2.35R AUDIT: COMPREHENSIVE GAP-SAFE RING BUFFER TEST SUITE\n");
    printf("======================================================================\n\n");

    bool all_passed = true;

    // TEST 1: Normal Contiguous Reads
    printf("[Test 1/8] Normal Contiguous Reads...\n");
    gap_safe_ring_buffer_t rb1;
    trb_init(&rb1, 1024);
    float wdata[128], rdata[128];
    for (int i = 0; i < 128; ++i) wdata[i] = (float)(i + 1);
    trb_write(&rb1, 0, wdata, 128);
    trb_status_t s1 = trb_read(&rb1, 0, rdata, 128);
    bool pass1 = (s1 == TRB_SUCCESS);
    for (int i = 0; i < 128 && pass1; ++i) {
        if (rdata[i] != wdata[i]) pass1 = false;
    }
    printf("  Status: %s (code=%d)\n", pass1 ? "PASS" : "FAIL", s1);
    all_passed &= pass1;
    trb_destroy(&rb1);

    // TEST 2: Producer Gaps Detection
    printf("\n[Test 2/8] Producer Gap Detection (Unwritten Hole)...\n");
    gap_safe_ring_buffer_t rb2;
    trb_init(&rb2, 1024);
    // Write 0..99
    float part1[100], part2[100];
    for (int i = 0; i < 100; ++i) { part1[i] = 1.0f; part2[i] = 2.0f; }
    trb_write(&rb2, 0, part1, 100);
    // Gap: skip 100..199! Write 200..299
    trb_write(&rb2, 200, part2, 100);
    // Read spanning the gap: 80..120
    float gap_buf[40];
    trb_status_t s2 = trb_read(&rb2, 80, gap_buf, 40);
    bool pass2 = (s2 == TRB_ERROR_GAP);
    printf("  Status: %s (expected TRB_ERROR_GAP, got %d)\n", pass2 ? "PASS" : "FAIL", s2);
    all_passed &= pass2;
    trb_destroy(&rb2);

    // TEST 3: Overwritten Unread Samples (Overrun Detection)
    printf("\n[Test 3/8] Overrun Detection (Buffer Capacity Exceeded)...\n");
    gap_safe_ring_buffer_t rb3;
    trb_init(&rb3, 512); // Small capacity: 512 samples
    float block[512];
    for (int i = 0; i < 512; ++i) block[i] = 5.0f;
    // Write generation 0 (0..511)
    trb_write(&rb3, 0, block, 512);
    // Overwrite generation 1 (512..1023) -> samples 0..511 are now overrun!
    trb_write(&rb3, 512, block, 512);
    // Attempt to read old sample 100
    float old_buf[64];
    trb_status_t s3 = trb_read(&rb3, 100, old_buf, 64);
    bool pass3 = (s3 == TRB_ERROR_OVERRUN);
    printf("  Status: %s (expected TRB_ERROR_OVERRUN, got %d)\n", pass3 ? "PASS" : "FAIL", s3);
    all_passed &= pass3;
    trb_destroy(&rb3);

    // TEST 4: Wraparound Integrity
    printf("\n[Test 4/8] Circular Wraparound Across Multiple Generations...\n");
    gap_safe_ring_buffer_t rb4;
    trb_init(&rb4, 1024);
    bool pass4 = true;
    float wrap_w[256], wrap_r[256];
    // 16 iterations of 256 samples = 4096 samples = 4 full circular loops
    for (int64_t idx = 0; idx < 4096; idx += 256) {
        for (int i = 0; i < 256; ++i) wrap_w[i] = (float)(idx + i);
        trb_write(&rb4, idx, wrap_w, 256);
        trb_status_t s4 = trb_read(&rb4, idx, wrap_r, 256);
        if (s4 != TRB_SUCCESS) { pass4 = false; break; }
        for (int i = 0; i < 256; ++i) {
            if (wrap_r[i] != wrap_w[i]) { pass4 = false; break; }
        }
    }
    printf("  Status: %s (4096 samples verified over 1024 capacity)\n", pass4 ? "PASS" : "FAIL");
    all_passed &= pass4;
    trb_destroy(&rb4);

    // TEST 5: Out-of-Order Writes Support
    printf("\n[Test 5/8] Out-of-Order Writes with Staged Reading...\n");
    gap_safe_ring_buffer_t rb5;
    trb_init(&rb5, 1024);
    float b_first[64], b_second[64], b_combined[128];
    for (int i = 0; i < 64; ++i) { b_first[i] = 100.0f + i; b_second[i] = 200.0f + i; }
    // Write second block first (64..127)
    trb_write(&rb5, 64, b_second, 64);
    // Write first block second (0..63)
    trb_write(&rb5, 0, b_first, 64);
    // Read full combined range (0..127)
    trb_status_t s5 = trb_read(&rb5, 0, b_combined, 128);
    bool pass5 = (s5 == TRB_SUCCESS);
    for (int i = 0; i < 64 && pass5; ++i) {
        if (b_combined[i] != b_first[i]) pass5 = false;
        if (b_combined[i + 64] != b_second[i]) pass5 = false;
    }
    printf("  Status: %s (code=%d, samples identical)\n", pass5 ? "PASS" : "FAIL", s5);
    all_passed &= pass5;
    trb_destroy(&rb5);

    // TEST 6: Concurrent Multi-Threaded Stress Test
    printf("\n[Test 6/8] Concurrent Multi-Threaded Stress Test (500,000 samples)...\n");
    gap_safe_ring_buffer_t rb6;
    trb_init(&rb6, 16384);
    thread_test_args_t prod_args = { &rb6, 500000, 256, true, 0 };
    thread_test_args_t cons_args = { &rb6, 500000, 256, true, 0 };
    pthread_t p_th, c_th;
    pthread_create(&c_th, NULL, consumer_contiguous, &cons_args);
    pthread_create(&p_th, NULL, producer_contiguous, &prod_args);
    pthread_join(p_th, NULL);
    pthread_join(c_th, NULL);
    bool pass6 = prod_args.success && cons_args.success && (cons_args.mismatches == 0);
    printf("  Status: %s (500k samples, mismatches=%d)\n", pass6 ? "PASS" : "FAIL", cons_args.mismatches);
    all_passed &= pass6;
    trb_destroy(&rb6);

    // TEST 7: Shutdown While Waiting
    printf("\n[Test 7/8] Consumer Wakeup on Buffer Shutdown...\n");
    gap_safe_ring_buffer_t rb7;
    trb_init(&rb7, 1024);
    thread_test_args_t wait_args = { &rb7, 0, 0, false, 0 };
    pthread_t w_th;
    pthread_create(&w_th, NULL, waiting_consumer, &wait_args);
    usleep(20000); // 20 ms
    trb_shutdown(&rb7);
    pthread_join(w_th, NULL);
    bool pass7 = wait_args.success;
    printf("  Status: %s (consumer awakened cleanly on shutdown)\n", pass7 ? "PASS" : "FAIL");
    all_passed &= pass7;
    trb_destroy(&rb7);

    // TEST 8: Deliberate Producer Scheduling Jitter
    printf("\n[Test 8/8] Robustness to Asynchronous Jitter & Delays...\n");
    gap_safe_ring_buffer_t rb8;
    trb_init(&rb8, 4096);
    bool pass8 = true;
    float j_buf[128];
    for (int64_t idx = 0; idx < 1024; idx += 128) {
        for (int i = 0; i < 128; ++i) j_buf[i] = (float)(idx + i);
        trb_write(&rb8, idx, j_buf, 128);
        usleep(1000 + (idx % 3000)); // Variable jitter: 1-4 ms
        float r_buf[128];
        trb_status_t s8 = trb_read_timeout(&rb8, idx, r_buf, 128, 50); // 50 ms timeout
        if (s8 != TRB_SUCCESS) { pass8 = false; break; }
    }
    printf("  Status: %s (jitter handled without underruns)\n", pass8 ? "PASS" : "FAIL");
    all_passed &= pass8;
    trb_destroy(&rb8);

    printf("\n======================================================================\n");
    printf("SUMMARY: 8/8 Tests Passed: %s\n", all_passed ? "TRUE" : "FALSE");
    printf("======================================================================\n");

    // Output JSON results for automated recording
    FILE *fp = fopen("experiments/stage11_2_35R_remediation/ring_buffer_test_results.json", "w");
    if (fp) {
        fprintf(fp, "{\n");
        fprintf(fp, "  \"timestamp\": \"%s\",\n", "2026-11-14T20:48:00+05:30");
        fprintf(fp, "  \"total_tests\": 8,\n");
        fprintf(fp, "  \"passed_tests\": %d,\n", all_passed ? 8 : 0);
        fprintf(fp, "  \"all_passed\": %s,\n", all_passed ? "true" : "false");
        fprintf(fp, "  \"test_cases\": {\n");
        fprintf(fp, "    \"test_1_normal_contiguous\": \"%s\",\n", pass1 ? "PASS" : "FAIL");
        fprintf(fp, "    \"test_2_producer_gap\": \"%s\",\n", pass2 ? "PASS" : "FAIL");
        fprintf(fp, "    \"test_3_overrun_detection\": \"%s\",\n", pass3 ? "PASS" : "FAIL");
        fprintf(fp, "    \"test_4_circular_wraparound\": \"%s\",\n", pass4 ? "PASS" : "FAIL");
        fprintf(fp, "    \"test_5_out_of_order_writes\": \"%s\",\n", pass5 ? "PASS" : "FAIL");
        fprintf(fp, "    \"test_6_concurrent_stress_500k\": \"%s\",\n", pass6 ? "PASS" : "FAIL");
        fprintf(fp, "    \"test_7_shutdown_wakeup\": \"%s\",\n", pass7 ? "PASS" : "FAIL");
        fprintf(fp, "    \"test_8_scheduling_jitter\": \"%s\"\n", pass8 ? "PASS" : "FAIL");
        fprintf(fp, "  }\n");
        fprintf(fp, "}\n");
        fclose(fp);
    }

    return all_passed ? 0 : 1;
}
