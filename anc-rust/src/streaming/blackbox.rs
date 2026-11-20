//! Tactical Mission Blackbox Logger & Telemetry Ring Recorder.
//!
//! Provides a zero-allocation, fixed-capacity circular ring recorder maintaining
//! a rolling 10+ seconds of high-resolution acoustic telemetry, XRUN timestamps,
//! DOA trajectory, and incident flags for forensic post-mission acoustic analysis.
//!
//! Zero heap allocations in the real-time audio recording path.

use std::io::{self, Write};
use std::time::Instant;

/// Number of frames maintained in rolling circular ring buffer (1024 frames * 16 ms ~= 16.38 seconds).
pub const BLACKBOX_CAPACITY: usize = 1024;
pub const BLACKBOX_MASK: usize = BLACKBOX_CAPACITY - 1;

/// Incident detection bitflags.
pub const FLAG_NOMINAL: u32 = 0;
pub const FLAG_CONCUSSION_SHOCK: u32 = 1 << 0;
pub const FLAG_XRUN_DEADLINE_BREACH: u32 = 1 << 1;
pub const FLAG_OUTPUT_CLIPPING: u32 = 1 << 2;
pub const FLAG_RF_BURST_LOSS: u32 = 1 << 3;
pub const FLAG_ACOUSTIC_FEEDBACK: u32 = 1 << 4;

/// A single timestamped forensic telemetry entry recorded per hop.
#[derive(Debug, Clone, Copy, Default)]
pub struct BlackboxEntry {
    pub timestamp_us: u64,
    pub frame_seq: u64,
    pub input_rms: f32,
    pub output_rms: f32,
    pub snr_gain_est_db: f32,
    pub talker_angle_deg: f32,
    pub doa_confidence: f32,
    pub mean_cdr_db: f32,
    pub speech_intelligibility_index: f32,
    pub total_dsp_us: u32,
    pub incident_flags: u32,
}

/// Incident summary statistics over the rolling telemetry window.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct BlackboxIncidentSummary {
    pub total_recorded_frames: u64,
    pub rolling_window_frames: usize,
    pub concussion_events: u32,
    pub xrun_deadline_breaches: u32,
    pub clipping_events: u32,
    pub mean_input_rms: f32,
    pub mean_output_rms: f32,
    pub max_dsp_us: u32,
}

/// Zero-Allocation Tactical Mission Blackbox Logger.
pub struct TacticalBlackbox {
    entries: Box<[BlackboxEntry; BLACKBOX_CAPACITY]>,
    write_head: usize,
    total_frames: u64,
    concussion_count: u32,
    xrun_count: u32,
    clipping_count: u32,
    start_instant: Instant,
}

impl TacticalBlackbox {
    /// Creates a new `TacticalBlackbox` with pre-allocated circular ring storage.
    pub fn new() -> Self {
        // Allocate once at initialization
        let entries = vec![BlackboxEntry::default(); BLACKBOX_CAPACITY]
            .into_boxed_slice()
            .try_into()
            .unwrap_or_else(|_| panic!("Failed to allocate blackbox ring buffer"));

        Self {
            entries,
            write_head: 0,
            total_frames: 0,
            concussion_count: 0,
            xrun_count: 0,
            clipping_count: 0,
            start_instant: Instant::now(),
        }
    }

    /// Resets all recorded blackbox history.
    pub fn reset(&mut self) {
        for entry in self.entries.iter_mut() {
            *entry = BlackboxEntry::default();
        }
        self.write_head = 0;
        self.total_frames = 0;
        self.concussion_count = 0;
        self.xrun_count = 0;
        self.clipping_count = 0;
        self.start_instant = Instant::now();
    }

