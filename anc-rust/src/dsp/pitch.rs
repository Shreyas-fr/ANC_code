//! Causal Pitch-Synchronous Harmonic Comb Filter & Pitch Tracker.
//!
//! Provides real-time causal pitch tracking using normalized cross-correlation (NCCF)
//! with parabolic sub-sample refinement, coupled to a pitch-synchronous harmonic comb filter.
//!
//! In voiced speech segments, vowel harmonics are passed with 0 dB loss while stationary
//! inter-harmonic mechanical interference (aircraft whine, rotor blade tones, gearbox harmonics)
//! is attenuated by 6 to 12 dB. In unvoiced segments and pauses, the filter smoothly transitions
//! to transparent unity passthrough to preserve fricatives and consonants.
//!
//! Zero heap allocations in the real-time processing loop.

/// Configuration parameters for pitch tracking and harmonic comb filtering.
#[derive(Debug, Clone)]
pub struct PitchTrackerConfig {
    pub sample_rate: f32,
    pub min_f0: f32,
    pub max_f0: f32,
    pub voicing_threshold: f32,
    pub max_comb_depth: f32,
    pub smoothing_factor: f32,
}

impl Default for PitchTrackerConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000.0,
            min_f0: 70.0,
            max_f0: 400.0,
            voicing_threshold: 0.42,
            max_comb_depth: 0.38, // Yields ~10 dB inter-harmonic attenuation
            smoothing_factor: 0.25,
        }
    }
}

/// Real-time Causal Pitch Tracker using Normalized Cross-Correlation (NCCF).
#[derive(Debug, Clone)]
pub struct PitchTracker {
    config: PitchTrackerConfig,
    min_lag: usize,
    max_lag: usize,
    history: [f32; 1024],
    write_pos: usize,
    tracked_lag: f32,
    tracked_f0: f32,
    voicing_strength: f32,
    is_voiced: bool,
}

impl PitchTracker {
    /// Creates a new `PitchTracker`.
    pub fn new(config: PitchTrackerConfig) -> Self {
        let min_lag = (config.sample_rate / config.max_f0).floor() as usize; // e.g. 40 @ 16k
        let max_lag = (config.sample_rate / config.min_f0).ceil() as usize;  // e.g. 228 @ 16k
        let default_lag = (config.sample_rate / 150.0).clamp(min_lag as f32, max_lag as f32);

        Self {
            config,
            min_lag,
            max_lag,
            history: [0.0; 1024],
            write_pos: 0,
            tracked_lag: default_lag,
            tracked_f0: 150.0,
            voicing_strength: 0.0,
            is_voiced: false,
        }
    }

    /// Resets pitch tracking history.
    pub fn reset(&mut self) {
        self.history = [0.0; 1024];
        self.write_pos = 0;
        self.tracked_lag = (self.config.sample_rate / 150.0).clamp(self.min_lag as f32, self.max_lag as f32);
        self.tracked_f0 = 150.0;
        self.voicing_strength = 0.0;
        self.is_voiced = false;
    }

    /// Pushes a block of samples into the history buffer and updates pitch estimate.
    pub fn process_block(&mut self, input: &[f32]) {
        let hist_len = self.history.len();
        for &s in input {
            self.history[self.write_pos] = s;
            self.write_pos = (self.write_pos + 1) % hist_len;
        }

        self.estimate_pitch();
    }

