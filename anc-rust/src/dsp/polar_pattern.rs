//! First-Order Differential Polar Directivity Pattern Shaper.
//!
//! Developed for SIH 26052 Tactical Military Audio Systems.
//!
//! Dual-microphone differential arrays (separated by acoustic distance $d$) can synthesize
//! any first-order differential polar directivity pattern:
//! $$Y(t) = \frac{1}{1 + \tau / \tau_0} \left[ X_1(t) - \alpha \cdot X_2(t - \tau) \right]$$
//! where $\tau_0 = d / c$ is the acoustic transit time between microphone capsules.
//!
//! By tuning the attenuation factor $\alpha$ and internal acoustic delay $\tau = \beta \cdot d / c$:
//! - Omnidirectional: $\alpha = 0.0, \tau = 0$
//! - Cardioid: $\alpha = 1.0, \tau = d/c$ (acoustic null at $180^\circ$)
//! - Supercardioid: $\alpha = 0.577, \tau = 0.577 d/c$ (acoustic nulls at $\pm 126^\circ$)
//! - Hypercardioid: $\alpha = 0.333, \tau = 0.333 d/c$ (acoustic nulls at $\pm 110^\circ$)
//! - Figure-8: $\alpha = 1.0, \tau = 0$ (acoustic nulls at $\pm 90^\circ$)
//! - Custom Steered Null: $\tau = -\tau_0 \cos(\theta_{\text{null}})$, placing a deep null directly
//!   at the operator-specified angle $\theta_{\text{null}} \in [90^\circ, 180^\circ]$ to null out
//!   tanks, artillery, or drone motors.
//!
//! Features:
//! 1. High-Precision Cubic Hermite Fractional Delay Interpolator (sub-sample accuracy).
//! 2. 1st-Order Integrating Equalizer (+6 dB/octave differential slope compensation with DC highpass).
//! 3. Strictly ZERO heap allocations in real-time execution.

/// Speed of sound in dry air at 20°C in m/s.
pub const SPEED_OF_SOUND_M_S: f32 = 343.0;

/// Ring buffer capacity for fractional delay line.
pub const POLAR_DELAY_BUFFER_CAPACITY: usize = 128;

/// Supported first-order differential polar directivity patterns.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
#[repr(u8)]
pub enum PolarPatternType {
    /// Non-directional omni pattern (alpha = 0.0).
    Omnidirectional = 0,
    /// Standard Cardioid pattern (null at 180°).
    #[default]
    Cardioid = 1,
    /// Supercardioid pattern (maximum front-to-random index, nulls at ±126°).
    Supercardioid = 2,
    /// Hypercardioid pattern (maximum directivity factor = 4.0, nulls at ±110°).
    Hypercardioid = 3,
    /// Bidirectional Figure-8 pattern (nulls at ±90°).
    Figure8 = 4,
    /// Custom Steered Null Pattern toward tactical threat.
    CustomSteered = 5,
}

impl PolarPatternType {
    pub fn name(&self) -> &'static str {
        match self {
            Self::Omnidirectional => "Omnidirectional",
            Self::Cardioid => "Cardioid (Null: 180°)",
            Self::Supercardioid => "Supercardioid (Null: ±126°)",
            Self::Hypercardioid => "Hypercardioid (Null: ±110°)",
            Self::Figure8 => "Figure-8 (Null: ±90°)",
            Self::CustomSteered => "Custom Steered Null",
        }
    }

    pub fn from_u8(val: u8) -> Self {
        match val {
            0 => Self::Omnidirectional,
            1 => Self::Cardioid,
            2 => Self::Supercardioid,
            3 => Self::Hypercardioid,
            4 => Self::Figure8,
            _ => Self::CustomSteered,
        }
    }
}

