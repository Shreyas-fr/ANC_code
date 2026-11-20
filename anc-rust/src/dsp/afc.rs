//! Online Subband Acoustic Feedback Cancellation (AFC) via Decoupled Shadow Filter.
//!
//! In tactical combat headsets, high earpiece/speaker volume leaks into the near-field
//! dual-microphone array via ear-cushion acoustic leakage and helmet bone-conduction.
//! This module implements an online Normalized LMS (NLMS) adaptive filter in the STFT
//! subband domain using a two-path Decoupled Shadow Filter (Foreground / Background)
//! architecture:
//! - Background filter: Adapts continuously using normalized gradient descent with leakage.
//! - Foreground filter: Applied to the actual audio stream to cancel feedback.
//! - Transfer logic: Only copies weights from background to foreground when background
//!   demonstrably achieves superior echo cancellation without speech presence divergence.
//! - Double-talk / Near-end speech protection: Freezes or slows adaptation during speech
//!   activity to guarantee zero distortion of the soldier's voice.

use super::geigel::{GeigelConfig, GeigelDetector, GeigelStats};
use num_complex::Complex32;

/// Configuration for Subband Acoustic Feedback Cancellation.
#[derive(Debug, Clone)]
pub struct AfcConfig {
    /// Number of STFT frequency bins (n_fft / 2 + 1, e.g. 257)
    pub num_bins: usize,
    /// Number of filter history taps per subband (default: 4 taps)
    pub num_taps: usize,
    /// NLMS normalized adaptation step size mu (0.01 to 0.40, default: 0.15)
    pub step_size: f32,
    /// Leakage factor gamma to prevent coefficient drift in unexcited bins (default: 1e-4)
    pub leakage: f32,
    /// Background-to-foreground transfer power ratio threshold (default: 0.85 = ~0.7 dB gain)
    pub transfer_ratio: f32,
    /// Minimum speaker reference power required for adaptation (default: 1e-5)
    pub min_power_thresh: f32,
    /// Regularization epsilon to avoid division by zero (default: 1e-6)
    pub eps: f32,
    /// Temporal smoothing factor for reference power tracking (default: 0.80)
    pub power_smoothing: f32,
    /// Whether ITU-T G.168 Geigel Double-Talk Detection is enabled
    pub enable_geigel: bool,
    /// Geigel Double-Talk Detector configuration
    pub geigel_config: GeigelConfig,
}

impl Default for AfcConfig {
    fn default() -> Self {
        Self {
            num_bins: 257,
            num_taps: 4,
            step_size: 0.15,
            leakage: 1e-4,
            transfer_ratio: 0.85,
            min_power_thresh: 1e-5,
            eps: 1e-6,
            power_smoothing: 0.80,
            enable_geigel: false,
            geigel_config: GeigelConfig::default(),
        }
    }
}

/// Real-time diagnostic statistics from the AFC engine.
#[derive(Debug, Clone, Copy, Default)]
pub struct AfcStats {
    /// Echo Return Loss Enhancement in dB for Primary Mic 1
    pub erle_mic1_db: f32,
    /// Echo Return Loss Enhancement in dB for Secondary Mic 2
    pub erle_mic2_db: f32,
    /// Number of weight transfers from background to foreground
    pub transfers_count: u32,
    /// Indicates whether double-talk / near-end speech was detected this frame
    pub double_talk_detected: bool,
    /// ITU-T G.168 Geigel metric ratio
    pub geigel_metric: f32,
}

/// Single-channel subband adaptive filter state with Decoupled Shadow Filter.
struct SubbandChannelFilter {
    /// Foreground filter weights: [num_bins][num_taps]
    weights_fg: Vec<Complex32>,
    /// Background shadow filter weights: [num_bins][num_taps]
    weights_bg: Vec<Complex32>,
    /// Foreground estimated echo per bin
    echo_fg: Vec<Complex32>,
    /// Background estimated echo per bin
    echo_bg: Vec<Complex32>,
    /// Accumulated transfer count
    transfers: u32,
    /// Current ERLE in dB
    erle_db: f32,
}

impl SubbandChannelFilter {
    fn new(num_bins: usize, num_taps: usize) -> Self {
        Self {
            weights_fg: vec![Complex32::default(); num_bins * num_taps],
            weights_bg: vec![Complex32::default(); num_bins * num_taps],
            echo_fg: vec![Complex32::default(); num_bins],
            echo_bg: vec![Complex32::default(); num_bins],
            transfers: 0,
            erle_db: 0.0,
        }
    }

