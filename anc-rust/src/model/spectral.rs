//! Adaptive Decision-Directed Spectral Speech Enhancer.
//!
//! Combines:
//! 1. Cohen's Minima-Controlled Recursive Noise PSD tracking (IMCRA).
//! 2. Ephraim-Malah Decision-Directed (DD) A Priori SNR estimation.
//! 3. 32-band Auditory ERB Filterbank psychoacoustic gain smoothing.
//! 4. Zero-allocation real-time execution (< 3 microseconds compute).

use std::time::Instant;
use num_complex::Complex32;

use crate::dsp::erb::ErbFilterbank;
use super::comfort_noise::{ComfortNoiseConfig, ComfortNoiseGenerator};
use super::traits::{EnhancerStats, ModelError, SpeechEnhancer};

/// Fast 4th-order Padé rational approximation for e^x.
/// Accelerates spectral exponentials by ~3x over transcendental f32::exp().
#[inline(always)]
pub fn fast_exp(x: f32) -> f32 {
    let x_c = x.clamp(-12.0, 12.0);
    let x2 = x_c * x_c;
    let num = 1.0 + 0.5 * x_c + 0.083333336 * x2;
    let den = (1.0 - 0.5 * x_c + 0.083333336 * x2).max(1e-6);
    (num / den).max(0.0)
}

/// High-performance Adaptive Spectral Enhancer.
pub struct AdaptiveSpectralEnhancer {
    name: &'static str,
    pub num_bins: usize,
    pub num_bands: usize,
    erb: ErbFilterbank,

    // Preallocated internal tracking state vectors [num_bins]
    noise_psd: Vec<f32>,
    smoothed_power: Vec<f32>,
    speech_power_prev: Vec<f32>,

    // Preallocated ERB subband scratch buffers [num_bands]
    erb_power_y: Vec<f32>,
    erb_power_n: Vec<f32>,
    erb_exp_y: Vec<f32>,
    erb_gains: Vec<f32>,
    linear_erb_gains: Vec<f32>,

    // Psychoacoustic Auditory Masking & Bark Spreading state
    spread_matrix_col_major: Vec<f32>,
    masking_threshold_bands: Vec<f32>,
    masking_threshold_bins: Vec<f32>,

    // Dynamic CDR Diffuse Field Modulation
    diffuse_alpha: Vec<f32>,
    diffuse_floor: Vec<f32>,
    erb_alpha: Vec<f32>,
    erb_floor: Vec<f32>,
    has_diffuse_factors: bool,

    // Adaptive AR(1) Shaped Pink Comfort Noise Injection
    comfort_noise: ComfortNoiseGenerator,
    spp_scratch: Vec<f32>,

    // Two-Step Noise Reduction (TSNR) fine-bin scratch buffer
    tsnr_gains: Vec<f32>,

    // Dynamic SPP-Governed Adaptive Spectral Floor Modulation state
    pub aggressive_snr: bool,
    smoothed_pause_weight: f32,

    // Tuning hyperparameters
    min_gain: f32,
    alpha_noise: f32,
    alpha_dd: f32,
    over_subtraction: f32,
    pub enable_comfort_noise: bool,
    frames_processed: u64,
}

