//! Subband Causal Weighted Prediction Error (WPE) Dereverberation.
//!
//! Enclosed military vehicle cabins (T-90 tanks, BMP APCs, fighter cockpits)
//! suffer from severe metallic acoustic reflections (T60 > 300 ms).
//! This module implements an online, causal subband linear prediction dereverberator:
//!
//! D[k, t] = X[k, t] - \sum_{\tau = \Delta}^{K + \Delta - 1} W^*[k, \tau] X[k, t - \tau]
//!
//! With prediction delay \Delta = 2 frames (~16 ms), direct speech and early
//! reflections are strictly preserved while late reverberant tails are cancelled.

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

/// Real-time streaming subband causal dereverberator.
pub struct CausalDereverberator {
    config: DereverbConfig,
    /// Ring buffer of past complex spectra: [history_len][num_bins]
    history: Vec<Vec<Complex32>>,
    history_idx: usize,
    history_len: usize,
    /// Adaptive complex filter weights: [num_bins][filter_taps]
    weights: Vec<Vec<Complex32>>,
}

impl CausalDereverberator {
    /// Creates a new CausalDereverberator.
    pub fn new(config: DereverbConfig) -> Self {
        let history_len = config.delay_frames + config.filter_taps + 1;
        let num_bins = config.num_bins;
        let filter_taps = config.filter_taps;

        Self {
            history: vec![vec![Complex32::default(); num_bins]; history_len],
            history_idx: 0,
            history_len,
            weights: vec![vec![Complex32::default(); filter_taps]; num_bins],
            config,
        }
    }

    /// Resets all internal histories and adaptive weights.
    pub fn reset(&mut self) {
        for frame in &mut self.history {
            frame.fill(Complex32::default());
        }
        for w in &mut self.weights {
            w.fill(Complex32::default());
        }
        self.history_idx = 0;
    }

    /// Processes a single STFT complex spectrum frame in-place.
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
        self.history[self.history_idx].copy_from_slice(spec);

        for k in 0..self.config.num_bins {
            let x_k = spec[k];

            // 1. Predict late reverberation from delayed past frames:
            // \hat{R}[k] = \sum_{\tau = 0}^{taps - 1} W[k, \tau] * X[k, t - delay - \tau]
            let mut pred_rev = Complex32::default();
            let mut delayed_energy = 0.0f32;

            for tau in 0..taps {
                let past_offset = delay + tau;
                let past_idx = (self.history_idx + self.history_len - past_offset) % self.history_len;
                let x_past = self.history[past_idx][k];

                pred_rev += self.weights[k][tau] * x_past;
                delayed_energy += x_past.norm_sqr();
            }

            // 2. Dereverberated direct signal: D[k] = X[k] - \hat{R}[k]
            // Limit late reflection subtraction to avoid over-subtraction musical artifacts
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
                    let x_past = self.history[past_idx][k];

                    // W[k, \tau] = leakage * W[k, \tau] + norm_factor * err * conj(x_past)
                    let delta_w = err * x_past.conj() * norm_factor;
                    self.weights[k][tau] = self.weights[k][tau] * leakage + delta_w;

                    // Clamp weight magnitude to prevent divergence
                    let w_norm = self.weights[k][tau].norm();
                    if w_norm > 1.2 {
                        self.weights[k][tau] *= 1.2 / w_norm;
                    }
                }
            }
        }

        // Advance history pointer
        self.history_idx = (self.history_idx + 1) % self.history_len;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_dereverb_preserves_initial_direct_impulse() {
        let mut dereverb = CausalDereverberator::new(DereverbConfig {
            num_bins: 65,
            delay_frames: 2,
            filter_taps: 3,
            step_size: 0.1,
            eps: 1e-4,
            leakage: 0.999,
        });

        let spp = vec![1.0f32; 65];
        let mut direct_frame = vec![Complex32::new(1.0, 0.0); 65];
        let original_val = direct_frame[10];

        // Process first frame
        dereverb.process_frame(&mut direct_frame, &spp);

        // First frame has no history, direct impulse must pass with zero distortion
        assert!((direct_frame[10].re - original_val.re).abs() < 1e-4);
    }

    #[test]
    fn test_dereverb_converges_and_attenuates_delayed_echo() {
        let mut dereverb = CausalDereverberator::new(DereverbConfig {
            num_bins: 65,
            delay_frames: 2,
            filter_taps: 3,
            step_size: 0.25,
            eps: 1e-4,
            leakage: 0.9999,
        });

        let spp = vec![1.0f32; 65];

        // Simulate repetitive room reflection with delay = 2 frames and attenuation = 0.4
        let direct_tone = Complex32::new(0.8, 0.2);
        let echo_val = direct_tone * 0.4;

        for step in 0..100 {
            let mut frame = vec![Complex32::default(); 65];
            if step % 8 == 0 {
                // Direct path
                frame[20] = direct_tone;
            } else if step % 8 == 2 {
                // Late echo arriving 2 frames later
                frame[20] = echo_val;
            }
            dereverb.process_frame(&mut frame, &spp);
        }

        // Test attenuation on the 2-frame delayed echo
        let mut test_echo = vec![Complex32::default(); 65];
        test_echo[20] = echo_val;

        // Process a few frames to establish delayed state
        let mut direct_test = vec![Complex32::default(); 65];
        direct_test[20] = direct_tone;
        dereverb.process_frame(&mut direct_test, &spp);

        let mut blank_frame = vec![Complex32::default(); 65];
        dereverb.process_frame(&mut blank_frame, &spp);

        let mut echo_frame = test_echo.clone();
        dereverb.process_frame(&mut echo_frame, &spp);

        // Late echo should be attenuated relative to original echo value
        assert!(
            echo_frame[20].norm() < echo_val.norm(),
            "Late reflection must be attenuated by predictive filter: got {}, expected < {}",
            echo_frame[20].norm(),
            echo_val.norm()
        );
    }
}