/// Configuration parameters for First-Order Polar Directivity Shaper.
#[derive(Debug, Clone, Copy)]
pub struct PolarPatternConfig {
    /// Sampling rate in Hz (default: 16000.0).
    pub sample_rate: f32,
    /// Physical distance between microphone capsules in meters (default: 0.020 m = 20 mm).
    pub mic_distance_m: f32,
    /// Selected directivity pattern.
    pub pattern: PolarPatternType,
    /// Steered null angle in degrees for CustomSteered mode (90.0° to 180.0°).
    pub custom_null_angle_deg: f32,
    /// Whether differential integration equalizer is enabled to flatten +6 dB/oct slope.
    pub enable_equalizer: bool,
    /// Active state of pattern shaper.
    pub enabled: bool,
}

impl Default for PolarPatternConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000.0,
            mic_distance_m: 0.020, // 20 mm inter-capsule distance
            pattern: PolarPatternType::Cardioid,
            custom_null_angle_deg: 180.0,
            enable_equalizer: true,
            enabled: true,
        }
    }
}

/// Telemetry information from the Polar Pattern Shaper.
#[derive(Debug, Clone, Copy, Default)]
pub struct PolarPatternTelemetry {
    /// Selected polar directivity pattern.
    pub pattern_type: u8,
    /// Acoustic null angle in degrees (90° to 180°).
    pub null_angle_deg: f32,
    /// Front-to-back sensitivity ratio in dB.
    pub front_to_back_ratio_db: f32,
    /// Directivity Index (DI) in dB.
    pub directivity_index_db: f32,
    /// Internal synthesis delay in microseconds.
    pub internal_delay_us: f32,
}

/// First-Order Differential Polar Directivity Pattern Shaper.
pub struct PolarPatternShaper {
    config: PolarPatternConfig,

    // Synthesis parameters
    alpha: f32,
    delay_samples: f32,
    tau_sec: f32,
    norm_gain: f32,

    // Fractional delay ring buffer for Mic 2
    delay_buffer: [f32; POLAR_DELAY_BUFFER_CAPACITY],
    write_idx: usize,

    // Integrating equalizer filter state (Direct Form I / II)
    eq_b0: f32,
    eq_b1: f32,
    eq_a1: f32,
    eq_x1: f32,
    eq_y1: f32,

    // Telemetry
    telemetry: PolarPatternTelemetry,
}

impl PolarPatternShaper {
    /// Creates a new PolarPatternShaper with the given configuration.
    pub fn new(config: PolarPatternConfig) -> Self {
        let mut shaper = Self {
            config,
            alpha: 1.0,
            delay_samples: 0.0,
            tau_sec: 0.0,
            norm_gain: 1.0,
            delay_buffer: [0.0; POLAR_DELAY_BUFFER_CAPACITY],
            write_idx: 0,
            eq_b0: 1.0,
            eq_b1: 0.0,
            eq_a1: 0.0,
            eq_x1: 0.0,
            eq_y1: 0.0,
            telemetry: PolarPatternTelemetry::default(),
        };

        shaper.recompute_parameters();
        shaper
    }

