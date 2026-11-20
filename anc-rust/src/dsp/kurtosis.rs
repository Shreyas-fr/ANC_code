//! Higher-Order Spectral Kurtosis (SK) and Non-Gaussian Shock Transient Detector.
//!
//! In combat acoustic environments, stationary background noise (diesel vehicle rumble,
//! rotor wash, wind hiss, thermal noise) exhibits Gaussian or near-Gaussian statistical
//! properties. Conversely, impulsive combat transients (sniper rifle muzzle detonations,
//! supersonic bullet shockwaves, blast concussions, shrapnel ricochets) exhibit extreme
//! non-Gaussian heavy-tailed distributions.
//!
//! Spectral Kurtosis (SK) computes the 4th-order cumulant of complex STFT spectral bins:
//!
//! $$K(f) = \frac{\langle |X(f, t)|^4 \rangle}{\langle |X(f, t)|^2 \rangle^2} - 2$$
//!
//! - Stationary Gaussian noise yields $K(f) \approx 0$.
//! - Persistent tonal / harmonic signals yield $K(f) \approx -1$.
//! - High-energy impulsive shock transients produce $K(f) \gg 10$ (often $> 25$).
//!
//! This module continuously tracks spectral kurtosis across all STFT bins, aggregates them
//! into 32 perceptual subbands for HUD visualization, computes the instantaneous Crest Factor (dB),
//! and issues sub-millisecond shock triggers to the Acoustic Concussion Blanker and True-Peak
//! Hearing Protection Limiter before damaging acoustic energy impacts the user's eardrum.
//!
//! Strictly pre-allocated buffers with ZERO HEAP ALLOCATIONS in the streaming loop.

use num_complex::Complex32;

/// Number of perceptual frequency bands for the Diagnostic HUD.
pub const KURTOSIS_HUD_BANDS: usize = 32;

/// Configuration for the Spectral Kurtosis Detector.
#[derive(Debug, Clone)]
pub struct KurtosisConfig {
    /// Number of STFT frequency bins (n_fft / 2 + 1, e.g. 257)
    pub num_bins: usize,
    /// Sample rate in Hz (default: 16000.0)
    pub sample_rate: f32,
    /// Exponential temporal smoothing factor for 2nd and 4th spectral moments (0.85 to 0.98, default: 0.95)
    pub smoothing_alpha: f32,
    /// Spectral Kurtosis threshold indicating impulsive non-Gaussian shock (default: 4.0)
    pub shock_kurtosis_threshold: f32,
    /// Peak Spectral Kurtosis threshold for single-bin shock trigger (default: 10.0)
    pub peak_kurtosis_threshold: f32,
    /// Crest Factor threshold in dB indicating severe peak-to-average disparity (default: 12.0 dB)
    pub crest_factor_threshold_db: f32,
    /// Regularization epsilon to avoid division by zero
    pub eps: f32,
}

impl Default for KurtosisConfig {
    fn default() -> Self {
        Self {
            num_bins: 257,
            sample_rate: 16000.0,
            smoothing_alpha: 0.95,
            shock_kurtosis_threshold: 4.0,
            peak_kurtosis_threshold: 10.0,
            crest_factor_threshold_db: 12.0,
            eps: 1e-8,
        }
    }
}

/// Real-time diagnostic statistics and shock warnings from Spectral Kurtosis tracking.
#[derive(Debug, Clone)]
pub struct KurtosisTelemetry {
    /// True if an impulsive non-Gaussian combat shock transient is detected
    pub is_shock_transient: bool,
    /// Mean Spectral Kurtosis across all bins
    pub mean_kurtosis: f32,
    /// Maximum peak Spectral Kurtosis across frequency spectrum
    pub peak_kurtosis: f32,
    /// Frequency in Hz of the highest kurtosis peak
    pub peak_frequency_hz: f32,
    /// Time-domain Crest Factor in dB: $20 \log_{10}(\text{peak} / \text{RMS})$
    pub crest_factor_db: f32,
    /// 32 aggregated frequency subbands formatted for Diagnostic HUD rendering
    pub hud_band_kurtosis: [f32; KURTOSIS_HUD_BANDS],
    /// Recommended blanking / limiting attenuation factor (0.0 to 1.0)
    pub suggested_attenuation: f32,
}

impl Default for KurtosisTelemetry {
    fn default() -> Self {
        Self {
            is_shock_transient: false,
            mean_kurtosis: 0.0,
            peak_kurtosis: 0.0,
            peak_frequency_hz: 0.0,
            crest_factor_db: 0.0,
            hud_band_kurtosis: [0.0; KURTOSIS_HUD_BANDS],
            suggested_attenuation: 1.0,
        }
    }
}

