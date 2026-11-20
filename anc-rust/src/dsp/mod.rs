//! Digital Signal Processing (DSP) core modules for SIH 26052.

pub mod afc;
pub mod afc_postfilter;
pub mod agc;
pub mod ambisonics;
pub mod ashp;
pub mod audiogram;
pub mod auxiva;
pub mod beamformer;
pub mod binaural;
pub mod bone_fusion;
pub mod camouflage;
pub mod cdr;
pub mod contrast;
pub mod deesser;
pub mod dereverb;
pub mod diffraction;
pub mod dither;
pub mod doa;
pub mod erb;
pub mod geigel;
pub mod gsc;
pub mod howling;
pub mod intelligibility;
pub mod kurtosis;
pub mod limiter;
pub mod lombard;
pub mod lufs;
pub mod phase_align;
pub mod pitch;
pub mod polar_pattern;
pub mod polyphase;
pub mod resample;
pub mod sensor_cal;
pub mod simd;
pub mod stft;
pub mod thermal_noise;
pub mod transient;
pub mod transparency;
pub mod whisper;
pub mod wind;
pub mod window;
pub mod xtc;

pub use afc::{AfcConfig, AfcStats, SubbandAfc};
pub use afc_postfilter::{ResPostfilterConfig, ResPostfilterStats, SubbandResPostfilter};
pub use agc::CausalAgc;
pub use ambisonics::{
    AmbisonicsConfig, AmbisonicsSpatializer, AmbisonicsTelemetry, AMBISONICS_MAX_BLOCK_SIZE,
};
pub use ashp::{AshpConfig, AshpLimiter, AshpTelemetry};
pub use audiogram::{
    Ear, NalNl2WdrcEngine, PersonalAudiogram, WdrcChannel, AUDIOMETRIC_FREQUENCIES,
    NUM_AUDIOMETRIC_BANDS,
};
pub use auxiva::{AuxIvaConfig, AuxIvaStats, OnlineAuxIva, MAX_IVA_BINS};
pub use beamformer::{CausalMvdrBeamformer, MvdrConfig};
pub use binaural::{BinauralConfig, BinauralSpatialRenderer};
pub use bone_fusion::{
    BoneFusionConfig, BoneFusionTelemetry, SubbandBoneFusionEngine, DEFAULT_FUSION_CROSSOVER_HZ,
};
pub use camouflage::{
    AcousticCamouflageEngine, CamouflageConfig, CamouflageProfile, CamouflageTelemetry,
    MAX_CAMOUFLAGE_BINS,
};
pub use cdr::{CdrConfig, CdrEstimator};
pub use contrast::{
    SpectralContrastConfig, SpectralContrastEnhancer, SpectralContrastTelemetry, MAX_CONTRAST_BINS,
    NUM_CONTRAST_SUBBANDS,
};
pub use deesser::{DeEsser, DeEsserConfig, DeEsserTelemetry, DEESSER_MAX_BLOCK_SIZE};
pub use dereverb::{CausalDereverberator, DereverbConfig};
pub use diffraction::{CreepingWaveDiffraction, DiffractionConfig};
pub use dither::{DitherEngine, DitherMode};
pub use doa::{DoaConfig, GccPhatDoaTracker, MouthTrackingKalman};
pub use erb::ErbFilterbank;
pub use geigel::{GeigelConfig, GeigelDetector, GeigelStats};
pub use gsc::{GscConfig, GscStats, SubbandGsc};
pub use howling::{AntiHowlingShifter, HowlingConfig, HowlingTelemetry};
pub use intelligibility::{IntelligibilityConfig, IntelligibilityEnhancer};
pub use kurtosis::{
    KurtosisConfig, KurtosisTelemetry, SpectralKurtosisDetector, KURTOSIS_HUD_BANDS,
};
pub use limiter::SoftLimiter;
pub use lombard::{InverseLombardCompensator, LombardConfig, LombardTelemetry};
pub use lufs::{LufsConfig, LufsGovernor, LufsTelemetry};
pub use phase_align::{
    AcousticPhaseAligner, AllPassBiquad, PhaseAlignConfig, PhaseAlignmentProfile,
};
pub use pitch::{HarmonicCombFilter, PitchHarmonicCombEngine, PitchTracker, PitchTrackerConfig};
pub use polar_pattern::{
    PolarPatternConfig, PolarPatternShaper, PolarPatternTelemetry, PolarPatternType,
    SPEED_OF_SOUND_M_S,
};
pub use polyphase::{
    MinimumPhasePolyphaseDecimator3x, MinimumPhasePolyphaseInterpolator3x, MIN_PHASE_FIR_48,
};
pub use resample::StatefulResampler;
pub use sensor_cal::{OnlineSensorCalibrator, SensorCalConfig, SensorCalTelemetry};
pub use simd::*;
pub use stft::StreamingStft;
pub use thermal_noise::{
    ThermalNoiseConfig, ThermalNoiseEstimator, ThermalNoiseTelemetry, BOLTZMANN_CONSTANT,
    MAX_THERMAL_BINS,
};
pub use transient::{TransientBlanker, TransientConfig};
pub use transparency::{TacticalTransparency, TransparencyConfig};
pub use whisper::{WhisperConfig, WhisperReconstructor, WhisperStats};
pub use wind::{WindDetectorConfig, WindTelemetry, WindTurbulenceSuppressor};
pub use window::{compute_synthesis_window, generate_analysis_window, WindowType};
pub use xtc::{TransauralXtc, XtcConfig};
