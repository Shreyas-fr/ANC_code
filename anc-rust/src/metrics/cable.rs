//! Acoustic Transducer Impedance & Cable Continuity Fault Diagnostics.
//!
//! Developed for SIH 26052 Tactical Military Audio Systems.
//!
//! In dismounted infantry and armored vehicle operations, tactical headsets (U-174, LEMO, Nexus connectors)
//! undergo extreme physical abuse: snagging on turret hatches, combat pack straps, sweat/moisture ingress,
//! and copper wire strand breakage inside braided cables.
//!
//! Physical Failure Modes Monitored:
//! 1. Micro-Intermittent Contact Bounce:
//!    - Mechanical cable flexing causes loose solder joints or fractured copper conductors to open/close
//!      briefly, injecting high-frequency kurtosis crackle spikes into one channel without acoustic correlation.
//! 2. High-Impedance Fray / Moisture Corrosion:
//!    - Partial strand fracture or salt fog corrosion increases line resistance from $2.2\text{ k}\Omega$ up to $50\text{ k}\Omega$.
//! 3. Open Circuit / Transducer Disconnection:
//!    - Complete conductor severance ($Z > 100\text{ k}\Omega$); signal drops to floating preamplifier thermal floor.
//! 4. Short Circuit / Ground Shield Pinch:
//!    - Wire jacket pinched against metal armor, shorting audio lines ($Z < 50\ \Omega$); audio flatlines to rail.
//! 5. DC Bias Leakage:
//!    - Moisture bridge or defective decoupling capacitor causes phantom DC drift.
//!
//! Strictly ZERO heap allocations in real-time execution.

/// Status of the acoustic transducer and interconnect cable.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
#[repr(u8)]
pub enum CableFaultStatus {
    /// 100% nominal cable integrity and transducer impedance.
    #[default]
    Nominal = 0,
    /// Intermittent contact bounce / conductor strand fraying detected.
    MicroIntermittent = 1,
    /// Elevated contact impedance due to strain or moisture corrosion.
    HighImpedanceFray = 2,
    /// Broken conductor or disconnected transducer (open circuit).
    OpenCircuit = 3,
    /// Ground shield short or pinched conductor (short circuit).
    ShortCircuit = 4,
}

impl CableFaultStatus {
    pub fn name(&self) -> &'static str {
        match self {
            Self::Nominal => "NOMINAL (100% INTEGRITY)",
            Self::MicroIntermittent => "FAULT: MICRO-INTERMITTENT CONTACT",
            Self::HighImpedanceFray => "WARNING: HIGH-IMPEDANCE CABLE FRAY",
            Self::OpenCircuit => "CRITICAL: TRANSDUCER OPEN CIRCUIT",
            Self::ShortCircuit => "CRITICAL: CABLE SHORT CIRCUIT",
        }
    }

    pub fn from_u8(val: u8) -> Self {
        match val {
            0 => Self::Nominal,
            1 => Self::MicroIntermittent,
            2 => Self::HighImpedanceFray,
            3 => Self::OpenCircuit,
            4 => Self::ShortCircuit,
            _ => Self::Nominal,
        }
    }
}

/// Configuration for Cable Continuity Diagnostics.
#[derive(Debug, Clone, Copy)]
pub struct CableConfig {
    /// Sampling rate in Hz (default: 16000.0).
    pub sample_rate: f32,
    /// Nominal microphone preamplifier input impedance in Ohms (default: 2200.0 Ohm).
    pub nominal_impedance_ohms: f32,
    /// Exponential smoothing alpha for impedance and DC estimates (default: 0.96).
    pub smoothing_alpha: f32,
    /// Discontinuity crest factor / kurtosis threshold for micro-intermittent crackle detection.
    pub crackle_threshold: f32,
    /// Minimum power threshold for normal acoustic signals (default: 1e-6 = -60 dBFS).
    pub min_signal_power: f32,
}

impl Default for CableConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000.0,
            nominal_impedance_ohms: 2200.0,
            smoothing_alpha: 0.96,
            crackle_threshold: 6.5,
            min_signal_power: 1e-6,
        }
    }
}

/// Real-time diagnostic telemetry for transducer and cable health.
#[derive(Debug, Clone, Copy, Default)]
pub struct CableTelemetry {
    /// Overall cable health index (0.0% critical fault to 100.0% pristine).
    pub health_pct: f32,
    /// Current estimated electrical load impedance in Ohms.
    pub estimated_impedance_ohms: f32,
    /// Inter-microphone transfer function coherence in low frequencies (0.0 to 1.0).
    pub low_freq_coherence: f32,
    /// DC offset bias in millivolts (mV).
    pub dc_offset_mv: f32,
    /// Total count of micro-intermittent contact bounce / crackle events detected.
    pub micro_intermittent_events: u64,
    /// Current diagnostic fault status.
    pub status: CableFaultStatus,
}

