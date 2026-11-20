//! Tactical RF Jamming & Link Degradation Detector.
//!
//! Developed for SIH 26052 Tactical Military Communications.
//!
//! In modern Electronic Warfare (EW) combat scenarios, hostile airborne or vehicular
//! jamming pods flood the tactical RF spectrum with:
//! 1. Spot Jamming: Narrowband energy concentrated on the tactical channel.
//! 2. Barrage Jamming: High-power broadband white Gaussian noise covering the entire operational band.
//! 3. Sweep Jamming: Rapidly sweeping narrowband chirp carrier that cyclically punches holes in packets.
//! 4. RF Spoofing / Tampering: Hostile replay or bit-flipping attacks causing Poly1305 auth tag failures.
//!
//! This module continuously analyzes:
//! - Packet inter-arrival jitter and jitter variance (sigma_J^2).
//! - Sequence gap distribution and burst drop clustering (bursts of >= 3 dropped packets).
//! - Poly1305 cryptographic authentication integrity.
//! - Sweep jamming recurrence periodicity.
//!
//! Upon jamming detection, it automatically commands the sender to switch to:
//! - 4-bit IMA/DVI ADPCM (reducing datagram payload from 1032 B to 140 B, an 86.4% reduction in airtime).
//! - Maximum 1:1 XOR FEC parity redundancy to guarantee voice delivery under 50% packet erasure.
//!
//! Strictly ZERO heap allocations in the real-time network path.

use serde::{Deserialize, Serialize};

/// Number of historical packet frames tracked in circular buffers.
pub const JAMMING_HISTORY_SIZE: usize = 64;

/// Classification of tactical RF channel condition.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[repr(u8)]
pub enum JammingType {
    /// Nominal RF propagation conditions (drop < 3%, low jitter).
    NominalRF = 0,
    /// Narrowband spot jamming concentrated on the carrier.
    SpotJamming = 1,
    /// High-power wideband barrage jamming (extreme jitter & collapse of packets).
    BarrageJamming = 2,
    /// Periodic sweeping chirp jamming.
    SweepJamming = 3,
}

impl JammingType {
    pub fn name(&self) -> &'static str {
        match self {
            Self::NominalRF => "NOMINAL RF",
            Self::SpotJamming => "SPOT JAMMING",
            Self::BarrageJamming => "BARRAGE JAMMING",
            Self::SweepJamming => "SWEEP JAMMING",
        }
    }

    pub fn code(&self) -> u8 {
        *self as u8
    }

    pub fn from_u8(code: u8) -> Self {
        match code {
            1 => Self::SpotJamming,
            2 => Self::BarrageJamming,
            3 => Self::SweepJamming,
            _ => Self::NominalRF,
        }
    }
}

/// Tactical remediation action commanded by the Jamming Detector.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum JammingRemediation {
    /// Nominal transmission parameters (full PCM, standard FEC).
    None,
    /// Switch to 4-bit ADPCM and engage 100% XOR FEC parity redundancy.
    EngageAdpcm4BitAndMaxFec,
    /// Cryptographic alarm: hostile auth tampering or packet injection detected.
    CryptographicTamperAlarm,
}

/// Configuration for the Tactical Jamming Detector.
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct JammingDetectorConfig {
    /// Nominal expected inter-packet arrival time in milliseconds (default: 16.0 ms for 256 samples @ 16 kHz).
    pub nominal_interval_ms: f32,
    /// Jitter variance threshold for Barrage Jamming in ms^2 (default: 15.0 ms^2).
    pub barrage_jitter_var_thresh: f32,
    /// Packet loss threshold for Barrage Jamming (default: 0.25 = 25%).
    pub barrage_loss_thresh: f32,
    /// Burst loss clustering threshold for Spot Jamming (default: 0.35).
    pub spot_burst_thresh: f32,
    /// Minimum packet loss rate for Spot Jamming (default: 0.04 = 4%).
    pub spot_loss_thresh: f32,
    /// Auth failure threshold for tampering alarm (default: 0.02 = 2%).
    pub auth_failure_thresh: f32,
    /// Master enable toggle.
    pub enabled: bool,
}

impl Default for JammingDetectorConfig {
    fn default() -> Self {
        Self {
            nominal_interval_ms: 16.0,
            barrage_jitter_var_thresh: 15.0,
            barrage_loss_thresh: 0.25,
            spot_burst_thresh: 0.35,
            spot_loss_thresh: 0.04,
            auth_failure_thresh: 0.02,
            enabled: true,
        }
    }
}

