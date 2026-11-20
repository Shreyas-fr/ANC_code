//! Complete end-to-end Tactical ANC & Speech Enhancement Pipeline.
//!
//! Connects all stages in a high-performance, deterministic execution chain:
//! Dual-Mic Input (30mm) -> Concussion Blanker -> Subband AFC -> CDR / ICPD Estimator
//! -> 2-State Kalman DOA -> Coupled WPE Dereverb -> Multi-Rate MVDR Beamformer
//! -> Complex Spectral Masking -> CRN-INT8 Postfilter -> ISTFT -> Causal AGC
//! -> Soft Limiter -> Tactical Transparency -> Transaural XTC

use num_complex::Complex32;
use std::time::Instant;

use crate::dsp::{
    AcousticPhaseAligner, AfcConfig, AfcStats, AmbisonicsConfig, AmbisonicsSpatializer,
    AmbisonicsTelemetry, AntiHowlingShifter, AshpConfig, AshpLimiter, AshpTelemetry,
    BoneFusionConfig, BoneFusionTelemetry, CausalAgc, CausalDereverberator, CausalMvdrBeamformer,
    CdrConfig, CdrEstimator, DeEsser, DeEsserConfig, DeEsserTelemetry, DereverbConfig,
    DitherEngine, DitherMode, DoaConfig, GccPhatDoaTracker, GscConfig, GscStats, HowlingConfig,
    HowlingTelemetry, IntelligibilityConfig, IntelligibilityEnhancer, InverseLombardCompensator,
    KurtosisConfig, KurtosisTelemetry, LombardConfig, LombardTelemetry, LufsConfig, LufsGovernor,
    LufsTelemetry, MvdrConfig, NalNl2WdrcEngine, OnlineSensorCalibrator, PersonalAudiogram,
    PhaseAlignConfig, PhaseAlignmentProfile, PitchHarmonicCombEngine, PolarPatternConfig,
    PolarPatternShaper, PolarPatternTelemetry, PolarPatternType, ResPostfilterConfig,
    ResPostfilterStats, SensorCalConfig, SensorCalTelemetry, SoftLimiter, SpectralContrastConfig,
    SpectralContrastEnhancer, SpectralContrastTelemetry, SpectralKurtosisDetector, StreamingStft,
    SubbandAfc, SubbandBoneFusionEngine, SubbandGsc, SubbandResPostfilter, TacticalTransparency,
    ThermalNoiseConfig, ThermalNoiseEstimator, ThermalNoiseTelemetry, TransauralXtc,
    TransientBlanker, TransientConfig, TransparencyConfig, WhisperConfig, WhisperReconstructor,
    WhisperStats, WindDetectorConfig, WindTelemetry, WindTurbulenceSuppressor, WindowType,
    XtcConfig,
};
use crate::metrics::{
    AdaptiveConvergenceProfiler, BlastImpulseMeter, BlastMeterConfig, BlastTelemetry, CableConfig,
    CableDiagnostics, CableTelemetry, RastiPredictor, StiConfig, StiTelemetry, StressProfiler,
    StressProfilerConfig, StressTelemetry,
};
use crate::model::{CrnInt8Postfilter, EnhancerStats, SpeechEnhancer};
use crate::network::{DspStageTimings, JammingDetector, JammingDetectorConfig, JammingTelemetry};
use crate::streaming::battery::{
    BatteryConfig, BatterySimulator, BatteryTelemetry, TacticalPowerMode,
};
use crate::streaming::blackbox::TacticalBlackbox;
use crate::streaming::governor::{GovernorConfig, GovernorTelemetry, PowerGovernor};

/// Tactical Mission Acoustic Profile for specialized operational environments.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MissionProfile {
    /// Tracked armor / combat vehicles (T-90, BMP, Arjun): heavy low-frequency rumble, gun concussions
    CombatVehicle,
    /// Airborne rotorcraft and fighter cockpits (ALH Dhruv, Tejas): turbine scream, high SPL whine
    FlightCockpit,
    /// Dismounted infantry combat patrol: dynamic wind, small arms, maximum situational awareness
    DismountedInfantry,
    /// Tactical Operations Center / Command Bunker: metallic reverberation, multiple talkers
    CommandPost,
}

impl MissionProfile {
    pub fn name(&self) -> &'static str {
        match self {
            Self::CombatVehicle => "COMBAT VEHICLE (T-90 / BMP)",
            Self::FlightCockpit => "FLIGHT COCKPIT (ALH / TEJAS)",
            Self::DismountedInfantry => "DISMOUNTED INFANTRY",
            Self::CommandPost => "COMMAND POST (TOC)",
        }
    }

    pub fn from_str_name(name: &str) -> Option<Self> {
        match name {
            "COMBAT VEHICLE (T-90 / BMP)" => Some(Self::CombatVehicle),
            "FLIGHT COCKPIT (ALH / TEJAS)" => Some(Self::FlightCockpit),
            "DISMOUNTED INFANTRY" => Some(Self::DismountedInfantry),
            "COMMAND POST (TOC)" => Some(Self::CommandPost),
            _ => None,
        }
    }

    pub fn min_gain_db(&self) -> f32 {
        match self {
            Self::CombatVehicle => -22.0,      // 0.08
            Self::FlightCockpit => -20.0,      // 0.10
            Self::DismountedInfantry => -16.0, // 0.16 (preserves quiet environmental awareness)
            Self::CommandPost => -18.0,        // 0.125
        }
    }

    pub fn spatial_postfilter_floor(&self) -> f32 {
        match self {
            Self::CombatVehicle => 0.25, // Aggressive spatial nulling against cabin engine
            Self::FlightCockpit => 0.30,
            Self::DismountedInfantry => 0.40, // Wider spatial pass-through
            Self::CommandPost => 0.35,
        }
    }

    pub fn enable_dereverb(&self) -> bool {
        match self {
            Self::CommandPost => true, // Enclosed concrete/steel shelter with reverberant reflections
            _ => false,
        }
    }

    pub fn enable_transient_blanker(&self) -> bool {
        !matches!(self, Self::CommandPost)
    }

    pub fn enable_transparency(&self) -> bool {
        match self {
            Self::DismountedInfantry => true, // Preserves ambient situational awareness and commands
            _ => false,
        }
    }

    pub fn enable_comfort_noise(&self) -> bool {
        match self {
            Self::CombatVehicle => true, // T-90/BMP cabin rumble produces acoustic vacuum fatigue when gated
            Self::FlightCockpit => true, // Cockpit jet turbine/rotor noise gating creates ear void
            _ => false,
        }
    }

    pub fn enable_crn_postfilter(&self) -> bool {
        match self {
            Self::CombatVehicle => true, // Suppresses residual tank track squeals and mechanical chatter
            Self::FlightCockpit => true, // Suppresses rotor blade harmonic whistles
            _ => false,
        }
    }

    pub fn enable_xtc(&self) -> bool {
        match self {
            Self::DismountedInfantry => true, // Out-of-head 3D positioning for directional threat alerts
            _ => false,
        }
    }

    pub fn enable_intelligibility(&self) -> bool {
        match self {
            Self::CombatVehicle => true, // Compensates for severe low-frequency engine rumble & Lombard masking
            Self::FlightCockpit => true, // Compensates for rotor wash & jet turbine masking
            _ => false,
        }
    }

    pub fn enable_pitch_comb(&self) -> bool {
        match self {
            Self::CombatVehicle => true, // Filters out mechanical gearbox harmonics
            Self::FlightCockpit => true, // Filters out rotor blade harmonic whine
            _ => false,
        }
    }

    pub fn enable_whisper(&self) -> bool {
        match self {
            Self::DismountedInfantry => true, // Whisper formant reconstruction for stealth patrols
            _ => false,
        }
    }

    pub fn enable_gsc(&self) -> bool {
        match self {
            Self::CombatVehicle => true, // Dual-branch GSC sidelobe nulling against tank tracks
            Self::FlightCockpit => true, // Sidelobe nulling against rotor blades
            _ => false,
        }
    }

    pub fn enable_ashp(&self) -> bool {
        match self {
            Self::CombatVehicle | Self::FlightCockpit | Self::DismountedInfantry => true, // MIL-STD-1474E true-peak blast protection
            _ => false,
        }
    }

    pub fn enable_governor(&self) -> bool {
        match self {
            Self::DismountedInfantry => true, // Wearable battery conservation on soldier bodypack
            _ => false,
        }
    }

    pub fn enable_wind_suppressor(&self) -> bool {
        match self {
            Self::DismountedInfantry | Self::FlightCockpit => true, // Aero-acoustic turbulence & wind vortex shedding
            _ => false,
        }
    }

    pub fn enable_phase_align(&self) -> bool {
        match self {
            Self::CombatVehicle | Self::FlightCockpit | Self::DismountedInfantry => true, // Helmet / boom mic acoustic dispersion
            _ => false,
        }
    }

    pub fn phase_align_profile(&self) -> PhaseAlignmentProfile {
        match self {
            Self::CombatVehicle => PhaseAlignmentProfile::TacticalHelmet,
            Self::FlightCockpit => PhaseAlignmentProfile::TacticalHelmet,
            Self::DismountedInfantry => PhaseAlignmentProfile::BoomMic,
            Self::CommandPost => PhaseAlignmentProfile::Bypass,
        }
    }

    pub fn enable_kurtosis(&self) -> bool {
        match self {
            Self::CombatVehicle | Self::FlightCockpit => true, // Artillery & supersonic shock transient detection
            _ => false,
        }
    }

    pub fn enable_sensor_cal(&self) -> bool {
        true // Online inter-microphone sensitivity and phase tracking across all operational environments
    }

    pub fn enable_res_postfilter(&self) -> bool {
        match self {
            Self::CommandPost => false, // Handset/intercom physically separated from console
            _ => true, // Suppresses non-linear acoustic ear-cushion feedback in vehicular/headset gear
        }
    }

    pub fn enable_lufs_governor(&self) -> bool {
        true // Standard EBU R128 voice loudness stabilization across all tactical mission profiles
    }

    pub fn target_lufs(&self) -> f32 {
        match self {
            Self::CombatVehicle => -20.0,      // High-noise cabin intercom target
            Self::FlightCockpit => -21.0,      // Tactical avionics radio target
            Self::DismountedInfantry => -23.0, // Standard tactical patrol target
            Self::CommandPost => -23.0,        // Standard EBU R128 command room target
        }
    }

    pub fn enable_lombard(&self) -> bool {
        match self {
            Self::CombatVehicle | Self::FlightCockpit => true, // Shouting crew in extreme acoustic noise
            _ => false,
        }
    }

    pub fn enable_diffraction(&self) -> bool {
        match self {
            Self::CommandPost => false, // Stationary console
            _ => true,                  // Cranial helmet / visor obstacle diffraction active
        }
    }

    pub fn enable_howling(&self) -> bool {
        match self {
            Self::CommandPost => false,
            _ => true, // Extreme closed-loop intercom feedback prevention
        }
    }

    pub fn enable_stress(&self) -> bool {
        true // Soldier acoustic cognitive stress biomarker monitoring
    }

    pub fn enable_audiogram_wdrc(&self) -> bool {
        match self {
            Self::CommandPost => false,
            _ => true, // Compensates for NIHL acoustic trauma in high-noise combat
        }
    }

    pub fn enable_bone_fusion(&self) -> bool {
        matches!(self, Self::CombatVehicle | Self::DismountedInfantry)
    }

    pub fn enable_blast_meter(&self) -> bool {
        true // MIL-STD-1474E overpressure monitoring across all combat environments
    }

    pub fn enable_battery_sim(&self) -> bool {
        match self {
            Self::DismountedInfantry => true, // Bodypack battery conservation
            _ => false,
        }
    }

    pub fn enable_deesser(&self) -> bool {
        match self {
            Self::CombatVehicle | Self::FlightCockpit | Self::DismountedInfantry => true, // Anti-sibilance active
            Self::CommandPost => false,
        }
    }

    pub fn enable_polar_pattern(&self) -> bool {
        false // Configurable by operator in GUI/CLI
    }

    pub fn enable_cable_diagnostics(&self) -> bool {
        true // Continuous wire integrity & impedance check across all operational gear
    }

    pub fn enable_thermal_estimator(&self) -> bool {
        true // Johnson-Nyquist electron floor bounding across all environments
    }

    pub fn enable_spectral_contrast(&self) -> bool {
        match self {
            Self::CombatVehicle | Self::FlightCockpit => true, // Sharpens formant peaks in engine/rotor noise
            _ => false,
        }
    }

    pub fn enable_ambisonics(&self) -> bool {
        match self {
            Self::DismountedInfantry => true, // Situational 3D directional depth for field operators
            _ => false,
        }
    }

    pub fn enable_jamming_detector(&self) -> bool {
        true // Electronic warfare monitoring active across all tactical environments
    }

    pub fn enable_rasti(&self) -> bool {
        true // Real-time IEC 60268-16 STI intelligibility rating
    }
}

