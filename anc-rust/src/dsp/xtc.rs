//! Binaural Transaural Cross-Talk Cancellation (XTC) & 3D Spatial Audio Positioning.
//!
//! Provides:
//! 1. Headphone transaural cross-talk cancellation filter with delay-and-attenuation
//!    head shadow inversion (Atal-Schroeder physical model).
//! 2. 3D Spatial Audio Positioning (Woodworth spherical head model for ITD & ILD)
//!    allowing tactical operators to perceive acoustic separation between:
//!    - Intercom talker (anchored in front / center)
//!    - Ambient transparency (wide lateral soundstage)
//!    - Directional threat alerts (e.g. sniper crack, approaching drone at target azimuth)
//! 3. Strictly ZERO heap allocations in real-time streaming methods.

use std::f32::consts::PI;

/// Configuration for Transaural Cross-Talk Cancellation and 3D positioning.
#[derive(Debug, Clone)]
pub struct XtcConfig {
    /// Sample rate in Hz (default: 16000.0)
    pub sample_rate: f32,
    /// Head radius in meters (default: 0.0875 m = 8.75 cm, Woodworth standard)
    pub head_radius_m: f32,
    /// Speed of sound in m/s (default: 343.0 m/s)
    pub speed_of_sound_m_s: f32,
    /// Cross-talk cancellation coupling gain (0.0 to 0.70, default: 0.38)
    pub cancellation_gain: f32,
    /// Head shadow diffraction filter cutoff in Hz (default: 1800.0 Hz)
    pub head_shadow_cutoff_hz: f32,
    /// Master enable for XTC processing
    pub enabled: bool,
}

impl Default for XtcConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000.0,
            head_radius_m: 0.0875,
            speed_of_sound_m_s: 343.0,
            cancellation_gain: 0.38,
            head_shadow_cutoff_hz: 1800.0,
            enabled: true,
        }
    }
}

/// Zero-Allocation Transaural Cross-Talk Cancellation and 3D Spatial Positioning Engine.
pub struct TransauralXtc {
    pub config: XtcConfig,

    // Precomputed delay for contralateral cross-path in samples (~8 samples @ 16kHz)
    delay_samples: usize,
    // 1st-order IIR low-pass filter coefficient for head shadow diffraction: y[n] = a * y[n-1] + (1 - a) * x[n]
    shadow_alpha: f32,
    // Energy normalization factor: 1.0 / sqrt(1 + cancellation_gain^2)
    norm_factor: f32,

    // Circular delay buffers for left and right cross-talk cancellation (Zero Heap Allocation)
    delay_buf_l: [f32; 64],
    delay_buf_r: [f32; 64],
    write_ptr_l: usize,
    write_ptr_r: usize,

    // 1st-order IIR filter state for shadow low-pass
    shadow_state_l: f32,
    shadow_state_r: f32,

    // Delay lines for 3D spatial positioning
    pos_delay_line: [f32; 128],
    pos_write_ptr: usize,
    pos_shadow_state: f32,
}

impl TransauralXtc {
    /// Creates a new TransauralXtc engine.
    pub fn new(config: XtcConfig) -> Self {
        let dt_cross = (2.0 * config.head_radius_m) / config.speed_of_sound_m_s;
        let delay_samples = ((dt_cross * config.sample_rate).round() as usize).clamp(1, 32);

        // 1st-order IIR filter pole: alpha = exp(-2 * pi * fc / fs)
        let wc = 2.0 * PI * config.head_shadow_cutoff_hz / config.sample_rate;
        let shadow_alpha = (-wc).exp().clamp(0.1, 0.95);
        let norm_factor = 1.0 / (1.0 + config.cancellation_gain * config.cancellation_gain).sqrt();

        Self {
            config,
            delay_samples,
            shadow_alpha,
            norm_factor,
            delay_buf_l: [0.0f32; 64],
            delay_buf_r: [0.0f32; 64],
            write_ptr_l: 0,
            write_ptr_r: 0,
            shadow_state_l: 0.0,
            shadow_state_r: 0.0,
            pos_delay_line: [0.0f32; 128],
            pos_write_ptr: 0,
            pos_shadow_state: 0.0,
        }
    }

    /// Resets all delay line histories and IIR states.
    pub fn reset(&mut self) {
        self.delay_buf_l.fill(0.0);
        self.delay_buf_r.fill(0.0);
        self.write_ptr_l = 0;
        self.write_ptr_r = 0;
        self.shadow_state_l = 0.0;
        self.shadow_state_r = 0.0;
        self.pos_delay_line.fill(0.0);
        self.pos_write_ptr = 0;
        self.pos_shadow_state = 0.0;
    }

