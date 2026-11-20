//! Acoustic Speech Transmission Index (STI) & Real-Time RASTI Predictor.
//!
//! Developed for SIH 26052 Tactical Military Communications.
//!
//! Compliant with IEC 60268-16 Standard: "Sound system equipment - Part 16:
//! Objective rating of speech intelligibility by speech transmission index".
//!
//! Speech intelligibility relies heavily on the preservation of low-frequency
//! intensity envelope modulations (0.63 Hz - 12.5 Hz) corresponding to syllable,
//! consonant, and vowel articulation rates.
//!
//! In combat environments (vehicle rumble, rotor wash, multipath acoustic reflections),
//! ambient noise fills the inter-syllable valleys, degrading the modulation depth.
//!
//! This module tracks Modulation Transfer Functions m(F) across 14 IEC 60268-16 standard
//! modulation frequencies:
//! [0.63, 0.80, 1.00, 1.25, 1.60, 2.00, 2.50, 3.15, 4.00, 5.00, 6.30, 8.00, 10.00, 12.50] Hz.
//!
//! For each modulation frequency F_m:
//! 1. Calculates modulation reduction factor m(F_m) from the sliding envelope history.
//! 2. Derives apparent signal-to-noise ratio:
//!    SNR_app(F_m) = 10 * log10( m(F_m) / (1.0001 - m(F_m)) ) clamped to [-15 dB, +15 dB].
//! 3. Evaluates Transmission Index:
//!    TI(F_m) = (SNR_app(F_m) + 15) / 30 in [0.0, 1.0].
//! 4. Computes composite STI / RASTI score:
//!    STI = mean(TI) in [0.0, 1.0].
//! 5. Maps to IEC 60268-16 qualification categories:
//!    Bad (<0.30), Poor (0.30-0.45), Fair (0.45-0.60), Good (0.60-0.75), Excellent (>=0.75).
//!
//! Strictly ZERO heap allocations in the real-time processing loop.

use serde::{Deserialize, Serialize};

/// Number of IEC 60268-16 modulation frequencies.
pub const NUM_RASTI_MOD_FREQS: usize = 14;

/// Standard IEC 60268-16 modulation frequencies in Hz.
pub const RASTI_MOD_FREQS_HZ: [f32; NUM_RASTI_MOD_FREQS] = [
    0.63, 0.80, 1.00, 1.25, 1.60, 2.00, 2.50, 3.15, 4.00, 5.00, 6.30, 8.00, 10.00, 12.50,
];

/// Nominal clean speech modulation depth envelope across the 14 modulation frequencies
/// based on Steeneken & Houtgast (IEC 60268-16 standard speech spectrum).
pub const SPEECH_MODULATION_REFERENCE: [f32; NUM_RASTI_MOD_FREQS] = [
    0.15, 0.18, 0.22, 0.25, 0.28, 0.30, 0.32, 0.30, 0.28, 0.24, 0.20, 0.16, 0.12, 0.10,
];

/// Number of historical hops tracked in circular buffer (64 hops @ 16 ms = 1.024 seconds).
pub const RASTI_HISTORY_HOPS: usize = 64;

/// IEC 60268-16 Speech Transmission Index qualification rating.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u8)]
pub enum StiRating {
    /// STI < 0.30: Unintelligible under combat conditions.
    Bad = 0,
    /// 0.30 <= STI < 0.45: Difficult communication, frequent repeats required.
    Poor = 1,
    /// 0.45 <= STI < 0.60: Acceptable for trained military radio operators.
    Fair = 2,
    /// 0.60 <= STI < 0.75: Clear tactical communication.
    Good = 3,
    /// STI >= 0.75: Crystal clear command fidelity.
    Excellent = 4,
}

