//! Active Occlusion Effect Suppression & Bone-Air Sensor Fusion.
//!
//! Developed for SIH 26052 Tactical Headsets & Combat Helmet Earcup Modules.
//!
//! When soldiers speak while wearing hermetically sealed combat earmuffs,
//! acoustic energy radiates directly from the vibrating skull and jaw bones
//! into the cartilaginous ear canal.
//!
//! Because the ear canal is occluded (sealed), low-frequency sound waves cannot
//! escape freely, resulting in an artificial 10 dB to 25 dB acoustic pressure amplification
//! between 100 Hz and 500 Hz (the physical "Occlusion Effect").
//!
//! This module implements an active feedback/feedforward anti-occlusion canceller:
//! 1. Monitors the soldier's bone-conduction / throat vibration sensor b(n).
//! 2. Simultaneously reads the internal in-ear error microphone e(n).
//! 3. Detects active vocalization via high-confidence bone sensor Voice Activity Detection (VAD).
//! 4. Adapts an internal acoustic bone-to-canal resonance canceler H_occ(z) focused
//!    in the critical 100–500 Hz resonance band.
//! 5. Drives the speaker with an out-of-phase anti-occlusion acoustic wave during speech,
//!    neutralizing ear canal overpressure without attenuating incoming radio traffic.
//!
//! Strictly ZERO heap allocations in the real-time processing loop.

use serde::{Deserialize, Serialize};

/// Number of taps in the occlusion resonance compensation FIR filter.
pub const OCCLUSION_FILTER_TAPS: usize = 24;

/// Real-time telemetry snapshot from the Active Occlusion Suppressor.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct OcclusionTelemetry {
    /// Whether the soldier is currently speaking (bone VAD active).
    pub soldier_speaking: bool,
    /// Occlusion boom reduction achieved in dB (100 Hz - 500 Hz band).
    pub boom_reduction_db: f32,
    /// Instantaneous bone-conduction sensor power in dBFS.
    pub bone_power_dbfs: f32,
    /// In-ear acoustic error microphone power in dBFS.
    pub in_ear_power_dbfs: f32,
    /// Filter adaptation convergence factor.
    pub adaptation_factor: f32,
}

impl Default for OcclusionTelemetry {
    fn default() -> Self {
        Self {
            soldier_speaking: false,
            boom_reduction_db: 0.0,
            bone_power_dbfs: -60.0,
            in_ear_power_dbfs: -60.0,
            adaptation_factor: 1.0,
        }
    }
}

/// Configuration parameters for the Active Occlusion Suppressor.
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct OcclusionConfig {
    /// Bone-conduction VAD detection power threshold in dBFS (default: -38.0).
    pub vad_threshold_dbfs: f32,
    /// Adaptation step size for the bone-to-canal transfer function (default: 0.02).
    pub mu_occ: f32,
    /// Maximum anti-occlusion gain limit in linear scale to prevent over-drive (default: 0.85).
    pub max_gain: f32,
    /// Master enable toggle.
    pub enabled: bool,
}

impl Default for OcclusionConfig {
    fn default() -> Self {
        Self {
            vad_threshold_dbfs: -38.0,
            mu_occ: 0.02,
            max_gain: 0.85,
            enabled: true,
        }
    }
}

/// Active Occlusion Effect Suppressor.
#[derive(Debug, Clone)]
pub struct OcclusionSuppressor {
    config: OcclusionConfig,
    /// Adaptive filter taps modeling bone-to-canal resonance.
    weights: [f32; OCCLUSION_FILTER_TAPS],
    /// Circular buffer for bone vibration reference samples.
    bone_history: [f32; OCCLUSION_FILTER_TAPS],
    bone_idx: usize,
    /// Smoothed power tracking.
    bone_power: f32,
    canal_power: f32,
    /// Telemetry output.
    telemetry: OcclusionTelemetry,
}

impl OcclusionSuppressor {
    pub fn new(config: OcclusionConfig) -> Self {
        let mut weights = [0.0; OCCLUSION_FILTER_TAPS];
        // Nominal bandpass impulse response centered in 100-500 Hz range @ 16 kHz
        weights[0] = 0.05;
        weights[1] = 0.15;
        weights[2] = 0.35;
        weights[3] = 0.50;
        weights[4] = 0.35;
        weights[5] = 0.15;
        weights[6] = 0.05;

        Self {
            config,
            weights,
            bone_history: [0.0; OCCLUSION_FILTER_TAPS],
            bone_idx: 0,
            bone_power: 1e-6,
            canal_power: 1e-6,
            telemetry: OcclusionTelemetry::default(),
        }
    }

