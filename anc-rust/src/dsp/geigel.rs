//! ITU-T G.168 Geigel Double-Talk Detector for Acoustic Feedback Cancellation (AFC).
//!
//! In tactical communication headsets, loudspeaker audio leaks acoustically and mechanically
//! into the microphone. While the adaptive filter cancels this echo, if the near-end soldier
//! speaks simultaneously (double-talk), the near-end speech acts as a large disturbance signal,
//! causing the adaptive filter to rapidly diverge and corrupt the soldier's voice.
//!
//! The ITU-T G.168 Geigel detector evaluates the instantaneous ratio of the microphone signal
//! magnitude $|d(t)|$ against the maximum loudspeaker reference magnitude observed across the
//! acoustic impulse response window $L$:
//!
//! $$\text{Geigel}(t) = \frac{|d(t)|}{\max_{\tau=0..L} |x(t - \tau)| + \epsilon}$$
//!
//! When $\text{Geigel}(t) > \text{threshold}$ (typically $0.50 \approx -6\text{ dB}$), near-end speech
//! is declared and the AFC weight adaptation is instantly frozen in $< 0.25\text{ ms}$.
//! A configurable hangover counter preserves the frozen state through brief speech pauses to prevent
//! filter fluttering.
//!
//! Strictly pre-allocated circular delay lines with ZERO HEAP ALLOCATIONS in the real-time loop.

use num_complex::Complex32;

/// Configuration for the ITU-T G.168 Geigel Double-Talk Detector.
#[derive(Debug, Clone)]
pub struct GeigelConfig {
    /// Audio sample rate in Hz (default: 16000.0)
    pub sample_rate: f32,
    /// Delay line history window $L$ in samples (e.g. 512 samples = 32.0 ms @ 16 kHz)
    pub history_len: usize,
    /// Geigel detection threshold (default: 0.50 = -6.0 dB)
    pub threshold: f32,
    /// Hangover duration in milliseconds (default: 50.0 ms)
    pub hangover_ms: f32,
    /// Minimum reference signal threshold to prevent division by zero on absolute silence
    pub min_ref_threshold: f32,
    /// Regularization epsilon
    pub eps: f32,
}

impl Default for GeigelConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000.0,
            history_len: 512,
            threshold: 0.50,
            hangover_ms: 50.0,
            min_ref_threshold: 1e-4,
            eps: 1e-6,
        }
    }
}

/// Real-time diagnostic statistics from the Geigel detector.
#[derive(Debug, Clone, Copy, Default)]
pub struct GeigelStats {
    /// Whether double-talk is actively detected
    pub is_double_talk: bool,
    /// Computed Geigel ratio metric
    pub geigel_metric: f32,
    /// Peak absolute amplitude in reference history line
    pub peak_reference: f32,
    /// Current near-end microphone amplitude or norm
    pub mic_magnitude: f32,
    /// Whether the hangover hold-time is actively extending the freeze
    pub hangover_active: bool,
    /// Recommended adaptation step size scale factor (0.0 = completely frozen, 1.0 = full adaptation)
    pub step_scale: f32,
}

/// Zero-allocation ITU-T G.168 Geigel Double-Talk Detector.
pub struct GeigelDetector {
    config: GeigelConfig,
    ref_history: Vec<f32>,
    history_idx: usize,
    hangover_samples_total: usize,
    hangover_countdown: usize,
    current_stats: GeigelStats,
}

impl GeigelDetector {
    /// Creates a new GeigelDetector with pre-allocated circular delay line.
    pub fn new(config: GeigelConfig) -> Self {
        let history_len = config.history_len.max(16);
        let hangover_samples_total =
            ((config.hangover_ms / 1000.0) * config.sample_rate).round() as usize;

        Self {
            config,
            ref_history: vec![0.0f32; history_len],
            history_idx: 0,
            hangover_samples_total,
            hangover_countdown: 0,
            current_stats: GeigelStats::default(),
        }
    }

    /// Resets delay line and internal states to initial silence.
    pub fn reset(&mut self) {
        self.ref_history.fill(0.0);
        self.history_idx = 0;
        self.hangover_countdown = 0;
        self.current_stats = GeigelStats::default();
    }

    /// Returns the current configuration.
    pub fn config(&self) -> &GeigelConfig {
        &self.config
    }

    /// Evaluates double-talk condition on a single sample pair $(d(t), x(t))$.
    ///
    /// - `mic_sample`: near-end microphone signal $d(t)$.
    /// - `ref_sample`: loudspeaker reference signal $x(t)$.
    ///
    /// Strictly zero heap allocations.
    #[inline]
    pub fn process_sample(&mut self, mic_sample: f32, ref_sample: f32) -> GeigelStats {
        // 1. Update circular history buffer with new reference sample
        self.ref_history[self.history_idx] = ref_sample.abs();
        self.history_idx = (self.history_idx + 1) % self.ref_history.len();

        // 2. Find max absolute reference in circular buffer L
        let mut max_ref = 0.0f32;
        for &r in self.ref_history.iter() {
            if r > max_ref {
                max_ref = r;
            }
        }

        let mic_mag = mic_sample.abs();

        // 3. Compute Geigel metric
        let geigel_metric = if max_ref >= self.config.min_ref_threshold {
            mic_mag / (max_ref + self.config.eps)
        } else {
            0.0
        };

        // 4. Trigger double-talk detection and update hangover
        let raw_trigger =
            geigel_metric > self.config.threshold && max_ref >= self.config.min_ref_threshold;

        if raw_trigger {
            self.hangover_countdown = self.hangover_samples_total;
        } else if self.hangover_countdown > 0 {
            self.hangover_countdown -= 1;
        }

        let is_double_talk = raw_trigger || (self.hangover_countdown > 0);
        let hangover_active = !raw_trigger && (self.hangover_countdown > 0);

        // When double-talk is detected, instantly freeze adaptation (scale 0.0)
        let step_scale = if is_double_talk { 0.0 } else { 1.0 };

        self.current_stats = GeigelStats {
            is_double_talk,
            geigel_metric,
            peak_reference: max_ref,
            mic_magnitude: mic_mag,
            hangover_active,
            step_scale,
        };

        self.current_stats
    }

