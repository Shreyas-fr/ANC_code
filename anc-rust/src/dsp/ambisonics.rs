//! First-Order 2D/3D B-Format Ambisonics Tactical Spatializer.
//!
//! Developed for SIH 26052 Tactical Military Audio Systems.
//!
//! Tactical situational awareness requires distinguishing localized point sources
//! (sniper gunshot, drone propeller, directional radio operator) from diffuse
//! ambient sound fields (artillery rumble, rain, wind turbulence, cockpit roar).
//!
//! This module provides:
//! 1. Real-time 1st-Order B-Format Encoding (W, X, Y, Z channels):
//!    - W: 0th-order omnidirectional pressure monopole (1/sqrt(2) normalized).
//!    - X: 1st-order front-back directional gradient dipole (cos(theta)*cos(phi)).
//!    - Y: 1st-order left-right directional gradient dipole (sin(theta)*cos(phi)).
//!    - Z: 1st-order vertical up-down directional gradient dipole (sin(phi)).
//! 2. Active Acoustic Intensity Vector I(t) & Diffuseness psi(t):
//!    - Directional acoustic intensity: I = sqrt(2) * W * [X, Y, Z]^T
//!    - Acoustic energy density: E = W^2 + 0.5 * (X^2 + Y^2 + Z^2)
//!    - Diffuseness parameter: psi = 1.0 - ||I|| / (E + eps) in [0.0, 1.0]
//!      - psi -> 0.0: Localized single point source (e.g. sniper, drone)
//!      - psi -> 1.0: Diffuse ambient sound field (e.g. artillery rumble, rain)
//! 3. Binaural Spatial Audio Decoding with Exact Energy Conservation:
//!    - Virtual ear capsules at +/- theta_ear (e.g. +/- 90 degrees for headphones).
//!    - Energy conservation constraint: ||L||^2 + ||R||^2 = ||B-Format||^2,
//!      guaranteeing consistent loudness without gain pumping across spatial transitions.
//! 4. Strictly ZERO heap allocations in the streaming loop.

use serde::{Deserialize, Serialize};

/// Maximum supported block size for pre-allocated scratch buffers.
pub const AMBISONICS_MAX_BLOCK_SIZE: usize = 1024;
/// Speed of sound in dry air at 20°C in m/s.
pub const SPEED_OF_SOUND_M_S: f32 = 343.0;

/// Configuration for the Ambisonics Tactical Spatializer.
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct AmbisonicsConfig {
    pub sample_rate: f32,
    /// Ear angle in degrees for binaural virtual capsules (default: 90.0°).
    pub ear_angle_deg: f32,
    /// Smoothing coefficient for diffuseness and intensity vector (default: 0.85).
    pub smoothing_factor: f32,
    /// Enable binaural spatial decoding.
    pub enable_binaural: bool,
    /// Master bypass toggle.
    pub enabled: bool,
}

impl Default for AmbisonicsConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000.0,
            ear_angle_deg: 90.0,
            smoothing_factor: 0.85,
            enable_binaural: true,
            enabled: true,
        }
    }
}

/// Real-time telemetry produced by the Ambisonics Spatializer.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct AmbisonicsTelemetry {
    pub intensity_x: f32,
    pub intensity_y: f32,
    pub intensity_z: f32,
    pub intensity_mag: f32,
    pub energy_density: f32,
    pub diffuseness: f32,
    pub azimuth_deg: f32,
    pub elevation_deg: f32,
    pub is_localized: bool,
}

impl Default for AmbisonicsTelemetry {
    fn default() -> Self {
        Self {
            intensity_x: 0.0,
            intensity_y: 0.0,
            intensity_z: 0.0,
            intensity_mag: 0.0,
            energy_density: 0.0,
            diffuseness: 0.0,
            azimuth_deg: 0.0,
            elevation_deg: 0.0,
            is_localized: false,
        }
    }
}

