//! Subband Causal Weighted Prediction Error (WPE) Dereverberation.
//!
//! Enclosed military vehicle cabins (T-90 tanks, BMP APCs, fighter cockpits, and command bunkers)
//! suffer from severe metallic acoustic reflections (T60 > 300 ms).
//! This module implements an online, causal subband linear prediction dereverberator supporting both:
//! 1. Single-channel subband linear prediction:
//!    D[k, t] = X[k, t] - \sum_{\tau = 0}^{K - 1} W^*[k, \tau] X[k, t - \Delta - \tau]
//! 2. Multi-Channel Coupled Dual-Microphone Linear Prediction:
//!    D_m[k, t] = X_m[k, t] - \sum_{c=1}^2 \sum_{\tau = 0}^{K - 1} W^*_{m, c}[k, \tau] X_c[k, t - \Delta - \tau]
//!
//! With prediction delay \Delta = 2 frames (~16 ms @ 128 hop), direct speech and early
//! reflections are strictly preserved while late reverberant tails and spatial cross-reflections
//! are decoupled before MVDR spatial covariance estimation.

use num_complex::Complex32;

/// Configuration for the Causal Dereverberator.
#[derive(Debug, Clone)]
pub struct DereverbConfig {
    pub num_bins: usize,
    /// Prediction delay \Delta in frames (preserves direct path + early reflections)
    pub delay_frames: usize,
    /// Number of prediction filter taps K per subband
    pub filter_taps: usize,
    /// Step size \mu for Normalized Least Mean Squares update
    pub step_size: f32,
    /// Regularization epsilon to prevent division by near-zero energy
    pub eps: f32,
    /// Forgetting / leakage factor (0.9995 = slow decay of inactive filter coefficients)
    pub leakage: f32,
}

impl Default for DereverbConfig {
    fn default() -> Self {
        Self {
            num_bins: 257,
            delay_frames: 2,
            filter_taps: 3,
            step_size: 0.08,
            eps: 1e-4,
            leakage: 0.9992,
        }
    }
}

/// Real-time streaming subband causal dereverberator supporting single and coupled multi-channel operation.
pub struct CausalDereverberator {
    config: DereverbConfig,
    /// Ring buffer of past complex spectra for Channel 1: [history_len][num_bins]
    history_ch1: Vec<Vec<Complex32>>,
    /// Ring buffer of past complex spectra for Channel 2: [history_len][num_bins]
    history_ch2: Vec<Vec<Complex32>>,
    history_idx: usize,
    history_len: usize,
    /// Adaptive complex filter weights:
    /// Channel 1 predicted from Channel 1 history: [num_bins][filter_taps]
    weights_ch1_from_ch1: Vec<Vec<Complex32>>,
    /// Channel 1 predicted from Channel 2 history: [num_bins][filter_taps]
    weights_ch1_from_ch2: Vec<Vec<Complex32>>,
    /// Channel 2 predicted from Channel 1 history: [num_bins][filter_taps]
    weights_ch2_from_ch1: Vec<Vec<Complex32>>,
    /// Channel 2 predicted from Channel 2 history: [num_bins][filter_taps]
    weights_ch2_from_ch2: Vec<Vec<Complex32>>,
}

impl CausalDereverberator {
    /// Creates a new CausalDereverberator.
    pub fn new(config: DereverbConfig) -> Self {
        let history_len = config.delay_frames + config.filter_taps + 1;
        let num_bins = config.num_bins;
        let filter_taps = config.filter_taps;

        Self {
            history_ch1: vec![vec![Complex32::default(); num_bins]; history_len],
            history_ch2: vec![vec![Complex32::default(); num_bins]; history_len],
            history_idx: 0,
            history_len,
            weights_ch1_from_ch1: vec![vec![Complex32::default(); filter_taps]; num_bins],
            weights_ch1_from_ch2: vec![vec![Complex32::default(); filter_taps]; num_bins],
            weights_ch2_from_ch1: vec![vec![Complex32::default(); filter_taps]; num_bins],
            weights_ch2_from_ch2: vec![vec![Complex32::default(); filter_taps]; num_bins],
            config,
        }
    }

    /// Resets all internal histories and adaptive weights.
    pub fn reset(&mut self) {
        for frame in &mut self.history_ch1 {
            frame.fill(Complex32::default());
        }
        for frame in &mut self.history_ch2 {
            frame.fill(Complex32::default());
        }
        for w in &mut self.weights_ch1_from_ch1 {
            w.fill(Complex32::default());
        }
        for w in &mut self.weights_ch1_from_ch2 {
            w.fill(Complex32::default());
        }
        for w in &mut self.weights_ch2_from_ch1 {
            w.fill(Complex32::default());
        }
        for w in &mut self.weights_ch2_from_ch2 {
            w.fill(Complex32::default());
        }
        self.history_idx = 0;
    }