/// Zero-allocation Higher-Order Spectral Kurtosis and Non-Gaussian Shock Detector.
pub struct SpectralKurtosisDetector {
    config: KurtosisConfig,
    /// Exponential moving average of 2nd spectral moment: $\langle |X(f)|^2 \rangle$
    moment2: Vec<f32>,
    /// Exponential moving average of 4th spectral moment: $\langle |X(f)|^4 \rangle$
    moment4: Vec<f32>,
    /// Pre-allocated array for bin-wise kurtosis values
    kurtosis_bins: Vec<f32>,
    /// Pre-allocated mapping from STFT bins to 32 HUD bands: (start_bin, end_bin)
    hud_band_ranges: [(usize, usize); KURTOSIS_HUD_BANDS],
    /// Running telemetry report
    telemetry: KurtosisTelemetry,
}

impl SpectralKurtosisDetector {
    /// Creates a new SpectralKurtosisDetector with pre-allocated moment histories.
    pub fn new(config: KurtosisConfig) -> Self {
        let num_bins = config.num_bins;
        let moment2 = vec![1e-5f32; num_bins];
        let moment4 = vec![2e-10f32; num_bins]; // Initialized to circular Gaussian ratio (M4 = 2 * M2^2)
        let kurtosis_bins = vec![0.0f32; num_bins];

        // Construct 32 logarithmic/linear band mappings across [0, num_bins)
        let mut hud_band_ranges = [(0usize, 0usize); KURTOSIS_HUD_BANDS];
        for b in 0..KURTOSIS_HUD_BANDS {
            let start = (b * num_bins) / KURTOSIS_HUD_BANDS;
            let end = (((b + 1) * num_bins) / KURTOSIS_HUD_BANDS).max(start + 1).min(num_bins);
            hud_band_ranges[b] = (start, end);
        }

        Self {
            config,
            moment2,
            moment4,
            kurtosis_bins,
            hud_band_ranges,
            telemetry: KurtosisTelemetry::default(),
        }
    }

    /// Resets moments to baseline Gaussian quiet state.
    pub fn reset(&mut self) {
        self.moment2.fill(1e-5);
        self.moment4.fill(2e-10);
        self.kurtosis_bins.fill(0.0);
        self.telemetry = KurtosisTelemetry::default();
    }

    /// Returns the current configuration.
    pub fn config(&self) -> &KurtosisConfig {
        &self.config
    }

    /// Evaluates Spectral Kurtosis and Crest Factor across an STFT frame and optional time PCM block.
    ///
    /// - `spectrum`: Complex STFT spectrum bins [num_bins].
    /// - `time_block`: Optional time-domain audio samples for exact Crest Factor calculation.
    ///
    /// Strictly zero heap allocations.
    pub fn process_frame(
        &mut self,
        spectrum: &[Complex32],
        time_block: Option<&[f32]>,
    ) -> &KurtosisTelemetry {
        let num_bins = self.config.num_bins.min(spectrum.len());
        let alpha = self.config.smoothing_alpha;
        let beta = 1.0 - alpha;
        let eps = self.config.eps;

        let mut sum_kurt = 0.0f32;
        let mut max_kurt = -2.0f32;
        let mut max_bin = 0usize;

        // 1. Update 2nd and 4th spectral moments and calculate instantaneous Kurtosis per bin
        for i in 0..num_bins {
            let p2 = spectrum[i].norm_sqr();
            let p4 = p2 * p2;

            self.moment2[i] = alpha * self.moment2[i] + beta * p2;
            self.moment4[i] = alpha * self.moment4[i] + beta * p4;

            let denom = self.moment2[i] + eps;
            let kurt = (self.moment4[i] / (denom * denom)) - 2.0;

            self.kurtosis_bins[i] = kurt;
            sum_kurt += kurt;

            if kurt > max_kurt {
                max_kurt = kurt;
                max_bin = i;
            }
        }

        let mean_kurt = sum_kurt / num_bins.max(1) as f32;
        let peak_freq_hz = (max_bin as f32 / num_bins as f32) * (self.config.sample_rate * 0.5);

        // 2. Aggregate into 32 perceptual subbands for HUD visualization
        let mut hud_bands = [0.0f32; KURTOSIS_HUD_BANDS];
        for (b, &(start, end)) in self.hud_band_ranges.iter().enumerate() {
            let count = (end - start).max(1);
            let mut band_sum = 0.0f32;
            for i in start..end {
                band_sum += self.kurtosis_bins[i];
            }
            hud_bands[b] = band_sum / count as f32;
        }

        // 3. Compute time-domain Crest Factor if audio block provided
        let mut crest_factor_db = 0.0f32;
        if let Some(pcm) = time_block {
            let mut peak_val = 0.0f32;
            let mut sum_sq = 0.0f32;
            for &s in pcm {
                let abs_s = s.abs();
                if abs_s > peak_val {
                    peak_val = abs_s;
                }
                sum_sq += abs_s * abs_s;
            }
            let rms = (sum_sq / pcm.len().max(1) as f32).sqrt();
            if rms > eps {
                let ratio = peak_val / (rms + eps);
                crest_factor_db = 20.0 * ratio.max(1.0).log10();
            }
        }

        // 4. Combat Non-Gaussian Shock Transient Decision Logic
        let shock_by_mean = mean_kurt > self.config.shock_kurtosis_threshold;
        let shock_by_peak = max_kurt > self.config.peak_kurtosis_threshold;
        let shock_by_crest = crest_factor_db > self.config.crest_factor_threshold_db;

        let is_shock = shock_by_mean || shock_by_peak || (shock_by_crest && max_kurt > 2.0);

        // Recommended attenuation: rapidly clamp gain when shock is detected
        let suggested_attenuation = if is_shock {
            let severity = (max_kurt / self.config.peak_kurtosis_threshold).max(1.0);
            (1.0 / severity).clamp(0.05, 0.40)
        } else {
            1.0
        };

        self.telemetry = KurtosisTelemetry {
            is_shock_transient: is_shock,
            mean_kurtosis: mean_kurt,
            peak_kurtosis: max_kurt,
            peak_frequency_hz: peak_freq_hz,
            crest_factor_db,
            hud_band_kurtosis: hud_bands,
            suggested_attenuation,
        };

        &self.telemetry
    }