/// Telemetry output produced by the Jamming Detector.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct JammingTelemetry {
    pub jamming_type: JammingType,
    pub confidence: f32,
    pub jitter_variance_ms2: f32,
    pub mean_jitter_ms: f32,
    pub packet_loss_rate: f32,
    pub burst_clustering: f32,
    pub auth_failure_rate: f32,
    pub remediation_active: bool,
    pub remediation_code: u8,
}

impl Default for JammingTelemetry {
    fn default() -> Self {
        Self {
            jamming_type: JammingType::NominalRF,
            confidence: 1.0,
            jitter_variance_ms2: 0.0,
            mean_jitter_ms: 0.0,
            packet_loss_rate: 0.0,
            burst_clustering: 0.0,
            auth_failure_rate: 0.0,
            remediation_active: false,
            remediation_code: 0,
        }
    }
}

/// Zero-heap Tactical RF Jamming and EW Degradation Detector.
#[derive(Debug, Clone)]
pub struct JammingDetector {
    config: JammingDetectorConfig,
    /// Circular buffer of recent inter-arrival intervals in ms
    intervals_ms: [f32; JAMMING_HISTORY_SIZE],
    /// Circular buffer of recent sequence drop gaps
    seq_gaps: [u32; JAMMING_HISTORY_SIZE],
    /// Circular buffer of auth failure flags (1 = failure, 0 = success)
    auth_flags: [u8; JAMMING_HISTORY_SIZE],
    /// Ring buffer head index
    head: usize,
    /// Total received packets count
    total_received: u64,
    /// Last received sequence number
    last_seq: Option<u64>,
    /// Last received timestamp in milliseconds
    last_timestamp_ms: Option<f64>,
    /// Smoothed mean jitter in ms
    smoothed_jitter_ms: f32,
    /// Smoothed jitter variance in ms^2
    smoothed_jitter_var: f32,
    /// Last classified state
    last_telemetry: JammingTelemetry,
}

impl JammingDetector {
    /// Creates a new JammingDetector.
    pub fn new(config: JammingDetectorConfig) -> Self {
        Self {
            config,
            intervals_ms: [config.nominal_interval_ms; JAMMING_HISTORY_SIZE],
            seq_gaps: [0; JAMMING_HISTORY_SIZE],
            auth_flags: [0; JAMMING_HISTORY_SIZE],
            head: 0,
            total_received: 0,
            last_seq: None,
            last_timestamp_ms: None,
            smoothed_jitter_ms: 0.0,
            smoothed_jitter_var: 0.0,
            last_telemetry: JammingTelemetry::default(),
        }
    }

    /// Resets all internal history buffers and counters.
    pub fn reset(&mut self) {
        self.intervals_ms.fill(self.config.nominal_interval_ms);
        self.seq_gaps.fill(0);
        self.auth_flags.fill(0);
        self.head = 0;
        self.total_received = 0;
        self.last_seq = None;
        self.last_timestamp_ms = None;
        self.smoothed_jitter_ms = 0.0;
        self.smoothed_jitter_var = 0.0;
        self.last_telemetry = JammingTelemetry::default();
    }

