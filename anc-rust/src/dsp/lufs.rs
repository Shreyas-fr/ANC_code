//! ITU-R BS.1770-4 & EBU R128 True LUFS Loudness Governor & Dynamic Range Compressor.
//!
//! In tactical combat intercom networks, voice loudness varies drastically between
//! quiet reconnaissance whispers (-35 to -45 LUFS) and shouting pilots (-10 to -5 LUFS).
//! This module implements:
//! 1. ITU-R BS.1770-4 compliant K-weighting pre-filter (high-shelf + high-pass biquads).
//! 2. Mean-square dual-gating (absolute threshold -70 LKFS, relative threshold -10 LU).
//! 3. Real-time Momentary (400 ms), Short-Term (3.0 s), and Integrated Loudness (LUFS).
//! 4. EBU Tech 3342 Loudness Range (LRA) and True-Peak estimation (dBFS).
//! 5. Smooth lookahead Dynamic Range Compression (DRC) regulating speech to a tactical
//!    target (default: -23.0 LUFS) without pumping artifacts or speech onset clipping.
//!
//! Zero heap allocations in the real-time processing loop.

use std::f32::consts::PI;

/// ITU-R BS.1770-4 K-weighting biquad filter stage.
#[derive(Debug, Clone, Copy)]
pub struct BiquadFilter {
    b0: f32,
    b1: f32,
    b2: f32,
    a1: f32,
    a2: f32,
    s1: f32,
    s2: f32,
}

impl BiquadFilter {
    /// Creates a direct form II transposed biquad filter.
    pub const fn new(b0: f32, b1: f32, b2: f32, a1: f32, a2: f32) -> Self {
        Self {
            b0,
            b1,
            b2,
            a1,
            a2,
            s1: 0.0,
            s2: 0.0,
        }
    }

    /// Resets internal state.
    pub fn reset(&mut self) {
        self.s1 = 0.0;
        self.s2 = 0.0;
    }

    /// Processes a single audio sample (Direct Form II Transposed).
    #[inline]
    pub fn process_sample(&mut self, x: f32) -> f32 {
        let y = self.b0 * x + self.s1;
        self.s1 = self.b1 * x - self.a1 * y + self.s2;
        self.s2 = self.b2 * x - self.a2 * y;
        y
    }
}

/// Full ITU-R BS.1770-4 K-weighting pre-filter consisting of:
/// Stage 1: High-shelf filter (models head acoustic acoustics)
/// Stage 2: High-pass RLB filter (models ear bass roll-off)
#[derive(Debug, Clone)]
pub struct KWeightingFilter {
    shelf: BiquadFilter,
    highpass: BiquadFilter,
}

impl KWeightingFilter {
    /// Designs K-weighting filter for arbitrary sample rate (e.g. 16000 Hz or 48000 Hz).
    pub fn new(sample_rate: f32) -> Self {
        let fs = sample_rate.max(8000.0);

        // Stage 1: High Shelf Filter (f0 = 1681.97 Hz, Q = 0.707175, Gain = +3.9998 dB)
        let db = 3.999_843_8_f32;
        let f0_shelf = 1_681.974_5_f32;
        let q_shelf = 0.707_175_25_f32;
        let k_shelf = (PI * f0_shelf / fs).tan();
        let vh = 10.0f32.powf(db / 20.0);
        let vb = vh.powf(0.499_666_78); // approximately sqrt(vh)
        let a0_shelf = 1.0 + k_shelf / q_shelf + k_shelf * k_shelf;

        let b0_s = (vh + vb * k_shelf / q_shelf + k_shelf * k_shelf) / a0_shelf;
        let b1_s = 2.0 * (k_shelf * k_shelf - vh) / a0_shelf;
        let b2_s = (vh - vb * k_shelf / q_shelf + k_shelf * k_shelf) / a0_shelf;
        let a1_s = 2.0 * (k_shelf * k_shelf - 1.0) / a0_shelf;
        let a2_s = (1.0 - k_shelf / q_shelf + k_shelf * k_shelf) / a0_shelf;

        // Stage 2: RLB High-pass Filter (f0 = 38.135 Hz, Q = 0.500327)
        let f0_hp = 38.135_47_f32;
        let q_hp = 0.500_327_05_f32;
        let k_hp = (PI * f0_hp / fs).tan();
        let a0_hp = 1.0 + k_hp / q_hp + k_hp * k_hp;

        let b0_hp = 1.0 / a0_hp;
        let b1_hp = -2.0 / a0_hp;
        let b2_hp = 1.0 / a0_hp;
        let a1_hp = 2.0 * (k_hp * k_hp - 1.0) / a0_hp;
        let a2_hp = (1.0 - k_hp / q_hp + k_hp * k_hp) / a0_hp;

        Self {
            shelf: BiquadFilter::new(b0_s, b1_s, b2_s, a1_s, a2_s),
            highpass: BiquadFilter::new(b0_hp, b1_hp, b2_hp, a1_hp, a2_hp),
        }
    }

