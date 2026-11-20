//! End-to-end integration tests for TacticalAncPipeline.
#![allow(clippy::needless_range_loop, clippy::chunks_exact_to_as_chunks)]

use anc_rust::dsp::{AfcConfig, MvdrConfig, PhaseAlignConfig, PhaseAlignmentProfile, WindowType};
use anc_rust::metrics::snr::compute_si_sdr;
use anc_rust::model::{AdaptiveSpectralEnhancer, TractEnhancer};
use anc_rust::streaming::{PipelineConfig, TacticalAncPipeline};
use std::f32::consts::PI;

#[test]
fn test_end_to_end_pipeline_stability_and_snr_gain() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        window_type: WindowType::AsymmetricLowLatency,
        enable_mvdr: true,
        enable_agc: true,
        enable_limiter: true,
        mvdr_config: MvdrConfig {
            num_bins,
            sample_rate,
            mic_distance_m: 0.03, // 30 mm
            speed_of_sound_m_s: 343.0,
            target_angle_deg: 0.0,
            alpha: 0.95,
            diag_loading_eps: 1e-3,
            enable_spp_vad: true,
            spp_threshold: 0.35,
            weight_smoothing: 0.50,
            ..Default::default()
        },
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);

    // Synthesize target speech from broadside (0 deg)
    // Harmonics: 300 Hz, 600 Hz, 1200 Hz
    let total_hops = 150;
    let total_samples = total_hops * hop_size;

    let mut clean_speech = Vec::with_capacity(total_samples);
    for n in 0..total_samples {
        let t = n as f32 / sample_rate;
        let s = 0.3 * (2.0 * PI * 300.0 * t).sin()
            + 0.2 * (2.0 * PI * 600.0 * t).sin()
            + 0.1 * (2.0 * PI * 1200.0 * t).sin();
        clean_speech.push(s);
    }

    // Directional noise from endfire (90 deg)
    // Array spacing 30 mm => delta_t = 0.03 / 343 = 8.746e-5 s => 1.399 samples @ 16 kHz
    let noise_delay_samples = (0.03 / 343.0) * sample_rate;
    let mut noise_m1 = Vec::with_capacity(total_samples);
    let mut noise_m2 = Vec::with_capacity(total_samples);

    for n in 0..total_samples {
        let t1 = n as f32 / sample_rate;
        let t2 = (n as f32 - noise_delay_samples) / sample_rate;
        // Directional high-frequency siren noise (2500 Hz + 4000 Hz)
        let n1 = 0.4 * (2.0 * PI * 2500.0 * t1).sin() + 0.3 * (2.0 * PI * 4000.0 * t1).sin();
        let n2 = 0.4 * (2.0 * PI * 2500.0 * t2).sin() + 0.3 * (2.0 * PI * 4000.0 * t2).sin();
        noise_m1.push(n1);
        noise_m2.push(n2);
    }

    // Mix noisy inputs
    let mut noisy_mic1 = Vec::with_capacity(total_samples);
    let mut noisy_mic2 = Vec::with_capacity(total_samples);
    for n in 0..total_samples {
        noisy_mic1.push(clean_speech[n] + noise_m1[n]);
        noisy_mic2.push(clean_speech[n] + noise_m2[n]);
    }

    let mut enhanced_output = Vec::with_capacity(total_samples);
    let mut hop_out = vec![0.0f32; hop_size];

    // Stream through pipeline hop-by-hop
    for h in 0..total_hops {
        let start = h * hop_size;
        let end = start + hop_size;
        let m1_chunk = &noisy_mic1[start..end];
        let m2_chunk = &noisy_mic2[start..end];

        let _stats = pipeline
            .process_hop(m1_chunk, Some(m2_chunk), &mut model, &mut hop_out)
            .expect("Hop processing must succeed");

        // Verify no NaNs or Infs
        for &s in &hop_out {
            assert!(s.is_finite(), "Output sample must be finite, got {}", s);
            assert!(
                s.abs() <= 1.0,
                "Limiter must clamp samples to [-1, 1], got {}",
                s
            );
        }

        enhanced_output.extend_from_slice(&hop_out);
    }

    assert_eq!(enhanced_output.len(), total_samples);

    // Evaluate input vs output SI-SDR after convergence (> hop 20)
    // Account for causal overlap-add framing delay (exactly 1 hop = 256 samples)
    let delay = hop_size;
    let eval_start = 25 * hop_size;
    let eval_end = total_samples - delay;

    let eval_clean = &clean_speech[eval_start..eval_end];
    let eval_noisy = &noisy_mic1[eval_start..eval_end];
    let eval_enhanced = &enhanced_output[(eval_start + delay)..(eval_end + delay)];

    let input_si_sdr = compute_si_sdr(eval_clean, eval_noisy);
    let output_si_sdr = compute_si_sdr(eval_clean, eval_enhanced);

    println!(
        "Integration Test: Input SI-SDR = {:.2} dB -> Enhanced SI-SDR = {:.2} dB (Gain = +{:.2} dB)",
        input_si_sdr, output_si_sdr, output_si_sdr - input_si_sdr
    );

    // Enhanced audio must improve SI-SDR over the noisy input
    assert!(
        output_si_sdr > input_si_sdr,
        "Enhanced SI-SDR ({:.2} dB) must exceed Input SI-SDR ({:.2} dB)",
        output_si_sdr,
        input_si_sdr
    );
}

#[test]
fn test_pipeline_reset_and_reproducibility() {
    let config = PipelineConfig::default();
    let mut pipeline = TacticalAncPipeline::new(config.clone());
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", 257, 32);

    let hop_in = vec![0.25f32; 256];
    let mut out1 = vec![0.0f32; 256];
    let mut out2 = vec![0.0f32; 256];

    // Process a hop
    pipeline
        .process_hop(&hop_in, None, &mut model, &mut out1)
        .unwrap();

    // Reset pipeline
    pipeline.reset();

    // Process the exact same initial hop
    pipeline
        .process_hop(&hop_in, None, &mut model, &mut out2)
        .unwrap();

    for i in 0..256 {
        assert!(
            (out1[i] - out2[i]).abs() < 1e-6,
            "Reset must return pipeline to identical initial deterministic state"
        );
    }
}

#[test]
fn test_dynamic_mission_profile_switching() {
    use anc_rust::model::AdaptiveSpectralEnhancer;
    use anc_rust::streaming::MissionProfile;

    let config = PipelineConfig::default();
    let mut pipeline = TacticalAncPipeline::new(config);
    let mut enhancer = AdaptiveSpectralEnhancer::new(257, 32, 16000.0);

    // Initial default profile is CombatVehicle
    assert_eq!(pipeline.active_profile(), MissionProfile::CombatVehicle);

    // Switch to CommandPost (enclosed bunker)
    pipeline.set_mission_profile(MissionProfile::CommandPost, Some(&mut enhancer));
    assert_eq!(pipeline.active_profile(), MissionProfile::CommandPost);
    assert!(
        pipeline.config.enable_dereverb,
        "Command post profile must activate WPE dereverberation"
    );
    assert!(
        !pipeline.config.enable_transient_blanker,
        "Command post profile should disable impulsive concussion blanker"
    );

    // Switch to DismountedInfantry (situational awareness)
    pipeline.set_mission_profile(MissionProfile::DismountedInfantry, Some(&mut enhancer));
    assert_eq!(
        pipeline.active_profile(),
        MissionProfile::DismountedInfantry
    );
    assert!(
        !pipeline.config.enable_dereverb,
        "Dismounted infantry profile should not run dereverberation"
    );
    assert!(
        pipeline.config.enable_transient_blanker,
        "Dismounted infantry profile must enable concussion blanker for gunfire"
    );
}

#[test]
fn test_pipeline_online_doa_tracking_and_headset_slip_compensation() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        window_type: WindowType::Hann,
        enable_mvdr: true,
        enable_doa_tracking: true, // Activate online talker tracking
        enable_agc: true,
        enable_limiter: true,
        mvdr_config: MvdrConfig {
            num_bins,
            sample_rate,
            mic_distance_m: 0.03,
            ..Default::default()
        },
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);

    // Operator headset has slipped to +25 degrees
    let target_slip_deg = 25.0f32;
    let slip_rad = target_slip_deg * PI / 180.0;
    let delta_t = (0.03 * slip_rad.sin()) / 343.0;

    let total_hops = 60;
    let mut hop_out = vec![0.0f32; hop_size];

    for h in 0..total_hops {
        let mut m1 = vec![0.0f32; hop_size];
        let mut m2 = vec![0.0f32; hop_size];

        for n in 0..hop_size {
            let sample_idx = h * hop_size + n;
            let t1 = sample_idx as f32 / sample_rate;
            let t2 = (sample_idx as f32 - delta_t * sample_rate) / sample_rate;
            // Rich wideband multi-harmonic speech (200 Hz fundamental + harmonics up to 2.4 kHz)
            let mut s1 = 0.0f32;
            let mut s2 = 0.0f32;
            for m in 1..=12 {
                let f = 200.0 * m as f32;
                let amp = 0.25 / (m as f32).sqrt();
                s1 += amp * (2.0 * PI * f * t1).sin();
                s2 += amp * (2.0 * PI * f * t2).sin();
            }
            m1[n] = s1;
            m2[n] = s2;
        }

        pipeline
            .process_hop(&m1, Some(&m2), &mut model, &mut hop_out)
            .unwrap();
    }

    let tracked = pipeline.tracked_talker_angle_deg();
    println!(
        "Pipeline Tracked Angle for +25 deg target: {:.2} deg",
        tracked
    );
    assert!(
        (tracked - target_slip_deg).abs() < 15.0,
        "Online DOA tracking should adapt to slipped headset (+25 deg), got {:.2} deg",
        tracked
    );
    assert!(pipeline.doa_confidence() > 0.1);
}