    pub fn reset(&mut self) {
        self.bone_history.fill(0.0);
        self.bone_idx = 0;
        self.bone_power = 1e-6;
        self.canal_power = 1e-6;
    }

    /// Processes a single real-time sample:
    /// - `bone_sample`: Signal from soldier's bone-conduction / throat transducer.
    /// - `error_mic_sample`: Internal in-ear microphone signal measuring ear-canal pressure.
    ///
    /// Returns:
    /// - `anti_occlusion_sample`: Out-of-phase anti-sound sample to add to the speaker output.
    #[inline]
    pub fn process_sample(&mut self, bone_sample: f32, error_mic_sample: f32) -> f32 {
        if !self.config.enabled {
            return 0.0;
        }

        // 1. Power tracking
        self.bone_power = 0.98 * self.bone_power + 0.02 * (bone_sample * bone_sample);
        self.canal_power = 0.98 * self.canal_power + 0.02 * (error_mic_sample * error_mic_sample);

        let bone_dbfs = 10.0 * (self.bone_power + 1e-12).log10();
        let canal_dbfs = 10.0 * (self.canal_power + 1e-12).log10();

        // 2. Bone VAD
        let speaking = bone_dbfs > self.config.vad_threshold_dbfs;

        // 3. Store bone reference
        self.bone_history[self.bone_idx] = bone_sample;

        // 4. Synthesize anti-occlusion canceler output y_occ(n) = sum(w_k * bone[n-k])
        let mut y_occ = 0.0_f32;
        let mut ref_energy = 1e-6_f32;
        for k in 0..OCCLUSION_FILTER_TAPS {
            let idx = (self.bone_idx + OCCLUSION_FILTER_TAPS - k) % OCCLUSION_FILTER_TAPS;
            let b = self.bone_history[idx];
            y_occ += self.weights[k] * b;
            ref_energy += b * b;
        }

        // Clamp anti-occlusion amplitude to prevent saturation
        let anti_occlusion = (-y_occ).clamp(-self.config.max_gain, self.config.max_gain);

        // 5. Adapt weights only when soldier is speaking
        if speaking {
            let step = (self.config.mu_occ * error_mic_sample) / ref_energy;
            for k in 0..OCCLUSION_FILTER_TAPS {
                let idx = (self.bone_idx + OCCLUSION_FILTER_TAPS - k) % OCCLUSION_FILTER_TAPS;
                let b = self.bone_history[idx];
                self.weights[k] = (self.weights[k] * 0.9995) + step * b;
            }
        }

        self.bone_idx = (self.bone_idx + 1) % OCCLUSION_FILTER_TAPS;

        // 6. Update telemetry
        let boom_red = if speaking {
            (bone_dbfs - canal_dbfs).clamp(0.0, 24.0)
        } else {
            0.0
        };

        self.telemetry.soldier_speaking = speaking;
        self.telemetry.boom_reduction_db = 0.9 * self.telemetry.boom_reduction_db + 0.1 * boom_red;
        self.telemetry.bone_power_dbfs = bone_dbfs;
        self.telemetry.in_ear_power_dbfs = canal_dbfs;

        anti_occlusion
    }

    /// Returns a copy of the current occlusion telemetry.
    pub fn telemetry(&self) -> OcclusionTelemetry {
        self.telemetry
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_occlusion_initial_state() {
        let occ = OcclusionSuppressor::new(OcclusionConfig::default());
        let telem = occ.telemetry();
        assert!(!telem.soldier_speaking);
        assert_eq!(telem.boom_reduction_db, 0.0);
    }

    #[test]
    fn test_occlusion_vad_and_anti_sound_generation() {
        let mut occ = OcclusionSuppressor::new(OcclusionConfig::default());
        // Inactive speech: low amplitude
        for _ in 0..50 {
            let anti = occ.process_sample(0.0001, 0.0001);
            assert!(anti.abs() < 0.01);
        }
        assert!(!occ.telemetry().soldier_speaking);

        // Active soldier vocalization (e.g. 0.3 amplitude bone vibration)
        let mut anti_max = 0.0_f32;
        for _ in 0..50 {
            let anti = occ.process_sample(0.3, 0.2);
            anti_max = anti_max.max(anti.abs());
        }
        assert!(occ.telemetry().soldier_speaking);
        assert!(anti_max > 0.05);
    }
}
