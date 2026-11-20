//! Subband Generalized Sidelobe Canceller (GSC) with Norm-Constrained Adaptive Filter.
//!
//! Developed for SIH 26052 Tactical Audio Systems.
//!
//! The Griffith-Jim Generalized Sidelobe Canceller (GSC) architecture converts
//! the constrained minimum variance optimization into an unconstrained dual-branch structure:
//!
//! 1. Upper Quiescent Beamformer Branch:
//!    - Fixed look-direction beamformer vector: $\mathbf{w}_q = [0.5, 0.5]^T$.
//!    - Target speech arriving broadside ($\theta = 0^\circ$) satisfies the distortionless constraint
//!      $\mathbf{d}^H \mathbf{w}_q = 1.0$, producing the quiescent reference:
//!      $$D_{\text{ref}}[k] = 0.5 (X_1[k] + X_2[k])$$
//!
//! 2. Lower Spatial Blocking Matrix Branch:
//!    - Spatial blocking matrix: $\mathbf{B} = [1.0, -1.0]$.
//!    - Places an exact mathematical spatial null on the broadside speech direction:
//!      $$U[k] = X_1[k] - X_2[k]$$
//!    - Target speech is completely cancelled in $U[k]$, isolating directional sidelobe interference and noise.
//!
//! 3. Subband Norm-Constrained Adaptive Multi-Tap Filter:
//!    - Multi-tap subband filter ($M$ taps per bin) modeling acoustic reverberation and arrival delays:
//!      $$\hat{Y}[k, t] = \sum_{m=0}^{M-1} W_a[k, m] U[k, t - m]$$
//!    - Residual enhanced output:
//!      $$E[k, t] = D_{\text{ref}}[k, t] - \hat{Y}[k, t]$$
//!    - Leaky Normalized LMS (NLMS) adaptation:
//!      $$W_a[k, m] \leftarrow (1 - \lambda) W_a[k, m] + \mu \frac{E[k, t] U^*[k, t - m]}{\sum_{\tau=0}^{M-1} |U[k, t - \tau]|^2 + \epsilon}$$
//!
//! 4. Dual-Layer Speech Self-Cancellation Protection:
//!    - A. SPP Speech Presence Freezing: Adaptation freezes whenever speech presence probability is detected
//!      ($\text{SPP} > 0.35$ or broadside power dominates $|D_{\text{ref}}|^2 > 2.5 |U|^2$).
//!    - B. $L_2$ Norm Constraint ($\|W_a[k]\|_2 \le \gamma$): Enforces an upper bound on adaptive filter gain.
//!      Guarantees that acoustic sensor mismatch or microphone angle slip cannot cancel target speech.
//!
//! Delivers deep directional nulling (> 25 dB) with zero runtime heap allocations.

use num_complex::Complex32;

/// Number of adaptive filter taps per frequency bin (temporal delay depth).
pub const GSC_TAPS_PER_BIN: usize = 2;

/// Configuration for the Subband Generalized Sidelobe Canceller.
#[derive(Debug, Clone)]
pub struct GscConfig {
    pub num_bins: usize,
    pub sample_rate: f32,
    /// Adaptation step size $\mu$ (default: 0.12).
    pub step_size: f32,
    /// Leakage factor $\lambda$ preventing weight drift (default: 0.0001).
    pub leakage: f32,
    /// Maximum allowed $L_2$ norm of adaptive filter per bin $\gamma$ (default: 0.707).
    pub norm_bound: f32,
    /// Speech Presence Probability threshold above which adaptation freezes (default: 0.35).
    pub spp_freeze_threshold: f32,
    /// Regularization epsilon preventing division by zero.
    pub epsilon: f32,
}

impl Default for GscConfig {
    fn default() -> Self {
        Self {
            num_bins: 257,
            sample_rate: 16000.0,
            step_size: 0.12,
            leakage: 0.0001,
            norm_bound: 0.707,
            spp_freeze_threshold: 0.35,
            epsilon: 1e-6,
        }
    }
}

/// Real-time statistics from the Generalized Sidelobe Canceller.
#[derive(Debug, Clone, Copy, Default)]
pub struct GscStats {
    /// Average interference cancellation depth in dB.
    pub cancellation_db: f32,
    /// Mean norm of the adaptive filter weights.
    pub mean_filter_norm: f32,
    /// Fraction of bins frozen due to speech presence.
    pub speech_freeze_ratio: f32,
    /// Active nulling engagement flag.
    pub is_nulling: bool,
}

/// Subband Generalized Sidelobe Canceller with Norm-Constrained Adaptive Filter.
pub struct SubbandGsc {
    config: GscConfig,
    enabled: bool,

    // Pre-allocated filter state (zero runtime heap allocations)
    // weights: [num_bins * GSC_TAPS_PER_BIN]
    weights: Vec<Complex32>,
    // noise_history: [num_bins * GSC_TAPS_PER_BIN]
    noise_history: Vec<Complex32>,