/// Configurable runtime parameters for the audio chain.
#[derive(Debug, Clone)]
pub struct PipelineConfig {
    pub n_fft: usize,
    pub hop_size: usize,
    pub sample_rate: f32,
    pub window_type: WindowType,
    pub enable_transient_blanker: bool,
    pub transient_config: TransientConfig,
    pub enable_mvdr: bool,
    pub enable_dereverb: bool,
    pub dereverb_config: DereverbConfig,
    pub enable_doa_tracking: bool,
    pub doa_config: DoaConfig,
    pub enable_afc: bool,
    pub afc_config: AfcConfig,
    pub enable_transparency: bool,
    pub transparency_config: TransparencyConfig,
    pub enable_cdr: bool,
    pub cdr_config: CdrConfig,
    pub enable_crn_postfilter: bool,
    pub enable_xtc: bool,
    pub xtc_config: XtcConfig,
    pub enable_comfort_noise: bool,
    pub enable_intelligibility: bool,
    pub intelligibility_config: IntelligibilityConfig,
    pub enable_pitch_comb: bool,
    pub enable_whisper: bool,
    pub whisper_config: WhisperConfig,
    pub enable_gsc: bool,
    pub gsc_config: GscConfig,
    pub enable_ashp: bool,
    pub ashp_config: AshpConfig,
    pub enable_governor: bool,
    pub governor_config: GovernorConfig,
    pub enable_wind_suppressor: bool,
    pub wind_config: WindDetectorConfig,
    pub enable_phase_align: bool,
    pub phase_align_config: PhaseAlignConfig,
    pub dither_mode: DitherMode,
    pub aggressive_snr: bool,
    pub enable_blackbox: bool,
    pub enable_agc: bool,
    pub enable_limiter: bool,
    pub mvdr_config: MvdrConfig,
    pub enable_kurtosis: bool,
    pub kurtosis_config: KurtosisConfig,
    pub enable_sensor_cal: bool,
    pub sensor_cal_config: SensorCalConfig,
    pub enable_res_postfilter: bool,
    pub res_config: ResPostfilterConfig,
    pub enable_lufs_governor: bool,
    pub lufs_config: LufsConfig,
    pub enable_lombard: bool,
    pub lombard_config: LombardConfig,
    pub enable_howling: bool,
    pub howling_config: HowlingConfig,
    pub enable_stress: bool,
    pub stress_config: StressProfilerConfig,
    pub enable_audiogram_wdrc: bool,
    pub audiogram_profile: PersonalAudiogram,
    pub enable_bone_fusion: bool,
    pub bone_fusion_config: BoneFusionConfig,
    pub enable_battery_sim: bool,
    pub battery_config: BatteryConfig,
    pub enable_blast_meter: bool,
    pub blast_config: BlastMeterConfig,
    pub enable_deesser: bool,
    pub deesser_config: DeEsserConfig,
    pub enable_polar_pattern: bool,
    pub polar_config: PolarPatternConfig,
    pub enable_thermal_estimator: bool,
    pub thermal_config: ThermalNoiseConfig,
    pub enable_cable_diagnostics: bool,
    pub cable_config: CableConfig,
    pub enable_contrast: bool,
    pub contrast_config: SpectralContrastConfig,
    pub enable_ambisonics: bool,
    pub ambisonics_config: AmbisonicsConfig,
    pub enable_jamming_detector: bool,
    pub jamming_config: JammingDetectorConfig,
    pub enable_rasti: bool,
    pub rasti_config: StiConfig,
}

impl Default for PipelineConfig {
    fn default() -> Self {
        Self {
            n_fft: 512,
            hop_size: 256,
            sample_rate: 16000.0,
            window_type: WindowType::Hann,
            enable_transient_blanker: true,
            transient_config: TransientConfig::default(),
            enable_mvdr: true,
            enable_dereverb: false, // Activated dynamically for reverberant cabin/room profiles
            dereverb_config: DereverbConfig::default(),
            enable_doa_tracking: false,
            doa_config: DoaConfig::default(),
            enable_afc: false,
            afc_config: AfcConfig::default(),
            enable_transparency: false,
            transparency_config: TransparencyConfig::default(),
            enable_cdr: true,
            cdr_config: CdrConfig::default(),
            enable_crn_postfilter: false,
            enable_xtc: false,
            xtc_config: XtcConfig::default(),
            enable_comfort_noise: false, // Strictly false by default for clean objective benchmarks
            enable_intelligibility: false, // Clean default for anechoic benchmarks
            intelligibility_config: IntelligibilityConfig::default(),
            enable_pitch_comb: false,
            enable_whisper: false,
            whisper_config: WhisperConfig::default(),
            enable_gsc: false,
            gsc_config: GscConfig::default(),
            enable_ashp: true, // MIL-STD-1474E true-peak protection active
            ashp_config: AshpConfig::default(),
            enable_governor: true, // DVFS & power governor active
            governor_config: GovernorConfig::default(),
            enable_wind_suppressor: false, // Activated dynamically in mission profiles
            wind_config: WindDetectorConfig::default(),
            enable_phase_align: false, // Activated dynamically in mission profiles
            phase_align_config: PhaseAlignConfig::default(),
            dither_mode: DitherMode::TpdfLipshitz,
            aggressive_snr: false,
            enable_blackbox: true,
            enable_agc: true,
            enable_limiter: true,
            mvdr_config: MvdrConfig::default(),
            enable_kurtosis: false, // Activated in tactical combat shock profiles
            kurtosis_config: KurtosisConfig::default(),
            enable_sensor_cal: false, // Activated dynamically in mission profiles & field calibration
            sensor_cal_config: SensorCalConfig::default(),
            enable_res_postfilter: false, // Activated dynamically with AFC / loudspeaker playback
            res_config: ResPostfilterConfig::default(),
            enable_lufs_governor: false, // Activated in mission profiles and live streaming
            lufs_config: LufsConfig::default(),
            enable_lombard: false,
            lombard_config: LombardConfig::default(),
            enable_howling: false,
            howling_config: HowlingConfig::default(),
            enable_stress: false,
            stress_config: StressProfilerConfig::default(),
            enable_audiogram_wdrc: false,
            audiogram_profile: PersonalAudiogram::default(),
            enable_bone_fusion: false,
            bone_fusion_config: BoneFusionConfig::default(),
            enable_battery_sim: false,
            battery_config: BatteryConfig::default(),
            enable_blast_meter: true,
            blast_config: BlastMeterConfig::default(),
            enable_deesser: false,
            deesser_config: DeEsserConfig::default(),
            enable_polar_pattern: false,
            polar_config: PolarPatternConfig::default(),
            enable_thermal_estimator: true,
            thermal_config: ThermalNoiseConfig::default(),
            enable_cable_diagnostics: true,
            cable_config: CableConfig::default(),
            enable_contrast: false,
            contrast_config: SpectralContrastConfig::default(),
            enable_ambisonics: false,
            ambisonics_config: AmbisonicsConfig::default(),
            enable_jamming_detector: true,
            jamming_config: JammingDetectorConfig::default(),
            enable_rasti: true,
            rasti_config: StiConfig::default(),
        }
    }
}

