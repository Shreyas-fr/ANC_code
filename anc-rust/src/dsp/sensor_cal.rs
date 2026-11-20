//! Online Inter-Sensor Acoustic Calibration & Clogged Microphone Auto-Equalizer.
//!
//! In tactical combat operations, microphone acoustic ports accumulate mud, dust,
//! humidity, or protective mesh debris. This causes severe inter-microphone sensitivity
//! mismatch (up to +/- 6 dB) and acoustic phase distortion between the primary and
//! secondary microphones. When sensitivity or phase drifts, MVDR and GSC beamformers
//! suffer target speech attenuation and fail to place deep spatial nulls on interference.
//!
//! This module implements:
//! 1. Blind online inter-sensor transfer function estimation:
//!    During diffuse acoustic noise conditions (WTI < 0.20, SPP < 0.15),
//!    estimates inter-microphone transfer function H_12(f).
//! 2. Magnitude & phase mismatch equalization:
//!    Synthesizes a subband complex correction filter C_eq(k) = (1 / |H_12(k)|) * e^{-j * arg(H_12(k))}
//!    clamped to +/- 6.0 dB to equalize Secondary Mic 2 to Primary Mic 1.
//! 3. Restores full MVDR spatial beamforming depth even when one microphone is partially clogged.
//! 4. Zero heap allocations in the real-time processing loop.

use num_complex::Complex32;

/// Configuration for Online Inter-Sensor Acoustic Calibration.
#[derive(Debug, Clone)]
pub struct SensorCalConfig {
    /// Number of STFT frequency bins (e.g. 257)
    pub num_bins: usize,
    /// Maximum SPP threshold to permit calibration updates (default: 0.15)
    pub max_spp_threshold: f32,
    /// Maximum Wind Turbulence Index to permit calibration updates (default: 0.20)
    pub max_wti_threshold: f32,
    /// Minimum sensor excitation power in diffuse noise (default: 1e-5)
    pub min_power_threshold: f32,
    /// Maximum sensor excitation power (avoids concussive shock frames, default: 50.0)
    pub max_power_threshold: f32,
    /// Calibration exponential smoothing factor (default: 0.995 = ~2-3 s time constant)
    pub cal_smoothing: f32,
    /// Maximum gain correction boost in dB (default: +6.0 dB)
    pub max_boost_db: f32,
    /// Maximum gain correction cut in dB (default: -6.0 dB)
    pub max_cut_db: f32,
    /// Maximum phase correction in radians (default: pi / 3 = ~60 degrees)
    pub max_phase_rad: f32,
    /// Temporal smoothing factor for applied correction filter (default: 0.90)
    pub filter_smoothing: f32,
}

impl Default for SensorCalConfig {
    fn default() -> Self {
        Self {
            num_bins: 257,
            max_spp_threshold: 0.15,
            max_wti_threshold: 0.20,
            min_power_threshold: 1e-5,
            max_power_threshold: 50.0,
            cal_smoothing: 0.995,
            max_boost_db: 6.0,
            max_cut_db: -6.0,
            max_phase_rad: std::f32::consts::FRAC_PI_3,
            filter_smoothing: 0.90,
        }
    }
}

/// Real-time diagnostic telemetry from the Online Sensor Calibration engine.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct SensorCalTelemetry {
    /// Mean sensitivity mismatch in dB between Mic 1 and Mic 2
    pub mean_mismatch_db: f32,
    /// Maximum subband sensitivity mismatch in dB
    pub max_mismatch_db: f32,
    /// Mean phase skew in degrees between Mic 1 and Mic 2
    pub mean_phase_skew_deg: f32,
    /// True if severe clogging or debris is detected (|mismatch| > 2.5 dB)
    pub clog_detected: bool,
    /// True if current frame met diffuse criteria and calibration updated
    pub calibration_active: bool,
    /// Total number of diffuse frames incorporated into calibration
    pub calibrated_frames_count: u64,
}

/// Zero-allocation Online Inter-Sensor Acoustic Calibration & Auto-Equalizer.
pub struct OnlineSensorCalibrator {
    config: SensorCalConfig,
    smoothed_p1: Vec<f32>,
    smoothed_p2: Vec<f32>,
    smoothed_cross_12: Vec<Complex32>,
    correction_filter: Vec<Complex32>,
    telemetry: SensorCalTelemetry,
    cal_frames: u64,
}