#[test]
fn test_pipeline_coupled_dereverb_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        window_type: WindowType::Hann,
        enable_mvdr: true,
        enable_dereverb: true, // Joint multi-channel coupled dereverberator active
        enable_agc: true,
        enable_limiter: true,
        mvdr_config: MvdrConfig {
            num_bins,
            sample_rate,
            mic_distance_m: 0.03,
            ..Default::default()
        },
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);

    let m1 = vec![0.2f32; hop_size];
    let m2 = vec![0.15f32; hop_size];
    let mut out = vec![0.0f32; hop_size];

    // Stream 20 hops to verify stability and absence of NaNs / infinities
    for _ in 0..20 {
        pipeline
            .process_hop(&m1, Some(&m2), &mut model, &mut out)
            .unwrap();
        for &s in &out {
            assert!(s.is_finite());
            assert!(s.abs() <= 1.0);
        }
    }
}

#[test]
fn test_pipeline_subband_dual_beamforming_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        window_type: WindowType::Hann,
        enable_mvdr: true,
        enable_agc: true,
        enable_limiter: true,
        mvdr_config: MvdrConfig {
            num_bins,
            sample_rate,
            mic_distance_m: 0.03,
            split_freq_hz: 1800.0,
            enable_subband_dual_beamforming: true,
            ..Default::default()
        },
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);

    let m1 = vec![0.15f32; hop_size];
    let m2 = vec![0.12f32; hop_size];
    let mut out = vec![0.0f32; hop_size];

    for _ in 0..30 {
        let stats = pipeline
            .process_hop(&m1, Some(&m2), &mut model, &mut out)
            .unwrap();
        assert!(
            stats.compute_time_us < 50_000,
            "Compute must remain well under real-time deadline"
        );
        for &s in &out {
            assert!(s.is_finite());
        }
    }
}

#[test]
fn test_pipeline_comfort_noise_combat_profile_integration() {
    use anc_rust::model::AdaptiveSpectralEnhancer;
    use anc_rust::streaming::MissionProfile;

    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        window_type: WindowType::Hann,
        enable_mvdr: true,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut spectral_enhancer = AdaptiveSpectralEnhancer::new(num_bins, 32, sample_rate);

    // Switch mission profile to CombatVehicle (T-90 / BMP cabin profile)
    pipeline.set_mission_profile(MissionProfile::CombatVehicle, Some(&mut spectral_enhancer));
    assert!(pipeline.active_profile().enable_comfort_noise());

    let silent_mic1 = vec![0.0f32; hop_size];
    let silent_mic2 = vec![0.0f32; hop_size];
    let mut out = vec![0.0f32; hop_size];

    // Process silent frames: comfort noise should be blended in to prevent acoustic vacuum
    for _ in 0..25 {
        pipeline
            .process_hop(
                &silent_mic1,
                Some(&silent_mic2),
                &mut spectral_enhancer,
                &mut out,
            )
            .unwrap();
        for &s in &out {
            assert!(s.is_finite());
        }
    }
}

#[test]
fn test_pipeline_alsa_mmap_direct_integration() {
    use anc_rust::streaming::{AlsaMmapConfig, AlsaMmapSimulator};

    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        window_type: WindowType::AsymmetricLowLatency,
        enable_mvdr: true,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);

    let alsa_config = AlsaMmapConfig {
        sample_rate,
        channels: 2,
        period_size: hop_size,
        periods: 2,
        ..Default::default()
    };
    let mut alsa_sim = AlsaMmapSimulator::new(alsa_config);

    // Run 20 periods through ALSA zero-copy MMAP simulator connected to TacticalAncPipeline
    let mut mic1_scratch = vec![0.0f32; hop_size];
    let mut mic2_scratch = vec![0.0f32; hop_size];
    let mut mono_out = vec![0.0f32; hop_size];

    let report = alsa_sim.run_hil_simulation(20, |capture_slice, playback_slice| {
        let t0 = std::time::Instant::now();

        // De-interleave zero-copy capture slice
        for f in 0..hop_size {
            mic1_scratch[f] = capture_slice[f * 2];
            mic2_scratch[f] = capture_slice[f * 2 + 1];
        }

        pipeline
            .process_hop(
                &mic1_scratch,
                Some(&mic2_scratch),
                &mut model,
                &mut mono_out,
            )
            .unwrap();

        // Duplicate mono enhanced output to stereo playback slice
        for f in 0..hop_size {
            playback_slice[f * 2] = mono_out[f];
            playback_slice[f * 2 + 1] = mono_out[f];
        }

        t0.elapsed().as_micros() as f32
    });

    assert_eq!(
        report.total_xruns, 0,
        "Pipeline with ALSA MMAP should have zero XRUNs"
    );
    assert_eq!(report.total_periods, 20);
    assert!(report.dma_throughput_mb_s > 0.1);
}

#[test]
fn test_pipeline_subband_afc_speaker_cancellation_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        window_type: WindowType::Hann,
        enable_mvdr: true,
        enable_afc: true,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);

    let total_hops = 50;
    let mut out = vec![0.0f32; hop_size];

    // Loudspeaker plays radio transmission: 400 Hz tone
    // Feedback path couples 40% into mic 1 and 30% into mic 2
    for h in 0..total_hops {
        let mut spk = vec![0.0f32; hop_size];
        let mut m1 = vec![0.0f32; hop_size];
        let mut m2 = vec![0.0f32; hop_size];

        for n in 0..hop_size {
            let t = (h * hop_size + n) as f32 / sample_rate;
            let radio = 0.5 * (2.0 * PI * 400.0 * t).sin();
            spk[n] = radio;
            m1[n] = 0.4 * radio;
            m2[n] = 0.3 * radio;
        }

        pipeline
            .process_hop_tactical(&m1, Some(&m2), Some(&spk), &mut model, &mut out)
            .expect("AFC hop processing must succeed");
    }

    let stats = pipeline.afc_stats();
    assert!(
        stats.erle_mic1_db > 5.0,
        "Subband AFC should achieve positive ERLE (> 5 dB), got {:.2} dB",
        stats.erle_mic1_db
    );
    let timings = pipeline.stage_timings();
    assert!(timings.total_us > 0, "Execution timings must be populated");
}

#[test]
fn test_pipeline_transparency_concussive_hearing_protection_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        window_type: WindowType::Hann,
        enable_mvdr: true,
        enable_transparency: true,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);

    let mut out = vec![0.0f32; hop_size];
    let safe_limit = 10.0f32.powf(-12.0 / 20.0); // 0.2512 linear limit

    // Hop 0-5: quiet ambient sound
    for _ in 0..5 {
        let ambient = vec![0.02f32; hop_size];
        pipeline
            .process_hop(&ambient, Some(&ambient), &mut model, &mut out)
            .unwrap();
    }

    // Hop 6: loud concussive explosion impulse (+6.0 amplitude)
    let mut blast_m1 = vec![0.02f32; hop_size];
    let mut blast_m2 = vec![0.02f32; hop_size];
    blast_m1[10] = 6.0;
    blast_m1[11] = -5.5;
    blast_m2[10] = 5.8;

    pipeline
        .process_hop(&blast_m1, Some(&blast_m2), &mut model, &mut out)
        .unwrap();

    // Verify all output samples are strictly clamped within the calibrated safe hearing limit
    for (i, &s) in out.iter().enumerate() {
        assert!(
            s.abs() <= safe_limit + 1e-4,
            "Sample {} exceeded hearing safe limit: val={}, limit={}",
            i,
            s,
            safe_limit
        );
    }
}

#[test]
fn test_pipeline_cdr_diffuse_field_suppression_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        window_type: WindowType::Hann,
        enable_mvdr: true,
        enable_cdr: true,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);

    let mut out = vec![0.0f32; hop_size];

    // Feed directional coherent speech (identical signals on M1 and M2)
    for h in 0..40 {
        let mut m1 = vec![0.0f32; hop_size];
        for n in 0..hop_size {
            let t = (h * hop_size + n) as f32 / sample_rate;
            m1[n] = 0.5 * (2.0 * PI * 350.0 * t).sin();
        }
        pipeline
            .process_hop(&m1, Some(&m1), &mut model, &mut out)
            .unwrap();
    }

    assert!(
        pipeline.mean_coherence() > 0.90,
        "Coherent speech must have high spatial coherence, got {}",
        pipeline.mean_coherence()
    );
    assert!(
        pipeline.mean_cdr_db() > 8.0,
        "Coherent speech CDR must be > 8 dB, got {:.2} dB",
        pipeline.mean_cdr_db()
    );
}

#[test]
fn test_pipeline_crn_int8_postfilter_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        window_type: WindowType::Hann,
        enable_mvdr: true,
        enable_crn_postfilter: true,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);

    let mut out = vec![0.0f32; hop_size];
    let m1 = vec![0.2f32; hop_size];

    for _ in 0..10 {
        let res = pipeline.process_hop(&m1, Some(&m1), &mut model, &mut out);
        assert!(res.is_ok(), "CRN-INT8 pipeline process_hop must succeed");
    }

    // Verify non-zero enhanced output with zero allocations
    assert!(out.iter().any(|&s| s.abs() > 0.01));
}

#[test]
fn test_pipeline_transaural_xtc_spatial_positioning_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        window_type: WindowType::Hann,
        enable_mvdr: true,
        enable_xtc: true,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);

    let mono_threat = vec![0.5f32; hop_size];
    let mut stereo_out = vec![0.0f32; hop_size * 2];

    // Position a directional threat alert (e.g. incoming fire) at +60 degrees
    pipeline
        .xtc
        .position_source_3d(&mono_threat, 60.0, &mut stereo_out);

    // Right channel (ipsilateral) must be stronger than left channel (contralateral)
    let left_energy: f32 = stereo_out.chunks_exact(2).map(|c| c[0] * c[0]).sum();
    let right_energy: f32 = stereo_out.chunks_exact(2).map(|c| c[1] * c[1]).sum();

    assert!(
        right_energy > left_energy,
        "Source at +60 deg must have higher energy on right ear: R={}, L={}",
        right_energy,
        left_energy
    );
}