/// First-Order 2D/3D Ambisonics Spatializer and Intensity Analyzer.
#[derive(Debug, Clone)]
pub struct AmbisonicsSpatializer {
    config: AmbisonicsConfig,
    /// Pre-allocated scratch buffers for B-format channels
    w_buf: [f32; AMBISONICS_MAX_BLOCK_SIZE],
    x_buf: [f32; AMBISONICS_MAX_BLOCK_SIZE],
    y_buf: [f32; AMBISONICS_MAX_BLOCK_SIZE],
    z_buf: [f32; AMBISONICS_MAX_BLOCK_SIZE],
    /// Smoothed intensity vector components
    smooth_ix: f32,
    smooth_iy: f32,
    smooth_iz: f32,
    smooth_energy: f32,
    smooth_diffuseness: f32,
    /// Last telemetry snapshot
    last_telemetry: AmbisonicsTelemetry,
}

impl AmbisonicsSpatializer {
    /// Creates a new AmbisonicsSpatializer instance.
    pub fn new(config: AmbisonicsConfig) -> Self {
        Self {
            config,
            w_buf: [0.0; AMBISONICS_MAX_BLOCK_SIZE],
            x_buf: [0.0; AMBISONICS_MAX_BLOCK_SIZE],
            y_buf: [0.0; AMBISONICS_MAX_BLOCK_SIZE],
            z_buf: [0.0; AMBISONICS_MAX_BLOCK_SIZE],
            smooth_ix: 0.0,
            smooth_iy: 0.0,
            smooth_iz: 0.0,
            smooth_energy: 0.0,
            smooth_diffuseness: 0.0,
            last_telemetry: AmbisonicsTelemetry::default(),
        }
    }

    /// Resets all internal buffers and temporal filters.
    pub fn reset(&mut self) {
        self.w_buf.fill(0.0);
        self.x_buf.fill(0.0);
        self.y_buf.fill(0.0);
        self.z_buf.fill(0.0);
        self.smooth_ix = 0.0;
        self.smooth_iy = 0.0;
        self.smooth_iz = 0.0;
        self.smooth_energy = 0.0;
        self.smooth_diffuseness = 0.0;
        self.last_telemetry = AmbisonicsTelemetry::default();
    }

    /// Sets whether Ambisonics processing is enabled.
    pub fn set_enabled(&mut self, enabled: bool) {
        self.config.enabled = enabled;
    }

    /// Returns latest telemetry.
    pub fn telemetry(&self) -> AmbisonicsTelemetry {
        self.last_telemetry
    }

    /// Encodes a mono source signal into 1st-order B-format with specified azimuth and elevation angles.
    ///
    /// - `azimuth_deg`: -180.0 to +180.0 degrees (0° = front, +90° = left, -90° = right)
    /// - `elevation_deg`: -90.0 to +90.0 degrees (0° = horizontal, +90° = zenith)
    pub fn encode_point_source(
        mono: &[f32],
        azimuth_deg: f32,
        elevation_deg: f32,
        w: &mut [f32],
        x: &mut [f32],
        y: &mut [f32],
        z: &mut [f32],
    ) {
        let n = mono
            .len()
            .min(w.len())
            .min(x.len())
            .min(y.len())
            .min(z.len())
            .min(AMBISONICS_MAX_BLOCK_SIZE);

        let az_rad = azimuth_deg.to_radians();
        let el_rad = elevation_deg.to_radians();

        let w_gain = std::f32::consts::FRAC_1_SQRT_2; // 1 / sqrt(2)
        let cos_el = el_rad.cos();
        let sin_el = el_rad.sin();
        let x_gain = az_rad.cos() * cos_el;
        let y_gain = az_rad.sin() * cos_el;
        let z_gain = sin_el;

        for i in 0..n {
            let s = mono[i];
            w[i] = s * w_gain;
            x[i] = s * x_gain;
            y[i] = s * y_gain;
            z[i] = s * z_gain;
        }
    }

