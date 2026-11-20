//! Dynamic Psychoacoustic Split-Band De-Esser & Anti-Sibilance Engine.
//!
//! Developed for SIH 26052 Tactical Military Audio Systems.
//!
//! In high-gain combat intercom communications, high-frequency sibilant consonants
//! ("s", "sh", "ch", "z", "ts" in the 5.0 kHz - 8.0 kHz band) cause harsh acoustic fatigue,
//! ear pain, and consonant clipping splatter, especially when high-frequency hearing compensation
//! (audiogram boost) or boom mic resonance peaks are active.
//!
//! Traditional wideband de-essers duck the entire audio signal, causing noticeable volume
//! pumping and dulling vowel clarity.
//!
//! This module implements an ultra-fast split-band dynamic de-esser:
//! 1. 4th-Order Linkwitz-Riley (LR4) Crossover:
//!    - Decomposes the signal into a low/mid band (untouched fundamentals and formants)
//!      and a high sibilance band with zero phase cancellation at crossover.
//! 2. Sidechain Sibilance Ratio Detector:
//!    - Compares isolated sibilant band energy (5.5 kHz - 7.8 kHz) against broadband energy.
//!    - Dynamically detects sibilant phonemes while ignoring normal wideband speech and flat noise.
//! 3. Ultra-Fast Attack (< 0.8 ms) & Adaptive Release Envelope Follower:
//!    - Ramps down harsh consonant spikes instantly (< 0.5 ms), smoothing harsh consonants
//!      without softening consonant intelligibility.
//!    - Release smoothly adapts between fast (transient consonant release) and sustained sibilance.
//! 4. Split-Band Gain Modulation:
//!    - Gain reduction is applied *strictly* to the high sibilance band.
//!    - Low and mid speech fundamentals (100 Hz - 5000 Hz) remain 100% mathematically uncolored.
//! 5. Strictly ZERO heap allocations in the real-time processing loop.

/// Maximum block size supported in scratch buffers.
pub const DEESSER_MAX_BLOCK_SIZE: usize = 1024;

/// 2nd-order Biquad IIR filter section (Direct Form II Transposed).
#[derive(Debug, Clone, Copy, Default)]
struct Biquad {
    b0: f32,
    b1: f32,
    b2: f32,
    a1: f32,
    a2: f32,
    d1: f32,
    d2: f32,
}

impl Biquad {
    #[inline(always)]
    fn process(&mut self, x: f32) -> f32 {
        let y = self.b0 * x + self.d1;
        self.d1 = self.b1 * x - self.a1 * y + self.d2;
        self.d2 = self.b2 * x - self.a2 * y;
        y
    }

    fn reset(&mut self) {
        self.d1 = 0.0;
        self.d2 = 0.0;
    }

    /// 2nd-order Butterworth Low-Pass Filter.
    fn set_lowpass(&mut self, sample_rate: f32, cutoff_hz: f32) {
        let cutoff = cutoff_hz.clamp(20.0, sample_rate * 0.45);
        let w0 = 2.0 * std::f32::consts::PI * cutoff / sample_rate;
        let cos_w0 = w0.cos();
        let sin_w0 = w0.sin();
        let alpha = sin_w0 / (2.0 * std::f32::consts::FRAC_1_SQRT_2);

        let a0 = 1.0 + alpha;
        self.b0 = ((1.0 - cos_w0) / 2.0) / a0;
        self.b1 = (1.0 - cos_w0) / a0;
        self.b2 = ((1.0 - cos_w0) / 2.0) / a0;
        self.a1 = (-2.0 * cos_w0) / a0;
        self.a2 = (1.0 - alpha) / a0;
    }

    /// 2nd-order Butterworth High-Pass Filter.
    fn set_highpass(&mut self, sample_rate: f32, cutoff_hz: f32) {
        let cutoff = cutoff_hz.clamp(20.0, sample_rate * 0.45);
        let w0 = 2.0 * std::f32::consts::PI * cutoff / sample_rate;
        let cos_w0 = w0.cos();
        let sin_w0 = w0.sin();
        let alpha = sin_w0 / (2.0 * std::f32::consts::FRAC_1_SQRT_2);

        let a0 = 1.0 + alpha;
        self.b0 = ((1.0 + cos_w0) / 2.0) / a0;
        self.b1 = (-(1.0 + cos_w0)) / a0;
        self.b2 = ((1.0 + cos_w0) / 2.0) / a0;
        self.a1 = (-2.0 * cos_w0) / a0;
        self.a2 = (1.0 - alpha) / a0;
    }

