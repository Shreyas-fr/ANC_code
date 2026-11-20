//! Real-Time Total Harmonic Distortion (THD+N) & Transducer Voice-Coil Health Analyzer.
//!
//! Developed for SIH 26052 Tactical Audio Systems.
//!
//! In high-stress combat vehicle headsets and tactical pilot helmets, transducers operate
//! under extreme acoustic sound pressure levels (up to 115-130 dB SPL).
//!
//! Physical hardware failure modes include:
//! 1. Transducer Non-Linear Saturation: Over-excursion of the speaker diaphragm beyond
//!    its linear magnetic flux gap, producing severe 2nd and 3rd harmonic distortion.
//! 2. Voice-Coil Overheating / Thermal Compression: Voice coil temperature spikes
//!    (increasing DC resistance $R_e$), resulting in power compression and elevated odd harmonics.
//! 3. Ear Cushion Acoustic Seal Leakage: Ballistic helmet movement or eyeglass frame breaks
//!    the ear cushion seal, causing severe low-frequency bass loss and resonant distortion.
//!
//! This module continuously monitors output audio frames:
//! - Identifies fundamental voice/test frequency $F_0$ (70–500 Hz).
//! - Measures fundamental energy $P_{\text{fund}}$ vs 2nd, 3rd, 4th, 5th harmonics ($P_2, P_3, P_4, P_5$).
//! - Measures residual inter-harmonic noise floor $P_{\text{noise}}$.
//! - Calculates instantaneous and smoothed THD and THD+N:
//!   $$\text{THD} = \frac{\sqrt{\sum_{k=2}^5 P_k}}{\sqrt{P_{\text{fund}}} + \epsilon}$$
//!   $$\text{THD+N} = \frac{\sqrt{\sum_{k=2}^5 P_k + P_{\text{noise}}}}{\sqrt{P_{\text{fund}}} + \epsilon}$$
//! - Flags transducer degradation before speech intelligibility is compromised.
//! - Strictly ZERO heap allocations in real-time execution.

use rustfft::{num_complex::Complex, Fft, FftPlanner};
use std::sync::Arc;

pub const DEFAULT_ANALYZER_FFT_SIZE: usize = 512;
pub const MAX_SPECTRUM_BINS: usize = DEFAULT_ANALYZER_FFT_SIZE / 2 + 1;

/// Health and fault state of the tactical headset transducer / driver voice coil.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum VoiceCoilHealthStatus {
    /// Transducer operating nominally with low distortion (< 2.0% THD).
    #[default]
    Nominal,
    /// Non-linear diaphragm excursion or magnetic flux saturation (THD > 8.0%).
    SaturationWarning,
    /// Ear cushion seal leakage causing acoustic coupling breakdown.
    AcousticLeakage,
    /// Voice coil thermal stress / power compression (elevated odd harmonics).
    ThermalStress,
}

/// Configuration for real-time THD+N and transducer health analysis.
#[derive(Debug, Clone, Copy)]
pub struct DistortionConfig {
    pub sample_rate: f32,
    pub fft_size: usize,
    pub min_f0_hz: f32,
    pub max_f0_hz: f32,
    pub smoothing_alpha: f32,
    pub saturation_thd_threshold: f32,
    pub thermal_thd_threshold: f32,
    pub min_signal_power: f32,
}

impl Default for DistortionConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000.0,
            fft_size: DEFAULT_ANALYZER_FFT_SIZE,
            min_f0_hz: 75.0,
            max_f0_hz: 500.0,
            smoothing_alpha: 0.90,
            saturation_thd_threshold: 0.08, // 8% THD
            thermal_thd_threshold: 0.05,    // 5% THD
            min_signal_power: 1e-5,
        }
    }
}

/// Instantaneous distortion telemetry and voice-coil health metrics.
#[derive(Debug, Clone, Copy, Default)]
pub struct DistortionMetrics {
    /// Fundamental Frequency F0 in Hertz.
    pub f0_hz: f32,
    /// Power of fundamental F0.
    pub p_fund: f32,
    /// Powers of harmonics: [2*F0, 3*F0, 4*F0, 5*F0].
    pub p_harmonics: [f32; 4],
    /// Power of residual noise floor.
    pub p_noise: f32,
    /// Total Harmonic Distortion (ratio, e.g. 0.015 = 1.5%).
    pub thd: f32,
    /// THD expressed in decibels ($20 \log_{10}(\text{THD})$).
    pub thd_db: f32,
    /// Total Harmonic Distortion + Noise (ratio).
    pub thd_plus_n: f32,
    /// THD+N expressed in decibels.
    pub thd_plus_n_db: f32,
    /// Transducer health score (0.0 to 100.0%).
    pub health_score: f32,
    /// Transducer voice-coil diagnostic status.
    pub status: VoiceCoilHealthStatus,
}