    /// Encodes a dual-mic tactical array (M1, M2) into 1st-order B-format.
    ///
    /// M1 = forward / left mic, M2 = rear / right mic.
    pub fn encode_dual_mic(
        mic1: &[f32],
        mic2: &[f32],
        w: &mut [f32],
        x: &mut [f32],
        y: &mut [f32],
    ) {
        let n = mic1
            .len()
            .min(mic2.len())
            .min(w.len())
            .min(x.len())
            .min(y.len())
            .min(AMBISONICS_MAX_BLOCK_SIZE);
        let w_gain = std::f32::consts::FRAC_1_SQRT_2;

        for i in 0..n {
            let m1 = mic1[i];
            let m2 = mic2[i];
            // Monopole pressure: sum
            w[i] = (m1 + m2) * 0.5 * w_gain;
            // Dipole front-back gradient: difference
            x[i] = (m1 - m2) * 0.5;
            // Dipole lateral gradient (estimated from quadrature / cross-component)
            y[i] = (m1 - m2) * 0.5 * std::f32::consts::FRAC_1_SQRT_2;
        }
    }

    /// Computes instantaneous intensity and energy averages from B-format frames.
    pub fn compute_frame_intensity(
        w: &[f32],
        x: &[f32],
        y: &[f32],
        z: &[f32],
    ) -> (f32, f32, f32, f32) {
        let n = w.len().min(x.len()).min(y.len()).min(z.len());
        if n == 0 {
            return (0.0, 0.0, 0.0, 0.0);
        }

        let mut sum_ix = 0.0f32;
        let mut sum_iy = 0.0f32;
        let mut sum_iz = 0.0f32;
        let mut sum_e = 0.0f32;

        let sqrt2 = std::f32::consts::SQRT_2;
        for i in 0..n {
            let wi = w[i];
            let xi = x[i];
            let yi = y[i];
            let zi = z[i];

            // Instantaneous acoustic intensity: I = sqrt(2) * W * [X, Y, Z]^T
            sum_ix += sqrt2 * wi * xi;
            sum_iy += sqrt2 * wi * yi;
            sum_iz += sqrt2 * wi * zi;

            // Instantaneous acoustic energy: E = W^2 + 0.5 * (X^2 + Y^2 + Z^2)
            sum_e += wi * wi + 0.5 * (xi * xi + yi * yi + zi * zi);
        }

        let inv_n = 1.0 / n as f32;
        (
            sum_ix * inv_n,
            sum_iy * inv_n,
            sum_iz * inv_n,
            (sum_e * inv_n).max(1e-9),
        )
    }

    /// Updates smoothed intensity vector and diffuseness.
    pub fn update_smoothed_intensity(
        &mut self,
        frame_ix: f32,
        frame_iy: f32,
        frame_iz: f32,
        frame_e: f32,
    ) -> AmbisonicsTelemetry {
        let alpha = self.config.smoothing_factor.clamp(0.0, 0.99);
        self.smooth_ix = alpha * self.smooth_ix + (1.0 - alpha) * frame_ix;
        self.smooth_iy = alpha * self.smooth_iy + (1.0 - alpha) * frame_iy;
        self.smooth_iz = alpha * self.smooth_iz + (1.0 - alpha) * frame_iz;
        self.smooth_energy = alpha * self.smooth_energy + (1.0 - alpha) * frame_e;

        let intensity_mag = (self.smooth_ix * self.smooth_ix
            + self.smooth_iy * self.smooth_iy
            + self.smooth_iz * self.smooth_iz)
            .sqrt();

        // Diffuseness: psi = 1.0 - ||I|| / (E + eps)
        let raw_diffuseness = (1.0 - (intensity_mag / self.smooth_energy)).clamp(0.0, 1.0);
        self.smooth_diffuseness = alpha * self.smooth_diffuseness + (1.0 - alpha) * raw_diffuseness;

        // Azimuth and Elevation
        let az_deg = self.smooth_iy.atan2(self.smooth_ix).to_degrees();
        let horiz_mag = (self.smooth_ix * self.smooth_ix + self.smooth_iy * self.smooth_iy).sqrt();
        let el_deg = self.smooth_iz.atan2(horiz_mag.max(1e-9)).to_degrees();

        let is_localized = self.smooth_diffuseness < 0.35 && intensity_mag > 1e-6;

        self.last_telemetry = AmbisonicsTelemetry {
            intensity_x: self.smooth_ix,
            intensity_y: self.smooth_iy,
            intensity_z: self.smooth_iz,
            intensity_mag,
            energy_density: self.smooth_energy,
            diffuseness: self.smooth_diffuseness,
            azimuth_deg: az_deg,
            elevation_deg: el_deg,
            is_localized,
        };

        self.last_telemetry
    }

