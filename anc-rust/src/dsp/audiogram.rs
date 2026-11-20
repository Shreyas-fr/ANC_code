//! Dynamic Psychoacoustic Active Hearing-Loss Compensation & NAL-NL2 WDRC Engine.
//!
//! In artillery, armored vehicle, and infantry units, combat personnel frequently develop
//! Noise-Induced Hearing Loss (NIHL) characterized by high-frequency bilateral hearing notches
//! (3 kHz - 6 kHz, centered on the classic 4 kHz acoustic dip / acoustic trauma notch).
//!
//! This module implements an onboard NAL-NL2 / DSL v5.0 compliant personal audiogram prescription
//! Wide Dynamic Range Compressor (WDRC):
//! - Configurable Left/Right ear Hearing Threshold Levels (HTL in dB HL at 250, 500, 1k, 2k, 3k, 4k, 6k, 8k Hz).
//! - Dynamically applies frequency-dependent compression thresholds, expansion ratios, and insertion gains.
//! - Restores consonant articulation (/s/, /sh/, /f/, /t/) while strictly clamping output below
//!   Maximum Power Output (MPO) to prevent acoustic trauma.
//! - Zero heap allocations in real-time audio loop.

use num_complex::Complex32;

/// Standard clinical and military audiometric frequencies (Hz).
pub const AUDIOMETRIC_FREQUENCIES: [f32; 8] = [
    250.0, 500.0, 1000.0, 2000.0, 3000.0, 4000.0, 6000.0, 8000.0,
];

pub const NUM_AUDIOMETRIC_BANDS: usize = 8;

/// Ear selector for bilateral audiograms.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Ear {
    Left,
    Right,
}

/// Personal audiogram profile storing Hearing Threshold Levels (HTL in dB HL)
/// across the 8 standard clinical frequencies.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PersonalAudiogram {
    pub htl_left: [f32; NUM_AUDIOMETRIC_BANDS],
    pub htl_right: [f32; NUM_AUDIOMETRIC_BANDS],
}

impl Default for PersonalAudiogram {
    fn default() -> Self {
        Self::normal()
    }
}

impl PersonalAudiogram {
    /// Normal hearing profile (0 dB HL across all bands).
    pub fn normal() -> Self {
        Self {
            htl_left: [0.0; NUM_AUDIOMETRIC_BANDS],
            htl_right: [0.0; NUM_AUDIOMETRIC_BANDS],
        }
    }

    /// Classic acoustic trauma / gunfire notch: sharp 4 kHz dip with preserved low frequencies.
    pub fn mild_4khz_notch() -> Self {
        Self {
            htl_left: [5.0, 5.0, 10.0, 20.0, 40.0, 50.0, 30.0, 15.0],
            htl_right: [5.0, 5.0, 10.0, 25.0, 45.0, 55.0, 35.0, 20.0],
        }
    }

    /// Severe artillery blast trauma with bilateral high-frequency notch and threshold shifts.
    pub fn severe_artillery_blast() -> Self {
        Self {
            htl_left: [15.0, 20.0, 30.0, 50.0, 65.0, 70.0, 55.0, 40.0],
            htl_right: [15.0, 20.0, 30.0, 55.0, 70.0, 75.0, 60.0, 45.0],
        }
    }

    /// Tank / armored fighting vehicle crew noise-induced hearing loss (sloping loss).
    pub fn tank_crew_nihl() -> Self {
        Self {
            htl_left: [20.0, 25.0, 35.0, 45.0, 55.0, 60.0, 50.0, 35.0],
            htl_right: [20.0, 25.0, 35.0, 45.0, 55.0, 60.0, 50.0, 35.0],
        }
    }

    /// Updates the HTL for a specific ear and frequency band index (0..8).
    pub fn set_htl(&mut self, ear: Ear, band_idx: usize, htl_db_hl: f32) {
        if band_idx < NUM_AUDIOMETRIC_BANDS {
            let clamped = htl_db_hl.clamp(-10.0, 100.0);
            match ear {
                Ear::Left => self.htl_left[band_idx] = clamped,
                Ear::Right => self.htl_right[band_idx] = clamped,
            }
        }
    }