/// Zero-allocation Real-Time THD+N & Transducer Voice-Coil Health Analyzer.
pub struct DistortionAnalyzer {
    config: DistortionConfig,
    fft: Arc<dyn Fft<f32>>,
    window: [f32; DEFAULT_ANALYZER_FFT_SIZE],
    fft_buffer: [Complex<f32>; DEFAULT_ANALYZER_FFT_SIZE],
    power_spectrum: [f32; MAX_SPECTRUM_BINS],
    smoothed_thd: f32,
    smoothed_thd_plus_n: f32,
    smoothed_health_score: f32,
    last_status: VoiceCoilHealthStatus,
    frame_count: u64,
}

impl DistortionAnalyzer {
    /// Creates a new DistortionAnalyzer with pre-allocated FFT and scratch buffers.
    pub fn new(config: DistortionConfig) -> Self {
        let mut planner = FftPlanner::new();
        let fft = planner.plan_fft_forward(config.fft_size);

        // Precompute Hann window
        let mut window = [0.0f32; DEFAULT_ANALYZER_FFT_SIZE];
        let n = config.fft_size;
        for (i, w) in window.iter_mut().enumerate().take(n) {
            *w = 0.5 * (1.0 - (2.0 * std::f32::consts::PI * i as f32 / n as f32).cos());
        }

        Self {
            config,
            fft,
            window,
            fft_buffer: [Complex::new(0.0, 0.0); DEFAULT_ANALYZER_FFT_SIZE],
            power_spectrum: [0.0f32; MAX_SPECTRUM_BINS],
            smoothed_thd: 0.0,
            smoothed_thd_plus_n: 0.0,
            smoothed_health_score: 100.0,
            last_status: VoiceCoilHealthStatus::Nominal,
            frame_count: 0,
        }
    }

    /// Resets all historical rolling averages and status flags.
    pub fn reset(&mut self) {
        self.smoothed_thd = 0.0;
        self.smoothed_thd_plus_n = 0.0;
        self.smoothed_health_score = 100.0;
        self.last_status = VoiceCoilHealthStatus::Nominal;
        self.frame_count = 0;
    }

    /// Analyzes an output time-domain frame (e.g. 256 or 512 samples) with zero heap allocations.
    pub fn process_frame(&mut self, samples: &[f32]) -> DistortionMetrics {
        let n = self.config.fft_size;
        let len = samples.len().min(n);

        // Window and load into pre-allocated FFT buffer
        for i in 0..len {
            self.fft_buffer[i] = Complex::new(samples[i] * self.window[i], 0.0);
        }
        for i in len..n {
            self.fft_buffer[i] = Complex::new(0.0, 0.0);
        }

        // Execute in-place forward FFT
        self.fft.process(&mut self.fft_buffer);

        // Compute power spectrum
        let num_bins = n / 2 + 1;
        let scale = 1.0 / (n as f32);
        for i in 0..num_bins {
            let re = self.fft_buffer[i].re * scale;
            let im = self.fft_buffer[i].im * scale;
            self.power_spectrum[i] = re * re + im * im;
        }

        self.analyze_internal(num_bins, None)
    }

    /// Analyzes a pre-calculated power spectrum directly (with optional known F0).
    pub fn process_spectrum(
        &mut self,
        power_spectrum: &[f32],
        known_f0: Option<f32>,
    ) -> DistortionMetrics {
        let num_bins = power_spectrum.len().min(MAX_SPECTRUM_BINS);
        self.power_spectrum[..num_bins].copy_from_slice(&power_spectrum[..num_bins]);
        self.analyze_internal(num_bins, known_f0)
    }

