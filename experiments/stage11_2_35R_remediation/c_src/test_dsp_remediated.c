#include "dsp_remediated.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

typedef struct {
    double sdr_db;
    double rmse;
    double max_err;
    bool pass;
} dsp_test_result_t;

dsp_test_result_t evaluate_reconstruction(const float *orig, const float *recon, int num_samples) {
    dsp_test_result_t res;
    double sum_sq_orig = 0.0;
    double sum_sq_err = 0.0;
    double max_e = 0.0;

    for (int i = 0; i < num_samples; ++i) {
        double diff = (double)recon[i] - (double)orig[i];
        sum_sq_orig += (double)orig[i] * (double)orig[i];
        sum_sq_err += diff * diff;
        if (fabs(diff) > max_e) max_e = fabs(diff);
    }

    res.rmse = sqrt(sum_sq_err / (double)num_samples);
    res.max_err = max_e;
    res.sdr_db = 10.0 * log10((sum_sq_orig + 1e-12) / (sum_sq_err + 1e-12));
    res.pass = (res.sdr_db >= 100.0) && (res.max_err < 1e-4);
    return res;
}

// Test streaming STFT + iSTFT reconstruction with exact OLA
dsp_test_result_t test_signal_ola(DspTables *tables, const float *signal, int num_samples, bool use_gtcrn) {
    const int pad = DSP_N_FFT / 2; // 256 samples reflection padding
    int padded_len = num_samples + 2 * pad;
    float *padded = (float *)calloc(padded_len, sizeof(float));

    // Centered reflection padding
    for (int i = 0; i < pad; ++i) {
        padded[pad - 1 - i] = signal[i + 1];
    }
    memcpy(padded + pad, signal, num_samples * sizeof(float));
    for (int i = 0; i < pad; ++i) {
        int idx = num_samples - 2 - i;
        padded[pad + num_samples + i] = (idx >= 0) ? signal[idx] : 0.0f;
    }

    int num_frames = (padded_len - DSP_N_FFT) / DSP_HOP_SIZE + 1;

    DspOlaStream ola;
    dsp_ola_init(&ola);

    const float *synth_win = use_gtcrn ? tables->sqrt_hann_window : tables->hann_window;

    float *emitted = (float *)calloc((num_frames + 1) * DSP_HOP_SIZE, sizeof(float));
    int emit_ptr = 0;

    for (int t = 0; t < num_frames; ++t) {
        float in_frame[DSP_N_FFT];
        memcpy(in_frame, padded + t * DSP_HOP_SIZE, DSP_N_FFT * sizeof(float));

        float r257[DSP_NUM_FREQS];
        float i257[DSP_NUM_FREQS];
        float out_frame[DSP_N_FFT];

        if (use_gtcrn) {
            dsp_gtcrn_stft_frame(tables, in_frame, r257, i257);
            dsp_gtcrn_istft_frame(tables, r257, i257, out_frame);
        } else {
            dsp_fullsubnet_stft_frame(tables, in_frame, r257, i257);
            dsp_fullsubnet_istft_frame(tables, r257, i257, out_frame);
        }

        dsp_ola_add_frame(&ola, out_frame, synth_win, t);
        dsp_ola_emit_chunk(&ola, emitted + emit_ptr, t);
        emit_ptr += DSP_HOP_SIZE;
    }

    // Final flush
    dsp_ola_flush_chunk(&ola, emitted + emit_ptr, num_frames);
    emit_ptr += DSP_HOP_SIZE;

    // Slice to [pad : pad + num_samples]
    float *reconstructed = emitted + pad;
    dsp_test_result_t res = evaluate_reconstruction(signal, reconstructed, num_samples);

    free(padded);
    free(emitted);
    return res;
}

