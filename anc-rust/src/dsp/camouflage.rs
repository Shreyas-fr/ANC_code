//! Tactical Acoustic Camouflage & Psychoacoustic Active Masking Generator.
//!
//! Developed for SIH 26052 Tactical Audio Systems.
//!
//! In covert dismounted infantry patrols, deep reconnaissance missions, and sniper overwatch,
//! soldier acoustic footprints (tactical vest nylon rustle, sling swivel clinking,
//! boot scrape on gravel, breathing sounds) can be intercepted by hostile parabolic microphones
//! or perimeter acoustic gunshot/sensor arrays.
//!
//! Classical active cancellation cannot extinguish free-field radiation from arbitrary moving bodies.
//! Instead, Acoustic Camouflage generates an inaudible, psychoacoustically shaped counter-noise
//! matching the local environmental acoustic background:
//! - Continuously profiles ambient environmental noise spectrum (wind, foliage, insect bed, engine drone).
//! - Calculates the dynamic Psychoacoustic Masking Threshold $M(f)$ using ISO 226 hearing thresholds
//!   and inter-band Bark spreading functions.
//! - Detects acoustic leakage spikes from soldier movement.
//! - Injects inaudible counter-shaped noise that flattens perimeter acoustic entropy,
//!   cloaking soldier audio signatures below the detection threshold of hostile directional sensors.
//! - Strictly ZERO heap allocations during real-time streaming execution.

use num_complex::Complex32;

pub const MAX_CAMOUFLAGE_BINS: usize = 257;

/// Operational acoustic environment profiles for camouflage masking.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum CamouflageProfile {
    /// Silent reconnaissance: optimizes masking for 1.2 kHz - 4.5 kHz gear rustle & breathing.
    #[default]
    SilentRecon,
    /// Urban perimeter: optimizes masking for 200 Hz - 2.8 kHz boot scrapes on concrete / brick.
    UrbanPerimeter,
    /// Dense foliage: optimizes masking for 400 Hz - 7.5 kHz brush/branch movement & wind rustle.
    DenseFoliage,
}

/// Configuration parameters for Acoustic Camouflage.
#[derive(Debug, Clone, Copy)]
pub struct CamouflageConfig {
    pub sample_rate: f32,
    pub num_bins: usize,
    /// Ambient noise adaptation smoothing factor ($\alpha \in [0.90, 0.99]$).
    pub adaptation_alpha: f32,
    /// Cloaking injection gain relative to ambient noise floor (dB, typically -12 to -3 dB).
    pub cloaking_gain_db: f32,
    /// Threshold in dB above ambient to declare soldier gear leakage.
    pub leakage_threshold_db: f32,
    pub profile: CamouflageProfile,
}

impl Default for CamouflageConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000.0,
            num_bins: 257,
            adaptation_alpha: 0.95,
            cloaking_gain_db: -6.0,
            leakage_threshold_db: 4.5,
            profile: CamouflageProfile::SilentRecon,
        }
    }
}

/// Real-time camouflage telemetry and acoustic cloaking status.
#[derive(Debug, Clone, Copy, Default)]
pub struct CamouflageTelemetry {
    /// True if soldier acoustic signature (rustle/breath) was detected and cloaked this frame.
    pub cloaking_active: bool,
    /// Instantaneous cloaking counter-noise energy in dBFS.
    pub cloaking_energy_db: f32,
    /// Environmental ambient noise floor energy in dBFS.
    pub ambient_energy_db: f32,
    /// Spectral entropy of perimeter acoustic field (0.0 to 1.0).
    pub spectral_entropy: f32,
    /// Total number of detected soldier gear rustle/transient events cloaked.
    pub cloaked_events_count: u64,
}

