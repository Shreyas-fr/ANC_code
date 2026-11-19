#include "dsp_remediated.h"
#include <math.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

void dsp_init_tables(DspTables *tables) {
    if (!tables) return;

    for (int n = 0; n < DSP_N_FFT; ++n) {
        float w = 0.5f * (1.0f - cosf((float)(2.0 * M_PI * (double)n / (double)DSP_N_FFT)));
        tables->hann_window[n] = w;
        tables->sqrt_hann_window[n] = sqrtf(w);
    }

    for (int i = 0; i < DSP_N_FFT; ++i) {
        uint16_t r = 0;
        for (int j = 0; j < 9; ++j) {
            if (i & (1 << j)) {
                r |= (1 << (8 - j));
            }
        }
        tables->bit_rev[i] = r;
    }

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

    xr[0] = in_real[0];
    xi[0] = 0.0f;
    xr[256] = in_real[256];
    xi[256] = 0.0f;

    for (int k = 1; k < 256; ++k) {
        xr[k] = in_real[k];
        xi[k] = -in_imag[k];
        xr[512 - k] = in_real[k];
        xi[512 - k] = in_imag[k];
    }

    float wr[DSP_N_FFT];
    float wi[DSP_N_FFT];

    for (int i = 0; i < DSP_N_FFT; ++i) {
        uint16_t rev = tables->bit_rev[i];
        wr[i] = xr[rev];
        wi[i] = xi[rev];
    }

    fft_core(tables, wr, wi);

    float inv_n = 1.0f / (float)DSP_N_FFT;
    for (int i = 0; i < DSP_N_FFT; ++i) {
        out_real[i] = wr[i] * inv_n;
    }
}

void dsp_unfold_neighbors(const float *mag_in, float *unfold_out) {
    if (!mag_in || !unfold_out) return;

    const int num_freqs = DSP_NUM_FREQS;
    const int num_neighbors = DSP_SB_NEIGHBORS;
    const int unit_size = num_neighbors * 2 + 1;

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
        memcpy(dest, src_noisy, 31 * sizeof(float));
        dest[31] = fb_out[f];
    }
}

void dsp_decompress_cirm(const float *compressed_mask, float *cirm_real, float *cirm_imag, float K, float limit) {
    if (!compressed_mask || !cirm_real || !cirm_imag) return;

    for (int f = 0; f < DSP_NUM_FREQS; ++f) {
        float mr = compressed_mask[f * 2 + 0];
        float mi = compressed_mask[f * 2 + 1];

        if (mr > limit) mr = limit;
        else if (mr < -limit) mr = -limit;

        if (mi > limit) mi = limit;
        else if (mi < -limit) mi = -limit;

        cirm_real[f] = -K * logf((K - mr) / (K + mr));
        cirm_imag[f] = -K * logf((K - mi) / (K + mi));
    }
}