int main(int argc, char **argv) {
    printf("======================================================================\n");
    printf("STAGE 11.2.35R AUDIT: DSP & OVERLAP-ADD NORMALIZATION BENCHMARK\n");
    printf("======================================================================\n\n");

    DspTables tables;
    dsp_init_tables(&tables);

    const int L = 48000; // 3 seconds at 16 kHz
    float *sig_impulse  = (float *)calloc(L, sizeof(float));
    float *sig_constant = (float *)calloc(L, sizeof(float));
    float *sig_sine     = (float *)calloc(L, sizeof(float));
    float *sig_random   = (float *)calloc(L, sizeof(float));

    // 1. Impulse train (impulses at samples 100, 5000, 24000, 47900)
    sig_impulse[100] = 1.0f;
    sig_impulse[5000] = 1.0f;
    sig_impulse[24000] = 1.0f;
    sig_impulse[47900] = 1.0f;

    // 2. Constant (DC = 1.0)
    for (int i = 0; i < L; ++i) sig_constant[i] = 1.0f;

    // 3. 1 kHz Sinusoid
    for (int i = 0; i < L; ++i) {
        sig_sine[i] = sinf((float)(2.0 * M_PI * 1000.0 * (double)i / 16000.0));
    }

    // 4. Random noise (deterministic pseudo-random)
    srand(42);
    for (int i = 0; i < L; ++i) {
        sig_random[i] = ((float)rand() / (float)RAND_MAX) * 2.0f - 1.0f;
    }

    printf("--- PART A: FullSubNet Hann Window STFT / iSTFT / OLA ---\n");
    dsp_test_result_t r_fs_imp = test_signal_ola(&tables, sig_impulse, L, false);
    printf("  Impulse Test:   SDR = %7.2f dB | RMSE = %9.2e | MaxErr = %9.2e | %s\n",
           r_fs_imp.sdr_db, r_fs_imp.rmse, r_fs_imp.max_err, r_fs_imp.pass ? "PASS" : "FAIL");

    dsp_test_result_t r_fs_const = test_signal_ola(&tables, sig_constant, L, false);
    printf("  Constant DC:    SDR = %7.2f dB | RMSE = %9.2e | MaxErr = %9.2e | %s\n",
           r_fs_const.sdr_db, r_fs_const.rmse, r_fs_const.max_err, r_fs_const.pass ? "PASS" : "FAIL");

    dsp_test_result_t r_fs_sine = test_signal_ola(&tables, sig_sine, L, false);
    printf("  1 kHz Sinusoid: SDR = %7.2f dB | RMSE = %9.2e | MaxErr = %9.2e | %s\n",
           r_fs_sine.sdr_db, r_fs_sine.rmse, r_fs_sine.max_err, r_fs_sine.pass ? "PASS" : "FAIL");

    dsp_test_result_t r_fs_rand = test_signal_ola(&tables, sig_random, L, false);
    printf("  Random Noise:   SDR = %7.2f dB | RMSE = %9.2e | MaxErr = %9.2e | %s\n",
           r_fs_rand.sdr_db, r_fs_rand.rmse, r_fs_rand.max_err, r_fs_rand.pass ? "PASS" : "FAIL");

    printf("\n--- PART B: GTCRN Sqrt-Hann Window STFT / iSTFT / OLA ---\n");
    dsp_test_result_t r_gt_imp = test_signal_ola(&tables, sig_impulse, L, true);
    printf("  Impulse Test:   SDR = %7.2f dB | RMSE = %9.2e | MaxErr = %9.2e | %s\n",
           r_gt_imp.sdr_db, r_gt_imp.rmse, r_gt_imp.max_err, r_gt_imp.pass ? "PASS" : "FAIL");

    dsp_test_result_t r_gt_const = test_signal_ola(&tables, sig_constant, L, true);
    printf("  Constant DC:    SDR = %7.2f dB | RMSE = %9.2e | MaxErr = %9.2e | %s\n",
           r_gt_const.sdr_db, r_gt_const.rmse, r_gt_const.max_err, r_gt_const.pass ? "PASS" : "FAIL");

    dsp_test_result_t r_gt_sine = test_signal_ola(&tables, sig_sine, L, true);
    printf("  1 kHz Sinusoid: SDR = %7.2f dB | RMSE = %9.2e | MaxErr = %9.2e | %s\n",
           r_gt_sine.sdr_db, r_gt_sine.rmse, r_gt_sine.max_err, r_gt_sine.pass ? "PASS" : "FAIL");

    dsp_test_result_t r_gt_rand = test_signal_ola(&tables, sig_random, L, true);
    printf("  Random Noise:   SDR = %7.2f dB | RMSE = %9.2e | MaxErr = %9.2e | %s\n",
           r_gt_rand.sdr_db, r_gt_rand.rmse, r_gt_rand.max_err, r_gt_rand.pass ? "PASS" : "FAIL");

    bool all_dsp_pass = r_fs_imp.pass && r_fs_const.pass && r_fs_sine.pass && r_fs_rand.pass &&
                         r_gt_imp.pass && r_gt_const.pass && r_gt_sine.pass && r_gt_rand.pass;

    printf("\n======================================================================\n");
    printf("DSP OVERLAP-ADD RECONSTRUCTION RESULT: %s\n", all_dsp_pass ? "ALL PASSED" : "FAILED");
    printf("======================================================================\n");

    free(sig_impulse);
    free(sig_constant);
    free(sig_sine);
    free(sig_random);
    return all_dsp_pass ? 0 : 1;
}