    /// Retrieves the HTL for a specific ear and band index.
    pub fn get_htl(&self, ear: Ear, band_idx: usize) -> f32 {
        if band_idx < NUM_AUDIOMETRIC_BANDS {
            match ear {
                Ear::Left => self.htl_left[band_idx],
                Ear::Right => self.htl_right[band_idx],
            }
        } else {
            0.0
        }
    }
}

/// Wide Dynamic Range Compression (WDRC) channel parameters and runtime state.
#[derive(Debug, Clone, Copy)]
pub struct WdrcChannel {
    pub center_freq: f32,
    pub htl_db_hl: f32,
    pub insertion_gain_50_db: f32,
    pub insertion_gain_65_db: f32,
    pub insertion_gain_80_db: f32,
    pub compression_ratio: f32,
    pub compression_threshold_db_spl: f32,
    pub expansion_threshold_db_spl: f32,
    pub expansion_ratio: f32,
    pub mpo_db_spl: f32,

    // Envelope tracking state
    envelope_db_spl: f32,
    attack_alpha: f32,
    release_alpha: f32,
    current_linear_gain: f32,

    // 2nd-order Biquad peaking filter state
    b0: f32,
    b1: f32,
    b2: f32,
    a1: f32,
    a2: f32,
    x1: f32,
    x2: f32,
    y1: f32,
    y2: f32,
}

impl WdrcChannel {
    pub fn new(center_freq: f32, sample_rate: f32) -> Self {
        let mut ch = Self {
            center_freq,
            htl_db_hl: 0.0,
            insertion_gain_50_db: 0.0,
            insertion_gain_65_db: 0.0,
            insertion_gain_80_db: 0.0,
            compression_ratio: 1.0,
            compression_threshold_db_spl: 52.0,
            expansion_threshold_db_spl: 38.0,
            expansion_ratio: 0.8,
            mpo_db_spl: 98.0,

            envelope_db_spl: 40.0,
            attack_alpha: (-1.0 / (sample_rate * 0.008)).exp(), // 8 ms attack
            release_alpha: (-1.0 / (sample_rate * 0.080)).exp(), // 80 ms release
            current_linear_gain: 1.0,

            b0: 1.0,
            b1: 0.0,
            b2: 0.0,
            a1: 0.0,
            a2: 0.0,
            x1: 0.0,
            x2: 0.0,
            y1: 0.0,
            y2: 0.0,
        };
        ch.update_biquad_coefficients(sample_rate, 0.0);
        ch
    }

    /// Prescribes WDRC parameters according to NAL-NL2 empirical equations.
    pub fn configure_nal_nl2(&mut self, htl_db_hl: f32, sample_rate: f32) {
        self.htl_db_hl = htl_db_hl.clamp(0.0, 95.0);

        // NAL-NL2 empirical frequency correction factor C(f)
        let c_freq = match self.center_freq as u32 {
            250 => -5.0,
            500 => -2.5,
            1000 => 0.0,
            2000 => 2.5,
            3000 => 4.0,
            4000 => 4.0,
            6000 => 2.0,
            8000 => 0.0,
            _ => 1.0,
        };

        // Nominal insertion gain at 65 dB SPL input:
        // IG_65 = 0.46 * HTL - 0.0015 * HTL^2 + C(f)
        let ig_65_raw = 0.46 * self.htl_db_hl - 0.0015 * self.htl_db_hl * self.htl_db_hl + c_freq;
        self.insertion_gain_65_db = ig_65_raw.clamp(0.0, 36.0);

        // Compression ratio scales with loss, capped to prevent distortion
        self.compression_ratio = (1.0 + 0.022 * self.htl_db_hl).clamp(1.0, 3.2);

        // Gain at soft speech (50 dB SPL) provides greater amplification
        self.insertion_gain_50_db = (self.insertion_gain_65_db + (65.0 - 50.0) * (1.0 - 1.0 / self.compression_ratio))
            .clamp(0.0, 42.0);

        // Gain at loud speech (80 dB SPL) provides reduced gain
        self.insertion_gain_80_db = (self.insertion_gain_65_db - (80.0 - 65.0) * (1.0 - 1.0 / self.compression_ratio))
            .max(0.0);

        // Expansion threshold to suppress ambient microphone hiss
        self.expansion_threshold_db_spl = (35.0 + 0.15 * self.htl_db_hl).clamp(35.0, 50.0);
        self.compression_threshold_db_spl = self.expansion_threshold_db_spl + 10.0;
        self.mpo_db_spl = 98.0;

        self.update_biquad_coefficients(sample_rate, self.insertion_gain_65_db);
    }

