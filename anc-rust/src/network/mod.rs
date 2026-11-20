//! Network wire protocols, low-latency UDP streamers, and receivers.

pub mod atak;
pub mod codec;
pub mod crypto;
pub mod fec;
pub mod jamming;
pub mod mesh;
pub mod protocol;
pub mod receiver;
pub mod sender;

pub use atak::{
    AtakCotBridge, AtakTelemetry, TacticalSoldierProfile, ATAK_MULTICAST_ADDR, MAX_COT_XML_BYTES,
};
pub use codec::{
    AdpcmDecoder, AdpcmEncoder, AdpcmFecCodec, AdpcmPacket, ADPCM_FEC_PACKET_BYTES,
    ADPCM_FRAME_SAMPLES, ADPCM_PACKET_BYTES, ADPCM_PAYLOAD_BYTES,
};
pub use crypto::{
    constant_time_eq_16, AntiReplayWindow, AuthResult, Poly1305, TacticalFrameAuthenticator,
    CRYPTO_KEY_BYTES, MAC_TAG_BYTES, REPLAY_WINDOW_SIZE,
};
pub use fec::{FecDecoder, FecEncoder, FecStats};
pub use jamming::{
    JammingDetector, JammingDetectorConfig, JammingRemediation, JammingTelemetry, JammingType,
    JAMMING_HISTORY_SIZE,
};
pub use mesh::{
    CryptoRatchet, MeshPacket, MeshPacketType, MeshRouter, Position3D, RoutingAction,
    SpatialConsensusEngine, SquadMemberNode, MAX_SQUAD_MEMBERS, MESH_BROADCAST_ID,
    MESH_PAYLOAD_BYTES,
};
pub use protocol::{
    AudioPacket, DspStageTimings, EdgeTelemetry, AUDIO_FRAME_SAMPLES, AUDIO_PACKET_BYTES,
    DEFAULT_AUDIO_PORT, DEFAULT_RAW_INPUT_PORT, DEFAULT_TELEMETRY_PORT, FEC_PACKET_TOTAL_BYTES,
};
pub use receiver::{AudioReceiver, TelemetryReceiver};
pub use sender::EdgeSender;