    /// Computes directional acoustic intensity vector I(t) and diffuseness psi(t)
    /// across the current B-format frame.
    pub fn analyze_intensity(
        &mut self,
        w: &[f32],
        x: &[f32],
        y: &[f32],
        z: &[f32],
    ) -> AmbisonicsTelemetry {
        let (ix, iy, iz, e) = Self::compute_frame_intensity(w, x, y, z);
        self.update_smoothed_intensity(ix, iy, iz, e)
    }

    /// Decodes 1st-order B-format (W, X, Y) to stereo binaural audio with energy conservation.
    ///
    /// Preserves exact total energy: ||L||^2 + ||R||^2 = ||B-Format||^2.
    pub fn decode_binaural_energy_conserved(
        &self,
        w: &[f32],
        x: &[f32],
        y: &[f32],
        out_left: &mut [f32],
        out_right: &mut [f32],
    ) {
        let n = w
            .len()
            .min(x.len())
            .min(y.len())
            .min(out_left.len())
            .min(out_right.len());
        if n == 0 {
            return;
        }

        let ear_rad = self.config.ear_angle_deg.to_radians();
        let cos_ear = ear_rad.cos();
        let sin_ear = ear_rad.sin();
        let w_gain = std::f32::consts::FRAC_1_SQRT_2;

        let mut e_bformat = 0.0f32;
        let mut e_binaural_raw = 0.0f32;

        // 1. Raw virtual capsule synthesis
        for i in 0..n {
            let wi = w[i];
            let xi = x[i];
            let yi = y[i];

            // B-format total energy: W^2 + 0.5 * (X^2 + Y^2)
            e_bformat += wi * wi + 0.5 * (xi * xi + yi * yi);

            // Left ear capsule: oriented at +ear_angle
            let l_raw = wi * w_gain + 0.5 * (xi * cos_ear + yi * sin_ear);
            // Right ear capsule: oriented at -ear_angle (cos(-th)=cos(th), sin(-th)=-sin(th))
            let r_raw = wi * w_gain + 0.5 * (xi * cos_ear - yi * sin_ear);

            out_left[i] = l_raw;
            out_right[i] = r_raw;
            e_binaural_raw += l_raw * l_raw + r_raw * r_raw;
        }

        // 2. Strict energy conservation: scale output so ||L||^2 + ||R||^2 == ||B-Format||^2
        let scale = if e_binaural_raw > 1e-12 && e_bformat > 1e-12 {
            (e_bformat / e_binaural_raw).sqrt()
        } else {
            1.0
        };

        for i in 0..n {
            out_left[i] *= scale;
            out_right[i] *= scale;
        }
    }