    /// Recomputes alpha, delay, and equalizer parameters.
    pub fn recompute_parameters(&mut self) {
        let fs = self.config.sample_rate.max(8000.0);
        let d = self.config.mic_distance_m.clamp(0.005, 0.200);
        let tau0 = d / SPEED_OF_SOUND_M_S; // e.g. 20 mm / 343 m/s = 58.31 us

        let (alpha, tau_sec, null_angle_deg, di_db, fbr_db) = match self.config.pattern {
            PolarPatternType::Omnidirectional => {
                // Y(t) = X1(t)
                (0.0f32, 0.0f32, 0.0f32, 0.0f32, 0.0f32)
            }
            PolarPatternType::Cardioid => {
                // Null at 180 deg: tau = tau0, alpha = 1.0
                (1.0f32, tau0, 180.0f32, 4.8f32, 35.0f32)
            }
            PolarPatternType::Supercardioid => {
                // Null at 126 deg: beta = 0.577, tau = 0.577 * tau0, alpha = 0.577
                (0.577f32, 0.577 * tau0, 126.0f32, 5.7f32, 11.5f32)
            }
            PolarPatternType::Hypercardioid => {
                // Null at 110 deg: beta = 0.333, tau = 0.333 * tau0, alpha = 0.333
                (0.333f32, 0.333 * tau0, 110.0f32, 6.0f32, 6.0f32)
            }
            PolarPatternType::Figure8 => {
                // Null at 90 deg: tau = 0, alpha = 1.0
                (1.0f32, 0.0f32, 90.0f32, 4.8f32, 0.0f32)
            }
            PolarPatternType::CustomSteered => {
                let angle_deg = self.config.custom_null_angle_deg.clamp(90.0, 180.0);
                let angle_rad = angle_deg.to_radians();
                // tau = -tau0 * cos(theta_null) >= 0 since cos(90..180) <= 0
                let tau = -tau0 * angle_rad.cos();
                let fbr = if angle_deg >= 175.0 {
                    30.0
                } else {
                    20.0 * ((1.0 + angle_rad.cos().abs()) / (1.0 - angle_rad.cos().abs()).max(1e-3)).log10()
                };
                (1.0f32, tau.max(0.0), angle_deg, 4.5f32, fbr.clamp(0.0, 40.0))
            }
        };

        self.alpha = alpha;
        self.tau_sec = tau_sec;
        let delay_samples = tau_sec * fs;
        self.delay_samples = delay_samples.clamp(0.0, (POLAR_DELAY_BUFFER_CAPACITY - 4) as f32);

        // Normalization factor so on-axis sensitivity is consistent
        let delay_ratio = tau_sec / tau0;
        self.norm_gain = if self.config.pattern == PolarPatternType::Omnidirectional {
            1.0
        } else {
            1.0 / (1.0 + delay_ratio).max(0.5)
        };

        // Equalizer design: 1st-order integrating filter compensating for omega*d/c slope.
        // Corner frequency f_corner = c / (2 * pi * d) (e.g. 2730 Hz for 20 mm).
        // Low cutoff f_hp = 80 Hz to prevent extreme DC boost.
        let f_corner = (SPEED_OF_SOUND_M_S / (2.0 * std::f32::consts::PI * d)).clamp(500.0, fs * 0.45);
        let f_hp = 80.0f32;

        let w_hp = 2.0 * std::f32::consts::PI * f_hp / fs;
        let w_corner = 2.0 * std::f32::consts::PI * f_corner / fs;

        // Bilinear transform of (s + w_corner) / (s + w_hp)
        let k = 2.0; // Bilinear scaling constant
        let a0 = k + w_hp;
        self.eq_b0 = (k + w_corner) / a0;
        self.eq_b1 = (-k + w_corner) / a0;
        self.eq_a1 = (-k + w_hp) / a0;

        self.telemetry = PolarPatternTelemetry {
            pattern_type: self.config.pattern as u8,
            null_angle_deg,
            front_to_back_ratio_db: fbr_db,
            directivity_index_db: di_db,
            internal_delay_us: tau_sec * 1_000_000.0,
        };
    }

    /// Resets delay line and equalizer states.
    pub fn reset(&mut self) {
        self.delay_buffer = [0.0; POLAR_DELAY_BUFFER_CAPACITY];
        self.write_idx = 0;
        self.eq_x1 = 0.0;
        self.eq_y1 = 0.0;
    }

    /// Sets the polar directivity pattern.
    pub fn set_pattern(&mut self, pattern: PolarPatternType) {
        self.config.pattern = pattern;
        self.recompute_parameters();
    }

    /// Sets the custom steered null angle in degrees (90.0° to 180.0°).
    pub fn set_custom_null_angle_deg(&mut self, angle_deg: f32) {
        self.config.pattern = PolarPatternType::CustomSteered;
        self.config.custom_null_angle_deg = angle_deg.clamp(90.0, 180.0);
        self.recompute_parameters();
    }