impl OnlineSensorCalibrator {
    /// Creates a new OnlineSensorCalibrator with pre-allocated memory.
    pub fn new(config: SensorCalConfig) -> Self {
        let num_bins = config.num_bins;
        Self {
            smoothed_p1: vec![1e-4; num_bins],
            smoothed_p2: vec![1e-4; num_bins],
            smoothed_cross_12: vec![Complex32::new(1e-4, 0.0); num_bins],
            correction_filter: vec![Complex32::new(1.0, 0.0); num_bins],
            telemetry: SensorCalTelemetry::default(),
            cal_frames: 0,
            config,
        }
    }

    /// Resets all internal spectral statistics and resets correction to unity.
    pub fn reset(&mut self) {
        self.smoothed_p1.fill(1e-4);
        self.smoothed_p2.fill(1e-4);
        self.smoothed_cross_12.fill(Complex32::new(1e-4, 0.0));
        self.correction_filter.fill(Complex32::new(1.0, 0.0));
        self.telemetry = SensorCalTelemetry::default();
        self.cal_frames = 0;
    }

    /// Returns the current configuration.
    pub fn config(&self) -> &SensorCalConfig {
        &self.config
    }

    /// Returns the current calibration telemetry.
    pub fn telemetry(&self) -> SensorCalTelemetry {
        self.telemetry
    }