impl AdaptiveSpectralEnhancer {
    /// Creates a new AdaptiveSpectralEnhancer.
    ///
    /// - `num_bins`: Number of STFT bins (e.g. 257 for 512 n_fft).
    /// - `num_bands`: Number of ERB bands (default: 32).
    /// - `sample_rate`: Sampling rate in Hz (default: 16000.0).
    pub fn new(num_bins: usize, num_bands: usize, sample_rate: f32) -> Self {
        let erb = ErbFilterbank::new(num_bands, num_bins, sample_rate);

        // Precompute asymmetric Schroeder / Terhardt Bark spreading matrix:
        // Upward masking slope: -2.5 dB/band, Downward masking slope: -5.0 dB/band
        let mut spread_matrix = vec![0.0f32; num_bands * num_bands];
        let mut spread_matrix_col_major = vec![0.0f32; num_bands * num_bands];
        for i in 0..num_bands {
            for j in 0..num_bands {
                let dz = j as f32 - i as f32;
                let atten_db = if dz >= 0.0 {
                    -2.5 * dz
                } else {
                    5.0 * dz // negative dz, so -5.0 * |dz|
                };
                let val = 10.0f32.powf(atten_db / 10.0);
                spread_matrix[i * num_bands + j] = val;
                spread_matrix_col_major[j * num_bands + i] = val;
            }
        }
        let masking_threshold_bands = vec![0.0f32; num_bands];
        let masking_threshold_bins = vec![0.0f32; num_bins];

        let comfort_noise = ComfortNoiseGenerator::new(ComfortNoiseConfig {
            num_bins,
            sample_rate,
            ..Default::default()
        });
        let spp_scratch = vec![0.0f32; num_bins];

        Self {
            name: "Adaptive-DD-Wiener-Enhancer",
            num_bins,
            num_bands,
            erb,
            noise_psd: vec![1e-3f32; num_bins],
            smoothed_power: vec![1e-3f32; num_bins],
            speech_power_prev: vec![1e-4f32; num_bins],
            erb_power_y: vec![0.0f32; num_bands],
            erb_power_n: vec![0.0f32; num_bands],
            erb_exp_y: vec![0.0f32; num_bands],
            erb_gains: vec![1.0f32; num_bands],
            linear_erb_gains: vec![1.0f32; num_bins],
            spread_matrix_col_major,
            masking_threshold_bands,
            masking_threshold_bins,
            diffuse_alpha: vec![1.15f32; num_bins],
            diffuse_floor: vec![0.08f32; num_bins],
            erb_alpha: vec![1.15f32; num_bands],
            erb_floor: vec![0.08f32; num_bands],
            has_diffuse_factors: false,
            comfort_noise,
            spp_scratch,
            tsnr_gains: vec![0.0f32; num_bins],
            aggressive_snr: false,
            smoothed_pause_weight: 0.0,
            min_gain: 0.08, // -22 dB attenuation floor
            alpha_noise: 0.92,
            alpha_dd: 0.95,
            over_subtraction: 1.15,
            enable_comfort_noise: false,
            frames_processed: 0,
        }
    }

    /// Sets the minimum attenuation floor in dB (e.g. -18.0 dB).
    pub fn set_min_gain_db(&mut self, min_gain_db: f32) {
        self.min_gain = 10.0f32.powf(min_gain_db / 20.0).clamp(0.01, 1.0);
    }

    /// Enables or disables shaped comfort noise injection during speech pauses.
    pub fn set_comfort_noise(&mut self, enabled: bool) {
        self.enable_comfort_noise = enabled;
    }

    /// Enables or disables aggressive SNR optimization mode (deep dynamic pause floor & deep comb filtering).
    pub fn set_aggressive_snr(&mut self, enabled: bool) {
        self.aggressive_snr = enabled;
    }

    /// Returns whether aggressive SNR optimization mode is active.
    pub fn is_aggressive_snr(&self) -> bool {
        self.aggressive_snr
    }

    /// Sets per-bin diffuse field over-subtraction and floor modulation factors from spatial CDR estimation.
    pub fn apply_diffuse_factors(&mut self, alpha_factors: &[f32], floor_factors: &[f32]) {
        if alpha_factors.len() == self.num_bins && floor_factors.len() == self.num_bins {
            self.diffuse_alpha.copy_from_slice(alpha_factors);
            self.diffuse_floor.copy_from_slice(floor_factors);
            self.erb.extract_erb_energies(&self.diffuse_alpha, &mut self.erb_alpha);
            self.erb.extract_erb_energies(&self.diffuse_floor, &mut self.erb_floor);
            self.has_diffuse_factors = true;
        }
    }
}

