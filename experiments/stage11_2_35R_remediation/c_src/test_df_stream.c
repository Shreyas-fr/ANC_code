#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <time.h>
#include <math.h>

typedef void DFState;

extern DFState* df_create(const char* path, float atten_lim, const char* log_level);
extern size_t df_get_frame_length(DFState* st);
extern float df_process_frame(DFState* st, float* input, float* output);
extern void df_free(DFState* st);

static double get_time_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1000000.0;
}

int main(int argc, char** argv) {
    const char* model_path = "models/dfn3_step500_tract.tar.gz";
    printf("Initializing DFN3 Tract model from %s...\n", model_path);

    double t0_init = get_time_ms();
    DFState* df = df_create(model_path, 100.0f, NULL);
    double t_init = get_time_ms() - t0_init;
    if (!df) {
        fprintf(stderr, "Failed to load DFN3 model!\n");
        return 1;
    }
    printf("DFN3 initialized in %.2f ms. Frame length: %zu samples\n", t_init, df_get_frame_length(df));

    // Warm-up with 10 frames of silence
    float frame_in[480] = {0};
    float frame_out[480] = {0};
    for (int i = 0; i < 10; ++i) {
        df_process_frame(df, frame_in, frame_out);
    }

    // Benchmark 300 consecutive frames (representing 3.0 seconds of audio at 48 kHz / 10 ms hop)
    const int N_FRAMES = 300;
    double latencies[300];
    double total_lat = 0.0;
    double max_lat = 0.0;
    double min_lat = 1e9;

    for (int i = 0; i < N_FRAMES; ++i) {
        // Feed synthetic speech-like harmonics
        for (int j = 0; j < 480; ++j) {
            frame_in[j] = 0.3f * sinf(2.0f * 3.14159f * 1000.0f * (float)(i * 480 + j) / 48000.0f);
        }
        double t0 = get_time_ms();
        df_process_frame(df, frame_in, frame_out);
        double dt = get_time_ms() - t0;
        latencies[i] = dt;
        total_lat += dt;
        if (dt > max_lat) max_lat = dt;
        if (dt < min_lat) min_lat = dt;
    }

    // Compute percentiles
    // Simple sort for percentiles
    for (int i = 0; i < N_FRAMES - 1; ++i) {
        for (int j = i + 1; j < N_FRAMES; ++j) {
            if (latencies[i] > latencies[j]) {
                double tmp = latencies[i];
                latencies[i] = latencies[j];
                latencies[j] = tmp;
            }
        }
    }

    double mean_lat = total_lat / N_FRAMES;
    double p50 = latencies[N_FRAMES / 2];
    double p95 = latencies[(int)(N_FRAMES * 0.95)];
    double p99 = latencies[(int)(N_FRAMES * 0.99)];

    printf("\n=== REAL DFN3 NATIVE TRACT INFERENCE BENCHMARK (300 FRAMES = 3.0s AUDIO) ===\n");
    printf("Mean Latency: %.3f ms/frame\n", mean_lat);
    printf("p50  Latency: %.3f ms/frame\n", p50);
    printf("p95  Latency: %.3f ms/frame\n", p95);
    printf("p99  Latency: %.3f ms/frame\n", p99);
    printf("Max  Latency: %.3f ms/frame\n", max_lat);
    printf("Min  Latency: %.3f ms/frame\n", min_lat);
    printf("Real-Time Factor (RTF at 10ms frame budget): %.4f (Headroom: %.1fx)\n",
           mean_lat / 10.0, 10.0 / mean_lat);
    printf("========================================================================\n");

    df_free(df);
    return 0;
}

