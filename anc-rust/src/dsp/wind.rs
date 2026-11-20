//! Dynamic Wind Noise Acoustic Turbulence Detector & Aero-Acoustic De-Rumbling Filter.
//!
//! Wind noise is convective air turbulence vortex shedding directly on microphone diaphragms (< 250 Hz).
//! The dual microphones (30 mm tactical array spacing) experience completely uncorrelated vortex
//! turbulence (zero inter-channel coherence: \gamma_12(f) ~ 0), whereas true acoustic speech and
//! ambient acoustic sound propagate as waves and remain highly correlated at low frequencies.
//!
//! Features:
//! - Real-time Wind Turbulence Index (WTI) tracking from cross-spectral vs auto-spectral densities:
//!   WTI(f) = 1.0 - |\Phi_12(f)| / \sqrt{\Phi_11(f) \cdot \Phi_22(f)}
//! - Infrasonic (< 250 Hz) aero-acoustic turbulence identification
//! - Speech Pitch Harmonic (F0) Protection: preserves vocal pitch fundamental and harmonics
//!   even when falling below 250 Hz (e.g. 100-240 Hz vowels) while suppressing turbulent rumble
//! - Inter-sensor wind desensitization against differential buffeting
//! - Strictly ZERO heap allocations in real-time `process_frame`.

use num_complex::Complex32;

/// Telemetry metrics produced by the Wind Turbulence Detector.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct WindTelemetry {
    /// Aggregate Wind Turbulence Index in the low-frequency band [0.0, 1.0]
    pub mean_wti: f32,
    /// Whether wind turbulence vortex shedding is actively detected (WTI > threshold)
    pub wind_detected: bool,
    /// Low-frequency band power in dBFS
    pub low_freq_power_db: f32,
    /// Applied suppression attenuation in dB (e.g. 0.0 dB to -24.0 dB)
    pub suppression_db: f32,
}

impl Default for WindTelemetry {
    fn default() -> Self {
        Self {
            mean_wti: 0.0,
            wind_detected: false,
            low_freq_power_db: -90.0,
            suppression_db: 0.0,
        }
    }
}

/// Configuration parameters for the Wind Turbulence Suppressor.
#[derive(Debug, Clone)]
pub struct WindDetectorConfig {
    /// Number of STFT frequency bins (n_fft / 2 + 1)
    pub num_bins: usize,
    /// Audio sampling rate in Hz (default: 16000.0)
    pub sample_rate: f32,
    /// Turbulence detection low-frequency cutoff in Hz (default: 250.0 Hz)
    pub cutoff_hz: f32,
    /// Wind Turbulence Index threshold to trigger suppression (default: 0.85)
    pub wti_threshold: f32,
    /// Recursive PSD smoothing / forgetting factor (default: 0.85)
    pub alpha_smooth: f32,
    /// Maximum de-rumbling suppression attenuation in dB (default: -24.0 dB)
    pub max_attenuation_db: f32,
    /// Bandwidth around F0 and harmonics to protect from suppression in Hz (default: 22.0 Hz)
    pub f0_protect_bandwidth_hz: f32,
    /// Minimum low-frequency power to trigger detection (default: 1e-5 / -50 dBFS)
    pub min_power_threshold: f32,
}

impl Default for WindDetectorConfig {
    fn default() -> Self {
        Self {
            num_bins: 257,
            sample_rate: 16000.0,
            cutoff_hz: 250.0,
            wti_threshold: 0.85,
            alpha_smooth: 0.85,
            max_attenuation_db: -24.0,
            f0_protect_bandwidth_hz: 22.0,
            min_power_threshold: 1e-5,
        }
    }
}

/// Zero-allocation Dynamic Wind Noise Acoustic Turbulence Detector & Aero-Acoustic De-Rumbling Filter.
pub struct WindTurbulenceSuppressor {
    pub config: WindDetectorConfig,

    // Preallocated recursive spectral density states [num_bins]
    phi11: Vec<f32>,
    phi22: Vec<f32>,
    phi12: Vec<Complex32>,

    // Preallocated per-bin output arrays [num_bins]
    wti_bins: Vec<f32>,
    suppression_gains: Vec<f32>,

