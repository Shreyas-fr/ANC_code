//! Adaptive AR(1) Shaped Pink Comfort Noise Generator.
//!
//! Specifically modeled for armored combat vehicle (T-90 / BMP) and flight cockpit (ALH / Tejas)
//! acoustic environments where aggressive noise suppression creates an unnatural acoustic vacuum
//! or gating ear fatigue during speech pauses.
//!
//! Generates autoregressive AR(1) filtered pink noise matching the long-term estimated
//! background noise power spectral density (PSD) tilt (~1/f).
//!
//! Features:
//! - Strictly causal, zero heap allocations in inner audio loops.
//! - Fast 64-bit xorshift pseudo-random generator (1 clock cycle per bin).
//! - Dynamically adapts AR(1) pole rho to match background noise spectral tilt.
//! - Smooth temporal blending into and out of speech pauses (spp < 0.25).

use num_complex::Complex32;
use std::f32::consts::PI;

/// Configuration for Adaptive AR(1) Shaped Comfort Noise Generator.
#[derive(Debug, Clone)]
pub struct ComfortNoiseConfig {
    /// Number of STFT frequency bins (n_fft / 2 + 1)
    pub num_bins: usize,
    /// Sampling rate in Hz (default: 16000.0)
    pub sample_rate: f32,
    /// Target injection level in dBFS during speech pauses (default: -52.0 dBFS)
    pub target_level_dbfs: f32,
    /// Speech presence probability threshold below which comfort noise blends in (default: 0.25)
    pub spp_pause_threshold: f32,
    /// Adaptation rate for AR(1) pole rho (default: 0.05)
    pub tilt_adaptation_rate: f32,
}

impl Default for ComfortNoiseConfig {
    fn default() -> Self {
        Self {
            num_bins: 257,
            sample_rate: 16000.0,
            target_level_dbfs: -52.0,
            spp_pause_threshold: 0.25,
            tilt_adaptation_rate: 0.05,
        }
    }
}

/// Adaptive AR(1) Shaped Pink Comfort Noise Generator.
pub struct ComfortNoiseGenerator {
    config: ComfortNoiseConfig,
    /// Autoregressive AR(1) filter pole rho (in [0.60, 0.96], default: 0.88 for ~1/f tilt)
    ar1_pole: f32,
    /// Precomputed / adapted spectral shape envelope per bin [num_bins]
    psd_shape: Vec<f32>,
    /// Target amplitude scalar in linear units
    target_amplitude: f32,
    /// Smoothed speech pause state [0.0 = speech active, 1.0 = speech paused]
    smoothed_pause_state: f32,
    /// 64-bit xorshift PRNG state for ultra-fast, deterministic random phase generation
    prng_state: u64,
}

impl ComfortNoiseGenerator {
    /// Creates a new ComfortNoiseGenerator.
    pub fn new(config: ComfortNoiseConfig) -> Self {
        let num_bins = config.num_bins;
        let target_amplitude = 10.0f32.powf(config.target_level_dbfs / 20.0);
        let ar1_pole = 0.88f32; // Baseline 1/f pink tilt

        let mut gen = Self {
            config,
            ar1_pole,
            psd_shape: vec![1.0f32; num_bins],
            target_amplitude,
            smoothed_pause_state: 0.0,
            prng_state: 0x9E3779B97F4A7C15, // Golden ratio 64-bit seed
        };

        gen.recompute_psd_shape();
        gen
    }

    /// Resets PRNG seed and pause smoothing state.
    pub fn reset(&mut self) {
        self.ar1_pole = 0.88;
        self.smoothed_pause_state = 0.0;
        self.prng_state = 0x9E3779B97F4A7C15;
        self.recompute_psd_shape();
    }

    /// Returns the currently active AR(1) pole rho.
    #[inline]
    pub fn ar1_pole(&self) -> f32 {
        self.ar1_pole
    }

    /// Sets the target injection level in dBFS.
    pub fn set_target_level_dbfs(&mut self, dbfs: f32) {
        self.config.target_level_dbfs = dbfs;
        self.target_amplitude = 10.0f32.powf(dbfs / 20.0);
    }

    /// Fast 64-bit xorshift pseudo-random generator returning uniform float in [0, 1).
    #[inline(always)]
    fn next_f32(&mut self) -> f32 {
        let mut x = self.prng_state;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.prng_state = x;
        // Map 24 bits of mantissa to [0.0, 1.0)
        (x & 0x00FF_FFFF) as f32 / 16777216.0
    }