    /// Evaluates double-talk condition across an audio block.
    ///
    /// Returns the worst-case `GeigelStats` over the block. Strictly zero heap allocations.
    pub fn process_block(&mut self, mic_block: &[f32], ref_block: &[f32]) -> GeigelStats {
        let n = mic_block.len().min(ref_block.len());
        let mut worst_stats = GeigelStats::default();

        for i in 0..n {
            let stats = self.process_sample(mic_block[i], ref_block[i]);
            if stats.is_double_talk {
                worst_stats.is_double_talk = true;
                worst_stats.step_scale = 0.0;
            }
            if stats.geigel_metric > worst_stats.geigel_metric {
                worst_stats.geigel_metric = stats.geigel_metric;
                worst_stats.mic_magnitude = stats.mic_magnitude;
                worst_stats.peak_reference = stats.peak_reference;
            }
            worst_stats.hangover_active = stats.hangover_active;
        }

        if !worst_stats.is_double_talk {
            worst_stats.step_scale = 1.0;
        }

        worst_stats
    }

    /// Evaluates double-talk condition in the frequency/subband domain from STFT spectra.
    ///
    /// Computes RMS magnitudes across frequency bins to evaluate broad-spectrum Geigel metric.
    /// Strictly zero heap allocations.
    pub fn process_spectrum(
        &mut self,
        mic_spec: &[Complex32],
        ref_spec: &[Complex32],
    ) -> GeigelStats {
        let num_bins = mic_spec.len().min(ref_spec.len()).max(1);
        let mut mic_pwr = 0.0f32;
        let mut ref_pwr = 0.0f32;

        for (m, r) in mic_spec.iter().zip(ref_spec.iter()) {
            mic_pwr += m.norm_sqr();
            ref_pwr += r.norm_sqr();
        }

        let mic_rms = (mic_pwr / num_bins as f32).sqrt();
        let ref_rms = (ref_pwr / num_bins as f32).sqrt();

        self.process_sample(mic_rms, ref_rms)
    }

    /// Returns the most recent diagnostic statistics.
    #[inline]
    pub fn stats(&self) -> GeigelStats {
        self.current_stats
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_geigel_single_talk_echo_only_allows_adaptation() {
        let config = GeigelConfig {
            sample_rate: 16000.0,
            history_len: 256,
            threshold: 0.50,
            hangover_ms: 20.0,
            min_ref_threshold: 1e-4,
            eps: 1e-6,
        };
        let mut geigel = GeigelDetector::new(config);

        // Echo path attenuation: loudspeaker is 0.8, echo arriving at mic is 0.2 (25% < 50% threshold)
        for _ in 0..100 {
            let stats = geigel.process_sample(0.2, 0.8);
            assert!(
                !stats.is_double_talk,
                "Single talk echo must not trigger double-talk"
            );
            assert_eq!(
                stats.step_scale, 1.0,
                "Filter adaptation must remain active"
            );
        }
    }

    #[test]
    fn test_geigel_double_talk_freezes_adaptation_instantly() {
        let config = GeigelConfig {
            sample_rate: 16000.0,
            history_len: 256,
            threshold: 0.50,
            hangover_ms: 20.0,
            min_ref_threshold: 1e-4,
            eps: 1e-6,
        };
        let mut geigel = GeigelDetector::new(config);

        // Warm up with echo
        for _ in 0..50 {
            geigel.process_sample(0.2, 0.8);
        }

        // Near-end soldier begins shouting: mic signal jumps to 0.7 while ref is 0.8 -> ratio 0.875 > 0.50
        let stats = geigel.process_sample(0.7, 0.8);
        assert!(
            stats.is_double_talk,
            "Double-talk must be instantly detected"
        );
        assert_eq!(
            stats.step_scale, 0.0,
            "Filter adaptation must be immediately frozen (step_scale = 0)"
        );
        assert!(stats.geigel_metric > 0.50);
    }

    #[test]
    fn test_geigel_hangover_persists_during_speech_valley() {
        let config = GeigelConfig {
            sample_rate: 16000.0,
            history_len: 256,
            threshold: 0.50,
            hangover_ms: 10.0, // 160 samples
            min_ref_threshold: 1e-4,
            eps: 1e-6,
        };
        let mut geigel = GeigelDetector::new(config);

        // Trigger double-talk
        let _ = geigel.process_sample(0.8, 0.8);
        assert!(geigel.stats().is_double_talk);

        // Next sample: mic drops to quiet echo (0.1), but hangover should maintain freeze
        let stats = geigel.process_sample(0.1, 0.8);
        assert!(
            stats.is_double_talk,
            "Hangover must sustain double-talk flag during momentary dip"
        );
        assert!(stats.hangover_active, "Hangover flag must be set");
        assert_eq!(stats.step_scale, 0.0);
    }
}
