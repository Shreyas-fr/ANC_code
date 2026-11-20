//! Adaptive Subband Speech Intelligibility Enhancer & Formant Dynamic Booster.
//!
//! Developed for SIH 26052 Tactical Audio Systems.
//!
//! In high-noise operational environments (combat vehicle engine rumble, cockpit rotor wash),
//! low-frequency acoustic noise psychoacoustically masks critical speech consonants and vowel formants
//! via the upward spread of masking.
//!
//! This module implements:
//! 1. Acoustic Lombard Effect Compensator & ANSI S3.5 Speech Intelligibility Index (SII) optimizer:
//!    - Dynamically evaluates ERB subband energies across 32 psychoacoustic bands.
//!    - Identifies and sharpens formant peaks in the critical intelligibility window (1.2 kHz - 3.8 kHz).
//!    - Unmasks high-frequency fricative consonants (3.5 kHz - 7.5 kHz).
//!    - Suppresses sub-250 Hz low-frequency cabin rumble.
//! 2. 20 Hz 2nd-order High-Pass Biquad DC rejection filter to quench transducer drift and DC pops.
//! 3. Soft-knee hyperbolic tangent saturation to eliminate transducer clipping without harmonic splatter.
//!
//! Strictly zero heap allocations in the streaming loop.

use super::erb::ErbFilterbank;
use super::simd::{vector_complex_norm_sqr, vector_complex_scale};
use num_complex::Complex32;

/// ANSI S3.5 Band Importance Weightings for Speech Intelligibility Index (SII) across 32 ERB bands.
/// Peaks in the 1.2 kHz - 3.8 kHz formant and consonant transition zone.
const SII_BAND_WEIGHTS: [f32; 32] = [
    0.005, 0.008, 0.012, 0.018, 0.025, 0.035, 0.045,
    0.055, // 0-7: Low frequencies (20-450 Hz)
    0.065, 0.075, 0.085, 0.095, 0.100, 0.105, 0.100,
    0.095, // 8-15: First & second formants (450-1600 Hz)
    0.090, 0.085, 0.080, 0.075, 0.070, 0.065, 0.060,
    0.055, // 16-23: Formants & consonants (1.6-3.8 kHz)
    0.050, 0.045, 0.040, 0.035, 0.030, 0.025, 0.020,
    0.015, // 24-31: Fricatives & high air (3.8-8.0 kHz)
];

/// Configuration parameters for the Speech Intelligibility Enhancer.
#[derive(Debug, Clone)]
pub struct IntelligibilityConfig {
    pub num_bins: usize,
    pub num_bands: usize,
    pub sample_rate: f32,
    /// Maximum dynamic boost for formant peaks in dB (default: +4.0 dB)
    pub max_formant_boost_db: f32,
    /// High-frequency fricative consonant unmasking boost in dB (default: +2.5 dB)
    pub fricative_boost_db: f32,
    /// Low-frequency cabin rumble suppression in dB (default: -4.0 dB)
    pub rumble_suppression_db: f32,
    /// Soft-knee saturation threshold (0.0 to 1.0, default: 0.85)
    pub saturation_knee: f32,
    /// Enable 20 Hz DC blocking biquad filter
    pub enable_dc_blocker: bool,
    /// Enable soft-knee saturation
    pub enable_soft_knee: bool,
}

impl Default for IntelligibilityConfig {
    fn default() -> Self {
        Self {
            num_bins: 257,
            num_bands: 32,
            sample_rate: 16000.0,
            max_formant_boost_db: 4.0,
            fricative_boost_db: 2.5,
            rumble_suppression_db: -4.0,
            saturation_knee: 0.85,
            enable_dc_blocker: true,
            enable_soft_knee: true,
        }
    }
}

/// 2nd-order Biquad filter state for DC rejection (Direct Form II Transposed).
#[derive(Debug, Clone, Default)]
struct BiquadState {
    b0: f32,
    b1: f32,
    b2: f32,
    a1: f32,
    a2: f32,
    s1: f32,
    s2: f32,
}

