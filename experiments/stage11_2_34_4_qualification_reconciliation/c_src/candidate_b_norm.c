#include "candidate_b_norm.h"
#include <math.h>

void ema_norm_init(EmaNormalizer *norm, float alpha, float eps) {
    if (!norm) return;
    norm->alpha = alpha;
    norm->eps = eps;
    norm->t_sample = (uint32_t)roundf(2.0f / alpha - 1.0f);
    ema_norm_reset(norm);
}

void ema_norm_reset(EmaNormalizer *norm) {
    if (!norm) return;
    norm->step_idx = 0;
    norm->running_mu = 0.0f;
    norm->initialized = false;
}

static inline void ema_update(EmaNormalizer *norm, float cur_mean) {
    if (!norm->initialized) {
        norm->running_mu = cur_mean;
        norm->step_idx = 0;
        norm->initialized = true;
    } else {
        norm->step_idx++;
        if (norm->step_idx < norm->t_sample) {
            float ratio = (norm->step_idx > 0) ? ((float)norm->step_idx - 1.0f) / ((float)norm->step_idx + 1.0f) : 0.0f;
            float alp = (ratio < norm->alpha) ? ratio : norm->alpha;
            if (alp < 0.0f) alp = 0.0f;
            norm->running_mu = (1.0f - alp) * norm->running_mu + alp * cur_mean;
        } else {
            norm->running_mu = (1.0f - norm->alpha) * norm->running_mu + norm->alpha * cur_mean;
        }
    }
}

void ema_norm_fb_frame(EmaNormalizer *norm, const float *in_mag, float *out_normed, uint32_t num_freqs) {
    if (!norm || !in_mag || !out_normed || num_freqs == 0) return;

    /* Compute spatial mean in exact float32 matching PyTorch */
    float sum = 0.0f;
    for (uint32_t f = 0; f < num_freqs; ++f) {
        sum += in_mag[f];
    }
    float cur_mean = sum / (float)num_freqs;

    ema_update(norm, cur_mean);

    float denom = norm->running_mu + norm->eps;
    for (uint32_t f = 0; f < num_freqs; ++f) {
        out_normed[f] = in_mag[f] / denom;
    }
}

void ema_norm_sb_frame(EmaNormalizer *norm, const float *in_sb, float *out_normed, uint32_t num_freqs, uint32_t num_features) {
    if (!norm || !in_sb || !out_normed || num_freqs == 0 || num_features == 0) return;

    uint32_t total_elements = num_freqs * num_features;
    float sum = 0.0f;
    for (uint32_t i = 0; i < total_elements; ++i) {
        sum += in_sb[i];
    }
    float cur_mean = sum / (float)total_elements;

    ema_update(norm, cur_mean);

    float denom = norm->running_mu + norm->eps;
    for (uint32_t i = 0; i < total_elements; ++i) {
        out_normed[i] = in_sb[i] / denom;
    }
}

float ema_norm_get_mu(const EmaNormalizer *norm) {
    return norm ? norm->running_mu : 0.0f;
}

uint32_t ema_norm_get_step(const EmaNormalizer *norm) {
    return norm ? norm->step_idx : 0;
}