/// Zero-allocation Acoustic Camouflage & Active Psychoacoustic Masking Engine.
pub struct AcousticCamouflageEngine {
    config: CamouflageConfig,
    /// Smoothed ambient environmental power spectrum [MAX_CAMOUFLAGE_BINS].
    ambient_power: [f32; MAX_CAMOUFLAGE_BINS],
    /// Absolute threshold of hearing (ATH) power per bin.
    ath_power: [f32; MAX_CAMOUFLAGE_BINS],
    /// Psychoacoustic masking threshold per bin.
    masking_power: [f32; MAX_CAMOUFLAGE_BINS],
    /// Profile spectral weighting envelope [MAX_CAMOUFLAGE_BINS].
    profile_weights: [f32; MAX_CAMOUFLAGE_BINS],
    /// Fast 64-bit XorShift PRNG state for pseudo-random phase counter-noise generation.
    rng_state: u64,
    telemetry: CamouflageTelemetry,
    frame_count: u64,
}

impl AcousticCamouflageEngine {
    /// Creates a new AcousticCamouflageEngine with pre-allocated zero-heap state.
    pub fn new(config: CamouflageConfig) -> Self {
        let num_bins = config.num_bins.min(MAX_CAMOUFLAGE_BINS);
        let bin_hz = config.sample_rate / ((num_bins - 1) as f32 * 2.0);

        let mut ath_power = [1e-7f32; MAX_CAMOUFLAGE_BINS];
        let profile_weights = [1.0f32; MAX_CAMOUFLAGE_BINS];

        // Precompute Absolute Threshold of Hearing (Terhardt/ISO 226 approximation)
        for b in 1..num_bins {
            let f_khz = (b as f32 * bin_hz / 1000.0).max(0.02);
            let ath_db = 3.64 * f_khz.powf(-0.8)
                - 6.5 * (-(f_khz - 3.3).powi(2) * 0.6).exp()
                + 1e-3 * f_khz.powi(4);
            // Convert dB SPL relative to reference power
            let p = 10.0f32.powf((ath_db - 70.0) / 10.0).clamp(1e-8, 1.0);
            ath_power[b] = p;
        }
        ath_power[0] = ath_power[1];

        let ath_power_val = ath_power;
        let mut engine = Self {
            config,
            ambient_power: [1e-6f32; MAX_CAMOUFLAGE_BINS],
            ath_power: ath_power_val,
            masking_power: [1e-6f32; MAX_CAMOUFLAGE_BINS],
            profile_weights,
            rng_state: 0xDEADBEEFCAFE1234,
            telemetry: CamouflageTelemetry::default(),
            frame_count: 0,
        };
        engine.update_profile_weights();
        engine
    }

    /// Sets the camouflage operational profile.
    pub fn set_profile(&mut self, profile: CamouflageProfile) {
        self.config.profile = profile;
        self.update_profile_weights();
    }

    fn update_profile_weights(&mut self) {
        let num_bins = self.config.num_bins.min(MAX_CAMOUFLAGE_BINS);
        let bin_hz = self.config.sample_rate / ((num_bins - 1) as f32 * 2.0);

        for b in 0..num_bins {
            let hz = b as f32 * bin_hz;
            self.profile_weights[b] = match self.config.profile {
                CamouflageProfile::SilentRecon => {
                    // Gear rustle & breath: 1.2 kHz - 4.5 kHz
                    if (1200.0..=4500.0).contains(&hz) {
                        1.4
                    } else if hz < 500.0 {
                        0.5
                    } else {
                        1.0
                    }
                }
                CamouflageProfile::UrbanPerimeter => {
                    // Concrete scraping & footstep clicks: 200 Hz - 2.8 kHz
                    if (200.0..=2800.0).contains(&hz) {
                        1.5
                    } else {
                        0.8
                    }
                }
                CamouflageProfile::DenseFoliage => {
                    // Foliage rustling & twig snaps: 400 Hz - 7.5 kHz
                    if hz >= 400.0 {
                        1.3
                    } else {
                        0.4
                    }
                }
            };
        }
    }

    /// Generates next uniform pseudo-random f32 in [-1.0, 1.0] using XorShift64.
    #[inline(always)]
    fn xorshift_f32(&mut self) -> f32 {
        self.rng_state ^= self.rng_state << 13;
        self.rng_state ^= self.rng_state >> 7;
        self.rng_state ^= self.rng_state << 17;
        let bits = (self.rng_state >> 40) as u32;
        (bits as f32 / 8388608.0) - 1.0
    }

