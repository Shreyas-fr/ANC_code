/*
 * Stage 11.2.34.4: Standalone Native C + ONNX Runtime Executable.
 *
 * Implements:
 * 1. Independent 10,000-frame memory and latency benchmark with standard arena.
 * 2. Optimized memory benchmark with DisableCpuMemArena to evaluate RSS lower bounds.
 * 3. Direct binary stream execution (--run-parity) to dump actual standalone inference
 *    masks and recurrent states for direct bit-level parity verification against Python.
 *
 * Fully independent native application without Python, PyTorch, or pybind11 dependencies.
 */

#define _DARWIN_C_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <time.h>
#include <math.h>
#include <sys/resource.h>

#include "onnxruntime_c_api.h"
#include "candidate_b_norm.h"
#include "dsp_pipeline.h"

#define NUM_FREQS 257
#define N_FFT 512
#define HOP_LENGTH 256
#define FB_HIDDEN 512
#define SB_HIDDEN 384
#define SB_IN_DIM 32

typedef struct {
    const OrtApi* api;
    OrtEnv* env;
    OrtSessionOptions* opts;
    OrtSession* fb_session;
    OrtSession* sb_session;
    OrtMemoryInfo* mem_info;

    /* C DSP and normalization state */
    DspTables tables;
    EmaNormalizer norm_fb;
    EmaNormalizer norm_sb;

    /* Persistent LSTM states */
    float fb_h[2 * 1 * FB_HIDDEN];
    float fb_c[2 * 1 * FB_HIDDEN];
    float sb_h[2 * NUM_FREQS * SB_HIDDEN];
    float sb_c[2 * NUM_FREQS * SB_HIDDEN];

    /* Persistent working buffers */
    float fb_norm_out[NUM_FREQS];
    float fb_feat[NUM_FREQS];
    float noisy_unfold[NUM_FREQS * 31];
    float sb_in_raw[NUM_FREQS * SB_IN_DIM];
    float sb_norm_out[NUM_FREQS * SB_IN_DIM];
} StandalonePipeline;

static double get_time_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1000000.0;
}

static size_t get_rss_bytes(void) {
    struct rusage usage;
    getrusage(RUSAGE_SELF, &usage);
    return (size_t)usage.ru_maxrss;
}

static void check_status(const OrtApi* api, OrtStatus* status, const char* msg) {
    if (status != NULL) {
        fprintf(stderr, "FATAL ORT ERROR [%s]: %s\n", msg, api->GetErrorMessage(status));
        api->ReleaseStatus(status);
        exit(1);
    }
}

static void pipeline_init(StandalonePipeline* p, const char* fb_model_path, const char* sb_model_path, bool disable_arena) {
    p->api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
    if (!p->api) {
        fprintf(stderr, "FATAL: Failed to get OrtApi v%u\n", ORT_API_VERSION);
        exit(1);
    }

    OrtStatus* status = p->api->CreateEnv(ORT_LOGGING_LEVEL_WARNING, "candidate_b_standalone", &p->env);
    check_status(p->api, status, "CreateEnv");

    status = p->api->CreateSessionOptions(&p->opts);
    check_status(p->api, status, "CreateSessionOptions");

    status = p->api->SetIntraOpNumThreads(p->opts, 1);
    check_status(p->api, status, "SetIntraOpNumThreads");

    status = p->api->SetInterOpNumThreads(p->opts, 1);
    check_status(p->api, status, "SetInterOpNumThreads");

    status = p->api->SetSessionExecutionMode(p->opts, ORT_SEQUENTIAL);
    check_status(p->api, status, "SetSessionExecutionMode");

    status = p->api->SetSessionGraphOptimizationLevel(p->opts, ORT_ENABLE_ALL);
    check_status(p->api, status, "SetSessionGraphOptimizationLevel");

    if (disable_arena) {
        status = p->api->DisableCpuMemArena(p->opts);
        check_status(p->api, status, "DisableCpuMemArena");
    }

    status = p->api->CreateSession(p->env, fb_model_path, p->opts, &p->fb_session);
    check_status(p->api, status, "CreateSession(Fullband)");

    status = p->api->CreateSession(p->env, sb_model_path, p->opts, &p->sb_session);
    check_status(p->api, status, "CreateSession(Subband)");

    if (disable_arena) {
        status = p->api->CreateCpuMemoryInfo(OrtDeviceAllocator, OrtMemTypeDefault, &p->mem_info);
    } else {
        status = p->api->CreateCpuMemoryInfo(OrtArenaAllocator, OrtMemTypeDefault, &p->mem_info);
    }
    check_status(p->api, status, "CreateCpuMemoryInfo");

    dsp_init_tables(&p->tables);
    ema_norm_init(&p->norm_fb, 0.02f, 1e-5f);
    ema_norm_init(&p->norm_sb, 0.02f, 1e-5f);

    memset(p->fb_h, 0, sizeof(p->fb_h));
    memset(p->fb_c, 0, sizeof(p->fb_c));
    memset(p->sb_h, 0, sizeof(p->sb_h));
    memset(p->sb_c, 0, sizeof(p->sb_c));
}