    /// 2nd-order Bandpass Filter with constant 0 dB peak gain.
    fn set_bandpass(&mut self, sample_rate: f32, center_hz: f32, q: f32) {
        let center = center_hz.clamp(20.0, sample_rate * 0.46);
        let w0 = 2.0 * std::f32::consts::PI * center / sample_rate;
        let cos_w0 = w0.cos();
        let sin_w0 = w0.sin();
        let alpha = sin_w0 / (2.0 * q.max(0.1));

        let a0 = 1.0 + alpha;
        self.b0 = alpha / a0;
        self.b1 = 0.0;
        self.b2 = -alpha / a0;
        self.a1 = (-2.0 * cos_w0) / a0;
        self.a2 = (1.0 - alpha) / a0;
    }
}

/// 4th-order Linkwitz-Riley Crossover (cascaded dual 2nd-order Butterworth).
#[derive(Debug, Clone, Copy, Default)]
struct LinkwitzRiley4Crossover {
    lp1: Biquad,
    lp2: Biquad,
    hp1: Biquad,
    hp2: Biquad,
}

impl LinkwitzRiley4Crossover {
    fn new(sample_rate: f32, crossover_hz: f32) -> Self {
        let mut xover = Self::default();
        xover.configure(sample_rate, crossover_hz);
        xover
    }

    fn configure(&mut self, sample_rate: f32, crossover_hz: f32) {
        self.lp1.set_lowpass(sample_rate, crossover_hz);
        self.lp2.set_lowpass(sample_rate, crossover_hz);
        self.hp1.set_highpass(sample_rate, crossover_hz);
        self.hp2.set_highpass(sample_rate, crossover_hz);
    }

    fn reset(&mut self) {
        self.lp1.reset();
        self.lp2.reset();
        self.hp1.reset();
        self.hp2.reset();
    }

    #[inline(always)]
    fn split(&mut self, x: f32) -> (f32, f32) {
        let low = self.lp2.process(self.lp1.process(x));
        let high = self.hp2.process(self.hp1.process(x));
        (low, high)
    }
}

/// Configuration parameters for the Dynamic Split-Band De-Esser.
#[derive(Debug, Clone, Copy)]
pub struct DeEsserConfig {
    /// Audio sampling rate in Hz (default: 16000.0).
    pub sample_rate: f32,
    /// Crossover frequency in Hz separating low speech fundamentals from sibilance (default: 5200.0 Hz).
    pub crossover_freq_hz: f32,
    /// Center frequency of sidechain sibilance bandpass filter (default: 6500.0 Hz).
    pub sibilant_center_hz: f32,
    /// Q factor of sidechain sibilance bandpass filter (default: 2.2).
    pub sibilant_q: f32,
    /// Sibilance-to-broadband energy ratio threshold in dB (default: 3.5 dB).
    pub ratio_threshold_db: f32,
    /// Minimum absolute sibilant band power threshold in dBFS to trigger de-essing (default: -42.0 dBFS).
    pub energy_threshold_dbfs: f32,
    /// Attack time in milliseconds (< 0.8 ms for ultra-fast peak suppression; default: 0.5 ms).
    pub attack_ms: f32,
    /// Minimum release time in milliseconds for transient sibilants (default: 12.0 ms).
    pub release_min_ms: f32,
    /// Maximum release time in milliseconds for sustained sibilants (default: 40.0 ms).
    pub release_max_ms: f32,
    /// Maximum allowed attenuation in dB (default: 18.0 dB).
    pub max_reduction_db: f32,
    /// Compression slope ratio above threshold (default: 3.0).
    pub compression_ratio: f32,
    /// Whether de-esser is active.
    pub enabled: bool,
}