    /// Records a pre-built telemetry entry into the circular buffer.
    ///
    /// Zero heap allocations.
    #[inline(always)]
    pub fn record_entry(&mut self, mut entry: BlackboxEntry) {
        if (entry.incident_flags & FLAG_CONCUSSION_SHOCK) != 0 {
            self.concussion_count = self.concussion_count.saturating_add(1);
        }
        if (entry.incident_flags & FLAG_XRUN_DEADLINE_BREACH) != 0 {
            self.xrun_count = self.xrun_count.saturating_add(1);
        }
        if (entry.incident_flags & FLAG_OUTPUT_CLIPPING) != 0 {
            self.clipping_count = self.clipping_count.saturating_add(1);
        }

        entry.timestamp_us = self.start_instant.elapsed().as_micros() as u64;

        self.entries[self.write_head] = entry;
        self.write_head = (self.write_head + 1) & BLACKBOX_MASK;
        self.total_frames = self.total_frames.saturating_add(1);
    }

    /// Convenience record helper for the audio processing thread.
    ///
    /// Zero heap allocations.
    #[allow(clippy::too_many_arguments)]
    #[inline(always)]
    pub fn record_hop(
        &mut self,
        frame_seq: u64,
        input_rms: f32,
        output_rms: f32,
        talker_angle_deg: f32,
        doa_confidence: f32,
        mean_cdr_db: f32,
        speech_intelligibility_index: f32,
        total_dsp_us: u32,
        is_xrun: bool,
        is_concussion: bool,
    ) {
        let mut flags = FLAG_NOMINAL;
        if is_concussion || input_rms > 0.85 {
            flags |= FLAG_CONCUSSION_SHOCK;
        }
        if is_xrun || total_dsp_us > 15_000 {
            flags |= FLAG_XRUN_DEADLINE_BREACH;
        }
        if output_rms > 0.99 {
            flags |= FLAG_OUTPUT_CLIPPING;
        }

        let snr_gain_est_db = if input_rms > 1e-6 && output_rms > 1e-6 {
            20.0 * (input_rms / output_rms).max(0.1).log10()
        } else {
            0.0
        };

        let entry = BlackboxEntry {
            timestamp_us: 0, // Filled in record_entry
            frame_seq,
            input_rms,
            output_rms,
            snr_gain_est_db,
            talker_angle_deg,
            doa_confidence,
            mean_cdr_db,
            speech_intelligibility_index,
            total_dsp_us,
            incident_flags: flags,
        };

        self.record_entry(entry);
    }

    /// Returns the most recent recorded telemetry entry, if any.
    pub fn latest_entry(&self) -> Option<&BlackboxEntry> {
        if self.total_frames == 0 {
            None
        } else {
            let last_idx = (self.write_head + BLACKBOX_CAPACITY - 1) & BLACKBOX_MASK;
            Some(&self.entries[last_idx])
        }
    }

    /// Total count of frames recorded since creation/reset.
    pub fn total_frames(&self) -> u64 {
        self.total_frames
    }

    /// Current count of active entries stored in the rolling buffer.
    pub fn count(&self) -> usize {
        (self.total_frames as usize).min(BLACKBOX_CAPACITY)
    }

    /// Retrieves incident summary statistics over the rolling telemetry window.
    pub fn incident_summary(&self) -> BlackboxIncidentSummary {
        let count = self.count();
        if count == 0 {
            return BlackboxIncidentSummary::default();
        }

        let mut sum_in = 0.0f32;
        let mut sum_out = 0.0f32;
        let mut max_dsp = 0u32;
        let mut conc = 0u32;
        let mut xrun = 0u32;
        let mut clip = 0u32;

        for i in 0..count {
            let idx = (self.write_head + BLACKBOX_CAPACITY - 1 - i) & BLACKBOX_MASK;
            let e = &self.entries[idx];
            sum_in += e.input_rms;
            sum_out += e.output_rms;
            if e.total_dsp_us > max_dsp {
                max_dsp = e.total_dsp_us;
            }
            if (e.incident_flags & FLAG_CONCUSSION_SHOCK) != 0 {
                conc += 1;
            }
            if (e.incident_flags & FLAG_XRUN_DEADLINE_BREACH) != 0 {
                xrun += 1;
            }
            if (e.incident_flags & FLAG_OUTPUT_CLIPPING) != 0 {
                clip += 1;
            }
        }

        BlackboxIncidentSummary {
            total_recorded_frames: self.total_frames,
            rolling_window_frames: count,
            concussion_events: conc,
            xrun_deadline_breaches: xrun,
            clipping_events: clip,
            mean_input_rms: sum_in / count as f32,
            mean_output_rms: sum_out / count as f32,
            max_dsp_us: max_dsp,
        }
    }

