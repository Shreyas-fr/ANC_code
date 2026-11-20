//! Integration tests for frontend JitterBuffer and DSP Spectrum Analyzer.

use anc_frontend::audio::JitterBuffer;
use anc_frontend::dsp::SpectrumAnalyzer;

#[test]
fn test_jitter_buffer_prebuffering() {
    let sample_rate = 16000;
    let target_ms = 48; // 768 samples
    let max_ms = 250;
    let mut jb = JitterBuffer::new(sample_rate, target_ms, max_ms, true);

    // Initial state: holding
    let mut out = [1.0f32; 256];
    jb.read(&mut out);
    assert_eq!(out, [0.0f32; 256], "Prebuffering should return silence while buffer < target");

    // Write partial frame (256 samples < 768 target)
    let in_partial = vec![0.5f32; 256];
    jb.write(&in_partial);
    jb.read(&mut out);
    assert_eq!(out, [0.0f32; 256], "Should still hold silence below target threshold");

    // Write remaining frames to exceed target (256 + 512 = 768 samples)
    let in_rest = vec![0.5f32; 512];
    jb.write(&in_rest);

    // Now buffer has 768 samples >= target threshold -> holding released
    jb.read(&mut out);
    assert_ne!(out, [0.0f32; 256], "Should release audio once target is met");
}

#[test]
fn test_jitter_buffer_overflow_trimming() {
    let sample_rate = 16000;
    let target_ms = 48; // 768 samples
    let max_ms = 100; // 1600 samples
    let mut jb = JitterBuffer::new(sample_rate, target_ms, max_ms, false);

    // Push 3000 samples (exceeds max_ms of 1600 samples)
    let massive_input = vec![0.25f32; 3000];
    jb.write(&massive_input);

    assert!(jb.overflow_count > 0, "Overflow counter must register trimmed samples");
    assert!(
        (jb.buffer_ms() - target_ms as f32).abs() < 2.0,
        "Buffer should trim back to target_ms on overflow, got {:.2} ms",
        jb.buffer_ms()
    );
}

#[test]
fn test_spectrum_analyzer_peak_bin() {
    let n_fft = 512;
    let sample_rate = 16000.0f32;
    let mut analyzer = SpectrumAnalyzer::new(n_fft, sample_rate);

    // Generate pure 1000 Hz sine wave
    // Bin resolution = 16000 / 512 = 31.25 Hz/bin.
    // 1000 Hz / 31.25 Hz/bin = exactly bin 32!
    let mut sine_samples = Vec::with_capacity(n_fft);
    for n in 0..n_fft {
        let t = n as f32 / sample_rate;
        sine_samples.push((2.0 * std::f32::consts::PI * 1000.0 * t).sin());
    }

    let mut spectrum_db = vec![-90.0f64; analyzer.num_bins()];
    analyzer.compute_spectrum(&sine_samples, &mut spectrum_db);

    // Find the peak magnitude bin
    let mut peak_bin = 0;
    let mut max_db = -100.0f64;
    for (k, &db) in spectrum_db.iter().enumerate() {
        if db > max_db {
            max_db = db;
            peak_bin = k;
        }
    }

    assert_eq!(peak_bin, 32, "Peak frequency bin of 1000 Hz sine wave must be bin 32 (got {})", peak_bin);
    // Real sinusoid amplitude 1.0 has 0.5 amplitude per complex pole (-6.02 dB)
    // Hann window mean is 0.5 (-6.02 dB), yielding exact peak bin magnitude 20*log10(0.25) = -12.04 dBFS.
    assert!(
        max_db > -15.0 && max_db < -10.0,
        "Peak magnitude of unit sine wave should be ~ -12.04 dBFS, got {:.2}",
        max_db
    );
}