    /// Ingests an incoming packet event with arrival timestamp and sequence number.
    ///
    /// - `timestamp_ms`: Arrival time of packet in milliseconds (e.g. from monotonic clock).
    /// - `sequence`: Packet sequence number from wire protocol.
    /// - `auth_valid`: True if Poly1305 MAC tag verified, False if invalid or tampered.
    pub fn record_packet(
        &mut self,
        timestamp_ms: f64,
        sequence: u64,
        auth_valid: bool,
    ) -> (JammingType, JammingRemediation) {
        if !self.config.enabled {
            return (JammingType::NominalRF, JammingRemediation::None);
        }

        // 1. Calculate inter-arrival time and jitter
        let interval_ms = if let Some(last_ts) = self.last_timestamp_ms {
            let dt = (timestamp_ms - last_ts) as f32;
            if dt > 0.0 && dt < 1000.0 {
                dt
            } else {
                self.config.nominal_interval_ms
            }
        } else {
            self.config.nominal_interval_ms
        };
        self.last_timestamp_ms = Some(timestamp_ms);

        let jitter = (interval_ms - self.config.nominal_interval_ms).abs();

        // Exponential moving average for jitter and jitter variance
        let alpha = 0.10f32;
        self.smoothed_jitter_ms = (1.0 - alpha) * self.smoothed_jitter_ms + alpha * jitter;
        let j_diff = jitter - self.smoothed_jitter_ms;
        self.smoothed_jitter_var = (1.0 - alpha) * self.smoothed_jitter_var + alpha * (j_diff * j_diff);

        // 2. Calculate sequence drop gap
        let gap = if let Some(last_s) = self.last_seq {
            if sequence > last_s + 1 {
                (sequence - last_s - 1).min(100) as u32
            } else {
                0
            }
        } else {
            0
        };
        self.last_seq = Some(sequence);

        // 3. Store in circular history buffers
        self.intervals_ms[self.head] = interval_ms;
        self.seq_gaps[self.head] = gap;
        self.auth_flags[self.head] = if auth_valid { 0 } else { 1 };
        self.head = (self.head + 1) % JAMMING_HISTORY_SIZE;
        self.total_received += 1;

        // 4. Compute window statistics
        let window_len = (self.total_received as usize).min(JAMMING_HISTORY_SIZE);
        let mut total_drops = 0u32;
        let mut burst_drops = 0u32;
        let mut auth_errors = 0u32;

        for i in 0..window_len {
            let g = self.seq_gaps[i];
            total_drops += g;
            if g >= 3 {
                burst_drops += g;
            }
            if self.auth_flags[i] == 1 {
                auth_errors += 1;
            }
        }

        let total_packets = (window_len as u32) + total_drops;
        let drop_rate = if total_packets > 0 {
            total_drops as f32 / total_packets as f32
        } else {
            0.0
        };

        let burst_clustering = if total_drops > 0 {
            burst_drops as f32 / total_drops as f32
        } else {
            0.0
        };

        let auth_failure_rate = if window_len > 0 {
            auth_errors as f32 / window_len as f32
        } else {
            0.0
        };

        // 5. Detect sweep jamming recurrence periodicity
        let mut sweep_periodic_score = 0.0f32;
        if total_drops > 4 {
            let mut loss_intervals = [0usize; 16];
            let mut loss_count = 0;
            let mut last_drop_pos = None;

            for i in 0..window_len {
                if self.seq_gaps[i] > 0 {
                    if let Some(prev) = last_drop_pos {
                        let span = i - prev;
                        if (3..=20).contains(&span) && loss_count < 16 {
                            loss_intervals[loss_count] = span;
                            loss_count += 1;
                        }
                    }
                    last_drop_pos = Some(i);
                }
            }

            if loss_count >= 3 {
                // Check if intervals are approximately equal (+/- 1)
                let first = loss_intervals[0] as f32;
                let mut match_count = 0;
                for k in 0..loss_count {
                    if ((loss_intervals[k] as f32) - first).abs() <= 1.5 {
                        match_count += 1;
                    }
                }
                sweep_periodic_score = match_count as f32 / loss_count as f32;
            }
        }

        // 6. EW Jamming Classification & Mitigation
        let (jamming_type, confidence, remediation) = if auth_failure_rate > self.config.auth_failure_thresh {
            (
                JammingType::SpotJamming,
                0.95,
                JammingRemediation::CryptographicTamperAlarm,
            )
        } else if (drop_rate >= self.config.barrage_loss_thresh && self.smoothed_jitter_var >= 5.0)
            || drop_rate >= 0.55
            || self.smoothed_jitter_var >= self.config.barrage_jitter_var_thresh
        {
            let conf = ((drop_rate / 0.5).min(1.0) + (self.smoothed_jitter_var / 30.0).min(1.0)) * 0.5;
            (
                JammingType::BarrageJamming,
                conf.clamp(0.60, 0.99),
                JammingRemediation::EngageAdpcm4BitAndMaxFec,
            )
        } else if sweep_periodic_score > 0.60 && drop_rate > 0.05 {
            (
                JammingType::SweepJamming,
                sweep_periodic_score.clamp(0.50, 0.95),
                JammingRemediation::EngageAdpcm4BitAndMaxFec,
            )
        } else if drop_rate >= self.config.spot_loss_thresh
            && burst_clustering >= self.config.spot_burst_thresh
        {
            (
                JammingType::SpotJamming,
                burst_clustering.clamp(0.50, 0.90),
                JammingRemediation::EngageAdpcm4BitAndMaxFec,
            )
        } else {
            (JammingType::NominalRF, 1.0, JammingRemediation::None)
        };

        let remediation_active = remediation != JammingRemediation::None;
        let remediation_code = match remediation {
            JammingRemediation::None => 0,
            JammingRemediation::EngageAdpcm4BitAndMaxFec => 1,
            JammingRemediation::CryptographicTamperAlarm => 2,
        };

        self.last_telemetry = JammingTelemetry {
            jamming_type,
            confidence,
            jitter_variance_ms2: self.smoothed_jitter_var,
            mean_jitter_ms: self.smoothed_jitter_ms,
            packet_loss_rate: drop_rate,
            burst_clustering,
            auth_failure_rate,
            remediation_active,
            remediation_code,
        };

        (jamming_type, remediation)
    }