    // Frequency metadata
    bin_hz: f32,
    cutoff_bin: usize,

    // Cached smoothed metrics
    smoothed_wti: f32,
    is_wind_active: bool,
    current_suppression_db: f32,
    frames_processed: u64,
}

impl WindTurbulenceSuppressor {
    /// Creates a new zero-allocation WindTurbulenceSuppressor.
    pub fn new(config: WindDetectorConfig) -> Self {
        let num_bins = config.num_bins;
        let bin_hz = config.sample_rate / (2.0 * (num_bins - 1) as f32);
        let cutoff_bin = ((config.cutoff_hz / bin_hz).ceil() as usize).clamp(1, num_bins - 1);

        Self {
            config,
            phi11: vec![1e-5f32; num_bins],
            phi22: vec![1e-5f32; num_bins],
            phi12: vec![Complex32::default(); num_bins],
            wti_bins: vec![0.0f32; num_bins],
            suppression_gains: vec![1.0f32; num_bins],
            bin_hz,
            cutoff_bin,
            smoothed_wti: 0.0,
            is_wind_active: false,
            current_suppression_db: 0.0,
            frames_processed: 0,
        }
    }

    /// Resets all internal spectral densities and tracking states.
    pub fn reset(&mut self) {
        self.phi11.fill(1e-5);
        self.phi22.fill(1e-5);
        self.phi12.fill(Complex32::default());
        self.wti_bins.fill(0.0);
        self.suppression_gains.fill(1.0);
        self.smoothed_wti = 0.0;
        self.is_wind_active = false;
        self.current_suppression_db = 0.0;
        self.frames_processed = 0;
    }

    /// Returns the current aggregate Wind Turbulence Index [0.0, 1.0].
    pub fn current_wti(&self) -> f32 {
        self.smoothed_wti
    }

    /// Returns whether wind turbulence is currently detected.
    pub fn is_wind_detected(&self) -> bool {
        self.is_wind_active
    }

    /// Returns current suppression attenuation in dB.
    pub fn suppression_db(&self) -> f32 {
        self.current_suppression_db
    }