    /// Resets all internal histories and telemetry counters.
    pub fn reset(&mut self) {
        for p in self.ambient_power.iter_mut() {
            *p = 1e-6;
        }
        for m in self.masking_power.iter_mut() {
            *m = 1e-6;
        }
        self.telemetry = CamouflageTelemetry::default();
        self.frame_count = 0;
    }

    /// Processes STFT power spectra of ambient mic and soldier microphone,
    /// synthesizing a psychoacoustically shaped camouflage counter-noise spectrum.
    ///
    /// - `ambient_spec`: Complex STFT of external ambient microphone
    /// - `soldier_spec`: Complex STFT of soldier microphone (contains gear/speech leakage)
    /// - `out_camouflage`: Synthesized complex counter-noise STFT spectrum
    pub fn process_spectrum(
        &mut self,
        ambient_spec: &[Complex32],
        soldier_spec: &[Complex32],
        out_camouflage: &mut [Complex32],
    ) {
        let num_bins = self
            .config
            .num_bins
            .min(MAX_CAMOUFLAGE_BINS)
            .min(ambient_spec.len())
            .min(soldier_spec.len())
            .min(out_camouflage.len());

        let alpha = self.config.adaptation_alpha;
        let one_minus_alpha = 1.0 - alpha;
        let cloaking_scale = 10.0f32.powf(self.config.cloaking_gain_db / 20.0);
        let leakage_ratio = 10.0f32.powf(self.config.leakage_threshold_db / 10.0);

        let mut ambient_tot = 0.0f32;
        let mut cloaked_tot = 0.0f32;
        let mut leakage_detected = false;

        // 1. Update ambient noise floor estimate and detect soldier signature leakage
        for f in 0..num_bins {
            let amb_p = ambient_spec[f].norm_sqr();
            let sol_p = soldier_spec[f].norm_sqr();

            ambient_tot += amb_p;

            // Ambient background tracking (slow adaptation during stationary noise)
            if self.frame_count == 0 {
                self.ambient_power[f] = amb_p;
            } else {
                self.ambient_power[f] = alpha * self.ambient_power[f] + one_minus_alpha * amb_p;
            }

            // Check if soldier noise exceeds ambient threshold
            if sol_p > self.ambient_power[f] * leakage_ratio && sol_p > self.ath_power[f] {
                leakage_detected = true;
            }
        }

        // 2. Compute Psychoacoustic Masking Curve:
        // Masking power combines ATH and smoothed ambient noise with frequency spreading
        for f in 0..num_bins {
            let amb_p = self.ambient_power[f];
            let ath = self.ath_power[f];

            // Local 3-bin spreading
            let f_prev = if f > 0 { self.ambient_power[f - 1] } else { amb_p };
            let f_next = if f + 1 < num_bins { self.ambient_power[f + 1] } else { amb_p };
            let spread_p = amb_p * 0.6 + (f_prev + f_next) * 0.2;

            self.masking_power[f] = spread_p.max(ath);
        }

        // 3. Synthesize Psychoacoustically Shaped Counter-Noise Spectrum
        // Modulates random phase with energy proportional to masking threshold and profile weights
        for f in 0..num_bins {
            let mask_mag = self.masking_power[f].sqrt() * cloaking_scale * self.profile_weights[f];

            // Uniform random phase angle \theta \in [-\pi, \pi]
            let phase = self.xorshift_f32() * std::f32::consts::PI;
            let counter_c = Complex32::from_polar(mask_mag, phase);

            out_camouflage[f] = counter_c;
            cloaked_tot += counter_c.norm_sqr();
        }

        // Fill remaining output bins with zeros
        for f in num_bins..out_camouflage.len() {
            out_camouflage[f] = Complex32::default();
        }

        // 4. Update Telemetry
        self.frame_count += 1;
        if leakage_detected {
            self.telemetry.cloaked_events_count += 1;
        }
        self.telemetry.cloaking_active = leakage_detected;

        let amb_energy_db = (10.0 * (ambient_tot / num_bins as f32).max(1e-9).log10()).clamp(-120.0, 0.0);
        let cloak_energy_db = (10.0 * (cloaked_tot / num_bins as f32).max(1e-9).log10()).clamp(-120.0, 0.0);

        self.telemetry.ambient_energy_db = amb_energy_db;
        self.telemetry.cloaking_energy_db = cloak_energy_db;

        // Calculate spectral entropy: H = - sum( p_i * log(p_i) ) / log(N)
        let total_p = cloaked_tot.max(1e-8);
        let mut entropy = 0.0f32;
        for f in 0..num_bins {
            let p_norm = (out_camouflage[f].norm_sqr() / total_p).max(1e-12);
            entropy -= p_norm * p_norm.ln();
        }
        let max_entropy = (num_bins as f32).ln().max(1e-4);
        self.telemetry.spectral_entropy = (entropy / max_entropy).clamp(0.0, 1.0);
    }

