//! Tactical Sliding-Window XOR Parity Forward Error Correction (FEC).
//!
//! Developed for SIH 26052 Tactical Audio Systems.
//!
//! Tactical field radio networks and line-of-sight relays suffer from
//! packet burst drops due to multipath fading, terrain shadowing, and RF jamming.
//!
//! This module provides a zero-allocation, deterministic sliding-window XOR Parity FEC
//! codec for `AudioPacket`:
//! - `FecEncoder`: Maintains a ring buffer of recent packets and computes sliding-window XOR parity.
//! - `FecDecoder`: Reconstructs dropped packets bit-identically from parity before falling back to PLC.
//! - `FecStats`: Tracks packet recovery rate and RF link health metrics in real time.

use super::protocol::{AudioPacket, AUDIO_FRAME_SAMPLES};

/// Real-time Forward Error Correction statistics and RF Link Health.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct FecStats {
    pub packets_received: u64,
    pub packets_lost: u64,
    pub packets_recovered: u64,
    pub recovery_rate: f32,
    pub rf_link_health: f32,
}

impl FecStats {
    pub fn update(&mut self) {
        let total_lost = self.packets_lost;
        if total_lost > 0 {
            self.recovery_rate = (self.packets_recovered as f32 / total_lost as f32) * 100.0;
        } else {
            self.recovery_rate = 100.0;
        }

        let effective_unrecovered = self.packets_lost.saturating_sub(self.packets_recovered);
        let total_packets = self.packets_received + effective_unrecovered;
        if total_packets > 0 {
            let eff_loss = (effective_unrecovered as f32 / total_packets as f32) * 100.0;
            self.rf_link_health = (100.0 - eff_loss).clamp(0.0, 100.0);
        } else {
            self.rf_link_health = 100.0;
        }
    }
}

/// Lightweight sliding-window XOR parity FEC encoder.
///
/// Pre-allocates a fixed history buffer of recent audio payloads.
/// Operates with strictly zero heap allocations.
pub struct FecEncoder {
    history: [[f32; AUDIO_FRAME_SAMPLES]; 8],
    history_seq: [u64; 8],
    count: usize,
    window_size: u8,
}

impl FecEncoder {
    /// Creates a new `FecEncoder` with the specified parity window size (e.g. 2).
    pub fn new(window_size: u8) -> Self {
        let win = window_size.clamp(1, 4);
        Self {
            history: [[0.0f32; AUDIO_FRAME_SAMPLES]; 8],
            history_seq: [0u64; 8],
            count: 0,
            window_size: win,
        }
    }

    /// Resets encoder history.
    pub fn reset(&mut self) {
        self.count = 0;
        self.history_seq.fill(0);
    }

    /// Encodes an incoming packet, attaching sliding-window XOR parity protecting previous packets.
    pub fn encode(&mut self, sequence: u64, samples: [f32; AUDIO_FRAME_SAMPLES]) -> AudioPacket {
        let win = self.window_size as usize;

        let (fec_base_seq, fec_window, fec_parity) = if self.count >= win {
            let base_seq = sequence - win as u64;
            let mut parity_bits = [0u32; AUDIO_FRAME_SAMPLES];

            for w in 0..win {
                let target_seq = base_seq + w as u64;
                if let Some(pos) = self.find_history_pos(target_seq) {
                    let pkt_samples = &self.history[pos];
                    for i in 0..AUDIO_FRAME_SAMPLES {
                        parity_bits[i] ^= pkt_samples[i].to_bits();
                    }
                }
            }

            let mut parity_samples = [0.0f32; AUDIO_FRAME_SAMPLES];
            for i in 0..AUDIO_FRAME_SAMPLES {
                parity_samples[i] = f32::from_bits(parity_bits[i]);
            }

            (Some(base_seq), self.window_size, Some(parity_samples))
        } else {
            (None, 0, None)
        };

        // Store current packet in circular history
        let hist_idx = self.count % 8;
        self.history[hist_idx] = samples;
        self.history_seq[hist_idx] = sequence;
        self.count += 1;

        AudioPacket {
            sequence,
            samples,
            fec_base_seq,
            fec_window,
            fec_parity,
        }
    }

    fn find_history_pos(&self, seq: u64) -> Option<usize> {
        let search_len = self.count.min(8);
        (0..search_len).find(|&i| self.history_seq[i] == seq)
    }
}

/// Tactical FEC Decoder with real-time drop recovery.
///
/// Pre-allocates a circular history of received packets.
/// When a sequence gap is detected, reconstructs missing packets bit-identically using XOR parity.
pub struct FecDecoder {
    history: [[f32; AUDIO_FRAME_SAMPLES]; 16],
    history_seq: [u64; 16],
    history_valid: [bool; 16],
    last_seq: Option<u64>,
    pub stats: FecStats,
}

impl FecDecoder {
    pub fn new() -> Self {
        Self {
            history: [[0.0f32; AUDIO_FRAME_SAMPLES]; 16],
            history_seq: [0u64; 16],
            history_valid: [false; 16],
            last_seq: None,
            stats: FecStats::default(),
        }
    }

    pub fn reset(&mut self) {
        self.history_valid.fill(false);
        self.last_seq = None;
        self.stats = FecStats::default();
    }

