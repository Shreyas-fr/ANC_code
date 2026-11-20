//! Dynamic Psychoacoustic Inverse-Lombard Vocal Fatigue & Strain Compensator.
//!
//! In extreme combat noise environments (>100 dBA in armored fighting vehicles,
//! tanks, and rotorcraft), soldiers involuntarily shout due to the physiological
//! Lombard reflex:
//! - Fundamental voice pitch (F0) shifts upwards by +30 to +60 Hz.
//! - High-frequency spectral tilt flattens (excessive harsh acoustic energy in 1.5–5 kHz).
//! - Vocal tract formants migrate upwards due to widened jaw opening, producing
//!   a strained, pinched vocal timbre that fatigues intercom listeners over time.
//!
//! Once ambient combat noise is suppressed by ANC, this shouted voice sounds unnaturally
//! harsh and strident over radio headsets. The Inverse-Lombard Compensator:
//! 1. Detects Lombard strain in real-time from pitch elevation Delta F0, formant centroid migration,
//!    and spectral tilt flattening.
//! 2. Dynamically applies subtle inverse spectral tilt and vocal tract formant relaxation,
//!    restoring a natural, relaxed speaking tone for squad intercom clarity without degrading
//!    speech intelligibility.
//!
//! Zero heap allocations in the real-time processing loop.

use num_complex::Complex32;

/// Configuration for the Inverse-Lombard Vocal Fatigue & Strain Compensator.
#[derive(Debug, Clone)]
pub struct LombardConfig {
    pub sample_rate: f32,
    pub num_bins: usize,
    pub baseline_f0_hz: f32,
    pub max_tilt_attenuation_db: f32,
    pub formant_relaxation_factor: f32,
    pub adaptation_rate: f32,
    pub enabled: bool,
}

impl Default for LombardConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000.0,
            num_bins: 257,
            baseline_f0_hz: 130.0,
            max_tilt_attenuation_db: 5.0,
            formant_relaxation_factor: 0.35,
            adaptation_rate: 0.08,
            enabled: true,
        }
    }
}

/// Real-time Lombard strain biomarkers and compensation telemetry.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct LombardTelemetry {
    /// Tracked physiological vocal strain index (0.0 = relaxed speech, 1.0 = maximum shout/strain).
    pub strain_index: f32,
    /// Detected elevation above nominal fundamental baseline (in Hz).
    pub pitch_elevation_hz: f32,
    /// Estimated spectral tilt roll-off in dB/octave (flatter tilt indicates shouted voice).
    pub spectral_tilt_db_oct: f32,
    /// Spectral centroid in Hz (shifts upwards under Lombard jaw deformation).
    pub centroid_hz: f32,
    /// Dynamic inverse-tilt high-frequency attenuation applied (in dB).
    pub tilt_correction_db: f32,
}

impl Default for LombardTelemetry {
    fn default() -> Self {
        Self {
            strain_index: 0.0,
            pitch_elevation_hz: 0.0,
            spectral_tilt_db_oct: -6.0,
            centroid_hz: 1200.0,
            tilt_correction_db: 0.0,
        }
    }
}

/// Dynamic Psychoacoustic Inverse-Lombard Vocal Fatigue & Strain Compensator.
pub struct InverseLombardCompensator {
    config: LombardConfig,
    smoothed_strain: f32,
    smoothed_centroid: f32,
    smoothed_tilt: f32,
    smoothed_f0: f32,
    gain_scratch: Vec<f32>,
}

impl InverseLombardCompensator {
    /// Creates a new InverseLombardCompensator with pre-allocated scratch memory.
    pub fn new(config: LombardConfig) -> Self {
        let num_bins = config.num_bins;
        Self {
            config,
            smoothed_strain: 0.0,
            smoothed_centroid: 1200.0,
            smoothed_tilt: -6.0,
            smoothed_f0: 130.0,
            gain_scratch: vec![1.0; num_bins],
        }
    }

    /// Resets all internal smoothing filters and biomarker trackers.
    pub fn reset(&mut self) {
        self.smoothed_strain = 0.0;
        self.smoothed_centroid = 1200.0;
        self.smoothed_tilt = -6.0;
        self.smoothed_f0 = self.config.baseline_f0_hz;
        self.gain_scratch.fill(1.0);
    }

    /// Dynamically enables or disables inverse-Lombard compensation.
    pub fn set_enabled(&mut self, enabled: bool) {
        self.config.enabled = enabled;
    }

    /// Returns whether the compensator is currently active.
    pub fn is_enabled(&self) -> bool {
        self.config.enabled
    }

    /// Sets the nominal baseline F0 (e.g. 120 Hz male, 210 Hz female, or tracked quiet baseline).
    pub fn set_baseline_f0(&mut self, baseline_hz: f32) {
        self.config.baseline_f0_hz = baseline_hz.clamp(70.0, 350.0);
    }

    /// Returns the current smoothed vocal strain index (0.0 to 1.0).
    pub fn current_strain_index(&self) -> f32 {
        self.smoothed_strain
    }