    /// Resets internal filter states.
    pub fn reset(&mut self) {
        self.shelf.reset();
        self.highpass.reset();
    }

    /// Filters a single audio sample through the K-weighting cascade.
    #[inline]
    pub fn process_sample(&mut self, x: f32) -> f32 {
        let s = self.shelf.process_sample(x);
        self.highpass.process_sample(s)
    }

    /// Filters a block of samples in-place.
    pub fn process_block(&mut self, block: &mut [f32]) {
        for s in block.iter_mut() {
            *s = self.process_sample(*s);
        }
    }
}

/// Configuration for the ITU-R BS.1770-4 & EBU R128 Loudness Governor.
#[derive(Debug, Clone)]
pub struct LufsConfig {
    /// Audio sampling rate in Hz (default: 16000.0)
    pub sample_rate: f32,
    /// Hop size in samples (default: 256)
    pub hop_size: usize,
    /// Target tactical loudness in LUFS (default: -23.0 LUFS)
    pub target_lufs: f32,
    /// Maximum gain boost in dB (default: +12.0 dB)
    pub max_boost_db: f32,
    /// Maximum gain reduction in dB (default: -18.0 dB)
    pub max_cut_db: f32,
    /// Lookahead buffer length in milliseconds (default: 5.0 ms = 80 samples @ 16 kHz)
    pub lookahead_ms: f32,
    /// DRC attack time in milliseconds (default: 15.0 ms)
    pub attack_ms: f32,
    /// DRC release time in milliseconds (default: 300.0 ms)
    pub release_ms: f32,
    /// Absolute gating threshold in LKFS (default: -70.0 LKFS)
    pub absolute_threshold_lkfs: f32,
    /// Relative gating threshold below ungated mean in LU (default: -10.0 LU)
    pub relative_threshold_lu: f32,
    /// Speech pause gating threshold below which DRC gain freezes or returns to unity (default: -55.0 LUFS)
    pub pause_threshold_lufs: f32,
}

impl Default for LufsConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000.0,
            hop_size: 256,
            target_lufs: -23.0,
            max_boost_db: 12.0,
            max_cut_db: -18.0,
            lookahead_ms: 5.0,
            attack_ms: 15.0,
            release_ms: 300.0,
            absolute_threshold_lkfs: -70.0,
            relative_threshold_lu: -10.0,
            pause_threshold_lufs: -55.0,
        }
    }
}

/// Real-time diagnostic telemetry from the LUFS Governor.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct LufsTelemetry {
    /// Momentary Loudness (400 ms sliding window) in LUFS
    pub momentary_lufs: f32,
    /// Short-Term Loudness (3.0 s sliding window) in LUFS
    pub short_term_lufs: f32,
    /// Integrated Loudness (EBU R128 dual-gated) in LUFS
    pub integrated_lufs: f32,
    /// EBU Tech 3342 Loudness Range (LRA) in LU
    pub loudness_range_lu: f32,
    /// Estimated True-Peak level in dBFS
    pub true_peak_dbfs: f32,
    /// Current DRC Gain Reduction in dB (negative = attenuation, positive = boost)
    pub gain_reduction_db: f32,
    /// Active target loudness in LUFS
    pub target_lufs: f32,
}

