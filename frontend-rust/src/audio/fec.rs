//! Tactical Forward Error Correction (FEC) Receiver and Jitter Buffer bridge.
//!
//! Developed for DRDO SIH 26052 Live Defence Dashboard.
//!
//! Provides a seamless bridge between sliding-window XOR Parity FEC reconstruction
//! and soundcard JitterBuffer playout with Packet Loss Concealment (PLC) fallback.

use super::jitter_buffer::JitterBuffer;
use anc_rust::network::{AudioPacket, FecDecoder, FecStats, AUDIO_FRAME_SAMPLES};

/// Tactical FEC bridge coupling sliding-window XOR decoding with JitterBuffer.
pub struct FecJitterBridge {
    pub decoder: FecDecoder,
    rec_buffer: [AudioPacket; 2],
}

impl FecJitterBridge {
    pub fn new() -> Self {
        Self {
            decoder: FecDecoder::new(),
            rec_buffer: [
                AudioPacket::new(0, [0.0; AUDIO_FRAME_SAMPLES]),
                AudioPacket::new(0, [0.0; AUDIO_FRAME_SAMPLES]),
            ],
        }
    }

    /// Processes an incoming audio packet:
    /// Reconstructs missing packets via XOR Parity FEC if possible and writes them into `jitter_buf`.
    /// Then writes the incoming packet.
    ///
    /// If packet loss exceeds FEC recovery window, unrecovered gaps are smoothly
    /// concealed by `JitterBuffer`'s pitch-synchronous Packet Loss Concealment (PLC).
    pub fn handle_packet(&mut self, packet: &AudioPacket, jitter_buf: &mut JitterBuffer) {
        let n_rec = self.decoder.process_packet(packet, &mut self.rec_buffer);
        for item in self.rec_buffer.iter().take(n_rec) {
            jitter_buf.write(&item.samples);
        }
        jitter_buf.write(&packet.samples);
    }

    /// Returns current FEC recovery and RF Link Health statistics.
    pub fn stats(&self) -> FecStats {
        self.decoder.stats
    }

    /// Resets FEC decoder history and statistics.
    pub fn reset(&mut self) {
        self.decoder.reset();
    }
}

impl Default for FecJitterBridge {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use anc_rust::network::FecEncoder;

    #[test]
    fn test_fec_jitter_bridge_exact_recovery_before_plc() {
        let mut encoder = FecEncoder::new(2);
        let mut bridge = FecJitterBridge::new();
        let mut jb = JitterBuffer::new(16000, 48, 250, false);

        let mut s0 = [0.0f32; AUDIO_FRAME_SAMPLES];
        s0[0] = 0.50;
        let mut s1 = [0.0f32; AUDIO_FRAME_SAMPLES];
        s1[0] = 0.75;
        let mut s2 = [0.0f32; AUDIO_FRAME_SAMPLES];
        s2[0] = 0.90;

        let pkt0 = encoder.encode(0, s0);
        let pkt1 = encoder.encode(1, s1);
        let _pkt2 = encoder.encode(2, s2); // Simulating pkt2 lost over RF

        let mut s3 = [0.0f32; AUDIO_FRAME_SAMPLES];
        s3[0] = 0.20;
        let pkt3 = encoder.encode(3, s3);

        bridge.handle_packet(&pkt0, &mut jb);
        bridge.handle_packet(&pkt1, &mut jb);

        // Packet 2 dropped; packet 3 arrives
        bridge.handle_packet(&pkt3, &mut jb);

        // Verification:
        // 1. FEC stats must show 1 packet recovered
        let stats = bridge.stats();
        assert_eq!(stats.packets_recovered, 1);
        assert_eq!(stats.recovery_rate, 100.0);
        assert_eq!(stats.rf_link_health, 100.0);

        // 2. JitterBuffer must contain 4 packets total (0, 1, recovered 2, 3) = 1024 samples
        let mut read_buf = vec![0.0f32; 1024];
        jb.read(&mut read_buf);

        // Sample 0 of packet 2 (at offset 512) must match s2[0] exactly!
        assert!((read_buf[512] - 0.90).abs() < 1e-6);
        // Sample 0 of packet 3 (at offset 768) must match s3[0]
        assert!((read_buf[768] - 0.20).abs() < 1e-6);
    }
}