#[test]
fn test_pipeline_intelligibility_enhancer_combat_profile_activation() {
    use anc_rust::streaming::MissionProfile;

    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        window_type: WindowType::Hann,
        enable_mvdr: true,
        enable_intelligibility: false, // Default is false for transparent benchmarks
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);

    assert!(
        !pipeline.intelligibility.is_enabled(),
        "Intelligibility enhancer must be disabled by default"
    );

    // Switch mission profile to CombatVehicle (T-90 / BMP)
    pipeline.set_mission_profile(MissionProfile::CombatVehicle, Some(&mut model));
    assert!(
        pipeline.config.enable_intelligibility,
        "CombatVehicle profile must enable intelligibility enhancer"
    );
    assert!(pipeline.intelligibility.is_enabled());

    // Stream low-frequency cabin rumble (100 Hz) + F2 speech formant (2000 Hz) + DC bias (0.2)
    let mut out = vec![0.0f32; hop_size];
    let mut m1 = vec![0.0f32; hop_size];

    for h in 0..30 {
        for i in 0..hop_size {
            let t = (h * hop_size + i) as f32 / sample_rate;
            let rumble = 0.5 * (2.0 * PI * 100.0 * t).sin();
            let formant = 0.3 * (2.0 * PI * 2000.0 * t).sin();
            let dc = 0.15;
            m1[i] = rumble + formant + dc;
        }

        let res = pipeline.process_hop(&m1, Some(&m1), &mut model, &mut out);
        assert!(
            res.is_ok(),
            "Process hop with Intelligibility Enhancer must succeed"
        );

        for &s in &out {
            assert!(s.is_finite());
            assert!(s.abs() <= 1.0, "Sample breached +/-1.0 boundary: {}", s);
        }
    }

    // Verify positive Speech Intelligibility Index and gain
    assert!(pipeline.current_sii() > 0.0, "Current SII must be positive");
    assert!(pipeline.intelligibility_gain_db().is_finite());
}

#[test]
fn test_pipeline_fec_burst_loss_recovery_integration() {
    use anc_rust::network::{AudioPacket, FecDecoder, FecEncoder, AUDIO_FRAME_SAMPLES};

    let mut encoder = FecEncoder::new(2);
    let mut decoder = FecDecoder::new();

    let mut stream_packets = Vec::new();
    for seq in 0..20 {
        let mut samples = [0.0f32; AUDIO_FRAME_SAMPLES];
        for (i, s) in samples.iter_mut().enumerate() {
            *s = ((seq as f32 * 0.2) + (i as f32 * 0.05)).sin();
        }
        let pkt = encoder.encode(seq, samples);
        stream_packets.push(pkt);
    }

    let mut rec_buf = [
        AudioPacket::new(0, [0.0; AUDIO_FRAME_SAMPLES]),
        AudioPacket::new(0, [0.0; AUDIO_FRAME_SAMPLES]),
    ];

    let mut all_delivered = Vec::new();

    // Stream through channel with simulated burst losses at sequence 4 and sequence 11
    for pkt in &stream_packets {
        if pkt.sequence == 4 || pkt.sequence == 11 {
            // Drop packet! (Simulate RF burst drop)
            continue;
        }

        let n_rec = decoder.process_packet(pkt, &mut rec_buf);
        for rec_pkt in rec_buf.iter().take(n_rec) {
            all_delivered.push(rec_pkt.clone());
        }
        all_delivered.push(pkt.clone());
    }

    // Both dropped packets (seq 4 and seq 11) must be recovered
    assert_eq!(decoder.stats.packets_lost, 2);
    assert_eq!(decoder.stats.packets_recovered, 2);
    assert_eq!(decoder.stats.recovery_rate, 100.0);
    assert_eq!(decoder.stats.rf_link_health, 100.0);

    // Verify all 20 packets delivered in sequential order
    assert_eq!(all_delivered.len(), 20);
    for (i, p) in all_delivered.iter().enumerate() {
        assert_eq!(p.sequence, i as u64, "Sequence mismatch at index {}", i);
    }
}

#[test]
fn test_pipeline_pitch_comb_and_dither_integration() {
    use anc_rust::dsp::DitherMode;
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_pitch_comb: true,
        dither_mode: DitherMode::TpdfLipshitz,
        enable_blackbox: true,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);

    let hops = 30;
    let total_samples = hops * hop_size;

    // Harmonic speech tone F0 = 160 Hz + non-harmonic 700 Hz mechanical whine
    let mut mic1 = Vec::with_capacity(total_samples);
    for n in 0..total_samples {
        let t = n as f32 / sample_rate;
        let speech = 0.5 * (2.0 * PI * 160.0 * t).sin() + 0.25 * (2.0 * PI * 320.0 * t).sin();
        let whine = 0.2 * (2.0 * PI * 700.0 * t).sin();
        mic1.push(speech + whine);
    }

    let mut hop_out = vec![0.0f32; hop_size];
    let mut i16_out = vec![0i16; hop_size];

    for h in 0..hops {
        let chunk = &mic1[h * hop_size..(h + 1) * hop_size];
        let res = pipeline.process_hop(chunk, None, &mut model, &mut hop_out);
        assert!(res.is_ok());

        pipeline.quantize_output_i16(&hop_out, &mut i16_out);
        assert_eq!(i16_out.len(), hop_size);
    }

    // After warm-up, pitch tracker should detect voiced speech near 160 Hz
    assert!(pipeline.pitch_is_voiced());
    assert!((pipeline.pitch_f0() - 160.0).abs() < 10.0);

    // Verify blackbox recorded all 30 hops
    assert_eq!(pipeline.blackbox().count(), 30);
}

#[test]
fn test_pipeline_blackbox_forensic_incident_recording_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_blackbox: true,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);

    let mut hop_in = vec![0.05f32; hop_size];
    let mut hop_out = vec![0.0f32; hop_size];

    // Feed 10 normal hops
    for _ in 0..10 {
        let _ = pipeline.process_hop(&hop_in, None, &mut model, &mut hop_out);
    }

    // Feed high-energy concussion shock impulse (RMS ~ 0.95)
    hop_in.fill(0.95);
    let _ = pipeline.process_hop(&hop_in, None, &mut model, &mut hop_out);

    let summary = pipeline.blackbox().incident_summary();
    assert_eq!(summary.rolling_window_frames, 11);
    assert_eq!(summary.concussion_events, 1);

    let mut csv_buf = Vec::new();
    let written = pipeline
        .blackbox()
        .export_forensic_csv(&mut csv_buf)
        .unwrap();
    assert_eq!(written, 11);
    let csv_str = String::from_utf8(csv_buf).unwrap();
    assert!(csv_str.contains("0x01")); // FLAG_CONCUSSION_SHOCK
}

#[test]
fn test_pipeline_minimum_phase_polyphase_resampling_integration() {
    use anc_rust::dsp::{MinimumPhasePolyphaseDecimator3x, MinimumPhasePolyphaseInterpolator3x};

    let mut decimator = MinimumPhasePolyphaseDecimator3x::new();
    let mut interpolator = MinimumPhasePolyphaseInterpolator3x::new();

    // Group delay checks
    assert!(decimator.group_delay_ms() < 0.40);
    assert!(interpolator.group_delay_ms() < 0.40);

    // 48 kHz synthetic speech frame (768 samples = 16 ms)
    let in_48k_samples = 768;
    let mut in_48k = vec![0.0f32; in_48k_samples];
    for (i, s) in in_48k.iter_mut().enumerate() {
        let t = i as f32 / 48000.0;
        *s = 0.5 * (2.0 * PI * 1000.0 * t).sin();
    }

    // Decimate 3:1 to 16 kHz (256 samples)
    let mut out_16k = vec![0.0f32; in_48k_samples / 3];
    decimator.process_block(&in_48k, &mut out_16k);
    assert_eq!(out_16k.len(), 256);

    // Interpolate 1:3 back to 48 kHz (768 samples)
    let mut reconstructed_48k = vec![0.0f32; in_48k_samples];
    interpolator.process_block(&out_16k, &mut reconstructed_48k);
    assert_eq!(reconstructed_48k.len(), 768);

    // Check amplitude preservation of 1 kHz tone through round-trip
    let pwr_in: f32 = in_48k[200..].iter().map(|s| s * s).sum();
    let pwr_recon: f32 = reconstructed_48k[200..].iter().map(|s| s * s).sum();
    let delta_db = (10.0 * (pwr_recon / pwr_in).log10()).abs();
    assert!(
        delta_db < 0.5,
        "Resampling round-trip delta too high: {:.2} dB",
        delta_db
    );
}

#[test]
fn test_pipeline_whisper_reconstruction_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_whisper: true,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);

    let hops = 20;
    let mut hop_out = vec![0.0f32; hop_size];

    // Synthesize whispered speech block: moderate low amplitude (-34 dBFS), high ZCR
    let mut whisper_chunk = vec![0.0f32; hop_size];
    for n in 0..hop_size {
        let sign = if n % 2 == 0 { 1.0 } else { -1.0 };
        whisper_chunk[n] = sign * 0.020;
    }

    for _ in 0..hops {
        let res = pipeline.process_hop(&whisper_chunk, None, &mut model, &mut hop_out);
        assert!(res.is_ok());
    }

    let stats = pipeline.whisper_stats();
    assert!(
        stats.whisper_prob > 0.35,
        "Whisper reconstructor should detect whispered speech, got prob={}",
        stats.whisper_prob
    );
    assert!(stats.active_boost_db > 1.0);
}

#[test]
fn test_pipeline_subband_gsc_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_mvdr: true,
        enable_gsc: true,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);

    let hops = 30;
    let mut hop_out = vec![0.0f32; hop_size];

    // Synthesize off-axis noise with 90 degree inter-mic delay
    let mut mic1 = vec![0.0f32; hop_size];
    let mut mic2 = vec![0.0f32; hop_size];

    for h in 0..hops {
        for n in 0..hop_size {
            let t = (h * hop_size + n) as f32 / sample_rate;
            // 2000 Hz off-axis tone
            mic1[n] = 0.3 * (2.0 * PI * 2000.0 * t).sin();
            mic2[n] = 0.3 * (2.0 * PI * 2000.0 * t + PI * 0.5).sin();
        }

        let res = pipeline.process_hop(&mic1, Some(&mic2), &mut model, &mut hop_out);
        assert!(res.is_ok());
    }

    let gsc_stats = pipeline.gsc_stats();
    assert!(
        gsc_stats.cancellation_db > 5.0,
        "GSC should cancel off-axis interference, got {} dB",
        gsc_stats.cancellation_db
    );
}