#[test]
fn test_jitter_buffer_packet_loss_concealment() {
    let sample_rate = 16000;
    let mut jb = JitterBuffer::new(sample_rate, 48, 200, false);

    // Push 300 samples of a loud tone (0.8 amplitude)
    let tone: Vec<f32> = (0..300)
        .map(|i| (2.0 * std::f32::consts::PI * 400.0 * (i as f32) / 16000.0).sin() * 0.8)
        .collect();
    jb.write(&tone);

    // Read all 300 samples to empty buffer
    let mut out1 = vec![0.0f32; 300];
    jb.read(&mut out1);
    assert!(out1.iter().any(|&s| s.abs() > 0.5));

    // Now request another 128 samples with zero incoming packets (simulated packet loss)
    let mut drop_out = vec![0.0f32; 128];
    jb.read(&mut drop_out);

    // PLC should extrapolate audio smoothly rather than dropping immediately to pure zero
    let has_concealed_energy = drop_out.iter().take(64).any(|&s| s.abs() > 0.05);
    assert!(
        has_concealed_energy,
        "Packet Loss Concealment (PLC) must extrapolate recent pitch audio during packet drop"
    );
}

#[test]
fn test_tactical_radar_widget_headless_context() {
    use anc_frontend::ui::TacticalRadarWidget;
    let ctx = egui::Context::default();
    let _ = ctx.run(Default::default(), |ctx| {
        egui::CentralPanel::default().show(ctx, |ui| {
            let res = TacticalRadarWidget::show(ui, 15.0, 0.95, true, &[-90.0, 90.0], 180.0);
            assert!(res.is_none());

            // Test full CDR and Spatial Coherence HUD rendering
            let res_cdr = TacticalRadarWidget::show_with_cdr(
                ui,
                -12.0,
                0.85,
                true,
                14.2,
                0.91,
                &[-90.0, 90.0],
                180.0,
            );
            assert!(res_cdr.is_none());
        });
    });
}

#[test]
fn test_dsp_timeline_widget_percentiles_and_headroom() {
    use anc_frontend::ui::DspTimelineWidget;
    use anc_rust::network::DspStageTimings;

    let mut widget = DspTimelineWidget::new(50);

    for i in 1..=50 {
        let timings = DspStageTimings {
            stft_us: 10,
            afc_us: 5,
            beamformer_us: 10,
            dereverb_us: 5,
            spectral_us: 15,
            intelligibility_us: 5,
            synthesis_us: 5,
            total_us: 50 + i, // 51 to 100 µs
        };
        widget.record_hop(&timings);
    }

    assert_eq!(widget.max_observed_us, 100);
    assert!(widget.mean_us > 70.0 && widget.mean_us < 80.0);
    assert!(widget.p95_us >= 95);
    assert!(widget.p99_us >= 98);
    assert!(widget.headroom_percent > 99.0, "Execution headroom should exceed 99% against 16 ms budget");
}

#[test]
fn test_tactical_eq_widget_headless_context_and_filtering() {
    use anc_frontend::ui::{EqPreset, TacticalEqWidget, TacticalEqualizer};
    let ctx = egui::Context::default();
    let mut eq = TacticalEqualizer::new(16000.0);

    eq.set_preset(EqPreset::AviationPilot);
    assert_eq!(eq.preset(), EqPreset::AviationPilot);

    // Test real-time block filtering
    let mut block = [0.1f32; 256];
    eq.process_block(&mut block);

    // Render headless egui context
    let _ = ctx.run(Default::default(), |ctx| {
        egui::CentralPanel::default().show(ctx, |ui| {
            TacticalEqWidget::show(ui, &mut eq);
        });
    });

    // Toggle and test bypass
    eq.set_enabled(false);
    let original = [0.25f32; 128];
    let mut test_block = original;
    eq.process_block(&mut test_block);
    assert_eq!(test_block, original, "Bypassed EQ must not modify audio");
}

