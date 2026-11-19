#ifndef DSP_PIPELINE_H
#define DSP_PIPELINE_H

#include <stdint.h>
#include <stdbool.h>

#define DSP_N_FFT 512
#define DSP_HOP_SIZE 256
#define DSP_NUM_FREQS 257
#define DSP_SB_NEIGHBORS 15
#define DSP_SB_FEATURES 32

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float hann_window[DSP_N_FFT];
    float ola_denom[DSP_HOP_SIZE];
    uint16_t bit_rev[DSP_N_FFT];
    float twiddle_r[DSP_N_FFT / 2];
    float twiddle_i[DSP_N_FFT / 2];
    bool initialized;
} DspTables;

/* Global or instance tables */
void dsp_init_tables(DspTables *tables);

/* FFT & iFFT 512-point radix-2 */
void dsp_fft512(const DspTables *tables, const float *in_real, float *out_real, float *out_imag);
void dsp_ifft512(const DspTables *tables, const float *in_real, const float *in_imag, float *out_real);

/* Frequency unfolding (31 neighbors with reflection) */
void dsp_unfold_neighbors(const float *mag_in, float *unfold_out);

/* Feature pack: 31 unfolded noisy neighbors + 1 fullband output -> 32 features */
void dsp_pack_subband_features(const float *unfold_noisy, const float *fb_out, float *sb_in);

/* cIRM Decompression: [-limit, limit] -> [-inf, +inf] */
void dsp_decompress_cirm(const float *compressed_mask, float *cirm_real, float *cirm_imag, float K, float limit);

/* Complex spectral masking: (Mr + j Mi) * (Yr + j Yi) */
void dsp_apply_cirm_mask(
    const float *noisy_real,
    const float *noisy_imag,
    const float *cirm_real,
    const float *cirm_imag,
    float *enh_real,
    float *enh_imag
);

#ifdef __cplusplus
}
#endif

#endif /* DSP_PIPELINE_H */

