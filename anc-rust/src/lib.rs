//! ANC-Rust: High-Performance Real-Time AI Active Noise Cancellation
//! and Tactical Speech Enhancement Daemon for Embedded Hardware (Raspberry Pi 5).
//!
//! Developed for DRDO SIH 26052.

#![allow(clippy::needless_range_loop, clippy::chunks_exact_to_as_chunks)]

pub mod dsp;
pub mod metrics;
pub mod model;
pub mod network;
pub mod streaming;

pub use dsp::{
    BinauralConfig, BinauralSpatialRenderer, CausalAgc, CausalDereverberator, CausalMvdrBeamformer,
    DereverbConfig, IntelligibilityConfig, IntelligibilityEnhancer, LufsConfig, LufsGovernor,
    LufsTelemetry, MvdrConfig, OnlineSensorCalibrator, ResPostfilterConfig, ResPostfilterStats,
    SensorCalConfig, SensorCalTelemetry, SoftLimiter, StreamingStft, SubbandResPostfilter,
    TransientBlanker, TransientConfig, WindowType,
};
pub use metrics::{
    compute_active_speech_level, compute_explicit_snr, compute_si_sdr, PerformanceProfiler,
};
pub use model::{
    AdaptiveSpectralEnhancer, EnhancerStats, FrozenEnsemble, SpeechEnhancer, TractEnhancer,
};
pub use network::{
    AudioPacket, AudioReceiver, EdgeSender, EdgeTelemetry, FecDecoder, FecEncoder, FecStats,
    TelemetryReceiver,
};
pub use streaming::{
    AudioConsumer, AudioProducer, MissionProfile, PipelineConfig, PlayoutScheduler,
    TacticalAncPipeline,
};