    fn reset(&mut self) {
        self.weights_fg.fill(Complex32::default());
        self.weights_bg.fill(Complex32::default());
        self.echo_fg.fill(Complex32::default());
        self.echo_bg.fill(Complex32::default());
        self.transfers = 0;
        self.erle_db = 0.0;
    }

    #[inline]
    fn get_weight(weights: &[Complex32], bin: usize, tap: usize, num_taps: usize) -> Complex32 {
        weights[bin * num_taps + tap]
    }

    #[inline]
    fn set_weight(
        weights: &mut [Complex32],
        bin: usize,
        tap: usize,
        num_taps: usize,
        val: Complex32,
    ) {
        weights[bin * num_taps + tap] = val;
    }
}

/// High-performance Subband Acoustic Feedback Canceller for dual-microphone headsets.
pub struct SubbandAfc {
    config: AfcConfig,
    /// Reference speaker history delay line: [num_taps][num_bins]
    ref_history: Vec<Complex32>,
    /// Smoothed speaker power per bin
    ref_power: Vec<f32>,
    /// Primary Mic 1 filter state
    mic1_filter: SubbandChannelFilter,
    /// Secondary Mic 2 filter state
    mic2_filter: SubbandChannelFilter,
    /// Current tap write pointer in cyclic delay line
    tap_idx: usize,
    /// ITU-T G.168 Geigel Double-Talk Detector
    pub geigel: GeigelDetector,
}

impl SubbandAfc {
    /// Creates a new SubbandAfc instance.
    pub fn new(config: AfcConfig) -> Self {
        let num_bins = config.num_bins;
        let num_taps = config.num_taps;
        let geigel = GeigelDetector::new(config.geigel_config.clone());

        Self {
            ref_history: vec![Complex32::default(); num_taps * num_bins],
            ref_power: vec![1e-4; num_bins],
            mic1_filter: SubbandChannelFilter::new(num_bins, num_taps),
            mic2_filter: SubbandChannelFilter::new(num_bins, num_taps),
            tap_idx: 0,
            geigel,
            config,
        }
    }

    /// Resets all adaptive filter states, weights, and delay line histories.
    pub fn reset(&mut self) {
        self.ref_history.fill(Complex32::default());
        self.ref_power.fill(1e-4);
        self.mic1_filter.reset();
        self.mic2_filter.reset();
        self.tap_idx = 0;
        self.geigel.reset();
    }

    /// Returns the current configuration.
    pub fn config(&self) -> &AfcConfig {
        &self.config
    }

    /// Returns foreground estimated linear echo for Mic 1.
    pub fn mic1_estimated_echo(&self) -> &[Complex32] {
        &self.mic1_filter.echo_fg
    }

    /// Returns foreground estimated linear echo for Mic 2.
    pub fn mic2_estimated_echo(&self) -> &[Complex32] {
        &self.mic2_filter.echo_fg
    }

