//! Acoustic Blast Wave Air-Overpressure & MIL-STD-1474E Impulse Exposure Meter.
//!
//! Models physical acoustic blast physics (Friedlander shock waves) and monitors
//! cumulative acoustic impulse noise exposure against MIL-STD-1474E Department of Defense
//! criteria for weapon firing, artillery concussions, and explosive breeches.
//!
//! Physical Relationships:
//! - Sound Pressure Level to Air Overpressure:
//!   `p_peak (Pa) = 20e-6 * 10^(SPL / 20)`
//!   `p_peak (PSI) = p_peak (Pa) / 6894.757`
//! - Friedlander shock wave profile:
//!   `p(t) = P_peak * (1 - t / t_plus) * exp(-b * t / t_plus)`
//! - MIL-STD-1474E Cumulative Impulse Dose:
//!   Calculates permissible daily impulses based on peak overpressure and A-duration (t_plus),
//!   incorporating active earcup noise attenuation.
//! - Strictly zero heap allocations in the real-time sample processing loop.

use serde::{Deserialize, Serialize};

/// Standard conversion constant: Pascals to Pounds per Square Inch (PSI).
pub const PASCALS_PER_PSI: f32 = 6894.757;

/// Reference sound pressure in air: 20 micropascals (0 dB SPL).
pub const P_REF_PASCALS: f32 = 20.0e-6;

/// Capacity of recent blast events history ring buffer.
pub const BLAST_HISTORY_CAPACITY: usize = 16;

/// MIL-STD-1474E Tactical Blast Hazard Status.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
pub enum BlastHazardStatus {
    /// Safe acoustic environment; cumulative blast exposure < 50% daily limit.
    #[default]
    Nominal,
    /// Elevated blast exposure (50% - 100% daily limit); hearing protection required.
    Caution,
    /// Daily impulse noise limit exceeded (> 100%) or dangerous concussion (> 175 dB SPL).
    Hazardous,
}

/// Recorded metadata for a single high-energy acoustic blast shock impulse.
#[derive(Debug, Clone, Copy, Default, PartialEq, Serialize, Deserialize)]
pub struct BlastEvent {
    pub frame_index: u64,
    pub peak_spl_db: f32,
    pub peak_overpressure_pa: f32,
    pub peak_overpressure_psi: f32,
    pub a_duration_ms: f32,
    pub dose_pct: f32,
}

/// Real-time blast and impulse exposure telemetry.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct BlastTelemetry {
    pub peak_spl_db: f32,
    pub peak_overpressure_pa: f32,
    pub peak_overpressure_psi: f32,
    pub current_a_duration_ms: f32,
    pub daily_impulse_count: u32,
    pub cumulative_dose_pct: f32,
    pub hazard_status: BlastHazardStatus,
    pub last_blast_event: BlastEvent,
}

impl Default for BlastTelemetry {
    fn default() -> Self {
        Self {
            peak_spl_db: 94.0,
            peak_overpressure_pa: 1.0,
            peak_overpressure_psi: 1.0 / PASCALS_PER_PSI,
            current_a_duration_ms: 0.0,
            daily_impulse_count: 0,
            cumulative_dose_pct: 0.0,
            hazard_status: BlastHazardStatus::Nominal,
            last_blast_event: BlastEvent::default(),
        }
    }
}

/// Configuration parameters for the blast wave overpressure meter.
#[derive(Debug, Clone, PartialEq)]
pub struct BlastMeterConfig {
    pub sample_rate: f32,
    pub blast_detection_threshold_db_spl: f32,
    pub earcup_attenuation_db: f32,
    pub daily_dose_limit: f32,
}

impl Default for BlastMeterConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000.0,
            blast_detection_threshold_db_spl: 140.0, // 200 Pa threshold for blast impulse
            earcup_attenuation_db: 32.0, // Tactical dual-layer earcup + active ANC attenuation
            daily_dose_limit: 100.0, // 100% MIL-STD-1474E allowable daily dose
        }
    }
}

/// Real-Time Acoustic Blast Wave Air-Overpressure & MIL-STD-1474E Meter.
#[derive(Debug, Clone)]
pub struct BlastImpulseMeter {
    pub config: BlastMeterConfig,
    pub telemetry: BlastTelemetry,