impl Default for DeEsserConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000.0,
            crossover_freq_hz: 5200.0,
            sibilant_center_hz: 6500.0,
            sibilant_q: 2.2,
            ratio_threshold_db: 3.5,
            energy_threshold_dbfs: -42.0,
            attack_ms: 0.5,
            release_min_ms: 12.0,
            release_max_ms: 40.0,
            max_reduction_db: 18.0,
            compression_ratio: 3.0,
            enabled: true,
        }
    }
}

/// Telemetry metrics emitted by the De-Esser.
#[derive(Debug, Clone, Copy, Default)]
pub struct DeEsserTelemetry {
    /// Whether a harsh sibilance event was detected in the current block.
    pub sibilance_detected: bool,
    /// Current sibilance-to-broadband energy ratio in dB.
    pub sibilance_ratio_db: f32,
    /// Current high-band gain reduction applied in dB (0.0 to -18.0 dB).
    pub gain_reduction_db: f32,
    /// Sibilant band energy in dBFS.
    pub sibilant_energy_dbfs: f32,
    /// Broadband voice energy in dBFS.
    pub broadband_energy_dbfs: f32,
}

/// Dynamic Psychoacoustic Split-Band De-Esser Engine.
///
/// Guaranteed zero heap allocations in real-time execution.
pub struct DeEsser {
    config: DeEsserConfig,
    crossover: LinkwitzRiley4Crossover,
    sidechain_bpf: Biquad,

    // Envelope and power state
    pwr_broadband: f32,
    pwr_sibilant: f32,
    gain_reduction_db: f32,
    sibilance_persisting: f32,

    // Time constants
    alpha_env: f32,
    alpha_attack: f32,
    alpha_rel_min: f32,
    alpha_rel_max: f32,

    // Latest telemetry
    telemetry: DeEsserTelemetry,
}

impl DeEsser {
    /// Creates a new Dynamic Split-Band De-Esser with the given configuration.
    pub fn new(config: DeEsserConfig) -> Self {
        let fs = config.sample_rate.max(8000.0);
        let crossover = LinkwitzRiley4Crossover::new(fs, config.crossover_freq_hz);

        let mut sidechain_bpf = Biquad::default();
        sidechain_bpf.set_bandpass(fs, config.sibilant_center_hz, config.sibilant_q);

        // Calculate smoothing coefficients
        let env_tc_ms = 4.0f32;
        let alpha_env = (-1.0 / (env_tc_ms * 0.001 * fs)).exp();
        let alpha_attack = (-1.0 / (config.attack_ms.max(0.1) * 0.001 * fs)).exp();
        let alpha_rel_min = (-1.0 / (config.release_min_ms.max(1.0) * 0.001 * fs)).exp();
        let alpha_rel_max = (-1.0 / (config.release_max_ms.max(5.0) * 0.001 * fs)).exp();

        Self {
            config,
            crossover,
            sidechain_bpf,
            pwr_broadband: 1e-8,
            pwr_sibilant: 1e-8,
            gain_reduction_db: 0.0,
            sibilance_persisting: 0.0,
            alpha_env,
            alpha_attack,
            alpha_rel_min,
            alpha_rel_max,
            telemetry: DeEsserTelemetry::default(),
        }
    }

    /// Resets all internal filter states and envelope trackers.
    pub fn reset(&mut self) {
        self.crossover.reset();
        self.sidechain_bpf.reset();
        self.pwr_broadband = 1e-8;
        self.pwr_sibilant = 1e-8;
        self.gain_reduction_db = 0.0;
        self.sibilance_persisting = 0.0;
        self.telemetry = DeEsserTelemetry::default();
    }

    /// Updates configuration and recalculates filter parameters.
    pub fn update_config(&mut self, config: DeEsserConfig) {
        let fs = config.sample_rate.max(8000.0);
        self.crossover.configure(fs, config.crossover_freq_hz);
        self.sidechain_bpf
            .set_bandpass(fs, config.sibilant_center_hz, config.sibilant_q);

        let env_tc_ms = 4.0f32;
        self.alpha_env = (-1.0 / (env_tc_ms * 0.001 * fs)).exp();
        self.alpha_attack = (-1.0 / (config.attack_ms.max(0.1) * 0.001 * fs)).exp();
        self.alpha_rel_min = (-1.0 / (config.release_min_ms.max(1.0) * 0.001 * fs)).exp();
        self.alpha_rel_max = (-1.0 / (config.release_max_ms.max(5.0) * 0.001 * fs)).exp();
        self.config = config;
    }