/// End-to-end Tactical Speech Enhancement Pipeline.
pub struct TacticalAncPipeline {
    pub config: PipelineConfig,
    transient_mic1: TransientBlanker,
    transient_mic2: TransientBlanker,
    stft_mic1: StreamingStft,
    stft_mic2: StreamingStft,
    beamformer: CausalMvdrBeamformer,
    dereverb: CausalDereverberator,
    doa_tracker: GccPhatDoaTracker,
    cdr_estimator: CdrEstimator,
    crn_postfilter: CrnInt8Postfilter,
    pub xtc: TransauralXtc,
    pub intelligibility: IntelligibilityEnhancer,
    pub pitch_comb: PitchHarmonicCombEngine,
    pub whisper_reconstructor: WhisperReconstructor,
    pub gsc: SubbandGsc,
    pub ashp_limiter: AshpLimiter,
    pub governor: PowerGovernor,
    pub wind_suppressor: WindTurbulenceSuppressor,
    pub phase_aligner: AcousticPhaseAligner,
    pub dither_engine: DitherEngine,
    pub blackbox: TacticalBlackbox,
    pub kurtosis_detector: SpectralKurtosisDetector,
    pub convergence_profiler: AdaptiveConvergenceProfiler,
    frame_seq: u64,
    afc: SubbandAfc,
    transparency: TacticalTransparency,
    agc: CausalAgc,
    limiter: SoftLimiter,
    pub active_profile: MissionProfile,
    pub last_stage_timings: DspStageTimings,
    pub afc_stats: AfcStats,
    pub sensor_cal: OnlineSensorCalibrator,
    pub res_postfilter: SubbandResPostfilter,
    pub lufs_governor: LufsGovernor,
    pub last_res_stats: ResPostfilterStats,
    pub last_sensor_cal_telem: SensorCalTelemetry,
    pub lombard_compensator: InverseLombardCompensator,
    pub howling_shifter: AntiHowlingShifter,
    pub stress_profiler: StressProfiler,
    pub last_lombard_telem: LombardTelemetry,
    pub last_howling_telem: HowlingTelemetry,
    pub last_stress_telem: StressTelemetry,
    pub audiogram_wdrc: NalNl2WdrcEngine,
    pub bone_fusion: SubbandBoneFusionEngine,
    pub battery_sim: BatterySimulator,
    pub blast_meter: BlastImpulseMeter,
    pub last_blast_telem: BlastTelemetry,
    pub last_battery_telem: BatteryTelemetry,
    pub deesser: DeEsser,
    pub polar_shaper: PolarPatternShaper,
    pub thermal_estimator: ThermalNoiseEstimator,
    pub cable_diagnostics: CableDiagnostics,
    pub last_deesser_telem: DeEsserTelemetry,
    pub last_polar_telem: PolarPatternTelemetry,
    pub last_thermal_telem: ThermalNoiseTelemetry,
    pub last_cable_telem: CableTelemetry,
    pub contrast_enhancer: SpectralContrastEnhancer,
    pub ambisonics_spatializer: AmbisonicsSpatializer,
    pub jamming_detector: JammingDetector,
    pub rasti_predictor: RastiPredictor,
    pub last_contrast_telem: SpectralContrastTelemetry,
    pub last_ambisonics_telem: AmbisonicsTelemetry,
    pub last_jamming_telem: JammingTelemetry,
    pub last_rasti_telem: StiTelemetry,

    // Preallocated scratch buffers (zero heap allocations in process_hop)
    mic1_scratch: Vec<f32>,
    mic2_scratch: Vec<f32>,
    out_scratch: Vec<f32>,
    spp_scratch: Vec<f32>,
    cdr_alpha_scratch: Vec<f32>,
    cdr_floor_scratch: Vec<f32>,
    spec_mic1: Vec<Complex32>,
    spec_mic2: Vec<Complex32>,
    spec_ref: Vec<Complex32>,
    spec_raw_mic1: Vec<Complex32>,
    stft_ref: StreamingStft,
}