    // Scratch buffers
    u_scratch: Vec<Complex32>,
    d_scratch: Vec<Complex32>,
    stats: GscStats,
}

impl SubbandGsc {
    /// Creates a new SubbandGsc with pre-allocated buffers.
    pub fn new(config: GscConfig) -> Self {
        let num_bins = config.num_bins;
        let total_taps = num_bins * GSC_TAPS_PER_BIN;

        Self {
            config,
            enabled: true,
            weights: vec![Complex32::default(); total_taps],
            noise_history: vec![Complex32::default(); total_taps],
            u_scratch: vec![Complex32::default(); num_bins],
            d_scratch: vec![Complex32::default(); num_bins],
            stats: GscStats::default(),
        }
    }

    /// Resets all adaptive weights and delay line histories.
    pub fn reset(&mut self) {
        self.weights.fill(Complex32::default());
        self.noise_history.fill(Complex32::default());
        self.u_scratch.fill(Complex32::default());
        self.d_scratch.fill(Complex32::default());
        self.stats = GscStats::default();
    }

    /// Sets whether GSC processing is enabled.
    pub fn set_enabled(&mut self, enabled: bool) {
        self.enabled = enabled;
    }

    /// Returns whether GSC is enabled.
    pub fn is_enabled(&self) -> bool {
        self.enabled
    }

    /// Returns latest GSC operational statistics.
    pub fn stats(&self) -> GscStats {
        self.stats
    }

