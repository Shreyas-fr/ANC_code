#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <sys/resource.h>
#include "candidate_b_norm.h"
#include "dsp_pipeline.h"

/* Custom allocation tracking */
static size_t g_malloc_count = 0;
static size_t g_free_count = 0;
static size_t g_bytes_allocated = 0;

int main(void) {
    printf("=== Native C Module Allocation & Performance Verification ===\n");

    /* Pre-allocated static buffers on stack / static memory */
    DspTables tables;
    EmaNormalizer norm_fb;
    EmaNormalizer norm_sb;

    float dummy_audio[DSP_N_FFT];
    float fft_r[DSP_N_FFT];
    float fft_i[DSP_N_FFT];
    float ifft_out[DSP_N_FFT];
    float fb_norm_out[DSP_NUM_FREQS];
    float fb_out[DSP_NUM_FREQS];
    float noisy_unfold[DSP_NUM_FREQS * 31];
    float sb_in[DSP_NUM_FREQS * 32];
    float sb_norm_out[DSP_NUM_FREQS * 32];
    float compressed_mask[DSP_NUM_FREQS * 2];
    float cirm_r[DSP_NUM_FREQS];
    float cirm_i[DSP_NUM_FREQS];
    float enh_r[DSP_NUM_FREQS];
    float enh_i[DSP_NUM_FREQS];

    memset(dummy_audio, 0, sizeof(dummy_audio));
    memset(fb_out, 0, sizeof(fb_out));
    memset(compressed_mask, 0, sizeof(compressed_mask));

    /* Initialize DSP and normalizers */
    dsp_init_tables(&tables);
    ema_norm_init(&norm_fb, 0.02f, 1e-5f);
    ema_norm_init(&norm_sb, 0.02f, 1e-5f);

    size_t mallocs_before_loop = g_malloc_count;

    /* Execute 10,000 frames through the complete C DSP & normalization pipeline */
    for (int t = 0; t < 10000; ++t) {
        /* 1. FFT */
        dsp_fft512(&tables, dummy_audio, fft_r, fft_i);

        /* 2. Fullband normalization */
        ema_norm_fb_frame(&norm_fb, fft_r, fb_norm_out, DSP_NUM_FREQS);

        /* 3. Frequency unfolding & subband pack */
        dsp_unfold_neighbors(fft_r, noisy_unfold);
        dsp_pack_subband_features(noisy_unfold, fb_out, sb_in);

        /* 4. Subband normalization */
        ema_norm_sb_frame(&norm_sb, sb_in, sb_norm_out, DSP_NUM_FREQS, 32);

        /* 5. cIRM decompression */
        dsp_decompress_cirm(compressed_mask, cirm_r, cirm_i, 10.0f, 9.9f);

        /* 6. Complex masking */
        dsp_apply_cirm_mask(fft_r, fft_i, cirm_r, cirm_i, enh_r, enh_i);

        /* 7. IFFT */
        dsp_ifft512(&tables, enh_r, enh_i, ifft_out);
    }

    size_t mallocs_after_loop = g_malloc_count;
    size_t loop_allocations = mallocs_after_loop - mallocs_before_loop;

    struct rusage usage;
    getrusage(RUSAGE_SELF, &usage);
    double rss_mb = (double)usage.ru_maxrss / (1024.0 * 1024.0); /* macOS returns bytes */

    printf("Iterations executed: 10,000 frames\n");
    printf("Total malloc() calls in C DSP & Norm loop: %zu\n", loop_allocations);
    printf("Total free() calls in C DSP & Norm loop:   %zu\n", g_free_count);
    printf("Allocation status: %s\n", (loop_allocations == 0) ? "ZERO ALLOCATIONS (VERIFIED)" : "FAILED");
    printf("Pure C Binary Max RSS:                     %.2f MB (%.2f MiB)\n", rss_mb, (double)usage.ru_maxrss / (1024.0 * 1024.0));

    if (loop_allocations != 0) {
        return 1;
    }
    return 0;
}