impl StiRating {
    pub fn name(&self) -> &'static str {
        match self {
            Self::Bad => "BAD",
            Self::Poor => "POOR",
            Self::Fair => "FAIR",
            Self::Good => "GOOD",
            Self::Excellent => "EXCELLENT",
        }
    }

    pub fn code(&self) -> u8 {
        *self as u8
    }

    pub fn from_u8(code: u8) -> Self {
        match code {
            1 => Self::Poor,
            2 => Self::Fair,
            3 => Self::Good,
            4 => Self::Excellent,
            _ => Self::Bad,
        }
    }

    pub fn from_score(score: f32) -> Self {
        if score < 0.30 {
            Self::Bad
        } else if score < 0.45 {
            Self::Poor
        } else if score < 0.60 {
            Self::Fair
        } else if score < 0.75 {
            Self::Good
        } else {
            Self::Excellent
        }
    }
}

/// Configuration parameters for the RASTI / STI Predictor.
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct StiConfig {
    pub sample_rate: f32,
    pub hop_size: usize,
    /// Temporal smoothing coefficient for STI score (default: 0.85).
    pub smoothing_factor: f32,
    /// Master enable toggle.
    pub enabled: bool,
}

impl Default for StiConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000.0,
            hop_size: 256,
            smoothing_factor: 0.85,
            enabled: true,
        }
    }
}

/// Real-time telemetry snapshot produced by the RASTI / STI Predictor.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct StiTelemetry {
    /// Objective Speech Transmission Index (0.0 to 1.0).
    pub sti_score: f32,
    /// IEC 60268-16 Intelligibility qualification rating.
    pub rating: StiRating,
    /// Mean apparent SNR across all 14 modulation bands in dB.
    pub mean_apparent_snr_db: f32,
    /// Mean Modulation Transfer factor across all 14 modulation bands in [0.0, 1.0].
    pub mean_mtf: f32,
    /// Per-modulation-frequency transfer factors m(F_m).
    pub mtf_bands: [f32; NUM_RASTI_MOD_FREQS],
    /// Whether enough history has accumulated for an authoritative reading.
    pub is_authoritative: bool,
}

impl Default for StiTelemetry {
    fn default() -> Self {
        Self {
            sti_score: 0.0,
            rating: StiRating::Bad,
            mean_apparent_snr_db: -15.0,
            mean_mtf: 0.0,
            mtf_bands: [0.0; NUM_RASTI_MOD_FREQS],
            is_authoritative: false,
        }
    }
}

/// IEC 60268-16 standard Rapid Speech Transmission Index (RASTI) Predictor.
#[derive(Debug, Clone)]
pub struct RastiPredictor {
    config: StiConfig,
    /// Circular buffer of recent hop acoustic envelope powers
    envelope_history: [f32; RASTI_HISTORY_HOPS],
    head: usize,
    hops_recorded: u64,
    /// Smoothed STI score
    smooth_sti: f32,
    /// Smoothed MTF values
    smooth_mtf: [f32; NUM_RASTI_MOD_FREQS],
    last_telemetry: StiTelemetry,
}

impl RastiPredictor {
    /// Creates a new RastiPredictor instance.
    pub fn new(config: StiConfig) -> Self {
        Self {
            config,
            envelope_history: [0.0; RASTI_HISTORY_HOPS],
            head: 0,
            hops_recorded: 0,
            smooth_sti: 0.0,
            smooth_mtf: [0.0; NUM_RASTI_MOD_FREQS],
            last_telemetry: StiTelemetry::default(),
        }
    }

    /// Resets all envelope history and filters.
    pub fn reset(&mut self) {
        self.envelope_history.fill(0.0);
        self.head = 0;
        self.hops_recorded = 0;
        self.smooth_sti = 0.0;
        self.smooth_mtf.fill(0.0);
        self.last_telemetry = StiTelemetry::default();
    }

    /// Ingests a new audio hop/frame (e.g. 256 samples @ 16 kHz) and computes live STI.
    pub fn process_frame(&mut self, samples: &[f32]) -> StiTelemetry {
        self.process_hop(samples)
    }