    /// Calculates theoretical directional sensitivity $D(\theta)$ normalized to 1.0 on-axis.
    pub fn sensitivity_at_angle(&self, angle_deg: f32) -> f32 {
        let angle_rad = angle_deg.to_radians();
        let cos_theta = angle_rad.cos();
        let d = self.config.mic_distance_m;
        let tau0 = d / SPEED_OF_SOUND_M_S;

        match self.config.pattern {
            PolarPatternType::Omnidirectional => 1.0,
            PolarPatternType::Cardioid => 0.5 * (1.0 + cos_theta),
            PolarPatternType::Supercardioid => 0.37 + 0.63 * cos_theta,
            PolarPatternType::Hypercardioid => 0.25 + 0.75 * cos_theta,
            PolarPatternType::Figure8 => cos_theta.abs(),
            PolarPatternType::CustomSteered => {
                let tau = self.tau_sec;
                let pattern = (tau + tau0 * cos_theta).abs() / (tau + tau0).max(1e-6);
                pattern.clamp(0.0, 1.0)
            }
        }
    }

    /// Reads fractional delayed sample from Mic 2 buffer via 4-point Cubic Hermite interpolation.
    #[inline(always)]
    fn read_delayed_mic2(&self, delay: f32) -> f32 {
        let cap = POLAR_DELAY_BUFFER_CAPACITY;
        let int_d = delay.floor() as usize;
        let frac = delay - int_d as f32;

        let current_idx = (self.write_idx + cap - 1) % cap;
        let idx1 = (current_idx + cap - int_d) % cap;
        let idx2 = (idx1 + cap - 1) % cap;
        let idx0 = (idx1 + 1) % cap;
        let idx3 = (idx2 + cap - 1) % cap;

        let x0 = self.delay_buffer[idx0];
        let x1 = self.delay_buffer[idx1];
        let x2 = self.delay_buffer[idx2];
        let x3 = self.delay_buffer[idx3];

        // 4-point Cubic Hermite interpolation
        let c0 = x1;
        let c1 = 0.5 * (x2 - x0);
        let c2 = x0 - 2.5 * x1 + 2.0 * x2 - 0.5 * x3;
        let c3 = 0.5 * (x3 - x0) + 1.5 * (x1 - x2);

        ((c3 * frac + c2) * frac + c1) * frac + c0
    }

    /// Processes a single pair of microphone samples.
    #[inline]
    pub fn process_sample(&mut self, mic1: f32, mic2: f32) -> f32 {
        if !self.config.enabled {
            return mic1;
        }

        // Write Mic 2 sample to circular buffer
        self.delay_buffer[self.write_idx] = mic2;
        self.write_idx = (self.write_idx + 1) % POLAR_DELAY_BUFFER_CAPACITY;

        if self.config.pattern == PolarPatternType::Omnidirectional {
            return mic1;
        }

        // Fetch fractional delayed Mic 2 sample
        let delayed_mic2 = self.read_delayed_mic2(self.delay_samples);

        // First-order differential subtraction
        let diff = (mic1 - self.alpha * delayed_mic2) * self.norm_gain;

        // Equalization compensation
        if self.config.enable_equalizer {
            let eq_out = self.eq_b0 * diff + self.eq_b1 * self.eq_x1 - self.eq_a1 * self.eq_y1;
            self.eq_x1 = diff;
            self.eq_y1 = eq_out;
            eq_out
        } else {
            diff
        }
    }

    /// Processes a block of stereo microphone samples in-place.
    pub fn process_block(&mut self, mic1: &mut [f32], mic2: &[f32]) {
        if !self.config.enabled {
            return;
        }
        let n = mic1.len().min(mic2.len());
        for i in 0..n {
            mic1[i] = self.process_sample(mic1[i], mic2[i]);
        }
    }

