//! ANC-Rust: High-Performance Real-Time AI Active Noise Cancellation
//! and Tactical Speech Enhancement Daemon for Embedded Hardware (Raspberry Pi 5).
//!
//! Developed for DRDO SIH 26052.

pub mod dsp;
pub mod metrics;
pub mod model;
pub mod network;
pub mod streaming;

pub use dsp::{
    CausalAgc, CausalDereverberator, CausalMvdrBeamformer, DereverbConfig, MvdrConfig, SoftLimiter,
    StreamingStft, TransientBlanker, TransientConfig, WindowType,
};
pub use metrics::{compute_active_speech_level, compute_explicit_snr, compute_si_sdr, PerformanceProfiler};
pub use model::{AdaptiveSpectralEnhancer, EnhancerStats, FrozenEnsemble, SpeechEnhancer, TractEnhancer};
pub use network::{AudioPacket, AudioReceiver, EdgeSender, EdgeTelemetry, TelemetryReceiver};
pub use streaming::{AudioConsumer, AudioProducer, PipelineConfig, PlayoutScheduler, TacticalAncPipeline};