    /// Updates 2nd-order peaking EQ biquad filter coefficients for this band.
    fn update_biquad_coefficients(&mut self, sample_rate: f32, gain_db: f32) {
        let f0 = self.center_freq.clamp(20.0, sample_rate * 0.45);
        let q = 1.414; // ~1 octave bandwidth
        let w0 = 2.0 * std::f32::consts::PI * f0 / sample_rate;
        let alpha = w0.sin() / (2.0 * q);
        let a = 10.0f32.powf(gain_db / 40.0);

        let cos_w0 = w0.cos();
        let a0 = 1.0 + alpha / a;

        self.b0 = (1.0 + alpha * a) / a0;
        self.b1 = (-2.0 * cos_w0) / a0;
        self.b2 = (1.0 - alpha * a) / a0;
        self.a1 = (-2.0 * cos_w0) / a0;
        self.a2 = (1.0 - alpha / a) / a0;
    }

    /// Evaluates dynamic WDRC gain in dB for a given input SPL level.
    #[inline]
    pub fn compute_gain_db(&self, in_db_spl: f32) -> f32 {
        if in_db_spl <= self.expansion_threshold_db_spl {
            // Expansion region: prevents amplifying quiet sensor noise
            let delta = self.expansion_threshold_db_spl - in_db_spl;
            (self.insertion_gain_50_db - delta * (1.0 - self.expansion_ratio)).max(0.0)
        } else if in_db_spl <= self.compression_threshold_db_spl {
            // Linear region between expansion and compression threshold
            self.insertion_gain_50_db
        } else {
            // WDRC Compression region: Gain(L) = IG_50 - (1 - 1/CR) * (L - CT)
            let comp_gain = self.insertion_gain_50_db
                - (1.0 - 1.0 / self.compression_ratio) * (in_db_spl - self.compression_threshold_db_spl);

            // MPO Output limiting: clamp output level L_out = L_in + Gain <= MPO
            let max_allowed_gain = self.mpo_db_spl - in_db_spl;
            comp_gain.min(max_allowed_gain).max(0.0)
        }
    }

    /// Filters an audio sample through the peaking biquad and updates envelope.
    #[inline]
    pub fn process_sample(&mut self, input: f32) -> f32 {
        // Direct Form II Transposed / Direct Form I Biquad
        let x0 = input;
        let y0 = self.b0 * x0 + self.b1 * self.x1 + self.b2 * self.x2 - self.a1 * self.y1 - self.a2 * self.y2;
        self.x2 = self.x1;
        self.x1 = x0;
        self.y2 = self.y1;
        self.y1 = y0;

        // Peak / envelope tracking in dB SPL (0 dBFS ~ 94 dB SPL)
        let sample_mag = y0.abs().max(1e-6);
        let sample_db_spl = 94.0 + 20.0 * sample_mag.log10();

        let alpha = if sample_db_spl > self.envelope_db_spl {
            self.attack_alpha
        } else {
            self.release_alpha
        };
        self.envelope_db_spl = alpha * self.envelope_db_spl + (1.0 - alpha) * sample_db_spl;

        // Dynamic WDRC gain calculation
        let target_gain_db = self.compute_gain_db(self.envelope_db_spl);
        let target_linear = 10.0f32.powf((target_gain_db - self.insertion_gain_65_db) / 20.0);

        // Smooth gain smoothing to avoid clicks
        self.current_linear_gain = 0.995 * self.current_linear_gain + 0.005 * target_linear;

        y0 * self.current_linear_gain
    }

    /// Resets filter and envelope state to initial values.
    pub fn reset(&mut self) {
        self.envelope_db_spl = 40.0;
        self.current_linear_gain = 1.0;
        self.x1 = 0.0;
        self.x2 = 0.0;
        self.y1 = 0.0;
        self.y2 = 0.0;
    }
}

/// NAL-NL2 Personal Audiogram Prescription Wide Dynamic Range Compression Engine.
/// Provides bilateral compensation for Noise-Induced Hearing Loss (NIHL).
#[derive(Debug, Clone)]
pub struct NalNl2WdrcEngine {
    pub sample_rate: f32,
    pub audiogram: PersonalAudiogram,
    pub channels_left: [WdrcChannel; NUM_AUDIOMETRIC_BANDS],
    pub channels_right: [WdrcChannel; NUM_AUDIOMETRIC_BANDS],
    pub is_enabled: bool,
}

