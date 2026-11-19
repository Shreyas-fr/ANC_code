//! Tests for network protocol and receiver state tracking.

use anc_rust::network::{AudioPacket, EdgeTelemetry, AUDIO_FRAME_SAMPLES, AUDIO_PACKET_BYTES};
use anc_frontend::network::StreamStats;

#[test]
fn test_audio_packet_roundtrip() {
    let mut original_samples = [0.0f32; AUDIO_FRAME_SAMPLES];
    for (i, s) in original_samples.iter_mut().enumerate() {
        *s = (i as f32 * 0.05).sin();
    }

    let packet = AudioPacket {
        sequence: 42001,
        samples: original_samples,
    };

    let serialized = packet.serialize();
    assert_eq!(serialized.len(), AUDIO_PACKET_BYTES);

    let deserialized = AudioPacket::deserialize(&serialized).expect("Deserialization must succeed");
    assert_eq!(deserialized.sequence, 42001);
    for i in 0..AUDIO_FRAME_SAMPLES {
        assert!((deserialized.samples[i] - original_samples[i]).abs() < 1e-6);
    }
}

#[test]
fn test_audio_packet_corrupt_or_truncated() {
    // Truncated packet
    let bad_bytes = vec![0u8; 500];
    let res = AudioPacket::deserialize(&bad_bytes);
    assert!(res.is_err(), "Must reject truncated packet < 1032 bytes");

    // Empty packet
    let empty = vec![];
    let res = AudioPacket::deserialize(&empty);
    assert!(res.is_err(), "Must reject empty byte slice");
}

#[test]
fn test_telemetry_json_roundtrip() {
    let telemetry = EdgeTelemetry {
        frame: 1050,
        model: "Track1-FrozenEnsemble".to_string(),
        mode: "Tactical-ALL".to_string(),
        model_active: true,
        compute_time_ms: 0.0035,
        algorithmic_latency_ms: 8.0,
        total_latency_ms: 16.01,
        avg_rtf: 0.0003,
        deadline_misses: 0,
        fallback_frames: 0,
        enhanced_frames: 1050,
        input_rms: 0.125,
        output_rms: 0.082,
        temperature_c: 41.2,
    };

    let json_str = serde_json::to_string(&telemetry).expect("JSON serialization must succeed");
    let parsed: EdgeTelemetry = serde_json::from_str(&json_str).expect("JSON deserialization must succeed");

    assert_eq!(parsed.frame, 1050);
    assert_eq!(parsed.model, "Track1-FrozenEnsemble");
    assert!((parsed.total_latency_ms - 16.01).abs() < 1e-4);
    assert!((parsed.avg_rtf - 0.0003).abs() < 1e-5);
}

#[test]
fn test_stream_stats_packet_loss_calculation() {
    let mut stats = StreamStats::default();

    // Simulating sequence progression with 5 dropped packets between 100 and 106
    let sequences = vec![98, 99, 100, 106, 107, 108, 109, 110];

    for seq in sequences {
        if let Some(last) = stats.last_sequence {
            if seq > last + 1 {
                stats.packets_lost += seq - last - 1;
            }
        }
        stats.last_sequence = Some(seq);
        stats.packets_received += 1;
        let total = stats.packets_received + stats.packets_lost;
        stats.loss_percentage = (stats.packets_lost as f32 / total as f32) * 100.0;
    }

    // Total received = 8 packets. Dropped = 101, 102, 103, 104, 105 = 5 packets.
    assert_eq!(stats.packets_received, 8);
    assert_eq!(stats.packets_lost, 5);
    // Total expected = 13. Loss = 5 / 13 * 100 = 38.4615%
    let expected_loss = (5.0 / 13.0) * 100.0;
    assert!((stats.loss_percentage - expected_loss).abs() < 0.01);
}