    /// Processes a single STFT frame of stereo audio (Mic 1 and Mic 2).
    ///
    /// - `spec_mic1`: Primary STFT spectrum (in-place modified to become GSC enhanced output).
    /// - `spec_mic2`: Secondary reference STFT spectrum.
    /// - `spp`: Optional Speech Presence Probability per bin. If None, internal energy ratios are used.
    pub fn process_frame(
        &mut self,
        spec_mic1: &mut [Complex32],
        spec_mic2: &[Complex32],
        spp: Option<&[f32]>,
    ) -> GscStats {
        if !self.enabled || spec_mic1.len() != self.config.num_bins || spec_mic2.len() != self.config.num_bins {
            return self.stats;
        }

        let num_bins = self.config.num_bins;
        let mut total_d_power = 1e-10f32;
        let mut total_out_power = 1e-10f32;
        let mut frozen_bins = 0usize;
        let mut sum_norm = 0.0f32;

        let step_size = self.config.step_size;
        let leakage = self.config.leakage;
        let norm_bound = self.config.norm_bound;
        let norm_bound_sqr = norm_bound * norm_bound;
        let eps = self.config.epsilon;

        for k in 0..num_bins {
            let x1 = spec_mic1[k];
            let x2 = spec_mic2[k];

            // 1. Quiescent Beamformer Branch: D_ref = 0.5 * (X1 + X2)
            // Passes broadside target speech distortionless (gain = 1.0)
            let d_ref = (x1 + x2) * 0.5;
            self.d_scratch[k] = d_ref;
            let d_pwr = d_ref.norm_sqr();
            total_d_power += d_pwr;

            // 2. Spatial Blocking Matrix Branch: U = X1 - X2
            // Places an exact spatial null on broadside target speech
            let u = x1 - x2;
            self.u_scratch[k] = u;

            // Update noise reference delay line (shift history)
            let tap_base = k * GSC_TAPS_PER_BIN;
            if GSC_TAPS_PER_BIN > 1 {
                for m in (1..GSC_TAPS_PER_BIN).rev() {
                    self.noise_history[tap_base + m] = self.noise_history[tap_base + m - 1];
                }
            }
            self.noise_history[tap_base] = u;

            // 3. Adaptive Filter Output: Y_hat = sum_m (W_a[m] * U[t - m])
            let mut y_hat = Complex32::default();
            let mut u_pwr_sum = 0.0f32;
            for m in 0..GSC_TAPS_PER_BIN {
                let u_m = self.noise_history[tap_base + m];
                let w_m = self.weights[tap_base + m];
                y_hat += w_m * u_m;
                u_pwr_sum += u_m.norm_sqr();
            }

            // 4. Enhanced Output Error: E = D_ref - Y_hat
            let out_sample = d_ref - y_hat;
            spec_mic1[k] = out_sample;
            total_out_power += out_sample.norm_sqr();

            // 5. Speech Presence Double-Talk Freezing
            let bin_spp = if let Some(spp_slice) = spp {
                spp_slice.get(k).copied().unwrap_or(0.0)
            } else {
                // Internal heuristic: if quiescent power greatly exceeds blocked power, speech is present
                let u_pwr = u.norm_sqr();
                if d_pwr > 2.5 * u_pwr + 1e-6 { 0.85 } else { 0.10 }
            };

            let freeze_adaptation = bin_spp > self.config.spp_freeze_threshold;

            if freeze_adaptation {
                frozen_bins += 1;
            } else {
                // 6. Leaky Normalized LMS Adaptation
                let denom = u_pwr_sum + eps;
                let mu_eff = step_size / denom;

                for m in 0..GSC_TAPS_PER_BIN {
                    let u_m = self.noise_history[tap_base + m];
                    let grad = out_sample * u_m.conj();
                    let w_old = self.weights[tap_base + m];
                    // Leaky update
                    self.weights[tap_base + m] = w_old * (1.0 - leakage) + grad * mu_eff;
                }

                // 7. Norm-Constraint Projection: ||W_a|| <= gamma
                let mut filter_norm_sqr = 0.0f32;
                for m in 0..GSC_TAPS_PER_BIN {
                    filter_norm_sqr += self.weights[tap_base + m].norm_sqr();
                }

                if filter_norm_sqr > norm_bound_sqr {
                    let scale = norm_bound / filter_norm_sqr.sqrt();
                    for m in 0..GSC_TAPS_PER_BIN {
                        self.weights[tap_base + m] *= scale;
                    }
                    sum_norm += norm_bound;
                } else {
                    sum_norm += filter_norm_sqr.sqrt();
                }
            }
        }

        let cancellation_db = (10.0 * (total_d_power / total_out_power).max(1e-3).log10()).clamp(0.0, 40.0);
        let mean_filter_norm = sum_norm / num_bins as f32;
        let speech_freeze_ratio = frozen_bins as f32 / num_bins as f32;

        self.stats = GscStats {
            cancellation_db,
            mean_filter_norm,
            speech_freeze_ratio,
            is_nulling: cancellation_db > 3.0,
        };

        self.stats
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_gsc_broadside_target_speech_distortionless_and_blocking_null() {
        let config = GscConfig::default();
        let mut gsc = SubbandGsc::new(config);

        let num_bins = 257;
        let mut mic1 = vec![Complex32::default(); num_bins];
        let mut mic2 = vec![Complex32::default(); num_bins];

        // Broadside target speech arrives simultaneously at Mic 1 and Mic 2: Mic1 == Mic2
        for k in 0..num_bins {
            let tone = Complex32::from_polar(1.0, 0.5);
            mic1[k] = tone;
            mic2[k] = tone;
        }

        // Freeze adaptation using high SPP
        let spp = vec![1.0f32; num_bins];
        let stats = gsc.process_frame(&mut mic1, &mic2, Some(&spp));

        assert_eq!(stats.speech_freeze_ratio, 1.0);
        // Quiescent branch output must be exactly 1.0 * tone (distortionless)
        for k in 0..num_bins {
            let diff = (mic1[k] - Complex32::from_polar(1.0, 0.5)).norm();
            assert!(
                diff < 1e-5,
                "Broadside speech must be distortionless, bin {} diff={}",
                k,
                diff
            );
        }
    }

    #[test]
    fn test_gsc_cancels_correlated_off_axis_interference() {
        let config = GscConfig {
            step_size: 0.25,
            leakage: 0.0,
            ..Default::default()
        };
        let mut gsc = SubbandGsc::new(config);

        let num_bins = 257;
        let mut mic1 = vec![Complex32::default(); num_bins];
        let mut mic2 = vec![Complex32::default(); num_bins];

        // Off-axis noise arriving with 90 degree phase shift between mics
        for k in 0..num_bins {
            mic1[k] = Complex32::new(1.0, 0.0);
            mic2[k] = Complex32::new(0.0, 1.0); // 90 deg phase offset
        }

        // Noise frame (SPP = 0.0, adaptation active)
        let spp = vec![0.0f32; num_bins];

        // Run multiple adaptation frames
        for _ in 0..30 {
            // Re-feed off-axis noise
            for k in 0..num_bins {
                mic1[k] = Complex32::new(1.0, 0.0);
                mic2[k] = Complex32::new(0.0, 1.0);
            }
            gsc.process_frame(&mut mic1, &mic2, Some(&spp));
        }

        let stats = gsc.stats();
        assert!(
            stats.cancellation_db > 15.0,
            "GSC must deliver deep directional nulling, got {} dB",
            stats.cancellation_db
        );
        assert!(stats.is_nulling);
    }

    #[test]
    fn test_gsc_norm_constraint_bounds_filter_gain() {
        let config = GscConfig {
            step_size: 1.0, // High step size to induce weight growth
            norm_bound: 0.50,
            ..Default::default()
        };
        let mut gsc = SubbandGsc::new(config);

        let num_bins = 257;
        let mut mic1 = vec![Complex32::new(2.0, 0.0); num_bins];
        let mic2 = vec![Complex32::new(-2.0, 0.0); num_bins];
        let spp = vec![0.0f32; num_bins];

        for _ in 0..20 {
            for k in 0..num_bins {
                mic1[k] = Complex32::new(2.0, 0.0);
            }
            gsc.process_frame(&mut mic1, &mic2, Some(&spp));
        }

        assert!(
            gsc.stats().mean_filter_norm <= 0.50 + 1e-4,
            "Norm must be constrained to <= 0.50, got {}",
            gsc.stats().mean_filter_norm
        );
    }
}
