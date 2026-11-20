//! Online Direction of Arrival (DOA) Tracking via GCC-PHAT with 2-State Kalman Filter
//! and Near-Field Spherical Wavefront Correction.
//!
//! Provides real-time acoustic mouth tracking for the SIH 26052 30mm dual-microphone baseline array:
//! - Distance d = 0.03 m (30 mm)
//! - Speed of sound c = 343.0 m/s
//! - Nominal Broadside: 0 degrees (perpendicular to array axis)
//! - Near-Field Spherical Geometry: Mouth positioned at r < 15 cm from array center
//! - 2-State Kinematic Kalman Filter: State [theta, dot_theta] tracks mouth angle and angular
//!   velocity, eliminating sensor jitter during combat vehicle vibration and rapid soldier head shaking.
//!
//! Generalized Cross-Correlation with Phase Transform (GCC-PHAT) and sub-sample parabolic
//! interpolation measures delay tau(t). The near-field spherical model calculates the true
//! physical angle theta(t), which is then fused by the 2-state Kalman filter to dynamically
//! steer the MVDR beamformer steering vector d(omega, theta(t)).

use num_complex::Complex32;
use rustfft::{Fft, FftPlanner};
use std::f32::consts::PI;
use std::sync::Arc;

/// Configuration for GCC-PHAT Direction of Arrival (DOA) tracking.
#[derive(Debug, Clone)]
pub struct DoaConfig {
    /// Number of STFT frequency bins (n_fft / 2 + 1)
    pub num_bins: usize,
    /// STFT FFT size (e.g. 512)
    pub n_fft: usize,
    /// Hop size in samples (e.g. 256)
    pub hop_size: usize,
    /// Sampling rate in Hz (e.g. 16000.0)
    pub sample_rate: f32,
    /// Microphone baseline spacing in meters (default: 0.03 m / 30 mm)
    pub mic_distance_m: f32,
    /// Speed of sound in m/s (default: 343.0 m/s)
    pub speed_of_sound_m_s: f32,
    /// Maximum allowable tracking angle in degrees (default: 45.0 degrees)
    pub max_angle_deg: f32,
    /// Temporal smoothing factor for legacy fallback (default: 0.90)
    pub smoothing: f32,
    /// Minimum Speech Presence Probability (SPP) required to update angle tracking (default: 0.30)
    pub spp_threshold: f32,
    /// Regularization epsilon for GCC-PHAT denominator (default: 1e-6)
    pub phat_eps: f32,
    /// Near-field mouth distance from array center in meters (default: 0.08 m = 8 cm, < 15 cm)
    pub near_field_radius_m: f32,
    /// Kalman process noise acceleration variance q in (deg/s^2)^2 (default: 350.0)
    pub kalman_process_var: f32,
    /// Base measurement noise variance R0 in deg^2 (default: 2.5)
    pub kalman_meas_var: f32,
}

impl Default for DoaConfig {
    fn default() -> Self {
        Self {
            num_bins: 257,
            n_fft: 512,
            hop_size: 256,
            sample_rate: 16000.0,
            mic_distance_m: 0.03, // 30 mm baseline
            speed_of_sound_m_s: 343.0,
            max_angle_deg: 45.0,
            smoothing: 0.90,
            spp_threshold: 0.30,
            phat_eps: 1e-6,
            near_field_radius_m: 0.08, // 80 mm (near-field mouth boom position)
            kalman_process_var: 40.0,
            kalman_meas_var: 3.5,
        }
    }
}

/// 2-State Kinematic Kalman Filter for mouth tracking: State x = [theta (deg), dot_theta (deg/s)]^T.
#[derive(Debug, Clone, Copy)]
pub struct MouthTrackingKalman {
    pub theta_deg: f32,
    pub dot_theta_dps: f32,
    pub p00: f32,
    pub p01: f32,
    pub p11: f32,
}

impl Default for MouthTrackingKalman {
    fn default() -> Self {
        Self {
            theta_deg: 0.0,
            dot_theta_dps: 0.0,
            p00: 5.0,
            p01: 0.0,
            p11: 25.0,
        }
    }
}