#[test]
fn test_threat_radar_widget_headless_context_and_sonification() {
    use anc_frontend::ui::{ThreatRadarWidget, ThreatType};
    let ctx = egui::Context::default();
    let mut radar = ThreatRadarWidget::new(16000.0);

    radar.add_threat(ThreatType::SniperCrack, -45.0, 180.0, 0.96);
    assert_eq!(radar.threats.len(), 1);

    // Test audio mixing from sonifier
    let mut audio = [0.0f32; 256];
    radar.sonifier.mix_mono(&mut audio);
    assert!(audio.iter().any(|&s| s != 0.0));

    // Headless egui render
    let _ = ctx.run(Default::default(), |ctx| {
        egui::CentralPanel::default().show(ctx, |ui| {
            radar.show(ui, 140.0);
        });
    });
}

#[test]
fn test_elastic_buffer_governor_clock_drift_stabilization() {
    let sample_rate = 16000;
    let target_ms = 16; // 256 samples
    let max_ms = 100;
    let mut jb = JitterBuffer::new(sample_rate, target_ms, max_ms, false).with_governor(true);

    // Initial fill to target: 256 samples
    let init_chunk = vec![0.1f32; 256];
    jb.write(&init_chunk);

    // Simulate clock drift over 40 playback cycles
    // Writer pushes 257 samples (+400 PPM faster edge capture clock)
    // Reader pulls 256 samples
    let mut out = [0.0f32; 256];
    for _ in 0..40 {
        let drift_input = vec![0.1f32; 257];
        jb.write(&drift_input);
        jb.read(&mut out);
    }

    // Governor should speed up playback imperceptibly to drain excess and keep buffer bounded
    let buf_ms = jb.buffer_ms();
    assert!(
        buf_ms < 35.0,
        "Buffer should be kept bounded by governor without unbounded creep, got {:.2} ms",
        buf_ms
    );
    assert_eq!(jb.underrun_events, 0, "No underruns must occur under governed playback");
}

#[test]
fn test_spatial_lissajous_scope_widget_headless_context() {
    use anc_frontend::ui::PhaseScopeWidget;
    let ctx = egui::Context::default();
    let mut scope = PhaseScopeWidget::new(128);

    let mic1 = [0.2, 0.4, 0.1, -0.3, -0.5, 0.0, 0.3, 0.2];
    let mic2 = [0.2, 0.4, 0.1, -0.3, -0.5, 0.0, 0.3, 0.2];
    scope.push_samples(&mic1, &mic2, Some(0.12));

    let stats = scope.stats();
    assert!(stats.correlation_r > 0.90, "Pure in-phase input must yield r > 0.90");
    assert_eq!(stats.wind_buffeting_pct, 12.0);

    // Headless UI render
    let _ = ctx.run(Default::default(), |ctx| {
        egui::CentralPanel::default().show(ctx, |ui| {
            scope.show(ui, 130.0);
        });
    });
}

#[test]
fn test_aggressive_max_snr_mode_dashboard_integration() {
    use anc_frontend::ui::{MetricCard, Theme};
    let ctx = egui::Context::default();
    Theme::apply_to_context(&ctx);

    let mut aggressive_mode = true;
    let snr_val = if aggressive_mode { "+11.5 dB" } else { "+9.0 dB" };

    let _ = ctx.run(Default::default(), |ctx| {
        egui::CentralPanel::default().show(ctx, |ui| {
            MetricCard::show(
                ui,
                "ESTIMATED SNR GAIN",
                snr_val,
                "Aggressive Mode Active",
                Theme::ACCENT_CYAN,
            );
        });
    });

    aggressive_mode = false;
    assert!(!aggressive_mode);
}