    // Circular ring buffer of historical blast events
    blast_history: [BlastEvent; BLAST_HISTORY_CAPACITY],
    history_write_idx: usize,

    // Tracking state for currently ongoing impulse shock
    is_in_blast: bool,
    blast_peak_sample: f32,
    blast_sample_count: u32,
    frame_counter: u64,
}

impl BlastImpulseMeter {
    /// Creates a new BlastImpulseMeter.
    pub fn new(config: BlastMeterConfig) -> Self {
        Self {
            config,
            telemetry: BlastTelemetry::default(),
            blast_history: [BlastEvent::default(); BLAST_HISTORY_CAPACITY],
            history_write_idx: 0,
            is_in_blast: false,
            blast_peak_sample: 0.0,
            blast_sample_count: 0,
            frame_counter: 0,
        }
    }

    /// Resets exposure accumulators and blast history.
    pub fn reset(&mut self) {
        self.telemetry = BlastTelemetry::default();
        self.blast_history = [BlastEvent::default(); BLAST_HISTORY_CAPACITY];
        self.history_write_idx = 0;
        self.is_in_blast = false;
        self.blast_peak_sample = 0.0;
        self.blast_sample_count = 0;
        self.frame_counter = 0;
    }

    /// Converts raw audio sample magnitude to physical peak air overpressure in Pascals.
    /// Assumes calibrated 0 dBFS nominal corresponds to 120 dB SPL RMS (or 140 dB SPL peak).
    #[inline]
    pub fn sample_to_pascals(&self, sample: f32) -> f32 {
        let mag = sample.abs().max(1e-7);
        // Calibration: 1.0 peak amplitude = 140 dB SPL = 200 Pa
        mag * 200.0
    }

    /// Converts sound pressure in Pascals to dB SPL re 20 uPa.
    #[inline]
    pub fn pascals_to_db_spl(&self, pascals: f32) -> f32 {
        20.0 * (pascals.max(1e-7) / P_REF_PASCALS).log10()
    }

    /// Converts Pascals to Pounds per Square Inch (PSI).
    #[inline]
    pub fn pascals_to_psi(&self, pascals: f32) -> f32 {
        pascals / PASCALS_PER_PSI
    }

    /// Processes a block of audio samples and monitors blast overpressure & MIL-STD-1474E dose.
    /// Strictly zero heap allocations.
    pub fn process_frame(&mut self, samples: &[f32]) {
        self.frame_counter += 1;
        let mut frame_peak_sample = 0.0f32;

        for &s in samples {
            let abs_s = s.abs();
            if abs_s > frame_peak_sample {
                frame_peak_sample = abs_s;
            }

            let s_pa = self.sample_to_pascals(abs_s);
            let s_spl = self.pascals_to_db_spl(s_pa);

            if s_spl >= self.config.blast_detection_threshold_db_spl {
                if !self.is_in_blast {
                    self.is_in_blast = true;
                    self.blast_peak_sample = abs_s;
                    self.blast_sample_count = 1;
                } else {
                    if abs_s > self.blast_peak_sample {
                        self.blast_peak_sample = abs_s;
                    }
                    self.blast_sample_count += 1;
                }
            } else if self.is_in_blast {
                // Blast wave has returned below threshold: close event
                let a_duration_ms = (self.blast_sample_count as f32 / self.config.sample_rate) * 1000.0;
                let peak_pa = self.sample_to_pascals(self.blast_peak_sample);
                let peak_psi = self.pascals_to_psi(peak_pa);
                let peak_spl = self.pascals_to_db_spl(peak_pa);

                // Calculate MIL-STD-1474E exposure dose for this single impulse:
                // Attenuated level reaching soldier's eardrum:
                let effective_spl = (peak_spl - self.config.earcup_attenuation_db).max(85.0);
                // Normalized dose: 140 dB effective with 1.0 ms duration corresponds to ~0.5% daily dose
                let single_dose_pct = 0.5 * 10.0f32.powf((effective_spl - 140.0) / 10.0) * (a_duration_ms / 1.0).max(0.1);

                let event = BlastEvent {
                    frame_index: self.frame_counter,
                    peak_spl_db: peak_spl,
                    peak_overpressure_pa: peak_pa,
                    peak_overpressure_psi: peak_psi,
                    a_duration_ms,
                    dose_pct: single_dose_pct,
                };

                // Store in history
                self.blast_history[self.history_write_idx] = event;
                self.history_write_idx = (self.history_write_idx + 1) % BLAST_HISTORY_CAPACITY;

                // Update cumulative stats
                self.telemetry.daily_impulse_count += 1;
                self.telemetry.cumulative_dose_pct += single_dose_pct;
                self.telemetry.last_blast_event = event;

                self.is_in_blast = false;
                self.blast_peak_sample = 0.0;
                self.blast_sample_count = 0;
            }
        }

        // Current instantaneous peak
        let frame_pa = self.sample_to_pascals(frame_peak_sample);
        let frame_psi = self.pascals_to_psi(frame_pa);
        let frame_spl = self.pascals_to_db_spl(frame_pa);

        self.telemetry.peak_spl_db = frame_spl;
        self.telemetry.peak_overpressure_pa = frame_pa;
        self.telemetry.peak_overpressure_psi = frame_psi;

        // Evaluate hazard status
        self.telemetry.hazard_status = if self.telemetry.cumulative_dose_pct >= self.config.daily_dose_limit
            || frame_spl >= 175.0
        {
            BlastHazardStatus::Hazardous
        } else if self.telemetry.cumulative_dose_pct >= self.config.daily_dose_limit * 0.5 {
            BlastHazardStatus::Caution
        } else {
            BlastHazardStatus::Nominal
        };
    }

