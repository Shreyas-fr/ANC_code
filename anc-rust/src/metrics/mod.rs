//! Objective metrics, SI-SDR/SNR estimators, and system telemetry.

pub mod blast;
pub mod cable;
pub mod convergence;
pub mod distortion;
pub mod snr;
pub mod sti;
pub mod stress;
pub mod telemetry;

pub use blast::{
    BlastEvent, BlastHazardStatus, BlastImpulseMeter, BlastMeterConfig, BlastTelemetry,
    BLAST_HISTORY_CAPACITY, PASCALS_PER_PSI, P_REF_PASCALS,
};
pub use cable::{CableConfig, CableDiagnostics, CableFaultStatus, CableTelemetry};
pub use convergence::{
    AdaptiveConvergenceProfiler, ConvergenceState, FilterConvergenceConfig,
    FilterConvergenceStatus, FilterType, SingleFilterTracker,
};
pub use distortion::{
    DistortionAnalyzer, DistortionConfig, DistortionMetrics, VoiceCoilHealthStatus,
    DEFAULT_ANALYZER_FFT_SIZE, MAX_SPECTRUM_BINS,
};
pub use snr::{compute_active_speech_level, compute_explicit_snr, compute_si_sdr};
pub use sti::{
    RastiPredictor, StiConfig, StiRating, StiTelemetry, NUM_RASTI_MOD_FREQS, RASTI_HISTORY_HOPS,
    RASTI_MOD_FREQS_HZ,
};
pub use stress::{StressProfiler, StressProfilerConfig, StressTelemetry};
pub use telemetry::{read_system_temperature_c, PerformanceProfiler};