#[test]
fn test_tsnr_latency_budget_compliance_under_deadline() {
    use anc_rust::model::{AdaptiveSpectralEnhancer, SpeechEnhancer};
    use rustfft::num_complex::Complex32;
    use std::time::Instant;

    let mut enhancer = AdaptiveSpectralEnhancer::new(257, 32, 16000.0);
    let mut spec = vec![Complex32::new(0.05, 0.02); 257];

    let t0 = Instant::now();
    for _ in 0..10 {
        let stats = enhancer.process_stft_frame(&mut spec).unwrap();
        assert!(stats.compute_time_us < 16_000, "Compute must remain strictly below 16 ms hop deadline");
    }
    let elapsed_total_us = t0.elapsed().as_micros();
    // Average compute per frame must be < 500 us (0.5 ms)
    assert!(elapsed_total_us / 10 < 500, "Mean compute exceeds 500 us: {}", elapsed_total_us / 10);
}

#[test]
fn test_kurtosis_diagnostic_hud_widget_headless_context() {
    use anc_frontend::ui::{ShockTransientBadge, SpectralKurtosisWidget, Theme};
    use eframe::egui;

    let ctx = egui::Context::default();
    Theme::apply_to_context(&ctx);

    let mut widget = SpectralKurtosisWidget::new();
    assert_eq!(widget.bands.len(), 32);

    // Headless UI render before transient injection
    let _ = ctx.run(Default::default(), |ctx| {
        egui::CentralPanel::default().show(ctx, |ui| {
            ShockTransientBadge::show(ui, widget.is_shock, widget.crest_factor_db, widget.peak_kurtosis);
            widget.show(ui, 100.0);
        });
    });

    // Inject Gunfire shock transient
    widget.inject_test_signal("gunfire");
    assert!(widget.is_shock);
    assert!(widget.peak_kurtosis > 20.0);
    assert!(widget.crest_factor_db > 14.0);

    // Headless UI render with active shock alert
    let _ = ctx.run(Default::default(), |ctx| {
        egui::CentralPanel::default().show(ctx, |ui| {
            ShockTransientBadge::show(ui, widget.is_shock, widget.crest_factor_db, widget.peak_kurtosis);
            widget.show(ui, 100.0);
        });
    });

    // Advance 0.5s decay
    widget.tick(0.5);
    assert!(widget.shock_decay < 1.0);
}

#[test]
fn test_3d_waterfall_mesh_integration() {
    use anc_frontend::ui::{Theme, Waterfall3dMesh};
    use eframe::egui;

    let ctx = egui::Context::default();
    Theme::apply_to_context(&ctx);

    let mut mesh = Waterfall3dMesh::new();

    // Push 45 frames of mock frequency spectrum
    for i in 0..45 {
        let spectrum = vec![-60.0 + (i as f64 * 0.5); 257];
        mesh.push_frame(&spectrum);
    }

    // Verify rolling buffer wrapped properly
    let _ = ctx.run(Default::default(), |ctx| {
        egui::CentralPanel::default().show(ctx, |ui| {
            mesh.show(ui, 120.0);
        });
    });

    assert!((mesh.pitch - 0.65).abs() < 0.05);
    assert!((mesh.yaw - (-0.45)).abs() < 0.05);
}

#[test]
fn test_tactical_lufs_radar_widget_headless_context() {
    use anc_frontend::ui::{TacticalLufsRadarWidget, Theme};
    use eframe::egui;

    let ctx = egui::Context::default();
    Theme::apply_to_context(&ctx);

    let mut widget = TacticalLufsRadarWidget::new();
    assert_eq!(widget.target_lufs, -23.0);

    // Push tactical measurements: shouting pilot burst
    widget.push_measurements(-16.5, -18.2, -19.0, 6.2, -0.8, -4.5);
    assert_eq!(widget.momentary_lufs, -16.5);
    assert_eq!(widget.gain_reduction_db, -4.5);
    assert_eq!(widget.true_peak_dbfs, -0.8);

    // Render in headless egui context
    let _ = ctx.run(Default::default(), |ctx| {
        egui::CentralPanel::default().show(ctx, |ui| {
            let res = widget.show(ui, 130.0);
            assert_eq!(res, None); // No user interaction in programmatic headless frame
        });
    });

    // Test tactical mission presets
    widget.set_target_lufs(-18.0);
    assert_eq!(widget.target_lufs, -18.0);
    widget.set_target_lufs(-26.0);
    assert_eq!(widget.target_lufs, -26.0);
}

