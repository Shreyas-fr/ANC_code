//! Tests for network protocol and receiver state tracking.

use anc_rust::network::{AudioPacket, EdgeTelemetry, AUDIO_FRAME_SAMPLES, AUDIO_PACKET_BYTES};
use anc_frontend::network::StreamStats;

#[test]
fn test_audio_packet_roundtrip() {
    let mut original_samples = [0.0f32; AUDIO_FRAME_SAMPLES];
    for (i, s) in original_samples.iter_mut().enumerate() {
        *s = (i as f32 * 0.05).sin();
    }

    let packet = AudioPacket::new(42001, original_samples);

    let serialized = packet.serialize();
    assert_eq!(serialized.len(), AUDIO_PACKET_BYTES);

    let deserialized = AudioPacket::deserialize(&serialized).expect("Deserialization must succeed");
    assert_eq!(deserialized.sequence, 42001);
    for (&d_samp, &o_samp) in deserialized.samples.iter().zip(original_samples.iter()) {
        assert!((d_samp - o_samp).abs() < 1e-6);
    }
}

#[test]
fn test_audio_packet_with_fec_roundtrip() {
    let mut original_samples = [0.0f32; AUDIO_FRAME_SAMPLES];
    let mut parity_samples = [0.0f32; AUDIO_FRAME_SAMPLES];
    for (i, s) in original_samples.iter_mut().enumerate() {
        *s = (i as f32 * 0.05).sin();
        parity_samples[i] = (i as f32 * 0.10).cos();
    }

    let packet = AudioPacket::new_with_fec(
        100,
        original_samples,
        98,
        2,
        parity_samples,
    );

    let serialized = packet.serialize();
    assert_eq!(serialized.len(), anc_rust::network::FEC_PACKET_TOTAL_BYTES);

    let deserialized = AudioPacket::deserialize(&serialized).expect("FEC Deserialization must succeed");
    assert_eq!(deserialized.sequence, 100);
    assert_eq!(deserialized.fec_base_seq, Some(98));
    assert_eq!(deserialized.fec_window, 2);
    assert!(deserialized.fec_parity.is_some());
    let des_parity = deserialized.fec_parity.unwrap();
    for i in 0..AUDIO_FRAME_SAMPLES {
        assert_eq!(des_parity[i].to_bits(), parity_samples[i].to_bits());
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
        talker_angle_deg: 12.5,
        doa_confidence: 0.94,
        mean_cdr_db: 14.2,
        spatial_coherence: 0.89,
        speech_intelligibility_index: 0.88,
        intelligibility_gain_db: 3.4,
        fec_recovery_rate: 100.0,
        rf_link_health: 100.0,
        wind_turbulence_index: 0.12,
        wind_detected: false,
        glottal_crest_factor: 3.8,
        estimated_snr_gain_db: 9.0,
        aggressive_snr_active: false,
        momentary_lufs: -22.5,
        short_term_lufs: -23.1,
        integrated_lufs: -23.0,
        loudness_range_lu: 4.2,
        true_peak_dbfs: -2.8,
        lufs_gain_reduction_db: -0.6,
        res_echo_suppression_db: 15.2,
        total_erle_db: 28.5,
        mic_cal_mismatch_db: 0.2,
        mic_clog_detected: false,
        tactical_stress_index: 24.5,
        vocal_jitter_pct: 0.72,
        vocal_shimmer_pct: 2.8,
        lombard_strain_index: 0.15,
        howling_detected: false,
        howling_suppression_db: 0.0,
        battery_soc_pct: 88.5,
        battery_voltage_v: 7.78,
        battery_runtime_hours: 7.2,
        battery_power_mw: 980.0,
        blast_overpressure_pa: 12.5,
        blast_overpressure_psi: 0.0018,
        blast_daily_dose_pct: 2.5,
        bone_fusion_active: true,
        audiogram_wdrc_gain_db: 4.5,
        deesser_gain_reduction_db: -3.2,
        deesser_sibilance_ratio_db: 4.5,
        deesser_active: true,
        polar_pattern_type: 1,
        polar_null_angle_deg: 180.0,
        polar_front_to_back_ratio_db: 24.5,
        thermal_noise_floor_dbfs: -92.5,
        preamp_temperature_c: 42.0,
        cable_impedance_ohms: 2200.0,
        cable_health_pct: 100.0,
        cable_fault_status: 0,
        spectral_contrast_db: 5.4,
        spectral_contrast_gamma: 0.25,
        ambisonics_intensity_mag: 0.45,
        ambisonics_diffuseness: 0.22,
        ambisonics_azimuth_deg: 18.0,
        jamming_type: 0,
        jamming_confidence: 1.0,
        rf_jitter_var_ms2: 0.8,
        packet_burst_clustering: 0.05,
        rasti_sti_score: 0.82,
        rasti_rating: 4,
        stage_timings: anc_rust::network::DspStageTimings {
            stft_us: 14,
            afc_us: 6,
            beamformer_us: 12,
            dereverb_us: 8,
            spectral_us: 18,
            intelligibility_us: 6,
            synthesis_us: 10,
            total_us: 74,
        },
    };

    let json_str = serde_json::to_string(&telemetry).expect("JSON serialization must succeed");
    let parsed: EdgeTelemetry = serde_json::from_str(&json_str).expect("JSON deserialization must succeed");

    assert_eq!(parsed.frame, 1050);
    assert_eq!(parsed.model, "Track1-FrozenEnsemble");
    assert!((parsed.total_latency_ms - 16.01).abs() < 1e-4);
    assert!((parsed.avg_rtf - 0.0003).abs() < 1e-5);
    assert_eq!(parsed.momentary_lufs, -22.5);
    assert_eq!(parsed.short_term_lufs, -23.1);
    assert_eq!(parsed.integrated_lufs, -23.0);
    assert_eq!(parsed.res_echo_suppression_db, 15.2);
    assert!(!parsed.mic_clog_detected);
    assert!(parsed.deesser_active);
    assert_eq!(parsed.deesser_gain_reduction_db, -3.2);
    assert_eq!(parsed.polar_pattern_type, 1);
    assert_eq!(parsed.polar_null_angle_deg, 180.0);
    assert_eq!(parsed.cable_impedance_ohms, 2200.0);
    assert_eq!(parsed.cable_health_pct, 100.0);
    assert_eq!(parsed.cable_fault_status, 0);
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