#[test]
fn test_pipeline_ashp_true_peak_compliance_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_transient_blanker: false, // Bypass input mic blanker so output ASHP receives the shock
        enable_ashp: true,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);

    let mut hop_in = vec![0.05f32; hop_size];
    let mut hop_out = vec![0.0f32; hop_size];

    // Feed normal hops
    for _ in 0..5 {
        let _ = pipeline.process_hop(&hop_in, None, &mut model, &mut hop_out);
    }

    // Inject concussive blast pulse: amplitude = 4.0 (+12 dBFS)
    hop_in.fill(0.0);
    hop_in[10] = 4.0;
    hop_in[11] = 3.5;
    hop_in[12] = 2.0;

    let _ = pipeline.process_hop(&hop_in, None, &mut model, &mut hop_out);
    // Feed trailing hop for STFT overlap-add synthesis emergence
    hop_in.fill(0.0);
    let _ = pipeline.process_hop(&hop_in, None, &mut model, &mut hop_out);

    let ashp_tele = pipeline.ashp_telemetry();
    assert!(
        ashp_tele.concussive_blasts_clamped > 0,
        "ASHP must detect and clamp concussive blast"
    );

    // Verify MIL-STD-1474E compliance: every output sample must strictly respect True-Peak ceiling
    let ceiling = 10.0f32.powf(-1.0 / 20.0);
    for (idx, &s) in hop_out.iter().enumerate() {
        assert!(
            s.abs() <= ceiling + 1e-4,
            "Sample at index {} ({}) breached MIL-STD-1474E ceiling {}",
            idx,
            s,
            ceiling
        );
    }
}

#[test]
fn test_pipeline_realtime_power_governor_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_governor: true,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);

    let hop_in = vec![0.1f32; hop_size];
    let mut hop_out = vec![0.0f32; hop_size];

    for _ in 0..30 {
        let _ = pipeline.process_hop(&hop_in, None, &mut model, &mut hop_out);
    }

    let gov_tele = pipeline.governor_telemetry();
    assert!(
        gov_tele.rtf < 0.25,
        "Edge RTF must be well under deadline in debug mode, got {}",
        gov_tele.rtf
    );
    assert!(
        gov_tele.headroom_pct > 75.0,
        "Headroom must be > 75%, got {}%",
        gov_tele.headroom_pct
    );
    assert!(
        gov_tele.energy_savings_pct > 50.0,
        "Energy savings must exceed 50%, got {}%",
        gov_tele.energy_savings_pct
    );
    assert_eq!(gov_tele.deadline_risk_count, 0);
}

#[test]
fn test_pipeline_wind_turbulence_derumbling_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_mvdr: true,
        enable_wind_suppressor: true,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);

    let mut m1 = vec![0.0f32; hop_size];
    let mut m2 = vec![0.0f32; hop_size];
    let mut out = vec![0.0f32; hop_size];

    // Simulate 80 hops (~1.28s) of uncorrelated aero-acoustic wind vortex shedding on dual mics
    let mut seed: u64 = 0x55555555;
    for h in 0..80 {
        for n in 0..hop_size {
            let t = (h * hop_size + n) as f32 / sample_rate;
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
            let n1 = (seed as f32 / u64::MAX as f32 - 0.5) * 2.0;
            seed = seed.wrapping_mul(6364136223846793005).wrapping_add(1);
            let n2 = (seed as f32 / u64::MAX as f32 - 0.5) * 2.0;

            // Infrasonic turbulence (< 100 Hz rumble)
            let rumble1 = 0.8 * (2.0 * PI * 45.0 * t).sin() + 0.3 * n1;
            let rumble2 = 0.8 * (2.0 * PI * 85.0 * t + 1.8).sin() + 0.3 * n2;

            m1[n] = rumble1;
            m2[n] = rumble2;
        }

        pipeline
            .process_hop(&m1, Some(&m2), &mut model, &mut out)
            .unwrap();
    }

    let wind_telem = pipeline.wind_telemetry();
    assert!(
        wind_telem.mean_wti > 0.70,
        "WTI should detect uncorrelated wind turbulence, got {:.3}",
        wind_telem.mean_wti
    );
    assert!(
        wind_telem.wind_detected,
        "Wind detector must flag active wind buffeting"
    );
}

#[test]
fn test_pipeline_phase_aligner_glottal_attack_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_phase_align: true,
        phase_align_config: PhaseAlignConfig {
            sample_rate,
            profile: PhaseAlignmentProfile::TacticalHelmet,
            enable_adaptive_tuning: false,
        },
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);

    let mut dispersed_hop = vec![0.0f32; hop_size];
    let mut out = vec![0.0f32; hop_size];

    // Synthesize dispersed vowel glottal pulses
    for h in 0..10 {
        for n in 0..hop_size {
            let t = (h * hop_size + n) as f32 / sample_rate;
            let mut val = 0.0f32;
            for k in 1..=12 {
                let disp_phase = (12.0 - k as f32).powi(2) * 0.15;
                val += (2.0 * PI * (k as f32 * 130.0) * t + disp_phase).cos() / (k as f32).sqrt();
            }
            dispersed_hop[n] = val * 0.25;
        }

        pipeline
            .process_hop(&dispersed_hop, None, &mut model, &mut out)
            .unwrap();
    }

    assert!(
        pipeline.glottal_crest_factor() > 1.5,
        "Glottal crest factor must be preserved and sharpened, got {:.2}",
        pipeline.glottal_crest_factor()
    );
}

#[test]
fn test_pipeline_adpcm_codec_mesh_streaming_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);

    let mut speech_hop = vec![0.0f32; hop_size];
    let mut out_hop = vec![0.0f32; hop_size];

    for n in 0..hop_size {
        let t = n as f32 / sample_rate;
        speech_hop[n] = 0.6 * (2.0 * PI * 440.0 * t).sin();
    }

    for _ in 0..6 {
        pipeline
            .process_hop(&speech_hop, None, &mut model, &mut out_hop)
            .unwrap();
    }

    let mut samples_arr = [0.0f32; 256];
    samples_arr.copy_from_slice(&out_hop);

    // Encode into ultra-compact 4-bit ADPCM wire packet
    let packet = anc_rust::network::AudioPacket::new(101, samples_arr);
    let adpcm_bytes = packet.serialize_adpcm();

    // 4x bandwidth reduction verified: 140 bytes vs 1032 bytes
    assert_eq!(adpcm_bytes.len(), anc_rust::network::ADPCM_PACKET_BYTES);
    assert_eq!(adpcm_bytes.len(), 140);

    // Transparent deserialization from compressed wire packet
    let decoded_packet = anc_rust::network::AudioPacket::deserialize(&adpcm_bytes)
        .expect("ADPCM packet deserialization must succeed");

    assert_eq!(decoded_packet.sequence, 101);
    assert_eq!(decoded_packet.samples.len(), 256);

    // Check SNR of ADPCM recovery
    let mut sig = 0.0f32;
    let mut err = 0.0f32;
    for i in 10..256 {
        sig += samples_arr[i] * samples_arr[i];
        let diff = samples_arr[i] - decoded_packet.samples[i];
        err += diff * diff;
    }
    let snr = 10.0 * (sig / err.max(1e-12)).log10();
    assert!(
        snr > 20.0,
        "Tactical ADPCM reconstruction SNR must exceed 20 dB, got {:.2} dB",
        snr
    );
}

#[test]
fn test_pipeline_dynamic_spp_spectral_floor_and_tsnr_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        window_type: WindowType::Hann,
        enable_mvdr: false,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut spectral_enhancer = AdaptiveSpectralEnhancer::new(num_bins, 32, sample_rate);

    // Warm-up on ambient noise for 25 hops
    let mut noise_hop = vec![0.0f32; hop_size];
    let mut out_hop = vec![0.0f32; hop_size];
    for n in 0..hop_size {
        noise_hop[n] = ((n as f32 * 19.3).sin() * 0.05).clamp(-0.1, 0.1);
    }

    for _ in 0..25 {
        pipeline
            .process_hop(&noise_hop, None, &mut spectral_enhancer, &mut out_hop)
            .unwrap();
    }

    // Measure pause attenuation during sustained pause
    for _ in 0..10 {
        pipeline
            .process_hop(&noise_hop, None, &mut spectral_enhancer, &mut out_hop)
            .unwrap();
    }

    let pwr_in_pause: f32 = noise_hop.iter().map(|s| s * s).sum();
    let pwr_out_pause: f32 = out_hop.iter().map(|s| s * s).sum();
    let pause_gain_db = 10.0 * (pwr_out_pause / pwr_in_pause.max(1e-12)).log10();

    assert!(
        pause_gain_db <= -16.0,
        "Dynamic SPP floor modulation must deeply suppress pause noise, got {:.2} dB",
        pause_gain_db
    );

    // Sudden speech vowel burst onset (F0 = 150 Hz + harmonics)
    // Pipeline has a 2-hop STFT overlap-add synthesis latency (512 / 256 = 2).
    // Feed through to verify TSNR rapid speech onset tracking without clipping.
    for h in 0..4 {
        let mut speech_hop = vec![0.0f32; hop_size];
        for n in 0..hop_size {
            let t = (h * hop_size + n) as f32 / sample_rate;
            speech_hop[n] = 0.5 * (2.0 * PI * 150.0 * t).sin()
                + 0.3 * (2.0 * PI * 300.0 * t).sin()
                + 0.15 * (2.0 * PI * 450.0 * t).sin();
        }

        pipeline
            .process_hop(&speech_hop, None, &mut spectral_enhancer, &mut out_hop)
            .unwrap();

        if h >= 2 {
            let pwr_in_speech: f32 = speech_hop.iter().map(|s| s * s).sum();
            let pwr_out_speech: f32 = out_hop.iter().map(|s| s * s).sum();
            let onset_ratio = pwr_out_speech / pwr_in_speech.max(1e-12);

            assert!(
                onset_ratio > 0.40,
                "TSNR fast attack must cleanly pass speech onset without clipping at hop {}: ratio={:.2}",
                h,
                onset_ratio
            );
        }
    }
}

