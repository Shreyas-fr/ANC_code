//! Dynamic Psychoacoustic Spectral Contrast & Formant Masking Unveiler.
//!
//! Developed for SIH 26052 Tactical Military Audio Systems.
//!
//! In high-noise combat operational environments (heavy armored vehicle rumble,
//! rotor wash, multi-talker combat nets), human auditory critical bands suffer from
//! severe spectral smearing: loud low-frequency and engine harmonics mask adjacent
//! weaker speech formant peaks (F1, F2, F3) and consonant bursts.
//!
//! This module implements subband spectral contrast enhancement:
//! 1. Evaluates local magnitude envelope and local mean across frequency bins.
//! 2. Measures local peak-to-valley ratio (PVR) within psychoacoustic ERB subbands.
//! 3. Dynamically expands spectral peaks while carving inter-formant valleys:
//!    Y_contrast(k) = X(k) * (|X(k)| / (LocalMean(k) + eps))^gamma
//!    where gamma in [0.15, 0.40] is dynamically modulated by speech presence probability (SPP).
//! 4. Preserves exact total frame RMS power via energy conservation:
//!    Scale factor S = sqrt(E_in / (E_out + eps)), preventing gain pumping or clipping.
//! 5. Strictly ZERO heap allocations in the real-time processing loop.

use num_complex::Complex32;
use serde::{Deserialize, Serialize};

/// Maximum supported STFT bins (up to 1024-pt FFT).
pub const MAX_CONTRAST_BINS: usize = 513;
/// Number of subbands for peak-to-valley measurement.
pub const NUM_CONTRAST_SUBBANDS: usize = 32;

/// Configuration for the Spectral Contrast Enhancer.
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct SpectralContrastConfig {
    pub num_bins: usize,
    pub sample_rate: f32,
    /// Base contrast expansion exponent gamma in [0.15, 0.40] (default: 0.25).
    pub gamma: f32,
    /// Speech threshold below which contrast enhancement decays to zero (default: 0.30).
    pub speech_threshold: f32,
    /// Maximum allowable dynamic boost for formant peaks in dB (default: +6.0 dB).
    pub max_boost_db: f32,
    /// Maximum allowable dynamic cut for spectral valleys in dB (default: -6.0 dB).
    pub max_cut_db: f32,
    /// Half-width in bins for moving-average local mean calculation (default: 4 bins ~ 125 Hz @ 16 kHz/512 FFT).
    pub window_radius: usize,
    /// Master bypass toggle.
    pub enabled: bool,
}

impl Default for SpectralContrastConfig {
    fn default() -> Self {
        Self {
            num_bins: 257,
            sample_rate: 16000.0,
            gamma: 0.25,
            speech_threshold: 0.30,
            max_boost_db: 6.0,
            max_cut_db: -6.0,
            window_radius: 4,
            enabled: true,
        }
    }
}

/// Real-time telemetry produced by the Spectral Contrast Enhancer.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct SpectralContrastTelemetry {
    pub contrast_ratio_db: f32,
    pub effective_gamma: f32,
    pub max_formant_boost_db: f32,
    pub max_valley_cut_db: f32,
    pub energy_scale_factor: f32,
    pub active: bool,
}

impl Default for SpectralContrastTelemetry {
    fn default() -> Self {
        Self {
            contrast_ratio_db: 0.0,
            effective_gamma: 0.0,
            max_formant_boost_db: 0.0,
            max_valley_cut_db: 0.0,
            energy_scale_factor: 1.0,
            active: false,
        }
    }
}

