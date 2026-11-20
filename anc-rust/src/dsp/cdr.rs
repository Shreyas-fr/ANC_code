//! Multi-Microphone Coherence-to-Diffuse Ratio (CDR) & Inter-Channel Phase Difference (ICPD) Estimator.
//!
//! Provides spatial coherence decomposition for dual-microphone tactical arrays:
//! - Theoretical 3D spherically isotropic diffuse field coherence:
//!   $$\Gamma_{12}(f) = \text{sinc}\left(\frac{2\pi f d}{c}\right) = \frac{\sin(2\pi f d / c)}{2\pi f d / c}$$
//! - Recursive auto- and cross-spectral densities: $\Phi_{11}(f), \Phi_{22}(f), \Phi_{12}(f)$
//! - Complex coherence $\gamma_{12}(f)$ and Inter-Channel Phase Difference (ICPD)
//! - Real-time Coherence-to-Diffuse Ratio (CDR) and Diffuse Field Ratio estimation
//! - Dynamic modulation of Wiener gain floor and over-subtraction factor $\alpha(f)$:
//!   high diffuse noise automatically increases aggressive spatial suppression while
//!   preserving directional near-end speech harmonics.
//! - Strictly ZERO heap allocations in `process_frame`.

use num_complex::Complex32;
use std::f32::consts::PI;

/// Configuration for the Coherence-to-Diffuse Ratio (CDR) estimator.
#[derive(Debug, Clone)]
pub struct CdrConfig {
    /// Number of STFT frequency bins (n_fft / 2 + 1)
    pub num_bins: usize,
    /// Sampling rate in Hz (e.g. 16000.0)
    pub sample_rate: f32,
    /// Microphone array spacing in meters (default: 0.03 m / 30 mm)
    pub mic_distance_m: f32,
    /// Speed of sound in m/s (default: 343.0 m/s)
    pub speed_of_sound_m_s: f32,
    /// Recursive PSD smoothing / forgetting factor (0.80 to 0.95, default: 0.85)
    pub alpha_smooth: f32,
    /// Target arrival angle in degrees (default: 0.0 broadside)
    pub target_angle_deg: f32,
}

impl Default for CdrConfig {
    fn default() -> Self {
        Self {
            num_bins: 257,
            sample_rate: 16000.0,
            mic_distance_m: 0.03, // 30 mm tactical baseline
            speed_of_sound_m_s: 343.0,
            alpha_smooth: 0.85,
            target_angle_deg: 0.0,
        }
    }
}

/// Zero-allocation Dual-Microphone Coherence-to-Diffuse Ratio (CDR) and ICPD Estimator.
pub struct CdrEstimator {
    pub config: CdrConfig,

    // Precomputed theoretical diffuse coherence sinc(2 * pi * f * d / c)
    gamma_diffuse: Vec<f32>,
    // Precomputed target direct steering cosines: cos(2 * pi * f * d * sin(theta) / c)
    cos_target: Vec<f32>,

    // Preallocated recursive spectral density states [num_bins]
    phi11: Vec<f32>,
    phi22: Vec<f32>,
    phi12: Vec<Complex32>,

    // Preallocated per-bin output states [num_bins]
    coherence_mag: Vec<f32>,
    coherence_re: Vec<f32>,
    icpd: Vec<f32>,
    cdr: Vec<f32>,
    diffuse_ratio: Vec<f32>,

    // Cached scalar metrics
    mean_cdr_db: f32,
    mean_coherence: f32,
    mean_diffuse_ratio: f32,
    frames_processed: u64,
}