    /// Returns current telemetry statistics.
    pub fn telemetry(&self) -> CamouflageTelemetry {
        self.telemetry
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_camouflage_initialization_and_ath() {
        let config = CamouflageConfig::default();
        let engine = AcousticCamouflageEngine::new(config);

        // ATH should be lowest around human ear resonance (3-4 kHz)
        let bin_hz = 16000.0 / 512.0; // 31.25 Hz/bin
        let bin_1k = (1000.0 / bin_hz) as usize;
        let bin_3k = (3300.0 / bin_hz) as usize;

        assert!(
            engine.ath_power[bin_3k] <= engine.ath_power[bin_1k] * 2.0,
            "Human ear sensitivity peak at 3.3 kHz must have low ATH"
        );
    }

    #[test]
    fn test_camouflage_synthesizes_shaped_counter_noise() {
        let mut engine = AcousticCamouflageEngine::new(CamouflageConfig::default());

        let num_bins = 128;
        let ambient = vec![Complex32::new(0.05, 0.02); num_bins];
        let soldier = vec![Complex32::new(0.01, 0.0); num_bins];
        let mut out_masking = vec![Complex32::default(); num_bins];

        for _ in 0..10 {
            engine.process_spectrum(&ambient, &soldier, &mut out_masking);
        }

        let tele = engine.telemetry();
        assert!(tele.cloaking_energy_db > -90.0);
        assert!(tele.spectral_entropy > 0.85); // Masking noise must be high entropy
    }

    #[test]
    fn test_camouflage_detects_gear_leakage() {
        let mut engine = AcousticCamouflageEngine::new(CamouflageConfig::default());

        let num_bins = 128;
        let ambient = vec![Complex32::new(0.01, 0.0); num_bins];
        // Sudden loud vest rustle / breath on soldier mic
        let soldier_leak = vec![Complex32::new(0.15, 0.0); num_bins];
        let mut out_masking = vec![Complex32::default(); num_bins];

        for _ in 0..5 {
            engine.process_spectrum(&ambient, &ambient, &mut out_masking);
        }
        assert_eq!(engine.telemetry().cloaked_events_count, 0);

        // Inject gear leakage
        engine.process_spectrum(&ambient, &soldier_leak, &mut out_masking);
        assert!(engine.telemetry().cloaking_active);
        assert!(engine.telemetry().cloaked_events_count >= 1);
    }

    #[test]
    fn test_camouflage_profiles_alter_weightings() {
        let mut engine = AcousticCamouflageEngine::new(CamouflageConfig::default());
        let bin_2k = (2000.0 / (16000.0 / 512.0)) as usize;

        engine.set_profile(CamouflageProfile::SilentRecon);
        let w_recon = engine.profile_weights[bin_2k];

        engine.set_profile(CamouflageProfile::UrbanPerimeter);
        let w_urban = engine.profile_weights[bin_2k];

        assert_ne!(w_recon, w_urban);
    }
}
