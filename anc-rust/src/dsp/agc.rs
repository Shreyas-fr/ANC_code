//! Truly causal running-RMS Automatic Gain Control (AGC).
//!
//! Provides level stabilization with strict causality (0.00 ms lookahead):
//! - Attack time: tau_att = 20 ms
//! - Release time: tau_rel = 200 ms
//! - Target level: -20 dBFS
//! - Gain clamping: [-6.0 dB, +24.0 dB]
//! - Pause detection: Freezes gain during quiet speech intervals to prevent noise pumping.

/// Causal AGC level controller.
pub struct CausalAgc {
    sample_rate: f32,
    target_rms: f32,
    alpha_attack: f32,
    alpha_release: f32,
    min_gain_linear: f32,
    max_gain_linear: f32,
    silence_threshold_rms: f32,

    running_rms: f32,
    current_gain: f32,
}

impl CausalAgc {
    /// Creates a new CausalAgc instance.
    pub fn new(
        sample_rate: f32,
        target_dbfs: f32,
        attack_ms: f32,
        release_ms: f32,
        min_gain_db: f32,
        max_gain_db: f32,
    ) -> Self {
        let target_rms = 10.0f32.powf(target_dbfs / 20.0);
        let min_gain_linear = 10.0f32.powf(min_gain_db / 20.0);
        let max_gain_linear = 10.0f32.powf(max_gain_db / 20.0);

        // Alpha = exp(-1 / (tau * fs))
        let tau_att_samples = (attack_ms * 0.001) * sample_rate;
        let tau_rel_samples = (release_ms * 0.001) * sample_rate;

        let alpha_attack = (-1.0 / tau_att_samples.max(1.0)).exp();
        let alpha_release = (-1.0 / tau_rel_samples.max(1.0)).exp();

        Self {
            sample_rate,
            target_rms,
            alpha_attack,
            alpha_release,
            min_gain_linear,
            max_gain_linear,
            silence_threshold_rms: 1e-4, // ~ -80 dBFS
            running_rms: target_rms,
            current_gain: 1.0,
        }
    }

    /// Resets running envelope and gain to 1.0 (0 dB).
    pub fn reset(&mut self) {
        self.running_rms = self.target_rms;
        self.current_gain = 1.0;
    }

    /// Processes a block of samples in-place.
    pub fn process_block(&mut self, samples: &mut [f32]) {
        if samples.is_empty() {
            return;
        }

        // Compute instantaneous block RMS
        let mut sum_sq = 0.0f32;
        for &s in samples.iter() {
            sum_sq += s * s;
        }
        let block_rms = (sum_sq / samples.len() as f32).sqrt();

        // Pause freeze: do not adapt gain on near-silent frames
        if block_rms > self.silence_threshold_rms {
            // Asymmetric attack/release envelope tracking
            let alpha = if block_rms > self.running_rms {
                self.alpha_attack
            } else {
                self.alpha_release
            };
            self.running_rms = alpha * self.running_rms + (1.0 - alpha) * block_rms;

            // Desired gain to hit target_rms
            let desired_gain = self.target_rms / self.running_rms.max(1e-6);
            let clamped_gain = desired_gain.clamp(self.min_gain_linear, self.max_gain_linear);

            // Smooth gain transition
            self.current_gain = 0.95 * self.current_gain + 0.05 * clamped_gain;
        }

        // Apply gain across samples
        let g = self.current_gain;
        for s in samples.iter_mut() {
            *s *= g;
        }
    }

    /// Returns current applied gain in decibels (dB).
    pub fn current_gain_db(&self) -> f32 {
        20.0 * self.current_gain.max(1e-6).log10()
    }

    /// Sampling rate in Hz.
    pub fn sample_rate(&self) -> f32 {
        self.sample_rate
    }
}