#[test]
fn test_pipeline_aggressive_snr_preset_mode_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        window_type: WindowType::Hann,
        aggressive_snr: true,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut spectral_enhancer = AdaptiveSpectralEnhancer::new(num_bins, 32, sample_rate);

    assert!(pipeline.is_aggressive_snr());
    pipeline.set_aggressive_snr(true, Some(&mut spectral_enhancer));
    assert!(spectral_enhancer.is_aggressive_snr());

    let test_hop = vec![0.02f32; hop_size];
    let mut out_hop = vec![0.0f32; hop_size];
    for _ in 0..15 {
        let stats = pipeline
            .process_hop(&test_hop, None, &mut spectral_enhancer, &mut out_hop)
            .unwrap();
        assert!(stats.compute_time_us < 16_000);
    }
}

#[test]
fn test_pipeline_deep_harmonic_comb_valley_rejection_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        window_type: WindowType::Hann,
        enable_pitch_comb: true,
        aggressive_snr: true,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Fallback", num_bins, 32);

    // Voiced speech (160 Hz vowel) + inter-harmonic valley noise (240 Hz tone)
    let total_hops = 20;
    let mut out_hop = vec![0.0f32; hop_size];

    for h in 0..total_hops {
        let mut in_hop = vec![0.0f32; hop_size];
        for n in 0..hop_size {
            let t = (h * hop_size + n) as f32 / sample_rate;
            let speech = 0.5 * (2.0 * PI * 160.0 * t).sin() + 0.3 * (2.0 * PI * 320.0 * t).sin();
            let valley_noise = 0.2 * (2.0 * PI * 240.0 * t).sin();
            in_hop[n] = speech + valley_noise;
        }

        pipeline
            .process_hop(&in_hop, None, &mut model, &mut out_hop)
            .unwrap();
    }

    assert!(pipeline.pitch_comb.is_enabled());
    assert!(pipeline.pitch_comb.is_aggressive());
}

#[test]
fn test_pipeline_geigel_double_talk_freeze_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let mut afc_config = AfcConfig {
        enable_geigel: true,
        ..Default::default()
    };
    afc_config.geigel_config.threshold = 0.50;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        window_type: WindowType::Hann,
        enable_mvdr: true,
        enable_afc: true,
        afc_config,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", num_bins, 32);
    let mut out = vec![0.0f32; hop_size];

    // Single talk echo phase (speaker plays 0.8, leak is 0.2 -> ratio 0.25 < 0.50)
    for h in 0..15 {
        let mut spk = vec![0.0f32; hop_size];
        let mut m1 = vec![0.0f32; hop_size];
        for n in 0..hop_size {
            let t = (h * hop_size + n) as f32 / sample_rate;
            let radio = 0.8 * (2.0 * PI * 400.0 * t).sin();
            spk[n] = radio;
            m1[n] = 0.2 * radio;
        }
        pipeline
            .process_hop_tactical(&m1, None, Some(&spk), &mut model, &mut out)
            .unwrap();
    }
    assert!(
        !pipeline.afc_stats().double_talk_detected,
        "Echo alone must not trigger Geigel double-talk"
    );

    // Near-end soldier begins shouting while loudspeaker plays (mic jumps to 0.9, ref is 0.8 -> ratio > 0.50)
    let mut spk = vec![0.0f32; hop_size];
    let mut m1 = vec![0.0f32; hop_size];
    for n in 0..hop_size {
        let t = (16 * hop_size + n) as f32 / sample_rate;
        spk[n] = 0.8 * (2.0 * PI * 400.0 * t).sin();
        m1[n] = 0.9 * (2.0 * PI * 250.0 * t).sin();
    }
    pipeline
        .process_hop_tactical(&m1, None, Some(&spk), &mut model, &mut out)
        .unwrap();

    let stats = pipeline.afc_stats();
    assert!(
        stats.double_talk_detected,
        "Geigel detector must immediately detect double-talk"
    );
    assert!(
        stats.geigel_metric > 0.50,
        "Geigel metric must exceed 0.50 threshold"
    );
}

#[test]
fn test_pipeline_spectral_kurtosis_gunfire_shock_blanker_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        window_type: WindowType::Hann,
        enable_kurtosis: true,
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Analytic-Fallback", num_bins, 32);
    let mut out = vec![0.0f32; hop_size];

    // Nominal background noise frames (pseudo-random distributed noise)
    let bg_noise: Vec<f32> = (0..hop_size)
        .map(|n| 0.02 * ((n as f32 * 0.1).sin() + (n as f32 * 0.37).cos()))
        .collect();
    for _ in 0..20 {
        pipeline
            .process_hop(&bg_noise, None, &mut model, &mut out)
            .unwrap();
    }
    assert!(
        !pipeline.kurtosis_telemetry().is_shock_transient,
        "Background noise must be non-shock"
    );

    // Sudden massive gunfire blast shock transient (high crest factor + non-Gaussian energy spike)
    let mut shock_impulse = bg_noise.clone();
    shock_impulse[10] = 0.98;
    shock_impulse[11] = -0.92;
    shock_impulse[12] = 0.85;

    pipeline
        .process_hop(&shock_impulse, None, &mut model, &mut out)
        .unwrap();

    let telem = pipeline.kurtosis_telemetry();
    assert!(
        telem.is_shock_transient,
        "Gunfire blast must trigger Spectral Kurtosis shock detection"
    );
    assert!(
        telem.crest_factor_db > 10.0,
        "Crest factor must indicate high-energy peak-to-RMS ratio"
    );
    assert!(
        telem.suggested_attenuation < 1.0,
        "Must recommend protective ear attenuation"
    );
}

#[test]
fn test_pipeline_full_duplex_hardware_coordinator_integration() {
    use anc_rust::streaming::duplex::{DuplexConfig, DuplexStreamCoordinator};

    let config = DuplexConfig {
        sample_rate: 16000.0,
        block_size: 128,
        ring_capacity: 1024,
        prebuffer_frames: 256,
    };
    let mut duplex = DuplexStreamCoordinator::new(config);

    // Stream 1024 frames of capture audio
    let input_pcm = vec![0.35f32; 1024];
    let pushed = duplex.push_capture(&input_pcm);
    assert_eq!(pushed, 1024);

    // Step DSP processing loop (zero heap allocations)
    let mut blocks = 0;
    while duplex.step_dsp(|inp, out| {
        for (i, o) in inp.iter().zip(out.iter_mut()) {
            *o = *i * 1.5;
        }
    }) {
        blocks += 1;
    }
    assert_eq!(blocks, 8);

    // Pull 768 frames of rendered audio (maintaining 256 frames in buffer = 16.0 ms latency)
    let mut render_buf = vec![0.0f32; 768];
    let pulled = duplex.pull_render(&mut render_buf);
    assert_eq!(pulled, 768);
    assert!((render_buf[0] - 0.525).abs() < 1e-3);

    let telem = duplex.telemetry();
    assert!(telem.is_flowing);
    assert!(
        telem.loopback_latency_ms <= 35.0,
        "Loopback latency must be <= 35.0 ms SIH budget (was {:.2} ms)",
        telem.loopback_latency_ms
    );
    assert_eq!(telem.render_underruns, 0);
}

#[test]
fn test_pipeline_adaptive_filter_convergence_profiler_integration() {
    use anc_rust::metrics::AdaptiveConvergenceProfiler;

    let mut profiler = AdaptiveConvergenceProfiler::new(16000.0, 128);
    assert!(!profiler.all_converged());

    // Feed steady-state convergence values
    for _ in 0..40 {
        profiler.mvdr.update(1.0);
        profiler.gsc.update(12.0);
        profiler.afc.update(15.0);
        profiler.kalman.update(0.01);
        profiler.wpe.update(1.0);
    }

    assert!(
        profiler.all_converged(),
        "All adaptive filters should achieve steady-state convergence"
    );
    assert!(profiler.mvdr.status().convergence_time_ms > 0.0);
    assert!(profiler.afc.status().convergence_time_ms > 0.0);
}

#[test]
fn test_pipeline_subband_auxiva_bss_dual_talker_integration() {
    use anc_rust::dsp::{AuxIvaConfig, OnlineAuxIva};
    use num_complex::Complex32;
    use std::f32::consts::PI;

    let num_bins = 257;
    let config = AuxIvaConfig {
        num_bins,
        forgetting_factor: 0.92,
        learning_rate: 0.35,
        epsilon: 1e-6,
    };
    let mut iva = OnlineAuxIva::new(config);

    let mut mic1 = vec![Complex32::default(); num_bins];
    let mut mic2 = vec![Complex32::default(); num_bins];
    let mut target = vec![Complex32::default(); num_bins];
    let mut interf = vec![Complex32::default(); num_bins];

    // Simulate co-channel cockpit dual-talker:
    // Pilot (bins 10..20) and Co-pilot (bins 40..60) with distinct time-varying amplitude envelopes
    for frame in 0..50 {
        let t = frame as f32 * 0.016;
        let pilot_env = (2.0 * PI * 2.0 * t).sin().abs() + 0.15;
        let copilot_env = (2.0 * PI * 3.5 * t).cos().abs() + 0.15;

        for f in 0..num_bins {
            let pilot = if (10..=20).contains(&f) {
                Complex32::new(pilot_env * 0.8, pilot_env * 0.2)
            } else {
                Complex32::default()
            };
            let copilot = if (40..=60).contains(&f) {
                Complex32::new(copilot_env * 0.7, -copilot_env * 0.3)
            } else {
                Complex32::default()
            };

            // Spatial acoustic mixture: 30 mm dual-microphone baseline
            mic1[f] = pilot + copilot * 0.55;
            mic2[f] = pilot * 0.45 + copilot;
        }

        iva.process_frame(&mic1, &mic2, &mut target, &mut interf);
    }

    let stats = iva.stats();
    assert!(stats.source1_envelope > 0.0);
    assert!(stats.source2_envelope > 0.0);

    // Verify pilot formant energy is preserved on target channel
    let pilot_energy: f32 = target[10..=20].iter().map(|c| c.norm_sqr()).sum();
    let copilot_leak: f32 = target[40..=60].iter().map(|c| c.norm_sqr()).sum();
    assert!(
        pilot_energy > copilot_leak,
        "AuxIVA must isolate target pilot ({:.6}) over copilot leakage ({:.6})",
        pilot_energy,
        copilot_leak
    );
}