    /// Single-channel subband dereverberation in-place (Channel 1).
    ///
    /// `spec`: Slice of length `num_bins`.
    /// `spp`: Speech presence probability per bin or scalar indicator (0.0 to 1.0).
    pub fn process_frame(&mut self, spec: &mut [Complex32], spp: &[f32]) {
        assert_eq!(spec.len(), self.config.num_bins);

        let delay = self.config.delay_frames;
        let taps = self.config.filter_taps;
        let mu = self.config.step_size;
        let eps = self.config.eps;
        let leakage = self.config.leakage;

        // Save current frame into cyclic history
        self.history_ch1[self.history_idx].copy_from_slice(spec);

        for k in 0..self.config.num_bins {
            let x_k = spec[k];

            // 1. Predict late reverberation from delayed past frames:
            // \hat{R}[k] = \sum_{\tau = 0}^{taps - 1} W[k, \tau] * X[k, t - delay - \tau]
            let mut pred_rev = Complex32::default();
            let mut delayed_energy = 0.0f32;

            for tau in 0..taps {
                let past_offset = delay + tau;
                let past_idx = (self.history_idx + self.history_len - past_offset) % self.history_len;
                let x_past = self.history_ch1[past_idx][k];

                pred_rev += self.weights_ch1_from_ch1[k][tau] * x_past;
                delayed_energy += x_past.norm_sqr();
            }

            // 2. Dereverberated direct signal: D[k] = X[k] - \hat{R}[k]
            let sub_ratio = (pred_rev.norm() / (x_k.norm() + 1e-6)).min(0.65);
            let d_k = if sub_ratio > 0.05 {
                let scaled_pred = pred_rev * (sub_ratio / (pred_rev.norm() + 1e-6));
                x_k - scaled_pred
            } else {
                x_k
            };

            spec[k] = d_k;

            // 3. Normalized LMS adaptive weight update (only when speech is present)
            let speech_prob = if k < spp.len() { spp[k] } else { 0.5 };
            if speech_prob > 0.25 {
                let norm_factor = mu / (delayed_energy + eps);
                let err = d_k;

                for tau in 0..taps {
                    let past_offset = delay + tau;
                    let past_idx = (self.history_idx + self.history_len - past_offset) % self.history_len;
                    let x_past = self.history_ch1[past_idx][k];

                    let delta_w = err * x_past.conj() * norm_factor;
                    self.weights_ch1_from_ch1[k][tau] = self.weights_ch1_from_ch1[k][tau] * leakage + delta_w;

                    let w_norm = self.weights_ch1_from_ch1[k][tau].norm();
                    if w_norm > 1.2 {
                        self.weights_ch1_from_ch1[k][tau] *= 1.2 / w_norm;
                    }
                }
            }
        }

        // Advance history pointer
        self.history_idx = (self.history_idx + 1) % self.history_len;
    }

