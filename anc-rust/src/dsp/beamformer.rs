//! Track 1 Corrected Causal Dual-Microphone MVDR (Minimum Variance Distortionless Response) Beamformer.
//!
//! Specifically modeled for the SIH 26052 30mm dual-microphone baseline geometry:
//! - Mic 1 (Primary / Speech + Noise)
//! - Mic 2 (Reference / Spatial Noise)
//! - Distance d = 0.03 m (30 mm)
//! - Speed of sound c = 343.0 m/s
//!
//! Provides spatial nulling against directional point noises (e.g. gunfire, artillery, engine)
//! while preserving direct-path speech along the target steering angle.
//! Includes Dual-Microphone Coherence Voice Activity Detection (VAD) / Speech Presence Probability (SPP)
//! and temporal weight recursive smoothing to eliminate musical warbling and self-speech cancellation.

use num_complex::Complex32;
use std::f32::consts::PI;

/// Configuration for the Causal MVDR Beamformer.
#[derive(Debug, Clone)]
pub struct MvdrConfig {
    /// Number of STFT frequency bins (n_fft / 2 + 1)
    pub num_bins: usize,
    /// Sampling rate in Hz (e.g. 16000 or 48000)
    pub sample_rate: f32,
    /// Microphone array spacing in meters (default: 0.03 m / 30 mm)
    pub mic_distance_m: f32,
    /// Speed of sound in m/s (default: 343.0 m/s)
    pub speed_of_sound_m_s: f32,
    /// Target arrival angle in degrees (0.0 = broadside / perpendicular to array)
    pub target_angle_deg: f32,
    /// Recursive covariance smoothing / forgetting factor (0.90 to 0.99, default: 0.98)
    pub alpha: f32,
    /// Diagonal loading regularization factor to prevent singular matrix inversion (default: 1e-3)
    pub diag_loading_eps: f32,
    /// Enables Dual-Mic Phase-Variance / Coherence Voice Activity Detection (VAD)
    pub enable_spp_vad: bool,
    /// SPP threshold above which frames are classified as speech-active and covariance updating freezes (default: 0.35)
    pub spp_threshold: f32,
    /// Temporal recursive smoothing factor for MVDR beamformer weight vector (0.0 to 0.95, default: 0.70)
    pub weight_smoothing: f32,
    /// Maximum condition number kappa for covariance inversion (governs adaptive diagonal loading, default: 1000.0)
    pub max_condition_number: f32,
    /// Enables Simmer & Bitzer Dual-Microphone Inter-Microphone Coherence Spatial Post-Filtering
    pub enable_spatial_postfilter: bool,
    /// Minimum attenuation floor for spatial coherence post-filter (0.10 to 0.50, default: 0.30)
    pub spatial_postfilter_floor: f32,
    /// Crossover frequency in Hz between Superdirective MVDR and Phase-calibrated Delay-and-Sum (default: 1800.0 Hz)
    pub split_freq_hz: f32,
    /// Enables Multi-Rate Subband Dual Beamforming (<1.8 kHz: Superdirective MVDR, >1.8 kHz: DSB + Post-Filter)
    pub enable_subband_dual_beamforming: bool,
    /// Enables Creeping-Wave Helmet & Cranial Obstacle Diffraction Steering Vector Correction
    pub enable_diffraction_correction: bool,
}

impl Default for MvdrConfig {
    fn default() -> Self {
        Self {
            num_bins: 257, // 512 n_fft
            sample_rate: 16000.0,
            mic_distance_m: 0.03, // 30 mm
            speed_of_sound_m_s: 343.0,
            target_angle_deg: 0.0,
            alpha: 0.98,
            diag_loading_eps: 1e-3,
            enable_spp_vad: true,
            spp_threshold: 0.35,
            weight_smoothing: 0.70,
            max_condition_number: 1000.0,
            enable_spatial_postfilter: true,
            spatial_postfilter_floor: 0.30,
            split_freq_hz: 1800.0,
            enable_subband_dual_beamforming: true,
            enable_diffraction_correction: false,
        }
    }
}