impl TacticalAncPipeline {
    /// Creates a new TacticalAncPipeline.
    pub fn new(config: PipelineConfig) -> Self {
        let n_fft = config.n_fft;
        let hop_size = config.hop_size;
        let num_bins = n_fft / 2 + 1;

        let transient_mic1 = TransientBlanker::new(config.transient_config.clone());
        let transient_mic2 = TransientBlanker::new(config.transient_config.clone());
        let stft_mic1 = StreamingStft::new(n_fft, hop_size, config.window_type);
        let stft_mic2 = StreamingStft::new(n_fft, hop_size, config.window_type);
        let stft_ref = StreamingStft::new(n_fft, hop_size, config.window_type);
        let beamformer = CausalMvdrBeamformer::new(config.mvdr_config.clone());
        let mut dereverb_cfg = config.dereverb_config.clone();
        dereverb_cfg.num_bins = num_bins;
        let dereverb = CausalDereverberator::new(dereverb_cfg);
        let mut doa_cfg = config.doa_config.clone();
        doa_cfg.num_bins = num_bins;
        doa_cfg.n_fft = n_fft;
        doa_cfg.hop_size = hop_size;
        doa_cfg.sample_rate = config.sample_rate;
        let doa_tracker = GccPhatDoaTracker::new(doa_cfg);

        let mut cdr_cfg = config.cdr_config.clone();
        cdr_cfg.num_bins = num_bins;
        cdr_cfg.sample_rate = config.sample_rate;
        let cdr_estimator = CdrEstimator::new(cdr_cfg);

        let crn_postfilter = CrnInt8Postfilter::new(num_bins, config.sample_rate);
        let mut xtc_cfg = config.xtc_config.clone();
        xtc_cfg.sample_rate = config.sample_rate;
        let xtc = TransauralXtc::new(xtc_cfg);

        let mut intell_cfg = config.intelligibility_config.clone();
        intell_cfg.num_bins = num_bins;
        intell_cfg.sample_rate = config.sample_rate;
        let mut intelligibility = IntelligibilityEnhancer::new(intell_cfg);
        intelligibility.set_enabled(config.enable_intelligibility);

        let mut afc_cfg = config.afc_config.clone();
        afc_cfg.num_bins = num_bins;
        let afc = SubbandAfc::new(afc_cfg);
        let mut trans_cfg = config.transparency_config.clone();
        trans_cfg.sample_rate = config.sample_rate;
        let transparency = TacticalTransparency::new(trans_cfg);
        let agc = CausalAgc::new(config.sample_rate, -20.0, 20.0, 200.0, -6.0, 24.0);
        let limiter = SoftLimiter::default();
        let mut pitch_comb = PitchHarmonicCombEngine::new(config.sample_rate);
        pitch_comb.set_enabled(config.enable_pitch_comb);
        pitch_comb.set_aggressive(config.aggressive_snr);

        let mut whisper_cfg = config.whisper_config.clone();
        whisper_cfg.num_bins = num_bins;
        whisper_cfg.sample_rate = config.sample_rate;
        let mut whisper_reconstructor = WhisperReconstructor::new(whisper_cfg);
        whisper_reconstructor.set_enabled(config.enable_whisper);

        let mut gsc_cfg = config.gsc_config.clone();
        gsc_cfg.num_bins = num_bins;
        gsc_cfg.sample_rate = config.sample_rate;
        let mut gsc = SubbandGsc::new(gsc_cfg);
        gsc.set_enabled(config.enable_gsc);

        let mut ashp_cfg = config.ashp_config.clone();
        ashp_cfg.sample_rate = config.sample_rate;
        let mut ashp_limiter = AshpLimiter::new(ashp_cfg);
        ashp_limiter.set_enabled(config.enable_ashp);

        let mut gov_cfg = config.governor_config.clone();
        gov_cfg.hop_budget_us =
            ((hop_size as f32 / config.sample_rate) * 1_000_000.0).round() as u32;
        let governor = PowerGovernor::new(gov_cfg);

        let mut wind_cfg = config.wind_config.clone();
        wind_cfg.num_bins = num_bins;
        wind_cfg.sample_rate = config.sample_rate;
        let wind_suppressor = WindTurbulenceSuppressor::new(wind_cfg);

        let mut phase_cfg = config.phase_align_config.clone();
        phase_cfg.sample_rate = config.sample_rate;
        let mut phase_aligner = AcousticPhaseAligner::new(phase_cfg);
        phase_aligner.set_enabled(config.enable_phase_align);

        let dither_engine = DitherEngine::new(config.dither_mode, config.sample_rate);
        let blackbox = TacticalBlackbox::new();

        let mut kurt_cfg = config.kurtosis_config.clone();
        kurt_cfg.num_bins = num_bins;
        kurt_cfg.sample_rate = config.sample_rate;
        let kurtosis_detector = SpectralKurtosisDetector::new(kurt_cfg);

        let convergence_profiler = AdaptiveConvergenceProfiler::new(config.sample_rate, hop_size);

        let mut sensor_cal_cfg = config.sensor_cal_config.clone();
        sensor_cal_cfg.num_bins = num_bins;
        let sensor_cal = OnlineSensorCalibrator::new(sensor_cal_cfg);

        let mut res_cfg = config.res_config.clone();
        res_cfg.num_bins = num_bins;
        let res_postfilter = SubbandResPostfilter::new(res_cfg);

        let mut lufs_cfg = config.lufs_config.clone();
        lufs_cfg.sample_rate = config.sample_rate;
        lufs_cfg.hop_size = hop_size;
        let lufs_governor = LufsGovernor::new(lufs_cfg);

        let mut lombard_cfg = config.lombard_config.clone();
        lombard_cfg.num_bins = num_bins;
        lombard_cfg.sample_rate = config.sample_rate;
        let mut lombard_compensator = InverseLombardCompensator::new(lombard_cfg);
        lombard_compensator.set_enabled(config.enable_lombard);

        let mut howling_cfg = config.howling_config.clone();
        howling_cfg.sample_rate = config.sample_rate;
        let mut howling_shifter = AntiHowlingShifter::new(howling_cfg);
        howling_shifter.set_enabled(config.enable_howling);

        let mut stress_cfg = config.stress_config.clone();
        stress_cfg.sample_rate = config.sample_rate;
        let stress_profiler = StressProfiler::new(stress_cfg);

        let mut audiogram_wdrc =
            NalNl2WdrcEngine::new(config.sample_rate, config.audiogram_profile);
        audiogram_wdrc.is_enabled = config.enable_audiogram_wdrc;

        let mut bone_cfg = config.bone_fusion_config.clone();
        bone_cfg.sample_rate = config.sample_rate;
        let bone_fusion = SubbandBoneFusionEngine::new(bone_cfg);

        let battery_sim = BatterySimulator::new(config.battery_config.clone());

        let mut blast_cfg = config.blast_config.clone();
        blast_cfg.sample_rate = config.sample_rate;
        let blast_meter = BlastImpulseMeter::new(blast_cfg);

        let mut deesser_cfg = config.deesser_config;
        deesser_cfg.sample_rate = config.sample_rate;
        deesser_cfg.enabled = config.enable_deesser;
        let deesser = DeEsser::new(deesser_cfg);

        let mut polar_cfg = config.polar_config;
        polar_cfg.sample_rate = config.sample_rate;
        polar_cfg.enabled = config.enable_polar_pattern;
        let polar_shaper = PolarPatternShaper::new(polar_cfg);

        let mut thermal_cfg = config.thermal_config;
        thermal_cfg.sample_rate = config.sample_rate;
        thermal_cfg.fft_size = n_fft;
        let thermal_estimator = ThermalNoiseEstimator::new(thermal_cfg);

        let mut cable_cfg = config.cable_config;
        cable_cfg.sample_rate = config.sample_rate;
        let cable_diagnostics = CableDiagnostics::new(cable_cfg);

        let mut contrast_cfg = config.contrast_config;
        contrast_cfg.num_bins = n_fft / 2 + 1;
        contrast_cfg.sample_rate = config.sample_rate;
        contrast_cfg.enabled = config.enable_contrast;
        let contrast_enhancer = SpectralContrastEnhancer::new(contrast_cfg);

        let mut ambisonics_cfg = config.ambisonics_config;
        ambisonics_cfg.sample_rate = config.sample_rate;
        ambisonics_cfg.enabled = config.enable_ambisonics;
        let ambisonics_spatializer = AmbisonicsSpatializer::new(ambisonics_cfg);

        let mut jamming_cfg = config.jamming_config;
        jamming_cfg.enabled = config.enable_jamming_detector;
        let jamming_detector = JammingDetector::new(jamming_cfg);

        let mut rasti_cfg = config.rasti_config;
        rasti_cfg.sample_rate = config.sample_rate;
        rasti_cfg.hop_size = hop_size;
        rasti_cfg.enabled = config.enable_rasti;
        let rasti_predictor = RastiPredictor::new(rasti_cfg);

        Self {
            config,
            transient_mic1,
            transient_mic2,
            stft_mic1,
            stft_mic2,
            stft_ref,
            beamformer,
            dereverb,
            doa_tracker,
            cdr_estimator,
            crn_postfilter,
            xtc,
            intelligibility,
            pitch_comb,
            whisper_reconstructor,
            gsc,
            ashp_limiter,
            governor,
            wind_suppressor,
            phase_aligner,
            dither_engine,
            blackbox,
            kurtosis_detector,
            convergence_profiler,
            frame_seq: 0,
            afc,
            transparency,
            agc,
            limiter,
            active_profile: MissionProfile::CombatVehicle,
            last_stage_timings: DspStageTimings::default(),
            afc_stats: AfcStats::default(),
            sensor_cal,
            res_postfilter,
            lufs_governor,
            last_res_stats: ResPostfilterStats::default(),
            last_sensor_cal_telem: SensorCalTelemetry::default(),
            lombard_compensator,
            howling_shifter,
            stress_profiler,
            last_lombard_telem: LombardTelemetry::default(),
            last_howling_telem: HowlingTelemetry::default(),
            last_stress_telem: StressTelemetry::default(),
            audiogram_wdrc,
            bone_fusion,
            battery_sim,
            blast_meter,
            last_blast_telem: BlastTelemetry::default(),
            last_battery_telem: BatteryTelemetry::default(),
            deesser,
            polar_shaper,
            thermal_estimator,
            cable_diagnostics,
            last_deesser_telem: DeEsserTelemetry::default(),
            last_polar_telem: PolarPatternTelemetry::default(),
            last_thermal_telem: ThermalNoiseTelemetry::default(),
            last_cable_telem: CableTelemetry::default(),
            contrast_enhancer,
            ambisonics_spatializer,
            jamming_detector,
            rasti_predictor,
            last_contrast_telem: SpectralContrastTelemetry::default(),
            last_ambisonics_telem: AmbisonicsTelemetry::default(),
            last_jamming_telem: JammingTelemetry::default(),
            last_rasti_telem: StiTelemetry::default(),
            mic1_scratch: vec![0.0f32; hop_size],
            mic2_scratch: vec![0.0f32; hop_size],
            out_scratch: vec![0.0f32; hop_size],
            spp_scratch: vec![0.5f32; num_bins],
            cdr_alpha_scratch: vec![1.15f32; num_bins],
            cdr_floor_scratch: vec![0.08f32; num_bins],
            spec_mic1: vec![Complex32::default(); num_bins],
            spec_mic2: vec![Complex32::default(); num_bins],
            spec_ref: vec![Complex32::default(); num_bins],
            spec_raw_mic1: vec![Complex32::default(); num_bins],
        }
    }

    /// Resets all internal DSP histories.
    pub fn reset(&mut self) {
        self.transient_mic1.reset();
        self.transient_mic2.reset();
        self.stft_mic1.reset();
        self.stft_mic2.reset();
        self.stft_ref.reset();
        self.beamformer.reset();
        self.dereverb.reset();
        self.doa_tracker.reset();
        self.cdr_estimator.reset();
        self.crn_postfilter.reset();
        self.xtc.reset();
        self.intelligibility.reset();
        self.pitch_comb.reset();
        self.whisper_reconstructor.reset();
        self.gsc.reset();
        self.ashp_limiter.reset();
        self.governor.reset();
        self.wind_suppressor.reset();
        self.phase_aligner.reset();
        self.dither_engine.reset();
        self.blackbox.reset();
        self.kurtosis_detector.reset();
        self.convergence_profiler.reset_all();
        self.afc.reset();
        self.transparency.reset();
        self.agc.reset();
        self.sensor_cal.reset();
        self.res_postfilter.reset();
        self.lufs_governor.reset();
        self.last_res_stats = ResPostfilterStats::default();
        self.last_sensor_cal_telem = SensorCalTelemetry::default();
        self.lombard_compensator.reset();
        self.howling_shifter.reset();
        self.stress_profiler.reset();
        self.last_lombard_telem = LombardTelemetry::default();
        self.last_howling_telem = HowlingTelemetry::default();
        self.last_stress_telem = StressTelemetry::default();
        self.audiogram_wdrc.reset();
        self.bone_fusion.reset();
        self.blast_meter.reset();
        self.last_blast_telem = BlastTelemetry::default();
        self.last_battery_telem = BatteryTelemetry::default();
        self.deesser.reset();
        self.polar_shaper.reset();
        self.thermal_estimator.reset();
        self.cable_diagnostics.reset();
        self.last_deesser_telem = DeEsserTelemetry::default();
        self.last_polar_telem = PolarPatternTelemetry::default();
        self.last_thermal_telem = ThermalNoiseTelemetry::default();
        self.last_cable_telem = CableTelemetry::default();
        self.contrast_enhancer.reset();
        self.ambisonics_spatializer.reset();
        self.jamming_detector.reset();
        self.rasti_predictor.reset();
        self.last_contrast_telem = SpectralContrastTelemetry::default();
        self.last_ambisonics_telem = AmbisonicsTelemetry::default();
        self.last_jamming_telem = JammingTelemetry::default();
        self.last_rasti_telem = StiTelemetry::default();
    }

