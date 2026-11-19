//! Virtual-clock cycle-accurate playout scheduler and zero-drop fallback coordinator.
//!
//! Synchronizes audio capture packets with neural inference results:
//! - Guarantees time-aligned output: at tick `seq`, plays source time `t = seq - J - Dp`.
//! - If model inference is delayed past the jitter budget, emits the time-aligned raw audio.
//! - Smooth offset-decay crossfading prevents clicks and pop artifacts during transitions.

use std::collections::HashMap;

/// Playout state: Enhanced vs Raw Fallback
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PlayoutState {
    Silence,
    Enhanced,
    FallbackRaw,
}

/// Playout Scheduler for deterministic low-latency streaming.
pub struct PlayoutScheduler {
    pub chain_delay_packets: usize,
    pub jitter_packets: usize,
    pub packet_size: usize,

    raw_history: HashMap<u64, Vec<f32>>,
    enhanced_queue: HashMap<u64, Vec<f32>>,

    last_state: PlayoutState,
    offset_decay: Vec<f32>,

    pub enhanced_frames: u64,
    pub fallback_frames: u64,
    pub state_switches: u64,
    pub late_results: u64,
}

impl PlayoutScheduler {
    /// Creates a new PlayoutScheduler.
    ///
    /// - `chain_delay_packets`: algorithmic delay of the processing chain in packets.
    /// - `jitter_packets`: slack given to slow model inference before raw fallback.
    /// - `packet_size`: audio samples per packet (e.g. 256 samples = 16 ms at 16 kHz).
    pub fn new(chain_delay_packets: usize, jitter_packets: usize, packet_size: usize) -> Self {
        let xfade_len = packet_size / 2; // e.g. 8 ms crossfade
        let mut offset_decay = Vec::with_capacity(xfade_len);
        for i in 0..xfade_len {
            offset_decay.push(1.0 - i as f32 / xfade_len as f32);
        }

        Self {
            chain_delay_packets,
            jitter_packets,
            packet_size,
            raw_history: HashMap::new(),
            enhanced_queue: HashMap::new(),
            last_state: PlayoutState::Silence,
            offset_decay,
            enhanced_frames: 0,
            fallback_frames: 0,
            state_switches: 0,
            late_results: 0,
        }
    }

    /// Total configured sender delay in packets.
    pub fn total_delay_packets(&self) -> usize {
        self.chain_delay_packets + self.jitter_packets
    }

    /// Stores a raw input audio packet at the given sequence index.
    pub fn push_input(&mut self, seq: u64, chunk: &[f32]) {
        self.raw_history.insert(seq, chunk.to_vec());

        // Prune stale input older than (total_delay + 32) packets
        let max_age = (self.total_delay_packets() + 32) as u64;
        if seq > max_age {
            self.raw_history.retain(|&k, _| k >= seq - max_age);
        }
    }

    /// Delivers an enhanced audio packet from the neural worker thread.
    pub fn push_enhanced_result(&mut self, seq: u64, chunk: Vec<f32>) {
        self.enhanced_queue.insert(seq, chunk);
    }

    /// Generates the next playout audio packet for transmission or speaker DAC.
    pub fn next_output(&mut self, seq: u64, out: &mut [f32]) {
        assert_eq!(out.len(), self.packet_size);

        let total_delay = self.total_delay_packets() as u64;
        if seq < total_delay {
            // Priming phase: output silence
            out.fill(0.0);
            self.last_state = PlayoutState::Silence;
            return;
        }

        let target_seq = seq - self.jitter_packets as u64;
        let source_seq = seq - total_delay;

        // Clean up any results that arrived too late to be played
        self.enhanced_queue.retain(|&k, _| {
            if k < target_seq {
                self.late_results += 1;
                false
            } else {
                true
            }
        });

        // Check if enhanced packet is ready
        if let Some(enh_chunk) = self.enhanced_queue.remove(&target_seq) {
            out.copy_from_slice(&enh_chunk);
            self.enhanced_frames += 1;

            if self.last_state == PlayoutState::FallbackRaw {
                self.state_switches += 1;
                self.apply_smoothing(out, source_seq, true);
            }
            self.last_state = PlayoutState::Enhanced;
        } else {
            // Fallback: Use time-aligned raw audio packet from exact same source instant
            if let Some(raw_chunk) = self.raw_history.get(&source_seq) {
                out.copy_from_slice(raw_chunk);
            } else {
                out.fill(0.0);
            }
            self.fallback_frames += 1;

            if self.last_state == PlayoutState::Enhanced {
                self.state_switches += 1;
                self.apply_smoothing(out, source_seq, false);
            }
            self.last_state = PlayoutState::FallbackRaw;
        }
    }

    /// Smooths state transition boundaries via decaying linear ramp to avoid audible clicks.
    fn apply_smoothing(&self, out: &mut [f32], _source_seq: u64, _to_enhanced: bool) {
        let n = self.offset_decay.len().min(out.len());
        let step = out[0] * 0.25;
        for i in 0..n {
            out[i] -= step * self.offset_decay[i];
        }
    }
}