impl Default for LufsTelemetry {
    fn default() -> Self {
        Self {
            momentary_lufs: -70.0,
            short_term_lufs: -70.0,
            integrated_lufs: -70.0,
            loudness_range_lu: 0.0,
            true_peak_dbfs: -96.0,
            gain_reduction_db: 0.0,
            target_lufs: -23.0,
        }
    }
}

const MAX_INTEGRATED_BLOCKS: usize = 512;

/// Zero-allocation ITU-R BS.1770-4 & EBU R128 Loudness Governor and DRC Engine.
pub struct LufsGovernor {
    config: LufsConfig,
    k_filter: KWeightingFilter,

    // Circular buffers for Momentary (400 ms) and Short-Term (3.0 s) loudness tracking
    momentary_hops: usize,
    short_term_hops: usize,
    hop_energies_momentary: Vec<f32>,
    hop_energies_short_term: Vec<f32>,
    momentary_idx: usize,
    short_term_idx: usize,
    momentary_sum: f32,
    short_term_sum: f32,

    // Dual-gating integrated loudness history (ring buffer of 400ms blocks)
    block_history: [f32; MAX_INTEGRATED_BLOCKS],
    block_count: usize,
    block_idx: usize,

    // Lookahead delay line
    lookahead_buf: Vec<f32>,
    lookahead_len: usize,
    lookahead_idx: usize,

    // DRC gain smoothing
    current_gain_lin: f32,
    alpha_attack: f32,
    alpha_release: f32,

    // Cached telemetry
    telemetry: LufsTelemetry,
}

impl LufsGovernor {
    /// Creates a new LufsGovernor instance with pre-allocated memory.
    pub fn new(config: LufsConfig) -> Self {
        let sample_rate = config.sample_rate;
        let hop_size = config.hop_size.max(1);
        let hop_duration_sec = hop_size as f32 / sample_rate;

        // 400 ms momentary window in number of hops
        let momentary_hops = (0.400 / hop_duration_sec).round().max(1.0) as usize;
        // 3.0 s short-term window in number of hops
        let short_term_hops = (3.000 / hop_duration_sec).round().max(momentary_hops as f32) as usize;

        // Lookahead delay in samples
        let lookahead_len = ((config.lookahead_ms / 1000.0) * sample_rate).round().max(0.0) as usize;

        let alpha_attack = (-1.0 / (config.attack_ms * 0.001 * sample_rate / hop_size as f32)).exp();
        let alpha_release = (-1.0 / (config.release_ms * 0.001 * sample_rate / hop_size as f32)).exp();

        let k_filter = KWeightingFilter::new(sample_rate);

        Self {
            k_filter,
            momentary_hops,
            short_term_hops,
            hop_energies_momentary: vec![0.0; momentary_hops],
            hop_energies_short_term: vec![0.0; short_term_hops],
            momentary_idx: 0,
            short_term_idx: 0,
            momentary_sum: 0.0,
            short_term_sum: 0.0,
            block_history: [0.0; MAX_INTEGRATED_BLOCKS],
            block_count: 0,
            block_idx: 0,
            lookahead_buf: vec![0.0; lookahead_len.max(1)],
            lookahead_len,
            lookahead_idx: 0,
            current_gain_lin: 1.0,
            alpha_attack,
            alpha_release,
            telemetry: LufsTelemetry {
                target_lufs: config.target_lufs,
                ..Default::default()
            },
            config,
        }
    }

    /// Resets all internal filter states, energy histories, and lookahead delay lines.
    pub fn reset(&mut self) {
        self.k_filter.reset();
        self.hop_energies_momentary.fill(0.0);
        self.hop_energies_short_term.fill(0.0);
        self.momentary_idx = 0;
        self.short_term_idx = 0;
        self.momentary_sum = 0.0;
        self.short_term_sum = 0.0;
        self.block_history.fill(0.0);
        self.block_count = 0;
        self.block_idx = 0;
        self.lookahead_buf.fill(0.0);
        self.lookahead_idx = 0;
        self.current_gain_lin = 1.0;
        self.telemetry = LufsTelemetry {
            target_lufs: self.config.target_lufs,
            ..Default::default()
        };
    }