    /// Processes a single audio sample and returns the de-essed sample.
    #[inline]
    pub fn process_sample(&mut self, x: f32) -> f32 {
        if !self.config.enabled {
            return x;
        }

        // 1. Split-band crossover decomposition
        let (low, high) = self.crossover.split(x);

        // 2. Sidechain bandpass extraction on sibilant high frequencies
        let sidechain = self.sidechain_bpf.process(high);

        // 3. Power tracking with leaky integration
        // Comparing sibilant power against low/mid speech fundamental core (below crossover)
        let low_sq = low * low;
        let sc_sq = sidechain * sidechain;
        self.pwr_broadband = self.alpha_env * self.pwr_broadband + (1.0 - self.alpha_env) * low_sq;
        self.pwr_sibilant = self.alpha_env * self.pwr_sibilant + (1.0 - self.alpha_env) * sc_sq;

        // 4. Sibilance ratio detector
        let ratio = (self.pwr_sibilant + 1e-12) / (self.pwr_broadband + 1e-12);
        let ratio_db = 10.0 * ratio.max(1e-6).log10();
        let sibilant_dbfs = 10.0 * self.pwr_sibilant.max(1e-12).log10();
        let broadband_dbfs = 10.0 * self.pwr_broadband.max(1e-12).log10();

        let is_sibilant = ratio_db > self.config.ratio_threshold_db
            && sibilant_dbfs > self.config.energy_threshold_dbfs;

        // 5. Target gain calculation
        let target_reduction_db = if is_sibilant {
            self.sibilance_persisting = (self.sibilance_persisting + 0.05).min(1.0);
            let excess_db = ratio_db - self.config.ratio_threshold_db;
            let comp_db = excess_db * (self.config.compression_ratio - 1.0);
            -comp_db.clamp(0.0, self.config.max_reduction_db)
        } else {
            self.sibilance_persisting = (self.sibilance_persisting - 0.01).max(0.0);
            0.0
        };

        // 6. Ultra-fast attack (< 0.8 ms) & adaptive release smoothing
        if target_reduction_db < self.gain_reduction_db {
            // Attack phase
            self.gain_reduction_db = self.alpha_attack * self.gain_reduction_db
                + (1.0 - self.alpha_attack) * target_reduction_db;
        } else {
            // Adaptive release phase
            let alpha_rel = self.alpha_rel_min * (1.0 - self.sibilance_persisting)
                + self.alpha_rel_max * self.sibilance_persisting;
            self.gain_reduction_db =
                alpha_rel * self.gain_reduction_db + (1.0 - alpha_rel) * target_reduction_db;
        }

        // 7. Modulate strictly high sibilance band
        let linear_gain = 10.0f32.powf(self.gain_reduction_db / 20.0);
        let out = low + high * linear_gain;

        self.telemetry = DeEsserTelemetry {
            sibilance_detected: is_sibilant || self.gain_reduction_db < -0.5,
            sibilance_ratio_db: ratio_db,
            gain_reduction_db: self.gain_reduction_db,
            sibilant_energy_dbfs: sibilant_dbfs,
            broadband_energy_dbfs: broadband_dbfs,
        };

        out
    }

    /// Processes an audio frame in-place with zero heap allocations.
    pub fn process_block(&mut self, block: &mut [f32]) {
        if !self.config.enabled || block.is_empty() {
            return;
        }

        let n = block.len().min(DEESSER_MAX_BLOCK_SIZE);
        for i in 0..n {
            block[i] = self.process_sample(block[i]);
        }
    }

    /// Returns the current telemetry metrics.
    pub fn telemetry(&self) -> DeEsserTelemetry {
        self.telemetry
    }

    /// Sets whether de-esser is active.
    pub fn set_enabled(&mut self, enabled: bool) {
        self.config.enabled = enabled;
        if !enabled {
            self.gain_reduction_db = 0.0;
            self.telemetry.gain_reduction_db = 0.0;
            self.telemetry.sibilance_detected = false;
        }
    }