impl MouthTrackingKalman {
    pub fn reset(&mut self) {
        self.theta_deg = 0.0;
        self.dot_theta_dps = 0.0;
        self.p00 = 5.0;
        self.p01 = 0.0;
        self.p11 = 25.0;
    }

    /// Predicts state forward by dt seconds.
    #[inline]
    pub fn predict(&mut self, dt: f32, q_accel: f32) {
        let alpha_v = (2.0 * dt).min(0.10); // Rotational velocity damping
        let f11 = 1.0 - alpha_v;

        // x_pred = F * x
        let theta_pred = self.theta_deg + dt * self.dot_theta_dps;
        let dot_theta_pred = f11 * self.dot_theta_dps;

        // Process noise covariance Q for constant velocity with continuous acceleration variance q
        let dt2 = dt * dt;
        let dt3 = dt2 * dt;
        let q00 = q_accel * (dt3 / 3.0);
        let q01 = q_accel * (dt2 / 2.0);
        let q11 = q_accel * dt;

        // P_pred = F * P * F^T + Q
        let p00_pred = self.p00 + 2.0 * dt * self.p01 + dt2 * self.p11 + q00;
        let p01_pred = f11 * (self.p01 + dt * self.p11) + q01;
        let p11_pred = f11 * f11 * self.p11 + q11;

        self.theta_deg = theta_pred;
        self.dot_theta_dps = dot_theta_pred;
        self.p00 = p00_pred;
        self.p01 = p01_pred;
        self.p11 = p11_pred;
    }

    /// Updates state with a measured angle and peak confidence.
    #[inline]
    pub fn update(&mut self, meas_angle_deg: f32, confidence: f32, r0: f32) {
        // Measurement noise variance R adapts inversely to peak sharpness confidence
        let conf_clamped = confidence.clamp(0.05, 1.0);
        let r_meas = r0 / (conf_clamped * conf_clamped);

        // Innovation y = z - H * x (H = [1, 0])
        let y = meas_angle_deg - self.theta_deg;

        // Innovation covariance S = H * P * H^T + R = P00 + R
        let s = self.p00 + r_meas;
        let inv_s = 1.0 / s;

        // Kalman gain K = P * H^T / S = [P00/S, P01/S]^T
        let k0 = self.p00 * inv_s;
        let k1 = self.p01 * inv_s;

        // Updated state: x = x + K * y
        self.theta_deg += k0 * y;
        self.dot_theta_dps += k1 * y;

        // Updated covariance: P = (I - K * H) * P
        let prior_p01 = self.p01;
        self.p00 *= 1.0 - k0;
        self.p01 = (1.0 - k0) * prior_p01;
        self.p11 = (self.p11 - k1 * prior_p01).max(1e-4);
    }
}

/// Real-time causal GCC-PHAT Direction of Arrival (DOA) tracker with Kalman filtering.
pub struct GccPhatDoaTracker {
    config: DoaConfig,
    fft_inverse: Arc<dyn Fft<f32>>,
    full_spec: Vec<Complex32>,
    time_corr: Vec<Complex32>,
    fft_scratch: Vec<Complex32>,
    kalman: MouthTrackingKalman,
    current_delay_samples: f32,
    confidence: f32,
}

impl GccPhatDoaTracker {
    /// Creates a new GCC-PHAT DOA tracker.
    pub fn new(config: DoaConfig) -> Self {
        let n_fft = config.n_fft;
        let mut planner = FftPlanner::<f32>::new();
        let fft_inverse = planner.plan_fft_inverse(n_fft);
        let scratch_len = fft_inverse.get_inplace_scratch_len();

        Self {
            fft_inverse,
            full_spec: vec![Complex32::default(); n_fft],
            time_corr: vec![Complex32::default(); n_fft],
            fft_scratch: vec![Complex32::default(); scratch_len],
            kalman: MouthTrackingKalman::default(),
            current_delay_samples: 0.0,
            confidence: 1.0,
            config,
        }
    }