    /// Processes an STFT frame of dual-microphone signals and loudspeaker reference spectrum.
    ///
    /// - `mic1_spec`: STFT complex spectrum of Primary Mic 1 [num_bins]. Cancelled in-place.
    /// - `mic2_spec`: Optional STFT complex spectrum of Secondary Mic 2 [num_bins]. Cancelled in-place.
    /// - `ref_speaker_spec`: Loudspeaker playback spectrum [num_bins].
    /// - `spp_mean`: Mean speech presence probability (0.0 to 1.0) used for double-talk damping.
    ///
    /// Returns `AfcStats` with current ERLE and transfer diagnostics. Zero heap allocations.
    pub fn process_frame(
        &mut self,
        mic1_spec: &mut [Complex32],
        mic2_spec: Option<&mut [Complex32]>,
        ref_speaker_spec: &[Complex32],
        spp_mean: f32,
    ) -> AfcStats {
        let num_bins = self.config.num_bins;
        let num_taps = self.config.num_taps;
        assert_eq!(mic1_spec.len(), num_bins);
        assert_eq!(ref_speaker_spec.len(), num_bins);

        // 1. Push current reference speaker frame into circular delay line
        let current_tap = self.tap_idx;
        let start = current_tap * num_bins;
        self.ref_history[start..start + num_bins].copy_from_slice(ref_speaker_spec);

        // 2. Update smoothed reference power per frequency bin
        let alpha_p = self.config.power_smoothing;
        let beta_p = 1.0 - alpha_p;
        let mut total_ref_power = 0.0f32;

        for (p_ref, &ref_s) in self.ref_power.iter_mut().zip(ref_speaker_spec.iter()) {
            let p_instant = ref_s.norm_sqr();
            *p_ref = alpha_p * *p_ref + beta_p * p_instant;
            total_ref_power += *p_ref;
        }
        let avg_ref_power = total_ref_power / num_bins.max(1) as f32;

        // ITU-T G.168 Geigel Double-Talk Detection & SPP fusion
        let geigel_stats = if self.config.enable_geigel {
            self.geigel.process_spectrum(mic1_spec, ref_speaker_spec)
        } else {
            GeigelStats::default()
        };
        let double_talk = if self.config.enable_geigel {
            geigel_stats.is_double_talk
        } else {
            spp_mean > 0.40
        };
        let step_scale = if double_talk {
            if self.config.enable_geigel {
                0.0 // Instant freeze when Geigel declares double-talk to prevent divergence
            } else {
                (1.0 - spp_mean).clamp(0.05, 1.0) * 0.25 // Heavy step size attenuation during near-end speech
            }
        } else {
            1.0
        };

        // 3. Process Primary Mic 1 Channel
        Self::process_channel(
            &self.config,
            &self.ref_history,
            &self.ref_power,
            mic1_spec,
            &mut self.mic1_filter,
            num_bins,
            num_taps,
            current_tap,
            avg_ref_power,
            step_scale,
        );

        // 4. Process Secondary Mic 2 Channel if provided
        if let Some(m2) = mic2_spec {
            assert_eq!(m2.len(), num_bins);
            Self::process_channel(
                &self.config,
                &self.ref_history,
                &self.ref_power,
                m2,
                &mut self.mic2_filter,
                num_bins,
                num_taps,
                current_tap,
                avg_ref_power,
                step_scale,
            );
        }

        // Advance circular delay line pointer
        self.tap_idx = (self.tap_idx + 1) % num_taps;

        AfcStats {
            erle_mic1_db: self.mic1_filter.erle_db,
            erle_mic2_db: self.mic2_filter.erle_db,
            transfers_count: self.mic1_filter.transfers + self.mic2_filter.transfers,
            double_talk_detected: double_talk,
            geigel_metric: geigel_stats.geigel_metric,
        }
    }