    /// Processes an STFT frame of dual-microphone spectra with zero heap allocations.
    ///
    /// - `spec_mic1`: Primary speech microphone spectrum (modified in-place if wind is suppressed).
    /// - `spec_mic2`: Secondary reference microphone spectrum (read-only for cross-spectral coherence).
    /// - `f0`: Optional tracked speech pitch fundamental frequency in Hz (for formant protection).
    pub fn process_frame(
        &mut self,
        spec_mic1: &mut [Complex32],
        spec_mic2: &[Complex32],
        f0: Option<f32>,
    ) -> WindTelemetry {
        assert_eq!(spec_mic1.len(), self.config.num_bins);
        assert_eq!(spec_mic2.len(), self.config.num_bins);

        self.frames_processed += 1;
        let alpha = self.config.alpha_smooth;
        let beta = 1.0 - alpha;

        let mut low_freq_pwr = 0.0f32;
        let mut weighted_wti_sum = 0.0f32;
        let mut total_weight = 0.0f32;

        // 1. Update auto- and cross-spectral densities and compute per-bin WTI
        for k in 0..self.config.num_bins {
            let x1 = spec_mic1[k];
            let x2 = spec_mic2[k];

            let p1 = x1.norm_sqr().max(1e-9);
            let p2 = x2.norm_sqr().max(1e-9);
            let cross = x1 * x2.conj();

            self.phi11[k] = alpha * self.phi11[k] + beta * p1;
            self.phi22[k] = alpha * self.phi22[k] + beta * p2;
            self.phi12[k] = self.phi12[k] * alpha + cross * beta;

            let denom = (self.phi11[k] * self.phi22[k]).max(1e-8);
            let coh_sq = (self.phi12[k].norm_sqr() / denom).clamp(0.0, 1.0);
            let wti = (1.0 - coh_sq).clamp(0.0, 1.0);
            self.wti_bins[k] = wti;

            // Accumulate low-frequency turbulence statistics (< cutoff_hz)
            if k > 0 && k <= self.cutoff_bin {
                let bin_pwr = (self.phi11[k] + self.phi22[k]) * 0.5;
                low_freq_pwr += bin_pwr;
                weighted_wti_sum += wti * bin_pwr;
                total_weight += bin_pwr;
            }
        }

        let mean_low_wti = if total_weight > 1e-8 {
            weighted_wti_sum / total_weight
        } else {
            0.0
        };

        // Aggregate low-frequency WTI from recursive spectral densities
        self.smoothed_wti = mean_low_wti;

        let avg_bin_pwr = low_freq_pwr / self.cutoff_bin.max(1) as f32;
        let low_pwr_db = 10.0 * (avg_bin_pwr + 1e-12).log10();

        // 2. Wind Detection Decision
        let has_wind_energy = avg_bin_pwr >= self.config.min_power_threshold;
        let wind_detected = has_wind_energy && (self.smoothed_wti >= self.config.wti_threshold);
        self.is_wind_active = wind_detected;

        if !wind_detected {
            self.suppression_gains.fill(1.0);
            self.current_suppression_db = 0.0;
            return WindTelemetry {
                mean_wti: self.smoothed_wti,
                wind_detected: false,
                low_freq_power_db: low_pwr_db,
                suppression_db: 0.0,
            };
        }

        // 3. Compute De-Rumbling Suppression Gains with Speech Pitch Harmonic Protection
        let min_linear_gain = 10.0f32.powf(self.config.max_attenuation_db / 20.0);
        let mut applied_gain_sum = 0.0f32;
        let mut gain_count = 0usize;

        for k in 0..self.config.num_bins {
            if k == 0 {
                // DC bin is completely notched if wind is active
                self.suppression_gains[k] = min_linear_gain * 0.1;
                spec_mic1[k] *= self.suppression_gains[k];
                continue;
            }

            if k <= self.cutoff_bin {
                let freq = k as f32 * self.bin_hz;

                // Check for Speech Pitch Harmonic (F0) Protection
                let mut is_near_harmonic = false;
                if let Some(pitch_hz) = f0 {
                    if (60.0..=450.0).contains(&pitch_hz) {
                        // Check F0, 2*F0, 3*F0...
                        let mut harm = pitch_hz;
                        while harm <= self.config.cutoff_hz + self.config.f0_protect_bandwidth_hz {
                            if (freq - harm).abs() <= self.config.f0_protect_bandwidth_hz {
                                is_near_harmonic = true;
                                break;
                            }
                            harm += pitch_hz;
                        }
                    }
                }

                let gain = if is_near_harmonic {
                    // Preserve speech formant harmonic with minimal attenuation
                    1.0f32
                } else {
                    // Suppress convective turbulence: severity scales with WTI above threshold
                    let severity = ((self.wti_bins[k] - 0.70) / 0.30).clamp(0.0, 1.0);
                    let target_gain = 1.0 - severity * (1.0 - min_linear_gain);
                    // Also account for sensor imbalance (desensitization)
                    let p1 = self.phi11[k];
                    let p2 = self.phi22[k];
                    let imbalance_factor = if p1 > 2.0 * p2 {
                        // Mic 1 buffeted more than Mic 2
                        (p2 / p1).sqrt().clamp(min_linear_gain, 1.0)
                    } else {
                        1.0
                    };
                    (target_gain * imbalance_factor).clamp(min_linear_gain, 1.0)
                };

                self.suppression_gains[k] = gain;
                spec_mic1[k] *= gain;
                applied_gain_sum += gain;
                gain_count += 1;
            } else {
                self.suppression_gains[k] = 1.0;
            }
        }

        let mean_applied_gain = if gain_count > 0 {
            applied_gain_sum / gain_count as f32
        } else {
            1.0
        };
        self.current_suppression_db = 20.0 * (mean_applied_gain.max(1e-4)).log10();

        WindTelemetry {
            mean_wti: self.smoothed_wti,
            wind_detected,
            low_freq_power_db: low_pwr_db,
            suppression_db: self.current_suppression_db,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::f32::consts::PI;

    #[test]
    fn test_wind_detector_identifies_uncorrelated_turbulence() {
        let config = WindDetectorConfig {
            num_bins: 257,
            sample_rate: 16000.0,
            cutoff_hz: 250.0,
            wti_threshold: 0.85,
            alpha_smooth: 0.85,
            max_attenuation_db: -24.0,
            f0_protect_bandwidth_hz: 20.0,
            min_power_threshold: 1e-4,
        };
        let mut wind = WindTurbulenceSuppressor::new(config);

        let mut spec1 = vec![Complex32::default(); 257];
        let mut spec2 = vec![Complex32::default(); 257];

        // Simulate 80 frames (~1.2s) of completely uncorrelated random phase noise at low frequencies (convective turbulence)
        let mut seed: u64 = 0x12345678;
        for _ in 0..80 {
            for k in 1..=8 {
                seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
                let phase1 = (seed as f32 / u64::MAX as f32) * 2.0 * PI;
                seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
                let phase2 = (seed as f32 / u64::MAX as f32) * 2.0 * PI;

                spec1[k] = Complex32::from_polar(0.5, phase1);
                spec2[k] = Complex32::from_polar(0.5, phase2);
            }
            wind.process_frame(&mut spec1, &spec2, None);
        }

        assert!(wind.current_wti() > 0.85, "Expected high WTI for uncorrelated turbulence, got {:.3}", wind.current_wti());
        assert!(wind.is_wind_detected());
    }

    #[test]
    fn test_wind_detector_preserves_correlated_speech_sound() {
        let config = WindDetectorConfig::default();
        let mut wind = WindTurbulenceSuppressor::new(config);

        let mut spec1 = vec![Complex32::default(); 257];
        let mut spec2 = vec![Complex32::default(); 257];

        // Simulate broadside acoustic sound (coherent across both mics: spec1 == spec2)
        for _ in 0..25 {
            for k in 1..=8 {
                let comp = Complex32::new(0.4, 0.3);
                spec1[k] = comp;
                spec2[k] = comp;
            }
            let telem = wind.process_frame(&mut spec1, &spec2, None);
            assert!(!telem.wind_detected);
        }

        assert!(wind.current_wti() < 0.15, "Expected near-zero WTI for coherent sound, got {:.3}", wind.current_wti());
        assert!(!wind.is_wind_detected());
        assert!(wind.suppression_db() >= -0.5);
    }

    #[test]
    fn test_f0_pitch_harmonic_protection_preserves_vowel_fundamental() {
        let config = WindDetectorConfig {
            num_bins: 257,
            sample_rate: 16000.0,
            cutoff_hz: 250.0,
            wti_threshold: 0.80,
            alpha_smooth: 0.85,
            max_attenuation_db: -24.0,
            f0_protect_bandwidth_hz: 18.0,
            min_power_threshold: 1e-4,
        };
        let mut wind = WindTurbulenceSuppressor::new(config);

        // Speech pitch F0 = 125 Hz (bin 4 at 16000/512 = 31.25 Hz/bin)
        let f0 = 125.0f32;
        let mut spec1 = vec![Complex32::default(); 257];
        let mut spec2 = vec![Complex32::default(); 257];

        let mut seed: u64 = 0x99999999;
        for _ in 0..80 {
            // High convective wind turbulence across low frequencies
            for k in 1..=8 {
                seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
                let p1 = (seed as f32 / u64::MAX as f32) * 2.0 * PI;
                seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
                let p2 = (seed as f32 / u64::MAX as f32) * 2.0 * PI;
                spec1[k] = Complex32::from_polar(0.8, p1);
                spec2[k] = Complex32::from_polar(0.8, p2);
            }

            // Injected vocal pitch harmonic at bin 4 (125 Hz)
            spec1[4] = Complex32::new(0.5, 0.0);
            spec2[4] = Complex32::new(0.5, 0.0);

            wind.process_frame(&mut spec1, &spec2, Some(f0));
        }

        // Bin 4 (F0 = 125 Hz) should be protected (gain ~ 1.0, preserving speech harmonic)
        assert!(spec1[4].norm() > 0.45, "F0 harmonic at 125 Hz should be protected, got {:.3}", spec1[4].norm());
        // Bin 2 (62.5 Hz, non-harmonic turbulence) should be notched
        assert!(spec1[2].norm() < 0.25, "Uncorrelated non-harmonic bin should be attenuated, got {:.3}", spec1[2].norm());
    }
}