    /// Resets the tracker state to broadside (0 degrees).
    pub fn reset(&mut self) {
        self.kalman.reset();
        self.current_delay_samples = 0.0;
        self.confidence = 1.0;
        self.full_spec.fill(Complex32::default());
        self.time_corr.fill(Complex32::default());
    }

    /// Returns the currently tracked talker angle in degrees.
    #[inline]
    pub fn tracked_angle_deg(&self) -> f32 {
        self.kalman.theta_deg
    }

    /// Returns the currently tracked mouth angular velocity in degrees per second.
    #[inline]
    pub fn tracked_angular_velocity(&self) -> f32 {
        self.kalman.dot_theta_dps
    }

    /// Returns the currently estimated acoustic delay in samples.
    #[inline]
    pub fn tracked_delay_samples(&self) -> f32 {
        self.current_delay_samples
    }

    /// Returns the current peak confidence metric [0.0, 1.0].
    #[inline]
    pub fn confidence(&self) -> f32 {
        self.confidence
    }

    /// Returns the current Kalman angle variance.
    #[inline]
    pub fn kalman_variance(&self) -> f32 {
        self.kalman.p00
    }

    /// Helper to convert a signed integer lag tau in [-N/2, N/2 - 1] to FFT index.
    #[inline]
    fn lag_to_index(lag: i32, n_fft: usize) -> usize {
        if lag >= 0 {
            lag as usize
        } else {
            (n_fft as i32 + lag) as usize
        }
    }

    /// Converts measured acoustic delay delta_t to mouth angle theta_deg using
    /// Near-Field Spherical Wavefront Geometry (r < 15 cm) or Far-Field Plane Wave.
    #[inline]
    fn delay_to_angle_deg(&self, delta_t: f32) -> f32 {
        let d = self.config.mic_distance_m;
        let c = self.config.speed_of_sound_m_s;
        let r = self.config.near_field_radius_m;

        let delta_r = delta_t * c;
        let max_rad = self.config.max_angle_deg * PI / 180.0;
        let sin_max = max_rad.sin();

        let sin_theta = if r > 0.02 && r < 0.50 {
            // Near-field spherical wavefront correction:
            // Path difference delta_r = r2 - r1
            // (r1 + r2)^2 = 4*r^2 + d^2 - delta_r^2
            // sin(theta) = (delta_r * sqrt(4*r^2 + d^2 - delta_r^2)) / (2 * d * r)
            let geom_term = (4.0 * r * r + d * d - delta_r * delta_r).max(0.0).sqrt();
            let raw_sin = (delta_r * geom_term) / (2.0 * d * r);
            raw_sin.clamp(-sin_max, sin_max)
        } else {
            // Far-field plane wave approximation
            (delta_r / d).clamp(-sin_max, sin_max)
        };

        sin_theta.asin() * 180.0 / PI
    }