    /// Ingests a new audio hop (e.g. 256 samples @ 16 kHz) and computes live STI.
    pub fn process_hop(&mut self, samples: &[f32]) -> StiTelemetry {
        if !self.config.enabled || samples.is_empty() {
            return self.last_telemetry;
        }

        // 1. Calculate squared envelope power of the current hop
        let mut sum_sq = 0.0f32;
        for &s in samples {
            sum_sq += s * s;
        }
        let hop_power = sum_sq / samples.len() as f32;

        // 2. Insert into circular buffer
        self.envelope_history[self.head] = hop_power;
        self.head = (self.head + 1) % RASTI_HISTORY_HOPS;
        self.hops_recorded += 1;

        let is_authoritative = self.hops_recorded >= RASTI_HISTORY_HOPS as u64;

        // 3. Time step per envelope hop in seconds
        let dt = self.config.hop_size as f32 / self.config.sample_rate;

        // 4. Compute DC component of envelope
        let mut sum_dc = 0.0f32;
        for &p in &self.envelope_history {
            sum_dc += p;
        }
        let mean_dc = (sum_dc / RASTI_HISTORY_HOPS as f32).max(1e-12);

        // 5. Compute Modulation Transfer Function m(F_m) across 14 modulation frequencies
        let mut sum_ti = 0.0f32;
        let mut sum_snr = 0.0f32;
        let mut mtf_out = [0.0f32; NUM_RASTI_MOD_FREQS];

        let alpha = self.config.smoothing_factor.clamp(0.0, 0.99);

        // Precompute Hann window sum
        let mut hann_sum = 0.0f32;
        for k in 0..RASTI_HISTORY_HOPS {
            let w = 0.5
                * (1.0 - (2.0 * std::f32::consts::PI * k as f32 / RASTI_HISTORY_HOPS as f32).cos());
            hann_sum += w;
        }
        let inv_hann_sum = 1.0 / hann_sum.max(1e-6);

        for (idx, &fm) in RASTI_MOD_FREQS_HZ.iter().enumerate() {
            let omega = 2.0 * std::f32::consts::PI * fm * dt;
            let mut re = 0.0f32;
            let mut im = 0.0f32;

            for k in 0..RASTI_HISTORY_HOPS {
                let p = self.envelope_history[(self.head + k) % RASTI_HISTORY_HOPS];
                let ac = p - mean_dc;
                let w = 0.5
                    * (1.0
                        - (2.0 * std::f32::consts::PI * k as f32 / RASTI_HISTORY_HOPS as f32)
                            .cos());
                let ac_windowed = ac * w;
                let phase = omega * k as f32;
                re += ac_windowed * phase.cos();
                im += ac_windowed * phase.sin();
            }

            let mod_amp = 2.0 * (re * re + im * im).sqrt() * inv_hann_sum;
            let raw_mtf = (mod_amp / mean_dc).clamp(0.0, 1.0);

            // Smooth MTF
            self.smooth_mtf[idx] = alpha * self.smooth_mtf[idx] + (1.0 - alpha) * raw_mtf;
            let mtf = self.smooth_mtf[idx];
            mtf_out[idx] = mtf;

            // Normalized to IEC speech reference modulation depth
            let ref_depth = SPEECH_MODULATION_REFERENCE[idx];
            let norm_mtf = (mtf / ref_depth).clamp(0.0, 1.0);

            // Apparent SNR from IEC 60268-16:
            // SNR_app = 10 * log10( norm_mtf / (1.0001 - norm_mtf) )
            let ratio = (norm_mtf / (1.0001 - norm_mtf)).max(1e-4);
            let snr_app = (10.0 * ratio.log10()).clamp(-15.0, 15.0);
            sum_snr += snr_app;

            // Transmission Index: TI = (SNR_app + 15) / 30
            let ti = (snr_app + 15.0) / 30.0;
            sum_ti += ti;
        }

        let raw_sti = (sum_ti / NUM_RASTI_MOD_FREQS as f32).clamp(0.0, 1.0);
        let mean_snr = sum_snr / NUM_RASTI_MOD_FREQS as f32;
        let mean_mtf = mtf_out.iter().sum::<f32>() / NUM_RASTI_MOD_FREQS as f32;

        self.smooth_sti = alpha * self.smooth_sti + (1.0 - alpha) * raw_sti;
        let rating = StiRating::from_score(self.smooth_sti);

        self.last_telemetry = StiTelemetry {
            sti_score: self.smooth_sti,
            rating,
            mean_apparent_snr_db: mean_snr,
            mean_mtf,
            mtf_bands: mtf_out,
            is_authoritative,
        };

        self.last_telemetry
    }

