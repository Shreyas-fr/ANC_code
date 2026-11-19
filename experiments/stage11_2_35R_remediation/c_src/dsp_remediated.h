#ifndef DSP_REMEDIATED_H
#define DSP_REMEDIATED_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#define DSP_N_FFT 512
#define DSP_HOP_SIZE 256
#define DSP_NUM_FREQS 257
#define DSP_SB_NEIGHBORS 15
#define DSP_SB_FEATURES 32
#define DSP_OLA_BUF_SIZE (DSP_N_FFT * 2)

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float hann_window[DSP_N_FFT];
    float sqrt_hann_window[DSP_N_FFT];
    uint16_t bit_rev[DSP_N_FFT];
    float twiddle_r[DSP_N_FFT / 2];
    float twiddle_i[DSP_N_FFT / 2];
    bool initialized;
} DspTables;

typedef struct {
    float accum[DSP_OLA_BUF_SIZE];
    float wss[DSP_OLA_BUF_SIZE];
    int64_t next_emit_idx;
    uint32_t buf_len;
} DspOlaStream;

/* Initialize tables */
void dsp_init_tables(DspTables *tables);

/* FFT & iFFT 512 */
void dsp_fft512(const DspTables *tables, const float *in_real, float *out_real, float *out_imag);
void dsp_ifft512(const DspTables *tables, const float *in_real, const float *in_imag, float *out_real);

/* Frequency unfolding & feature packing */
void dsp_unfold_neighbors(const float *mag_in, float *unfold_out);
void dsp_pack_subband_features(const float *unfold_noisy, const float *fb_out, float *sb_in);

/* cIRM decompression & masking */
void dsp_decompress_cirm(const float *compressed_mask, float *cirm_real, float *cirm_imag, float K, float limit);
void dsp_apply_cirm_mask(const float *noisy_real, const float *noisy_imag, const float *cirm_real, const float *cirm_imag, float *enh_real, float *enh_imag);

/* STFT and iSTFT */
void dsp_fullsubnet_stft_frame(const DspTables *tables, const float *in_frame512, float *out_real257, float *out_imag257);
void dsp_fullsubnet_istft_frame(const DspTables *tables, const float *in_real257, const float *in_imag257, float *out_frame512);

void dsp_gtcrn_stft_frame(const DspTables *tables, const float *in_frame512, float *out_real257, float *out_imag257);
void dsp_gtcrn_istft_frame(const DspTables *tables, const float *in_real257, const float *in_imag257, float *out_frame512);

/* Streaming OLA with exact cumulative window envelope normalization */
void dsp_ola_init(DspOlaStream *ola);
void dsp_ola_reset(DspOlaStream *ola);
void dsp_ola_add_frame(DspOlaStream *ola, const float *synth_frame512, const float *synth_window512, int64_t frame_idx);
void dsp_ola_emit_chunk(DspOlaStream *ola, float *chunk_out, int64_t chunk_idx);
void dsp_ola_flush_chunk(DspOlaStream *ola, float *chunk_out, int64_t chunk_idx);

#ifdef __cplusplus
}
#endif

#endif /* DSP_REMEDIATED_H */