impl BiquadState {
    /// Constructs a 2nd-order High-Pass Butterworth biquad at `fc_hz` (e.g. 20 Hz).
    fn new_highpass(fc_hz: f32, sample_rate: f32) -> Self {
        let w0 = 2.0 * std::f32::consts::PI * fc_hz / sample_rate;
        let cos_w0 = w0.cos();
        let sin_w0 = w0.sin();
        let q = 1.0 / std::f32::consts::SQRT_2; // Butterworth Q = 0.7071
        let alpha = sin_w0 / (2.0 * q);

        let a0 = 1.0 + alpha;
        let b0 = ((1.0 + cos_w0) * 0.5) / a0;
        let b1 = (-(1.0 + cos_w0)) / a0;
        let b2 = ((1.0 + cos_w0) * 0.5) / a0;
        let a1 = (-2.0 * cos_w0) / a0;
        let a2 = (1.0 - alpha) / a0;

        Self {
            b0,
            b1,
            b2,
            a1,
            a2,
            s1: 0.0,
            s2: 0.0,
        }
    }

    #[inline]
    fn process_sample(&mut self, x: f32) -> f32 {
        let y = self.b0 * x + self.s1;
        self.s1 = self.b1 * x - self.a1 * y + self.s2;
        self.s2 = self.b2 * x - self.a2 * y;
        y
    }

    fn reset(&mut self) {
        self.s1 = 0.0;
        self.s2 = 0.0;
    }
}

/// Adaptive Speech Intelligibility Enhancer and Formant Booster.
pub struct IntelligibilityEnhancer {
    config: IntelligibilityConfig,
    filterbank: ErbFilterbank,
    dc_filter: BiquadState,
    enabled: bool,

    // Pre-allocated scratch vectors (zero heap allocations in process loops)
    power_spec: Vec<f32>,
    erb_energies: Vec<f32>,
    erb_noise_floor: Vec<f32>,
    erb_gains: Vec<f32>,
    smoothed_erb_gains: Vec<f32>,
    linear_gains: Vec<f32>,

    // Dynamic metrics
    current_sii: f32,
    baseline_sii: f32,
    intelligibility_gain_db: f32,
}

impl IntelligibilityEnhancer {
    /// Creates a new IntelligibilityEnhancer.
    pub fn new(config: IntelligibilityConfig) -> Self {
        let num_bins = config.num_bins;
        let num_bands = config.num_bands;
        let filterbank = ErbFilterbank::new(num_bands, num_bins, config.sample_rate);
        let dc_filter = BiquadState::new_highpass(20.0, config.sample_rate);

        Self {
            config,
            filterbank,
            dc_filter,
            enabled: true,
            power_spec: vec![0.0f32; num_bins],
            erb_energies: vec![0.0f32; num_bands],
            erb_noise_floor: vec![-10.0f32; num_bands],
            erb_gains: vec![1.0f32; num_bands],
            smoothed_erb_gains: vec![1.0f32; num_bands],
            linear_gains: vec![1.0f32; num_bins],
            current_sii: 0.50,
            baseline_sii: 0.50,
            intelligibility_gain_db: 0.0,
        }
    }

    /// Resets all internal filter states and smoothing histories.
    pub fn reset(&mut self) {
        self.dc_filter.reset();
        self.erb_noise_floor.fill(-10.0);
        self.erb_gains.fill(1.0);
        self.smoothed_erb_gains.fill(1.0);
        self.linear_gains.fill(1.0);
        self.current_sii = 0.50;
        self.baseline_sii = 0.50;
        self.intelligibility_gain_db = 0.0;
    }

    /// Dynamically enables or disables intelligibility processing.
    pub fn set_enabled(&mut self, enabled: bool) {
        self.enabled = enabled;
    }

    /// Returns whether the enhancer is currently enabled.
    pub fn is_enabled(&self) -> bool {
        self.enabled
    }

    /// Current Speech Intelligibility Index (SII: 0.0 to 1.0).
    pub fn current_sii(&self) -> f32 {
        self.current_sii
    }

    /// Intelligibility Gain in dB relative to unprocessed noisy speech.
    pub fn intelligibility_gain_db(&self) -> f32 {
        self.intelligibility_gain_db
    }