    /// Processes a single STFT complex spectrum frame in-place.
    ///
    /// - `spec`: STFT spectrum of enhanced or primary microphone speech (in/out).
    /// - `f0_opt`: Optional fundamental frequency from pitch tracker (in Hz).
    /// - `spp_opt`: Optional speech presence probability per bin.
    ///
    /// Strictly zero heap allocations in the audio loop.
    pub fn process_frame(
        &mut self,
        spec: &mut [Complex32],
        f0_opt: Option<f32>,
        spp_opt: Option<&[f32]>,
    ) -> LombardTelemetry {
        assert_eq!(spec.len(), self.config.num_bins);

        if !self.config.enabled {
            return LombardTelemetry {
                strain_index: self.smoothed_strain,
                pitch_elevation_hz: 0.0,
                spectral_tilt_db_oct: self.smoothed_tilt,
                centroid_hz: self.smoothed_centroid,
                tilt_correction_db: 0.0,
            };
        }

        let num_bins = self.config.num_bins;
        let n_fft = (num_bins - 1) * 2;
        let bin_hz = self.config.sample_rate / n_fft as f32;

        // 1. Compute acoustic biomarkers: Energy, Spectral Centroid, and Spectral Tilt
        let mut total_energy = 0.0f32;
        let mut weighted_freq_energy = 0.0f32;
        let mut low_band_energy = 1e-8f32; // 200 Hz - 1000 Hz (vocal body)
        let mut high_band_energy = 1e-8f32; // 1500 Hz - 4000 Hz (strained harmonic splash)

        let use_spp = if let Some(spp) = spp_opt {
            let mean = spp.iter().copied().sum::<f32>() / spp.len().max(1) as f32;
            mean > 0.05
        } else {
            false
        };

        for (k, c) in spec.iter().enumerate() {
            let freq = k as f32 * bin_hz;
            let pwr = c.norm_sqr();

            // Speech presence weighting if available and active
            let weight = if use_spp {
                spp_opt.unwrap()[k].max(0.15)
            } else {
                1.0
            };
            let effective_pwr = pwr * weight;

            total_energy += effective_pwr;
            weighted_freq_energy += freq * effective_pwr;

            if (200.0..=1000.0).contains(&freq) {
                low_band_energy += effective_pwr;
            } else if (1500.0..=4000.0).contains(&freq) {
                high_band_energy += effective_pwr;
            }
        }

        // Check if active speech is present
        let is_speech = total_energy > 1e-4;

        let inst_centroid = if is_speech && total_energy > 1e-6 {
            weighted_freq_energy / total_energy
        } else {
            1200.0
        };

        // Spectral tilt estimation: ratio of high-to-low band energy in dB
        // Relaxed speech: high band is typically -12 to -18 dB below low band (-6 dB/oct roll-off).
        // Shouted Lombard speech: high band is elevated, approaching -3 to -6 dB below low band.
        let inst_tilt = if is_speech {
            let band_ratio_db = 10.0 * (high_band_energy / low_band_energy).max(1e-6).log10();
            (band_ratio_db / 2.0).clamp(-18.0, 0.0)
        } else {
            -12.0
        };

        // Track F0 elevation
        let (inst_f0, delta_f0) = if let Some(f0) = f0_opt {
            if f0 > 60.0 && f0 < 450.0 && is_speech {
                let d_f0 = (f0 - self.config.baseline_f0_hz).max(0.0);
                (f0, d_f0)
            } else {
                (self.smoothed_f0, 0.0)
            }
        } else {
            (self.smoothed_f0, 0.0)
        };

        // Smooth biomarkers with leaky integrator
        let alpha = if is_speech {
            self.config.adaptation_rate
        } else {
            0.05
        };
        self.smoothed_centroid = (1.0 - alpha) * self.smoothed_centroid + alpha * inst_centroid;
        self.smoothed_tilt = (1.0 - alpha) * self.smoothed_tilt + alpha * inst_tilt;
        self.smoothed_f0 = (1.0 - alpha) * self.smoothed_f0 + alpha * inst_f0;

        // 2. Multi-Biomarker Lombard Vocal Strain Index (0.0 to 1.0)
        // Strain factors:
        // - Pitch elevation factor: Delta F0 from 0 to 50+ Hz
        let f0_factor = (delta_f0 / 50.0).clamp(0.0, 1.0);
        // - Centroid migration factor: nominal ~1100-1300 Hz -> Lombard >1800 Hz
        let centroid_factor = ((self.smoothed_centroid - 1300.0) / 700.0).clamp(0.0, 1.0);
        // - Tilt flattening factor: -12 dB/oct (relaxed) -> -3 dB/oct (shouted)
        let tilt_factor = ((self.smoothed_tilt - (-12.0)) / 8.0).clamp(0.0, 1.0);

        let raw_strain = if is_speech {
            0.35 * f0_factor + 0.35 * centroid_factor + 0.30 * tilt_factor
        } else {
            0.0
        };
        self.smoothed_strain = if is_speech {
            (1.0 - alpha) * self.smoothed_strain + alpha * raw_strain
        } else {
            0.0
        };
        let strain = self.smoothed_strain.clamp(0.0, 1.0);

        // 3. Synthesize Inverse-Lombard Compensation Filter Curve
        // - High-frequency gentle de-tilting: restores natural roll-off above 1.2 kHz
        // - Formant peak relaxation: softens upward-shifted F1/F2 resonant harshness
        let max_atten_lin = 10.0f32.powf(-self.config.max_tilt_attenuation_db / 20.0);
        let current_atten_db = strain * self.config.max_tilt_attenuation_db;

        for k in 0..num_bins {
            let freq = k as f32 * bin_hz;

            let mut gain = 1.0f32;

            if freq > 1200.0 {
                // Gentle logarithmic shelf attenuation up to Nyquist
                let freq_norm =
                    ((freq - 1200.0) / (self.config.sample_rate * 0.5 - 1200.0)).clamp(0.0, 1.0);
                let tilt_gain = 1.0 - strain * (1.0 - max_atten_lin) * freq_norm;
                gain *= tilt_gain;
            }

            // Formant relaxation around 1800 - 2800 Hz (migrated Lombard F2/F3 region)
            if (1600.0..=3000.0).contains(&freq) {
                let dist = ((freq - 2200.0) / 600.0).abs().min(1.0);
                let formant_bell = (1.0 - dist * dist).max(0.0);
                let formant_relax =
                    1.0 - strain * self.config.formant_relaxation_factor * formant_bell;
                gain *= formant_relax;
            }

            self.gain_scratch[k] = gain.clamp(0.40, 1.0);
        }

        // Apply gain curve in-place to complex spectrum
        for k in 0..num_bins {
            spec[k] *= self.gain_scratch[k];
        }

        LombardTelemetry {
            strain_index: strain,
            pitch_elevation_hz: delta_f0,
            spectral_tilt_db_oct: self.smoothed_tilt,
            centroid_hz: self.smoothed_centroid,
            tilt_correction_db: current_atten_db,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_lombard_silence_passthrough() {
        let cfg = LombardConfig::default();
        let mut compensator = InverseLombardCompensator::new(cfg);
        let mut spec = vec![Complex32::default(); 257];

        let telem = compensator.process_frame(&mut spec, None, None);
        assert_eq!(telem.strain_index, 0.0);
        assert_eq!(telem.tilt_correction_db, 0.0);

        for c in &spec {
            assert_eq!(c.norm_sqr(), 0.0);
        }
    }

    #[test]
    fn test_lombard_detects_shouting_and_relaxes_formants() {
        let cfg = LombardConfig {
            adaptation_rate: 0.50, // fast adaptation for test
            ..Default::default()
        };
        let mut compensator = InverseLombardCompensator::new(cfg);

        // Simulate shouted Lombard voice:
        // Elevated F0 = 190 Hz (baseline 130 Hz -> +60 Hz elevation)
        // High energy concentrated around 2200 Hz (upward-migrated centroid)
        let num_bins = 257;
        let mut spec = vec![Complex32::new(0.01, 0.0); num_bins];
        // Inject strong high formant cluster
        for k in 30..70 {
            spec[k] = Complex32::new(1.2, 0.5);
        }

        let initial_high_bin_pwr = spec[40].norm_sqr();

        // Process multiple frames of sustained shouted speech
        let mut last_telem = LombardTelemetry::default();
        for _ in 0..10 {
            last_telem = compensator.process_frame(&mut spec, Some(190.0), None);
        }

        assert!(
            last_telem.strain_index > 0.40,
            "Expected strain index > 0.40 for shouted voice, got {:.3}",
            last_telem.strain_index
        );
        assert!(
            last_telem.tilt_correction_db > 1.5,
            "Expected tilt correction > 1.5 dB, got {:.2} dB",
            last_telem.tilt_correction_db
        );
        assert!(
            spec[40].norm_sqr() < initial_high_bin_pwr,
            "Expected high-frequency formant energy to be relaxed/attenuated"
        );
    }

    #[test]
    fn test_lombard_reset() {
        let mut compensator = InverseLombardCompensator::new(LombardConfig::default());
        compensator.smoothed_strain = 0.85;
        compensator.reset();
        assert_eq!(compensator.current_strain_index(), 0.0);
    }

    #[test]
    fn test_lombard_bypassed_when_disabled() {
        let cfg = LombardConfig {
            enabled: false,
            ..Default::default()
        };
        let mut compensator = InverseLombardCompensator::new(cfg);
        let mut spec = vec![Complex32::new(1.0, 0.5); 257];
        let original_val = spec[50];

        let telem = compensator.process_frame(&mut spec, Some(220.0), None);
        assert_eq!(telem.tilt_correction_db, 0.0);
        assert_eq!(spec[50], original_val);
    }
}