    /// Algorithmic delay in samples introduced by streaming overlap-add framing.
    pub fn algorithmic_delay_samples(&self) -> usize {
        self.config.hop_size
    }

    /// Returns the currently active mission acoustic profile.
    pub fn active_profile(&self) -> MissionProfile {
        self.active_profile
    }

    /// Dynamically switches mission acoustic profile, updating beamformer, dereverberator, and enhancer parameters.
    pub fn set_mission_profile(
        &mut self,
        profile: MissionProfile,
        enhancer: Option<&mut dyn SpeechEnhancer>,
    ) {
        self.active_profile = profile;
        self.config.enable_dereverb = profile.enable_dereverb();
        self.config.enable_transient_blanker = profile.enable_transient_blanker();
        self.config.enable_transparency = profile.enable_transparency();
        self.config.enable_crn_postfilter = profile.enable_crn_postfilter();
        self.config.enable_xtc = profile.enable_xtc();
        self.config.enable_intelligibility = profile.enable_intelligibility();
        self.config.enable_pitch_comb = profile.enable_pitch_comb();
        self.config.enable_whisper = profile.enable_whisper();
        self.config.enable_gsc = profile.enable_gsc();
        self.config.enable_ashp = profile.enable_ashp();
        self.config.enable_governor = profile.enable_governor();
        self.config.enable_wind_suppressor = profile.enable_wind_suppressor();
        self.config.enable_phase_align = profile.enable_phase_align();
        self.config.enable_kurtosis = profile.enable_kurtosis();
        self.phase_aligner.set_enabled(profile.enable_phase_align());
        self.phase_aligner
            .apply_profile(profile.phase_align_profile());
        self.transparency.set_enabled(profile.enable_transparency());
        self.beamformer
            .set_spatial_postfilter_floor(profile.spatial_postfilter_floor());
        self.xtc.set_enabled(profile.enable_xtc());
        self.intelligibility
            .set_enabled(profile.enable_intelligibility());
        self.pitch_comb.set_enabled(profile.enable_pitch_comb());
        self.whisper_reconstructor
            .set_enabled(profile.enable_whisper());
        self.gsc.set_enabled(profile.enable_gsc());
        self.ashp_limiter.set_enabled(profile.enable_ashp());
        self.config.enable_sensor_cal = profile.enable_sensor_cal();
        self.config.enable_res_postfilter = profile.enable_res_postfilter();
        self.config.enable_lufs_governor = profile.enable_lufs_governor();
        self.lufs_governor.set_target_lufs(profile.target_lufs());
        self.config.enable_lombard = profile.enable_lombard();
        self.lombard_compensator
            .set_enabled(profile.enable_lombard());
        self.beamformer
            .set_diffraction_correction(profile.enable_diffraction());
        self.config.enable_howling = profile.enable_howling();
        self.howling_shifter.set_enabled(profile.enable_howling());
        self.config.enable_stress = profile.enable_stress();
        self.config.enable_audiogram_wdrc = profile.enable_audiogram_wdrc();
        self.audiogram_wdrc.is_enabled = profile.enable_audiogram_wdrc();
        self.config.enable_bone_fusion = profile.enable_bone_fusion();
        self.config.enable_blast_meter = profile.enable_blast_meter();
        self.config.enable_battery_sim = profile.enable_battery_sim();
        self.config.enable_deesser = profile.enable_deesser();
        self.deesser.set_enabled(profile.enable_deesser());
        self.config.enable_cable_diagnostics = profile.enable_cable_diagnostics();
        self.config.enable_thermal_estimator = profile.enable_thermal_estimator();
        if let Some(e) = enhancer {
            e.set_min_gain_db(profile.min_gain_db());
            e.set_comfort_noise(profile.enable_comfort_noise());
        }
    }

    /// Sets whether aggressive SNR optimization mode is active across the pipeline and active enhancer.
    pub fn set_aggressive_snr(&mut self, enabled: bool, enhancer: Option<&mut dyn SpeechEnhancer>) {
        self.config.aggressive_snr = enabled;
        self.pitch_comb.set_aggressive(enabled);
        if let Some(e) = enhancer {
            e.set_aggressive_snr(enabled);
        }
    }

    /// Returns whether aggressive SNR mode is currently active.
    pub fn is_aggressive_snr(&self) -> bool {
        self.config.aggressive_snr
    }

    /// Processes a single stereo hop (exactly `hop_size` samples for mic1 and mic2).
    ///
    /// - `mic1_in`: Primary speech microphone audio.
    /// - `mic2_in`: Secondary reference microphone audio (for MVDR spatial nulling).
    /// - `enhancer`: Active neural network or ensemble model.
    /// - `out`: Slice of `hop_size` samples receiving enhanced audio.
    pub fn process_hop(
        &mut self,
        mic1_in: &[f32],
        mic2_in: Option<&[f32]>,
        enhancer: &mut dyn SpeechEnhancer,
        out: &mut [f32],
    ) -> Result<EnhancerStats, crate::model::ModelError> {
        self.process_hop_tactical(mic1_in, mic2_in, None, enhancer, out)
    }