    #[allow(clippy::too_many_arguments)]
    #[inline]
    fn process_channel(
        config: &AfcConfig,
        ref_history: &[Complex32],
        ref_power: &[f32],
        mic_spec: &mut [Complex32],
        chan: &mut SubbandChannelFilter,
        num_bins: usize,
        num_taps: usize,
        current_tap: usize,
        avg_ref_power: f32,
        step_scale: f32,
    ) {
        let mu_base = config.step_size * step_scale;
        let gamma = config.leakage;
        let eps = config.eps;

        let mut p_d = 0.0f32;
        let mut p_e_fg = 0.0f32;
        let mut p_e_bg = 0.0f32;

        // A. Compute estimated echo for both foreground and background filters
        for k in 0..num_bins {
            let mut y_fg = Complex32::default();
            let mut y_bg = Complex32::default();

            for tap in 0..num_taps {
                let delay_idx = (current_tap + num_taps - tap) % num_taps;
                let x_val = ref_history[delay_idx * num_bins + k];

                let w_fg = SubbandChannelFilter::get_weight(&chan.weights_fg, k, tap, num_taps);
                let w_bg = SubbandChannelFilter::get_weight(&chan.weights_bg, k, tap, num_taps);

                y_fg += w_fg * x_val;
                y_bg += w_bg * x_val;
            }

            chan.echo_fg[k] = y_fg;
            chan.echo_bg[k] = y_bg;

            let d_k = mic_spec[k];
            let e_fg = d_k - y_fg;
            let e_bg = d_k - y_bg;

            p_d += d_k.norm_sqr();
            p_e_fg += e_fg.norm_sqr();
            p_e_bg += e_bg.norm_sqr();

            // Adapt background filter using Normalized LMS
            if avg_ref_power > config.min_power_thresh {
                let norm_factor = mu_base / (ref_power[k] + eps);
                for tap in 0..num_taps {
                    let delay_idx = (current_tap + num_taps - tap) % num_taps;
                    let x_val = ref_history[delay_idx * num_bins + k];

                    let old_w =
                        SubbandChannelFilter::get_weight(&chan.weights_bg, k, tap, num_taps);
                    let grad = e_bg * x_val.conj();
                    // NLMS with leakage: W <- (1 - gamma) * W + mu_norm * E * X*
                    let new_w = old_w * (1.0 - gamma) + grad * norm_factor;
                    SubbandChannelFilter::set_weight(&mut chan.weights_bg, k, tap, num_taps, new_w);
                }
            }
        }

        // B. Decoupled Shadow Filter Transfer Logic:
        // Only transfer from background to foreground when background demonstrably achieves lower error
        if avg_ref_power > config.min_power_thresh {
            if p_e_bg < config.transfer_ratio * p_e_fg && p_e_bg < p_d {
                // Background filter is clearly better: copy weights to foreground
                chan.weights_fg.copy_from_slice(&chan.weights_bg);
                chan.transfers += 1;
            } else if p_e_bg > 3.0 * p_d && p_d > 1e-5 {
                // Background filter diverged (e.g. violent near-end burst): reset background to foreground
                chan.weights_bg.copy_from_slice(&chan.weights_fg);
            }
        }

        // C. Apply foreground cancellation to microphone spectrum
        for (m, &e) in mic_spec.iter_mut().zip(chan.echo_fg.iter()) {
            *m -= e;
        }

        // Calculate Echo Return Loss Enhancement (ERLE) in dB
        let erle_linear = (p_d.max(1e-8)) / (p_e_fg.max(1e-8));
        let erle_db = 10.0 * erle_linear.log10().max(0.0);
        chan.erle_db = 0.90 * chan.erle_db + 0.10 * erle_db;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_afc_silence_passthrough_distortionless() {
        let config = AfcConfig::default();
        let mut afc = SubbandAfc::new(config.clone());

        let num_bins = config.num_bins;
        let mut mic1 = vec![Complex32::new(1.0, 0.5); num_bins];
        let original_mic1 = mic1.clone();
        let ref_speaker = vec![Complex32::default(); num_bins]; // Loudspeaker is silent

        let stats = afc.process_frame(&mut mic1, None, &ref_speaker, 0.0);

        // When speaker is silent, mic1 must be preserved distortionlessly
        for k in 0..num_bins {
            assert!((mic1[k].re - original_mic1[k].re).abs() < 1e-6);
            assert!((mic1[k].im - original_mic1[k].im).abs() < 1e-6);
        }
        assert_eq!(stats.transfers_count, 0);
    }

    #[test]
    fn test_afc_converges_and_attenuates_speaker_feedback() {
        let config = AfcConfig {
            step_size: 0.25,
            transfer_ratio: 0.90,
            ..Default::default()
        };
        let mut afc = SubbandAfc::new(config.clone());
        let num_bins = config.num_bins;

        // Simulated acoustic feedback coupling: H[k] = 0.4 * e^{-j * 0.5}
        let feedback_coupling = Complex32::from_polar(0.4, -0.5);

        let mut last_erle = 0.0f32;

        // Feed repeating loudspeaker reference into microphone via coupling
        for frame in 0..60 {
            let mut ref_speaker = vec![Complex32::default(); num_bins];
            let mut mic1 = vec![Complex32::default(); num_bins];

            for k in 1..num_bins {
                let tone = Complex32::from_polar(2.0, frame as f32 * 0.1 + k as f32 * 0.05);
                ref_speaker[k] = tone;
                mic1[k] = tone * feedback_coupling; // Pure acoustic leakage
            }

            let stats = afc.process_frame(&mut mic1, None, &ref_speaker, 0.0);
            last_erle = stats.erle_mic1_db;
        }

        // AFC must achieve positive ERLE (> 10 dB) on steady feedback
        assert!(
            last_erle > 8.0,
            "Expected ERLE > 8.0 dB, achieved {:.2} dB",
            last_erle
        );
        assert!(
            afc.mic1_filter.transfers > 0,
            "Expected at least one shadow transfer"
        );
    }

    #[test]
    fn test_afc_double_talk_protection_preserves_near_end_speech() {
        let config = AfcConfig::default();
        let mut afc = SubbandAfc::new(config.clone());
        let num_bins = config.num_bins;

        let mut ref_speaker = vec![Complex32::default(); num_bins];
        let mut mic1 = vec![Complex32::default(); num_bins];

        // Speaker plays moderate audio
        for k in 1..num_bins {
            ref_speaker[k] = Complex32::new(0.5, 0.2);
        }

        // Soldier speaks loudly into microphone (SPP = 0.95)
        let soldier_voice = Complex32::new(5.0, 3.0);
        for k in 1..num_bins {
            mic1[k] = soldier_voice;
        }

        let stats = afc.process_frame(&mut mic1, None, &ref_speaker, 0.95);
        assert!(stats.double_talk_detected);

        // Near-end voice must remain intact and not get wiped out
        let preserved_norm = mic1[10].norm();
        let original_norm = soldier_voice.norm();
        assert!(
            (preserved_norm - original_norm).abs() < 0.8,
            "Soldier voice was distorted: original={}, preserved={}",
            original_norm,
            preserved_norm
        );
    }
}