    /// Decodes an incoming packet.
    ///
    /// If dropped packets are detected and successfully recovered, they are written to `recovered_out`.
    /// Returns the number of recovered packets written into `recovered_out`.
    pub fn process_packet(
        &mut self,
        packet: &AudioPacket,
        recovered_out: &mut [AudioPacket],
    ) -> usize {
        let mut recovered_count = 0;

        if let Some(last) = self.last_seq {
            if packet.sequence > last + 1 {
                let dropped_count = packet.sequence - (last + 1);
                self.stats.packets_lost += dropped_count;

                // Single packet loss recovery via XOR Parity
                if dropped_count == 1 && !recovered_out.is_empty() {
                    let missing_seq = last + 1;
                    if let (Some(base_seq), Some(parity)) = (packet.fec_base_seq, packet.fec_parity.as_ref()) {
                        let win = packet.fec_window as u64;
                        if missing_seq >= base_seq && missing_seq < base_seq + win {
                            // Check if all other packets in the window exist in history
                            let mut all_others_present = true;
                            let mut rec_bits = [0u32; AUDIO_FRAME_SAMPLES];
                            for i in 0..AUDIO_FRAME_SAMPLES {
                                rec_bits[i] = parity[i].to_bits();
                            }

                            for w in 0..win {
                                let check_seq = base_seq + w;
                                if check_seq != missing_seq {
                                    if let Some(pos) = self.find_history_pos(check_seq) {
                                        let h_samples = &self.history[pos];
                                        for i in 0..AUDIO_FRAME_SAMPLES {
                                            rec_bits[i] ^= h_samples[i].to_bits();
                                        }
                                    } else {
                                        all_others_present = false;
                                        break;
                                    }
                                }
                            }

                            if all_others_present {
                                let mut rec_samples = [0.0f32; AUDIO_FRAME_SAMPLES];
                                for i in 0..AUDIO_FRAME_SAMPLES {
                                    rec_samples[i] = f32::from_bits(rec_bits[i]);
                                }

                                // Store recovered packet in history
                                self.store_history(missing_seq, rec_samples);
                                self.stats.packets_recovered += 1;

                                recovered_out[0] = AudioPacket {
                                    sequence: missing_seq,
                                    samples: rec_samples,
                                    fec_base_seq: None,
                                    fec_window: 0,
                                    fec_parity: None,
                                };
                                recovered_count = 1;
                            }
                        }
                    }
                }
            }
        }

        // Store received packet in history
        self.store_history(packet.sequence, packet.samples);
        self.last_seq = Some(packet.sequence);
        self.stats.packets_received += 1;
        self.stats.update();

        recovered_count
    }

    fn store_history(&mut self, seq: u64, samples: [f32; AUDIO_FRAME_SAMPLES]) {
        let idx = (seq % 16) as usize;
        self.history[idx] = samples;
        self.history_seq[idx] = seq;
        self.history_valid[idx] = true;
    }

    fn find_history_pos(&self, seq: u64) -> Option<usize> {
        let idx = (seq % 16) as usize;
        if self.history_valid[idx] && self.history_seq[idx] == seq {
            Some(idx)
        } else {
            None
        }
    }
}

impl Default for FecDecoder {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fec_encode_decode_perfect_recovery() {
        let mut encoder = FecEncoder::new(2);
        let mut decoder = FecDecoder::new();

        let mut samples0 = [0.0f32; AUDIO_FRAME_SAMPLES];
        samples0[0] = 0.42;
        samples0[100] = -0.75;

        let mut samples1 = [0.0f32; AUDIO_FRAME_SAMPLES];
        samples1[0] = 0.88;
        samples1[100] = 0.12;

        let mut samples2 = [0.0f32; AUDIO_FRAME_SAMPLES];
        samples2[0] = -0.33;
        samples2[100] = 0.99;

        let pkt0 = encoder.encode(0, samples0);
        let pkt1 = encoder.encode(1, samples1);
        let _pkt2 = encoder.encode(2, samples2);

        let mut rec_buf = [AudioPacket {
            sequence: 0,
            samples: [0.0; AUDIO_FRAME_SAMPLES],
            fec_base_seq: None,
            fec_window: 0,
            fec_parity: None,
        }];

        // Receive pkt0 and pkt1
        assert_eq!(decoder.process_packet(&pkt0, &mut rec_buf), 0);
        assert_eq!(decoder.process_packet(&pkt1, &mut rec_buf), 0);

        // Now imagine pkt2 was LOST, and pkt3 arrives
        let mut samples3 = [0.0f32; AUDIO_FRAME_SAMPLES];
        samples3[0] = 0.55;
        let pkt3 = encoder.encode(3, samples3);

        // Process pkt3: it should recover dropped pkt2!
        let n_rec = decoder.process_packet(&pkt3, &mut rec_buf);
        assert_eq!(n_rec, 1, "FEC should have recovered the dropped packet");
        assert_eq!(rec_buf[0].sequence, 2);

        // Verify bit-exact recovery of samples2
        assert_eq!(rec_buf[0].samples[0].to_bits(), samples2[0].to_bits());
        assert_eq!(rec_buf[0].samples[100].to_bits(), samples2[100].to_bits());
        assert_eq!(decoder.stats.packets_recovered, 1);
        assert_eq!(decoder.stats.recovery_rate, 100.0);
    }
}