    /// Enables or disables XTC cross-talk cancellation.
    pub fn set_enabled(&mut self, enabled: bool) {
        self.config.enabled = enabled;
    }

    /// Returns whether XTC cross-talk cancellation is active.
    pub fn is_enabled(&self) -> bool {
        self.config.enabled
    }

    /// Sets the cross-talk cancellation coupling gain [0.0, 0.70].
    pub fn set_cancellation_gain(&mut self, gain: f32) {
        self.config.cancellation_gain = gain.clamp(0.0, 0.70);
        self.norm_factor =
            1.0 / (1.0 + self.config.cancellation_gain * self.config.cancellation_gain).sqrt();
    }

    /// Processes separate left and right channel slices in-place with cross-talk cancellation.
    ///
    /// Zero heap allocations during execution.
    pub fn process_stereo(&mut self, left: &mut [f32], right: &mut [f32]) {
        assert_eq!(left.len(), right.len());
        if !self.config.enabled {
            return;
        }

        let n = left.len();
        let c_gain = self.config.cancellation_gain;
        let d = self.delay_samples;
        let alpha = self.shadow_alpha;
        let beta = 1.0 - alpha;
        let norm = self.norm_factor;

        for i in 0..n {
            let l_in = left[i];
            let r_in = right[i];

            // Write to circular buffers
            self.delay_buf_l[self.write_ptr_l] = l_in;
            self.delay_buf_r[self.write_ptr_r] = r_in;

            // Read delayed contralateral samples
            let read_ptr_l = (self.write_ptr_l + 64 - d) % 64;
            let read_ptr_r = (self.write_ptr_r + 64 - d) % 64;

            let l_delayed = self.delay_buf_l[read_ptr_l];
            let r_delayed = self.delay_buf_r[read_ptr_r];

            // Apply 1st-order head shadow low-pass filter to delayed cross-path
            self.shadow_state_r = alpha * self.shadow_state_r + beta * r_delayed;
            self.shadow_state_l = alpha * self.shadow_state_l + beta * l_delayed;

            // Cross-talk cancellation:
            // L_out = (L_in - c * Shadow(R_delayed)) * norm
            // R_out = (R_in - c * Shadow(L_delayed)) * norm
            let l_out = (l_in - c_gain * self.shadow_state_r) * norm;
            let r_out = (r_in - c_gain * self.shadow_state_l) * norm;

            left[i] = l_out;
            right[i] = r_out;

            self.write_ptr_l = (self.write_ptr_l + 1) % 64;
            self.write_ptr_r = (self.write_ptr_r + 1) % 64;
        }
    }

    /// Processes interleaved stereo audio [L, R, L, R, ...] in-place.
    ///
    /// Zero heap allocations during execution.
    pub fn process_interleaved(&mut self, stereo: &mut [f32]) {
        if !self.config.enabled {
            return;
        }
        assert_eq!(stereo.len() % 2, 0);
        let frames = stereo.len() / 2;

        let c_gain = self.config.cancellation_gain;
        let d = self.delay_samples;
        let alpha = self.shadow_alpha;
        let beta = 1.0 - alpha;
        let norm = self.norm_factor;

        for f in 0..frames {
            let idx = f * 2;
            let l_in = stereo[idx];
            let r_in = stereo[idx + 1];

            self.delay_buf_l[self.write_ptr_l] = l_in;
            self.delay_buf_r[self.write_ptr_r] = r_in;

            let read_ptr_l = (self.write_ptr_l + 64 - d) % 64;
            let read_ptr_r = (self.write_ptr_r + 64 - d) % 64;

            let l_delayed = self.delay_buf_l[read_ptr_l];
            let r_delayed = self.delay_buf_r[read_ptr_r];

            self.shadow_state_r = alpha * self.shadow_state_r + beta * r_delayed;
            self.shadow_state_l = alpha * self.shadow_state_l + beta * l_delayed;

            stereo[idx] = (l_in - c_gain * self.shadow_state_r) * norm;
            stereo[idx + 1] = (r_in - c_gain * self.shadow_state_l) * norm;

            self.write_ptr_l = (self.write_ptr_l + 1) % 64;
            self.write_ptr_r = (self.write_ptr_r + 1) % 64;
        }
    }