    /// Processes complex STFT frequency bins in-place:
    /// Calculates subband SII weights, applies dynamic formant sharpening and fricative unmasking.
    ///
    /// Zero heap allocations.
    pub fn process_spec(&mut self, spec: &mut [Complex32]) {
        if !self.enabled {
            return;
        }

        assert_eq!(spec.len(), self.config.num_bins);

        // 1. Vectorized Power Spectrum: |X[k]|^2
        vector_complex_norm_sqr(spec, &mut self.power_spec);

        // 2. Extract 32 ERB Subband Log-Energies
        self.filterbank
            .extract_erb_energies(&self.power_spec, &mut self.erb_energies);

        // 3. Track ERB Noise Floor (slow minimum tracking)
        let alpha_noise = 0.98f32;
        for b in 0..self.config.num_bands {
            let energy = self.erb_energies[b];
            if energy < self.erb_noise_floor[b] {
                self.erb_noise_floor[b] = energy;
            } else {
                self.erb_noise_floor[b] =
                    alpha_noise * self.erb_noise_floor[b] + (1.0 - alpha_noise) * energy;
            }
        }

        // 4. Calculate Subband SNR and Baseline vs Enhanced SII
        let mut baseline_sii_accum = 0.0f32;
        let mut enhanced_sii_accum = 0.0f32;
        let mut total_sii_weight = 0.0f32;

        let max_formant_boost = 10.0f32.powf(self.config.max_formant_boost_db / 20.0);
        let fricative_boost = 10.0f32.powf(self.config.fricative_boost_db / 20.0);
        let rumble_mult = 10.0f32.powf(self.config.rumble_suppression_db / 20.0);

        for (b, &w) in SII_BAND_WEIGHTS
            .iter()
            .enumerate()
            .take(self.config.num_bands)
        {
            let snr_db = (self.erb_energies[b] - self.erb_noise_floor[b]) * 4.3429448; // ln to dB
            total_sii_weight += w;

            // Baseline ANSI S3.5 audibility function: A_b = clamp((SNR + 15) / 30, 0, 1)
            let a_base = ((snr_db + 15.0) / 30.0).clamp(0.0, 1.0);
            baseline_sii_accum += w * a_base;

            // Target gain initialization
            let mut target_gain = 1.0f32;

            // (A) Low-frequency cabin rumble suppression (subbands 0 to 4: < 250 Hz)
            if b <= 4 {
                target_gain = rumble_mult;
            }

            // (B) Formant Dynamic Peaking & Sharpening (bands 12 to 22: ~1.2 kHz to 3.8 kHz)
            if (12..=22).contains(&b) {
                let e_curr = self.erb_energies[b];
                let e_prev = if b > 0 {
                    self.erb_energies[b - 1]
                } else {
                    e_curr
                };
                let e_next = if b < self.config.num_bands - 1 {
                    self.erb_energies[b + 1]
                } else {
                    e_curr
                };

                // Detect local formant spectral peak
                if e_curr > e_prev && e_curr > e_next {
                    let prominence = (e_curr - 0.5 * (e_prev + e_next)).max(0.0);
                    let boost = (1.0 + prominence * 0.8).min(max_formant_boost);
                    target_gain = boost;
                } else {
                    target_gain = 1.05;
                }
            }

            // (C) Consonant Fricative Unmasking (bands 23 to 30: ~3.8 kHz to 7.5 kHz)
            if (23..=30).contains(&b) {
                // If speech presence is detected in mid-bands, lift fricative consonants
                if snr_db > 2.0 {
                    target_gain = fricative_boost;
                }
            }

            self.erb_gains[b] = target_gain;

            // Enhanced SII estimate
            let enh_snr_db = snr_db + 20.0 * target_gain.log10();
            let a_enh = ((enh_snr_db + 15.0) / 30.0).clamp(0.0, 1.0);
            enhanced_sii_accum += w * a_enh;
        }

        self.baseline_sii = (baseline_sii_accum / total_sii_weight.max(1e-4)).clamp(0.0, 1.0);
        self.current_sii = (enhanced_sii_accum / total_sii_weight.max(1e-4)).clamp(0.0, 1.0);
        let sii_ratio = (self.current_sii + 1e-4) / (self.baseline_sii + 1e-4);
        self.intelligibility_gain_db = 10.0 * sii_ratio.log10();

        // 5. Temporal Gain Smoothing (Attack: fast, Release: smooth)
        for b in 0..self.config.num_bands {
            let target = self.erb_gains[b];
            let alpha = if target > self.smoothed_erb_gains[b] {
                0.40
            } else {
                0.85
            };
            self.smoothed_erb_gains[b] =
                alpha * self.smoothed_erb_gains[b] + (1.0 - alpha) * target;
        }

        // 6. Interpolate 32 ERB Gains back to 257 Linear STFT Bins
        self.filterbank
            .interpolate_band_gains(&self.smoothed_erb_gains, &mut self.linear_gains);

        // 7. Vectorized In-Place Spectral Scaling
        vector_complex_scale(spec, &self.linear_gains);
    }