    /// Internal distortion calculation and health diagnostics.
    fn analyze_internal(&mut self, num_bins: usize, known_f0: Option<f32>) -> DistortionMetrics {
        let bin_hz = self.config.sample_rate / self.config.fft_size as f32;

        let min_bin = ((self.config.min_f0_hz / bin_hz).floor() as usize).max(1);
        let max_bin = ((self.config.max_f0_hz / bin_hz).ceil() as usize).min(num_bins - 1);

        // 1. Locate fundamental frequency F0
        let (f0_bin, f0_hz) = if let Some(f0) = known_f0 {
            let bin = ((f0 / bin_hz).round() as usize).clamp(min_bin, max_bin);
            (bin, f0)
        } else {
            // Find peak bin in F0 search range
            let mut best_bin = min_bin;
            let mut best_p = 0.0f32;
            for (b, &p) in self.power_spectrum[..num_bins]
                .iter()
                .enumerate()
                .take(max_bin + 1)
                .skip(min_bin)
            {
                if p > best_p {
                    best_p = p;
                    best_bin = b;
                }
            }
            (best_bin, best_bin as f32 * bin_hz)
        };

        // Integrate energy in 3-bin window around a bin to capture spectral leakage
        let start_bin = f0_bin.saturating_sub(1);
        let end_bin = (f0_bin + 2).min(num_bins);
        let mut p_fund = 0.0f32;
        for b in start_bin..end_bin {
            p_fund += self.power_spectrum[b];
        }

        // If signal power is below threshold, return nominal clean metrics
        if p_fund < self.config.min_signal_power {
            return DistortionMetrics {
                f0_hz,
                p_fund,
                p_harmonics: [0.0; 4],
                p_noise: 0.0,
                thd: 0.0,
                thd_db: -90.0,
                thd_plus_n: 0.0,
                thd_plus_n_db: -90.0,
                health_score: self.smoothed_health_score,
                status: VoiceCoilHealthStatus::Nominal,
            };
        }

        // 2. Measure harmonics (2*F0, 3*F0, 4*F0, 5*F0)
        let mut p_harmonics = [0.0f32; 4];
        let mut sum_harm_p = 0.0f32;

        for (idx, order) in [2, 3, 4, 5].iter().enumerate() {
            let harm_bin = ((f0_hz * (*order as f32) / bin_hz).round() as usize).min(num_bins - 1);
            if harm_bin < num_bins {
                let h_start = harm_bin.saturating_sub(1);
                let h_end = (harm_bin + 2).min(num_bins);
                let mut harm_p = 0.0f32;
                for b in h_start..h_end {
                    harm_p += self.power_spectrum[b];
                }
                p_harmonics[idx] = harm_p;
                sum_harm_p += harm_p;
            }
        }

        // 3. Measure total power and residual noise floor
        let total_power: f32 = self.power_spectrum[1..num_bins].iter().sum();
        let p_noise = (total_power - p_fund - sum_harm_p).max(0.0);

        // 4. Calculate THD and THD+N
        let eps = 1e-9f32;
        let raw_thd = (sum_harm_p / (p_fund + eps)).sqrt();
        let raw_thd_plus_n = ((sum_harm_p + p_noise) / (p_fund + eps)).sqrt();

        // Exponential smoothing
        let alpha = self.config.smoothing_alpha;
        if self.frame_count == 0 {
            self.smoothed_thd = raw_thd;
            self.smoothed_thd_plus_n = raw_thd_plus_n;
        } else {
            self.smoothed_thd = alpha * self.smoothed_thd + (1.0 - alpha) * raw_thd;
            self.smoothed_thd_plus_n =
                alpha * self.smoothed_thd_plus_n + (1.0 - alpha) * raw_thd_plus_n;
        }

        let thd = self.smoothed_thd;
        let thd_plus_n = self.smoothed_thd_plus_n;

        let thd_db = (20.0 * thd.max(1e-5).log10()).clamp(-90.0, 10.0);
        let thd_plus_n_db = (20.0 * thd_plus_n.max(1e-5).log10()).clamp(-90.0, 10.0);

        // 5. Diagnostics & Voice-Coil Health Classification
        // Status evaluation:
        let p2 = p_harmonics[0];
        let p3 = p_harmonics[1];

        let status = if thd >= self.config.saturation_thd_threshold {
            VoiceCoilHealthStatus::SaturationWarning
        } else if thd >= self.config.thermal_thd_threshold && p3 > p2 * 1.3 {
            // Elevated 3rd harmonic without gross clipping indicates thermal compression
            VoiceCoilHealthStatus::ThermalStress
        } else if f0_hz < 120.0 && p_fund < total_power * 0.15 && thd > 0.04 {
            VoiceCoilHealthStatus::AcousticLeakage
        } else {
            VoiceCoilHealthStatus::Nominal
        };

        self.last_status = status;

        // Health score (100% down to 0%)
        let instant_score = (100.0 - thd * 600.0).clamp(0.0, 100.0);
        self.smoothed_health_score =
            alpha * self.smoothed_health_score + (1.0 - alpha) * instant_score;
        self.frame_count += 1;

        DistortionMetrics {
            f0_hz,
            p_fund,
            p_harmonics,
            p_noise,
            thd,
            thd_db,
            thd_plus_n,
            thd_plus_n_db,
            health_score: self.smoothed_health_score,
            status,
        }
    }