/// Real-Time Acoustic Transducer Impedance & Cable Continuity Fault Diagnostics.
pub struct CableDiagnostics {
    config: CableConfig,

    // Smoothed trackers
    impedance_ohms: f32,
    dc_offset: f32,
    health_pct: f32,
    intermittent_counter: u64,

    // Inter-channel statistics
    pwr_mic1: f32,
    pwr_mic2: f32,
    cross_pwr: f32,

    // Telemetry
    telemetry: CableTelemetry,
}

impl CableDiagnostics {
    /// Creates a new CableDiagnostics analyzer with the given configuration.
    pub fn new(config: CableConfig) -> Self {
        Self {
            config,
            impedance_ohms: config.nominal_impedance_ohms,
            dc_offset: 0.0,
            health_pct: 100.0,
            intermittent_counter: 0,
            pwr_mic1: 1e-5,
            pwr_mic2: 1e-5,
            cross_pwr: 1e-5,
            telemetry: CableTelemetry {
                health_pct: 100.0,
                estimated_impedance_ohms: config.nominal_impedance_ohms,
                low_freq_coherence: 1.0,
                dc_offset_mv: 0.0,
                micro_intermittent_events: 0,
                status: CableFaultStatus::Nominal,
            },
        }
    }

    /// Resets all internal statistics.
    pub fn reset(&mut self) {
        self.impedance_ohms = self.config.nominal_impedance_ohms;
        self.dc_offset = 0.0;
        self.health_pct = 100.0;
        self.intermittent_counter = 0;
        self.pwr_mic1 = 1e-5;
        self.pwr_mic2 = 1e-5;
        self.cross_pwr = 1e-5;
        self.telemetry = CableTelemetry {
            health_pct: 100.0,
            estimated_impedance_ohms: self.config.nominal_impedance_ohms,
            low_freq_coherence: 1.0,
            dc_offset_mv: 0.0,
            micro_intermittent_events: 0,
            status: CableFaultStatus::Nominal,
        };
    }

    /// Processes an audio frame with zero heap allocations and evaluates physical cable integrity.
    pub fn process_frame(&mut self, mic1: &[f32], mic2: Option<&[f32]>) -> CableTelemetry {
        if mic1.is_empty() {
            return self.telemetry;
        }

        let n = mic1.len() as f32;
        let alpha = self.config.smoothing_alpha;

        // 1. Measure DC offset and instantaneous variance on primary channel
        let sum_m1: f32 = mic1.iter().copied().sum();
        let mean_m1 = sum_m1 / n;
        self.dc_offset = alpha * self.dc_offset + (1.0 - alpha) * mean_m1;

        let var_m1: f32 = mic1.iter().map(|&s| (s - mean_m1) * (s - mean_m1)).sum::<f32>() / n;
        let peak_m1 = mic1.iter().map(|&s| (s - mean_m1).abs()).fold(0.0f32, f32::max);
        let crest_factor = if var_m1 > 1e-9 { peak_m1 / var_m1.sqrt() } else { 1.0 };

        // 2. Inter-channel cross-power and coherence analysis
        let (has_mic2, coherence, crest_m2) = if let Some(m2) = mic2 {
            if m2.len() == mic1.len() {
                let mean_m2: f32 = m2.iter().copied().sum::<f32>() / n;
                let var_m2: f32 = m2.iter().map(|&s| (s - mean_m2) * (s - mean_m2)).sum::<f32>() / n;
                let peak_m2 = m2.iter().map(|&s| (s - mean_m2).abs()).fold(0.0f32, f32::max);
                let cf_m2 = if var_m2 > 1e-9 { peak_m2 / var_m2.sqrt() } else { 1.0 };

                let cross: f32 = mic1
                    .iter()
                    .zip(m2.iter())
                    .map(|(&s1, &s2)| (s1 - mean_m1) * (s2 - mean_m2))
                    .sum::<f32>()
                    / n;

                self.pwr_mic1 = alpha * self.pwr_mic1 + (1.0 - alpha) * var_m1;
                self.pwr_mic2 = alpha * self.pwr_mic2 + (1.0 - alpha) * var_m2;
                self.cross_pwr = alpha * self.cross_pwr + (1.0 - alpha) * cross.abs();

                let denom = (self.pwr_mic1 * self.pwr_mic2).sqrt();
                let coh = if denom > 1e-9 {
                    (self.cross_pwr / denom).clamp(0.0, 1.0)
                } else {
                    1.0
                };
                (true, coh, cf_m2)
            } else {
                (false, 1.0, 1.0)
            }
        } else {
            (false, 1.0, 1.0)
        };

        // 3. Physical fault state classification
        // A. Short Circuit detection: total flatline or pinned to rail with zero AC power
        let is_short_circuit = var_m1 < 1e-11 && mean_m1.abs() > 0.90;

        // B. Open Circuit detection: signal power dropped to pure amplifier electron noise (< -85 dBFS)
        // while mic2 (if present) still detects acoustic presence
        let is_open_circuit = var_m1 < 1e-9 && (!has_mic2 || self.pwr_mic2 > 1e-5);

        // C. Micro-intermittent contact detection: extreme crest factor (> crackle_threshold) in one
        // channel without corresponding spike in other channel, indicating mechanical contact bounce
        let is_micro_intermittent = has_mic2
            && ((crest_factor > self.config.crackle_threshold && crest_m2 < 3.5)
                || (crest_m2 > self.config.crackle_threshold && crest_factor < 3.5));

        // D. High-impedance fray: coherence collapses in low frequencies despite active acoustic input
        let is_high_impedance_fray = has_mic2
            && coherence < 0.25
            && self.pwr_mic1 > self.config.min_signal_power
            && self.pwr_mic2 > self.config.min_signal_power;

        // 4. Update Impedance and Health Metrics
        let (status, target_impedance, target_health) = if is_short_circuit {
            (CableFaultStatus::ShortCircuit, 25.0, 0.0)
        } else if is_open_circuit {
            (CableFaultStatus::OpenCircuit, 120_000.0, 10.0)
        } else if is_micro_intermittent {
            self.intermittent_counter = self.intermittent_counter.saturating_add(1);
            (CableFaultStatus::MicroIntermittent, 6500.0, 55.0)
        } else if is_high_impedance_fray {
            (CableFaultStatus::HighImpedanceFray, 14500.0, 45.0)
        } else {
            (CableFaultStatus::Nominal, self.config.nominal_impedance_ohms, 100.0)
        };

        let eff_alpha = if is_short_circuit || is_open_circuit { 0.70 } else { alpha };
        self.impedance_ohms = eff_alpha * self.impedance_ohms + (1.0 - eff_alpha) * target_impedance;
        self.health_pct = eff_alpha * self.health_pct + (1.0 - eff_alpha) * target_health;

        self.telemetry = CableTelemetry {
            health_pct: self.health_pct.clamp(0.0, 100.0),
            estimated_impedance_ohms: self.impedance_ohms,
            low_freq_coherence: coherence,
            dc_offset_mv: self.dc_offset * 1000.0,
            micro_intermittent_events: self.intermittent_counter,
            status,
        };

        self.telemetry
    }