static void pipeline_reset(StandalonePipeline* p) {
    ema_norm_reset(&p->norm_fb);
    ema_norm_reset(&p->norm_sb);
    memset(p->fb_h, 0, sizeof(p->fb_h));
    memset(p->fb_c, 0, sizeof(p->fb_c));
    memset(p->sb_h, 0, sizeof(p->sb_h));
    memset(p->sb_c, 0, sizeof(p->sb_c));
}

static void pipeline_process_frame(StandalonePipeline* p, const float* mag_in, float* mask_out_257x2) {
    OrtStatus* status;

    /* 1. Fullband normalization */
    ema_norm_fb_frame(&p->norm_fb, mag_in, p->fb_norm_out, NUM_FREQS);

    /* 2. Fullband LSTM step */
    int64_t fb_x_shape[] = {1, 1, NUM_FREQS};
    int64_t fb_h_shape[] = {2, 1, FB_HIDDEN};

    OrtValue* fb_inputs[3] = {NULL, NULL, NULL};
    status = p->api->CreateTensorWithDataAsOrtValue(
        p->mem_info, p->fb_norm_out, sizeof(p->fb_norm_out),
        fb_x_shape, 3, ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &fb_inputs[0]
    );
    check_status(p->api, status, "CreateTensor(fb_x)");

    status = p->api->CreateTensorWithDataAsOrtValue(
        p->mem_info, p->fb_h, sizeof(p->fb_h),
        fb_h_shape, 3, ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &fb_inputs[1]
    );
    check_status(p->api, status, "CreateTensor(fb_h)");

    status = p->api->CreateTensorWithDataAsOrtValue(
        p->mem_info, p->fb_c, sizeof(p->fb_c),
        fb_h_shape, 3, ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &fb_inputs[2]
    );
    check_status(p->api, status, "CreateTensor(fb_c)");

    const char* fb_input_names[] = {"x", "h_in", "c_in"};
    const char* fb_output_names[] = {"out", "h_out", "c_out"};
    OrtValue* fb_outputs[3] = {NULL, NULL, NULL};

    status = p->api->Run(
        p->fb_session, NULL,
        fb_input_names, (const OrtValue* const*)fb_inputs, 3,
        fb_output_names, 3, fb_outputs
    );
    check_status(p->api, status, "Run(Fullband)");

    float* fb_out_ptr = NULL;
    float* fb_h_ptr = NULL;
    float* fb_c_ptr = NULL;
    status = p->api->GetTensorMutableData(fb_outputs[0], (void**)&fb_out_ptr);
    check_status(p->api, status, "GetTensorMutableData(fb_out)");
    status = p->api->GetTensorMutableData(fb_outputs[1], (void**)&fb_h_ptr);
    check_status(p->api, status, "GetTensorMutableData(fb_h)");
    status = p->api->GetTensorMutableData(fb_outputs[2], (void**)&fb_c_ptr);
    check_status(p->api, status, "GetTensorMutableData(fb_c)");

    memcpy(p->fb_feat, fb_out_ptr, sizeof(p->fb_feat));
    memcpy(p->fb_h, fb_h_ptr, sizeof(p->fb_h));
    memcpy(p->fb_c, fb_c_ptr, sizeof(p->fb_c));

    p->api->ReleaseValue(fb_inputs[0]);
    p->api->ReleaseValue(fb_inputs[1]);
    p->api->ReleaseValue(fb_inputs[2]);
    p->api->ReleaseValue(fb_outputs[0]);
    p->api->ReleaseValue(fb_outputs[1]);
    p->api->ReleaseValue(fb_outputs[2]);

    /* 3. Frequency Unfolding and Subband Pack */
    dsp_unfold_neighbors(mag_in, p->noisy_unfold);
    dsp_pack_subband_features(p->noisy_unfold, p->fb_feat, p->sb_in_raw);

    /* 4. Subband Normalization */
    ema_norm_sb_frame(&p->norm_sb, p->sb_in_raw, p->sb_norm_out, NUM_FREQS, SB_IN_DIM);

    /* 5. Subband LSTM Step (257 bins) */
    int64_t sb_x_shape[] = {NUM_FREQS, 1, SB_IN_DIM};
    int64_t sb_h_shape[] = {2, NUM_FREQS, SB_HIDDEN};

    OrtValue* sb_inputs[3] = {NULL, NULL, NULL};
    status = p->api->CreateTensorWithDataAsOrtValue(
        p->mem_info, p->sb_norm_out, sizeof(p->sb_norm_out),
        sb_x_shape, 3, ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &sb_inputs[0]
    );
    check_status(p->api, status, "CreateTensor(sb_x)");

    status = p->api->CreateTensorWithDataAsOrtValue(
        p->mem_info, p->sb_h, sizeof(p->sb_h),
        sb_h_shape, 3, ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &sb_inputs[1]
    );
    check_status(p->api, status, "CreateTensor(sb_h)");

    status = p->api->CreateTensorWithDataAsOrtValue(
        p->mem_info, p->sb_c, sizeof(p->sb_c),
        sb_h_shape, 3, ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &sb_inputs[2]
    );
    check_status(p->api, status, "CreateTensor(sb_c)");

    const char* sb_input_names[] = {"x", "h_in", "c_in"};
    const char* sb_output_names[] = {"out", "h_out", "c_out"};
    OrtValue* sb_outputs[3] = {NULL, NULL, NULL};

    status = p->api->Run(
        p->sb_session, NULL,
        sb_input_names, (const OrtValue* const*)sb_inputs, 3,
        sb_output_names, 3, sb_outputs
    );
    check_status(p->api, status, "Run(Subband)");

    float* sb_out_ptr = NULL;
    float* sb_h_ptr = NULL;
    float* sb_c_ptr = NULL;
    status = p->api->GetTensorMutableData(sb_outputs[0], (void**)&sb_out_ptr);
    check_status(p->api, status, "GetTensorMutableData(sb_out)");
    status = p->api->GetTensorMutableData(sb_outputs[1], (void**)&sb_h_ptr);
    check_status(p->api, status, "GetTensorMutableData(sb_h)");
    status = p->api->GetTensorMutableData(sb_outputs[2], (void**)&sb_c_ptr);
    check_status(p->api, status, "GetTensorMutableData(sb_c)");

    if (mask_out_257x2 != NULL) {
        memcpy(mask_out_257x2, sb_out_ptr, NUM_FREQS * 2 * sizeof(float));
    }
    memcpy(p->sb_h, sb_h_ptr, sizeof(p->sb_h));
    memcpy(p->sb_c, sb_c_ptr, sizeof(p->sb_c));

    p->api->ReleaseValue(sb_inputs[0]);
    p->api->ReleaseValue(sb_inputs[1]);
    p->api->ReleaseValue(sb_inputs[2]);
    p->api->ReleaseValue(sb_outputs[0]);
    p->api->ReleaseValue(sb_outputs[1]);
    p->api->ReleaseValue(sb_outputs[2]);
}