impl CdrEstimator {
    /// Creates a new zero-allocation CdrEstimator.
    pub fn new(config: CdrConfig) -> Self {
        let num_bins = config.num_bins;
        let mut gamma_diffuse = vec![1.0f32; num_bins];
        let mut cos_target = vec![1.0f32; num_bins];

        let bin_hz = config.sample_rate / (2.0 * (num_bins - 1) as f32);
        let dist = config.mic_distance_m;
        let c = config.speed_of_sound_m_s;
        let target_rad = config.target_angle_deg * PI / 180.0;

        for k in 0..num_bins {
            let freq = k as f32 * bin_hz;
            // 3D diffuse field coherence: sinc(2 * pi * f * d / c)
            let arg = 2.0 * PI * freq * dist / c;
            gamma_diffuse[k] = if arg.abs() < 1e-4 {
                1.0
            } else {
                arg.sin() / arg
            };

            // Target steering phase difference: 2 * pi * f * (d * sin(theta) / c)
            let target_phase = 2.0 * PI * freq * (dist * target_rad.sin()) / c;
            cos_target[k] = target_phase.cos();
        }

        Self {
            config,
            gamma_diffuse,
            cos_target,
            phi11: vec![1e-4f32; num_bins],
            phi22: vec![1e-4f32; num_bins],
            phi12: vec![Complex32::default(); num_bins],
            coherence_mag: vec![1.0f32; num_bins],
            coherence_re: vec![1.0f32; num_bins],
            icpd: vec![0.0f32; num_bins],
            cdr: vec![10.0f32; num_bins],
            diffuse_ratio: vec![0.1f32; num_bins],
            mean_cdr_db: 10.0,
            mean_coherence: 0.85,
            mean_diffuse_ratio: 0.1,
            frames_processed: 0,
        }
    }

    /// Resets all internal spectral densities and tracking states.
    pub fn reset(&mut self) {
        self.phi11.fill(1e-4);
        self.phi22.fill(1e-4);
        self.phi12.fill(Complex32::default());
        self.coherence_mag.fill(1.0);
        self.coherence_re.fill(1.0);
        self.icpd.fill(0.0);
        self.cdr.fill(10.0);
        self.diffuse_ratio.fill(0.1);
        self.mean_cdr_db = 10.0;
        self.mean_coherence = 0.85;
        self.mean_diffuse_ratio = 0.1;
        self.frames_processed = 0;
    }

    /// Dynamically updates target steering angle for CDR direct-path projection.
    pub fn set_target_angle(&mut self, angle_deg: f32) {
        self.config.target_angle_deg = angle_deg;
        let bin_hz = self.config.sample_rate / (2.0 * (self.config.num_bins - 1) as f32);
        let dist = self.config.mic_distance_m;
        let c = self.config.speed_of_sound_m_s;
        let target_rad = angle_deg * PI / 180.0;

        for k in 0..self.config.num_bins {
            let freq = k as f32 * bin_hz;
            let target_phase = 2.0 * PI * freq * (dist * target_rad.sin()) / c;
            self.cos_target[k] = target_phase.cos();
        }
    }

    /// Processes a single STFT frame of Mic 1 and Mic 2 spectra.
    ///
    /// Zero heap allocations during execution.
    pub fn process_frame(&mut self, spec_mic1: &[Complex32], spec_mic2: &[Complex32]) {
        assert_eq!(spec_mic1.len(), self.config.num_bins);
        assert_eq!(spec_mic2.len(), self.config.num_bins);

        self.frames_processed += 1;
        let alpha = self.config.alpha_smooth;
        let beta = 1.0 - alpha;

        let mut sum_cdr_db = 0.0f32;
        let mut sum_coh = 0.0f32;
        let mut sum_diffuse = 0.0f32;
        let mut speech_band_bins = 0usize;

        // Core speech band for metrics: 300 Hz to 4000 Hz
        let bin_hz = self.config.sample_rate / (2.0 * (self.config.num_bins - 1) as f32);
        let k_min = ((300.0 / bin_hz) as usize).clamp(1, self.config.num_bins - 1);
        let k_max = ((4000.0 / bin_hz) as usize).clamp(k_min, self.config.num_bins - 1);

        for k in 0..self.config.num_bins {
            let x1 = spec_mic1[k];
            let x2 = spec_mic2[k];

            let p1 = x1.norm_sqr().max(1e-9);
            let p2 = x2.norm_sqr().max(1e-9);
            let cross = x1 * x2.conj();

            // 1. Recursive Auto- and Cross-Spectral Densities
            self.phi11[k] = alpha * self.phi11[k] + beta * p1;
            self.phi22[k] = alpha * self.phi22[k] + beta * p2;
            self.phi12[k] = self.phi12[k] * alpha + cross * beta;

            // 2. Complex Spatial Coherence: gamma_12 = Phi_12 / sqrt(Phi_11 * Phi_22)
            let denom = (self.phi11[k] * self.phi22[k]).sqrt().max(1e-8);
            let gamma = self.phi12[k] / denom;
            let re_gamma = gamma.re.clamp(-1.0, 1.0);
            let mag_gamma = gamma.norm().clamp(0.0, 1.0);

            self.coherence_re[k] = re_gamma;
            self.coherence_mag[k] = mag_gamma;

            // 3. Inter-Channel Phase Difference (ICPD) in radians [-PI, PI]
            self.icpd[k] = self.phi12[k].im.atan2(self.phi12[k].re);

            // 4. Coherence-to-Diffuse Ratio (CDR):
            // Under diffuse field + direct sound model:
            // Re{gamma_12} = (CDR * cos(target_phase) + Gamma_diffuse) / (CDR + 1)
            // => CDR = (Re{gamma_12} - Gamma_diffuse) / (cos(target_phase) - Re{gamma_12})
            let g_diff = self.gamma_diffuse[k];
            let c_targ = self.cos_target[k];

            let num = re_gamma - g_diff;
            let den = c_targ - re_gamma;

            let cdr_k = if den <= 1e-4 {
                // Measured coherence equals or exceeds direct target coherence => purely direct
                1000.0
            } else if num <= 0.0 {
                // Measured coherence falls below theoretical diffuse coherence => purely diffuse
                0.001
            } else {
                (num / den).clamp(0.001, 1000.0)
            };

            self.cdr[k] = cdr_k;

            // 5. Diffuse Sound Field Ratio in [0.0, 1.0]:
            // DiffuseRatio = 1 / (1 + CDR)
            let diff_ratio = 1.0 / (1.0 + cdr_k);
            self.diffuse_ratio[k] = diff_ratio;

            // Accumulate metrics over human vocal speech band (300 Hz - 4000 Hz)
            if k >= k_min && k <= k_max {
                sum_cdr_db += 10.0 * cdr_k.log10();
                sum_coh += mag_gamma;
                sum_diffuse += diff_ratio;
                speech_band_bins += 1;
            }
        }

        if speech_band_bins > 0 {
            let inv_n = 1.0 / speech_band_bins as f32;
            self.mean_cdr_db = sum_cdr_db * inv_n;
            self.mean_coherence = sum_coh * inv_n;
            self.mean_diffuse_ratio = sum_diffuse * inv_n;
        }
    }