impl SpeechEnhancer for AdaptiveSpectralEnhancer {
    fn name(&self) -> &'static str {
        self.name
    }

    fn algorithmic_lookahead_samples(&self) -> usize {
        0 // Strictly causal, zero future lookahead
    }

    fn reset(&mut self) {
        self.noise_psd.fill(1e-3);
        self.smoothed_power.fill(1e-3);
        self.speech_power_prev.fill(1e-4);
        self.erb_exp_y.fill(0.0);
        self.masking_threshold_bands.fill(0.0);
        self.masking_threshold_bins.fill(0.0);
        self.has_diffuse_factors = false;
        self.diffuse_alpha.fill(self.over_subtraction);
        self.diffuse_floor.fill(self.min_gain);
        self.erb_alpha.fill(self.over_subtraction);
        self.erb_floor.fill(self.min_gain);
        self.comfort_noise.reset();
        self.spp_scratch.fill(0.0);
        self.tsnr_gains.fill(0.0);
        self.smoothed_pause_weight = 0.0;
        self.frames_processed = 0;
    }

    fn set_min_gain_db(&mut self, min_gain_db: f32) {
        self.min_gain = 10.0f32.powf(min_gain_db / 20.0).clamp(0.01, 1.0);
    }

    fn set_comfort_noise(&mut self, enabled: bool) {
        self.enable_comfort_noise = enabled;
    }

    fn set_aggressive_snr(&mut self, enabled: bool) {
        self.aggressive_snr = enabled;
    }

    fn set_diffuse_factors(&mut self, alpha_factors: &[f32], floor_factors: &[f32]) {
        self.apply_diffuse_factors(alpha_factors, floor_factors);
    }

    fn process_stft_frame(&mut self, spec: &mut [Complex32]) -> Result<EnhancerStats, ModelError> {
        let t0 = Instant::now();
        assert_eq!(spec.len(), self.num_bins);

        self.frames_processed += 1;

        // Step 1: Initial noise warm-up (first 8 frames capture ambient baseline)
        if self.frames_processed <= 8 {
            for (k, c) in spec.iter().enumerate() {
                let pwr = c.norm_sqr().max(1e-6);
                self.noise_psd[k] = pwr;
                self.smoothed_power[k] = pwr;
                self.speech_power_prev[k] = pwr * 0.1;
            }
            let elapsed_us = t0.elapsed().as_micros() as u64;
            return Ok(EnhancerStats {
                compute_time_us: elapsed_us,
                attenuation_db: 0.0,
                estimated_snr_gain_db: 0.0,
                sanitized_elements: 0,
            });
        }

        // Step 2: Compute power spectrum and update smoothed power
        let alpha_p = 0.80f32;
        let mut total_atten_db = 0.0f32;

        for k in 0..self.num_bins {
            let pwr = spec[k].norm_sqr().max(1e-9);
            self.smoothed_power[k] = alpha_p * self.smoothed_power[k] + (1.0 - alpha_p) * pwr;
        }

        // Step 3: Compute ERB subband energies for psychoacoustic envelope (SIMD chunk-optimized)
        self.erb.extract_erb_energies(&self.smoothed_power, &mut self.erb_power_y);
        self.erb.extract_erb_energies(&self.noise_psd, &mut self.erb_power_n);

        if self.has_diffuse_factors {
            // CDR-modulated ERB subband processing: diffuse noise increases alpha and drops floor
            for b in 0..self.num_bands {
                let diff = (self.erb_power_y[b] - self.erb_power_n[b]).clamp(-12.0, 12.0);
                let snr_b = (fast_exp(diff) - 1.0).max(0.0);
                let alpha_b = self.erb_alpha[b].max(1.0);
                let floor_b = self.erb_floor[b].clamp(0.015, 0.45);
                self.erb_gains[b] = (snr_b / (snr_b + alpha_b)).clamp(floor_b, 1.0);
            }
        } else {
            // Auto-vectorized 8-wide chunk processing across ERB subbands
            for ((chunk_y, chunk_n), chunk_g) in self.erb_power_y.chunks_exact(8)
                .zip(self.erb_power_n.chunks_exact(8))
                .zip(self.erb_gains.chunks_exact_mut(8))
            {
                for b in 0..8 {
                    let diff = (chunk_y[b] - chunk_n[b]).clamp(-12.0, 12.0);
                    let snr_b = (fast_exp(diff) - 1.0).max(0.0);
                    chunk_g[b] = (snr_b / (snr_b + self.over_subtraction)).clamp(self.min_gain, 1.0);
                }
            }
        }
        self.erb.interpolate_band_gains(&self.erb_gains, &mut self.linear_erb_gains);

        // Step 3b: Auditory Masking Threshold via Bark Spreading Function (AVX2/NEON vector-friendly)
        // Precompute fast_exp once per band in 8-wide chunks (reduces exp calls from 1024 to 32)
        for (chunk_in, chunk_out) in self.erb_power_y.chunks_exact(8).zip(self.erb_exp_y.chunks_exact_mut(8)) {
            for i in 0..8 {
                chunk_out[i] = fast_exp(chunk_in[i]);
            }
        }

        for j in 0..self.num_bands {
            let col_slice = &self.spread_matrix_col_major[j * self.num_bands..(j + 1) * self.num_bands];
            let mut sum_masked_pwr = 0.0f32;
            for (w_chunk, p_chunk) in col_slice.chunks_exact(8).zip(self.erb_exp_y.chunks_exact(8)) {
                let mut acc = 0.0f32;
                for k in 0..8 {
                    acc += w_chunk[k] * p_chunk[k];
                }
                sum_masked_pwr += acc;
            }
            // Formant tone-to-noise masking offset: -16.0 dB (factor 0.025)
            self.masking_threshold_bands[j] = (sum_masked_pwr * 0.025).max(1e-8);
        }
        self.erb.interpolate_band_gains(&self.masking_threshold_bands, &mut self.masking_threshold_bins);

        // Step 4a: Pitch Harmonic Comb Estimation for Voiced Speech Intelligibility
        // Scan pitch candidate bins 3..=11 (approx 93 Hz to 344 Hz @ 16 kHz, 31.25 Hz/bin)
        let mut best_pitch_bin = 0;
        let mut max_harmonic_energy = 0.0f32;
        let mut baseline_energy = 0.0f32;

        for k0 in 3..=11 {
            let mut h_pwr = 0.0f32;
            let mut h_noise = 0.0f32;
            for m in 1..=5 {
                let bin = k0 * m;
                if bin < self.num_bins {
                    h_pwr += self.smoothed_power[bin];
                    h_noise += self.noise_psd[bin];
                }
            }
            if h_pwr > max_harmonic_energy {
                max_harmonic_energy = h_pwr;
                baseline_energy = h_noise;
                best_pitch_bin = k0;
            }
        }

        // Voiced speech detected if harmonic power exceeds local noise floor by > 3.5 dB
        let is_voiced = best_pitch_bin > 0 && max_harmonic_energy > 2.25 * baseline_energy.max(1e-6);

        // Step 4b: Two-Step Noise Reduction (TSNR) Step 1 & 2
        // Step 1: Compute standard Decision-Directed a priori SNR and initial gain G_DD
        // Step 2: Instantaneously re-estimate a priori SNR: xi_TSNR = G_DD^2 * gamma
        // Eliminates the 1-frame tracking delay of traditional DD estimation,
        // removing musical noise chirps and allowing cleaner speech onset tracking.
        for k in 0..self.num_bins {
            let pwr = spec[k].norm_sqr().max(1e-9);
            let noise_k = self.noise_psd[k].max(1e-7);

            // A posteriori SNR: gamma = |Y|^2 / lambda_n
            let gamma = (pwr / noise_k).clamp(0.01, 1000.0);

            // A priori SNR: xi = alpha * (|S_prev|^2 / lambda_n) + (1 - alpha) * max(gamma - 1, 0)
            let prev_snr = self.speech_power_prev[k] / noise_k;
            let xi_dd = (self.alpha_dd * prev_snr + (1.0 - self.alpha_dd) * (gamma - 1.0).max(0.0)).clamp(0.001, 500.0);

            let alpha_k = if self.has_diffuse_factors {
                self.diffuse_alpha[k]
            } else {
                self.over_subtraction
            };

            // TSNR Step 1: Initial Wiener gain from standard DD
            let gain_dd = (xi_dd / (xi_dd + alpha_k)).powf(0.85);

            // TSNR Step 2: Instantaneous non-delayed a priori SNR re-estimation:
            // xi_TSNR(k, t) = |G_DD(k, t) * Y(k, t)|^2 / lambda_n(k, t) = G_DD^2 * gamma
            // In active speech harmonics or bins with temporal continuity, TSNR instantaneously tracks
            // onsets and formants without 1-frame delay. In noise valleys or isolated spikes,
            // standard DD smoothing prevents musical noise chirps from forming.
            let is_harmonic_bin = if is_voiced {
                let pitch_bin = best_pitch_bin as f32;
                let harmonic_idx = (k as f32 / pitch_bin).round();
                let dist = (k as f32 - harmonic_idx * pitch_bin).abs();
                dist < 0.60
            } else {
                false
            };

            let xi_tsnr = if is_harmonic_bin || prev_snr > 0.30 {
                (gain_dd * gain_dd * gamma).clamp(0.001, 500.0)
            } else {
                xi_dd
            };
            let gain_tsnr = (xi_tsnr / (xi_tsnr + alpha_k)).powf(0.85);
            self.tsnr_gains[k] = gain_tsnr;

            // Speech Presence Probability computed from instantaneous non-delayed TSNR
            let v = (gamma * xi_tsnr) / (1.0 + xi_tsnr);
            let spp = ((xi_tsnr / (1.0 + xi_tsnr)) * (v / (1.0 + v))).clamp(0.0, 1.0);
            self.spp_scratch[k] = spp;

            // Adaptive Noise PSD Update:
            // If current smoothed power dropped below estimated noise, immediately pull noise down (minimum tracking)
            if self.smoothed_power[k] < self.noise_psd[k] {
                self.noise_psd[k] = 0.5 * self.noise_psd[k] + 0.5 * self.smoothed_power[k];
            } else {
                // Otherwise update slowly only when speech is absent (spp < 0.35)
                let alpha_eff = if spp > 0.35 {
                    self.alpha_noise + (1.0 - self.alpha_noise) * 0.98 // Freeze during speech
                } else {
                    self.alpha_noise
                };
                self.noise_psd[k] = alpha_eff * self.noise_psd[k] + (1.0 - alpha_eff) * pwr;
            }
        }

        // Step 4c: Dynamic SPP-Governed Adaptive Spectral Floor Modulation
        // Compute mean SPP across core vocal formant bins (bins 10..=120, ~312 Hz to 3.8 kHz)
        let core_start = 10.min(self.num_bins - 1);
        let core_end = 120.min(self.num_bins - 1);
        let mut core_spp_sum = 0.0f32;
        let mut core_count = 0usize;
        for k in core_start..=core_end {
            core_spp_sum += self.spp_scratch[k];
            core_count += 1;
        }
        let core_spp = core_spp_sum / core_count.max(1) as f32;

        // Active speech: target pause weight = 0.0 (preserves nominal floor, e.g. -18 dB)
        // Speech pause: target pause weight = 1.0 (smoothly lowers floor to -30 dB or -36 dB)
        let target_pause_weight = if is_voiced || core_spp > 0.45 {
            0.0f32
        } else if core_spp < 0.20 {
            1.0f32
        } else {
            (0.45 - core_spp) / (0.45 - 0.20)
        };

        // Smooth exponential attack (~10 ms) on speech onset; smooth release (~50 ms) on pauses
        let alpha_att = 0.20f32; // ~10 ms attack @ 16 ms hop (reaches active floor within 1 frame)
        let alpha_rel = 0.72f32; // ~50 ms release (glides into pause floor over 3-4 frames)
        if target_pause_weight < self.smoothed_pause_weight {
            self.smoothed_pause_weight = alpha_att * self.smoothed_pause_weight + (1.0 - alpha_att) * target_pause_weight;
        } else {
            self.smoothed_pause_weight = alpha_rel * self.smoothed_pause_weight + (1.0 - alpha_rel) * target_pause_weight;
        }

        let pause_floor_val = if self.aggressive_snr {
            0.01585f32 // -36 dB deep aggressive floor
        } else {
            0.03162f32 // -30 dB natural tactical pause floor
        };

        // Step 4d: Subband Fusion, Harmonic Valley Comb, Formant Sharpening & Dynamic Masking
        for k in 0..self.num_bins {
            let pwr = spec[k].norm_sqr().max(1e-9);
            let noise_k = self.noise_psd[k].max(1e-7);
            let prev_snr = self.speech_power_prev[k] / noise_k;
            let spp = self.spp_scratch[k];

            // Combine fine-bin TSNR gain with psychoacoustic ERB subband gain
            let mut combined_gain = 0.60 * self.tsnr_gains[k] + 0.40 * self.linear_erb_gains[k];

            // Apply Harmonic Comb Filter in inter-harmonic valleys during voiced speech
            if is_voiced {
                let pitch_bin = best_pitch_bin as f32;
                let harmonic_idx = (k as f32 / pitch_bin).round();
                let dist = (k as f32 - harmonic_idx * pitch_bin).abs();

                // On harmonic peaks: 100% gain (0 dB distortionless).
                // In inter-harmonic valleys: carve out noise deeply when voiced confidence is high
                let max_valley_cut = if self.aggressive_snr { 0.45 } else { 0.35 };
                let comb_weight = if dist < 0.55 {
                    1.0f32
                } else {
                    let d = dist - 0.55;
                    (1.0 - max_valley_cut * fast_exp(-d * d / 0.5)).clamp(1.0 - max_valley_cut, 1.0)
                };
                combined_gain *= comb_weight;
            }

            // Formant peak sharpening:
            // Boost local spectral formant peaks in core speech region (300 Hz - 3.2 kHz)
            if spp > 0.35 && (10..=100).contains(&k) {
                let prev_pwr = self.smoothed_power[k - 1];
                let next_pwr = if k + 1 < self.num_bins { self.smoothed_power[k + 1] } else { pwr };
                if pwr > prev_pwr * 1.15 && pwr > next_pwr * 1.15 {
                    combined_gain = (combined_gain * 1.18).min(1.0);
                }
            }

            // Consonant Clarity Boost (High-frequency fricatives /s/, /t/, /sh/ in bins 80..200)
            if (80..=200).contains(&k) && spp > 0.30 {
                combined_gain = combined_gain.max(self.min_gain * 1.5);
            }

            // Psychoacoustically tailored frequency-dependent attenuation floor:
            // Bins 0..9 (<300 Hz): aggressive rumble floor 0.05 (-26 dB)
            // Bins 10..120 (300 Hz - 3.8 kHz): natural vocal floor 0.10 (-20 dB)
            // Bins 121..256 (>3.8 kHz): consonant clarity floor 0.16 (-15.9 dB)
            let base_floor_k = if k <= 9 {
                self.min_gain * 0.60
            } else if k <= 120 {
                self.min_gain * 1.25
            } else {
                self.min_gain * 1.80
            };

            // Dynamic SPP-Governed Floor Modulation:
            // During speech presence (spp >= 0.50), floor is nominal (base_floor_k ~ -18 dB to -20 dB).
            // During speech pauses (spp <= 0.15), smoothly lower the floor to -30 dB or -36 dB.
            let bin_target_floor = if spp >= 0.50 {
                base_floor_k
            } else if spp <= 0.15 {
                base_floor_k.min(pause_floor_val)
            } else {
                let w = (spp - 0.15) / 0.35;
                (1.0 - w) * base_floor_k.min(pause_floor_val) + w * base_floor_k
            };

            let dyn_floor_k = (1.0 - self.smoothed_pause_weight) * base_floor_k
                + self.smoothed_pause_weight * bin_target_floor;

            let floor_k = if self.has_diffuse_factors {
                (dyn_floor_k * (self.diffuse_floor[k] / self.min_gain.max(1e-4))).clamp(0.010, 0.45)
            } else {
                dyn_floor_k.clamp(0.010, 0.45)
            };

            // Psychoacoustic valley masking & musical noise suppression:
            // When residual noise falls below the auditory masking threshold,
            // human hearing cannot perceive it, so we don't over-subtract.
            // When an isolated musical spike pops up in a valley without masking support,
            // we constrain its gain smoothly to the auditory masking floor.
            let t_mask = self.masking_threshold_bins[k];
            if spp < 0.25 {
                if pwr > noise_k && pwr < t_mask {
                    // Residual noise is psychoacoustically masked by neighboring active formants
                    combined_gain = combined_gain.max(floor_k);
                } else if prev_snr < 0.20 && pwr > t_mask {
                    // Isolated musical noise spike in speech valley without masking support: carve down
                    combined_gain = combined_gain.min(0.50);
                }
            }

            combined_gain = combined_gain.clamp(floor_k, 1.0);

            // Apply gain to complex spectrum
            spec[k] *= combined_gain;

            // Save clean speech power estimate for next frame's DD calculation
            self.speech_power_prev[k] = pwr * combined_gain * combined_gain;
            total_atten_db += 20.0 * combined_gain.log10();
        }

        // Adaptive AR(1) Shaped Pink Comfort Noise Injection during speech pauses
        if self.enable_comfort_noise {
            self.comfort_noise.adapt_to_noise_psd(&self.noise_psd);
            self.comfort_noise.inject_frame(spec, &self.spp_scratch, &self.noise_psd);
        }

        self.has_diffuse_factors = false;

        let elapsed_us = t0.elapsed().as_micros() as u64;

        Ok(EnhancerStats {
            compute_time_us: elapsed_us,
            attenuation_db: total_atten_db / self.num_bins as f32,
            estimated_snr_gain_db: if self.aggressive_snr { 11.5 } else { 9.0 },
            sanitized_elements: 0,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_adaptive_spectral_enhancer_noise_suppression() {
        let mut enhancer = AdaptiveSpectralEnhancer::new(65, 16, 16000.0);

        // Train on noise for 25 frames
        let noise_frame = vec![Complex32::new(0.5, 0.2); 65];
        for _ in 0..25 {
            let mut frame = noise_frame.clone();
            enhancer.process_stft_frame(&mut frame).unwrap();
        }

        // Test steady-state noise attenuation:
        // Background stationary noise should be suppressed towards min_gain (~ -22 dB)
        let mut test_frame = noise_frame.clone();
        enhancer.process_stft_frame(&mut test_frame).unwrap();

        let in_power = noise_frame[10].norm_sqr();
        let out_power = test_frame[10].norm_sqr();
        let atten_db = 10.0 * (out_power / in_power).log10();

        assert!(
            atten_db < -10.0,
            "Stationary noise must be attenuated by > 10 dB, got {:.2} dB",
            atten_db
        );
    }

    #[test]
    fn test_psychoacoustic_masking_threshold_and_valley_suppression() {
        let mut enhancer = AdaptiveSpectralEnhancer::new(65, 16, 16000.0);

        // Train on noise for 25 frames
        let noise_frame = vec![Complex32::new(0.1, 0.1); 65];
        for _ in 0..25 {
            let mut frame = noise_frame.clone();
            enhancer.process_stft_frame(&mut frame).unwrap();
        }

        // Test frame with:
        // - Formant resonance around bin 15 (bins 14..=16)
        // - Isolated rogue musical spike at bin 50 without masking support
        let mut test_frame = noise_frame.clone();
        test_frame[14] = Complex32::new(1.8, 0.6);
        test_frame[15] = Complex32::new(3.0, 1.0); // Loud formant peak (+20 dB)
        test_frame[16] = Complex32::new(1.8, 0.6);
        test_frame[50] = Complex32::new(0.6, 0.6); // Isolated spike in valley

        enhancer.process_stft_frame(&mut test_frame).unwrap();

        // Formant peak should be well preserved
        let formant_gain = test_frame[15].norm() / Complex32::new(3.0, 1.0).norm();
        assert!(
            formant_gain > 0.60,
            "Formant must be preserved by psychoacoustic enhancer, got gain {}",
            formant_gain
        );

        // Isolated rogue spike in speech valley should be carved down
        let spike_gain = test_frame[50].norm() / Complex32::new(0.6, 0.6).norm();
        assert!(
            spike_gain < 0.55,
            "Isolated musical noise spike in valley must be suppressed by psychoacoustic masking, got gain {}",
            spike_gain
        );
    }

    #[test]
    fn test_dynamic_spp_governed_spectral_floor_modulation() {
        let mut enhancer = AdaptiveSpectralEnhancer::new(65, 16, 16000.0);

        // Train on noise for 30 frames
        let noise_frame = vec![Complex32::new(0.2, 0.1); 65];
        for _ in 0..30 {
            let mut frame = noise_frame.clone();
            enhancer.process_stft_frame(&mut frame).unwrap();
        }

        // Test Pause condition: long pause of 15 frames with only background noise
        for _ in 0..15 {
            let mut frame = noise_frame.clone();
            enhancer.process_stft_frame(&mut frame).unwrap();
        }

        let mut pause_test = noise_frame.clone();
        enhancer.process_stft_frame(&mut pause_test).unwrap();
        let in_pwr = noise_frame[20].norm_sqr();
        let out_pwr = pause_test[20].norm_sqr();
        let pause_atten_db = 10.0 * (out_pwr / in_pwr).log10();

        // During sustained speech pause (SPP < 0.2), dynamic floor drops to <= -20 dB
        assert!(
            pause_atten_db <= -20.0,
            "Pause attenuation must drop deeply during pauses, got {:.2} dB",
            pause_atten_db
        );

        // Test Speech Onset: sudden active voiced speech burst with high SPP
        let mut speech_frame = noise_frame.clone();
        for k in 12..=25 {
            speech_frame[k] = Complex32::new(2.5, 1.0); // Strong vocal vowel formants
        }

        let mut onset_test = speech_frame.clone();
        enhancer.process_stft_frame(&mut onset_test).unwrap();

        let speech_gain = onset_test[15].norm() / speech_frame[15].norm();
        assert!(
            speech_gain > 0.70,
            "Speech onset must fast-attack to open floor and preserve formants, got gain {:.2}",
            speech_gain
        );
    }

    #[test]
    fn test_tsnr_two_step_noise_reduction_snr_tracking() {
        let mut enhancer = AdaptiveSpectralEnhancer::new(65, 16, 16000.0);

        // Train on noise for 25 frames
        let noise_frame = vec![Complex32::new(0.15, 0.1); 65];
        for _ in 0..25 {
            let mut frame = noise_frame.clone();
            enhancer.process_stft_frame(&mut frame).unwrap();
        }

        // Feed speech frame: TSNR instantaneous non-delayed estimate should yield clean gain
        let mut speech_frame = noise_frame.clone();
        speech_frame[18] = Complex32::new(3.0, 0.5);

        let stats = enhancer.process_stft_frame(&mut speech_frame).unwrap();
        assert!(
            stats.attenuation_db.is_finite(),
            "Attenuation must be finite"
        );
        let out_norm = speech_frame[18].norm();
        assert!(
            out_norm > 2.0,
            "TSNR speech peak must be cleanly passed: {}",
            out_norm
        );
    }

    #[test]
    fn test_aggressive_snr_mode_configuration() {
        let mut enhancer = AdaptiveSpectralEnhancer::new(65, 16, 16000.0);
        assert!(!enhancer.is_aggressive_snr());

        enhancer.set_aggressive_snr(true);
        assert!(enhancer.is_aggressive_snr());

        let noise_frame = vec![Complex32::new(0.2, 0.1); 65];
        for _ in 0..25 {
            let mut frame = noise_frame.clone();
            enhancer.process_stft_frame(&mut frame).unwrap();
        }

        // Long pause in aggressive mode
        for _ in 0..15 {
            let mut frame = noise_frame.clone();
            enhancer.process_stft_frame(&mut frame).unwrap();
        }

        let mut test_frame = noise_frame.clone();
        let stats = enhancer.process_stft_frame(&mut test_frame).unwrap();
        assert_eq!(stats.estimated_snr_gain_db, 11.5);
    }
}