void dsp_apply_cirm_mask(const float *noisy_real, const float *noisy_imag, const float *cirm_real, const float *cirm_imag, float *enh_real, float *enh_imag) {
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

void dsp_fullsubnet_stft_frame(const DspTables *tables, const float *in_frame512, float *out_real257, float *out_imag257) {
    if (!tables || !in_frame512 || !out_real257 || !out_imag257) return;

    float windowed[DSP_N_FFT];
    for (int n = 0; n < DSP_N_FFT; ++n) {
        windowed[n] = in_frame512[n] * tables->hann_window[n];
    }

    float full_r[DSP_N_FFT];
    float full_i[DSP_N_FFT];
    dsp_fft512(tables, windowed, full_r, full_i);

    for (int f = 0; f < DSP_NUM_FREQS; ++f) {
        out_real257[f] = full_r[f];
        out_imag257[f] = full_i[f];
    }
}

void dsp_fullsubnet_istft_frame(const DspTables *tables, const float *in_real257, const float *in_imag257, float *out_frame512) {
    if (!tables || !in_real257 || !in_imag257 || !out_frame512) return;

    float time_synth[DSP_N_FFT];
    dsp_ifft512(tables, in_real257, in_imag257, time_synth);

    for (int n = 0; n < DSP_N_FFT; ++n) {
        out_frame512[n] = time_synth[n] * tables->hann_window[n];
    }
}

void dsp_gtcrn_stft_frame(const DspTables *tables, const float *in_frame512, float *out_real257, float *out_imag257) {
    if (!tables || !in_frame512 || !out_real257 || !out_imag257) return;

    float windowed[DSP_N_FFT];
    for (int n = 0; n < DSP_N_FFT; ++n) {
        windowed[n] = in_frame512[n] * tables->sqrt_hann_window[n];
    }

    float full_r[DSP_N_FFT];
    float full_i[DSP_N_FFT];
    dsp_fft512(tables, windowed, full_r, full_i);

    for (int f = 0; f < DSP_NUM_FREQS; ++f) {
        out_real257[f] = full_r[f];
        out_imag257[f] = full_i[f];
    }
}

void dsp_gtcrn_istft_frame(const DspTables *tables, const float *in_real257, const float *in_imag257, float *out_frame512) {
    if (!tables || !in_real257 || !in_imag257 || !out_frame512) return;

    float time_synth[DSP_N_FFT];
    dsp_ifft512(tables, in_real257, in_imag257, time_synth);

    for (int n = 0; n < DSP_N_FFT; ++n) {
        out_frame512[n] = time_synth[n] * tables->sqrt_hann_window[n];
    }
}

void dsp_ola_init(DspOlaStream *ola) {
    if (!ola) return;
    ola->buf_len = DSP_OLA_BUF_SIZE;
    dsp_ola_reset(ola);
}

void dsp_ola_reset(DspOlaStream *ola) {
    if (!ola) return;
    memset(ola->accum, 0, sizeof(ola->accum));
    memset(ola->wss, 0, sizeof(ola->wss));
    ola->next_emit_idx = 0;
}

void dsp_ola_add_frame(DspOlaStream *ola, const float *synth_frame512, const float *synth_window512, int64_t frame_idx) {
    if (!ola || !synth_frame512 || !synth_window512) return;

    int64_t start_idx = frame_idx * DSP_HOP_SIZE;
    for (int i = 0; i < DSP_N_FFT; ++i) {
        uint32_t slot = (uint32_t)((start_idx + i) % (int64_t)ola->buf_len);
        ola->accum[slot] += synth_frame512[i];
        float w = synth_window512[i];
        ola->wss[slot] += w * w;
    }
}

void dsp_ola_emit_chunk(DspOlaStream *ola, float *chunk_out, int64_t chunk_idx) {
    if (!ola || !chunk_out) return;

    int64_t start_idx = chunk_idx * DSP_HOP_SIZE;
    for (int i = 0; i < DSP_HOP_SIZE; ++i) {
        uint32_t slot = (uint32_t)((start_idx + i) % (int64_t)ola->buf_len);
        float denom = ola->wss[slot];
        chunk_out[i] = (denom > 1e-8f) ? (ola->accum[slot] / denom) : 0.0f;
        // Zero out slot so subsequent circular loops are clean
        ola->accum[slot] = 0.0f;
        ola->wss[slot] = 0.0f;
    }
    ola->next_emit_idx = start_idx + DSP_HOP_SIZE;
}

void dsp_ola_flush_chunk(DspOlaStream *ola, float *chunk_out, int64_t chunk_idx) {
    if (!ola || !chunk_out) return;

    // Flush emits the final partial chunk
    int64_t start_idx = chunk_idx * DSP_HOP_SIZE;
    for (int i = 0; i < DSP_HOP_SIZE; ++i) {
        uint32_t slot = (uint32_t)((start_idx + i) % (int64_t)ola->buf_len);
        float denom = ola->wss[slot];
        chunk_out[i] = (denom > 1e-8f) ? (ola->accum[slot] / denom) : 0.0f;
        ola->accum[slot] = 0.0f;
        ola->wss[slot] = 0.0f;
    }
}