    /// Access historical blast events ring buffer.
    pub fn recent_blasts(&self) -> &[BlastEvent; BLAST_HISTORY_CAPACITY] {
        &self.blast_history
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sound_pressure_and_psi_conversions() {
        let meter = BlastImpulseMeter::new(BlastMeterConfig::default());

        // 140 dB SPL should equal ~200 Pa
        let pa_140 = 200.0;
        let spl_calc = meter.pascals_to_db_spl(pa_140);
        assert!((spl_calc - 140.0).abs() < 0.1);

        // 1 PSI = ~6895 Pa
        let psi_calc = meter.pascals_to_psi(PASCALS_PER_PSI);
        assert!((psi_calc - 1.0).abs() < 1e-4);

        // 170 dB SPL should equal ~6325 Pa and ~0.917 PSI
        let pa_170 = P_REF_PASCALS * 10.0f32.powf(170.0 / 20.0);
        assert!((pa_170 - 6324.5).abs() < 2.0);
        let psi_170 = meter.pascals_to_psi(pa_170);
        assert!((psi_170 - 0.917).abs() < 0.01);
    }

    #[test]
    fn test_blast_impulse_detection_and_dose_accumulation() {
        let config = BlastMeterConfig::default();
        let mut meter = BlastImpulseMeter::new(config);

        // Feed quiet samples (no blast)
        let quiet = [0.01f32; 256];
        meter.process_frame(&quiet);
        assert_eq!(meter.telemetry.daily_impulse_count, 0);
        assert_eq!(meter.telemetry.hazard_status, BlastHazardStatus::Nominal);

        // Feed an intense blast impulse: 5.0 amplitude peak (> 150 dB SPL)
        let mut blast = [0.01f32; 256];
        for i in 30..50 {
            blast[i] = 4.0; // Overpressure blast shock
        }

        meter.process_frame(&blast);
        // Follow with quiet frame to close the blast pulse
        meter.process_frame(&quiet);

        assert_eq!(meter.telemetry.daily_impulse_count, 1);
        assert!(meter.telemetry.cumulative_dose_pct > 0.0);
        assert!(meter.telemetry.last_blast_event.peak_overpressure_pa > 500.0);
    }

    #[test]
    fn test_hazardous_condition_trigger() {
        let config = BlastMeterConfig {
            daily_dose_limit: 0.20,
            earcup_attenuation_db: 15.0,
            ..Default::default()
        };
        let mut meter = BlastImpulseMeter::new(config);

        // Accumulate multiple heavy blast events
        for _ in 0..15 {
            let mut blast = [0.01f32; 128];
            for i in 10..30 {
                blast[i] = 12.0;
            }
            meter.process_frame(&blast);
            let quiet = [0.01f32; 128];
            meter.process_frame(&quiet);
        }

        assert!(meter.telemetry.cumulative_dose_pct > 0.20);
        assert_eq!(meter.telemetry.hazard_status, BlastHazardStatus::Hazardous);
    }
}