/// 2x2 Complex Hermitian Spatial Covariance Matrix
#[derive(Debug, Clone, Copy)]
struct Covariance2x2 {
    // R = [[r00, r01],
    //      [r10, r11]]
    // For Hermitian matrix: r00 and r11 are real; r10 = conj(r01)
    r00: f32,
    r01: Complex32,
    r11: f32,
}

impl Default for Covariance2x2 {
    fn default() -> Self {
        Self {
            r00: 1e-4,
            r01: Complex32::default(),
            r11: 1e-4,
        }
    }
}

impl Covariance2x2 {
    /// Updates covariance recursively: R <- alpha * R + (1 - alpha) * (X * X^H)
    #[inline]
    fn update(&mut self, x0: Complex32, x1: Complex32, alpha: f32) {
        let beta = 1.0 - alpha;
        // x0 * conj(x0) = |x0|^2 (real)
        self.r00 = alpha * self.r00 + beta * x0.norm_sqr();
        // x0 * conj(x1)
        self.r01 = self.r01 * alpha + (x0 * x1.conj()) * beta;
        // x1 * conj(x1) = |x1|^2 (real)
        self.r11 = alpha * self.r11 + beta * x1.norm_sqr();
    }

    /// Computes inverse of regularized covariance matrix with adaptive condition-number-governed diagonal loading:
    /// R_reg = R + delta * I
    /// where delta = max(diag_eps * tr(R), delta_cond) to strictly guarantee kappa(R_reg) <= max_cond.
    /// Returns inverted elements: (inv00, inv01, inv11)
    #[inline]
    fn invert_regularized(&self, diag_eps: f32, max_cond: f32) -> Option<(f32, Complex32, f32)> {
        let tr = (self.r00 + self.r11).max(1e-6);
        let diff = self.r00 - self.r11;
        let disc = (diff * diff + 4.0 * self.r01.norm_sqr()).max(0.0);
        let sqrt_disc = disc.sqrt();

        // Eigenvalues of 2x2 Hermitian matrix R
        let lambda_max = 0.5 * (tr + sqrt_disc);
        let lambda_min = (0.5 * (tr - sqrt_disc)).max(0.0);

        // 1. Condition-number-governed diagonal loading floor
        let delta_cond = if max_cond > 1.0 && lambda_max > max_cond * lambda_min {
            (lambda_max - max_cond * lambda_min) / (max_cond - 1.0)
        } else {
            0.0
        };

        let base_diag = (diag_eps * tr).max(delta_cond).max(1e-6 * tr);

        // 2. Sensor mismatch & occlusion protection:
        // On a 30mm array, physical acoustic propagation cannot cause > 16 dB (> 40x) power ratio between mics.
        // If one mic is severely occluded or defective (e.g. r00 >> 40 * r11), penalize the occluded mic's diagonal
        // to prevent standard MVDR from erroneously assigning all weight to the attenuated sensor.
        let load0 = if self.r11 > 40.0 * self.r00 {
            base_diag + (self.r11 - self.r00)
        } else {
            base_diag
        };

        let load1 = if self.r00 > 40.0 * self.r11 {
            base_diag + (self.r00 - self.r11)
        } else {
            base_diag
        };

        let a = self.r00 + load0;
        let b = self.r01;
        let d = self.r11 + load1;

        // Determinant: ad - |b|^2
        let det = a * d - b.norm_sqr();
        if det <= 1e-12 {
            return None;
        }

        let inv_det = 1.0 / det;
        // Inverse of [[a, b], [conj(b), d]] is (1/det) * [[d, -b], [-conj(b), a]]
        let inv00 = d * inv_det;
        let inv01 = -b * inv_det;
        let inv11 = a * inv_det;

        Some((inv00, inv01, inv11))
    }
}

