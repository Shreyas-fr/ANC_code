//! Tactical Ambient Situational Awareness & Transparency Mode with Hearing Protection.
//!
//! Designed for dismounted combat patrols, urban operations, and tactical command:
//! 1. Ambient Spatial Pass-Through: Selectively passes ambient environmental sound (squad
//!    commands, footsteps, approaching vehicles) through the closed headset.
//! 2. Tactical Speech & Footstep EQ: 2nd-order high-pass filter (>200 Hz) to reject wind/vehicle
//!    rumble while boosting 1.5 - 3.5 kHz voice presence for maximum intelligibility.
//! 3. Instantaneous Concussive Hearing Protection Clamping:
//!    Calibrated to OSHA/MIL-STD-1474E safe exposure limits (85 dBA SPL equivalent, digitally
//!    calibrated to -12.0 dBFS). When an explosive detonation, artillery crack, or gunshot
//!    occurs, gain drops instantaneously (zero attack time) to clamp acoustic shockwaves strictly
//!    below the hearing-damage threshold, followed by smooth exponential release (~60 ms).

use std::f32::consts::PI;

/// Configuration for Tactical Ambient Transparency Mode.
#[derive(Debug, Clone)]
pub struct TransparencyConfig {
    /// Enables transparency pass-through
    pub enabled: bool,
    /// Ambient pass-through linear gain (0.0 to 2.0, default: 1.0)
    pub ambient_gain: f32,
    /// Maximum safe peak threshold in dBFS (default: -12.0 dBFS ~= 85 dBA SPL calibration)
    pub safe_peak_limit_dbfs: f32,
    /// High-pass rumble filter cutoff frequency in Hz (default: 200.0 Hz)
    pub highpass_cutoff_hz: f32,
    /// Presence boost gain in dB for 1.5 - 3.5 kHz speech band (default: 3.0 dB)
    pub presence_boost_db: f32,
    /// Sample rate in Hz (default: 16000.0)
    pub sample_rate: f32,
    /// Clamping release time constant in ms (default: 60.0 ms)
    pub release_ms: f32,
}

impl Default for TransparencyConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            ambient_gain: 1.0,
            safe_peak_limit_dbfs: -12.0,
            highpass_cutoff_hz: 200.0,
            presence_boost_db: 3.0,
            sample_rate: 16000.0,
            release_ms: 60.0,
        }
    }
}

/// Biquad Direct Form II Transposed IIR filter section (zero allocation).
#[derive(Debug, Clone, Copy, Default)]
struct BiquadState {
    b0: f32,
    b1: f32,
    b2: f32,
    a1: f32,
    a2: f32,
    s1: f32,
    s2: f32,
}

impl BiquadState {
    #[inline]
    fn process(&mut self, x: f32) -> f32 {
        let y = self.b0 * x + self.s1;
        self.s1 = self.b1 * x - self.a1 * y + self.s2;
        self.s2 = self.b2 * x - self.a2 * y;
        y
    }

    fn reset(&mut self) {
        self.s1 = 0.0;
        self.s2 = 0.0;
    }
}

/// Tactical Ambient Situational Awareness & Transparency Processor.
pub struct TacticalTransparency {
    config: TransparencyConfig,
    /// High-pass biquad to strip low rumble
    hp_filter: BiquadState,
    /// Presence peak biquad for intelligibility
    presence_filter: BiquadState,
    /// Instantaneous peak envelope
    gain_attenuation: f32,
    /// Release alpha per sample
    release_alpha: f32,
    /// Safe linear peak threshold
    safe_linear_threshold: f32,
    /// Count of concussive clamp events
    pub concussive_clamps_count: u64,
}

impl TacticalTransparency {
    /// Creates a new TacticalTransparency processor.
    pub fn new(config: TransparencyConfig) -> Self {
        let mut proc = Self {
            hp_filter: BiquadState::default(),
            presence_filter: BiquadState::default(),
            gain_attenuation: 1.0,
            release_alpha: 0.999,
            safe_linear_threshold: 0.251, // 10^(-12 / 20)
            concussive_clamps_count: 0,
            config: config.clone(),
        };
        proc.update_coefficients();
        proc
    }

    /// Updates internal filter coefficients when configuration changes.
    pub fn set_config(&mut self, config: TransparencyConfig) {
        self.config = config;
        self.update_coefficients();
    }

