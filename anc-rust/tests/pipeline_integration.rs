//! End-to-end integration tests for TacticalAncPipeline.

use anc_rust::dsp::{MvdrConfig, WindowType};
use anc_rust::metrics::snr::compute_si_sdr;
use anc_rust::model::TractEnhancer;
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
            assert!(s.abs() <= 1.0, "Limiter must clamp samples to [-1, 1], got {}", s);
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
    pipeline.process_hop(&hop_in, None, &mut model, &mut out1).unwrap();

    // Reset pipeline
    pipeline.reset();

    // Process the exact same initial hop
    pipeline.process_hop(&hop_in, None, &mut model, &mut out2).unwrap();

    for i in 0..256 {
        assert!(
            (out1[i] - out2[i]).abs() < 1e-6,
            "Reset must return pipeline to identical initial deterministic state"
        );
    }
}