#[test]
fn test_pipeline_thd_distortion_analyzer_integration() {
    use anc_rust::metrics::{DistortionAnalyzer, DistortionConfig, VoiceCoilHealthStatus};
    use std::f32::consts::PI;

    let config = DistortionConfig {
        sample_rate: 16000.0,
        fft_size: 512,
        ..Default::default()
    };
    let mut analyzer = DistortionAnalyzer::new(config);

    // 1. Clean output test: 200 Hz speech tone
    let mut clean_frame = vec![0.0f32; 512];
    for (i, s) in clean_frame.iter_mut().enumerate() {
        *s = 0.5 * (2.0 * PI * 200.0 * (i as f32) / 16000.0).sin();
    }
    let mut clean_metrics = analyzer.process_frame(&clean_frame);
    for _ in 0..10 {
        clean_metrics = analyzer.process_frame(&clean_frame);
    }
    assert_eq!(clean_metrics.status, VoiceCoilHealthStatus::Nominal);
    assert!(clean_metrics.health_score > 90.0);

    // 2. Hardware saturation / non-linear voice-coil overdrive test
    let mut saturated_frame = vec![0.0f32; 512];
    for (i, s) in saturated_frame.iter_mut().enumerate() {
        let raw = 2.0 * (2.0 * PI * 200.0 * (i as f32) / 16000.0).sin();
        *s = raw.clamp(-0.6, 0.6); // Driver excursion saturation clipping
    }
    let mut sat_metrics = analyzer.process_frame(&saturated_frame);
    for _ in 0..15 {
        sat_metrics = analyzer.process_frame(&saturated_frame);
    }
    assert_eq!(sat_metrics.status, VoiceCoilHealthStatus::SaturationWarning);
    assert!(sat_metrics.thd > 0.08);
}

#[test]
fn test_pipeline_crypto_frame_authentication_anti_spoofing_integration() {
    use anc_rust::network::crypto::{AuthResult, TacticalFrameAuthenticator};

    let session_key = [0xA5u8; 32];
    let mut transmitter = TacticalFrameAuthenticator::new(&session_key);
    let mut receiver = TacticalFrameAuthenticator::new(&session_key);

    let sequence = 500u64;
    let audio_payload = vec![0x12u8; 256];
    let mut tag = [0u8; 16];

    // Transmit signed audio packet
    transmitter.sign_frame(sequence, &audio_payload, &mut tag);

    // Receiver verifies valid frame
    let res = receiver.verify_frame(sequence, &audio_payload, &tag);
    assert_eq!(res, AuthResult::Valid);

    // Hostile RF replay attack: adversary replays captured frame 500
    let replay_res = receiver.verify_frame(sequence, &audio_payload, &tag);
    assert_eq!(replay_res, AuthResult::ReplayDetected);

    // Hostile RF spoofing attack: forged audio commands with manipulated payload
    let mut forged_payload = audio_payload.clone();
    forged_payload[4] ^= 0x55;
    let forge_res = receiver.verify_frame(sequence + 1, &forged_payload, &tag);
    assert_eq!(forge_res, AuthResult::TagMismatch);
    assert_eq!(receiver.forged_packets_blocked(), 1);
    assert_eq!(receiver.replayed_packets_blocked(), 1);
}

#[test]
fn test_pipeline_acoustic_camouflage_psychoacoustic_masking_integration() {
    use anc_rust::dsp::{AcousticCamouflageEngine, CamouflageConfig, CamouflageProfile};
    use num_complex::Complex32;

    let config = CamouflageConfig {
        sample_rate: 16000.0,
        num_bins: 257,
        profile: CamouflageProfile::SilentRecon,
        ..Default::default()
    };
    let mut camouflage = AcousticCamouflageEngine::new(config);

    let ambient = vec![Complex32::new(0.02, 0.01); 257];
    let mut soldier = vec![Complex32::new(0.005, 0.0); 257];
    let mut out_masking = vec![Complex32::default(); 257];

    // Steady state quiet patrol
    for _ in 0..10 {
        camouflage.process_spectrum(&ambient, &soldier, &mut out_masking);
    }
    assert!(!camouflage.telemetry().cloaking_active);

    // Soldier gear rustle transient (sling swivel clink & vest rub)
    for s in soldier.iter_mut().take(120).skip(40) {
        *s = Complex32::new(0.12, -0.05);
    }
    camouflage.process_spectrum(&ambient, &soldier, &mut out_masking);

    let tele = camouflage.telemetry();
    assert!(
        tele.cloaking_active,
        "Camouflage engine must trigger on soldier gear rustle"
    );
    assert!(tele.cloaked_events_count >= 1);
    assert!(tele.spectral_entropy > 0.80);
}

#[test]
fn test_pipeline_lufs_loudness_governor_tactical_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_lufs_governor: true,
        enable_mvdr: false,
        ..Default::default()
    };
    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Fallback-Wiener", num_bins, 32);

    let mut out = vec![0.0f32; hop_size];

    // Feed shouting pilot speech bursts (high loudness)
    for frame in 0..40 {
        let mut mic1 = vec![0.0f32; hop_size];
        for (i, s) in mic1.iter_mut().enumerate() {
            let t = (frame * hop_size + i) as f32 / sample_rate;
            *s = 0.90 * (2.0 * PI * 1000.0 * t).sin();
        }
        pipeline
            .process_hop(&mic1, None, &mut model, &mut out)
            .unwrap();
    }

    let telem = pipeline.lufs_telemetry();
    assert!(
        telem.momentary_lufs > -15.0,
        "Momentary LUFS should measure high speech loudness"
    );
    assert!(
        telem.gain_reduction_db < -3.0,
        "Governor should apply gain reduction to regulate shouting"
    );
    assert!(
        telem.true_peak_dbfs <= 0.0,
        "True peak must not clip 0 dBFS ceiling"
    );
}

#[test]
fn test_pipeline_subband_afc_and_res_postfilter_integration() {
    use anc_rust::dsp::{AfcConfig, ResPostfilterConfig};

    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_afc: true,
        enable_res_postfilter: true,
        enable_mvdr: false,
        afc_config: AfcConfig {
            step_size: 0.25,
            transfer_ratio: 0.90,
            enable_geigel: true,
            ..Default::default()
        },
        res_config: ResPostfilterConfig {
            gain_smoothing: 0.30,
            over_subtraction: 2.5,
            ..Default::default()
        },
        ..Default::default()
    };
    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Fallback-Wiener", num_bins, 32);

    let mut out = vec![0.0f32; hop_size];

    // Loudspeaker plays radio transmission: 400 Hz tone
    // Injects linear echo + non-linear ear-cushion harmonic distortion (800 Hz overtone)
    for frame in 0..60 {
        let mut spk = vec![0.0f32; hop_size];
        let mut mic = vec![0.0f32; hop_size];
        for (i, s) in spk.iter_mut().enumerate() {
            let t = (frame * hop_size + i) as f32 / sample_rate;
            *s = 0.50 * (2.0 * PI * 400.0 * t).sin();
            // Linear echo 0.20 + non-linear 2nd harmonic 0.05
            mic[i] = 0.20 * (2.0 * PI * 400.0 * t).sin() + 0.05 * (2.0 * PI * 800.0 * t).sin();
        }
        pipeline
            .process_hop_tactical(&mic, None, Some(&spk), &mut model, &mut out)
            .unwrap();
    }

    let res_stats = pipeline.res_stats();
    assert!(
        res_stats.total_erle_db > 10.0,
        "Linear AFC + RES postfilter should achieve >10 dB cancellation"
    );
    assert!(res_stats.res_suppression_db >= 0.0);
}

#[test]
fn test_pipeline_sensor_calibration_restores_clogged_mic_mvdr_nulling() {
    use anc_rust::dsp::SensorCalConfig;

    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_sensor_cal: true,
        enable_mvdr: true,
        sensor_cal_config: SensorCalConfig {
            cal_smoothing: 0.10,
            filter_smoothing: 0.10,
            max_spp_threshold: 0.40, // Allows calibration during initial diffuse noise adaptation
            ..Default::default()
        },
        ..Default::default()
    };
    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Fallback-Wiener", num_bins, 32);

    let mut out = vec![0.0f32; hop_size];

    // Feed diffuse noise where Mic 2 has -4 dB sensitivity loss (mud/debris clog)
    let clog_scale = 10.0f32.powf(-4.0 / 20.0); // 0.631

    for frame in 0..70 {
        let mut mic1 = vec![0.0f32; hop_size];
        let mut mic2 = vec![0.0f32; hop_size];
        for (i, s) in mic1.iter_mut().enumerate() {
            let t = (frame * hop_size + i) as f32 / sample_rate;
            // Diffuse noise synthetic blend
            let noise = 0.08 * (2.0 * PI * 250.0 * t).sin() + 0.06 * (2.0 * PI * 750.0 * t).sin();
            *s = noise;
            mic2[i] = noise * clog_scale;
        }
        pipeline
            .process_hop(&mic1, Some(&mic2), &mut model, &mut out)
            .unwrap();
    }

    let cal_telem = pipeline.sensor_cal_telemetry();
    assert!(
        cal_telem.clog_detected,
        "Sensor calibration must detect severe sensitivity mismatch on clogged mic"
    );
    assert!(
        cal_telem.max_mismatch_db > 2.5,
        "Maximum mismatch should register the -4 dB deficit"
    );
    assert!(
        cal_telem.calibrated_frames_count > 0,
        "Diffuse frames should increment calibration counter"
    );
}