    /// Returns whether the de-esser is currently enabled.
    pub fn is_enabled(&self) -> bool {
        self.config.enabled
    }

    /// Returns the current high-band gain reduction in dB.
    pub fn gain_reduction_db(&self) -> f32 {
        self.gain_reduction_db
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_deesser_initialization_and_transparency_on_low_freq() {
        let config = DeEsserConfig {
            sample_rate: 16000.0,
            ..Default::default()
        };
        let mut deesser = DeEsser::new(config);

        // 500 Hz tone (low speech fundamental) should not trigger sibilance or gain reduction
        let mut audio = [0.0f32; 256];
        for (i, sample) in audio.iter_mut().enumerate() {
            let t = i as f32 / 16000.0;
            *sample = 0.5 * (2.0 * std::f32::consts::PI * 500.0 * t).sin();
        }

        deesser.process_block(&mut audio);
        let telem = deesser.telemetry();

        assert!(
            !telem.sibilance_detected,
            "500 Hz speech fundamental should not trigger sibilance"
        );
        assert!(
            telem.gain_reduction_db > -0.5,
            "Gain reduction should be negligible on 500 Hz tone"
        );
    }

    #[test]
    fn test_deesser_triggers_on_harsh_sibilant_tone() {
        let config = DeEsserConfig {
            sample_rate: 16000.0,
            ratio_threshold_db: 2.0,
            energy_threshold_dbfs: -45.0,
            ..Default::default()
        };
        let mut deesser = DeEsser::new(config);

        // 6500 Hz tone (sibilant consonant range "ssss")
        let mut audio = [0.0f32; 512];
        for (i, sample) in audio.iter_mut().enumerate() {
            let t = i as f32 / 16000.0;
            *sample = 0.6 * (2.0 * std::f32::consts::PI * 6500.0 * t).sin();
        }

        // Process multiple blocks to let energy trackers converge
        for _ in 0..4 {
            let mut blk = audio;
            deesser.process_block(&mut blk);
        }

        let telem = deesser.telemetry();
        assert!(
            telem.sibilance_detected,
            "6500 Hz tone must trigger sibilance detection"
        );
        assert!(
            telem.gain_reduction_db < -3.0,
            "Gain reduction must be applied to harsh 6500 Hz spike"
        );
    }

    #[test]
    fn test_deesser_fast_attack_response() {
        let config = DeEsserConfig {
            sample_rate: 16000.0,
            attack_ms: 0.5,
            ratio_threshold_db: 1.0,
            ..Default::default()
        };
        let mut deesser = DeEsser::new(config);

        // Pre-charge with quiet voice
        for i in 0..100 {
            let t = i as f32 / 16000.0;
            let sample = 0.05 * (2.0 * std::f32::consts::PI * 400.0 * t).sin();
            let _ = deesser.process_sample(sample);
        }

        // Inject high-amplitude 6.5 kHz sibilant burst
        let mut triggered = false;
        for i in 0..128 {
            let t = i as f32 / 16000.0;
            let sample = 0.8 * (2.0 * std::f32::consts::PI * 6500.0 * t).sin();
            let _ = deesser.process_sample(sample);
            if deesser.gain_reduction_db() < -1.5 {
                triggered = true;
                break;
            }
        }

        assert!(triggered, "De-esser attack must engage on sibilant burst");
    }

    #[test]
    fn test_deesser_biquad_linkwitz_riley_reconstruction() {
        // Test that LR4 crossover has flat steady-state magnitude response
        let mut xover = LinkwitzRiley4Crossover::new(16000.0, 5000.0);
        let mut sum_power = 0.0f32;
        let mut in_power = 0.0f32;

        for i in 0..600 {
            let t = i as f32 / 16000.0;
            let x = (2.0 * std::f32::consts::PI * 1000.0 * t).sin();
            let (low, high) = xover.split(x);
            let sum = low + high;
            if i >= 150 {
                sum_power += sum * sum;
                in_power += x * x;
            }
        }
        let gain_db = 10.0 * (sum_power / in_power).log10();
        assert!(
            gain_db.abs() < 0.25,
            "LR4 crossover magnitude should be flat within 0.25 dB"
        );
    }
}
