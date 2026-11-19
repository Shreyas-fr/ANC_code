//! Real-time streaming pipeline, lock-free ring buffers, and playout scheduling.

pub mod pipeline;
pub mod ring_buffer;
pub mod scheduler;

pub use pipeline::{PipelineConfig, TacticalAncPipeline};
pub use ring_buffer::{create_audio_ring_buffer, AudioConsumer, AudioProducer};
pub use scheduler::{PlayoutScheduler, PlayoutState};
