//! Acoustic Vocal Fatigue & Soldier Cognitive Stress Index Profiler.
//!
//! On the modern battlefield, soldiers undergo severe cognitive workload, acute fear,
//! adrenaline rushes, and extreme physical exhaustion. These psychological and physiological
//! states manifest immediately in vocal acoustic biomarkers:
//! 1. Vocal Jitter (Cycle-to-cycle fundamental period perturbation):
//!    Nominal calm speech: Jitter < 1.0%. Under acute stress / laryngeal tremor: Jitter > 1.5% - 4.0%.
//! 2. Vocal Shimmer (Cycle-to-cycle peak amplitude perturbation):
//!    Nominal calm speech: Shimmer < 3.8%. Under acute vocal strain: Shimmer > 5.0% - 14.0%.
//! 3. Fundamental Frequency Elevation (Delta F0) and Pitch Instability.
//! 4. Speaking Rate / Syllabic Cadence Modulation (pressured speech under threat).
//!
//! The Tactical Stress Profiler computes a composite Tactical Cognitive Stress Index
//! (0.0% to 100.0%) and Vocal Fatigue Index in real-time, providing mission commanders
//! with an objective biomarker of soldier operational readiness and psychological strain.
//!
//! Zero heap allocations in the real-time processing loop.

/// Configuration for the Tactical Stress Profiler.
#[derive(Debug, Clone)]
pub struct StressProfilerConfig {
    pub sample_rate: f32,
    pub baseline_f0_hz: f32,
    pub min_speech_energy: f32,
    pub history_len: usize,
}

impl Default for StressProfilerConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000.0,
            baseline_f0_hz: 130.0,
            min_speech_energy: 1e-4,
            history_len: 32,
        }
    }
}

/// Real-time Acoustic Stress Biomarkers and Cognitive State Telemetry.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct StressTelemetry {
    /// Composite Tactical Cognitive Stress Index (0.0% = calm/steady, 100.0% = acute panic/strain).
    pub stress_index_pct: f32,
    /// Vocal Jitter percentage (cycle-to-cycle pitch period variation).
    pub jitter_pct: f32,
    /// Vocal Shimmer percentage (cycle-to-cycle speech amplitude variation).
    pub shimmer_pct: f32,
    /// Fundamental frequency elevation above nominal baseline (in Hz).
    pub pitch_elevation_hz: f32,
    /// Estimated speaking cadence / syllabic rate (syllables per second).
    pub speaking_rate_sps: f32,
    /// Cumulative vocal fatigue level (0.0% to 100.0%).
    pub vocal_fatigue_pct: f32,
    /// Whether the speaker is currently exhibiting acute tactical stress (> 65.0%).
    pub is_acute_stress: bool,
}

impl Default for StressTelemetry {
    fn default() -> Self {
        Self {
            stress_index_pct: 0.0,
            jitter_pct: 0.5,
            shimmer_pct: 2.0,
            pitch_elevation_hz: 0.0,
            speaking_rate_sps: 3.5,
            vocal_fatigue_pct: 0.0,
            is_acute_stress: false,
        }
    }
}

const MAX_PERIODS: usize = 32;

/// Acoustic Vocal Fatigue & Soldier Cognitive Stress Index Profiler.
pub struct StressProfiler {
    config: StressProfilerConfig,
    period_history: [f32; MAX_PERIODS],
    amp_history: [f32; MAX_PERIODS],
    history_count: usize,
    history_idx: usize,
    smoothed_jitter: f32,
    smoothed_shimmer: f32,
    smoothed_stress: f32,
    smoothed_speaking_rate: f32,
    cumulative_fatigue: f32,
    last_energy: f32,
    syllable_burst_counter: u32,
    frame_counter: u32,
}

impl StressProfiler {
    /// Creates a new StressProfiler with pre-allocated circular ring buffers.
    pub fn new(config: StressProfilerConfig) -> Self {
        Self {
            config,
            period_history: [0.0; MAX_PERIODS],
            amp_history: [0.0; MAX_PERIODS],
            history_count: 0,
            history_idx: 0,
            smoothed_jitter: 0.5,
            smoothed_shimmer: 2.0,
            smoothed_stress: 0.0,
            smoothed_speaking_rate: 3.5,
            cumulative_fatigue: 0.0,
            last_energy: 0.0,
            syllable_burst_counter: 0,
            frame_counter: 0,
        }
    }