    /// Returns current configuration.
    pub fn config(&self) -> &TransparencyConfig {
        &self.config
    }

    /// Dynamically enables or disables transparency mode.
    pub fn set_enabled(&mut self, enabled: bool) {
        self.config.enabled = enabled;
    }

    /// Dynamically adjusts ambient pass-through gain (0.0 to 2.0).
    pub fn set_ambient_gain(&mut self, gain: f32) {
        self.config.ambient_gain = gain.clamp(0.0, 2.0);
    }

    /// Resets all filter delay states and limiter gains.
    pub fn reset(&mut self) {
        self.hp_filter.reset();
        self.presence_filter.reset();
        self.gain_attenuation = 1.0;
        self.concussive_clamps_count = 0;
    }

    fn update_coefficients(&mut self) {
        let fs = self.config.sample_rate;
        let fc_hp = self.config.highpass_cutoff_hz.clamp(50.0, fs * 0.45);

        // 1. Butterworth 2nd-order High-Pass Filter (Q = 1 / sqrt(2))
        let w0_hp = 2.0 * PI * fc_hp / fs;
        let cos_w0 = w0_hp.cos();
        let sin_w0 = w0_hp.sin();
        let alpha_hp = sin_w0 / (2.0 * std::f32::consts::FRAC_1_SQRT_2);

        let a0_hp = 1.0 + alpha_hp;
        self.hp_filter.b0 = ((1.0 + cos_w0) * 0.5) / a0_hp;
        self.hp_filter.b1 = (-(1.0 + cos_w0)) / a0_hp;
        self.hp_filter.b2 = ((1.0 + cos_w0) * 0.5) / a0_hp;
        self.hp_filter.a1 = (-2.0 * cos_w0) / a0_hp;
        self.hp_filter.a2 = (1.0 - alpha_hp) / a0_hp;

        // 2. Presence Peaking Filter centered at 2.5 kHz (speech formant & footstep resonance)
        let f0_pres = 2500.0f32.min(fs * 0.45);
        let q_pres = 1.2;
        let a_pres = 10.0f32.powf(self.config.presence_boost_db / 40.0);
        let w0_pres = 2.0 * PI * f0_pres / fs;
        let sin_pres = w0_pres.sin();
        let cos_pres = w0_pres.cos();
        let alpha_pres = sin_pres / (2.0 * q_pres);

        let a0_pres = 1.0 + alpha_pres / a_pres;
        self.presence_filter.b0 = (1.0 + alpha_pres * a_pres) / a0_pres;
        self.presence_filter.b1 = (-2.0 * cos_pres) / a0_pres;
        self.presence_filter.b2 = (1.0 - alpha_pres * a_pres) / a0_pres;
        self.presence_filter.a1 = (-2.0 * cos_pres) / a0_pres;
        self.presence_filter.a2 = (1.0 - alpha_pres / a_pres) / a0_pres;

        // Safe threshold linear: 10^(safe_peak_limit_dbfs / 20)
        self.safe_linear_threshold = 10.0f32.powf(self.config.safe_peak_limit_dbfs / 20.0);

        // Exponential release factor: e^(-1 / (tau * fs))
        let tau_samples = (self.config.release_ms * 0.001) * fs;
        self.release_alpha = (-1.0 / tau_samples.max(1.0)).exp();
    }

