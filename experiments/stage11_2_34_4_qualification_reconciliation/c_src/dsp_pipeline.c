#include "dsp_pipeline.h"
#include <math.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

void dsp_init_tables(DspTables *tables) {
    if (!tables) return;

    /* 1. Precompute periodic 512-point Hann window */
    for (int n = 0; n < DSP_N_FFT; ++n) {
        tables->hann_window[n] = 0.5f * (1.0f - cosf((float)(2.0 * M_PI * (double)n / (double)DSP_N_FFT)));
    }

    /* 2. Overlap-add denominator for 50% hop (256 samples) */
    for (int n = 0; n < DSP_HOP_SIZE; ++n) {
        float w1 = tables->hann_window[n];
        float w2 = tables->hann_window[n + DSP_HOP_SIZE];
        tables->ola_denom[n] = (w1 * w1) + (w2 * w2);
    }

    /* 3. Bit-reversal permutation (9 bits for 512) */
    for (int i = 0; i < DSP_N_FFT; ++i) {
        uint16_t r = 0;
        for (int j = 0; j < 9; ++j) {
            if (i & (1 << j)) {
                r |= (1 << (8 - j));
            }
        }
        tables->bit_rev[i] = r;
    }

    /* 4. Twiddle factors for forward FFT */
    for (int k = 0; k < DSP_N_FFT / 2; ++k) {
        double angle = -2.0 * M_PI * (double)k / (double)DSP_N_FFT;
        tables->twiddle_r[k] = (float)cos(angle);
        tables->twiddle_i[k] = (float)sin(angle);
    }

    tables->initialized = true;
}

static void fft_core(const DspTables *tables, float *xr, float *xi) {
    int step = 2;
    while (step <= DSP_N_FFT) {
        int half = step / 2;
        int factor = DSP_N_FFT / step;
        for (int k = 0; k < DSP_N_FFT; k += step) {
            for (int j = 0; j < half; ++j) {
                float tw_r = tables->twiddle_r[j * factor];
                float tw_i = tables->twiddle_i[j * factor];
                float tr = tw_r * xr[k + j + half] - tw_i * xi[k + j + half];
                float ti = tw_r * xi[k + j + half] + tw_i * xr[k + j + half];
                xr[k + j + half] = xr[k + j] - tr;
                xi[k + j + half] = xi[k + j] - ti;
                xr[k + j] += tr;
                xi[k + j] += ti;
            }
        }
        step *= 2;
    }
}

void dsp_fft512(const DspTables *tables, const float *in_real, float *out_real, float *out_imag) {
    if (!tables || !in_real || !out_real || !out_imag) return;

    /* Bit-reversal permutation */
    for (int i = 0; i < DSP_N_FFT; ++i) {
        uint16_t rev = tables->bit_rev[i];
        out_real[i] = in_real[rev];
        out_imag[i] = 0.0f;
    }

    fft_core(tables, out_real, out_imag);
}

void dsp_ifft512(const DspTables *tables, const float *in_real, const float *in_imag, float *out_real) {
    if (!tables || !in_real || !in_imag || !out_real) return;

    float xr[DSP_N_FFT];
    float xi[DSP_N_FFT];

    /* Reconstruct 512-point conjugate symmetric spectrum */
    xr[0] = in_real[0];
    xi[0] = 0.0f;
    xr[256] = in_real[256];
    xi[256] = 0.0f;

    for (int k = 1; k < 256; ++k) {
        xr[k] = in_real[k];
        xi[k] = -in_imag[k]; /* Conjugate for inverse FFT */
        xr[512 - k] = in_real[k];
        xi[512 - k] = in_imag[k]; /* Conjugate of conj is +imag */
    }

    /* Bit-reversal permutation into working buffers */
    float wr[DSP_N_FFT];
    float wi[DSP_N_FFT];
    for (int i = 0; i < DSP_N_FFT; ++i) {
        uint16_t rev = tables->bit_rev[i];
        wr[i] = xr[rev];
        wi[i] = xi[rev];
    }

    fft_core(tables, wr, wi);

    /* Conjugate and scale by 1 / 512 */
    float inv_n = 1.0f / (float)DSP_N_FFT;
    for (int i = 0; i < DSP_N_FFT; ++i) {
        out_real[i] = wr[i] * inv_n;
    }
}

void dsp_unfold_neighbors(const float *mag_in, float *unfold_out) {
    if (!mag_in || !unfold_out) return;

    const int num_freqs = DSP_NUM_FREQS;
    const int num_neighbors = DSP_SB_NEIGHBORS;
    const int unit_size = num_neighbors * 2 + 1; /* 31 */

    for (int f = 0; f < num_freqs; ++f) {
        float *dest = &unfold_out[f * unit_size];
        for (int k = -num_neighbors; k <= num_neighbors; ++k) {
            int idx = f + k;
            if (idx < 0) {
                idx = -idx;
            } else if (idx >= num_freqs) {
                idx = 2 * (num_freqs - 1) - idx;
            }
            dest[k + num_neighbors] = mag_in[idx];
        }
    }
}

void dsp_pack_subband_features(const float *unfold_noisy, const float *fb_out, float *sb_in) {
    if (!unfold_noisy || !fb_out || !sb_in) return;

    for (int f = 0; f < DSP_NUM_FREQS; ++f) {
        const float *src_noisy = &unfold_noisy[f * 31];
        float *dest = &sb_in[f * DSP_SB_FEATURES];

        /* Copy 31 noisy neighbors */
        memcpy(dest, src_noisy, 31 * sizeof(float));

        /* Append 1 fullband feature */
        dest[31] = fb_out[f];
    }
}

void dsp_decompress_cirm(const float *compressed_mask, float *cirm_real, float *cirm_imag, float K, float limit) {
    if (!compressed_mask || !cirm_real || !cirm_imag) return;

    for (int f = 0; f < DSP_NUM_FREQS; ++f) {
        float mr = compressed_mask[f * 2 + 0];
        float mi = compressed_mask[f * 2 + 1];

        /* Clip to [-limit, +limit] */
        if (mr > limit) mr = limit;
        else if (mr < -limit) mr = -limit;

        if (mi > limit) mi = limit;
        else if (mi < -limit) mi = -limit;

        /* Decompress: -K * log((K - m) / (K + m)) = K * log((K + m) / (K - m)) */
        cirm_real[f] = -K * logf((K - mr) / (K + mr));
        cirm_imag[f] = -K * logf((K - mi) / (K + mi));
    }
}

void dsp_apply_cirm_mask(
    const float *noisy_real,
    const float *noisy_imag,
    const float *cirm_real,
    const float *cirm_imag,
    float *enh_real,
    float *enh_imag
) {
    if (!noisy_real || !noisy_imag || !cirm_real || !cirm_imag || !enh_real || !enh_imag) return;

    for (int f = 0; f < DSP_NUM_FREQS; ++f) {
        float yr = noisy_real[f];
        float yi = noisy_imag[f];
        float mr = cirm_real[f];
        float mi = cirm_imag[f];

        enh_real[f] = (mr * yr) - (mi * yi);
        enh_imag[f] = (mr * yi) + (mi * yr);
    }
}