    /// Returns the latest jamming telemetry snapshot.
    pub fn telemetry(&self) -> JammingTelemetry {
        self.last_telemetry
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_jamming_nominal_channel() {
        let config = JammingDetectorConfig::default();
        let mut detector = JammingDetector::new(config);

        // Steady packets arriving at exact 16.0 ms intervals with consecutive sequence numbers
        for i in 0..64 {
            let ts = i as f64 * 16.0;
            let (jtype, rem) = detector.record_packet(ts, i as u64, true);
            if i > 10 {
                assert_eq!(jtype, JammingType::NominalRF);
                assert_eq!(rem, JammingRemediation::None);
            }
        }

        let telem = detector.telemetry();
        assert_eq!(telem.jamming_type, JammingType::NominalRF);
        assert!(telem.jitter_variance_ms2 < 1.0);
        assert_eq!(telem.packet_loss_rate, 0.0);
        assert!(!telem.remediation_active);
    }

    #[test]
    fn test_jamming_barrage_detection_on_extreme_jitter_and_loss() {
        let config = JammingDetectorConfig::default();
        let mut detector = JammingDetector::new(config);

        // Simulate barrage jamming: huge timing variance (random jitter 0..60 ms) and massive packet drops
        let mut seq = 0u64;
        let mut ts = 0.0f64;

        for i in 0..64 {
            let jitter = if i % 2 == 0 { 50.0 } else { 2.0 };
            ts += 16.0 + jitter;
            seq += 3; // Drops 2 packets every hop -> ~66% loss
            let (jtype, rem) = detector.record_packet(ts, seq, true);

            if i > 15 {
                assert_eq!(jtype, JammingType::BarrageJamming);
                assert_eq!(rem, JammingRemediation::EngageAdpcm4BitAndMaxFec);
            }
        }

        let telem = detector.telemetry();
        assert_eq!(telem.jamming_type, JammingType::BarrageJamming);
        assert!(telem.packet_loss_rate > 0.30);
        assert!(telem.remediation_active);
    }

    #[test]
    fn test_jamming_spot_detection_on_burst_clustering() {
        let config = JammingDetectorConfig::default();
        let mut detector = JammingDetector::new(config);

        let mut seq = 0u64;
        let mut ts = 0.0f64;

        // Spot jamming: steady arrival times but clustered burst drops at non-periodic intervals
        let drop_indices = [5, 11, 19, 29, 43];
        for i in 0..50 {
            ts += 16.0;
            if drop_indices.contains(&i) {
                seq += 5; // Clustered burst drop of 4 packets
            } else {
                seq += 1;
            }
            detector.record_packet(ts, seq, true);
        }

        let telem = detector.telemetry();
        assert_eq!(telem.jamming_type, JammingType::SpotJamming);
        assert!(telem.burst_clustering > 0.50);
        assert!(telem.remediation_active);
    }

    #[test]
    fn test_jamming_sweep_periodicity_detection() {
        let config = JammingDetectorConfig::default();
        let mut detector = JammingDetector::new(config);

        let mut seq = 0u64;
        let mut ts = 0.0f64;

        // Periodic drop every 6 packets (simulating radar sweep jammer rotation)
        for i in 0..48 {
            ts += 16.0;
            if i % 6 == 0 {
                seq += 2; // Single drop every 6 frames
            } else {
                seq += 1;
            }
            detector.record_packet(ts, seq, true);
        }

        let telem = detector.telemetry();
        assert_eq!(telem.jamming_type, JammingType::SweepJamming);
        assert!(telem.remediation_active);
    }

    #[test]
    fn test_jamming_cryptographic_tamper_alarm() {
        let config = JammingDetectorConfig::default();
        let mut detector = JammingDetector::new(config);

        let mut ts = 0.0f64;
        let mut seq = 0u64;

        // Ingest packets with bad auth tags
        for i in 0..30 {
            ts += 16.0;
            seq += 1;
            let auth_ok = i % 4 != 0; // 25% auth failure
            let (_jtype, rem) = detector.record_packet(ts, seq, auth_ok);

            if i > 10 && !auth_ok {
                assert_eq!(rem, JammingRemediation::CryptographicTamperAlarm);
            }
        }

        let telem = detector.telemetry();
        assert!(telem.auth_failure_rate > 0.10);
    }

    #[test]
    fn test_jamming_reset() {
        let config = JammingDetectorConfig::default();
        let mut detector = JammingDetector::new(config);

        detector.record_packet(100.0, 10, false);
        detector.reset();

        assert_eq!(detector.telemetry(), JammingTelemetry::default());
    }
}