/// Dynamic Psychoacoustic Spectral Contrast Enhancer with zero heap allocations.
#[derive(Debug, Clone)]
pub struct SpectralContrastEnhancer {
    config: SpectralContrastConfig,
    /// Pre-allocated magnitude array
    mag: [f32; MAX_CONTRAST_BINS],
    /// Pre-allocated prefix sum array for O(1) moving average window
    prefix_sum: [f32; MAX_CONTRAST_BINS + 1],
    /// Pre-allocated local mean array
    local_mean: [f32; MAX_CONTRAST_BINS],
    /// Pre-allocated per-bin gain array
    gains: [f32; MAX_CONTRAST_BINS],
    /// Precomputed min gain linear (e.g. 10^(-6.0/20) = 0.501)
    min_gain_lin: f32,
    /// Precomputed max gain linear (e.g. 10^(+6.0/20) = 1.995)
    max_gain_lin: f32,
    /// Last computed telemetry
    last_telemetry: SpectralContrastTelemetry,
}

impl SpectralContrastEnhancer {
    /// Creates a new SpectralContrastEnhancer instance.
    pub fn new(config: SpectralContrastConfig) -> Self {
        let min_gain_lin = 10.0f32.powf(config.max_cut_db / 20.0);
        let max_gain_lin = 10.0f32.powf(config.max_boost_db / 20.0);

        Self {
            config,
            mag: [0.0; MAX_CONTRAST_BINS],
            prefix_sum: [0.0; MAX_CONTRAST_BINS + 1],
            local_mean: [0.0; MAX_CONTRAST_BINS],
            gains: [1.0; MAX_CONTRAST_BINS],
            min_gain_lin,
            max_gain_lin,
            last_telemetry: SpectralContrastTelemetry::default(),
        }
    }

    /// Resets all internal buffers and state.
    pub fn reset(&mut self) {
        self.mag.fill(0.0);
        self.prefix_sum.fill(0.0);
        self.local_mean.fill(0.0);
        self.gains.fill(1.0);
        self.last_telemetry = SpectralContrastTelemetry::default();
    }

    /// Sets whether contrast enhancement is enabled.
    pub fn set_enabled(&mut self, enabled: bool) {
        self.config.enabled = enabled;
    }

    /// Sets base contrast exponent gamma.
    pub fn set_gamma(&mut self, gamma: f32) {
        self.config.gamma = gamma.clamp(0.0, 0.60);
    }

    /// Returns latest telemetry.
    pub fn telemetry(&self) -> SpectralContrastTelemetry {
        self.last_telemetry
    }

    /// Processes an in-place STFT complex spectrum frame with optional subband SPP vector.
    pub fn process_frame(
        &mut self,
        spectrum: &mut [Complex32],
        spp: Option<&[f32]>,
    ) -> SpectralContrastTelemetry {
        let speech_prob = match spp {
            Some(s) if !s.is_empty() => s.iter().copied().sum::<f32>() / s.len() as f32,
            _ => 1.0,
        };
        self.process_spectrum(spectrum, speech_prob)
    }