    /// Returns the last diagnosed voice-coil health status.
    pub fn status(&self) -> VoiceCoilHealthStatus {
        self.last_status
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::f32::consts::PI;

    #[test]
    fn test_thd_analyzer_pure_sine_low_distortion() {
        let config = DistortionConfig::default();
        let mut analyzer = DistortionAnalyzer::new(config);

        // Generate pure 250 Hz sine wave
        let n = 512;
        let mut samples = vec![0.0f32; n];
        for (i, s) in samples.iter_mut().enumerate() {
            *s = (2.0 * PI * 250.0 * (i as f32) / 16000.0).sin();
        }

        let mut metrics = DistortionMetrics::default();
        for _ in 0..15 {
            metrics = analyzer.process_frame(&samples);
        }

        assert!((metrics.f0_hz - 250.0).abs() < 35.0);
        assert!(
            metrics.thd < 0.02,
            "Pure sine must have THD < 2%, got {}",
            metrics.thd
        );
        assert_eq!(metrics.status, VoiceCoilHealthStatus::Nominal);
        assert!(metrics.health_score > 90.0);
    }

    #[test]
    fn test_thd_analyzer_detects_saturation_clipping() {
        let config = DistortionConfig::default();
        let mut analyzer = DistortionAnalyzer::new(config);

        // Generate clipped sine wave with strong 2nd and 3rd harmonics
        let n = 512;
        let mut samples = vec![0.0f32; n];
        for (i, s) in samples.iter_mut().enumerate() {
            let raw = 2.5 * (2.0 * PI * 200.0 * (i as f32) / 16000.0).sin();
            *s = raw.clamp(-0.8, 0.8); // Harsh clipping produces intense harmonics
        }

        let mut metrics = DistortionMetrics::default();
        for _ in 0..20 {
            metrics = analyzer.process_frame(&samples);
        }

        assert!(
            metrics.thd > 0.08,
            "Clipped sine must exceed saturation threshold (0.08), got {}",
            metrics.thd
        );
        assert_eq!(metrics.status, VoiceCoilHealthStatus::SaturationWarning);
        assert!(metrics.health_score < 80.0);
    }

    #[test]
    fn test_thd_analyzer_detects_thermal_stress_odd_harmonics() {
        let config = DistortionConfig::default();
        let mut analyzer = DistortionAnalyzer::new(config);

        // Generate signal with prominent 3rd harmonic (thermal compression signature)
        let n = 512;
        let mut samples = vec![0.0f32; n];
        for (i, s) in samples.iter_mut().enumerate() {
            let t = (i as f32) / 16000.0;
            // 200 Hz fundamental + 0.06 * 600 Hz (3rd harmonic) + negligible 2nd harmonic
            *s = (2.0 * PI * 200.0 * t).sin() + 0.065 * (2.0 * PI * 600.0 * t).sin();
        }

        let mut metrics = DistortionMetrics::default();
        for _ in 0..20 {
            metrics = analyzer.process_frame(&samples);
        }

        assert!(metrics.p_harmonics[1] > metrics.p_harmonics[0]); // 3rd > 2nd
        assert!(metrics.thd > 0.045);
        assert!(
            metrics.status == VoiceCoilHealthStatus::ThermalStress
                || metrics.status == VoiceCoilHealthStatus::SaturationWarning
        );
    }

    #[test]
    fn test_thd_analyzer_reset() {
        let config = DistortionConfig::default();
        let mut analyzer = DistortionAnalyzer::new(config);
        let samples = vec![0.5f32; 512];
        let _ = analyzer.process_frame(&samples);
        analyzer.reset();
        assert_eq!(analyzer.status(), VoiceCoilHealthStatus::Nominal);
    }
}
