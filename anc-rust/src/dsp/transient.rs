//! Acoustic Transient Suppressor and Concussion Blanker.
//!
//! Detects sudden high-energy impulsive transients (artillery shockwaves, gunshots,
//! explosive concussions, sharp metallic impacts) using instantaneous energy jump (dE/dt)
//! and Crest Factor relative to the running speech envelope.
//! Clamps acoustic shockwaves with zero lookahead latency and a smooth release envelope
//! (~20 ms) to protect user hearing and prevent STFT spectral splatter.

/// Configuration parameters for the Transient Blanker.
#[derive(Debug, Clone)]
pub struct TransientConfig {
    pub sample_rate: f32,
    /// Energy delta jump threshold (sample-to-sample difference)
    pub delta_threshold: f32,
    /// Crest factor threshold (|x| / E_avg)
    pub crest_threshold: f32,
    /// Release time constant in seconds (~20 ms)
    pub release_tau_s: f32,
    /// Maximum allowed peak amplitude during a transient
    pub clamp_ceiling: f32,
}

impl Default for TransientConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000.0,
            delta_threshold: 0.60,
            crest_threshold: 3.8,
            release_tau_s: 0.020,
            clamp_ceiling: 0.70,
        }
    }
}

/// Real-time causal acoustic transient blanker.
pub struct TransientBlanker {
    config: TransientConfig,
    avg_alpha: f32,
    release_alpha: f32,
    running_avg: f32,
    prev_sample: f32,
    current_gain: f32,
    transient_active: bool,
    transients_detected: u64,
}

impl TransientBlanker {
    /// Creates a new TransientBlanker with given configuration.
    pub fn new(config: TransientConfig) -> Self {
        let sr = config.sample_rate;
        let avg_alpha = (-1.0 / (0.025 * sr)).exp(); // ~25 ms envelope tracker
        let release_alpha = (-1.0 / (config.release_tau_s * sr)).exp();

        Self {
            config,
            avg_alpha,
            release_alpha,
            running_avg: 0.05,
            prev_sample: 0.0,
            current_gain: 1.0,
            transient_active: false,
            transients_detected: 0,
        }
    }

    /// Resets filter states to initial quiet state.
    pub fn reset(&mut self) {
        self.running_avg = 0.05;
        self.prev_sample = 0.0;
        self.current_gain = 1.0;
        self.transient_active = false;
        self.transients_detected = 0;
    }

    /// Returns the total number of transient events clamped.
    #[inline]
    pub fn transients_detected(&self) -> u64 {
        self.transients_detected
    }

    /// Returns whether a transient suppression event is currently active.
    #[inline]
    pub fn is_active(&self) -> bool {
        self.transient_active
    }

    /// Processes an in-place slice of audio samples (zero allocation).
    pub fn process(&mut self, samples: &mut [f32]) {
        for s in samples.iter_mut() {
            let abs_val = s.abs();

            // Track background speech average
            self.running_avg = (1.0 - self.avg_alpha) * abs_val + self.avg_alpha * self.running_avg;
            let bg = self.running_avg.max(0.04);

            let delta = abs_val - self.prev_sample.abs();
            let crest = abs_val / bg;

            // Transient detection: instantaneous violent step AND extreme crest factor, or hard overscale
            let is_transient_onset = (delta > self.config.delta_threshold && crest > self.config.crest_threshold)
                || abs_val > 1.25;

            if is_transient_onset {
                if !self.transient_active {
                    self.transients_detected += 1;
                    self.transient_active = true;
                }
                let target_gain = (self.config.clamp_ceiling / abs_val.max(1e-4)).min(1.0);
                self.current_gain = self.current_gain.min(target_gain);
            } else {
                if self.transient_active && self.current_gain > 0.95 {
                    self.transient_active = false;
                }
                // Smooth exponential release back to unity gain
                self.current_gain = (1.0 - self.release_alpha) * 1.0 + self.release_alpha * self.current_gain;
            }

            *s *= self.current_gain;
            self.prev_sample = *s;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_transient_suppression_on_impulse() {
        let mut blanker = TransientBlanker::new(TransientConfig::default());

        // Feed background quiet noise
        let mut bg = vec![0.02f32; 800];
        blanker.process(&mut bg);
        assert_eq!(blanker.transients_detected(), 0);

        // Inject severe gunshot impulse (amplitude 2.0 = +40 dB jump)
        let mut impulse_block = vec![0.02f32; 160];
        impulse_block[10] = 2.0;
        impulse_block[11] = 1.8;
        impulse_block[12] = 1.2;

        blanker.process(&mut impulse_block);

        assert!(blanker.transients_detected() >= 1);
        // The peak sample must be attenuated significantly below 1.0
        assert!(impulse_block[10] <= 0.75, "Impulse should be clamped to ceiling, got {}", impulse_block[10]);
    }

    #[test]
    fn test_transient_preserves_steady_speech() {
        let mut blanker = TransientBlanker::new(TransientConfig::default());

        // Feed a smooth sinusoidal tone simulating steady speech vowel
        let mut tone: Vec<f32> = (0..1600)
            .map(|i| (2.0 * std::f32::consts::PI * 300.0 * (i as f32) / 16000.0).sin() * 0.3)
            .collect();

        let original_rms: f32 = (tone.iter().map(|s| s * s).sum::<f32>() / tone.len() as f32).sqrt();
        blanker.process(&mut tone);
        let processed_rms: f32 = (tone.iter().map(|s| s * s).sum::<f32>() / tone.len() as f32).sqrt();

        // Steady signal should not trigger false transient blanking
        assert_eq!(blanker.transients_detected(), 0);
        let ratio = processed_rms / original_rms;
        assert!((ratio - 1.0).abs() < 0.05, "Steady tone RMS should remain intact, ratio = {}", ratio);
    }
}