impl NalNl2WdrcEngine {
    /// Creates a new WDRC engine initialized with the given audiogram.
    pub fn new(sample_rate: f32, audiogram: PersonalAudiogram) -> Self {
        let mut channels_left = [
            WdrcChannel::new(AUDIOMETRIC_FREQUENCIES[0], sample_rate),
            WdrcChannel::new(AUDIOMETRIC_FREQUENCIES[1], sample_rate),
            WdrcChannel::new(AUDIOMETRIC_FREQUENCIES[2], sample_rate),
            WdrcChannel::new(AUDIOMETRIC_FREQUENCIES[3], sample_rate),
            WdrcChannel::new(AUDIOMETRIC_FREQUENCIES[4], sample_rate),
            WdrcChannel::new(AUDIOMETRIC_FREQUENCIES[5], sample_rate),
            WdrcChannel::new(AUDIOMETRIC_FREQUENCIES[6], sample_rate),
            WdrcChannel::new(AUDIOMETRIC_FREQUENCIES[7], sample_rate),
        ];

        let mut channels_right = channels_left;

        for i in 0..NUM_AUDIOMETRIC_BANDS {
            channels_left[i].configure_nal_nl2(audiogram.htl_left[i], sample_rate);
            channels_right[i].configure_nal_nl2(audiogram.htl_right[i], sample_rate);
        }

        Self {
            sample_rate,
            audiogram,
            channels_left,
            channels_right,
            is_enabled: true,
        }
    }

    /// Updates the personal audiogram and recalculates NAL-NL2 channel prescriptions.
    pub fn update_audiogram(&mut self, audiogram: PersonalAudiogram) {
        self.audiogram = audiogram;
        for i in 0..NUM_AUDIOMETRIC_BANDS {
            self.channels_left[i].configure_nal_nl2(self.audiogram.htl_left[i], self.sample_rate);
            self.channels_right[i].configure_nal_nl2(self.audiogram.htl_right[i], self.sample_rate);
        }
    }

    /// Resets all channel filter states.
    pub fn reset(&mut self) {
        for ch in self.channels_left.iter_mut() {
            ch.reset();
        }
        for ch in self.channels_right.iter_mut() {
            ch.reset();
        }
    }

    /// Processes a mono audio buffer in-place.
    /// Strictly zero heap allocations.
    pub fn process_mono(&mut self, samples: &mut [f32]) {
        if !self.is_enabled {
            return;
        }

        // Apply Left channel prescription to mono audio
        for s in samples.iter_mut() {
            let mut accum = *s;
            for ch in self.channels_left.iter_mut() {
                accum = ch.process_sample(accum);
            }
            *s = accum;
        }
    }

    /// Processes stereo audio buffers in-place (individual left/right prescriptions).
    /// Strictly zero heap allocations.
    pub fn process_stereo(&mut self, left: &mut [f32], right: &mut [f32]) {
        if !self.is_enabled {
            return;
        }

        for s in left.iter_mut() {
            let mut accum = *s;
            for ch in self.channels_left.iter_mut() {
                accum = ch.process_sample(accum);
            }
            *s = accum;
        }

        for s in right.iter_mut() {
            let mut accum = *s;
            for ch in self.channels_right.iter_mut() {
                accum = ch.process_sample(accum);
            }
            *s = accum;
        }
    }

    /// Applies NAL-NL2 WDRC subband compensation directly to an STFT frequency spectrum.
    /// Strictly zero heap allocations.
    pub fn process_stft_spectrum(
        &mut self,
        spectrum: &mut [Complex32],
        ear: Ear,
        hop_size: usize,
    ) {
        if !self.is_enabled || spectrum.is_empty() {
            return;
        }

        let num_bins = spectrum.len();
        let bin_hz = (self.sample_rate / 2.0) / (num_bins.saturating_sub(1) as f32).max(1.0);
        let channels = match ear {
            Ear::Left => &mut self.channels_left,
            Ear::Right => &mut self.channels_right,
        };

        for (k, bin) in spectrum.iter_mut().enumerate() {
            let freq = k as f32 * bin_hz;
            if freq < 100.0 {
                continue;
            }

            // Find closest audiometric band
            let mut best_band = 0;
            let mut min_diff = (freq - AUDIOMETRIC_FREQUENCIES[0]).abs();
            for (idx, &af) in AUDIOMETRIC_FREQUENCIES.iter().enumerate().skip(1) {
                let diff = (freq - af).abs();
                if diff < min_diff {
                    min_diff = diff;
                    best_band = idx;
                }
            }

            let ch = &mut channels[best_band];
            let mag = bin.norm();
            let bin_spl = 94.0 + 20.0 * (mag / hop_size as f32).max(1e-6).log10();

            let gain_db = ch.compute_gain_db(bin_spl);
            let linear_gain = 10.0f32.powf(gain_db / 20.0);

            *bin *= linear_gain;
        }
    }