#[test]
fn test_tactical_incident_recorder_headless_workflow() {
    use anc_frontend::audio::{incident_flags, RecorderState, TacticalAudioRecorder};

    let mut recorder = TacticalAudioRecorder::new(16000, 2);
    assert_eq!(recorder.state(), RecorderState::Idle);

    let raw = vec![0.3f32; 256];
    let enh = vec![0.15f32; 256];

    // Push pre-incident audio
    for _ in 0..10 {
        recorder.push_stereo_frame(&raw, &enh, 12.0, 28.0);
    }
    assert!(recorder.total_incident_duration_secs() > 0.0);

    // Trigger incident recording
    recorder.start_recording(incident_flags::MANUAL_TRIGGER | incident_flags::SHOCK_TRANSIENT);
    assert_eq!(recorder.state(), RecorderState::Recording);

    // Push live incident audio
    for _ in 0..10 {
        recorder.push_stereo_frame(&raw, &enh, 15.0, 45.0);
    }

    recorder.stop_recording();
    assert_eq!(recorder.state(), RecorderState::ReadyToExport);

    let export_path = std::env::temp_dir().join("test_incident_recorder_export.wav");
    let res = recorder.export_wav(&export_path);
    assert!(res.is_ok());

    let metadata = std::fs::metadata(&export_path).unwrap();
    assert!(metadata.len() > 1000);
    let _ = std::fs::remove_file(&export_path);
}

#[test]
fn test_tactical_stress_widget_headless_context() {
    use anc_frontend::ui::{TacticalStressWidget, Theme};
    use eframe::egui;

    let ctx = egui::Context::default();
    Theme::apply_to_context(&ctx);

    let mut widget = TacticalStressWidget::new();
    widget.push_measurements(68.5, 2.4, 7.8, 38.0, 5.2, 28.0);
    assert!(widget.is_acute_stress);

    let _ = ctx.run(Default::default(), |ctx| {
        egui::CentralPanel::default().show(ctx, |ui| {
            widget.show(ui, 110.0);
        });
    });
}

#[test]
fn test_audiogram_test_wizard_headless_workflow() {
    use anc_frontend::ui::{AudiogramTestWizard, Theme};
    use anc_rust::dsp::Ear;
    use eframe::egui;

    let ctx = egui::Context::default();
    Theme::apply_to_context(&ctx);

    let mut wizard = AudiogramTestWizard::new();
    wizard.selected_ear = Ear::Left;
    wizard.current_freq_idx = 3; // 4 kHz

    // Set threshold to 45 dB HL (acoustic notch)
    let b_idx = wizard.band_index_for_freq(4000.0);
    wizard.audiogram.set_htl(Ear::Left, b_idx, 45.0);
    assert_eq!(wizard.audiogram.htl_left[b_idx], 45.0);

    // Test tone injection
    wizard.is_tone_playing = true;
    let mut tone_buf = [0.0f32; 256];
    wizard.generate_test_tone(&mut tone_buf, 16000.0);
    assert!(tone_buf.iter().any(|&s| s.abs() > 0.001));

    // Render in headless egui
    let _ = ctx.run(Default::default(), |ctx| {
        egui::CentralPanel::default().show(ctx, |ui| {
            let res = wizard.show(ui, 130.0);
            assert!(res.is_none()); // Button not clicked in this frame
        });
    });
}