/// Track 1 Corrected Causal MVDR Spatial Beamformer.
pub struct CausalMvdrBeamformer {
    config: MvdrConfig,
    /// Steering vector per bin: d = [d0, d1]
    steering_vectors: Vec<[Complex32; 2]>,
    /// Recursive spatial covariance matrix per frequency bin
    covariances: Vec<Covariance2x2>,
    /// Smoothed previous weight vector per bin [w0, w1]
    prev_weights: Vec<[Complex32; 2]>,
    /// Inter-microphone cross-power smoothed [num_bins]
    cross_power: Vec<Complex32>,
    /// Auto-power smoothed [num_bins] for mic 1 and mic 2
    auto_power_mic1: Vec<f32>,
    auto_power_mic2: Vec<f32>,
    /// Per-bin estimated Speech Presence Probability (0.0 to 1.0)
    pub spp: Vec<f32>,
    /// Creeping-Wave Helmet & Cranial Obstacle Diffraction Engine
    pub diffraction_engine: crate::dsp::diffraction::CreepingWaveDiffraction,
}

impl CausalMvdrBeamformer {
    /// Creates a new CausalMvdrBeamformer instance.
    pub fn new(config: MvdrConfig) -> Self {
        let num_bins = config.num_bins;
        let mut steering_vectors = Vec::with_capacity(num_bins);

        let diff_cfg = crate::dsp::diffraction::DiffractionConfig {
            sample_rate: config.sample_rate,
            num_bins: config.num_bins,
            mic_distance_m: config.mic_distance_m,
            speed_of_sound_m_s: config.speed_of_sound_m_s,
            enabled: config.enable_diffraction_correction,
            ..Default::default()
        };
        let diffraction_engine = crate::dsp::diffraction::CreepingWaveDiffraction::new(diff_cfg);

        // Precompute theoretical acoustic steering vectors per frequency bin
        // delta_t = (d * sin(theta)) / c
        let angle_rad = config.target_angle_deg * PI / 180.0;
        let delta_t = (config.mic_distance_m * angle_rad.sin()) / config.speed_of_sound_m_s;

        let n_fft = (num_bins - 1) * 2;
        let bin_hz = config.sample_rate / n_fft as f32;

        for k in 0..num_bins {
            let freq = k as f32 * bin_hz;
            // Phase delay at mic 2 relative to mic 1: phi = -2 * pi * f * delta_t
            let phase = -2.0 * PI * freq * delta_t;
            let d0 = Complex32::new(1.0, 0.0);
            let d1 = Complex32::from_polar(1.0, phase);
            let free_d = [d0, d1];
            let steer = if config.enable_diffraction_correction {
                diffraction_engine.correct_steering_vector(k, freq, config.target_angle_deg, free_d)
            } else {
                free_d
            };
            steering_vectors.push(steer);
        }

        let covariances = vec![Covariance2x2::default(); num_bins];
        let prev_weights = vec![[Complex32::new(1.0, 0.0), Complex32::default()]; num_bins];
        let cross_power = vec![Complex32::default(); num_bins];
        let auto_power_mic1 = vec![1e-4f32; num_bins];
        let auto_power_mic2 = vec![1e-4f32; num_bins];
        let spp = vec![0.0f32; num_bins];

        Self {
            config,
            steering_vectors,
            covariances,
            prev_weights,
            cross_power,
            auto_power_mic1,
            auto_power_mic2,
            spp,
            diffraction_engine,
        }
    }

    /// Resets all accumulated covariance statistics and smoothing states.
    pub fn reset(&mut self) {
        for cov in &mut self.covariances {
            *cov = Covariance2x2::default();
        }
        for w in &mut self.prev_weights {
            *w = [Complex32::new(1.0, 0.0), Complex32::default()];
        }
        self.cross_power.fill(Complex32::default());
        self.auto_power_mic1.fill(1e-4);
        self.auto_power_mic2.fill(1e-4);
        self.spp.fill(0.0);
    }

