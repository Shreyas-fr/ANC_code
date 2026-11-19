//! Objective metrics, SI-SDR/SNR estimators, and system telemetry.

pub mod snr;
pub mod telemetry;

pub use snr::{compute_active_speech_level, compute_explicit_snr, compute_si_sdr};
pub use telemetry::{read_system_temperature_c, PerformanceProfiler};