    /// Recomputes the AR(1) pink-noise spectral magnitude envelope across bins:
    /// S_AR1(f_k) = 1 / |1 - rho * e^{-j 2 pi f_k / f_s}|^2
    /// Shape(k) = sqrt(S_AR1(f_k)), normalized to unit RMS.
    fn recompute_psd_shape(&mut self) {
        let num_bins = self.config.num_bins;
        let rho = self.ar1_pole;
        let rho_sqr = rho * rho;
        let n_fft = (num_bins - 1) * 2;
        let bin_hz = self.config.sample_rate / n_fft as f32;

        let mut sum_sqr = 0.0f32;

        for k in 0..num_bins {
            let freq = k as f32 * bin_hz;
            let omega = 2.0 * PI * freq / self.config.sample_rate;
            // |1 - rho * e^{-j omega}|^2 = 1 - 2*rho*cos(omega) + rho^2
            let denom = (1.0 - 2.0 * rho * omega.cos() + rho_sqr).max(1e-6);
            let mag = (1.0 / denom).sqrt();
            self.psd_shape[k] = mag;
            sum_sqr += mag * mag;
        }

        // Normalize so mean power across bins is 1.0
        let rms = (sum_sqr / num_bins.max(1) as f32).sqrt().max(1e-6);
        let inv_rms = 1.0 / rms;
        for s in &mut self.psd_shape {
            *s *= inv_rms;
        }
    }

    /// Dynamically estimates the spectral tilt from long-term background noise PSD
    /// and adapts the AR(1) pole rho.
    pub fn adapt_to_noise_psd(&mut self, noise_psd: &[f32]) {
        if noise_psd.len() < self.config.num_bins {
            return;
        }

        let num_bins = self.config.num_bins;
        let mut r0 = 0.0f32;
        let mut r1 = 0.0f32;

        // Estimate lag-0 and lag-1 autocorrelation from PSD via Wiener-Khinchin theorem:
        // r[m] = sum_{k=0}^{K-1} P_N[k] * cos(pi * k * m / (K - 1))
        let k_max = (num_bins - 1) as f32;
        for k in 0..num_bins {
            let pwr = noise_psd[k].max(1e-9);
            let angle = PI * k as f32 / k_max;
            r0 += pwr;
            r1 += pwr * angle.cos();
        }

        if r0 > 1e-12 {
            let rho_raw = (r1 / r0).clamp(0.60, 0.96);
            let alpha = self.config.tilt_adaptation_rate;
            self.ar1_pole = (1.0 - alpha) * self.ar1_pole + alpha * rho_raw;
            self.recompute_psd_shape();
        }
    }