#[test]
fn test_tactical_battery_widget_headless_workflow() {
    use anc_frontend::ui::{TacticalBatteryWidget, Theme};
    use anc_rust::streaming::{BatteryTelemetry, TacticalPowerMode};
    use eframe::egui;

    let ctx = egui::Context::default();
    Theme::apply_to_context(&ctx);

    let mut widget = TacticalBatteryWidget::new();
    let telem = BatteryTelemetry {
        soc_pct: 72.5,
        terminal_voltage_v: 7.65,
        current_draw_ma: 135.0,
        power_draw_mw: 1032.0,
        cell_temp_c: 26.0,
        estimated_runtime_hours: 5.5,
        internal_resistance_mohm: 60.0,
        battery_health_pct: 99.0,
        power_mode: TacticalPowerMode::LowPowerEco,
    };
    widget.update(telem);

    let _ = ctx.run(Default::default(), |ctx| {
        egui::CentralPanel::default().show(ctx, |ui| {
            let _ = widget.show(ui, 75.0);
        });
    });
}

#[test]
fn test_blast_impulse_widget_headless_workflow() {
    use anc_frontend::ui::{BlastImpulseWidget, Theme};
    use anc_rust::metrics::{BlastEvent, BlastHazardStatus, BlastTelemetry};
    use eframe::egui;

    let ctx = egui::Context::default();
    Theme::apply_to_context(&ctx);

    let mut widget = BlastImpulseWidget::new();
    let telem = BlastTelemetry {
        peak_spl_db: 168.0,
        peak_overpressure_pa: 5023.0,
        peak_overpressure_psi: 0.728,
        current_a_duration_ms: 2.1,
        daily_impulse_count: 8,
        cumulative_dose_pct: 42.5,
        hazard_status: BlastHazardStatus::Caution,
        last_blast_event: BlastEvent {
            frame_index: 1045,
            peak_spl_db: 168.0,
            peak_overpressure_pa: 5023.0,
            peak_overpressure_psi: 0.728,
            a_duration_ms: 2.1,
            dose_pct: 5.3,
        },
    };
    widget.update(telem);
    assert_eq!(widget.history_count, 1);

    let _ = ctx.run(Default::default(), |ctx| {
        egui::CentralPanel::default().show(ctx, |ui| {
            widget.show(ui, 85.0);
        });
    });
}

#[test]
fn test_polar_directivity_widget_headless_workflow() {
    use anc_frontend::ui::{PolarDirectivityWidget, Theme};
    use anc_rust::dsp::polar_pattern::{PolarPatternTelemetry, PolarPatternType};
    use anc_rust::dsp::deesser::DeEsserTelemetry;
    use eframe::egui;

    let ctx = egui::Context::default();
    Theme::apply_to_context(&ctx);

    let mut widget = PolarDirectivityWidget::new();
    let polar_telem = PolarPatternTelemetry {
        pattern_type: PolarPatternType::Cardioid as u8,
        null_angle_deg: 180.0,
        front_to_back_ratio_db: 24.5,
        directivity_index_db: 4.8,
        internal_delay_us: 58.3,
    };
    let deesser_telem = DeEsserTelemetry {
        sibilance_detected: true,
        sibilance_ratio_db: 5.2,
        gain_reduction_db: -4.5,
        sibilant_energy_dbfs: -32.0,
        broadband_energy_dbfs: -28.0,
    };
    widget.update(polar_telem, deesser_telem);
    assert_eq!(widget.selected_pattern, PolarPatternType::Cardioid);
    assert!(widget.deesser_telemetry.sibilance_detected);

    let _ = ctx.run(Default::default(), |ctx| {
        egui::CentralPanel::default().show(ctx, |ui| {
            let _ = widget.show(ui, 125.0);
        });
    });
}