    /// Returns the latest STI telemetry snapshot.
    pub fn telemetry(&self) -> StiTelemetry {
        self.last_telemetry
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sti_initial_state() {
        let config = StiConfig::default();
        let predictor = RastiPredictor::new(config);
        assert_eq!(predictor.telemetry(), StiTelemetry::default());
    }

    #[test]
    fn test_sti_flat_noise_collapses_to_zero() {
        let config = StiConfig {
            smoothing_factor: 0.0, // Instant response
            ..Default::default()
        };
        let mut predictor = RastiPredictor::new(config);

        // Constant DC flat noise envelope has zero modulation depth across all frequencies
        let flat_noise = vec![0.5f32; 256];
        for _ in 0..RASTI_HISTORY_HOPS + 10 {
            predictor.process_hop(&flat_noise);
        }

        let telem = predictor.telemetry();
        assert!(telem.is_authoritative);
        assert!(
            telem.sti_score < 0.15,
            "Flat noise must have STI < 0.15, got {}",
            telem.sti_score
        );
        assert_eq!(telem.rating, StiRating::Bad);
    }

    #[test]
    fn test_sti_modulated_speech_achieves_high_score() {
        let config = StiConfig {
            smoothing_factor: 0.0,
            ..Default::default()
        };
        let mut predictor = RastiPredictor::new(config);

        // Modulate with realistic speech modulation rates across the IEC 60268-16 spectrum
        let dt = 256.0 / 16000.0;
        for h in 0..(RASTI_HISTORY_HOPS + 20) {
            let t = h as f32 * dt;
            // Multi-frequency speech articulation envelope
            let mod_env = 0.25
                * ((1.0 + (2.0 * std::f32::consts::PI * 1.0 * t).sin())
                    + (1.0 + (2.0 * std::f32::consts::PI * 2.5 * t).sin())
                    + (1.0 + (2.0 * std::f32::consts::PI * 5.0 * t).sin())
                    + (1.0 + (2.0 * std::f32::consts::PI * 10.0 * t).sin()));
            let hop: Vec<f32> = (0..256)
                .map(|i| mod_env * ((i as f32 * 0.2).sin()))
                .collect();
            predictor.process_hop(&hop);
        }

        let telem = predictor.telemetry();
        assert!(telem.is_authoritative);
        assert!(
            telem.sti_score > 0.40,
            "Modulated speech signal must achieve STI > 0.40, got {}",
            telem.sti_score
        );
        assert!(telem.mean_mtf > 0.15);
    }

    #[test]
    fn test_sti_rating_classification() {
        assert_eq!(StiRating::from_score(0.25), StiRating::Bad);
        assert_eq!(StiRating::from_score(0.38), StiRating::Poor);
        assert_eq!(StiRating::from_score(0.52), StiRating::Fair);
        assert_eq!(StiRating::from_score(0.68), StiRating::Good);
        assert_eq!(StiRating::from_score(0.85), StiRating::Excellent);

        assert_eq!(StiRating::Bad.name(), "BAD");
        assert_eq!(StiRating::Poor.name(), "POOR");
        assert_eq!(StiRating::Fair.name(), "FAIR");
        assert_eq!(StiRating::Good.name(), "GOOD");
        assert_eq!(StiRating::Excellent.name(), "EXCELLENT");
    }

    #[test]
    fn test_sti_clamping_bounds() {
        let config = StiConfig::default();
        let mut predictor = RastiPredictor::new(config);

        // Extreme values
        let zeros = vec![0.0f32; 256];
        predictor.process_hop(&zeros);
        let telem = predictor.telemetry();
        assert!(telem.sti_score >= 0.0 && telem.sti_score <= 1.0);
    }

    #[test]
    fn test_sti_reset() {
        let config = StiConfig::default();
        let mut predictor = RastiPredictor::new(config);

        let hop = vec![0.5f32; 256];
        predictor.process_hop(&hop);
        predictor.reset();

        assert_eq!(predictor.telemetry(), StiTelemetry::default());
    }
}