    /// Estimates pitch using NCCF with parabolic sub-sample refinement.
    fn estimate_pitch(&mut self) {
        let hist_len = self.history.len();
        let window_len = 240; // 15 ms correlation window

        // Calculate zero-lag energy over current window
        let mut e0 = 0.0f32;
        for i in 0..window_len {
            let idx = (self.write_pos + hist_len - 1 - i) % hist_len;
            let s = self.history[idx];
            e0 += s * s;
        }

        if e0 < 1e-5 {
            // Signal energy too low for reliable pitch
            self.voicing_strength = 0.0;
            self.is_voiced = false;
            return;
        }

        let mut best_corr = -1.0f32;
        let mut best_lag = self.min_lag;

        // Search lags
        let mut corr_vals = [0.0f32; 256];

        for lag in self.min_lag..=self.max_lag {
            let mut num = 0.0f32;
            let mut e_lag = 0.0f32;

            for i in 0..window_len {
                let idx0 = (self.write_pos + hist_len - 1 - i) % hist_len;
                let idx_lag = (self.write_pos + hist_len - 1 - i - lag) % hist_len;
                let s0 = self.history[idx0];
                let s_lag = self.history[idx_lag];
                num += s0 * s_lag;
                e_lag += s_lag * s_lag;
            }

            let denom = (e0 * e_lag).sqrt() + 1e-8;
            let nccf = (num / denom).clamp(-1.0, 1.0);
            corr_vals[lag] = nccf;

            if nccf > best_corr {
                best_corr = nccf;
                best_lag = lag;
            }
        }
        // Pitch-doubling / sub-harmonic avoidance:
        // Find the smallest lag (highest fundamental F0) that achieves >= 85% of peak correlation.
        if best_corr >= self.config.voicing_threshold {
            let threshold = 0.85 * best_corr;
            for lag in self.min_lag..=self.max_lag {
                if lag > self.min_lag && lag < self.max_lag {
                    let c = corr_vals[lag];
                    if c >= threshold && c >= corr_vals[lag - 1] && c >= corr_vals[lag + 1] {
                        best_lag = lag;
                        best_corr = c;
                        break;
                    }
                }
            }
        }

        // Parabolic sub-sample refinement around best_lag
        let refined_lag = if best_lag > self.min_lag && best_lag < self.max_lag {
            let prev_corr = corr_vals[best_lag - 1];
            let next_corr = corr_vals[best_lag + 1];
            let denom = 2.0 * (2.0 * best_corr - prev_corr - next_corr);
            let delta = if denom.abs() > 1e-6 {
                (next_corr - prev_corr) / denom
            } else {
                0.0
            };
            best_lag as f32 + delta.clamp(-0.5, 0.5)
        } else {
            best_lag as f32
        };

        // Smooth voicing strength and lag
        let alpha = self.config.smoothing_factor;
        self.voicing_strength = (1.0 - alpha) * self.voicing_strength + alpha * best_corr.max(0.0);
        self.is_voiced = self.voicing_strength >= self.config.voicing_threshold;

        if self.is_voiced {
            self.tracked_lag = (1.0 - alpha) * self.tracked_lag + alpha * refined_lag;
            self.tracked_f0 = self.config.sample_rate / self.tracked_lag;
        }
    }

    /// Current fundamental frequency F0 in Hz.
    pub fn tracked_f0(&self) -> f32 {
        self.tracked_f0
    }

    /// Current pitch lag in fractional samples.
    pub fn tracked_lag(&self) -> f32 {
        self.tracked_lag
    }

    /// Whether current speech frame is voiced.
    pub fn is_voiced(&self) -> bool {
        self.is_voiced
    }

    /// Voicing confidence metric in [0.0, 1.0].
    pub fn voicing_strength(&self) -> f32 {
        self.voicing_strength
    }
}

/// Pitch-Synchronous Harmonic Comb Filter.
///
/// Implements a fractional delay comb filter:
/// y[n] = (1 - alpha) * x[n] + alpha * x[n - tau]
///
/// When tau matches speech fundamental period, speech harmonics are constructively summed (0 dB loss),
/// while frequencies midway between harmonics suffer maximum notch attenuation.
#[derive(Debug, Clone)]
pub struct HarmonicCombFilter {
    delay_buf: [f32; 1024],
    write_idx: usize,
    sample_rate: f32,
    max_depth: f32,
    aggressive: bool,
    enabled: bool,
}

impl HarmonicCombFilter {
    /// Creates a new `HarmonicCombFilter`.
    pub fn new(sample_rate: f32, max_depth: f32) -> Self {
        Self {
            delay_buf: [0.0; 1024],
            write_idx: 0,
            sample_rate,
            max_depth: max_depth.clamp(0.0, 0.49),
            aggressive: false,
            enabled: true,
        }
    }

    /// Resets internal delay line.
    pub fn reset(&mut self) {
        self.delay_buf = [0.0; 1024];
        self.write_idx = 0;
    }

    /// Enables or disables the comb filter.
    pub fn set_enabled(&mut self, enabled: bool) {
        self.enabled = enabled;
    }

    /// Returns whether the comb filter is enabled.
    pub fn is_enabled(&self) -> bool {
        self.enabled
    }

    /// Enables or disables aggressive notch depth mode (-14 to -16.5 dB attenuation in inter-harmonic valleys).
    pub fn set_aggressive(&mut self, aggressive: bool) {
        self.aggressive = aggressive;
    }