    /// Returns the current telemetry metrics.
    pub fn telemetry(&self) -> PolarPatternTelemetry {
        self.telemetry
    }

    /// Returns the current pattern type.
    pub fn pattern(&self) -> PolarPatternType {
        self.config.pattern
    }

    /// Sets whether polar shaper is enabled.
    pub fn set_enabled(&mut self, enabled: bool) {
        self.config.enabled = enabled;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_polar_pattern_initialization() {
        let config = PolarPatternConfig {
            sample_rate: 16000.0,
            mic_distance_m: 0.020,
            pattern: PolarPatternType::Cardioid,
            ..Default::default()
        };
        let shaper = PolarPatternShaper::new(config);
        let telem = shaper.telemetry();

        assert_eq!(telem.pattern_type, PolarPatternType::Cardioid as u8);
        assert_eq!(telem.null_angle_deg, 180.0);
        assert!(telem.internal_delay_us > 50.0 && telem.internal_delay_us < 65.0);
    }

    #[test]
    fn test_cardioid_attenuates_rear_sound() {
        let config = PolarPatternConfig {
            sample_rate: 16000.0,
            mic_distance_m: 0.020,
            pattern: PolarPatternType::Cardioid,
            enable_equalizer: false,
            ..Default::default()
        };
        let mut shaper = PolarPatternShaper::new(config);

        let d = 0.020;
        let c = SPEED_OF_SOUND_M_S;
        let tau0 = d / c;
        let dt_rear = tau0; // Sound from rear hits Mic 2 first, then Mic 1 after tau0

        // Test with rear incident wave: Mic2 leads Mic1 by tau0
        // Mic1(t) = s(t - tau0), Mic2(t) = s(t)
        // With Cardioid, Y(t) = Mic1(t) - Mic2(t - tau0) = s(t - tau0) - s(t - tau0) = 0!
        let freq = 1000.0f32;
        let mut residual_power = 0.0f32;

        for i in 0..300 {
            let t = i as f32 / 16000.0;
            let mic2 = (2.0 * std::f32::consts::PI * freq * t).sin();
            let mic1 = (2.0 * std::f32::consts::PI * freq * (t - dt_rear)).sin();

            let out = shaper.process_sample(mic1, mic2);
            if i > 50 {
                residual_power += out * out;
            }
        }

        let mean_residual = residual_power / 250.0;
        assert!(mean_residual < 0.02, "Cardioid must deeply nullify rear-incident acoustic sound");
    }

    #[test]
    fn test_custom_steered_null_angle() {
        let mut shaper = PolarPatternShaper::new(PolarPatternConfig::default());
        shaper.set_custom_null_angle_deg(110.0);

        let telem = shaper.telemetry();
        assert_eq!(telem.pattern_type, PolarPatternType::CustomSteered as u8);
        assert_eq!(telem.null_angle_deg, 110.0);

        let sens_110 = shaper.sensitivity_at_angle(110.0);
        let sens_0 = shaper.sensitivity_at_angle(0.0);

        assert!(sens_110 < 0.05, "Sensitivity at steered null angle 110° should be near zero");
        assert!((sens_0 - 1.0).abs() < 0.01, "Sensitivity on-axis (0°) should be normalized to 1.0");
    }

    #[test]
    fn test_pattern_types_switch_cleanly() {
        let mut shaper = PolarPatternShaper::new(PolarPatternConfig::default());

        for pat in [
            PolarPatternType::Omnidirectional,
            PolarPatternType::Cardioid,
            PolarPatternType::Supercardioid,
            PolarPatternType::Hypercardioid,
            PolarPatternType::Figure8,
        ] {
            shaper.set_pattern(pat);
            assert_eq!(shaper.pattern(), pat);
            let out = shaper.process_sample(0.5, 0.5);
            assert!(!out.is_nan());
        }
    }
}