    /// Exports rolling telemetry to CSV format for external forensic analysis.
    pub fn export_forensic_csv(&self, writer: &mut dyn Write) -> io::Result<usize> {
        let count = self.count();
        writeln!(
            writer,
            "timestamp_us,frame_seq,input_rms,output_rms,snr_gain_db,talker_angle_deg,doa_confidence,mean_cdr_db,sii,dsp_us,flags"
        )?;

        let mut written = 0;
        // Output in chronological order: oldest to newest
        let start_offset = if self.total_frames >= BLACKBOX_CAPACITY as u64 {
            self.write_head
        } else {
            0
        };

        for i in 0..count {
            let idx = (start_offset + i) & BLACKBOX_MASK;
            let e = &self.entries[idx];
            writeln!(
                writer,
                "{},{},{:.4},{:.4},{:.2},{:.1},{:.3},{:.2},{:.3},{},0x{:02X}",
                e.timestamp_us,
                e.frame_seq,
                e.input_rms,
                e.output_rms,
                e.snr_gain_est_db,
                e.talker_angle_deg,
                e.doa_confidence,
                e.mean_cdr_db,
                e.speech_intelligibility_index,
                e.total_dsp_us,
                e.incident_flags
            )?;
            written += 1;
        }

        Ok(written)
    }
}

impl Default for TacticalBlackbox {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_blackbox_ring_wrapping_and_capacity() {
        let mut bb = TacticalBlackbox::new();
        assert_eq!(bb.count(), 0);

        // Push 1500 frames (exceeding 1024 capacity)
        for i in 0..1500 {
            bb.record_hop(i, 0.05, 0.02, 15.0, 0.90, 8.5, 0.88, 75, false, false);
        }

        assert_eq!(bb.total_frames(), 1500);
        assert_eq!(bb.count(), BLACKBOX_CAPACITY);

        let latest = bb.latest_entry().unwrap();
        assert_eq!(latest.frame_seq, 1499);
    }

    #[test]
    fn test_blackbox_incident_detection_and_summary() {
        let mut bb = TacticalBlackbox::new();

        // Record 10 nominal frames
        for i in 0..10 {
            bb.record_hop(i, 0.05, 0.02, 0.0, 0.8, 5.0, 0.8, 80, false, false);
        }

        // Record a concussion shock event
        bb.record_hop(10, 0.95, 0.10, 0.0, 0.8, 5.0, 0.8, 80, false, true);

        // Record an XRUN deadline breach
        bb.record_hop(11, 0.05, 0.02, 0.0, 0.8, 5.0, 0.8, 16500, true, false);

        // Record a clipping event
        bb.record_hop(12, 0.05, 1.05, 0.0, 0.8, 5.0, 0.8, 80, false, false);

        let summary = bb.incident_summary();
        assert_eq!(summary.rolling_window_frames, 13);
        assert_eq!(summary.concussion_events, 1);
        assert_eq!(summary.xrun_deadline_breaches, 1);
        assert_eq!(summary.clipping_events, 1);
        assert_eq!(summary.max_dsp_us, 16500);
    }

    #[test]
    fn test_blackbox_export_forensic_csv() {
        let mut bb = TacticalBlackbox::new();
        for i in 0..5 {
            bb.record_hop(i, 0.1, 0.05, 10.0, 0.95, 12.0, 0.85, 90, false, false);
        }

        let mut buf = Vec::new();
        let written = bb.export_forensic_csv(&mut buf).unwrap();
        assert_eq!(written, 5);

        let csv_text = String::from_utf8(buf).unwrap();
        assert!(csv_text.starts_with("timestamp_us,frame_seq,input_rms"));
        let lines: Vec<&str> = csv_text.lines().collect();
        assert_eq!(lines.len(), 6); // Header + 5 entries
    }
}