    /// Returns whether aggressive notch mode is enabled.
    pub fn is_aggressive(&self) -> bool {
        self.aggressive
    }

    /// Sample rate in Hz.
    pub fn sample_rate(&self) -> f32 {
        self.sample_rate
    }

    /// Filters audio block in-place based on pitch lag and voicing strength.
    ///
    /// Zero heap allocations.
    pub fn process_block(
        &mut self,
        input: &[f32],
        output: &mut [f32],
        pitch_lag: f32,
        voicing_strength: f32,
    ) {
        assert_eq!(input.len(), output.len());
        let buf_len = self.delay_buf.len();

        if !self.enabled || voicing_strength < 0.35 {
            // Bypass mode: transparent passthrough for unvoiced speech / pauses
            output.copy_from_slice(input);
            for &s in input {
                self.delay_buf[self.write_idx] = s;
                self.write_idx = (self.write_idx + 1) % buf_len;
            }
            return;
        }

        // Dynamically scale comb depth according to voicing confidence:
        // When pitch confidence > 0.70 (clear voiced vowel harmonics), apply deep notch
        // attenuation (up to -12 to -16.5 dB) strictly in inter-harmonic valleys.
        // Harmonic peaks pass with 0 dB distortionless gain.
        let alpha = if voicing_strength > 0.70 {
            let conf_factor = ((voicing_strength - 0.70) / 0.30).clamp(0.0, 1.0);
            let deep_max = if self.aggressive { 0.435 } else { 0.415 };
            self.max_depth + conf_factor * (deep_max - self.max_depth)
        } else {
            let depth_factor = ((voicing_strength - 0.35) / (0.70 - 0.35)).clamp(0.0, 1.0);
            self.max_depth * depth_factor
        };

        let lag_int = pitch_lag.floor() as usize;
        let frac = pitch_lag - lag_int as f32;

        for (in_samp, out_samp) in input.iter().zip(output.iter_mut()) {
            let x = *in_samp;

            // Store in delay line
            self.delay_buf[self.write_idx] = x;

            // Interpolate delayed sample with fractional lag
            let idx0 = (self.write_idx + buf_len - lag_int) % buf_len;
            let idx1 = (self.write_idx + buf_len - lag_int - 1) % buf_len;

            let s0 = self.delay_buf[idx0];
            let s1 = self.delay_buf[idx1];
            let x_delayed = (1.0 - frac) * s0 + frac * s1;

            // Causal comb filter equation: preserves harmonics, notches inter-harmonic noise
            let y = (1.0 - alpha) * x + alpha * x_delayed;
            *out_samp = y;

            self.write_idx = (self.write_idx + 1) % buf_len;
        }
    }
}

/// Integrated Pitch-Synchronous Harmonic Comb Engine.
/// Combines the pitch tracker and comb filter into a unified, zero-allocation component.
#[derive(Debug, Clone)]
pub struct PitchHarmonicCombEngine {
    tracker: PitchTracker,
    filter: HarmonicCombFilter,
    enabled: bool,
}

impl PitchHarmonicCombEngine {
    /// Creates a new `PitchHarmonicCombEngine`.
    pub fn new(sample_rate: f32) -> Self {
        let config = PitchTrackerConfig {
            sample_rate,
            ..Default::default()
        };
        let filter = HarmonicCombFilter::new(sample_rate, config.max_comb_depth);
        let tracker = PitchTracker::new(config);

        Self {
            tracker,
            filter,
            enabled: true,
        }
    }

    /// Resets internal state.
    pub fn reset(&mut self) {
        self.tracker.reset();
        self.filter.reset();
    }

    /// Sets whether comb filtering is active.
    pub fn set_enabled(&mut self, enabled: bool) {
        self.enabled = enabled;
        self.filter.set_enabled(enabled);
    }

    /// Returns whether the engine is enabled.
    pub fn is_enabled(&self) -> bool {
        self.enabled
    }

    /// Sets whether aggressive notch depth mode is enabled.
    pub fn set_aggressive(&mut self, aggressive: bool) {
        self.filter.set_aggressive(aggressive);
    }

    /// Returns whether aggressive notch mode is enabled.
    pub fn is_aggressive(&self) -> bool {
        self.filter.is_aggressive()
    }

