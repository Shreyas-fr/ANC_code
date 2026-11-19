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

    /// Computes inverse of regularized covariance matrix with diagonal loading:
    /// R_reg = R + eps * trace(R) * I
    /// Returns inverted elements: (inv00, inv01, inv11)
    #[inline]
    fn invert_regularized(&self, diag_eps: f32) -> Option<(f32, Complex32, f32)> {
        let tr = (self.r00 + self.r11).max(1e-6);
        let diag_load = diag_eps * tr;

        let a = self.r00 + diag_load;
        let b = self.r01;
        let d = self.r11 + diag_load;

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
}

impl CausalMvdrBeamformer {
    /// Creates a new CausalMvdrBeamformer instance.
    pub fn new(config: MvdrConfig) -> Self {
        let num_bins = config.num_bins;
        let mut steering_vectors = Vec::with_capacity(num_bins);

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
            steering_vectors.push([d0, d1]);
        }

        let covariances = vec![Covariance2x2::default(); num_bins];

        Self {
            config,
            steering_vectors,
            covariances,
        }
    }

    /// Resets all accumulated covariance statistics.
    pub fn reset(&mut self) {
        for cov in &mut self.covariances {
            *cov = Covariance2x2::default();
        }
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

        for k in 0..self.config.num_bins {
            let x0 = mic1_spec[k];
            let x1 = mic2_spec[k];

            // 1. Recursive covariance update
            let cov = &mut self.covariances[k];
            cov.update(x0, x1, alpha);

            // 2. Invert regularized covariance matrix
            if let Some((inv00, inv01, inv11)) = cov.invert_regularized(diag_eps) {
                let [d0, d1] = self.steering_vectors[k];

                // v = R^{-1} * d
                // v0 = inv00 * d0 + inv01 * d1
                // v1 = conj(inv01) * d0 + inv11 * d1
                let v0 = inv00 * d0 + inv01 * d1;
                let v1 = inv01.conj() * d0 + inv11 * d1;

                // denom = d^H * R^{-1} * d = d^H * v = conj(d0)*v0 + conj(d1)*v1 (real scalar)
                let denom = (d0.conj() * v0 + d1.conj() * v1).re;

                if denom > 1e-12 {
                    let inv_denom = 1.0 / denom;
                    // Optimal MVDR weight vector: w = v / denom
                    let w0 = v0 * inv_denom;
                    let w1 = v1 * inv_denom;

                    // Output beamformed spectrum: Y = w^H * X = conj(w0)*x0 + conj(w1)*x1
                    let y = w0.conj() * x0 + w1.conj() * x1;
                    mic1_spec[k] = y;
                    continue;
                }
            }

            // Fallback: If matrix inversion is ill-conditioned, pass primary mic through
            mic1_spec[k] = x0;
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
        };
        let mut mvdr = CausalMvdrBeamformer::new(config);

        // Target signal arriving simultaneously at both mics (broadside)
        let target_val = Complex32::new(1.0, 0.5);
        let mut mic1 = vec![target_val; 65];
        let mic2 = vec![target_val; 65];

        // Process several frames to settle covariance
        for _ in 0..50 {
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
}