    /// Returns the latest computed telemetry.
    #[inline]
    pub fn telemetry(&self) -> &KurtosisTelemetry {
        &self.telemetry
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_spectral_kurtosis_gaussian_noise_near_zero() {
        let config = KurtosisConfig {
            num_bins: 64,
            sample_rate: 16000.0,
            smoothing_alpha: 0.95,
            shock_kurtosis_threshold: 4.0,
            peak_kurtosis_threshold: 10.0,
            crest_factor_threshold_db: 12.0,
            eps: 1e-8,
        };
        let mut detector = SpectralKurtosisDetector::new(config);

        // Feed steady Gaussian noise spectra across multiple frames
        let spectrum = vec![Complex32::new(0.1, 0.1); 64];
        let pcm_nominal = vec![0.05f32; 128];

        for _ in 0..100 {
            detector.process_frame(&spectrum, Some(&pcm_nominal));
        }

        let telem = detector.telemetry();
        assert!(!telem.is_shock_transient, "Gaussian noise must not trigger shock alert");
        assert!(telem.mean_kurtosis < 2.0, "Gaussian noise mean kurtosis must be near 0 (was {})", telem.mean_kurtosis);
        assert_eq!(telem.suggested_attenuation, 1.0);
    }

    #[test]
    fn test_spectral_kurtosis_gunshot_transient_triggers_shock() {
        let config = KurtosisConfig {
            num_bins: 64,
            sample_rate: 16000.0,
            smoothing_alpha: 0.95,
            shock_kurtosis_threshold: 4.0,
            peak_kurtosis_threshold: 10.0,
            crest_factor_threshold_db: 10.0,
            eps: 1e-8,
        };
        let mut detector = SpectralKurtosisDetector::new(config);

        // Background stationary noise
        let quiet_spec = vec![Complex32::new(0.01, 0.01); 64];
        let quiet_pcm = vec![0.005f32; 128];
        for _ in 0..50 {
            detector.process_frame(&quiet_spec, Some(&quiet_pcm));
        }

        // Sudden massive combat shock transient (e.g. supersonic bullet crack / gunfire pulse)
        let shock_spec = vec![Complex32::new(2.5, 2.5); 64];
        let mut shock_pcm = vec![0.005f32; 128];
        shock_pcm[10] = 0.95; // Extreme impulse spike: huge crest factor
        shock_pcm[11] = -0.85;

        detector.process_frame(&shock_spec, Some(&shock_pcm));
        let telem = detector.telemetry();

        assert!(telem.is_shock_transient, "Combat impulse shock transient must trigger shock detection");
        assert!(telem.peak_kurtosis > 10.0, "Impulse peak kurtosis must be >> 10 (was {})", telem.peak_kurtosis);
        assert!(telem.crest_factor_db > 10.0, "Crest factor must be elevated (was {})", telem.crest_factor_db);
        assert!(telem.suggested_attenuation < 1.0, "Must recommend attenuation for ear protection");
    }
}