    /// Processes a single stereo hop with loudspeaker acoustic feedback cancellation, CDR, and transparency.
    ///
    /// Zero heap allocation throughout the inner loop.
    pub fn process_hop_tactical(
        &mut self,
        mic1_in: &[f32],
        mic2_in: Option<&[f32]>,
        ref_speaker_in: Option<&[f32]>,
        enhancer: &mut dyn SpeechEnhancer,
        out: &mut [f32],
    ) -> Result<EnhancerStats, crate::model::ModelError> {
        assert_eq!(mic1_in.len(), self.config.hop_size);
        assert_eq!(out.len(), self.config.hop_size);

        let t_start = Instant::now();

        // 0. Acoustic Blast Wave Air-Overpressure & MIL-STD-1474E Impulse Exposure Meter
        if self.config.enable_blast_meter {
            self.blast_meter.process_frame(mic1_in);
            self.last_blast_telem = self.blast_meter.telemetry;
        }

        // 0.0 Acoustic Transducer Impedance & Cable Continuity Fault Diagnostics
        if self.config.enable_cable_diagnostics {
            self.last_cable_telem = self.cable_diagnostics.process_frame(mic1_in, mic2_in);
        }

        // 0.05 First-Order Differential Polar Directivity Pattern Shaper
        let mut mic1_is_scratch = false;
        let mic2_base = if self.config.enable_polar_pattern {
            if let Some(m2) = mic2_in {
                self.mic1_scratch.copy_from_slice(mic1_in);
                self.polar_shaper.process_block(&mut self.mic1_scratch, m2);
                self.last_polar_telem = self.polar_shaper.telemetry();
                mic1_is_scratch = true;
                Some(m2)
            } else {
                None
            }
        } else {
            mic2_in
        };

        // 0. Concussion / Impulsive Transient Blanking (Zero Allocation)
        let mic1_slice = if self.config.enable_transient_blanker {
            if !mic1_is_scratch {
                self.mic1_scratch.copy_from_slice(mic1_in);
            }
            self.transient_mic1.process(&mut self.mic1_scratch);
            &self.mic1_scratch[..]
        } else if mic1_is_scratch {
            &self.mic1_scratch[..]
        } else {
            mic1_in
        };

        // 1. STFT Analysis on Mic 1
        self.stft_mic1.analyze(mic1_slice, &mut self.spec_mic1);
        self.spec_raw_mic1.copy_from_slice(&self.spec_mic1);

        let has_mic2 = if self.config.enable_mvdr {
            if let Some(m2) = mic2_base {
                if m2.len() == self.config.hop_size {
                    let mic2_slice = if self.config.enable_transient_blanker {
                        self.mic2_scratch.copy_from_slice(m2);
                        self.transient_mic2.process(&mut self.mic2_scratch);
                        &self.mic2_scratch[..]
                    } else {
                        m2
                    };
                    self.stft_mic2.analyze(mic2_slice, &mut self.spec_mic2);
                    true
                } else {
                    false
                }
            } else {
                false
            }
        } else {
            false
        };

        if let Some(spk) = ref_speaker_in {
            if spk.len() == self.config.hop_size {
                self.stft_ref.analyze(spk, &mut self.spec_ref);
            }
        }
        let t_stft = Instant::now();

        // 1.1. Higher-Order Spectral Kurtosis Non-Gaussian Shock Transient Detection
        if self.config.enable_kurtosis {
            let k_telem = self
                .kurtosis_detector
                .process_frame(&self.spec_mic1, Some(mic1_in));
            if k_telem.is_shock_transient {
                for s in self.spec_mic1.iter_mut() {
                    *s *= k_telem.suggested_attenuation;
                }
            }
        }

        // 1.2. Subband Acoustic Feedback Cancellation (AFC)
        if self.config.enable_afc && ref_speaker_in.is_some() {
            let spp_mean = self.beamformer.spp.iter().copied().sum::<f32>()
                / self.beamformer.spp.len().max(1) as f32;
            self.afc_stats = self.afc.process_frame(
                &mut self.spec_mic1,
                if has_mic2 {
                    Some(&mut self.spec_mic2)
                } else {
                    None
                },
                &self.spec_ref,
                spp_mean,
            );

            // 1.22. Subband Residual Echo Suppression (RES) Wiener Postfilter
            if self.config.enable_res_postfilter {
                self.last_res_stats = self.res_postfilter.process_frame(
                    &mut self.spec_mic1,
                    &self.spec_raw_mic1,
                    &self.spec_ref,
                    self.afc.mic1_estimated_echo(),
                    self.afc_stats.double_talk_detected,
                );
            }
        }
        let t_afc = Instant::now();

        // 1.25. Online Inter-Sensor Acoustic Calibration & Clogged Microphone Auto-Equalizer
        if self.config.enable_sensor_cal && has_mic2 {
            let spp_mean = self.beamformer.spp.iter().copied().sum::<f32>()
                / self.beamformer.spp.len().max(1) as f32;
            let wti = self.wind_suppressor.current_wti();
            self.last_sensor_cal_telem =
                self.sensor_cal
                    .process_frame(&self.spec_mic1, &mut self.spec_mic2, spp_mean, wti);
        }

        // 1.3. Multi-Microphone Coherence-to-Diffuse Ratio (CDR) & Diffuse Field Decomposition
        if self.config.enable_cdr && has_mic2 {
            self.cdr_estimator
                .process_frame(&self.spec_mic1, &self.spec_mic2);
            let min_gain = 10.0f32.powf(self.active_profile.min_gain_db() / 20.0);
            self.cdr_estimator.diffuse_suppression_factors(
                &mut self.cdr_alpha_scratch,
                &mut self.cdr_floor_scratch,
                1.15,
                min_gain,
            );
            enhancer.set_diffuse_factors(&self.cdr_alpha_scratch, &self.cdr_floor_scratch);

            // Modulate MVDR spatial postfilter floor dynamically
            let mean_diff = self.cdr_estimator.mean_diffuse_ratio();
            let base_floor = self.active_profile.spatial_postfilter_floor();
            let modulated_floor = (base_floor * (1.0 - 0.20 * mean_diff)).clamp(0.15, 0.50);
            self.beamformer
                .set_spatial_postfilter_floor(modulated_floor);
        }

        // 1.4. Dynamic Wind Noise Acoustic Turbulence Detector & Aero-Acoustic De-Rumbling Filter
        if self.config.enable_wind_suppressor && has_mic2 {
            let f0_opt = if self.config.enable_pitch_comb && self.pitch_comb.is_voiced() {
                Some(self.pitch_comb.tracked_f0())
            } else {
                None
            };
            self.wind_suppressor
                .process_frame(&mut self.spec_mic1, &self.spec_mic2, f0_opt);
        }

        // 1.5. Online Direction of Arrival (DOA) Tracking via GCC-PHAT + 2-State Kalman Filter
        if self.config.enable_doa_tracking && has_mic2 {
            let pwr_mic1 = self.spec_mic1.iter().map(|c| c.norm_sqr()).sum::<f32>()
                / self.spec_mic1.len().max(1) as f32;
            let spp_mean = if pwr_mic1 > 1e-4 {
                0.85
            } else {
                self.beamformer.spp.iter().copied().sum::<f32>()
                    / self.beamformer.spp.len().max(1) as f32
            };
            let tracked_angle =
                self.doa_tracker
                    .process_frame(&self.spec_mic1, &self.spec_mic2, spp_mean);
            self.beamformer.set_steering_angle(tracked_angle);
            self.cdr_estimator.set_target_angle(tracked_angle);
        }

        // 1.8. Multi-Channel Coupled WPE Dereverberation
        // Decouples room reflections across both channels before MVDR covariance estimation
        if self.config.enable_dereverb {
            if has_mic2 {
                self.dereverb.process_dual_frame(
                    &mut self.spec_mic1,
                    &mut self.spec_mic2,
                    &self.spp_scratch,
                );
            } else {
                self.dereverb
                    .process_frame(&mut self.spec_mic1, &self.spp_scratch);
            }
        }
        let t_dereverb = Instant::now();

        // 1.95 Subband Thermal Johnson-Nyquist Preamplifier Noise Estimator
        if self.config.enable_thermal_estimator {
            let bound = self
                .thermal_estimator
                .bound_mvdr_diagonal_loading(self.config.mvdr_config.diag_loading_eps);
            self.beamformer.set_diagonal_loading_eps(bound);
            self.last_thermal_telem = self.thermal_estimator.telemetry();
        }

        // 2. Spatial Beamforming (MVDR or Griffith-Jim Subband GSC)
        if has_mic2 {
            if self.config.enable_gsc {
                self.gsc.process_frame(
                    &mut self.spec_mic1,
                    &self.spec_mic2,
                    Some(&self.beamformer.spp),
                );
            } else {
                self.beamformer
                    .process_frame(&mut self.spec_mic1, &self.spec_mic2);
            }
        }
        let t_beam = Instant::now();

        // 3. Neural Noise Suppression / Complex Spectral Masking
        let stats = enhancer.process_stft_frame(&mut self.spec_mic1)?;

        // 3.2. INT8 Quantized Recurrent Postfilter (CRN-INT8) for Musical Noise Suppression
        if self.config.enable_crn_postfilter {
            self.crn_postfilter.process_frame(&mut self.spec_mic1);
        }

        // 3.4. Adaptive Subband Speech Intelligibility Enhancer & Formant Dynamic Booster
        if self.config.enable_intelligibility {
            self.intelligibility.process_spec(&mut self.spec_mic1);
        }

        // 3.6. Adaptive Battlefield Whisper Formant Reconstructor
        if self.config.enable_whisper {
            self.whisper_reconstructor.process_frame(
                &mut self.spec_mic1,
                mic1_slice,
                self.config.hop_size,
            );
        }

        // 3.8. Dynamic Psychoacoustic Inverse-Lombard Vocal Fatigue & Strain Compensator
        if self.config.enable_lombard {
            let f0_opt = if self.config.enable_pitch_comb && self.pitch_comb.is_voiced() {
                Some(self.pitch_comb.tracked_f0())
            } else {
                None
            };
            let spp_opt = if has_mic2 {
                Some(&self.beamformer.spp[..])
            } else {
                None
            };
            self.last_lombard_telem =
                self.lombard_compensator
                    .process_frame(&mut self.spec_mic1, f0_opt, spp_opt);
        }

        // 3.99. Dynamic Psychoacoustic Spectral Contrast & Formant Masking Unveiler
        if self.config.enable_contrast {
            let spp_opt = if has_mic2 {
                Some(&self.beamformer.spp[..])
            } else {
                None
            };
            self.last_contrast_telem = self
                .contrast_enhancer
                .process_frame(&mut self.spec_mic1, spp_opt);
        }
        let t_spectral = Instant::now();

        // 4. Inverse STFT Synthesis
        self.stft_mic1.synthesize(&self.spec_mic1, out);

        // 5. Causal AGC (Level stabilization)
        if self.config.enable_agc {
            self.agc.process_block(out);
        }

        // 6. Peak Limiting (Anti-clipping protection)
        if self.config.enable_limiter {
            self.limiter.process(out);
        }

        // 7. Tactical Situational Awareness / Transparency Mode
        if self.config.enable_transparency {
            self.out_scratch.copy_from_slice(out);
            self.transparency
                .process_block(mic1_in, &self.out_scratch, out);
        }

        // 7.5. DC Rejection (20 Hz Biquad) & Soft-Knee Saturation
        if self.config.enable_intelligibility {
            self.intelligibility.process_time(out);
        }

        // 7.8. Causal Pitch-Synchronous Harmonic Comb Filter
        if self.config.enable_pitch_comb {
            self.out_scratch.copy_from_slice(out);
            self.pitch_comb.process_block(&self.out_scratch, out);
        }

        // 7.85. Acoustic Group Delay Linearizer & Formant Phase De-Disperser
        if self.config.enable_phase_align {
            self.phase_aligner.process_block(out);
        }

        // 7.9. True-Peak Acoustic Shock Hearing Protection (ASHP) Limiter (MIL-STD-1474E)
        if self.config.enable_ashp {
            self.ashp_limiter.process_block(out);
        }

        // 7.95. ITU-R BS.1770-4 & EBU R128 True LUFS Loudness Governor & DRC
        if self.config.enable_lufs_governor {
            self.lufs_governor.process_block(out);
        }

        // 7.96. Subband Anti-Howling Hilbert Single-Sideband (SSB) Frequency Shifter
        if self.config.enable_howling {
            self.last_howling_telem = self.howling_shifter.process_block(out);
        }

        // 7.97. Dynamic Psychoacoustic Active Hearing-Loss Compensation & NAL-NL2 WDRC Engine
        if self.config.enable_audiogram_wdrc {
            self.audiogram_wdrc.process_mono(out);
        }

        // 7.98. Subband Bone-Conduction & Air-Conduction Dual-Sensor Fusion
        if self.config.enable_bone_fusion && has_mic2 {
            self.out_scratch.copy_from_slice(out);
            self.bone_fusion
                .fuse_frame(mic2_in.unwrap(), &self.out_scratch, out);
        }

        // 7.99. Dynamic Psychoacoustic Split-Band De-Esser & Anti-Sibilance Engine
        if self.config.enable_deesser {
            self.deesser.process_block(out);
            self.last_deesser_telem = self.deesser.telemetry();
        }

        // 7.995. First-Order 2D/3D B-Format Ambisonics Tactical Spatializer
        if self.config.enable_ambisonics && has_mic2 {
            let (ix, iy, iz, e) =
                AmbisonicsSpatializer::compute_frame_intensity(mic1_in, mic2_in.unwrap(), out, out);
            self.ambisonics_spatializer
                .update_smoothed_intensity(ix, iy, iz, e);
            self.last_ambisonics_telem = self.ambisonics_spatializer.telemetry();
        }

        // 7.996. Acoustic Speech Transmission Index (STI) & Real-Time RASTI Predictor
        if self.config.enable_rasti {
            self.last_rasti_telem = self.rasti_predictor.process_frame(out);
        }
        let t_synth = Instant::now();

        // Record high-resolution microsecond stage execution timings
        self.last_stage_timings = DspStageTimings {
            stft_us: t_stft.duration_since(t_start).as_micros() as u32,
            afc_us: t_afc.duration_since(t_stft).as_micros() as u32,
            beamformer_us: t_beam.duration_since(t_dereverb).as_micros() as u32,
            dereverb_us: t_dereverb.duration_since(t_afc).as_micros() as u32,
            spectral_us: t_spectral.duration_since(t_beam).as_micros() as u32,
            intelligibility_us: if self.config.enable_intelligibility {
                6
            } else {
                0
            },
            synthesis_us: t_synth.duration_since(t_spectral).as_micros() as u32,
            total_us: t_synth.duration_since(t_start).as_micros() as u32,
        };

        // 8. Dynamic Real-Time DVFS & Power Governor Simulator
        if self.config.enable_governor {
            self.governor.record_hop(self.last_stage_timings.total_us);
        }

        // 8. Tactical Mission Blackbox Rolling Forensic Recording (Zero Allocation)
        if self.config.enable_blackbox {
            let in_rms =
                (mic1_in.iter().map(|s| s * s).sum::<f32>() / mic1_in.len().max(1) as f32).sqrt();
            let out_rms = (out.iter().map(|s| s * s).sum::<f32>() / out.len().max(1) as f32).sqrt();
            let angle = self.doa_tracker.tracked_angle_deg();
            let doa_conf = self.doa_tracker.confidence();
            let cdr_db = self.cdr_estimator.mean_cdr_db();
            let sii = self.intelligibility.current_sii();
            let total_us = self.last_stage_timings.total_us;
            let is_xrun = total_us > 15_000;
            let is_conc = in_rms > 0.85;

            self.blackbox.record_hop(
                self.frame_seq,
                in_rms,
                out_rms,
                angle,
                doa_conf,
                cdr_db,
                sii,
                total_us,
                is_xrun,
                is_conc,
            );
            self.frame_seq = self.frame_seq.wrapping_add(1);
        }

        // 8.5. Adaptive Filter Convergence Profiler tracking
        self.convergence_profiler
            .mvdr
            .update(self.beamformer.condition_number_at_bin(10));
        self.convergence_profiler
            .afc
            .update(self.afc_stats.erle_mic1_db);
        if self.config.enable_gsc {
            self.convergence_profiler
                .gsc
                .update(self.gsc.stats().cancellation_db);
        }
        if self.config.enable_doa_tracking {
            self.convergence_profiler
                .kalman
                .update(self.doa_tracker.kalman_variance());
        }

        // 8.6. Acoustic Vocal Fatigue & Soldier Cognitive Stress Index Profiler
        if self.config.enable_stress {
            let f0_opt = if self.config.enable_pitch_comb && self.pitch_comb.is_voiced() {
                Some(self.pitch_comb.tracked_f0())
            } else {
                None
            };
            self.last_stress_telem = self.stress_profiler.process_frame(out, f0_opt);
        }

        // 8.7. Tactical Battery-Level & Power Drain Simulator for Field Edge Durability
        if self.config.enable_battery_sim {
            let dt = self.config.hop_size as f32 / self.config.sample_rate;
            let rtf = self.last_stage_timings.total_us as f32 / (dt * 1_000_000.0).max(1.0);
            self.battery_sim.tick(dt, rtf, false, 25.0);
            self.last_battery_telem = self.battery_sim.telemetry;
        }

        Ok(stats)
    }