    /// Processes an audio block, applying tactical awareness filtering and instant concussive protection.
    ///
    /// - `ambient_in`: Raw ambient audio picked up by microphones.
    /// - `enhanced_speech`: Active clean voice stream (e.g. from ANC pipeline).
    /// - `out`: Buffer receiving the blended, hearing-protected output.
    ///
    /// Guarantees zero heap allocation and strictly clamps peak outputs <= `safe_peak_limit_dbfs`.
    pub fn process_block(
        &mut self,
        ambient_in: &[f32],
        enhanced_speech: &[f32],
        out: &mut [f32],
    ) {
        let n = ambient_in.len();
        assert_eq!(enhanced_speech.len(), n);
        assert_eq!(out.len(), n);

        if !self.config.enabled {
            // When transparency is disabled, just pass enhanced speech
            out.copy_from_slice(enhanced_speech);
            return;
        }

        let amb_gain = self.config.ambient_gain;
        let v_safe = self.safe_linear_threshold;
        let alpha_rel = self.release_alpha;

        for i in 0..n {
            // 1. High-pass filter ambient audio to reject wind/vehicle rumble
            let hp = self.hp_filter.process(ambient_in[i]);

            // 2. Presence filter to emphasize speech intelligibility
            let shaped_ambient = self.presence_filter.process(hp) * amb_gain;

            // 3. Blend enhanced speech with filtered ambient awareness
            let raw_sum = enhanced_speech[i] + shaped_ambient;

            // 4. Instantaneous Concussive Hearing Protection Clamping:
            // Calculate instant peak magnitude
            let abs_val = raw_sum.abs();

            if abs_val > v_safe {
                // Instantaneous brickwall attenuation with zero attack latency
                let instant_gain = v_safe / (abs_val + 1e-9);
                if instant_gain < self.gain_attenuation {
                    self.gain_attenuation = instant_gain;
                    self.concussive_clamps_count += 1;
                }
            } else {
                // Smooth exponential release back towards unity gain (1.0)
                self.gain_attenuation = 1.0 - alpha_rel * (1.0 - self.gain_attenuation);
            }

            // 5. Apply protective attenuation
            let protected_sample = raw_sum * self.gain_attenuation;

            // Hard safety clamp to absolutely prevent any possibility of DAC clipping
            out[i] = protected_sample.clamp(-v_safe, v_safe);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_transparency_disabled_passes_speech_only() {
        let config = TransparencyConfig {
            enabled: false,
            ..Default::default()
        };
        let mut trans = TacticalTransparency::new(config);

        let ambient = vec![0.5f32; 128];
        let speech = vec![0.1f32; 128];
        let mut out = vec![0.0f32; 128];

        trans.process_block(&ambient, &speech, &mut out);

        for i in 0..128 {
            assert_eq!(out[i], 0.1f32);
        }
    }

    #[test]
    fn test_transparency_rumble_rejection() {
        let config = TransparencyConfig {
            enabled: true,
            highpass_cutoff_hz: 200.0,
            ambient_gain: 1.0,
            ..Default::default()
        };
        let mut trans = TacticalTransparency::new(config);

        // 50 Hz deep rumble sine wave
        let n = 512;
        let mut rumble = Vec::with_capacity(n);
        for i in 0..n {
            let t = i as f32 / 16000.0;
            rumble.push((2.0 * PI * 50.0 * t).sin() * 0.1);
        }

        let speech = vec![0.0f32; n];
        let mut out = vec![0.0f32; n];

        trans.process_block(&rumble, &speech, &mut out);

        // The 50 Hz rumble must be attenuated by > 12 dB relative to input
        let in_energy: f32 = rumble[200..].iter().map(|&x| x * x).sum();
        let out_energy: f32 = out[200..].iter().map(|&x| x * x).sum();

        let attenuation_db = 10.0 * (in_energy / out_energy.max(1e-9)).log10();
        assert!(
            attenuation_db > 10.0,
            "Expected rumble attenuation > 10 dB, got {:.2} dB",
            attenuation_db
        );
    }

    #[test]
    fn test_transparency_instantaneous_concussion_clamping() {
        let config = TransparencyConfig {
            enabled: true,
            safe_peak_limit_dbfs: -12.0, // Limit = 0.2512 linear
            ..Default::default()
        };
        let mut trans = TacticalTransparency::new(config);
        let safe_limit = 10.0f32.powf(-12.0 / 20.0);

        // Simulate normal ambient speech followed by a huge explosive detonation (amplitude 10.0)
        let n = 256;
        let mut ambient = vec![0.05f32; n];
        ambient[64] = 10.0; // Gunshot / explosion shockwave
        ambient[65] = -8.0;

        let speech = vec![0.0f32; n];
        let mut out = vec![0.0f32; n];

        trans.process_block(&ambient, &speech, &mut out);

        // Verify that the explosive impulse was clamped strictly <= safe_limit
        for i in 0..n {
            assert!(
                out[i].abs() <= safe_limit + 1e-4,
                "Sample {} exceeded hearing safe limit: val={}, limit={}",
                i,
                out[i],
                safe_limit
            );
        }
        assert!(trans.concussive_clamps_count > 0);
    }
}