    /// Dynamically calculates Wiener over-subtraction and attenuation floor modulation factors.
    ///
    /// When diffuse sound dominates (low CDR / high diffuse ratio):
    /// - `alpha_out` increases up to `base_alpha * 1.35` (aggressive spatial noise cancellation).
    /// - `floor_out` drops down to `base_floor * 0.70` (deeper suppression of vehicle rumble / babble).
    ///
    /// When directional speech dominates (high CDR / low diffuse ratio):
    /// - `alpha_out` relaxes towards `base_alpha` (preserves speech formants without distortion).
    /// - `floor_out` raises towards `base_floor` (prevents harsh musical noise gating).
    #[inline]
    pub fn diffuse_suppression_factors(
        &self,
        alpha_out: &mut [f32],
        floor_out: &mut [f32],
        base_alpha: f32,
        base_floor: f32,
    ) {
        assert_eq!(alpha_out.len(), self.config.num_bins);
        assert_eq!(floor_out.len(), self.config.num_bins);

        for k in 0..self.config.num_bins {
            let d_ratio = self.diffuse_ratio[k];
            // Scale over-subtraction: [base_alpha, base_alpha * 1.35]
            alpha_out[k] = base_alpha * (1.0 + 0.35 * d_ratio);
            // Scale floor: [base_floor * 0.70, base_floor]
            floor_out[k] = base_floor * (1.0 - 0.30 * d_ratio).clamp(0.01, 1.0);
        }
    }

    /// Returns the per-bin Coherence-to-Diffuse Ratio (CDR) linear values [num_bins].
    pub fn cdr(&self) -> &[f32] {
        &self.cdr
    }

    /// Returns the per-bin Diffuse Field Ratio [0.0, 1.0] [num_bins].
    pub fn diffuse_ratio(&self) -> &[f32] {
        &self.diffuse_ratio
    }

    /// Returns the per-bin Inter-Channel Phase Difference (ICPD) in radians [num_bins].
    pub fn icpd(&self) -> &[f32] {
        &self.icpd
    }

    /// Returns the per-bin magnitude coherence [0.0, 1.0] [num_bins].
    pub fn coherence_mag(&self) -> &[f32] {
        &self.coherence_mag
    }

