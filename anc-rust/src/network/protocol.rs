//! SIH 26052 UDP Network Wire Protocol specifications.

use std::io::{self, Cursor};
use byteorder::{LittleEndian, ReadBytesExt, WriteBytesExt};
use serde::{Deserialize, Serialize};

/// Standard packet sizes for SIH 26052 tactical audio transmission.
pub const AUDIO_FRAME_SAMPLES: usize = 256; // 16 ms @ 16 kHz
pub const AUDIO_PACKET_BYTES: usize = 8 + AUDIO_FRAME_SAMPLES * 4; // 1032 bytes

pub const DEFAULT_AUDIO_PORT: u16 = 5005;
pub const DEFAULT_TELEMETRY_PORT: u16 = 5006;
pub const DEFAULT_RAW_INPUT_PORT: u16 = 5007;

/// Parsed Audio Packet from UDP stream.
#[derive(Debug, Clone)]
pub struct AudioPacket {
    pub sequence: u64,
    pub samples: [f32; AUDIO_FRAME_SAMPLES],
}

impl AudioPacket {
    /// Serializes audio packet into a 1032-byte UDP datagram.
    pub fn serialize(&self) -> Vec<u8> {
        let mut buf = Vec::with_capacity(AUDIO_PACKET_BYTES);
        buf.write_u64::<LittleEndian>(self.sequence).unwrap();
        for &s in &self.samples {
            buf.write_f32::<LittleEndian>(s).unwrap();
        }
        buf
    }

    /// Deserializes a raw 1032-byte UDP datagram.
    pub fn deserialize(bytes: &[u8]) -> io::Result<Self> {
        if bytes.len() < AUDIO_PACKET_BYTES {
            return Err(io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "Packet smaller than minimum 1032 bytes",
            ));
        }

        let mut rdr = Cursor::new(bytes);
        let sequence = rdr.read_u64::<LittleEndian>()?;
        let mut samples = [0.0f32; AUDIO_FRAME_SAMPLES];
        for s in samples.iter_mut() {
            *s = rdr.read_f32::<LittleEndian>()?;
        }

        Ok(Self { sequence, samples })
    }
}

/// Real-time edge telemetry payload sent to mission control on port 5006.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EdgeTelemetry {
    pub frame: u64,
    pub model: String,
    pub mode: String,
    pub model_active: bool,
    pub compute_time_ms: f32,
    pub algorithmic_latency_ms: f32,
    pub total_latency_ms: f32,
    pub avg_rtf: f32,
    pub deadline_misses: u64,
    pub fallback_frames: u64,
    pub enhanced_frames: u64,
    pub input_rms: f32,
    pub output_rms: f32,
    pub temperature_c: f32,
}