    /// Renders a mono source at a 3D tactical azimuth angle into interleaved stereo [L, R, L, R, ...].
    ///
    /// Uses Woodworth's spherical head acoustic model:
    /// - `azimuth_deg`: -180.0 to +180.0 degrees (0 = front, +90 = right, -90 = left)
    /// - Computes physical Interaural Time Difference (ITD) and Interaural Level Difference (ILD)
    /// - Applies contralateral head shadow low-pass filtering
    /// - Zero heap allocations during execution
    pub fn position_source_3d(
        &mut self,
        mono_in: &[f32],
        azimuth_deg: f32,
        stereo_out: &mut [f32],
    ) {
        let n = mono_in.len();
        assert!(stereo_out.len() >= n * 2);

        let az_rad = azimuth_deg.to_radians();
        let sin_az = az_rad.sin();
        let abs_az = az_rad.abs();

        // 1. Woodworth spherical head model for ITD (seconds):
        // dt = (a / c) * (sin|az| + |az|)
        let a = self.config.head_radius_m;
        let c = self.config.speed_of_sound_m_s;
        let dt_sec = (a / c) * (sin_az.abs() + abs_az);
        let itd_samples = ((dt_sec * self.config.sample_rate).round() as usize).clamp(0, 31);

        // 2. Interaural Level Difference (ILD) in dB:
        // Contralateral ear attenuated by up to 8 dB at 90 degrees
        let ild_db = 8.0 * sin_az.abs();
        let contra_gain = 10.0f32.powf(-ild_db / 20.0);
        let ipsi_gain = 1.0f32;

        // Shadow low-pass filter for contralateral ear
        let wc = 2.0 * PI * 2200.0 / self.config.sample_rate;
        let lp_alpha = (-wc).exp().clamp(0.1, 0.95);
        let lp_beta = 1.0 - lp_alpha;

        for (i, &s) in mono_in.iter().enumerate() {
            // Write to positioning delay line
            self.pos_delay_line[self.pos_write_ptr] = s;
            let read_ptr = (self.pos_write_ptr + 128 - itd_samples) % 128;
            let s_delayed = self.pos_delay_line[read_ptr];

            // Filter contralateral delayed path
            self.pos_shadow_state = lp_alpha * self.pos_shadow_state + lp_beta * s_delayed;
            let s_contra = self.pos_shadow_state * contra_gain;
            let s_ipsi = s * ipsi_gain;

            let (l_val, r_val) = if sin_az >= 0.0 {
                // Source is to the right: right ear is ipsi (direct), left ear is contra (delayed + shadowed)
                (s_contra, s_ipsi)
            } else {
                // Source is to the left: left ear is ipsi (direct), right ear is contra (delayed + shadowed)
                (s_ipsi, s_contra)
            };

            stereo_out[i * 2] = l_val;
            stereo_out[i * 2 + 1] = r_val;

            self.pos_write_ptr = (self.pos_write_ptr + 1) % 128;
        }

        // Apply Transaural XTC cross-talk cancellation to decouple the binaural image
        if self.config.enabled {
            self.process_interleaved(&mut stereo_out[..n * 2]);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_xtc_crosstalk_cancellation_separation() {
        let config = XtcConfig {
            sample_rate: 16000.0,
            head_radius_m: 0.0875,
            speed_of_sound_m_s: 343.0,
            cancellation_gain: 0.40,
            head_shadow_cutoff_hz: 1800.0,
            enabled: true,
        };
        let mut xtc = TransauralXtc::new(config);

        // Stereo signal with prominent left content and small right leak
        let mut left = vec![1.0f32; 64];
        let mut right = vec![0.35f32; 64]; // Simulated contralateral head leak

        xtc.process_stereo(&mut left, &mut right);

        // Contralateral leak in right channel must be attenuated by XTC inversion
        let mean_right: f32 = right[16..48].iter().map(|s| s.abs()).sum::<f32>() / 32.0;
        assert!(
            mean_right < 0.25,
            "Contralateral acoustic leak should be reduced by XTC, got {}",
            mean_right
        );
    }

    #[test]
    fn test_xtc_3d_spatial_positioning_woodworth() {
        let config = XtcConfig {
            sample_rate: 16000.0,
            enabled: false, // test pure positioning geometry
            ..Default::default()
        };
        let mut xtc = TransauralXtc::new(config);

        let mono = vec![1.0f32; 64];
        let mut stereo = vec![0.0f32; 128];

        // Position source at +90 degrees (far right)
        xtc.position_source_3d(&mono, 90.0, &mut stereo);

        // Right ear (ipsilateral) must have higher amplitude than left ear (contralateral)
        let mut right_pwr = 0.0f32;
        let mut left_pwr = 0.0f32;
        for i in 16..48 {
            left_pwr += stereo[i * 2] * stereo[i * 2];
            right_pwr += stereo[i * 2 + 1] * stereo[i * 2 + 1];
        }

        assert!(
            right_pwr > left_pwr * 1.5,
            "Source at +90 deg must be significantly louder on right ear, left_pwr={}, right_pwr={}",
            left_pwr,
            right_pwr
        );
    }
}
