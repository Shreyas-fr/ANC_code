//! Network wire protocols, low-latency UDP streamers, and receivers.

pub mod protocol;
pub mod receiver;
pub mod sender;

pub use protocol::{
    AudioPacket, EdgeTelemetry, AUDIO_FRAME_SAMPLES, AUDIO_PACKET_BYTES,
    DEFAULT_AUDIO_PORT, DEFAULT_RAW_INPUT_PORT, DEFAULT_TELEMETRY_PORT,
};
pub use receiver::{AudioReceiver, TelemetryReceiver};
pub use sender::EdgeSender;