    /// Dynamically updates the spatial postfilter floor.
    pub fn set_spatial_postfilter_floor(&mut self, floor: f32) {
        self.config.spatial_postfilter_floor = floor.clamp(0.05, 1.0);
    }

    /// Dynamically sets the condition number ceiling for adaptive diagonal loading.
    pub fn set_max_condition_number(&mut self, max_cond: f32) {
        self.config.max_condition_number = max_cond.max(2.0);
    }

    /// Dynamically sets the minimum diagonal loading factor to bound inversion against thermal preamplifier noise.
    pub fn set_diagonal_loading_eps(&mut self, eps: f32) {
        self.config.diag_loading_eps = eps.clamp(1e-7, 0.1);
    }

    /// Dynamically updates the acoustic steering angle (in degrees) and recalculates steering vectors.
    /// Supports online headset rotation / slippage tracking within +/- 45 degrees.
    pub fn set_steering_angle(&mut self, angle_deg: f32) {
        let clamped_deg = angle_deg.clamp(-45.0, 45.0);
        self.config.target_angle_deg = clamped_deg;
        let angle_rad = clamped_deg * PI / 180.0;
        let delta_t = (self.config.mic_distance_m * angle_rad.sin()) / self.config.speed_of_sound_m_s;

        let n_fft = (self.config.num_bins - 1) * 2;
        let bin_hz = self.config.sample_rate / n_fft as f32;

        for k in 0..self.config.num_bins {
            let freq = k as f32 * bin_hz;
            let phase = -2.0 * PI * freq * delta_t;
            let free_d = [Complex32::new(1.0, 0.0), Complex32::from_polar(1.0, phase)];
            self.steering_vectors[k] = if self.config.enable_diffraction_correction {
                self.diffraction_engine.correct_steering_vector(k, freq, clamped_deg, free_d)
            } else {
                free_d
            };
        }
    }

    /// Dynamically enables or disables creeping-wave cranial diffraction steering vector correction.
    pub fn set_diffraction_correction(&mut self, enabled: bool) {
        self.config.enable_diffraction_correction = enabled;
        self.diffraction_engine.set_enabled(enabled);
        self.set_steering_angle(self.config.target_angle_deg);
    }

    /// Returns whether creeping-wave diffraction steering vector correction is enabled.
    pub fn is_diffraction_correction(&self) -> bool {
        self.config.enable_diffraction_correction
    }

    /// Returns the currently active steering angle in degrees.
    #[inline]
    pub fn steering_angle(&self) -> f32 {
        self.config.target_angle_deg
    }

    /// Computes the instantaneous condition number of the regularized covariance at bin k.
    pub fn condition_number_at_bin(&self, k: usize) -> f32 {
        if k >= self.config.num_bins {
            return 1.0;
        }
        let cov = self.covariances[k];
        let tr = (cov.r00 + cov.r11).max(1e-6);
        let diff = cov.r00 - cov.r11;
        let disc = (diff * diff + 4.0 * cov.r01.norm_sqr()).max(0.0);
        let sqrt_disc = disc.sqrt();
        let lambda_max = 0.5 * (tr + sqrt_disc);
        let lambda_min = (0.5 * (tr - sqrt_disc)).max(0.0);
        let delta = self.config.diag_loading_eps * tr;
        (lambda_max + delta) / (lambda_min + delta).max(1e-9)
    }