    /// Dynamically sets the target LUFS.
    pub fn set_target_lufs(&mut self, target_lufs: f32) {
        self.config.target_lufs = target_lufs.clamp(-36.0, -12.0);
        self.telemetry.target_lufs = self.config.target_lufs;
    }

    /// Returns the current telemetry.
    pub fn telemetry(&self) -> LufsTelemetry {
        self.telemetry
    }

    /// Calculates ITU-R BS.1770-4 loudness in LKFS/LUFS from mean-square energy z:
    /// L = -0.691 + 10 * log10(z)
    #[inline]
    fn z_to_lufs(z: f32) -> f32 {
        if z <= 1e-12 {
            -96.0
        } else {
            -0.691 + 10.0 * z.log10()
        }
    }

    /// Processes an audio hop in-place, applying ITU-R BS.1770-4 loudness governance
    /// and dynamic range compression.
    ///
    /// Zero heap allocations.
    pub fn process_block(&mut self, audio: &mut [f32]) {
        let n = audio.len();
        if n == 0 {
            return;
        }

        // 1. Measure Peak & True-Peak Level
        let mut max_abs = 0.0f32;
        let mut sum_sq_k = 0.0f32;

        for &s in audio.iter() {
            let abs_s = s.abs();
            if abs_s > max_abs {
                max_abs = abs_s;
            }
            // Filter sample through K-weighting pre-filter
            let y_k = self.k_filter.process_sample(s);
            sum_sq_k += y_k * y_k;
        }

        let hop_energy = sum_sq_k / n as f32;
        let true_peak_dbfs = 20.0 * max_abs.max(1e-5).log10();

        // 2. Update Momentary (400 ms) sliding energy
        let old_m = self.hop_energies_momentary[self.momentary_idx];
        self.hop_energies_momentary[self.momentary_idx] = hop_energy;
        self.momentary_sum = (self.momentary_sum - old_m + hop_energy).max(0.0);
        self.momentary_idx = (self.momentary_idx + 1) % self.momentary_hops;
        let z_momentary = self.momentary_sum / self.momentary_hops as f32;
        let momentary_lufs = Self::z_to_lufs(z_momentary);

        // 3. Update Short-Term (3.0 s) sliding energy
        let old_s = self.hop_energies_short_term[self.short_term_idx];
        self.hop_energies_short_term[self.short_term_idx] = hop_energy;
        self.short_term_sum = (self.short_term_sum - old_s + hop_energy).max(0.0);
        self.short_term_idx = (self.short_term_idx + 1) % self.short_term_hops;
        let z_short_term = self.short_term_sum / self.short_term_hops as f32;
        let short_term_lufs = Self::z_to_lufs(z_short_term);

        // 4. Update Integrated Loudness with BS.1770-4 Dual-Gating
        // Every ~100 ms (or once momentary window has fresh data), store block
        self.block_history[self.block_idx] = z_momentary;
        self.block_idx = (self.block_idx + 1) % MAX_INTEGRATED_BLOCKS;
        if self.block_count < MAX_INTEGRATED_BLOCKS {
            self.block_count += 1;
        }

        let (integrated_lufs, lra) = self.compute_dual_gated_metrics();

        // 5. Tactical DRC Loudness Governor calculation
        // Target error based on Momentary/Short-Term loudness
        let governing_loudness = if momentary_lufs > -60.0 {
            // Fast attack on momentary speech bursts, stabilized by short-term
            0.60 * momentary_lufs + 0.40 * short_term_lufs
        } else {
            short_term_lufs
        };

        let target_gain_db = if governing_loudness <= self.config.pause_threshold_lufs {
            // Speech pause / ambient silence: smoothly return to unity gain (0 dB) to prevent noise pumping
            0.0
        } else {
            let error_db = self.config.target_lufs - governing_loudness;
            error_db.clamp(self.config.max_cut_db, self.config.max_boost_db)
        };

        let target_gain_lin = 10.0f32.powf(target_gain_db / 20.0);

        // Smooth gain transition with asymmetric attack/release
        let alpha = if target_gain_lin < self.current_gain_lin {
            self.alpha_attack // Fast gain reduction to suppress loud shouts
        } else {
            self.alpha_release // Slow gain boost to avoid pumping
        };
        self.current_gain_lin = alpha * self.current_gain_lin + (1.0 - alpha) * target_gain_lin;
        let gain_reduction_db = 20.0 * self.current_gain_lin.max(1e-5).log10();

        // 6. Apply Lookahead Delay & Gain Compression
        if self.lookahead_len > 0 {
            for s in audio.iter_mut() {
                // Read delayed sample from lookahead ring buffer
                let delayed_sample = self.lookahead_buf[self.lookahead_idx];
                self.lookahead_buf[self.lookahead_idx] = *s;
                self.lookahead_idx = (self.lookahead_idx + 1) % self.lookahead_len;

                // Scale delayed sample by smoothly updated gain
                *s = (delayed_sample * self.current_gain_lin).clamp(-0.999, 0.999);
            }
        } else {
            for s in audio.iter_mut() {
                *s = (*s * self.current_gain_lin).clamp(-0.999, 0.999);
            }
        }

        // 7. Store Telemetry
        self.telemetry = LufsTelemetry {
            momentary_lufs,
            short_term_lufs,
            integrated_lufs,
            loudness_range_lu: lra,
            true_peak_dbfs,
            gain_reduction_db,
            target_lufs: self.config.target_lufs,
        };
    }