#[test]
fn test_pipeline_inverse_lombard_strain_compensation_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_lombard: true,
        enable_pitch_comb: true,
        lombard_config: anc_rust::dsp::LombardConfig {
            adaptation_rate: 0.30,
            ..Default::default()
        },
        ..Default::default()
    };
    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Fallback-Wiener", num_bins, 32);

    let mut out = vec![0.0f32; hop_size];

    // Feed shouted speech (elevated F0 = 195 Hz + harsh high formant harmonics)
    for frame in 0..40 {
        let mut mic1 = vec![0.0f32; hop_size];
        for (i, s) in mic1.iter_mut().enumerate() {
            let t = (frame * hop_size + i) as f32 / sample_rate;
            let voice = 0.5 * (2.0 * PI * 195.0 * t).sin()
                + 0.35 * (2.0 * PI * 2100.0 * t).sin()
                + 0.25 * (2.0 * PI * 2600.0 * t).sin();
            *s = voice;
        }
        pipeline
            .process_hop(&mic1, None, &mut model, &mut out)
            .unwrap();
    }

    let lombard = pipeline.lombard_telemetry();
    assert!(
        lombard.strain_index > 0.20,
        "Lombard compensator must detect strain on shouted voice, got {:.3}",
        lombard.strain_index
    );
    assert!(
        lombard.tilt_correction_db > 0.8,
        "Inverse tilt attenuation should be active"
    );
}

#[test]
fn test_pipeline_creeping_wave_diffraction_steering_vector_correction() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_mvdr: true,
        mvdr_config: MvdrConfig {
            num_bins,
            sample_rate,
            enable_diffraction_correction: true,
            ..Default::default()
        },
        ..Default::default()
    };
    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Fallback-Wiener", num_bins, 32);

    let mut out = vec![0.0f32; hop_size];

    // Target broadside speech + off-axis interference at 45 degrees
    let delta_t_45 = (0.03 * (45.0f32 * PI / 180.0).sin()) / 343.0;

    for frame in 0..30 {
        let mut mic1 = vec![0.0f32; hop_size];
        let mut mic2 = vec![0.0f32; hop_size];
        for (i, s1) in mic1.iter_mut().enumerate() {
            let t = (frame * hop_size + i) as f32 / sample_rate;
            let speech = 0.25 * (2.0 * PI * 350.0 * t).sin();
            let noise = 0.35 * (2.0 * PI * 3200.0 * t).sin();
            let noise_mic2 = 0.35 * (2.0 * PI * 3200.0 * (t - delta_t_45)).sin();
            *s1 = speech + noise;
            mic2[i] = speech + noise_mic2;
        }
        pipeline
            .process_hop(&mic1, Some(&mic2), &mut model, &mut out)
            .unwrap();
    }

    // Verify output is finite, stable, and beamformer is active
    let pwr = out.iter().map(|&s| s * s).sum::<f32>() / hop_size as f32;
    assert!(
        pwr > 0.001 && pwr < 1.0,
        "Beamformed output power should be nominal: {}",
        pwr
    );
}

#[test]
fn test_pipeline_anti_howling_hilbert_ssb_shifter_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_howling: true,
        howling_config: anc_rust::dsp::HowlingConfig {
            howling_threshold_db: 4.5,
            ..Default::default()
        },
        ..Default::default()
    };
    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Fallback-Wiener", num_bins, 32);

    let mut out = vec![0.0f32; hop_size];

    // Feed runaway feedback tone
    for frame in 0..25 {
        let mut mic1 = vec![0.0f32; hop_size];
        for (i, s) in mic1.iter_mut().enumerate() {
            let t = (frame * hop_size + i) as f32 / sample_rate;
            *s = 0.70 * (2.0 * PI * 2200.0 * t).sin();
        }
        pipeline
            .process_hop(&mic1, None, &mut model, &mut out)
            .unwrap();
    }

    let howling_telem = pipeline.howling_telemetry();
    assert!(
        howling_telem.howling_detected,
        "Anti-howling shifter must flag closed-loop acoustic resonance"
    );
    assert!(
        howling_telem.loop_attenuation_db > 0.0,
        "Anti-howling must engage protective loop attenuation"
    );
}

#[test]
fn test_pipeline_soldier_cognitive_stress_profiler_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_stress: true,
        enable_pitch_comb: true,
        ..Default::default()
    };
    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Fallback-Wiener", num_bins, 32);

    let mut out = vec![0.0f32; hop_size];

    for frame in 0..40 {
        let f0 = 175.0 + if frame % 2 == 0 { 12.0 } else { -12.0 };
        let mut mic1 = vec![0.0f32; hop_size];
        for (i, s) in mic1.iter_mut().enumerate() {
            let t = (frame * hop_size + i) as f32 / sample_rate;
            *s = 0.40 * (2.0 * PI * f0 * t).sin();
        }
        pipeline
            .process_hop(&mic1, None, &mut model, &mut out)
            .unwrap();
    }

    let stress_telem = pipeline.stress_telemetry();
    assert!(
        stress_telem.stress_index_pct > 15.0,
        "Stress index must register vocal tremor, got {:.1}%",
        stress_telem.stress_index_pct
    );
}

#[test]
fn test_pipeline_audiogram_nal_nl2_wdrc_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let notch = anc_rust::dsp::PersonalAudiogram::mild_4khz_notch();
    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_audiogram_wdrc: true,
        audiogram_profile: notch,
        ..Default::default()
    };
    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Fallback-Wiener", num_bins, 32);

    let mut out = vec![0.0f32; hop_size];

    // Feed soft 4 kHz tone (acoustic trauma region)
    for frame in 0..30 {
        let mut mic1 = vec![0.0f32; hop_size];
        for (i, s) in mic1.iter_mut().enumerate() {
            let t = (frame * hop_size + i) as f32 / sample_rate;
            *s = 0.05 * (2.0 * PI * 4000.0 * t).sin();
        }
        pipeline
            .process_hop(&mic1, None, &mut model, &mut out)
            .unwrap();
    }

    // Output must be boosted at 4 kHz while remaining stable and finite
    assert!(out[128].is_finite());
    assert!(
        pipeline
            .audiogram_wdrc
            .average_insertion_gain_db(anc_rust::dsp::Ear::Left)
            > 8.0
    );
}

#[test]
fn test_pipeline_subband_bone_air_sensor_fusion_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_bone_fusion: true,
        ..Default::default()
    };
    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Fallback-Wiener", num_bins, 32);

    let mut out = vec![0.0f32; hop_size];

    // mic1 is air mic with 3 kHz consonant formants
    // mic2 is bone sensor with 300 Hz low skull vibration
    for frame in 0..25 {
        let mut mic1 = vec![0.0f32; hop_size];
        let mut mic2 = vec![0.0f32; hop_size];
        for i in 0..hop_size {
            let t = (frame * hop_size + i) as f32 / sample_rate;
            mic1[i] = 0.20 * (2.0 * PI * 3000.0 * t).sin();
            mic2[i] = 0.35 * (2.0 * PI * 300.0 * t).sin();
        }
        pipeline
            .process_hop(&mic1, Some(&mic2), &mut model, &mut out)
            .unwrap();
    }

    let bone_telem = pipeline.bone_fusion_telemetry();
    assert!(
        bone_telem.is_bone_active,
        "Bone sensor activity must be flagged"
    );
    assert_eq!(bone_telem.fusion_crossover_hz, 1500.0);
    assert!(out[100].is_finite());
}

#[test]
fn test_pipeline_tactical_battery_simulator_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_battery_sim: true,
        ..Default::default()
    };
    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Fallback-Wiener", num_bins, 32);

    let mut out = vec![0.0f32; hop_size];
    let mic1 = vec![0.05f32; hop_size];

    for _ in 0..30 {
        pipeline
            .process_hop(&mic1, None, &mut model, &mut out)
            .unwrap();
    }

    let batt_telem = pipeline.battery_telemetry();
    assert!(batt_telem.soc_pct > 70.0);
    assert!(batt_telem.terminal_voltage_v >= 7.0);
    assert!(batt_telem.estimated_runtime_hours > 2.0);
    assert!(batt_telem.power_draw_mw > 200.0);
}

#[test]
fn test_pipeline_acoustic_blast_wave_overpressure_meter_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_blast_meter: true,
        ..Default::default()
    };
    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Fallback-Wiener", num_bins, 32);

    let mut out = vec![0.0f32; hop_size];

    // Feed an intense blast concussion pulse
    let mut blast_chunk = vec![0.01f32; hop_size];
    for i in 20..60 {
        blast_chunk[i] = 10.0; // Concussion peak
    }
    let quiet_chunk = vec![0.01f32; hop_size];

    pipeline
        .process_hop(&blast_chunk, None, &mut model, &mut out)
        .unwrap();
    pipeline
        .process_hop(&quiet_chunk, None, &mut model, &mut out)
        .unwrap();

    let blast_telem = pipeline.blast_telemetry();
    assert!(
        blast_telem.daily_impulse_count >= 1,
        "Impulse meter must log blast event"
    );
    assert!(
        blast_telem.last_blast_event.peak_overpressure_pa > 1000.0,
        "Overpressure in Pa must exceed 1000 Pa, got {}",
        blast_telem.last_blast_event.peak_overpressure_pa
    );
    assert!(
        blast_telem.last_blast_event.peak_overpressure_psi > 0.10,
        "Overpressure in PSI must register, got {}",
        blast_telem.last_blast_event.peak_overpressure_psi
    );
}