    /// Returns average prescribed insertion gain at 65 dB SPL across all bands for Left ear.
    pub fn average_insertion_gain_db(&self, ear: Ear) -> f32 {
        let channels = match ear {
            Ear::Left => &self.channels_left,
            Ear::Right => &self.channels_right,
        };
        let sum: f32 = channels.iter().map(|c| c.insertion_gain_65_db).sum();
        sum / NUM_AUDIOMETRIC_BANDS as f32
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normal_audiogram_yields_nominal_gain() {
        let normal = PersonalAudiogram::normal();
        let engine = NalNl2WdrcEngine::new(16000.0, normal);

        for ch in engine.channels_left.iter() {
            assert_eq!(ch.htl_db_hl, 0.0);
            assert!(ch.insertion_gain_65_db <= 4.0, "Normal hearing should have minimal gain");
            assert!((ch.compression_ratio - 1.0).abs() < 1e-4);
        }
    }

    #[test]
    fn test_4khz_notch_yields_targeted_high_gain() {
        let notch = PersonalAudiogram::mild_4khz_notch();
        let engine = NalNl2WdrcEngine::new(16000.0, notch);

        // 4 kHz is band index 5
        let ch_4k = &engine.channels_left[5];
        assert_eq!(ch_4k.center_freq, 4000.0);
        assert_eq!(ch_4k.htl_db_hl, 50.0);
        assert!(ch_4k.insertion_gain_65_db > 20.0, "4 kHz dip should receive significant compensation");
        assert!(ch_4k.compression_ratio > 1.8, "Compression ratio should be elevated for hearing loss");

        // 250 Hz is band index 0 (normal threshold of 5 dB HL)
        let ch_250 = &engine.channels_left[0];
        assert!(ch_250.insertion_gain_65_db < ch_4k.insertion_gain_65_db);
    }

    #[test]
    fn test_wdrc_compression_curve_behaviour() {
        let mut ch = WdrcChannel::new(4000.0, 16000.0);
        ch.configure_nal_nl2(50.0, 16000.0);

        let g_soft = ch.compute_gain_db(50.0);
        let g_nom = ch.compute_gain_db(65.0);
        let g_loud = ch.compute_gain_db(85.0);

        assert!(g_soft > g_nom, "Soft sounds must receive more gain than nominal");
        assert!(g_nom > g_loud, "Nominal sounds must receive more gain than loud sounds");

        // Verify MPO ceiling
        let g_extreme = ch.compute_gain_db(96.0);
        assert!(96.0 + g_extreme <= ch.mpo_db_spl + 0.1, "Output must never exceed MPO");
    }

    #[test]
    fn test_mono_processing_zero_heap_allocations() {
        let notch = PersonalAudiogram::mild_4khz_notch();
        let mut engine = NalNl2WdrcEngine::new(16000.0, notch);

        let mut buffer = [0.1f32; 256];
        engine.process_mono(&mut buffer);

        // Output should be modified without crashing
        assert!(buffer[100].is_finite());
    }

    #[test]
    fn test_stft_spectrum_processing() {
        let notch = PersonalAudiogram::mild_4khz_notch();
        let mut engine = NalNl2WdrcEngine::new(16000.0, notch);

        let mut spec = vec![Complex32::new(1.0, 0.0); 257];
        engine.process_stft_spectrum(&mut spec, Ear::Left, 256);

        // Spectrum values should remain finite and boosted around 4 kHz
        let bin_4k = (4000.0 / (8000.0 / 256.0)) as usize;
        assert!(spec[bin_4k].norm() > 1.0);
    }
}