    /// Injects shaped comfort noise into the enhanced STFT frame during speech pauses.
    ///
    /// - `spec`: STFT complex spectrum frame to be modified in-place.
    /// - `spp`: Per-bin Speech Presence Probability [num_bins].
    /// - `noise_floor_ref`: Background noise PSD estimate [num_bins].
    pub fn inject_frame(
        &mut self,
        spec: &mut [Complex32],
        spp: &[f32],
        noise_floor_ref: &[f32],
    ) {
        assert_eq!(spec.len(), self.config.num_bins);
        assert_eq!(spp.len(), self.config.num_bins);

        // 1. Calculate frame-averaged Speech Presence Probability
        let mean_spp = spp.iter().copied().sum::<f32>() / spp.len().max(1) as f32;

        // 2. Smoothly update pause state (alpha = 0.85 -> ~30 ms time constant @ 256-sample hop)
        let target_pause = if mean_spp < self.config.spp_pause_threshold {
            1.0f32
        } else {
            0.0f32
        };
        self.smoothed_pause_state = 0.85 * self.smoothed_pause_state + 0.15 * target_pause;

        // 3. Blend factor beta: ramp smoothly from 0.0 to 1.0
        let blend_beta = ((self.smoothed_pause_state - 0.20) / 0.60).clamp(0.0, 1.0);
        if blend_beta <= 1e-4 {
            return; // In active speech: zero comfort noise injection
        }

        // 4. Inject shaped AR(1) pink comfort noise with random phase
        let base_amp = self.target_amplitude * blend_beta;

        for k in 0..self.config.num_bins {
            // Local noise floor scaling: don't inject louder than ambient background
            let floor_ref = noise_floor_ref.get(k).copied().unwrap_or(1e-4).sqrt();
            let bin_amp = (base_amp * self.psd_shape[k]).min(floor_ref * 0.50);

            // Fast random phase in [0, 2*pi)
            let phase = self.next_f32() * 2.0 * PI;
            let cng_sample = Complex32::from_polar(bin_amp, phase);

            spec[k] += cng_sample;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_comfort_noise_pink_tilt() {
        let config = ComfortNoiseConfig {
            num_bins: 65,
            sample_rate: 16000.0,
            target_level_dbfs: -45.0,
            ..Default::default()
        };
        let gen = ComfortNoiseGenerator::new(config);

        // The AR(1) pink-noise shape must have significantly higher energy at low frequencies (rumble)
        // than at high frequencies (air hiss)
        let low_bin_shape = gen.psd_shape[2]; // ~250 Hz
        let mid_bin_shape = gen.psd_shape[16]; // ~2000 Hz
        let high_bin_shape = gen.psd_shape[60]; // ~7500 Hz

        assert!(
            low_bin_shape > mid_bin_shape,
            "Low bin shape ({}) must exceed mid bin shape ({})",
            low_bin_shape,
            mid_bin_shape
        );
        assert!(
            mid_bin_shape > high_bin_shape,
            "Mid bin shape ({}) must exceed high bin shape ({})",
            mid_bin_shape,
            high_bin_shape
        );

        // Verify tilt ratio: low should be > 2x high
        assert!(
            low_bin_shape > 2.0 * high_bin_shape,
            "Pink tilt must exhibit at least 6 dB drop across spectrum"
        );
    }

    #[test]
    fn test_comfort_noise_pause_gating() {
        let config = ComfortNoiseConfig {
            num_bins: 65,
            sample_rate: 16000.0,
            target_level_dbfs: -40.0,
            ..Default::default()
        };
        let mut gen = ComfortNoiseGenerator::new(config);

        let noise_floor = vec![1e-2f32; 65];

        // 1. In speech-active frames (spp = 1.0): spec must not be injected
        let spp_active = vec![1.0f32; 65];
        let mut spec_active = vec![Complex32::default(); 65];
        for _ in 0..10 {
            gen.inject_frame(&mut spec_active, &spp_active, &noise_floor);
        }
        let energy_active: f32 = spec_active.iter().map(|c| c.norm_sqr()).sum();
        assert_eq!(energy_active, 0.0, "Active speech must receive zero comfort noise");

        // 2. In speech pauses (spp = 0.0): comfort noise must smoothly blend in
        let spp_pause = vec![0.0f32; 65];
        let mut spec_pause = vec![Complex32::default(); 65];
        for _ in 0..25 {
            spec_pause.fill(Complex32::default());
            gen.inject_frame(&mut spec_pause, &spp_pause, &noise_floor);
        }
        let energy_pause: f32 = spec_pause.iter().map(|c| c.norm_sqr()).sum();
        assert!(
            energy_pause > 1e-7,
            "Speech pause must receive comfort noise injection, got {}",
            energy_pause
        );
    }

    #[test]
    fn test_comfort_noise_adaptation_to_noise_tilt() {
        let config = ComfortNoiseConfig {
            num_bins: 65,
            sample_rate: 16000.0,
            tilt_adaptation_rate: 0.20,
            ..Default::default()
        };
        let mut gen = ComfortNoiseGenerator::new(config);

        // Create heavy low-frequency noise PSD (steep 1/f^2 slope)
        let mut low_heavy_psd = vec![0.0f32; 65];
        for k in 0..65 {
            low_heavy_psd[k] = 1.0 / ((k as f32 + 1.0).powi(2));
        }

        let initial_pole = gen.ar1_pole();
        for _ in 0..20 {
            gen.adapt_to_noise_psd(&low_heavy_psd);
        }
        let adapted_pole = gen.ar1_pole();

        // Pole should adapt towards higher value (steeper low-frequency tilt)
        assert!(
            adapted_pole >= initial_pole,
            "Adapted pole ({}) should be >= initial ({}) on heavy rumble",
            adapted_pole,
            initial_pole
        );
    }
}