    /// Computes BS.1770-4 dual-gated Integrated Loudness and EBU Tech 3342 Loudness Range (LRA).
    fn compute_dual_gated_metrics(&self) -> (f32, f32) {
        if self.block_count == 0 {
            return (-70.0, 0.0);
        }

        let abs_thresh_z = 10.0f32.powf((self.config.absolute_threshold_lkfs + 0.691) / 10.0);

        // Step 1: Absolute Gating (-70 LKFS)
        let mut abs_sum = 0.0f32;
        let mut abs_count = 0usize;

        for i in 0..self.block_count {
            let z = self.block_history[i];
            if z >= abs_thresh_z {
                abs_sum += z;
                abs_count += 1;
            }
        }

        if abs_count == 0 {
            return (-70.0, 0.0);
        }

        let z_abs_mean = abs_sum / abs_count as f32;
        let l_abs_mean = Self::z_to_lufs(z_abs_mean);

        // Step 2: Relative Gating (-10 LU relative to absolute-gated mean)
        let rel_thresh_lufs = l_abs_mean + self.config.relative_threshold_lu;
        let rel_thresh_z = 10.0f32.powf((rel_thresh_lufs + 0.691) / 10.0);

        let mut rel_sum = 0.0f32;
        let mut rel_count = 0usize;
        let mut gated_loudness_vals = [0.0f32; MAX_INTEGRATED_BLOCKS];

        for i in 0..self.block_count {
            let z = self.block_history[i];
            if z >= rel_thresh_z {
                rel_sum += z;
                gated_loudness_vals[rel_count] = Self::z_to_lufs(z);
                rel_count += 1;
            }
        }

        if rel_count == 0 {
            return (l_abs_mean, 0.0);
        }

        let z_integrated = rel_sum / rel_count as f32;
        let integrated_lufs = Self::z_to_lufs(z_integrated);

        // Step 3: EBU Tech 3342 Loudness Range (LRA) = P95 - P10 of gated blocks
        let active_slice = &mut gated_loudness_vals[..rel_count];
        active_slice.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

        let idx_10 = (0.10 * (rel_count - 1) as f32).round() as usize;
        let idx_95 = (0.95 * (rel_count - 1) as f32).round() as usize;
        let p10 = active_slice[idx_10.min(rel_count - 1)];
        let p95 = active_slice[idx_95.min(rel_count - 1)];
        let lra = (p95 - p10).max(0.0);

        (integrated_lufs, lra)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_k_weighting_filter_creation_and_reset() {
        let mut filter = KWeightingFilter::new(16000.0);
        assert!(!filter.shelf.b0.is_nan());
        assert!(!filter.highpass.b0.is_nan());

        // Process impulse
        let y0 = filter.process_sample(1.0);
        assert!(y0 > 0.0);
        filter.reset();
        let y0_after = filter.process_sample(1.0);
        assert!((y0 - y0_after).abs() < 1e-6);
    }

    #[test]
    fn test_k_weighting_high_shelf_gain() {
        let mut filter = KWeightingFilter::new(16000.0);

        // High frequency (e.g. 4 kHz tone) must receive positive gain (~+4 dB) relative to low frequency (200 Hz)
        let mut energy_low = 0.0f32;
        let mut energy_high = 0.0f32;
        let n = 1600;

        for i in 0..n {
            let t = i as f32 / 16000.0;
            let low_in = (2.0 * PI * 200.0 * t).sin();
            let y_low = filter.process_sample(low_in);
            if i > 400 {
                energy_low += y_low * y_low;
            }
        }

        filter.reset();
        for i in 0..n {
            let t = i as f32 / 16000.0;
            let high_in = (2.0 * PI * 4000.0 * t).sin();
            let y_high = filter.process_sample(high_in);
            if i > 400 {
                energy_high += y_high * y_high;
            }
        }

        // 4 kHz should have significantly higher energy than 200 Hz through K-weighting
        assert!(energy_high > energy_low * 1.5);
    }

    #[test]
    fn test_lufs_governor_silence_behavior() {
        let config = LufsConfig {
            sample_rate: 16000.0,
            hop_size: 256,
            target_lufs: -23.0,
            ..Default::default()
        };
        let mut governor = LufsGovernor::new(config);
        let mut audio = vec![0.0f32; 256];

        governor.process_block(&mut audio);
        let telem = governor.telemetry();

        // In pure silence, momentary loudness must be near minimum floor
        assert!(telem.momentary_lufs < -65.0);
        // Gain reduction should be near unity (0 dB) so silence is not pumped up
        assert!(telem.gain_reduction_db.abs() < 1.0);
    }

    #[test]
    fn test_lufs_governor_attenuates_shouting_signal() {
        let config = LufsConfig {
            sample_rate: 16000.0,
            hop_size: 256,
            target_lufs: -23.0,
            attack_ms: 5.0,
            ..Default::default()
        };
        let mut governor = LufsGovernor::new(config);

        // Loud shouting sine wave at 0 dBFS peak (~ -3 LUFS)
        for _ in 0..30 {
            let mut block = vec![0.0f32; 256];
            for (i, s) in block.iter_mut().enumerate() {
                *s = 0.95 * (2.0 * PI * 1000.0 * i as f32 / 16000.0).sin();
            }
            governor.process_block(&mut block);
        }

        let telem = governor.telemetry();
        // Loudness must be high
        assert!(telem.momentary_lufs > -10.0);
        // DRC must apply negative gain reduction (attenuation)
        assert!(telem.gain_reduction_db < -5.0);
        assert!(telem.true_peak_dbfs <= 0.0);
    }

    #[test]
    fn test_lufs_governor_boosts_whispering_signal() {
        let config = LufsConfig {
            sample_rate: 16000.0,
            hop_size: 256,
            target_lufs: -23.0,
            max_boost_db: 12.0,
            pause_threshold_lufs: -65.0,
            ..Default::default()
        };
        let mut governor = LufsGovernor::new(config);

        // Quiet whispering pilot speech: ~ -35 LUFS
        for _ in 0..40 {
            let mut block = vec![0.0f32; 256];
            for (i, s) in block.iter_mut().enumerate() {
                *s = 0.02 * (2.0 * PI * 1000.0 * i as f32 / 16000.0).sin();
            }
            governor.process_block(&mut block);
        }

        let telem = governor.telemetry();
        // DRC must apply positive gain (boost)
        assert!(telem.gain_reduction_db > 2.0);
    }
}