    /// Resets all internal biomarker histories.
    pub fn reset(&mut self) {
        self.period_history = [0.0; MAX_PERIODS];
        self.amp_history = [0.0; MAX_PERIODS];
        self.history_count = 0;
        self.history_idx = 0;
        self.smoothed_jitter = 0.5;
        self.smoothed_shimmer = 2.0;
        self.smoothed_stress = 0.0;
        self.smoothed_speaking_rate = 3.5;
        self.cumulative_fatigue = 0.0;
        self.last_energy = 0.0;
        self.syllable_burst_counter = 0;
        self.frame_counter = 0;
    }

    /// Sets the soldier's nominal rest-state baseline pitch (in Hz).
    pub fn set_baseline_f0(&mut self, baseline_hz: f32) {
        self.config.baseline_f0_hz = baseline_hz.clamp(70.0, 350.0);
    }

    /// Processes an audio frame and updates real-time stress biomarkers.
    ///
    /// - `samples`: Time-domain enhanced speech samples for the current frame.
    /// - `f0_opt`: Optional fundamental frequency in Hz (from pitch tracker).
    ///
    /// Zero heap allocations in the audio loop.
    pub fn process_frame(&mut self, samples: &[f32], f0_opt: Option<f32>) -> StressTelemetry {
        if samples.is_empty() {
            return StressTelemetry::default();
        }

        self.frame_counter = self.frame_counter.wrapping_add(1);

        // 1. Frame Energy & Peak Amplitude
        let mut sum_sq = 0.0f32;
        let mut peak_amp = 0.0f32;
        for &s in samples {
            let abs_s = s.abs();
            if abs_s > peak_amp {
                peak_amp = abs_s;
            }
            sum_sq += s * s;
        }
        let frame_energy = sum_sq / samples.len() as f32;
        let is_voiced = frame_energy > self.config.min_speech_energy && peak_amp > 0.02;

        // 2. Syllable Rate Detection via Energy Envelope Attack Detection
        if frame_energy > 2.0 * self.last_energy.max(1e-5) && frame_energy > 1e-3 {
            self.syllable_burst_counter = self.syllable_burst_counter.saturating_add(1);
        }
        self.last_energy = 0.8 * self.last_energy + 0.2 * frame_energy;

        // Estimate speaking rate once every ~1 second (approx 62 frames at 16 ms hop)
        if self.frame_counter.is_multiple_of(62) {
            let inst_rate = (self.syllable_burst_counter as f32).clamp(1.0, 10.0);
            self.smoothed_speaking_rate = 0.8 * self.smoothed_speaking_rate + 0.2 * inst_rate;
            self.syllable_burst_counter = 0;
        }

        // 3. Cycle-to-Cycle Perturbation (Jitter & Shimmer)
        let delta_f0 = if let Some(f0) = f0_opt {
            if is_voiced && f0 > 70.0 && f0 < 450.0 {
                let period_s = 1.0 / f0;

                // Push to circular history
                self.period_history[self.history_idx] = period_s;
                self.amp_history[self.history_idx] = peak_amp;
                self.history_idx = (self.history_idx + 1) % MAX_PERIODS;
                if self.history_count < MAX_PERIODS {
                    self.history_count += 1;
                }

                (f0 - self.config.baseline_f0_hz).max(0.0)
            } else {
                0.0
            }
        } else {
            0.0
        };

        if self.history_count >= 8 && is_voiced {
            let n = self.history_count;
            let mut sum_diff_period = 0.0f32;
            let mut sum_period = 0.0f32;
            let mut sum_diff_amp = 0.0f32;
            let mut sum_amp = 0.0f32;

            for i in 0..(n - 1) {
                let p1 = self.period_history[i];
                let p2 = self.period_history[i + 1];
                sum_diff_period += (p1 - p2).abs();
                sum_period += p1;

                let a1 = self.amp_history[i];
                let a2 = self.amp_history[i + 1];
                sum_diff_amp += (a1 - a2).abs();
                sum_amp += a1;
            }
            sum_period += self.period_history[n - 1];
            sum_amp += self.amp_history[n - 1];

            let mean_p = sum_period / n as f32;
            let mean_a = sum_amp / n as f32;

            if mean_p > 1e-5 {
                let inst_jitter = ((sum_diff_period / (n - 1) as f32) / mean_p) * 100.0;
                self.smoothed_jitter = 0.90 * self.smoothed_jitter + 0.10 * inst_jitter.clamp(0.1, 10.0);
            }

            if mean_a > 1e-4 {
                let inst_shimmer = ((sum_diff_amp / (n - 1) as f32) / mean_a) * 100.0;
                self.smoothed_shimmer = 0.90 * self.smoothed_shimmer + 0.10 * inst_shimmer.clamp(0.2, 25.0);
            }
        }

        // 4. Multi-Biomarker Tactical Stress Index Calculation (0.0% to 100.0%)
        // Jitter score: calm < 1.0%, severe stress > 3.0%
        let s_jit = ((self.smoothed_jitter - 0.8) / 2.2).clamp(0.0, 1.0) * 100.0;
        // Shimmer score: calm < 3.5%, severe stress > 10.0%
        let s_shim = ((self.smoothed_shimmer - 3.2) / 7.0).clamp(0.0, 1.0) * 100.0;
        // Pitch elevation score: Delta F0 0 to 50 Hz
        let s_f0 = (delta_f0 / 50.0).clamp(0.0, 1.0) * 100.0;
        // Speaking rate score: nominal 3.5 sps, pressured > 6.5 sps
        let s_rate = ((self.smoothed_speaking_rate - 3.5) / 3.5).clamp(0.0, 1.0) * 100.0;

        let inst_stress = 0.30 * s_jit + 0.30 * s_shim + 0.25 * s_f0 + 0.15 * s_rate;
        let smooth_coeff = if is_voiced { 0.15 } else { 0.02 };
        self.smoothed_stress = (1.0 - smooth_coeff) * self.smoothed_stress + smooth_coeff * inst_stress;
        let final_stress = self.smoothed_stress.clamp(0.0, 100.0);

        // 5. Cumulative Vocal Fatigue Tracking
        if is_voiced {
            // Sustained stress and shouting slowly increases vocal fatigue
            let strain_rate = if final_stress > 50.0 { 0.005 } else { 0.001 };
            self.cumulative_fatigue = (self.cumulative_fatigue + strain_rate).clamp(0.0, 100.0);
        } else {
            // Silence slowly recovers vocal fatigue
            self.cumulative_fatigue = (self.cumulative_fatigue - 0.002).max(0.0);
        }

        StressTelemetry {
            stress_index_pct: final_stress,
            jitter_pct: self.smoothed_jitter,
            shimmer_pct: self.smoothed_shimmer,
            pitch_elevation_hz: delta_f0,
            speaking_rate_sps: self.smoothed_speaking_rate,
            vocal_fatigue_pct: self.cumulative_fatigue,
            is_acute_stress: final_stress >= 65.0,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_stress_profiler_silence_initial_state() {
        let mut profiler = StressProfiler::new(StressProfilerConfig::default());
        let samples = vec![0.0f32; 256];
        let telem = profiler.process_frame(&samples, None);

        assert_eq!(telem.stress_index_pct, 0.0);
        assert!(!telem.is_acute_stress);
    }

    #[test]
    fn test_stress_profiler_detects_high_jitter_and_pitch_elevation() {
        let mut profiler = StressProfiler::new(StressProfilerConfig::default());

        // Simulate acute combat stress:
        // Elevated F0 (185 Hz vs baseline 130 Hz)
        // High cycle-to-cycle perturbation (simulating vocal tremor and laryngeal tension)
        for i in 0..60 {
            let f0_jittered = 185.0 + if i % 2 == 0 { 15.0 } else { -15.0 };
            let mut samples = vec![0.0f32; 256];
            let amp_jittered = 0.50 + if i % 2 == 0 { 0.20 } else { -0.20 };
            for (n, s) in samples.iter_mut().enumerate() {
                *s = amp_jittered * (2.0 * std::f32::consts::PI * f0_jittered * (n as f32) / 16000.0).sin();
            }
            profiler.process_frame(&samples, Some(f0_jittered));
        }

        let mut samples = vec![0.5f32; 256];
        for (n, s) in samples.iter_mut().enumerate() {
            *s = 0.5 * (2.0 * std::f32::consts::PI * 185.0 * (n as f32) / 16000.0).sin();
        }
        let telem = profiler.process_frame(&samples, Some(185.0));

        assert!(
            telem.stress_index_pct > 35.0,
            "Expected stress index > 35% under acute tremor/elevation, got {:.1}%",
            telem.stress_index_pct
        );
        assert!(telem.pitch_elevation_hz > 40.0);
    }

    #[test]
    fn test_stress_profiler_reset() {
        let mut profiler = StressProfiler::new(StressProfilerConfig::default());
        profiler.smoothed_stress = 85.0;
        profiler.reset();
        assert_eq!(profiler.smoothed_stress, 0.0);
    }
}