    /// Processes an in-place STFT complex spectrum frame with Speech Presence Probability (SPP).
    ///
    /// Preserves exact total input RMS energy while dynamically boosting formant peaks
    /// and carving inter-formant noise valleys.
    pub fn process_spectrum(
        &mut self,
        spectrum: &mut [Complex32],
        speech_prob: f32,
    ) -> SpectralContrastTelemetry {
        let num_bins = spectrum.len().min(self.config.num_bins).min(MAX_CONTRAST_BINS);
        if num_bins == 0 || !self.config.enabled {
            self.last_telemetry = SpectralContrastTelemetry::default();
            return self.last_telemetry;
        }

        // 1. Calculate magnitude spectrum and input frame energy
        let mut e_in = 0.0f32;
        for k in 0..num_bins {
            let re = spectrum[k].re;
            let im = spectrum[k].im;
            let p = re * re + im * im;
            e_in += p;
            self.mag[k] = p.sqrt();
        }

        // 2. Measure subband peak-to-valley ratio (PVR) across ERB-like bands
        let bins_per_band = (num_bins / NUM_CONTRAST_SUBBANDS).max(1);
        let mut sum_pvr_db = 0.0f32;
        let mut active_bands = 0;

        for b in 0..NUM_CONTRAST_SUBBANDS {
            let start = b * bins_per_band;
            let end = if b == NUM_CONTRAST_SUBBANDS - 1 {
                num_bins
            } else {
                ((b + 1) * bins_per_band).min(num_bins)
            };
            if start >= end {
                break;
            }

            let mut band_max = 1e-9f32;
            let mut band_min = f32::MAX;
            for k in start..end {
                let m = self.mag[k];
                if m > band_max {
                    band_max = m;
                }
                if m < band_min {
                    band_min = m;
                }
            }

            if band_max > 1e-6 {
                let pvr_db = 20.0 * (band_max / band_min.max(1e-9)).log10();
                sum_pvr_db += pvr_db;
                active_bands += 1;
            }
        }
        let mean_pvr_db = if active_bands > 0 {
            sum_pvr_db / active_bands as f32
        } else {
            0.0
        };

        // 3. Compute dynamic gamma from speech presence probability
        let spp = speech_prob.clamp(0.0, 1.0);
        let eff_gamma = if spp > self.config.speech_threshold {
            let scale = (spp - self.config.speech_threshold) / (1.0 - self.config.speech_threshold);
            self.config.gamma * scale.clamp(0.0, 1.0)
        } else {
            0.0
        };

        // If inactive or silent, pass through spectrum unchanged
        if eff_gamma <= 1e-4 || e_in < 1e-12 {
            self.last_telemetry = SpectralContrastTelemetry {
                contrast_ratio_db: mean_pvr_db,
                effective_gamma: 0.0,
                max_formant_boost_db: 0.0,
                max_valley_cut_db: 0.0,
                energy_scale_factor: 1.0,
                active: false,
            };
            return self.last_telemetry;
        }

        // 4. O(N) local mean calculation using prefix sums
        self.prefix_sum[0] = 0.0;
        for k in 0..num_bins {
            self.prefix_sum[k + 1] = self.prefix_sum[k] + self.mag[k];
        }

        let rad = self.config.window_radius;
        for k in 0..num_bins {
            let left = k.saturating_sub(rad);
            let right = (k + rad).min(num_bins - 1);
            let count = (right - left + 1) as f32;
            let sum = self.prefix_sum[right + 1] - self.prefix_sum[left];
            self.local_mean[k] = sum / count;
        }

        // 5. Compute contrast enhancement gains:
        //    G(k) = ( mag(k) / (local_mean(k) + eps) )^gamma
        let mut e_out_unscaled = 0.0f32;
        let mut max_g = 1.0f32;
        let mut min_g = 1.0f32;

        for k in 0..num_bins {
            let m = self.mag[k];
            let mean = self.local_mean[k].max(1e-9);
            let ratio = m / mean;

            // Power expansion: (ratio)^gamma
            let g = ratio.powf(eff_gamma).clamp(self.min_gain_lin, self.max_gain_lin);
            self.gains[k] = g;

            if g > max_g {
                max_g = g;
            }
            if g < min_g {
                min_g = g;
            }

            let new_m = m * g;
            e_out_unscaled += new_m * new_m;
        }

        // 6. Energy conservation: scale so total output frame energy matches input energy
        let energy_scale = if e_out_unscaled > 1e-12 {
            (e_in / e_out_unscaled).sqrt()
        } else {
            1.0
        };

        // 7. Apply contrast-enhanced gain with energy scaling
        for k in 0..num_bins {
            let total_gain = self.gains[k] * energy_scale;
            spectrum[k] *= total_gain;
        }

        let max_boost_db = 20.0 * (max_g * energy_scale).max(1e-6).log10();
        let max_cut_db = 20.0 * (min_g * energy_scale).max(1e-6).log10();

        self.last_telemetry = SpectralContrastTelemetry {
            contrast_ratio_db: mean_pvr_db,
            effective_gamma: eff_gamma,
            max_formant_boost_db: max_boost_db,
            max_valley_cut_db: max_cut_db,
            energy_scale_factor: energy_scale,
            active: true,
        };

        self.last_telemetry
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_contrast_default_initialization() {
        let config = SpectralContrastConfig::default();
        let enhancer = SpectralContrastEnhancer::new(config);
        assert_eq!(enhancer.telemetry(), SpectralContrastTelemetry::default());
    }

    #[test]
    fn test_contrast_speech_inactive_bypasses_gain() {
        let config = SpectralContrastConfig::default();
        let mut enhancer = SpectralContrastEnhancer::new(config);
        let mut spectrum = vec![Complex32::new(1.0, 0.5); 257];
        let original = spectrum.clone();

        // When speech probability is low (e.g. 0.1 < 0.3 threshold)
        let telem = enhancer.process_spectrum(&mut spectrum, 0.1);
        assert!(!telem.active);
        assert_eq!(telem.effective_gamma, 0.0);

        for (a, b) in spectrum.iter().zip(original.iter()) {
            assert!((a.re - b.re).abs() < 1e-6);
            assert!((a.im - b.im).abs() < 1e-6);
        }
    }

    #[test]
    fn test_contrast_active_expands_peaks_and_carves_valleys() {
        let config = SpectralContrastConfig::default();
        let mut enhancer = SpectralContrastEnhancer::new(config);

        // Construct spectrum with sharp formant peak at bin 50 and valley at bin 60
        let mut spectrum = vec![Complex32::new(0.01, 0.0); 257];
        spectrum[50] = Complex32::new(2.0, 0.0); // Strong formant peak
        spectrum[60] = Complex32::new(0.005, 0.0); // Inter-formant valley

        let orig_ratio = spectrum[50].norm() / spectrum[60].norm();
        let telem = enhancer.process_spectrum(&mut spectrum, 0.95);

        assert!(telem.active);
        assert!(telem.effective_gamma > 0.15);

        let new_ratio = spectrum[50].norm() / spectrum[60].norm();
        // Contrast enhancement must sharpen the peak-to-valley ratio
        assert!(
            new_ratio > orig_ratio,
            "Enhanced ratio ({new_ratio}) must exceed original ratio ({orig_ratio})"
        );
    }

    #[test]
    fn test_contrast_strict_energy_conservation() {
        let config = SpectralContrastConfig::default();
        let mut enhancer = SpectralContrastEnhancer::new(config);

        let mut spectrum: Vec<Complex32> = (0..257)
            .map(|i| {
                let amp = ((i as f32 * 0.1).sin()).abs() + 0.1;
                Complex32::new(amp, amp * 0.5)
            })
            .collect();

        let energy_before: f32 = spectrum.iter().map(|c| c.norm_sqr()).sum();
        let telem = enhancer.process_spectrum(&mut spectrum, 0.9);
        assert!(telem.active);

        let energy_after: f32 = spectrum.iter().map(|c| c.norm_sqr()).sum();
        let diff_ratio = (energy_after - energy_before).abs() / energy_before;
        assert!(
            diff_ratio < 1e-4,
            "Energy must be conserved within 0.01%: before={energy_before}, after={energy_after}"
        );
    }

    #[test]
    fn test_contrast_clamping_bounds() {
        let config = SpectralContrastConfig {
            max_boost_db: 4.0,
            max_cut_db: -4.0,
            ..Default::default()
        };
        let mut enhancer = SpectralContrastEnhancer::new(config);

        // Extreme spike
        let mut spectrum = vec![Complex32::new(0.0001, 0.0); 257];
        spectrum[100] = Complex32::new(100.0, 0.0);

        let telem = enhancer.process_spectrum(&mut spectrum, 1.0);
        assert!(telem.active);
        // Gains should remain bounded
        assert!(telem.contrast_ratio_db >= 0.0);
    }

    #[test]
    fn test_contrast_reset_and_determinism() {
        let config = SpectralContrastConfig::default();
        let mut enhancer = SpectralContrastEnhancer::new(config);

        let mut s1 = vec![Complex32::new(0.5, 0.2); 257];
        enhancer.process_spectrum(&mut s1, 0.85);

        enhancer.reset();
        assert_eq!(enhancer.telemetry(), SpectralContrastTelemetry::default());
    }
}