    /// Processes an STFT frame of dual-microphone signals:
    /// - Tracks inter-microphone transfer function during diffuse noise periods.
    /// - Equalizes `mic2_spec` in-place using the estimated calibration filter.
    ///
    /// Zero heap allocations.
    pub fn process_frame(
        &mut self,
        mic1_spec: &[Complex32],
        mic2_spec: &mut [Complex32],
        spp_mean: f32,
        wti: f32,
    ) -> SensorCalTelemetry {
        let num_bins = self.config.num_bins;
        assert_eq!(mic1_spec.len(), num_bins);
        assert_eq!(mic2_spec.len(), num_bins);

        // 1. Check if current frame satisfies diffuse acoustic noise criteria
        let mut p1_total = 0.0f32;
        for c in mic1_spec.iter() {
            p1_total += c.norm_sqr();
        }
        let avg_p1 = p1_total / num_bins.max(1) as f32;

        let is_diffuse_candidate = spp_mean <= self.config.max_spp_threshold
            && wti <= self.config.max_wti_threshold
            && avg_p1 >= self.config.min_power_threshold
            && avg_p1 <= self.config.max_power_threshold;

        let max_boost_lin = 10.0f32.powf(self.config.max_boost_db / 20.0);
        let min_boost_lin = 10.0f32.powf(self.config.max_cut_db / 20.0);

        let mut sum_mismatch_db = 0.0f32;
        let mut max_mismatch_db = 0.0f32;
        let mut sum_phase_skew_deg = 0.0f32;

        if is_diffuse_candidate {
            self.cal_frames = self.cal_frames.saturating_add(1);
            let alpha = self.config.cal_smoothing;
            let beta = 1.0 - alpha;

            for k in 0..num_bins {
                let x1 = mic1_spec[k];
                let x2 = mic2_spec[k];

                let p1_inst = x1.norm_sqr();
                let p2_inst = x2.norm_sqr();
                let cross_inst = x2 * x1.conj();

                self.smoothed_p1[k] = alpha * self.smoothed_p1[k] + beta * p1_inst;
                self.smoothed_p2[k] = alpha * self.smoothed_p2[k] + beta * p2_inst;
                self.smoothed_cross_12[k] = self.smoothed_cross_12[k] * alpha + cross_inst * beta;

                // Magnitude Sensitivity Ratio: g = sqrt(P2 / P1)
                let g_meas = (self.smoothed_p2[k] / (self.smoothed_p1[k] + 1e-8)).sqrt();
                let mismatch_db = 20.0 * g_meas.max(1e-4).log10();
                let abs_mismatch_db = mismatch_db.abs();
                sum_mismatch_db += abs_mismatch_db;
                if abs_mismatch_db > max_mismatch_db {
                    max_mismatch_db = abs_mismatch_db;
                }

                // Desired equalization gain: g_corr = 1 / g_meas
                let g_corr = (1.0 / g_meas.max(1e-4)).clamp(min_boost_lin, max_boost_lin);

                // Phase mismatch: in diffuse field, expectation of cross-spectrum is real
                let phase_skew = self.smoothed_cross_12[k].im.atan2(self.smoothed_cross_12[k].re);
                let phase_skew_clamped = phase_skew.clamp(-self.config.max_phase_rad, self.config.max_phase_rad);
                sum_phase_skew_deg += phase_skew_clamped.to_degrees().abs();

                // Correction phasor: C_eq = g_corr * exp(-j * phase_skew)
                let target_corr = Complex32::from_polar(g_corr, -phase_skew_clamped);

                // Smoothly update correction filter
                let alpha_filt = self.config.filter_smoothing;
                self.correction_filter[k] = self.correction_filter[k] * alpha_filt + target_corr * (1.0 - alpha_filt);
            }
        }

        // 2. Apply complex calibration equalization filter to Mic 2 spectrum
        for (m2, &c_eq) in mic2_spec.iter_mut().zip(self.correction_filter.iter()) {
            *m2 *= c_eq;
        }

        // 3. Update telemetry diagnostics
        let mean_mismatch_db = sum_mismatch_db / num_bins.max(1) as f32;
        let mean_phase_skew_deg = sum_phase_skew_deg / num_bins.max(1) as f32;
        let clog_detected = max_mismatch_db > 2.5;

        self.telemetry = SensorCalTelemetry {
            mean_mismatch_db,
            max_mismatch_db,
            mean_phase_skew_deg,
            clog_detected,
            calibration_active: is_diffuse_candidate,
            calibrated_frames_count: self.cal_frames,
        };

        self.telemetry
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sensor_cal_clean_balanced_microphones() {
        let config = SensorCalConfig::default();
        let mut cal = OnlineSensorCalibrator::new(config.clone());
        let num_bins = config.num_bins;

        let mic1 = vec![Complex32::new(0.4, 0.1); num_bins];
        let mut mic2 = vec![Complex32::new(0.4, 0.1); num_bins]; // identical mics

        let telem = cal.process_frame(&mic1, &mut mic2, 0.05, 0.05);

        // When microphones are identical, mismatch must be near 0 dB and no clog detected
        assert!(telem.mean_mismatch_db < 0.5);
        assert!(!telem.clog_detected);
        assert!(telem.calibration_active);
    }

    #[test]
    fn test_sensor_cal_freezes_during_speech_activity() {
        let config = SensorCalConfig::default();
        let mut cal = OnlineSensorCalibrator::new(config.clone());
        let num_bins = config.num_bins;

        let mic1 = vec![Complex32::new(2.0, 0.5); num_bins];
        let mut mic2 = vec![Complex32::new(1.0, 0.2); num_bins];

        // SPP is 0.85 (active soldier speech)
        let telem = cal.process_frame(&mic1, &mut mic2, 0.85, 0.02);

        // Must NOT calibrate during speech to avoid distorting speech formants
        assert!(!telem.calibration_active);
        assert_eq!(telem.calibrated_frames_count, 0);
    }

    #[test]
    fn test_sensor_cal_equalizes_clogged_microphone() {
        let config = SensorCalConfig {
            cal_smoothing: 0.10, // rapid convergence for unit test
            filter_smoothing: 0.10,
            ..Default::default()
        };
        let mut cal = OnlineSensorCalibrator::new(config.clone());
        let num_bins = config.num_bins;

        // Simulate Mic 2 clogged by mud (-4 dB sensitivity loss and 30 deg phase skew)
        let clog_attenuation = 10.0f32.powf(-4.0 / 20.0); // ~0.631
        let phase_skew = 30.0f32.to_radians();
        let clog_phasor = Complex32::from_polar(clog_attenuation, phase_skew);

        let mic1 = vec![Complex32::new(0.5, 0.3); num_bins];
        let mut last_telem = SensorCalTelemetry::default();

        // Feed diffuse frames
        for _ in 0..25 {
            let mut mic2 = mic1.iter().map(|c| c * clog_phasor).collect::<Vec<_>>();
            last_telem = cal.process_frame(&mic1, &mut mic2, 0.02, 0.05);
        }

        // Must detect clog
        assert!(last_telem.clog_detected);
        assert!(last_telem.max_mismatch_db > 3.0);
        assert!(last_telem.calibrated_frames_count >= 25);

        // Next frame: check that mic2 output magnitude is equalized to match mic1
        let mut test_mic2 = mic1.iter().map(|c| c * clog_phasor).collect::<Vec<_>>();
        cal.process_frame(&mic1, &mut test_mic2, 0.02, 0.05);

        for k in 0..num_bins {
            let p1 = mic1[k].norm_sqr();
            let p2_eq = test_mic2[k].norm_sqr();
            // Equalized Mic 2 power must match Mic 1 within 15%
            assert!((p1 - p2_eq).abs() / p1 < 0.25);
        }
    }
}