    /// Full end-to-end processing: encodes dual microphone inputs or point source,
    /// measures acoustic intensity & diffuseness, and renders binaural stereo.
    pub fn process_tactical_spatial(
        &mut self,
        mic1: &[f32],
        mic2: &[f32],
        target_azimuth_deg: Option<f32>,
        out_left: &mut [f32],
        out_right: &mut [f32],
    ) -> AmbisonicsTelemetry {
        let n = mic1
            .len()
            .min(mic2.len())
            .min(out_left.len())
            .min(out_right.len())
            .min(AMBISONICS_MAX_BLOCK_SIZE);

        if !self.config.enabled || n == 0 {
            // Bypass: direct stereo pass-through
            out_left[..n].copy_from_slice(&mic1[..n]);
            out_right[..n].copy_from_slice(&mic2[..n]);
            return self.last_telemetry;
        }

        if let Some(azimuth) = target_azimuth_deg {
            // Encode target point source from mic1
            Self::encode_point_source(
                &mic1[..n],
                azimuth,
                0.0,
                &mut self.w_buf[..n],
                &mut self.x_buf[..n],
                &mut self.y_buf[..n],
                &mut self.z_buf[..n],
            );
        } else {
            // Encode dual-mic differential field
            Self::encode_dual_mic(
                &mic1[..n],
                &mic2[..n],
                &mut self.w_buf[..n],
                &mut self.x_buf[..n],
                &mut self.y_buf[..n],
            );
            self.z_buf[..n].fill(0.0);
        }

        // Analyze intensity and diffuseness
        let (ix, iy, iz, e) = Self::compute_frame_intensity(
            &self.w_buf[..n],
            &self.x_buf[..n],
            &self.y_buf[..n],
            &self.z_buf[..n],
        );
        let telem = self.update_smoothed_intensity(ix, iy, iz, e);

        // Decode to binaural stereo headphones with energy conservation
        self.decode_binaural_energy_conserved(
            &self.w_buf[..n],
            &self.x_buf[..n],
            &self.y_buf[..n],
            &mut out_left[..n],
            &mut out_right[..n],
        );

        telem
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ambisonics_point_source_encoding_orthogonality() {
        let input = vec![1.0f32; 128];
        let mut w = vec![0.0f32; 128];
        let mut x = vec![0.0f32; 128];
        let mut y = vec![0.0f32; 128];
        let mut z = vec![0.0f32; 128];

        // Encode point source at 0 degrees (pure front)
        AmbisonicsSpatializer::encode_point_source(
            &input, 0.0, 0.0, &mut w, &mut x, &mut y, &mut z,
        );
        assert!((w[0] - std::f32::consts::FRAC_1_SQRT_2).abs() < 1e-5);
        assert!((x[0] - 1.0).abs() < 1e-5);
        assert!(y[0].abs() < 1e-5);
        assert!(z[0].abs() < 1e-5);

        // Encode point source at +90 degrees (pure left)
        AmbisonicsSpatializer::encode_point_source(
            &input, 90.0, 0.0, &mut w, &mut x, &mut y, &mut z,
        );
        assert!((w[0] - std::f32::consts::FRAC_1_SQRT_2).abs() < 1e-5);
        assert!(x[0].abs() < 1e-5);
        assert!((y[0] - 1.0).abs() < 1e-5);
        assert!(z[0].abs() < 1e-5);
    }

    #[test]
    fn test_ambisonics_point_source_diffuseness_near_zero() {
        let config = AmbisonicsConfig {
            smoothing_factor: 0.0, // Instantaneous measurement
            ..Default::default()
        };
        let mut spat = AmbisonicsSpatializer::new(config);

        let input: Vec<f32> = (0..256).map(|i| (i as f32 * 0.1).sin()).collect();
        let mut w = vec![0.0f32; 256];
        let mut x = vec![0.0f32; 256];
        let mut y = vec![0.0f32; 256];
        let mut z = vec![0.0f32; 256];

        // 45 degrees azimuth
        AmbisonicsSpatializer::encode_point_source(
            &input, 45.0, 0.0, &mut w, &mut x, &mut y, &mut z,
        );
        let telem = spat.analyze_intensity(&w, &x, &y, &z);

        // A single point source must have low diffuseness (< 0.15) and correct angle (~45°)
        assert!(
            telem.diffuseness < 0.15,
            "Point source diffuseness must be near 0, got {}",
            telem.diffuseness
        );
        assert!(
            (telem.azimuth_deg - 45.0).abs() < 1.0,
            "Azimuth should be ~45 deg, got {}",
            telem.azimuth_deg
        );
        assert!(telem.is_localized);
    }

    #[test]
    fn test_ambisonics_diffuse_field_diffuseness_near_one() {
        let config = AmbisonicsConfig {
            smoothing_factor: 0.0,
            ..Default::default()
        };
        let mut spat = AmbisonicsSpatializer::new(config);

        // In an isotropic diffuse field, omni W has energy, but orthogonal gradient dipoles
        // average to zero net intensity vector (cancel out)
        let w: Vec<f32> = (0..512).map(|i| (i as f32 * 0.2).sin()).collect();
        let x = vec![0.0f32; 512]; // No net front-back flow
        let y = vec![0.0f32; 512]; // No net lateral flow
        let z = vec![0.0f32; 512];

        let telem = spat.analyze_intensity(&w, &x, &y, &z);
        // Intensity magnitude is 0, while energy is positive -> diffuseness = 1.0
        assert!(
            telem.diffuseness > 0.95,
            "Diffuse field must have diffuseness near 1.0, got {}",
            telem.diffuseness
        );
        assert!(!telem.is_localized);
    }

    #[test]
    fn test_ambisonics_binaural_energy_conservation() {
        let config = AmbisonicsConfig::default();
        let spat = AmbisonicsSpatializer::new(config);

        let input: Vec<f32> = (0..256).map(|i| (i as f32 * 0.05).sin()).collect();
        let mut w = vec![0.0f32; 256];
        let mut x = vec![0.0f32; 256];
        let mut y = vec![0.0f32; 256];
        let mut z = vec![0.0f32; 256];
        let mut left = vec![0.0f32; 256];
        let mut right = vec![0.0f32; 256];

        for &angle in &[0.0, 30.0, 60.0, 90.0, 135.0, 180.0, -90.0] {
            AmbisonicsSpatializer::encode_point_source(
                &input, angle, 0.0, &mut w, &mut x, &mut y, &mut z,
            );

            let e_bformat: f32 = w
                .iter()
                .zip(x.iter())
                .zip(y.iter())
                .map(|((&wi, &xi), &yi)| wi * wi + 0.5 * (xi * xi + yi * yi))
                .sum();

            spat.decode_binaural_energy_conserved(&w, &x, &y, &mut left, &mut right);

            let e_binaural: f32 = left
                .iter()
                .zip(right.iter())
                .map(|(&l, &r)| l * l + r * r)
                .sum();

            let diff = (e_binaural - e_bformat).abs() / e_bformat;
            assert!(
                diff < 1e-4,
                "Binaural energy must match B-format energy within 0.01% at angle {}: bformat={}, binaural={}",
                angle,
                e_bformat,
                e_binaural
            );
        }
    }

    #[test]
    fn test_ambisonics_dual_mic_process_pipeline() {
        let config = AmbisonicsConfig::default();
        let mut spat = AmbisonicsSpatializer::new(config);

        let mic1 = vec![0.1f32; 256];
        let mic2 = vec![0.05f32; 256];
        let mut left = vec![0.0f32; 256];
        let mut right = vec![0.0f32; 256];

        let telem = spat.process_tactical_spatial(&mic1, &mic2, None, &mut left, &mut right);
        assert!(telem.energy_density > 0.0);
        assert_eq!(left.len(), 256);
        assert_eq!(right.len(), 256);
    }

    #[test]
    fn test_ambisonics_reset() {
        let config = AmbisonicsConfig::default();
        let mut spat = AmbisonicsSpatializer::new(config);

        let mic1 = vec![0.5f32; 128];
        let mic2 = vec![0.2f32; 128];
        let mut l = vec![0.0f32; 128];
        let mut r = vec![0.0f32; 128];
        spat.process_tactical_spatial(&mic1, &mic2, Some(60.0), &mut l, &mut r);

        spat.reset();
        assert_eq!(spat.telemetry(), AmbisonicsTelemetry::default());
    }
}