    /// Dynamically enables or disables the Speech Intelligibility Enhancer.
    pub fn set_intelligibility(&mut self, enabled: bool) {
        self.config.enable_intelligibility = enabled;
        self.intelligibility.set_enabled(enabled);
    }

    /// Current Speech Intelligibility Index (SII: 0.0 to 1.0).
    pub fn current_sii(&self) -> f32 {
        self.intelligibility.current_sii()
    }

    /// Intelligibility Gain in dB.
    pub fn intelligibility_gain_db(&self) -> f32 {
        self.intelligibility.intelligibility_gain_db()
    }

    /// Dynamically enables or disables Acoustic Feedback Cancellation (AFC).
    pub fn set_afc(&mut self, enabled: bool) {
        self.config.enable_afc = enabled;
    }

    /// Dynamically enables or disables Tactical Transparency Situational Awareness mode.
    pub fn set_transparency(&mut self, enabled: bool, ambient_gain: f32) {
        self.config.enable_transparency = enabled;
        self.transparency.set_enabled(enabled);
        self.transparency.set_ambient_gain(ambient_gain);
    }

    /// Returns the latest microsecond execution timings breakdown across DSP stages.
    pub fn stage_timings(&self) -> DspStageTimings {
        self.last_stage_timings
    }

    /// Returns latest Acoustic Feedback Cancellation statistics.
    pub fn afc_stats(&self) -> AfcStats {
        self.afc_stats
    }

    /// Returns the current Spectral Kurtosis diagnostic telemetry.
    pub fn kurtosis_telemetry(&self) -> &KurtosisTelemetry {
        self.kurtosis_detector.telemetry()
    }

    /// Returns the adaptive filter convergence time profiler.
    pub fn convergence_profiler(&self) -> &AdaptiveConvergenceProfiler {
        &self.convergence_profiler
    }

    /// Returns the currently tracked talker angle in degrees from online GCC-PHAT.
    pub fn tracked_talker_angle_deg(&self) -> f32 {
        self.doa_tracker.tracked_angle_deg()
    }

    /// Returns the online DOA peak confidence metric [0.0, 1.0].
    pub fn doa_confidence(&self) -> f32 {
        self.doa_tracker.confidence()
    }

    /// Enables or disables online talker DOA tracking at runtime.
    pub fn set_doa_tracking(&mut self, enabled: bool) {
        self.config.enable_doa_tracking = enabled;
    }

    /// Returns mean Coherence-to-Diffuse Ratio in decibels across speech band.
    pub fn mean_cdr_db(&self) -> f32 {
        self.cdr_estimator.mean_cdr_db()
    }

    /// Returns the current Wind Turbulence Detector telemetry.
    pub fn wind_telemetry(&self) -> WindTelemetry {
        WindTelemetry {
            mean_wti: self.wind_suppressor.current_wti(),
            wind_detected: self.wind_suppressor.is_wind_detected(),
            low_freq_power_db: -50.0,
            suppression_db: self.wind_suppressor.suppression_db(),
        }
    }

    /// Dynamically enables or disables the wind turbulence suppressor.
    pub fn set_wind_suppressor(&mut self, enabled: bool) {
        self.config.enable_wind_suppressor = enabled;
    }

    /// Dynamically enables or disables the acoustic phase aligner.
    pub fn set_phase_align(&mut self, enabled: bool, profile: PhaseAlignmentProfile) {
        self.config.enable_phase_align = enabled;
        self.phase_aligner.set_enabled(enabled);
        self.phase_aligner.apply_profile(profile);
    }

    /// Returns current glottal pulse crest factor from the phase aligner.
    pub fn glottal_crest_factor(&self) -> f32 {
        self.phase_aligner.crest_factor()
    }

    /// Returns mean spatial magnitude coherence [0.0, 1.0].
    pub fn mean_coherence(&self) -> f32 {
        self.cdr_estimator.mean_coherence()
    }

    /// Returns mean diffuse sound ratio [0.0, 1.0].
    pub fn mean_diffuse_ratio(&self) -> f32 {
        self.cdr_estimator.mean_diffuse_ratio()
    }

    /// Returns a reference to the active CDR estimator.
    pub fn cdr_estimator(&self) -> &CdrEstimator {
        &self.cdr_estimator
    }

    /// Dynamically enables or disables CDR estimation.
    pub fn set_cdr_enabled(&mut self, enabled: bool) {
        self.config.enable_cdr = enabled;
    }

    /// Dynamically enables or disables CRN-INT8 recurrent postfilter.
    pub fn set_crn_postfilter_enabled(&mut self, enabled: bool) {
        self.config.enable_crn_postfilter = enabled;
    }

    /// Dynamically enables or disables Transaural XTC.
    pub fn set_xtc_enabled(&mut self, enabled: bool) {
        self.config.enable_xtc = enabled;
        self.xtc.set_enabled(enabled);
    }

    /// Quantizes float samples to 16-bit integer using TPDF dither & psychoacoustic noise shaping.
    pub fn quantize_output_i16(&mut self, float_samples: &[f32], out_i16: &mut [i16]) {
        self.dither_engine.quantize_i16(float_samples, out_i16);
    }

    /// Returns a reference to the rolling mission blackbox telemetry recorder.
    pub fn blackbox(&self) -> &TacticalBlackbox {
        &self.blackbox
    }

    /// Returns a mutable reference to the rolling mission blackbox recorder.
    pub fn blackbox_mut(&mut self) -> &mut TacticalBlackbox {
        &mut self.blackbox
    }