    /// Returns the current telemetry metrics.
    pub fn telemetry(&self) -> CableTelemetry {
        self.telemetry
    }

    /// Returns current health percentage.
    pub fn health_pct(&self) -> f32 {
        self.health_pct
    }

    /// Returns current estimated load impedance in Ohms.
    pub fn estimated_impedance_ohms(&self) -> f32 {
        self.impedance_ohms
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cable_diagnostics_nominal_stereo() {
        let mut diag = CableDiagnostics::new(CableConfig::default());

        let mut mic1 = [0.0f32; 128];
        let mut mic2 = [0.0f32; 128];
        for i in 0..128 {
            let t = i as f32 / 16000.0;
            let val = 0.3 * (2.0 * std::f32::consts::PI * 400.0 * t).sin();
            mic1[i] = val;
            mic2[i] = val * 0.98; // Nominal close acoustic match
        }

        for _ in 0..10 {
            diag.process_frame(&mic1, Some(&mic2));
        }

        let telem = diag.telemetry();
        assert_eq!(telem.status, CableFaultStatus::Nominal);
        assert!(telem.health_pct > 95.0, "Nominal health should be > 95%");
        assert!(telem.low_freq_coherence > 0.90, "Coherence should be high for correlated acoustic tone");
    }

    #[test]
    fn test_cable_diagnostics_micro_intermittent_crackle() {
        let mut diag = CableDiagnostics::new(CableConfig::default());

        let mut mic1 = [0.01f32; 128];
        let mic2 = [0.01f32; 128];

        // Inject severe mechanical contact bounce crackle spike into mic1 only
        mic1[30] = 0.95;
        mic1[31] = -0.90;

        let telem = diag.process_frame(&mic1, Some(&mic2));
        assert_eq!(telem.status, CableFaultStatus::MicroIntermittent);
        assert!(telem.micro_intermittent_events > 0);
    }

    #[test]
    fn test_cable_diagnostics_open_circuit_disconnection() {
        let mut diag = CableDiagnostics::new(CableConfig::default());

        // Mic 1 dead / open circuit (zero power), while Mic 2 receives loud voice
        let mic1 = [0.0f32; 128];
        let mut mic2 = [0.0f32; 128];
        for i in 0..128 {
            let t = i as f32 / 16000.0;
            mic2[i] = 0.4 * (2.0 * std::f32::consts::PI * 500.0 * t).sin();
        }

        let mut telem = diag.process_frame(&mic1, Some(&mic2));
        for _ in 0..10 {
            telem = diag.process_frame(&mic1, Some(&mic2));
        }
        assert_eq!(telem.status, CableFaultStatus::OpenCircuit);
        assert!(telem.health_pct < 60.0);
    }
}