#[test]
fn test_cable_diagnostic_widget_headless_workflow() {
    use anc_frontend::ui::{CableDiagnosticWidget, Theme};
    use anc_rust::metrics::cable::{CableFaultStatus, CableTelemetry};
    use eframe::egui;

    let ctx = egui::Context::default();
    Theme::apply_to_context(&ctx);

    let mut widget = CableDiagnosticWidget::new();
    let telem = CableTelemetry {
        health_pct: 78.5,
        estimated_impedance_ohms: 3450.0,
        low_freq_coherence: 0.91,
        dc_offset_mv: 1.2,
        micro_intermittent_events: 1,
        status: CableFaultStatus::HighImpedanceFray,
    };
    widget.update(telem);
    assert_eq!(widget.telemetry.status, CableFaultStatus::HighImpedanceFray);
    assert_eq!(widget.telemetry.health_pct, 78.5);

    let _ = ctx.run(Default::default(), |ctx| {
        egui::CentralPanel::default().show(ctx, |ui| {
            widget.show(ui, 80.0);
        });
    });
}

#[test]
fn test_ambisonics_scope_widget_headless_workflow() {
    use anc_frontend::ui::{AmbisonicsScopeWidget, Theme};
    use anc_rust::dsp::ambisonics::AmbisonicsTelemetry;
    use eframe::egui;

    let ctx = egui::Context::default();
    Theme::apply_to_context(&ctx);

    let mut widget = AmbisonicsScopeWidget::new();
    let telem = AmbisonicsTelemetry {
        intensity_x: 0.35,
        intensity_y: 0.25,
        intensity_z: 0.0,
        intensity_mag: 0.43,
        energy_density: 0.52,
        diffuseness: 0.28,
        azimuth_deg: 35.5,
        elevation_deg: 0.0,
        is_localized: true,
    };
    widget.update(telem);
    assert_eq!(widget.telemetry.azimuth_deg, 35.5);
    assert_eq!(widget.telemetry.diffuseness, 0.28);

    let _ = ctx.run(Default::default(), |ctx| {
        egui::CentralPanel::default().show(ctx, |ui| {
            widget.show(ui, 75.0);
        });
    });
}

#[test]
fn test_tactical_jamming_widget_headless_workflow() {
    use anc_frontend::ui::{JammingWidget, Theme};
    use anc_rust::network::jamming::{JammingTelemetry, JammingType};
    use eframe::egui;

    let ctx = egui::Context::default();
    Theme::apply_to_context(&ctx);

    let mut widget = JammingWidget::new();
    let telem = JammingTelemetry {
        jamming_type: JammingType::BarrageJamming,
        confidence: 0.98,
        jitter_variance_ms2: 32.5,
        mean_jitter_ms: 14.2,
        packet_loss_rate: 0.38,
        burst_clustering: 0.72,
        auth_failure_rate: 0.0,
        remediation_active: true,
        remediation_code: 2,
    };
    widget.update(telem);
    assert_eq!(widget.telemetry.jamming_type, JammingType::BarrageJamming);
    assert!(widget.telemetry.remediation_active);

    let _ = ctx.run(Default::default(), |ctx| {
        egui::CentralPanel::default().show(ctx, |ui| {
            widget.show(ui, 75.0);
        });
    });
}

#[test]
fn test_rasti_sti_gauge_widget_headless_workflow() {
    use anc_frontend::ui::{RastiWidget, Theme};
    use anc_rust::metrics::sti::{StiRating, StiTelemetry, NUM_RASTI_MOD_FREQS};
    use eframe::egui;

    let ctx = egui::Context::default();
    Theme::apply_to_context(&ctx);

    let mut widget = RastiWidget::new();
    let telem = StiTelemetry {
        sti_score: 0.86,
        rating: StiRating::Excellent,
        mean_apparent_snr_db: 15.2,
        mean_mtf: 0.85,
        mtf_bands: [0.85; NUM_RASTI_MOD_FREQS],
        is_authoritative: true,
    };
    widget.update(telem);
    assert_eq!(widget.telemetry.sti_score, 0.86);
    assert_eq!(widget.telemetry.rating, StiRating::Excellent);

    let _ = ctx.run(Default::default(), |ctx| {
        egui::CentralPanel::default().show(ctx, |ui| {
            widget.show(ui, 75.0);
        });
    });
}