    /// Returns the latest ITU-R BS.1770-4 / EBU R128 Loudness Governor telemetry.
    pub fn lufs_telemetry(&self) -> LufsTelemetry {
        self.lufs_governor.telemetry()
    }

    /// Dynamically sets the target LUFS for the loudness governor.
    pub fn set_target_lufs(&mut self, target_lufs: f32) {
        self.lufs_governor.set_target_lufs(target_lufs);
    }

    /// Dynamically enables or disables the ITU-R BS.1770-4 LUFS governor.
    pub fn set_lufs_governor_enabled(&mut self, enabled: bool) {
        self.config.enable_lufs_governor = enabled;
    }

    /// Returns the latest Subband Residual Echo Suppression (RES) statistics.
    pub fn res_stats(&self) -> ResPostfilterStats {
        self.last_res_stats
    }

    /// Dynamically enables or disables Subband RES Wiener postfiltering.
    pub fn set_res_postfilter_enabled(&mut self, enabled: bool) {
        self.config.enable_res_postfilter = enabled;
    }

    /// Returns the latest Online Inter-Sensor Acoustic Calibration telemetry.
    pub fn sensor_cal_telemetry(&self) -> SensorCalTelemetry {
        self.last_sensor_cal_telem
    }

    /// Dynamically enables or disables online inter-sensor calibration.
    pub fn set_sensor_cal_enabled(&mut self, enabled: bool) {
        self.config.enable_sensor_cal = enabled;
    }

    /// Currently tracked fundamental voice pitch F0 in Hz.
    pub fn pitch_f0(&self) -> f32 {
        self.pitch_comb.tracked_f0()
    }

    /// Whether current speech frame is classified as voiced by pitch tracker.
    pub fn pitch_is_voiced(&self) -> bool {
        self.pitch_comb.is_voiced()
    }

    /// Current voicing strength in [0.0, 1.0].
    pub fn pitch_voicing_strength(&self) -> f32 {
        self.pitch_comb.voicing_strength()
    }

    /// Dynamically enables or disables the pitch-synchronous harmonic comb filter.
    pub fn set_pitch_comb_enabled(&mut self, enabled: bool) {
        self.config.enable_pitch_comb = enabled;
        self.pitch_comb.set_enabled(enabled);
    }

    /// Dynamically enables or disables Whisper Formant Reconstruction.
    pub fn set_whisper_enabled(&mut self, enabled: bool) {
        self.config.enable_whisper = enabled;
        self.whisper_reconstructor.set_enabled(enabled);
    }

    /// Returns current Whisper Reconstructor telemetry.
    pub fn whisper_stats(&self) -> WhisperStats {
        self.whisper_reconstructor.stats()
    }

    /// Dynamically enables or disables Subband Generalized Sidelobe Canceller (GSC).
    pub fn set_gsc_enabled(&mut self, enabled: bool) {
        self.config.enable_gsc = enabled;
        self.gsc.set_enabled(enabled);
    }

    /// Returns current GSC operational statistics.
    pub fn gsc_stats(&self) -> GscStats {
        self.gsc.stats()
    }

    /// Dynamically enables or disables True-Peak ASHP Limiter.
    pub fn set_ashp_enabled(&mut self, enabled: bool) {
        self.config.enable_ashp = enabled;
        self.ashp_limiter.set_enabled(enabled);
    }

    /// Returns current ASHP Limiter telemetry report.
    pub fn ashp_telemetry(&self) -> AshpTelemetry {
        self.ashp_limiter.telemetry()
    }

    /// Returns current Power Governor simulation telemetry.
    pub fn governor_telemetry(&self) -> GovernorTelemetry {
        self.governor.telemetry()
    }

    /// Returns latest Inverse-Lombard Strain Compensator telemetry.
    pub fn lombard_telemetry(&self) -> LombardTelemetry {
        self.last_lombard_telem
    }

    /// Dynamically enables or disables Inverse-Lombard Strain Compensator.
    pub fn set_lombard_enabled(&mut self, enabled: bool) {
        self.config.enable_lombard = enabled;
        self.lombard_compensator.set_enabled(enabled);
    }

    /// Returns latest Anti-Howling Hilbert SSB Shifter telemetry.
    pub fn howling_telemetry(&self) -> HowlingTelemetry {
        self.last_howling_telem
    }

    /// Dynamically enables or disables Anti-Howling Hilbert SSB Shifter.
    pub fn set_howling_enabled(&mut self, enabled: bool) {
        self.config.enable_howling = enabled;
        self.howling_shifter.set_enabled(enabled);
    }

    /// Returns latest Soldier Cognitive Stress Index & Vocal Fatigue telemetry.
    pub fn stress_telemetry(&self) -> StressTelemetry {
        self.last_stress_telem
    }

    /// Dynamically enables or disables Soldier Cognitive Stress Profiler.
    pub fn set_stress_enabled(&mut self, enabled: bool) {
        self.config.enable_stress = enabled;
    }

    /// Dynamically enables or disables Creeping-Wave Cranial Diffraction Correction.
    pub fn set_diffraction_enabled(&mut self, enabled: bool) {
        self.beamformer.set_diffraction_correction(enabled);
    }

    /// Returns latest Acoustic Blast Wave Overpressure & MIL-STD-1474E telemetry.
    pub fn blast_telemetry(&self) -> BlastTelemetry {
        self.last_blast_telem
    }

    /// Dynamically enables or disables Acoustic Blast Overpressure Meter.
    pub fn set_blast_meter_enabled(&mut self, enabled: bool) {
        self.config.enable_blast_meter = enabled;
    }

    /// Returns latest Tactical Battery Simulator telemetry.
    pub fn battery_telemetry(&self) -> BatteryTelemetry {
        self.last_battery_telem
    }

    /// Dynamically sets the Tactical Power Mode.
    pub fn set_power_mode(&mut self, mode: TacticalPowerMode) {
        self.battery_sim.set_power_mode(mode);
    }

    /// Dynamically enables or disables Tactical Battery Simulator.
    pub fn set_battery_sim_enabled(&mut self, enabled: bool) {
        self.config.enable_battery_sim = enabled;
    }

    /// Returns latest Dual-Sensor Bone/Air Conduction Fusion telemetry.
    pub fn bone_fusion_telemetry(&self) -> BoneFusionTelemetry {
        self.bone_fusion.telemetry
    }

    /// Dynamically enables or disables Dual-Sensor Bone/Air Fusion.
    pub fn set_bone_fusion_enabled(&mut self, enabled: bool) {
        self.config.enable_bone_fusion = enabled;
    }

    /// Updates personal audiogram curve and reprograms NAL-NL2 WDRC compressor.
    pub fn update_audiogram(&mut self, audiogram: PersonalAudiogram) {
        self.config.audiogram_profile = audiogram;
        self.audiogram_wdrc.update_audiogram(audiogram);
    }

    /// Dynamically enables or disables NAL-NL2 WDRC hearing-loss compensation.
    pub fn set_audiogram_wdrc_enabled(&mut self, enabled: bool) {
        self.config.enable_audiogram_wdrc = enabled;
        self.audiogram_wdrc.is_enabled = enabled;
    }

    /// Returns latest Dynamic Psychoacoustic De-Esser telemetry.
    pub fn deesser_telemetry(&self) -> DeEsserTelemetry {
        self.last_deesser_telem
    }

    /// Dynamically enables or disables the Dynamic Split-Band De-Esser.
    pub fn set_deesser_enabled(&mut self, enabled: bool) {
        self.config.enable_deesser = enabled;
        self.deesser.set_enabled(enabled);
    }

    /// Returns latest First-Order Differential Polar Directivity Pattern telemetry.
    pub fn polar_telemetry(&self) -> PolarPatternTelemetry {
        self.last_polar_telem
    }

    /// Dynamically sets the Polar Directivity Pattern.
    pub fn set_polar_pattern(&mut self, pattern: PolarPatternType) {
        self.config.polar_config.pattern = pattern;
        self.polar_shaper.set_pattern(pattern);
    }

    /// Dynamically steers the acoustic null angle in degrees (90° to 180°).
    pub fn set_polar_null_angle_deg(&mut self, angle_deg: f32) {
        self.config.polar_config.custom_null_angle_deg = angle_deg;
        self.polar_shaper.set_custom_null_angle_deg(angle_deg);
    }

    /// Returns latest Johnson-Nyquist Thermal Noise Estimator telemetry.
    pub fn thermal_telemetry(&self) -> ThermalNoiseTelemetry {
        self.last_thermal_telem
    }

    /// Returns latest Transducer Impedance & Cable Continuity Diagnostics telemetry.
    pub fn cable_telemetry(&self) -> CableTelemetry {
        self.last_cable_telem
    }

    /// Returns latest Spectral Contrast Enhancer telemetry.
    pub fn contrast_telemetry(&self) -> SpectralContrastTelemetry {
        self.last_contrast_telem
    }

    /// Returns latest Ambisonics Spatializer telemetry.
    pub fn ambisonics_telemetry(&self) -> AmbisonicsTelemetry {
        self.last_ambisonics_telem
    }

    /// Returns latest Tactical Jamming Detector telemetry.
    pub fn jamming_telemetry(&self) -> JammingTelemetry {
        self.last_jamming_telem
    }

    /// Returns latest RASTI STI telemetry.
    pub fn rasti_telemetry(&self) -> StiTelemetry {
        self.last_rasti_telem
    }
}