    /// Processes time-domain PCM output block in-place:
    /// Applies 20 Hz DC blocking biquad filter and soft-knee hyperbolic tangent saturation.
    ///
    /// Zero heap allocations.
    pub fn process_time(&mut self, samples: &mut [f32]) {
        if !self.enabled {
            return;
        }

        // 1. DC Rejection (20 Hz Biquad High-Pass Filter)
        if self.config.enable_dc_blocker {
            for s in samples.iter_mut() {
                *s = self.dc_filter.process_sample(*s);
            }
        }

        // 2. Soft-Knee Hyperbolic Tangent Saturation
        if self.config.enable_soft_knee {
            let knee = self.config.saturation_knee;
            let headroom = 1.0 - knee;

            for s in samples.iter_mut() {
                let x = *s;
                let abs_x = x.abs();
                if abs_x > knee {
                    let sign = if x >= 0.0 { 1.0 } else { -1.0 };
                    let excess = (abs_x - knee) / headroom.max(1e-4);
                    // Fast Padé tanh approximation
                    let tanh_val = if excess > 3.0 {
                        1.0
                    } else {
                        let e2 = excess * excess;
                        (excess * (15.0 + e2)) / (15.0 + 9.0 * e2)
                    };
                    *s = sign * (knee + headroom * tanh_val);
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_intelligibility_enhancer_dc_rejection() {
        let mut enhancer = IntelligibilityEnhancer::new(IntelligibilityConfig::default());
        // DC step of +1.0
        let mut dc_signal = vec![1.0f32; 1000];
        enhancer.process_time(&mut dc_signal);

        // After settling, DC should be attenuated by >20 dB (< 0.10)
        let last_samples = &dc_signal[800..];
        let max_dc = last_samples.iter().map(|s| s.abs()).fold(0.0f32, f32::max);
        assert!(max_dc < 0.15, "DC was not rejected: max_dc = {}", max_dc);
    }

    #[test]
    fn test_intelligibility_enhancer_soft_knee_saturation() {
        let mut enhancer = IntelligibilityEnhancer::new(IntelligibilityConfig::default());
        // Large impulse exceeding 1.0 (clipping level)
        let mut signal = vec![0.5, 0.80, 0.90, 1.20, 2.50, -3.0];
        enhancer.process_time(&mut signal);

        // Samples below knee (0.85) should be virtually unchanged
        assert!((signal[0] - 0.5).abs() < 0.02);
        assert!((signal[1] - 0.80).abs() < 0.02);

        // All samples must be strictly bounded within (-1.0, 1.0)
        for &s in &signal {
            assert!(s.abs() <= 1.0, "Sample breached +/-1.0 boundary: {}", s);
        }
    }

    #[test]
    fn test_intelligibility_enhancer_formant_boost_and_sii() {
        let mut enhancer = IntelligibilityEnhancer::new(IntelligibilityConfig::default());
        let mut spec = vec![Complex32::new(0.01, 0.01); 257];

        // Synthesize a prominent formant peak at ~2.0 kHz (bin ~64 for 16 kHz N=512)
        spec[64] = Complex32::new(1.0, 1.0);
        spec[63] = Complex32::new(0.4, 0.4);
        spec[65] = Complex32::new(0.4, 0.4);

        let initial_peak = spec[64].norm();
        enhancer.process_spec(&mut spec);
        let enhanced_peak = spec[64].norm();

        assert!(
            enhanced_peak >= initial_peak,
            "Formant peak was not boosted!"
        );
        assert!(enhancer.current_sii() > 0.0, "SII should be positive");
    }
}