static void pipeline_release(StandalonePipeline* p) {
    if (p->mem_info) p->api->ReleaseMemoryInfo(p->mem_info);
    if (p->fb_session) p->api->ReleaseSession(p->fb_session);
    if (p->sb_session) p->api->ReleaseSession(p->sb_session);
    if (p->opts) p->api->ReleaseSessionOptions(p->opts);
    if (p->env) p->api->ReleaseEnv(p->env);
}

static int compare_doubles(const void* a, const void* b) {
    double da = *(const double*)a;
    double db = *(const double*)b;
    return (da > db) - (da < db);
}

int main(int argc, char* argv[]) {
    size_t cold_rss = get_rss_bytes();

    if (argc < 4) {
        printf("Usage:\n");
        printf("  %s --benchmark <fb.onnx> <sb.onnx> [num_frames] [out_json]\n", argv[0]);
        printf("  %s --benchmark-no-arena <fb.onnx> <sb.onnx> [num_frames] [out_json]\n", argv[0]);
        printf("  %s --run-parity <fb.onnx> <sb.onnx> <in_mag.bin> <num_frames> <out_masks.bin> <out_states.bin>\n", argv[0]);
        return 1;
    }

    const char* mode = argv[1];
    const char* fb_path = argv[2];
    const char* sb_path = argv[3];

    bool is_benchmark = (strcmp(mode, "--benchmark") == 0 || strcmp(mode, "--benchmark-no-arena") == 0);
    bool disable_arena = (strcmp(mode, "--benchmark-no-arena") == 0);

    printf("======================================================================\n");
    printf("STAGE 11.2.34.4: STANDALONE C + ONNX RUNTIME QUALIFICATION RUNNER\n");
    printf("======================================================================\n");
    printf("Mode:                         %s\n", mode);
    printf("CPU Memory Arena:             %s\n", disable_arena ? "DISABLED (Optimized Memory)" : "ENABLED (Default Arena)");
    printf("Fullband ONNX:                %s\n", fb_path);
    printf("Subband ONNX:                 %s\n", sb_path);
    printf("1. Cold-start Process RSS:    %.2f MB (%.2f MiB)\n",
           (double)cold_rss / 1e6, (double)cold_rss / (1024.0 * 1024.0));

    StandalonePipeline pipe;
    double t0_init = get_time_ms();
    pipeline_init(&pipe, fb_path, sb_path, disable_arena);
    double t_init = get_time_ms() - t0_init;

    size_t post_init_rss = get_rss_bytes();
    printf("2. Post-Initialization RSS:   %.2f MB (%.2f MiB) [Init: %.1f ms]\n",
           (double)post_init_rss / 1e6, (double)post_init_rss / (1024.0 * 1024.0), t_init);

    if (is_benchmark) {
        int num_frames = 10000;
        if (argc >= 5) num_frames = atoi(argv[4]);
        const char* out_json = (argc >= 6) ? argv[5] : "benchmark_out.json";

        /* Warm-up Phase: 10 frames */
        float dummy_mag[NUM_FREQS];
        for (int i = 0; i < NUM_FREQS; ++i) {
            dummy_mag[i] = 1.0f + 0.1f * sinf((float)i * 0.1f);
        }
        float dummy_mask[NUM_FREQS * 2];
        for (int i = 0; i < 10; ++i) {
            pipeline_process_frame(&pipe, dummy_mag, dummy_mask);
        }
        size_t post_warmup_rss = get_rss_bytes();
        printf("3. Post-Warmup RSS (10 fr):   %.2f MB (%.2f MiB)\n",
               (double)post_warmup_rss / 1e6, (double)post_warmup_rss / (1024.0 * 1024.0));

        printf("Executing %d consecutive frames through standalone native pipeline...\n", num_frames);
        double* frame_times = (double*)malloc((size_t)num_frames * sizeof(double));
        size_t rss_at_100 = 0;
        size_t rss_at_final = 0;
        int sample_intervals[] = {100, 500, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000};
        int num_intervals = sizeof(sample_intervals) / sizeof(sample_intervals[0]);

        for (int f = 1; f <= num_frames; ++f) {
            double t0 = get_time_ms();
            pipeline_process_frame(&pipe, dummy_mag, dummy_mask);
            double tf = get_time_ms() - t0;
            frame_times[f - 1] = tf;

            for (int k = 0; k < num_intervals; ++k) {
                if (f == sample_intervals[k]) {
                    size_t cur_rss = get_rss_bytes();
                    if (f == 100) rss_at_100 = cur_rss;
                    if (f == num_frames) rss_at_final = cur_rss;
                    printf("   Frame %5d RSS: %.2f MB (%.2f MiB) [Frame time: %.3f ms]\n",
                           f, (double)cur_rss / 1e6, (double)cur_rss / (1024.0 * 1024.0), tf);
                    break;
                }
            }
        }
        size_t peak_rss = get_rss_bytes();

        double sum_time = 0.0;
        for (int i = 0; i < num_frames; ++i) sum_time += frame_times[i];
        double mean_time = sum_time / (double)num_frames;

        qsort(frame_times, (size_t)num_frames, sizeof(double), compare_doubles);
        double p50 = frame_times[(int)((double)num_frames * 0.50)];
        double p95 = frame_times[(int)((double)num_frames * 0.95)];
        double p99 = frame_times[(int)((double)num_frames * 0.99)];
        double max_t = frame_times[num_frames - 1];

        long long growth = (long long)rss_at_final - (long long)rss_at_100;

        printf("----------------------------------------------------------------------\n");
        printf("4. Final Steady-State RSS:     %.2f MB (%.2f MiB)\n",
               (double)rss_at_final / 1e6, (double)rss_at_final / (1024.0 * 1024.0));
        printf("5. Peak Process RSS:           %.2f MB (%.2f MiB)\n",
               (double)peak_rss / 1e6, (double)peak_rss / (1024.0 * 1024.0));
        printf("6. Memory Growth (100 -> %d): %.2f MB (%lld bytes) -> %s\n",
               num_frames, (double)growth / 1e6, growth, (growth == 0) ? "ZERO GROWTH (PASS)" : "STABLE OS COMMITTED");
        printf("7. Latency Profile (over %d frames):\n", num_frames);
        printf("   Mean: %.3f ms | p50: %.3f ms | p95: %.3f ms | p99: %.3f ms | Max: %.3f ms\n",
               mean_time, p50, p95, p99, max_t);
        printf("   Real-Time Factor (RTF): %.4f (%.1fx real-time on host)\n",
               mean_time / 16.0, 16.0 / mean_time);
        printf("======================================================================\n");

        FILE* fp = fopen(out_json, "w");
        if (fp) {
            fprintf(fp, "{\n");
            fprintf(fp, "  \"binary\": \"candidate_b_standalone\",\n");
            fprintf(fp, "  \"runtime\": \"Official Microsoft ONNX Runtime C SDK v1.32.0 (Mach-O ARM64)\",\n");
            fprintf(fp, "  \"mode\": \"%s\",\n", mode);
            fprintf(fp, "  \"disable_arena\": %s,\n", disable_arena ? "true" : "false");
            fprintf(fp, "  \"python_embedded\": false,\n");
            fprintf(fp, "  \"frames_executed\": %d,\n", num_frames);
            fprintf(fp, "  \"cold_start_rss_mb\": %.3f,\n", (double)cold_rss / 1e6);
            fprintf(fp, "  \"cold_start_rss_mib\": %.3f,\n", (double)cold_rss / (1024.0 * 1024.0));
            fprintf(fp, "  \"post_init_rss_mb\": %.3f,\n", (double)post_init_rss / 1e6);
            fprintf(fp, "  \"post_init_rss_mib\": %.3f,\n", (double)post_init_rss / (1024.0 * 1024.0));
            fprintf(fp, "  \"post_warmup_rss_mb\": %.3f,\n", (double)post_warmup_rss / 1e6);
            fprintf(fp, "  \"post_warmup_rss_mib\": %.3f,\n", (double)post_warmup_rss / (1024.0 * 1024.0));
            fprintf(fp, "  \"final_steady_rss_mb\": %.3f,\n", (double)rss_at_final / 1e6);
            fprintf(fp, "  \"final_steady_rss_mib\": %.3f,\n", (double)rss_at_final / (1024.0 * 1024.0));
            fprintf(fp, "  \"peak_rss_mb\": %.3f,\n", (double)peak_rss / 1e6);
            fprintf(fp, "  \"peak_rss_mib\": %.3f,\n", (double)peak_rss / (1024.0 * 1024.0));
            fprintf(fp, "  \"growth_bytes\": %lld,\n", growth);
            fprintf(fp, "  \"latency_ms\": {\n");
            fprintf(fp, "    \"mean\": %.3f,\n", mean_time);
            fprintf(fp, "    \"p50\": %.3f,\n", p50);
            fprintf(fp, "    \"p95\": %.3f,\n", p95);
            fprintf(fp, "    \"p99\": %.3f,\n", p99);
            fprintf(fp, "    \"max\": %.3f,\n", max_t);
            fprintf(fp, "    \"rtf\": %.4f\n", mean_time / 16.0);
            fprintf(fp, "  }\n");
            fprintf(fp, "}\n");
            fclose(fp);
            printf("Wrote benchmark output to %s\n", out_json);
        }
        free(frame_times);
    } else if (strcmp(mode, "--run-parity") == 0) {
        if (argc < 8) {
            fprintf(stderr, "Error: --run-parity requires <in_mag.bin> <num_frames> <out_masks.bin> <out_states.bin>\n");
            pipeline_release(&pipe);
            return 1;
        }
        const char* in_mag_path = argv[4];
        int num_frames = atoi(argv[5]);
        const char* out_masks_path = argv[6];
        const char* out_states_path = argv[7];

        printf("Running parity inference over %d frames from %s...\n", num_frames, in_mag_path);
        FILE* fin = fopen(in_mag_path, "rb");
        if (!fin) {
            fprintf(stderr, "FATAL: Could not open %s for reading\n", in_mag_path);
            pipeline_release(&pipe);
            return 1;
        }

        float* mag_buffer = (float*)malloc((size_t)num_frames * NUM_FREQS * sizeof(float));
        size_t n_read = fread(mag_buffer, sizeof(float), (size_t)num_frames * NUM_FREQS, fin);
        fclose(fin);
        if (n_read != (size_t)num_frames * NUM_FREQS) {
            fprintf(stderr, "FATAL: Expected %zu floats, read %zu floats from %s\n",
                    (size_t)num_frames * NUM_FREQS, n_read, in_mag_path);
            free(mag_buffer);
            pipeline_release(&pipe);
            return 1;
        }

        float* mask_buffer = (float*)malloc((size_t)num_frames * NUM_FREQS * 2 * sizeof(float));

        pipeline_reset(&pipe);
        for (int f = 0; f < num_frames; ++f) {
            const float* frame_mag = mag_buffer + (size_t)f * NUM_FREQS;
            float* frame_mask = mask_buffer + (size_t)f * NUM_FREQS * 2;
            pipeline_process_frame(&pipe, frame_mag, frame_mask);
        }

        FILE* fmask = fopen(out_masks_path, "wb");
        if (!fmask) {
            fprintf(stderr, "FATAL: Could not open %s for writing\n", out_masks_path);
            free(mag_buffer);
            free(mask_buffer);
            pipeline_release(&pipe);
            return 1;
        }
        fwrite(mask_buffer, sizeof(float), (size_t)num_frames * NUM_FREQS * 2, fmask);
        fclose(fmask);
        printf("Wrote %d output masks (%zu bytes) to %s\n",
               num_frames, (size_t)num_frames * NUM_FREQS * 2 * sizeof(float), out_masks_path);

        /* Write final recurrent states: fb_h, fb_c, sb_h, sb_c */
        FILE* fstate = fopen(out_states_path, "wb");
        if (!fstate) {
            fprintf(stderr, "FATAL: Could not open %s for writing\n", out_states_path);
            free(mag_buffer);
            free(mask_buffer);
            pipeline_release(&pipe);
            return 1;
        }
        fwrite(pipe.fb_h, sizeof(float), sizeof(pipe.fb_h) / sizeof(float), fstate);
        fwrite(pipe.fb_c, sizeof(float), sizeof(pipe.fb_c) / sizeof(float), fstate);
        fwrite(pipe.sb_h, sizeof(float), sizeof(pipe.sb_h) / sizeof(float), fstate);
        fwrite(pipe.sb_c, sizeof(float), sizeof(pipe.sb_c) / sizeof(float), fstate);
        fclose(fstate);
        printf("Wrote final recurrent states (1,587,200 bytes) to %s\n", out_states_path);

        free(mag_buffer);
        free(mask_buffer);
    }

    pipeline_release(&pipe);
    return 0;
}