    /// Returns the currently tracked fundamental frequency F0 in Hz.
    pub fn tracked_f0(&self) -> f32 {
        self.tracker.tracked_f0()
    }

    /// Returns whether the current frame is voiced.
    pub fn is_voiced(&self) -> bool {
        self.tracker.is_voiced()
    }

    /// Returns the voicing confidence in [0.0, 1.0].
    pub fn voicing_strength(&self) -> f32 {
        self.tracker.voicing_strength()
    }

    /// Filters audio block in-place.
    pub fn process_block(&mut self, input: &[f32], output: &mut [f32]) {
        self.tracker.process_block(input);
        if self.enabled {
            let lag = self.tracker.tracked_lag();
            let voicing = self.tracker.voicing_strength();
            self.filter.process_block(input, output, lag, voicing);
        } else {
            output.copy_from_slice(input);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::f32::consts::PI;

    #[test]
    fn test_pitch_tracker_synthetic_vowel_f0() {
        let sample_rate = 16000.0;
        let mut tracker = PitchTracker::new(PitchTrackerConfig {
            sample_rate,
            ..Default::default()
        });

        // Generate synthetic voiced vowel with F0 = 160 Hz + harmonics at 320 Hz, 480 Hz
        let n = 2048;
        let mut signal = vec![0.0f32; n];
        for i in 0..n {
            let t = i as f32 / sample_rate;
            signal[i] = 0.6 * (2.0 * PI * 160.0 * t).sin()
                + 0.3 * (2.0 * PI * 320.0 * t).sin()
                + 0.15 * (2.0 * PI * 480.0 * t).sin();
        }

        // Process in 256-sample hops
        for chunk in signal.chunks(256) {
            tracker.process_block(chunk);
        }

        assert!(tracker.is_voiced(), "Voiced vowel was not detected as voiced");
        assert!(
            tracker.voicing_strength() > 0.70,
            "Voicing strength too low: {}",
            tracker.voicing_strength()
        );
        let f0 = tracker.tracked_f0();
        assert!(
            (f0 - 160.0).abs() < 3.0,
            "Tracked F0 deviates from 160 Hz: {}",
            f0
        );
    }

    #[test]
    fn test_harmonic_comb_filter_preserves_harmonics_and_attenuates_inter_harmonic_noise() {
        let sample_rate = 16000.0;
        let mut filter = HarmonicCombFilter::new(sample_rate, 0.40);

        let lag = sample_rate / 150.0; // F0 = 150 Hz -> lag = 106.667 samples
        let n = 1024;

        // Test 1: Harmonic speech tone at 150 Hz
        let mut harmonic_in = vec![0.0f32; n];
        let mut harmonic_out = vec![0.0f32; n];
        for i in 0..n {
            let t = i as f32 / sample_rate;
            harmonic_in[i] = (2.0 * PI * 150.0 * t).sin();
        }

        filter.process_block(&harmonic_in, &mut harmonic_out, lag, 0.95);

        // Discard first lag samples for delay-line warmup
        let pwr_in_harm: f32 = harmonic_in[200..].iter().map(|s| s * s).sum();
        let pwr_out_harm: f32 = harmonic_out[200..].iter().map(|s| s * s).sum();
        let harm_loss_db = 10.0 * (pwr_out_harm / pwr_in_harm).log10();

        // Harmonics should be preserved with almost 0 dB loss (< 0.2 dB)
        assert!(
            harm_loss_db.abs() < 0.25,
            "Harmonic tone attenuated too much: {:.2} dB",
            harm_loss_db
        );

        // Test 2: Inter-harmonic noise tone at 225 Hz (midway between 150 Hz and 300 Hz)
        let mut noise_in = vec![0.0f32; n];
        let mut noise_out = vec![0.0f32; n];
        for i in 0..n {
            let t = i as f32 / sample_rate;
            noise_in[i] = (2.0 * PI * 225.0 * t).sin();
        }

        filter.reset();
        filter.process_block(&noise_in, &mut noise_out, lag, 0.95);

        let pwr_in_noise: f32 = noise_in[200..].iter().map(|s| s * s).sum();
        let pwr_out_noise: f32 = noise_out[200..].iter().map(|s| s * s).sum();
        let noise_atten_db = 10.0 * (pwr_out_noise / pwr_in_noise).log10();

        // Inter-harmonic noise tone must be attenuated by >= 6.0 dB
        assert!(
            noise_atten_db <= -6.0,
            "Inter-harmonic noise not attenuated sufficiently: {:.2} dB",
            noise_atten_db
        );
    }

    #[test]
    fn test_unvoiced_passthrough_transparency() {
        let sample_rate = 16000.0;
        let mut engine = PitchHarmonicCombEngine::new(sample_rate);

        // White noise simulating unvoiced fricative 's'
        let n = 256;
        let mut unvoiced = vec![0.0f32; n];
        for i in 0..n {
            unvoiced[i] = ((i as f32 * 17.0).sin() * 0.2).clamp(-1.0, 1.0);
        }

        let mut output = vec![0.0f32; n];
        engine.process_block(&unvoiced, &mut output);

        // Since unvoiced, comb filter should be transparent (output ~= input)
        let diff: f32 = unvoiced.iter().zip(output.iter()).map(|(a, b)| (a - b).abs()).sum();
        assert!(
            diff < 0.05,
            "Unvoiced signal was colored by comb filter: diff={}",
            diff
        );
    }

    #[test]
    fn test_harmonic_comb_deep_notch_high_confidence() {
        let sample_rate = 16000.0;
        let mut filter = HarmonicCombFilter::new(sample_rate, 0.38);

        let lag = sample_rate / 150.0; // F0 = 150 Hz
        let n = 1024;

        // Harmonic speech tone at 150 Hz
        let mut harmonic_in = vec![0.0f32; n];
        let mut harmonic_out = vec![0.0f32; n];
        for i in 0..n {
            let t = i as f32 / sample_rate;
            harmonic_in[i] = (2.0 * PI * 150.0 * t).sin();
        }

        // Test with high voicing confidence (0.90)
        filter.process_block(&harmonic_in, &mut harmonic_out, lag, 0.90);
        let pwr_in_harm: f32 = harmonic_in[200..].iter().map(|s| s * s).sum();
        let pwr_out_harm: f32 = harmonic_out[200..].iter().map(|s| s * s).sum();
        let harm_loss_db = 10.0 * (pwr_out_harm / pwr_in_harm).log10();
        assert!(
            harm_loss_db.abs() < 0.25,
            "Harmonic was distorted: {:.2} dB",
            harm_loss_db
        );

        // Inter-harmonic valley noise tone at 225 Hz
        let mut noise_in = vec![0.0f32; n];
        let mut noise_out = vec![0.0f32; n];
        for i in 0..n {
            let t = i as f32 / sample_rate;
            noise_in[i] = (2.0 * PI * 225.0 * t).sin();
        }

        filter.reset();
        filter.process_block(&noise_in, &mut noise_out, lag, 0.90);
        let pwr_in_noise: f32 = noise_in[200..].iter().map(|s| s * s).sum();
        let pwr_out_noise: f32 = noise_out[200..].iter().map(|s| s * s).sum();
        let noise_atten_db = 10.0 * (pwr_out_noise / pwr_in_noise).log10();

        // High confidence (>0.70) must notch inter-harmonic noise by > 12.0 dB
        assert!(
            noise_atten_db <= -12.0,
            "High-confidence inter-harmonic notch should be <= -12 dB, got: {:.2} dB",
            noise_atten_db
        );
    }

    #[test]
    fn test_harmonic_comb_aggressive_mode() {
        let sample_rate = 16000.0;
        let mut filter = HarmonicCombFilter::new(sample_rate, 0.38);
        filter.set_aggressive(true);
        assert!(filter.is_aggressive());

        let lag = sample_rate / 150.0;
        let n = 1024;

        let mut noise_in = vec![0.0f32; n];
        let mut noise_out = vec![0.0f32; n];
        for i in 0..n {
            let t = i as f32 / sample_rate;
            noise_in[i] = (2.0 * PI * 225.0 * t).sin();
        }

        filter.process_block(&noise_in, &mut noise_out, lag, 0.95);
        let pwr_in_noise: f32 = noise_in[200..].iter().map(|s| s * s).sum();
        let pwr_out_noise: f32 = noise_out[200..].iter().map(|s| s * s).sum();
        let noise_atten_db = 10.0 * (pwr_out_noise / pwr_in_noise).log10();

        // Aggressive mode achieves up to -14 to -16 dB notch
        assert!(
            noise_atten_db <= -14.0,
            "Aggressive inter-harmonic notch should be <= -14 dB, got: {:.2} dB",
            noise_atten_db
        );
    }
}
