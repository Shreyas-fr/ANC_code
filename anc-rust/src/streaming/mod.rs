//! Real-time streaming pipeline, lock-free ring buffers, and playout scheduling.

pub mod alsa_hw;
pub mod battery;
pub mod blackbox;
pub mod dma;
pub mod duplex;
pub mod governor;
pub mod pipeline;
pub mod ring_buffer;
pub mod rt_prio;
pub mod scheduler;

pub use alsa_hw::{AlsaError, AlsaHwReport, AlsaIrqEvent, AlsaMmapConfig, AlsaMmapSimulator};
pub use battery::{BatteryConfig, BatterySimulator, BatteryTelemetry, TacticalPowerMode};
pub use blackbox::{
    BlackboxEntry, BlackboxIncidentSummary, TacticalBlackbox, BLACKBOX_CAPACITY,
    FLAG_CONCUSSION_SHOCK, FLAG_NOMINAL, FLAG_OUTPUT_CLIPPING, FLAG_RF_BURST_LOSS,
    FLAG_XRUN_DEADLINE_BREACH,
};
pub use dma::{CodecModel, DmaInterruptResult, DmaJitterConfig, DmaTelemetry, I2sDmaDriver};
pub use duplex::{DuplexConfig, DuplexStreamCoordinator, DuplexTelemetry};
pub use governor::{DvfsFrequency, GovernorConfig, GovernorTelemetry, PowerGovernor};
pub use pipeline::{MissionProfile, PipelineConfig, TacticalAncPipeline};
pub use ring_buffer::{create_audio_ring_buffer, AudioConsumer, AudioProducer};
pub use rt_prio::{RtGovernorConfig, RtGovernorStatus, RtPrioGovernor, RtSchedPolicy};
pub use scheduler::{PlayoutScheduler, PlayoutState};