    /// Returns the precomputed theoretical diffuse coherence sinc curve [num_bins].
    pub fn gamma_diffuse(&self) -> &[f32] {
        &self.gamma_diffuse
    }

    /// Mean CDR in decibels (dB) across core speech band (300 Hz - 4000 Hz).
    #[inline]
    pub fn mean_cdr_db(&self) -> f32 {
        self.mean_cdr_db
    }

    /// Mean spatial magnitude coherence [0.0, 1.0] across core speech band.
    #[inline]
    pub fn mean_coherence(&self) -> f32 {
        self.mean_coherence
    }

    /// Mean diffuse sound energy ratio [0.0, 1.0] across core speech band.
    #[inline]
    pub fn mean_diffuse_ratio(&self) -> f32 {
        self.mean_diffuse_ratio
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cdr_diffuse_field_sinc_theoretical() {
        let config = CdrConfig {
            num_bins: 257,
            sample_rate: 16000.0,
            mic_distance_m: 0.03, // 30 mm
            speed_of_sound_m_s: 343.0,
            alpha_smooth: 0.85,
            target_angle_deg: 0.0,
        };
        let cdr = CdrEstimator::new(config);

        // At DC (0 Hz), theoretical diffuse coherence must be strictly 1.0
        assert_eq!(cdr.gamma_diffuse()[0], 1.0);

        // At f = c / (2 * d) = 343 / 0.06 = 5716.7 Hz, sinc argument is exactly pi => sinc(pi) = 0.0
        let bin_hz = 16000.0f32 / 512.0f32; // 31.25 Hz
        let zero_crossing_bin = (5716.7f32 / bin_hz).round() as usize; // bin ~183
        assert!(
            cdr.gamma_diffuse()[zero_crossing_bin].abs() < 0.05,
            "Bin {} expected sinc zero crossing ~0, got {}",
            zero_crossing_bin,
            cdr.gamma_diffuse()[zero_crossing_bin]
        );
    }

    #[test]
    fn test_cdr_high_directional_speech_vs_diffuse_noise() {
        let config = CdrConfig {
            num_bins: 65,
            sample_rate: 16000.0,
            mic_distance_m: 0.03,
            speed_of_sound_m_s: 343.0,
            alpha_smooth: 0.80,
            target_angle_deg: 0.0, // Broadside
        };
        let mut cdr = CdrEstimator::new(config);

        // Scenario A: Directional Broadside Clean Speech (Mic 1 == Mic 2 exactly)
        let speech_frame = vec![Complex32::new(1.0, 0.5); 65];
        for _ in 0..30 {
            cdr.process_frame(&speech_frame, &speech_frame);
        }

        // Direct sound has high coherence (~1.0) and high CDR (> 10 dB)
        assert!(
            cdr.mean_coherence() > 0.95,
            "Direct speech coherence expected > 0.95, got {}",
            cdr.mean_coherence()
        );
        assert!(
            cdr.mean_cdr_db() > 15.0,
            "Direct speech CDR expected > 15 dB, got {:.2} dB",
            cdr.mean_cdr_db()
        );
        assert!(
            cdr.mean_diffuse_ratio() < 0.10,
            "Direct speech diffuse ratio expected < 0.10, got {}",
            cdr.mean_diffuse_ratio()
        );

        // Scenario B: Diffuse / Incoherent Noise (Independent noise on Mic 1 and Mic 2)
        cdr.reset();
        for i in 0..40 {
            let mut n1 = vec![Complex32::default(); 65];
            let mut n2 = vec![Complex32::default(); 65];
            for k in 0..65 {
                let p1 = ((i * 17 + k * 13) % 100) as f32 / 100.0;
                let p2 = ((i * 31 + k * 23) % 100) as f32 / 100.0;
                n1[k] = Complex32::from_polar(0.5, p1 * 2.0 * PI);
                n2[k] = Complex32::from_polar(0.5, p2 * 2.0 * PI);
            }
            cdr.process_frame(&n1, &n2);
        }

        // Incoherent noise should have lower coherence and high diffuse ratio
        assert!(
            cdr.mean_cdr_db() < 5.0,
            "Diffuse noise CDR expected < 5 dB, got {:.2} dB",
            cdr.mean_cdr_db()
        );
        assert!(
            cdr.mean_diffuse_ratio() > 0.40,
            "Diffuse noise ratio expected > 0.40, got {}",
            cdr.mean_diffuse_ratio()
        );
    }
}
