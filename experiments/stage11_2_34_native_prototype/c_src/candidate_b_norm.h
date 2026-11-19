#ifndef CANDIDATE_B_NORM_H
#define CANDIDATE_B_NORM_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    float alpha;
    float eps;
    uint32_t t_sample;
    uint32_t step_idx;
    float running_mu;
    bool initialized;
} EmaNormalizer;

void ema_norm_init(EmaNormalizer *norm, float alpha, float eps);
void ema_norm_reset(EmaNormalizer *norm);

/* Fullband normalization: in_mag has num_freqs (257) floats, writes out_normed */
void ema_norm_fb_frame(EmaNormalizer *norm, const float *in_mag, float *out_normed, uint32_t num_freqs);

/* Subband normalization: in_sb has num_freqs * num_features (257 * 32) floats, writes out_normed */
void ema_norm_sb_frame(EmaNormalizer *norm, const float *in_sb, float *out_normed, uint32_t num_freqs, uint32_t num_features);

/* Direct step inspection */
float ema_norm_get_mu(const EmaNormalizer *norm);
uint32_t ema_norm_get_step(const EmaNormalizer *norm);

#ifdef __cplusplus
}
#endif

#endif /* CANDIDATE_B_NORM_H */