    /// Processes a single multi-channel STFT frame in-place.
    ///
    /// - `mic1_spec`: Complex STFT spectrum of primary mic (in/out: overwritten with enhanced beamformed audio).
    /// - `mic2_spec`: Complex STFT spectrum of secondary mic (read-only reference).
    pub fn process_frame(&mut self, mic1_spec: &mut [Complex32], mic2_spec: &[Complex32]) {
        assert_eq!(mic1_spec.len(), self.config.num_bins);
        assert_eq!(mic2_spec.len(), self.config.num_bins);

        let alpha = self.config.alpha;
        let diag_eps = self.config.diag_loading_eps;
        let max_cond = self.config.max_condition_number;
        let beta = self.config.weight_smoothing;
        let gamma = 0.85f32; // Inter-frame coherence tracking time constant

        let n_fft = (self.config.num_bins - 1) * 2;
        let bin_hz = self.config.sample_rate / n_fft as f32;
        let split_hz = self.config.split_freq_hz;
        let trans_half_hz = 200.0f32; // Smooth 400 Hz transition band around split_hz
        let enable_subband = self.config.enable_subband_dual_beamforming;

        for k in 0..self.config.num_bins {
            let x0 = mic1_spec[k];
            let x1 = mic2_spec[k];
            let [d0, d1] = self.steering_vectors[k];
            let freq = k as f32 * bin_hz;

            // 1. Dual-Microphone Phase-Difference Coherence & Speech Presence Probability (SPP)
            // Steered cross product: X0 * conj(X1) * d1
            // When arriving along steering direction, phase(X1) - phase(X0) = phase(d1), so steered_cross has zero phase.
            let steered_cross = x0 * x1.conj() * d1;
            let p0 = x0.norm_sqr();
            let p1 = x1.norm_sqr();

            self.cross_power[k] = self.cross_power[k] * gamma + steered_cross * (1.0 - gamma);
            self.auto_power_mic1[k] = self.auto_power_mic1[k] * gamma + p0 * (1.0 - gamma);
            self.auto_power_mic2[k] = self.auto_power_mic2[k] * gamma + p1 * (1.0 - gamma);

            let denom_pow = (self.auto_power_mic1[k] * self.auto_power_mic2[k]).sqrt().max(1e-6);
            let coherence = (self.cross_power[k].re / denom_pow).clamp(-1.0, 1.0);

            let spp_k = if self.config.enable_spp_vad {
                // High coherence along target steering vector indicates speech
                ((coherence - 0.20) / 0.60).clamp(0.0, 1.0)
            } else {
                0.0
            };
            self.spp[k] = spp_k;

            // 2. Adaptive covariance update:
            // When speech is present, freeze or drastically slow noise covariance updates
            // to prevent self-speech cancellation.
            let alpha_eff = if spp_k > self.config.spp_threshold {
                alpha + (1.0 - alpha) * 0.95
            } else {
                alpha
            };

            let cov = &mut self.covariances[k];
            cov.update(x0, x1, alpha_eff);

            // 3. Multi-Rate Subband Dual Beamforming:
            // - Low subbands (<1.8 kHz): Adaptive Superdirective MVDR with SPP-governed noise covariance
            // - High subbands (>1.8 kHz): Phase-calibrated Delay-and-Sum Beamformer + Coherence Spatial Post-Filter
            //   (avoids spatial aliasing grating lobes near f_alias = 5.7 kHz on the 30mm array)
            // - Smooth cross-fade transition band [split_hz - 200 Hz, split_hz + 200 Hz]
            let w_final = if enable_subband && freq > (split_hz + trans_half_hz) {
                // Pure High-subband: Phase-calibrated Delay-and-Sum
                let w0_dsb = Complex32::new(0.5, 0.0) * d0;
                let w1_dsb = Complex32::new(0.5, 0.0) * d1;

                let prev_w = self.prev_weights[k];
                let mut w0_smooth = prev_w[0] * beta + w0_dsb * (1.0 - beta);
                let mut w1_smooth = prev_w[1] * beta + w1_dsb * (1.0 - beta);

                let c = w0_smooth.conj() * d0 + w1_smooth.conj() * d1;
                if c.norm_sqr() > 1e-12 {
                    let inv_c_conj = Complex32::new(1.0, 0.0) / c.conj();
                    w0_smooth *= inv_c_conj;
                    w1_smooth *= inv_c_conj;
                }
                [w0_smooth, w1_smooth]
            } else {
                // Compute Adaptive Superdirective MVDR weight vector
                let (w0_mvdr_raw, w1_mvdr_raw) = if let Some((inv00, inv01, inv11)) = cov.invert_regularized(diag_eps, max_cond) {
                    let v0 = inv00 * d0 + inv01 * d1;
                    let v1 = inv01.conj() * d0 + inv11 * d1;
                    let denom = (d0.conj() * v0 + d1.conj() * v1).re;

                    if denom > 1e-12 {
                        let inv_denom = 1.0 / denom;
                        (v0 * inv_denom, v1 * inv_denom)
                    } else {
                        (Complex32::new(0.5, 0.0) * d0, Complex32::new(0.5, 0.0) * d1)
                    }
                } else {
                    (Complex32::new(0.5, 0.0) * d0, Complex32::new(0.5, 0.0) * d1)
                };

                let prev_w = self.prev_weights[k];
                let mut w0_smooth = prev_w[0] * beta + w0_mvdr_raw * (1.0 - beta);
                let mut w1_smooth = prev_w[1] * beta + w1_mvdr_raw * (1.0 - beta);

                let c = w0_smooth.conj() * d0 + w1_smooth.conj() * d1;
                if c.norm_sqr() > 1e-12 {
                    let inv_c_conj = Complex32::new(1.0, 0.0) / c.conj();
                    w0_smooth *= inv_c_conj;
                    w1_smooth *= inv_c_conj;
                }

                if enable_subband && freq >= (split_hz - trans_half_hz) {
                    // Transition band: blend MVDR and DSB
                    let mu = ((freq - (split_hz - trans_half_hz)) / (2.0 * trans_half_hz)).clamp(0.0, 1.0);
                    let w0_dsb = Complex32::new(0.5, 0.0) * d0;
                    let w1_dsb = Complex32::new(0.5, 0.0) * d1;

                    let mut w0_blend = w0_smooth * (1.0 - mu) + w0_dsb * mu;
                    let mut w1_blend = w1_smooth * (1.0 - mu) + w1_dsb * mu;

                    let c_blend = w0_blend.conj() * d0 + w1_blend.conj() * d1;
                    if c_blend.norm_sqr() > 1e-12 {
                        let inv_c = Complex32::new(1.0, 0.0) / c_blend.conj();
                        w0_blend *= inv_c;
                        w1_blend *= inv_c;
                    }
                    [w0_blend, w1_blend]
                } else {
                    [w0_smooth, w1_smooth]
                }
            };

            self.prev_weights[k] = w_final;

            // 4. Output beamformed spectrum: Y = w^H * X = conj(w0)*x0 + conj(w1)*x1
            let y = w_final[0].conj() * x0 + w_final[1].conj() * x1;

            // 5. Simmer & Bitzer Coherence Spatial Post-Filter:
            // Attenuates incoherent diffuse noise while passing coherent target speech distortionlessly
            let y_out = if self.config.enable_spatial_postfilter {
                let floor = self.config.spatial_postfilter_floor;
                let g_spatial = (coherence.max(0.0) * (1.0 - floor) + floor).clamp(floor, 1.0);
                y * g_spatial
            } else {
                y
            };

            mic1_spec[k] = y_out;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mvdr_broadside_distortionless() {
        let config = MvdrConfig {
            num_bins: 65,
            sample_rate: 16000.0,
            mic_distance_m: 0.03,
            speed_of_sound_m_s: 343.0,
            target_angle_deg: 0.0, // Broadside target
            alpha: 0.95,
            diag_loading_eps: 1e-3,
            enable_spp_vad: true,
            spp_threshold: 0.35,
            weight_smoothing: 0.50,
            ..Default::default()
        };
        let mut mvdr = CausalMvdrBeamformer::new(config);

        // Target signal arriving simultaneously at both mics (broadside)
        let target_val = Complex32::new(1.0, 0.5);
        let mut mic1 = vec![target_val; 65];
        let mic2 = vec![target_val; 65];

        // Process several frames to settle covariance and smoothing filters
        for _ in 0..100 {
            mvdr.process_frame(&mut mic1, &mic2);
        }

        // Broadside target must be preserved with near-unity gain (distortionless response)
        for (k, &out) in mic1.iter().enumerate() {
            let gain = out.norm() / target_val.norm();
            assert!(
                (gain - 1.0).abs() < 0.05,
                "Bin {}: gain expected ~1.0, got {}",
                k,
                gain
            );
        }
    }

    #[test]
    fn test_mvdr_directional_noise_nulling() {
        let config = MvdrConfig {
            num_bins: 129,
            sample_rate: 16000.0,
            mic_distance_m: 0.03, // 30 mm
            speed_of_sound_m_s: 343.0,
            target_angle_deg: 0.0, // Target at broadside (0 deg)
            alpha: 0.90,
            diag_loading_eps: 1e-3,
            enable_spp_vad: false, // In noise phase, continuous tracking
            spp_threshold: 0.35,
            weight_smoothing: 0.40,
            ..Default::default()
        };
        let mut mvdr = CausalMvdrBeamformer::new(config);

        // Directional noise arriving from endfire theta = 90 deg:
        // delta_t = 0.03 / 343 = 8.746e-5 s
        let delta_t = 0.03 / 343.0;
        let bin_hz = 16000.0 / 256.0; // 62.5 Hz per bin

        // Train covariance on directional noise for 150 frames
        for _ in 0..150 {
            let mut noise1 = Vec::with_capacity(129);
            let mut noise2 = Vec::with_capacity(129);
            for k in 0..129 {
                let freq = k as f32 * bin_hz;
                let phase = -2.0 * PI * freq * delta_t;
                let n1 = Complex32::new(1.0, 0.2);
                let n2 = n1 * Complex32::from_polar(1.0, phase);
                noise1.push(n1);
                noise2.push(n2);
            }
            mvdr.process_frame(&mut noise1, &noise2);
        }

        // Test output attenuation on endfire noise at bin 20 (1250 Hz in Superdirective MVDR subband)
        let test_bin = 20;
        let freq = test_bin as f32 * bin_hz;
        let phase = -2.0 * PI * freq * delta_t;
        let n1 = Complex32::new(1.0, 0.2);
        let n2 = n1 * Complex32::from_polar(1.0, phase);

        let mut test_mic1 = vec![Complex32::default(); 129];
        let mut test_mic2 = vec![Complex32::default(); 129];
        test_mic1[test_bin] = n1;
        test_mic2[test_bin] = n2;

        mvdr.process_frame(&mut test_mic1, &test_mic2);

        let in_power = n1.norm_sqr();
        let out_power = test_mic1[test_bin].norm_sqr();
        let attenuation_db = 10.0 * (in_power / out_power.max(1e-12)).log10();

        // Directional endfire noise in the low subband (<1.8 kHz) must be substantially nulled (> 10 dB)
        assert!(
            attenuation_db > 10.0,
            "Endfire noise attenuation must be > 10 dB in superdirective subband, got {:.2} dB",
            attenuation_db
        );
    }

    #[test]
    fn test_subband_dual_beamforming_aliasing_protection_and_distortionless() {
        let config = MvdrConfig {
            num_bins: 129,
            sample_rate: 16000.0,
            mic_distance_m: 0.03,
            target_angle_deg: 0.0, // Broadside target
            split_freq_hz: 1800.0,
            enable_subband_dual_beamforming: true,
            ..Default::default()
        };
        let mut mvdr = CausalMvdrBeamformer::new(config);

        let bin_hz = 16000.0 / 256.0;

        // Verify across the entire spectrum (from low subband 300 Hz to high subband 6000 Hz near spatial aliasing f_alias = 5.7 kHz)
        // that broadside target audio passes distortionlessly with ~1.0 gain
        let target_signal = Complex32::new(0.8, 0.4);
        let mut mic1 = vec![target_signal; 129];
        let mic2 = vec![target_signal; 129];

        for _ in 0..50 {
            mvdr.process_frame(&mut mic1, &mic2);
        }

        // Check low band (bin 10 = 625 Hz), transition band (bin 29 = 1812 Hz), and high band (bin 80 = 5000 Hz)
        for &k in &[10, 20, 29, 40, 80, 100] {
            let out_mag = mic1[k].norm();
            let expected_mag = target_signal.norm();
            let gain = out_mag / expected_mag;
            assert!(
                (gain - 1.0).abs() < 0.08,
                "Bin {} ({} Hz): gain expected ~1.0, got {:.3}",
                k,
                k as f32 * bin_hz,
                gain
            );
        }
    }

    #[test]
    fn test_mvdr_adaptive_condition_number_loading_on_sensor_mismatch() {
        // Severe sensor occlusion / sensitivity mismatch:
        // mic2 drops by 40 dB relative to mic1 (severe ill-conditioned covariance)
        let config = MvdrConfig {
            num_bins: 65,
            sample_rate: 16000.0,
            mic_distance_m: 0.03,
            max_condition_number: 30.0, // Strictly enforced condition number ceiling
            ..Default::default()
        };
        let mut mvdr = CausalMvdrBeamformer::new(config);

        // Target signal arriving broadside
        let target_val = Complex32::new(1.0, 0.2);
        // Mic 2 occluded: 0.01x amplitude (-40 dB power)
        let mic2 = vec![target_val * 0.01; 65];

        for _ in 0..80 {
            let mut mic1 = vec![target_val; 65];
            mvdr.process_frame(&mut mic1, &mic2);
        }

        let mut test_mic1 = vec![target_val; 65];
        mvdr.process_frame(&mut test_mic1, &mic2);

        // Check that condition number is bounded and output does not diverge to NaN or infinity
        for (k, &out) in test_mic1.iter().enumerate() {
            assert!(out.is_finite(), "Output at bin {} must remain finite", k);
            let pwr = out.norm_sqr();
            assert!(
                pwr > 0.05 && pwr < 5.0,
                "Output power at bin {} should remain stable despite 40 dB mic mismatch, got {}",
                k,
                pwr
            );
        }
    }

    #[test]
    fn test_mvdr_dynamic_steering_angle_tracking() {
        let config = MvdrConfig {
            num_bins: 65,
            sample_rate: 16000.0,
            mic_distance_m: 0.03,
            target_angle_deg: 0.0,
            ..Default::default()
        };
        let mut mvdr = CausalMvdrBeamformer::new(config);

        // Operator's headset rotates / slips to +30 degrees
        let target_deg = 30.0f32;
        mvdr.set_steering_angle(target_deg);
        assert!((mvdr.steering_angle() - 30.0).abs() < 1e-4);

        let delta_t = (0.03 * (30.0f32 * PI / 180.0).sin()) / 343.0;
        let bin_hz = 16000.0 / 128.0;

        let mut mic1 = vec![Complex32::default(); 65];
        let mut mic2 = vec![Complex32::default(); 65];

        for k in 1..65 {
            let freq = k as f32 * bin_hz;
            let phase = -2.0 * PI * freq * delta_t;
            mic1[k] = Complex32::from_polar(1.0, 0.0);
            mic2[k] = Complex32::from_polar(1.0, phase);
        }

        // Process frames along the newly steered +30 deg direction
        for _ in 0..30 {
            let mut m1_copy = mic1.clone();
            mvdr.process_frame(&mut m1_copy, &mic2);
        }

        let mut test_out = mic1.clone();
        mvdr.process_frame(&mut test_out, &mic2);

        // Verify distortionless response along the steered direction (near 1.0)
        for k in 5..60 {
            let out_mag = test_out[k].norm();
            assert!(
                (out_mag - 1.0).abs() < 0.25,
                "Steered target at +30 deg should have near-unity gain, bin {} got {:.3}",
                k,
                out_mag
            );
        }
    }
}