    /// Joint Multi-Channel Coupled Dual-Microphone Dereverberation in-place.
    ///
    /// Decouples spatial acoustic reflections across both microphones before MVDR spatial covariance estimation:
    /// - `mic1_spec`: Primary microphone STFT complex spectrum (in/out).
    /// - `mic2_spec`: Secondary reference microphone STFT complex spectrum (in/out).
    /// - `spp`: Speech presence probability per bin (0.0 to 1.0).
    pub fn process_dual_frame(
        &mut self,
        mic1_spec: &mut [Complex32],
        mic2_spec: &mut [Complex32],
        spp: &[f32],
    ) {
        let num_bins = self.config.num_bins;
        assert_eq!(mic1_spec.len(), num_bins);
        assert_eq!(mic2_spec.len(), num_bins);

        let delay = self.config.delay_frames;
        let taps = self.config.filter_taps;
        let mu = self.config.step_size;
        let eps = self.config.eps;
        let leakage = self.config.leakage;

        // Save current frames into cyclic histories
        self.history_ch1[self.history_idx].copy_from_slice(mic1_spec);
        self.history_ch2[self.history_idx].copy_from_slice(mic2_spec);

        for k in 0..num_bins {
            let x1_k = mic1_spec[k];
            let x2_k = mic2_spec[k];

            // 1. Joint prediction of late reflections on both channels:
            // R_hat_1[k] = sum_tau (W_11 * X_1_past + W_12 * X_2_past)
            // R_hat_2[k] = sum_tau (W_21 * X_1_past + W_22 * X_2_past)
            let mut pred_rev1 = Complex32::default();
            let mut pred_rev2 = Complex32::default();
            let mut delayed_energy = 0.0f32;

            for tau in 0..taps {
                let past_offset = delay + tau;
                let past_idx = (self.history_idx + self.history_len - past_offset) % self.history_len;
                let x1_past = self.history_ch1[past_idx][k];
                let x2_past = self.history_ch2[past_idx][k];

                pred_rev1 += self.weights_ch1_from_ch1[k][tau] * x1_past
                    + self.weights_ch1_from_ch2[k][tau] * x2_past;
                pred_rev2 += self.weights_ch2_from_ch1[k][tau] * x1_past
                    + self.weights_ch2_from_ch2[k][tau] * x2_past;

                delayed_energy += x1_past.norm_sqr() + x2_past.norm_sqr();
            }

            // 2. Dereverberated signals with bounded subtraction ratio
            let sub_ratio1 = (pred_rev1.norm() / (x1_k.norm() + 1e-6)).min(0.65);
            let d1_k = if sub_ratio1 > 0.05 {
                let scaled_pred = pred_rev1 * (sub_ratio1 / (pred_rev1.norm() + 1e-6));
                x1_k - scaled_pred
            } else {
                x1_k
            };

            let sub_ratio2 = (pred_rev2.norm() / (x2_k.norm() + 1e-6)).min(0.65);
            let d2_k = if sub_ratio2 > 0.05 {
                let scaled_pred = pred_rev2 * (sub_ratio2 / (pred_rev2.norm() + 1e-6));
                x2_k - scaled_pred
            } else {
                x2_k
            };

            mic1_spec[k] = d1_k;
            mic2_spec[k] = d2_k;

            // 3. Multi-Channel Normalized LMS Weight Update
            let speech_prob = if k < spp.len() { spp[k] } else { 0.5 };
            if speech_prob > 0.25 {
                let norm_factor = mu / (delayed_energy + eps);

                for tau in 0..taps {
                    let past_offset = delay + tau;
                    let past_idx = (self.history_idx + self.history_len - past_offset) % self.history_len;
                    let x1_past_conj = self.history_ch1[past_idx][k].conj();
                    let x2_past_conj = self.history_ch2[past_idx][k].conj();

                    // Channel 1 updates
                    let dw11 = d1_k * x1_past_conj * norm_factor;
                    let dw12 = d1_k * x2_past_conj * norm_factor;
                    self.weights_ch1_from_ch1[k][tau] = self.weights_ch1_from_ch1[k][tau] * leakage + dw11;
                    self.weights_ch1_from_ch2[k][tau] = self.weights_ch1_from_ch2[k][tau] * leakage + dw12;

                    // Channel 2 updates
                    let dw21 = d2_k * x1_past_conj * norm_factor;
                    let dw22 = d2_k * x2_past_conj * norm_factor;
                    self.weights_ch2_from_ch1[k][tau] = self.weights_ch2_from_ch1[k][tau] * leakage + dw21;
                    self.weights_ch2_from_ch2[k][tau] = self.weights_ch2_from_ch2[k][tau] * leakage + dw22;

                    // Clamp norms
                    let w11_norm = self.weights_ch1_from_ch1[k][tau].norm();
                    if w11_norm > 1.2 {
                        self.weights_ch1_from_ch1[k][tau] *= 1.2 / w11_norm;
                    }
                    let w12_norm = self.weights_ch1_from_ch2[k][tau].norm();
                    if w12_norm > 1.2 {
                        self.weights_ch1_from_ch2[k][tau] *= 1.2 / w12_norm;
                    }
                    let w21_norm = self.weights_ch2_from_ch1[k][tau].norm();
                    if w21_norm > 1.2 {
                        self.weights_ch2_from_ch1[k][tau] *= 1.2 / w21_norm;
                    }
                    let w22_norm = self.weights_ch2_from_ch2[k][tau].norm();
                    if w22_norm > 1.2 {
                        self.weights_ch2_from_ch2[k][tau] *= 1.2 / w22_norm;
                    }
                }
            }
        }

        // Advance cyclic history index
        self.history_idx = (self.history_idx + 1) % self.history_len;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_dereverb_preserves_initial_direct_impulse() {
        let config = DereverbConfig {
            num_bins: 65,
            delay_frames: 2,
            filter_taps: 3,
            step_size: 0.1,
            ..Default::default()
        };
        let mut dereverb = CausalDereverberator::new(config);

        // Frame 0: Sharp direct speech impulse
        let mut frame0 = vec![Complex32::new(10.0, 0.0); 65];
        let spp = vec![1.0; 65];
        dereverb.process_frame(&mut frame0, &spp);

        // Direct path must remain 100% intact (delay = 2 prevents any subtraction)
        for (k, &val) in frame0.iter().enumerate() {
            assert!(
                (val.norm() - 10.0).abs() < 1e-3,
                "Frame 0 direct impulse should be preserved, bin {} got {}",
                k,
                val.norm()
            );
        }
    }

    #[test]
    fn test_dereverb_converges_and_attenuates_delayed_echo() {
        let config = DereverbConfig {
            num_bins: 16,
            delay_frames: 2,
            filter_taps: 2,
            step_size: 0.15,
            eps: 1e-4,
            leakage: 0.9995,
        };
        let mut dereverb = CausalDereverberator::new(config);

        let spp = vec![1.0; 16];
        let echo_attenuation = 0.50f32;

        // Repeat a simulated direct impulse followed 2 frames later by a reverberant reflection
        for _epoch in 0..40 {
            // Frame t: Direct speech impulse
            let mut direct_frame = vec![Complex32::new(5.0, 0.0); 16];
            dereverb.process_frame(&mut direct_frame, &spp);

            // Frame t+1: Silent early gap
            let mut gap_frame = vec![Complex32::default(); 16];
            dereverb.process_frame(&mut gap_frame, &spp);

            // Frame t+2: Delayed reverberant room echo
            let mut echo_frame = vec![Complex32::new(5.0 * echo_attenuation, 0.0); 16];
            dereverb.process_frame(&mut echo_frame, &spp);
        }

        // Test frame with delayed echo after learning
        let mut test_echo = vec![Complex32::new(5.0 * echo_attenuation, 0.0); 16];
        dereverb.process_frame(&mut test_echo, &spp);

        let original_echo_mag = 5.0 * echo_attenuation;
        let dereverberated_mag = test_echo[0].norm();

        assert!(
            dereverberated_mag < original_echo_mag * 0.80,
            "Reverberant echo must be attenuated by at least 20%: orig={}, out={}",
            original_echo_mag,
            dereverberated_mag
        );
    }

    #[test]
    fn test_dual_channel_coupled_dereverb_preserves_direct_impulse() {
        let config = DereverbConfig {
            num_bins: 32,
            delay_frames: 2,
            filter_taps: 3,
            step_size: 0.1,
            ..Default::default()
        };
        let mut dereverb = CausalDereverberator::new(config);

        let mut mic1 = vec![Complex32::new(8.0, 0.0); 32];
        let mut mic2 = vec![Complex32::new(6.0, 1.0); 32];
        let spp = vec![1.0; 32];

        dereverb.process_dual_frame(&mut mic1, &mut mic2, &spp);

        // Frame 0 direct speech impulses must remain intact on both channels
        for k in 0..32 {
            assert!(
                (mic1[k].norm() - 8.0).abs() < 1e-3,
                "Mic 1 direct impulse must be preserved at bin {}",
                k
            );
            assert!(
                (mic2[k].norm() - (37.0f32).sqrt()).abs() < 1e-3,
                "Mic 2 direct impulse must be preserved at bin {}",
                k
            );
        }
    }

    #[test]
    fn test_dual_channel_coupled_dereverb_converges_on_cross_reflections() {
        let config = DereverbConfig {
            num_bins: 16,
            delay_frames: 2,
            filter_taps: 2,
            step_size: 0.15,
            eps: 1e-4,
            leakage: 0.9995,
        };
        let mut dereverb = CausalDereverberator::new(config);
        let spp = vec![1.0; 16];

        // Simulate speech at mic 1 with cross-reflection leaking into mic 2 after 2 frames
        for _ in 0..45 {
            // Direct arrival
            let mut m1 = vec![Complex32::new(4.0, 0.0); 16];
            let mut m2 = vec![Complex32::new(2.0, 0.0); 16];
            dereverb.process_dual_frame(&mut m1, &mut m2, &spp);

            // Frame gap
            let mut m1_gap = vec![Complex32::default(); 16];
            let mut m2_gap = vec![Complex32::default(); 16];
            dereverb.process_dual_frame(&mut m1_gap, &mut m2_gap, &spp);

            // Reflection arrival at delay = 2
            let mut m1_refl = vec![Complex32::new(1.8, 0.0); 16];
            let mut m2_refl = vec![Complex32::new(2.2, 0.0); 16];
            dereverb.process_dual_frame(&mut m1_refl, &mut m2_refl, &spp);
        }

        // Test reflection attenuation
        let mut test_m1 = vec![Complex32::new(1.8, 0.0); 16];
        let mut test_m2 = vec![Complex32::new(2.2, 0.0); 16];
        dereverb.process_dual_frame(&mut test_m1, &mut test_m2, &spp);

        assert!(
            test_m1[0].norm() < 1.8 * 0.85,
            "Mic 1 reflection should be attenuated by >= 15%, got {:.3}",
            test_m1[0].norm()
        );
        assert!(
            test_m2[0].norm() < 2.2 * 0.85,
            "Mic 2 reflection should be attenuated by >= 15%, got {:.3}",
            test_m2[0].norm()
        );
    }
}