#[test]
fn test_pipeline_deesser_anti_sibilance_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_deesser: true,
        ..Default::default()
    };
    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Fallback-Wiener", num_bins, 32);

    let mut out = vec![0.0f32; hop_size];

    // Feed harsh sibilant speech tone (6.5 kHz)
    let mut sibilant_chunk = vec![0.0f32; hop_size];
    for (i, sample) in sibilant_chunk.iter_mut().enumerate() {
        let t = i as f32 / sample_rate;
        *sample = 0.7 * (2.0 * std::f32::consts::PI * 6500.0 * t).sin();
    }

    for _ in 0..6 {
        pipeline
            .process_hop(&sibilant_chunk, None, &mut model, &mut out)
            .unwrap();
    }

    let deesser_telem = pipeline.deesser_telemetry();
    assert!(
        deesser_telem.sibilance_detected,
        "De-esser must flag sibilance detection in pipeline"
    );
    assert!(
        deesser_telem.gain_reduction_db < -1.0,
        "High-band gain reduction must be applied to harsh sibilance"
    );
}

#[test]
fn test_pipeline_polar_pattern_shaper_directional_nulling_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let polar_cfg = anc_rust::dsp::PolarPatternConfig {
        pattern: anc_rust::dsp::PolarPatternType::Cardioid,
        sample_rate,
        ..Default::default()
    };

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_polar_pattern: true,
        polar_config: polar_cfg,
        ..Default::default()
    };
    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Fallback-Wiener", num_bins, 32);

    let mut mic1 = vec![0.0f32; hop_size];
    let mut mic2 = vec![0.0f32; hop_size];
    let mut out = vec![0.0f32; hop_size];

    let tau0 = 0.020 / anc_rust::dsp::SPEED_OF_SOUND_M_S;
    for i in 0..hop_size {
        let t = i as f32 / sample_rate;
        mic2[i] = (2.0 * std::f32::consts::PI * 1000.0 * t).sin();
        mic1[i] = (2.0 * std::f32::consts::PI * 1000.0 * (t - tau0)).sin();
    }

    for _ in 0..4 {
        pipeline
            .process_hop(&mic1, Some(&mic2), &mut model, &mut out)
            .unwrap();
    }

    let polar_telem = pipeline.polar_telemetry();
    assert_eq!(
        polar_telem.pattern_type,
        anc_rust::dsp::PolarPatternType::Cardioid as u8
    );
    assert_eq!(polar_telem.null_angle_deg, 180.0);
}

#[test]
fn test_pipeline_thermal_noise_estimator_wiener_floor_bounding_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_thermal_estimator: true,
        ..Default::default()
    };
    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Fallback-Wiener", num_bins, 32);

    let mic1 = vec![0.0001f32; hop_size]; // Silent patrol near thermal floor
    let mut out = vec![0.0f32; hop_size];

    pipeline
        .process_hop(&mic1, None, &mut model, &mut out)
        .unwrap();

    let thermal_telem = pipeline.thermal_telemetry();
    assert!(thermal_telem.thermal_noise_floor_dbfs < -70.0);
    assert!(thermal_telem.ein_dbv < -110.0);
}

#[test]
fn test_pipeline_cable_continuity_and_fault_diagnostics_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_cable_diagnostics: true,
        ..Default::default()
    };
    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Fallback-Wiener", num_bins, 32);

    let mut mic1 = vec![0.0f32; hop_size];
    let mut mic2 = vec![0.0f32; hop_size];
    let mut out = vec![0.0f32; hop_size];

    for i in 0..hop_size {
        let t = i as f32 / sample_rate;
        let s = 0.2 * (2.0 * std::f32::consts::PI * 400.0 * t).sin();
        mic1[i] = s;
        mic2[i] = s * 0.99;
    }

    for _ in 0..5 {
        pipeline
            .process_hop(&mic1, Some(&mic2), &mut model, &mut out)
            .unwrap();
    }

    let cable_telem = pipeline.cable_telemetry();
    assert_eq!(
        cable_telem.status,
        anc_rust::metrics::CableFaultStatus::Nominal
    );
    assert!(cable_telem.health_pct > 90.0);
    assert!(
        cable_telem.estimated_impedance_ohms > 1500.0
            && cable_telem.estimated_impedance_ohms < 3000.0
    );
}

#[test]
fn test_pipeline_spectral_contrast_formant_unmasking_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_contrast: true,
        ..Default::default()
    };
    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Fallback-Wiener", num_bins, 32);

    let mut mic1 = vec![0.0f32; hop_size];
    let mut mic2 = vec![0.0f32; hop_size];
    let mut out = vec![0.0f32; hop_size];

    // Formant speech signal: F0=200Hz + F1=800Hz + F2=2400Hz
    for i in 0..hop_size {
        let t = i as f32 / sample_rate;
        let speech = 0.3 * (2.0 * std::f32::consts::PI * 200.0 * t).sin()
            + 0.25 * (2.0 * std::f32::consts::PI * 800.0 * t).sin()
            + 0.15 * (2.0 * std::f32::consts::PI * 2400.0 * t).sin();
        let noise = 0.02 * (2.0 * std::f32::consts::PI * 600.0 * t).cos();
        mic1[i] = speech + noise;
        mic2[i] = speech * 0.98 + noise;
    }

    for _ in 0..10 {
        pipeline
            .process_hop(&mic1, Some(&mic2), &mut model, &mut out)
            .unwrap();
    }

    let contrast_telem = pipeline.contrast_telemetry();
    assert!(contrast_telem.contrast_ratio_db >= 0.0);
    assert!(contrast_telem.energy_scale_factor > 0.5 && contrast_telem.energy_scale_factor < 2.0);
}

#[test]
fn test_pipeline_ambisonics_intensity_diffuseness_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_ambisonics: true,
        ..Default::default()
    };
    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Fallback-Wiener", num_bins, 32);

    let mut mic1 = vec![0.0f32; hop_size];
    let mut mic2 = vec![0.0f32; hop_size];
    let mut out = vec![0.0f32; hop_size];

    // Directional plane wave arriving ~30 degrees off axis
    for i in 0..hop_size {
        let t = i as f32 / sample_rate;
        let s = 0.3 * (2.0 * std::f32::consts::PI * 1000.0 * t).sin();
        let s_delayed = 0.3 * (2.0 * std::f32::consts::PI * 1000.0 * (t - 0.000087)).sin();
        mic1[i] = s;
        mic2[i] = s_delayed;
    }

    for _ in 0..10 {
        pipeline
            .process_hop(&mic1, Some(&mic2), &mut model, &mut out)
            .unwrap();
    }

    let ambi_telem = pipeline.ambisonics_telemetry();
    assert!(ambi_telem.energy_density >= 0.0);
    assert!(ambi_telem.diffuseness >= 0.0 && ambi_telem.diffuseness <= 1.0);
}

#[test]
fn test_pipeline_jamming_detector_adpcm_fallback_integration() {
    use anc_rust::network::jamming::{
        JammingDetector, JammingDetectorConfig, JammingRemediation, JammingType,
    };

    let config = JammingDetectorConfig {
        nominal_interval_ms: 16.0,
        barrage_jitter_var_thresh: 10.0,
        barrage_loss_thresh: 0.20,
        spot_burst_thresh: 0.30,
        spot_loss_thresh: 0.03,
        auth_failure_thresh: 0.02,
        enabled: true,
    };
    let mut detector = JammingDetector::new(config);

    // Feed a sequence of jammed packets with high jitter variance and burst sequence drops
    let mut remediation = JammingRemediation::None;
    let mut seq = 0u64;
    for i in 0..60 {
        let timestamp_ms = (i as f64) * 16.0 + if i % 2 == 0 { 25.0 } else { -25.0 }; // Severe jitter
        seq += if i % 3 == 0 { 3 } else { 1 }; // Sequence loss bursts
        let (_, rem) = detector.record_packet(timestamp_ms, seq, true);
        if rem != JammingRemediation::None {
            remediation = rem;
        }
    }

    let telem = detector.telemetry();
    assert_ne!(telem.jamming_type, JammingType::NominalRF);
    assert!(telem.remediation_active);
    assert_eq!(remediation, JammingRemediation::EngageAdpcm4BitAndMaxFec);

    // Verify ADPCM round-trip compression and decompression
    use anc_rust::network::codec::{AdpcmDecoder, AdpcmEncoder};
    let mut encoder = AdpcmEncoder::new();
    let mut decoder = AdpcmDecoder::new();

    let original = [0.25f32; 256];
    let packet = encoder.encode_frame(1, &original);
    assert_eq!(packet.data.len(), 128); // 4 bits per sample = 128 bytes for 256 samples

    let mut decoded = [0.0f32; 256];
    decoder.decode_packet(&packet, &mut decoded);

    // Check correlation / energy conservation
    let orig_energy: f32 = original.iter().map(|x| x * x).sum();
    let dec_energy: f32 = decoded.iter().map(|x| x * x).sum();
    assert!((orig_energy - dec_energy).abs() / orig_energy < 0.25);
}

#[test]
fn test_pipeline_rasti_speech_transmission_index_integration() {
    let sample_rate = 16000.0f32;
    let n_fft = 512;
    let hop_size = 256;
    let num_bins = n_fft / 2 + 1;

    let config = PipelineConfig {
        n_fft,
        hop_size,
        sample_rate,
        enable_rasti: true,
        ..Default::default()
    };
    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = TractEnhancer::new_fallback("Fallback-Wiener", num_bins, 32);

    let mut mic1 = vec![0.0f32; hop_size];
    let mut out = vec![0.0f32; hop_size];

    // High intelligibility speech signal with clean envelope modulation (4 Hz syllabic rate)
    for frame in 0..60 {
        let t_sec = frame as f32 * 0.016;
        let syllabic_env = 0.5 * (1.0 + (2.0 * std::f32::consts::PI * 4.0 * t_sec).sin());
        for i in 0..hop_size {
            let t = (frame * hop_size + i) as f32 / sample_rate;
            let carrier = (2.0 * std::f32::consts::PI * 1000.0 * t).sin();
            mic1[i] = syllabic_env * carrier * 0.4;
        }
        pipeline
            .process_hop(&mic1, None, &mut model, &mut out)
            .unwrap();
    }

    let rasti = pipeline.rasti_telemetry();
    assert!(rasti.sti_score > 0.0);
    assert!(rasti.mean_mtf > 0.0);
}