    /// Processes a single STFT frame of dual-microphone spectra and updates the tracked DOA angle.
    ///
    /// - `mic1_spec`: STFT complex spectrum of Primary Mic 1 [num_bins].
    /// - `mic2_spec`: STFT complex spectrum of Secondary Mic 2 [num_bins].
    /// - `spp_mean`: Mean speech presence probability for the frame (0.0 to 1.0).
    ///
    /// Returns the updated smoothed talker angle in degrees within `[-max_angle_deg, +max_angle_deg]`.
    pub fn process_frame(
        &mut self,
        mic1_spec: &[Complex32],
        mic2_spec: &[Complex32],
        spp_mean: f32,
    ) -> f32 {
        let num_bins = self.config.num_bins;
        let n_fft = self.config.n_fft;
        assert_eq!(mic1_spec.len(), num_bins);
        assert_eq!(mic2_spec.len(), num_bins);

        // 1. Compute Phase Transform (PHAT) normalized cross-spectrum
        let eps = self.config.phat_eps;
        let half = n_fft / 2;

        self.full_spec[0] = Complex32::new((mic2_spec[0] * mic1_spec[0].conj()).re.signum(), 0.0);

        for k in 1..half {
            let cross = mic2_spec[k] * mic1_spec[k].conj();
            let norm = cross.norm() + eps;
            let phat_k = cross / norm;
            self.full_spec[k] = phat_k;
            self.full_spec[n_fft - k] = phat_k.conj();
        }

        if half < num_bins {
            let cross_nyq = mic2_spec[half] * mic1_spec[half].conj();
            self.full_spec[half] = Complex32::new(cross_nyq.re.signum(), 0.0);
        }

        // 2. Compute Inverse FFT to obtain time-domain cross-correlation
        self.time_corr.copy_from_slice(&self.full_spec);
        self.fft_inverse
            .process_with_scratch(&mut self.time_corr, &mut self.fft_scratch);

        let inv_n = 1.0 / (n_fft as f32);

        // 3. Search for peak within the physical propagation bounds of the 30mm array:
        let max_rad = self.config.max_angle_deg * PI / 180.0;
        let sin_max = max_rad.sin();
        let tau_max_sec = (self.config.mic_distance_m * sin_max) / self.config.speed_of_sound_m_s;
        let tau_max_samples = tau_max_sec * self.config.sample_rate;
        let max_search_lag = (tau_max_samples.ceil() as i32 + 1).max(2);

        let mut best_lag = 0i32;
        let mut best_val = -1e9f32;

        for lag in -max_search_lag..=max_search_lag {
            let idx = Self::lag_to_index(lag, n_fft);
            let val = self.time_corr[idx].re * inv_n;
            if val > best_val {
                best_val = val;
                best_lag = lag;
            }
        }

        // 4. Sub-sample Parabolic Peak Interpolation
        let idx_m1 = Self::lag_to_index(best_lag - 1, n_fft);
        let idx_0 = Self::lag_to_index(best_lag, n_fft);
        let idx_p1 = Self::lag_to_index(best_lag + 1, n_fft);

        let y_m1 = self.time_corr[idx_m1].re * inv_n;
        let y_0 = self.time_corr[idx_0].re * inv_n;
        let y_p1 = self.time_corr[idx_p1].re * inv_n;

        let denom = 2.0 * y_0 - y_m1 - y_p1;
        let delta = if denom.abs() > 1e-7 && denom > 0.0 {
            ((y_p1 - y_m1) / (2.0 * denom)).clamp(-0.5, 0.5)
        } else {
            0.0
        };

        let sub_sample_lag = best_lag as f32 + delta;
        let delta_t = sub_sample_lag / self.config.sample_rate;

        // 5. Near-Field Spherical Wavefront Calculation
        let measured_angle_deg = self.delay_to_angle_deg(delta_t);

        // Peak confidence based on GCC peak sharpness relative to neighbor average
        let avg_neighbor = 0.5 * (y_m1 + y_p1);
        let raw_conf = ((y_0 - avg_neighbor) / (y_0.abs() + 1e-6)).clamp(0.0, 1.0);
        self.confidence = 0.85 * self.confidence + 0.15 * raw_conf;

        // 6. 2-State Kalman Filter State Prediction & Speech-Gated Update
        let dt = self.config.hop_size as f32 / self.config.sample_rate;
        self.kalman.predict(dt, self.config.kalman_process_var);

        if spp_mean >= self.config.spp_threshold && self.confidence > 0.05 {
            // Speech active: fuse measurement via Kalman gain
            self.kalman.update(
                measured_angle_deg,
                self.confidence,
                self.config.kalman_meas_var,
            );
            self.current_delay_samples = 0.90 * self.current_delay_samples + 0.10 * sub_sample_lag;
        } else {
            // Speech pause: freeze angle, damp velocity
            self.kalman.dot_theta_dps *= 0.90;
        }

        self.kalman.theta_deg = self
            .kalman
            .theta_deg
            .clamp(-self.config.max_angle_deg, self.config.max_angle_deg);
        self.kalman.theta_deg
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_gcc_phat_broadside_zero_delay() {
        let config = DoaConfig::default();
        let mut tracker = GccPhatDoaTracker::new(config.clone());

        // Synthesize identical broadside tones at mic 1 and mic 2 (delay = 0.0)
        let num_bins = config.num_bins;
        let mut mic1 = vec![Complex32::default(); num_bins];
        let mut mic2 = vec![Complex32::default(); num_bins];

        // Strong voice formant peak at 1 kHz (bin 32 @ 16 kHz, 512 FFT)
        mic1[32] = Complex32::new(10.0, 0.0);
        mic2[32] = Complex32::new(10.0, 0.0);

        for _ in 0..10 {
            tracker.process_frame(&mic1, &mic2, 0.9);
        }

        assert!(
            tracker.tracked_angle_deg().abs() < 1.0,
            "Broadside speech should track to near 0.0 degrees, got {:.2}",
            tracker.tracked_angle_deg()
        );
        assert!(
            tracker.tracked_delay_samples().abs() < 0.05,
            "Broadside delay should be near 0 samples, got {:.4}",
            tracker.tracked_delay_samples()
        );
    }

    #[test]
    fn test_gcc_phat_positive_angle_slip() {
        let config = DoaConfig::default();
        let mut tracker = GccPhatDoaTracker::new(config.clone());
        let num_bins = config.num_bins;

        // Target rotated to +30 degrees
        let target_angle_deg = 30.0f32;
        let target_angle_rad = target_angle_deg * PI / 180.0;
        let delta_t = (config.mic_distance_m * target_angle_rad.sin()) / config.speed_of_sound_m_s;
        let bin_hz = config.sample_rate / config.n_fft as f32;

        let mut mic1 = vec![Complex32::default(); num_bins];
        let mut mic2 = vec![Complex32::default(); num_bins];

        // Wideband speech spectrum excitation across bins 20..100
        for k in 20..100 {
            let freq = k as f32 * bin_hz;
            let phase = -2.0 * PI * freq * delta_t;
            mic1[k] = Complex32::from_polar(5.0, 0.1 * k as f32);
            mic2[k] = Complex32::from_polar(5.0, 0.1 * k as f32 + phase);
        }

        for _ in 0..30 {
            tracker.process_frame(&mic1, &mic2, 0.85);
        }

        let tracked = tracker.tracked_angle_deg();
        assert!(
            (tracked - target_angle_deg).abs() < 3.5,
            "Target at +30 deg should be tracked accurately, got {:.2} deg",
            tracked
        );
    }

    #[test]
    fn test_gcc_phat_negative_angle_slip() {
        let config = DoaConfig::default();
        let mut tracker = GccPhatDoaTracker::new(config.clone());
        let num_bins = config.num_bins;

        // Target rotated to -25 degrees
        let target_angle_deg = -25.0f32;
        let target_angle_rad = target_angle_deg * PI / 180.0;
        let delta_t = (config.mic_distance_m * target_angle_rad.sin()) / config.speed_of_sound_m_s;
        let bin_hz = config.sample_rate / config.n_fft as f32;

        let mut mic1 = vec![Complex32::default(); num_bins];
        let mut mic2 = vec![Complex32::default(); num_bins];

        for k in 20..100 {
            let freq = k as f32 * bin_hz;
            let phase = -2.0 * PI * freq * delta_t;
            mic1[k] = Complex32::from_polar(5.0, 0.2 * k as f32);
            mic2[k] = Complex32::from_polar(5.0, 0.2 * k as f32 + phase);
        }

        for _ in 0..30 {
            tracker.process_frame(&mic1, &mic2, 0.85);
        }

        let tracked = tracker.tracked_angle_deg();
        assert!(
            (tracked - target_angle_deg).abs() < 3.5,
            "Target at -25 deg should be tracked accurately, got {:.2} deg",
            tracked
        );
    }

    #[test]
    fn test_gcc_phat_freezes_during_speech_pause() {
        let config = DoaConfig::default();
        let mut tracker = GccPhatDoaTracker::new(config.clone());
        let num_bins = config.num_bins;

        // First establish lock on +20 degrees speech
        let target_angle_deg = 20.0f32;
        let target_angle_rad = target_angle_deg * PI / 180.0;
        let delta_t = (config.mic_distance_m * target_angle_rad.sin()) / config.speed_of_sound_m_s;
        let bin_hz = config.sample_rate / config.n_fft as f32;

        let mut mic1 = vec![Complex32::default(); num_bins];
        let mut mic2 = vec![Complex32::default(); num_bins];

        for k in 20..80 {
            let freq = k as f32 * bin_hz;
            let phase = -2.0 * PI * freq * delta_t;
            mic1[k] = Complex32::from_polar(4.0, 0.05 * k as f32);
            mic2[k] = Complex32::from_polar(4.0, 0.05 * k as f32 + phase);
        }

        for _ in 0..50 {
            tracker.process_frame(&mic1, &mic2, 0.8);
        }

        let locked_angle = tracker.tracked_angle_deg();
        assert!(
            (locked_angle - target_angle_deg).abs() < 3.0,
            "Expected convergence near 20 deg, got {:.2}",
            locked_angle
        );

        // Now speech pauses (SPP = 0.05), and uncorrelated white noise appears
        let mut noise1 = vec![Complex32::default(); num_bins];
        let mut noise2 = vec![Complex32::default(); num_bins];
        for k in 0..num_bins {
            noise1[k] = Complex32::new(1.0, 0.5);
            noise2[k] = Complex32::new(-0.8, 1.2);
        }

        for _ in 0..20 {
            tracker.process_frame(&noise1, &noise2, 0.05); // speech absent
        }

        // Tracked angle should remain frozen at locked position (within 0.2 deg)
        assert!(
            (tracker.tracked_angle_deg() - locked_angle).abs() < 0.25,
            "Tracked angle drifted during speech pause from {:.2} to {:.2}",
            locked_angle,
            tracker.tracked_angle_deg()
        );
    }

    #[test]
    fn test_kalman_kinematic_velocity_and_jitter_attenuation() {
        let config = DoaConfig {
            near_field_radius_m: 0.08,
            kalman_meas_var: 3.0,
            ..Default::default()
        };
        let mut tracker = GccPhatDoaTracker::new(config.clone());
        let num_bins = config.num_bins;
        let bin_hz = config.sample_rate / config.n_fft as f32;

        // Simulate helmet vibration: sinusoidal jitter at 15 Hz (+/- 5 degrees) superimposed on 10 deg true head turn
        let mut angles_tracked = Vec::new();
        for frame in 0..40 {
            let t = frame as f32 * 0.016;
            let jitter = 5.0 * (2.0 * PI * 15.0 * t).sin();
            let true_angle = 10.0 + jitter;
            let delta_t = (config.mic_distance_m * (true_angle * PI / 180.0).sin())
                / config.speed_of_sound_m_s;

            let mut mic1 = vec![Complex32::default(); num_bins];
            let mut mic2 = vec![Complex32::default(); num_bins];
            for k in 20..80 {
                let freq = k as f32 * bin_hz;
                let phase = -2.0 * PI * freq * delta_t;
                mic1[k] = Complex32::from_polar(4.0, 0.1 * k as f32);
                mic2[k] = Complex32::from_polar(4.0, 0.1 * k as f32 + phase);
            }

            let angle = tracker.process_frame(&mic1, &mic2, 0.9);
            angles_tracked.push(angle);
        }

        // The Kalman filter should significantly smooth out the 15 Hz jitter
        let last_10 = &angles_tracked[30..40];
        let max_val = last_10.iter().copied().fold(f32::NEG_INFINITY, f32::max);
        let min_val = last_10.iter().copied().fold(f32::INFINITY, f32::min);
        let peak_to_peak = max_val - min_val;

        // Raw jitter peak-to-peak is 10 deg (+/- 5 deg). Kalman should reduce peak-to-peak by > 40%
        assert!(
            peak_to_peak < 6.5,
            "Kalman filter did not sufficiently damp 15Hz helmet vibration: peak-to-peak was {:.2} deg",
            peak_to_peak
        );
        // Tracked angle should remain centered near 10 degrees
        let mean_angle = last_10.iter().copied().sum::<f32>() / 10.0;
        assert!((mean_angle - 10.0).abs() < 2.0);
    }
}
