//! Standardized Military Acoustic Dataset Benchmark & Objective Quality Harness.
//!
//! Evaluates the complete TacticalAncPipeline across standardized tactical noise
//! environments (simulating NOISEX-92 / DEMAND / MIL-STD-1474E military corpora):
//! 1. Tank Cabin Rumble (M1A2 / T-90 low-frequency track & diesel drone 50-300 Hz)
//! 2. Helicopter Cockpit Noise (Mil Mi-17 / Apache blade vortex interactions & turbine whine)
//! 3. Infantry TOC Babble Noise (High-density multi-talker interfering chatter)
//! 4. Artillery Gunfire Shockwaves (Concussive impulse reflections & blast decay)
//!
//! Evaluates both ITU-T P.862 / P.862.1 PESQ MOS-LQO and SI-SDR across all profiles.

use anc_rust::dsp::{MvdrConfig, WindowType};
use anc_rust::metrics::pesq::PesqEvaluator;
use anc_rust::metrics::snr::compute_si_sdr;
use anc_rust::model::{GtcrnDeepFilterModel, SpeechEnhancer, TractEnhancer};
use anc_rust::streaming::{PipelineConfig, TacticalAncPipeline};
use std::f32::consts::PI;

fn run_noise_benchmark(
    env_name: &str,
    noise_fn: impl Fn(usize, f32) -> f32,
) -> (f32, f32, f32, f32) {
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
            mic_distance_m: 0.03,
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

    let total_hops = 120;
    let total_samples = total_hops * hop_size;

    let mut clean = Vec::with_capacity(total_samples);
    let mut enhanced = Vec::with_capacity(total_samples);

    let noise_delay_samples = (0.03 / 343.0) * sample_rate;
    let mut noisy_m1 = Vec::with_capacity(total_samples);
    let mut noisy_m2 = Vec::with_capacity(total_samples);

    for n in 0..total_samples {
        let t = n as f32 / sample_rate;
        let speech = (2.0 * PI * 200.0 * t).sin() * 0.35
            + (2.0 * PI * 400.0 * t).sin() * 0.25
            + (2.0 * PI * 800.0 * t).sin() * 0.15
            + (2.0 * PI * 1600.0 * t).sin() * 0.10;

        let noise_m1 = noise_fn(n, t);
        let t_delayed = (n as f32 - noise_delay_samples) / sample_rate;
        let noise_m2 = noise_fn(n, t_delayed);

        clean.push(speech);
        noisy_m1.push(speech + noise_m1);
        noisy_m2.push(speech + noise_m2);
    }

    // Stream through pipeline
    let mut out_frame = [0.0f32; 256];

    for h in 0..total_hops {
        let offset = h * hop_size;
        let mic1 = &noisy_m1[offset..offset + hop_size];
        let mic2 = &noisy_m2[offset..offset + hop_size];

        pipeline
            .process_hop(mic1, Some(mic2), &mut model, &mut out_frame)
            .expect("process_hop failed");

        for &val in out_frame.iter() {
            enhanced.push(val);
        }
    }

    // Account for causal overlap-add framing delay (exactly 1 hop = 256 samples)
    let delay = hop_size;
    let eval_start = 25 * hop_size;
    let eval_end = total_samples - delay;

    let clean_eval = &clean[eval_start..eval_end];
    let noisy_eval = &noisy_m1[eval_start..eval_end];
    let enh_eval = &enhanced[(eval_start + delay)..(eval_end + delay)];

    let input_sdr = compute_si_sdr(clean_eval, noisy_eval);
    let output_sdr = compute_si_sdr(clean_eval, enh_eval);

    let pesq = PesqEvaluator::new(sample_rate, 256);
    let input_pesq = pesq.evaluate(clean_eval, noisy_eval);
    let output_pesq = pesq.evaluate(clean_eval, enh_eval);

    println!(
        "[{}] SI-SDR: {:.2} -> {:.2} dB (Gain: +{:.2} dB) | PESQ MOS: {:.2} -> {:.2} ({})",
        env_name,
        input_sdr,
        output_sdr,
        output_sdr - input_sdr,
        input_pesq.mos_lqo,
        output_pesq.mos_lqo,
        output_pesq.qualification
    );

    (
        input_sdr,
        output_sdr,
        input_pesq.mos_lqo,
        output_pesq.mos_lqo,
    )
}

#[test]
fn test_dataset_benchmark_tank_cabin_rumble() {
    let (in_sdr, out_sdr, _in_pesq, _out_pesq) = run_noise_benchmark("TANK_CABIN_M1A2", |_n, t| {
        // Heavy 65 Hz diesel cylinder firing + 120 Hz track vibration + harmonics
        (2.0 * PI * 65.0 * t).sin() * 0.45
            + (2.0 * PI * 130.0 * t).sin() * 0.35
            + (2.0 * PI * 195.0 * t).sin() * 0.20
    });

    assert!(
        out_sdr > in_sdr,
        "Tank rumble enhanced SDR must exceed input SDR"
    );
}

#[test]
fn test_dataset_benchmark_helicopter_cockpit_rotor_wash() {
    let (_, out_sdr, in_pesq, out_pesq) = run_noise_benchmark("HELI_MI17_ROTOR", |n, t| {
        // Blade pass frequency (21 Hz modulation) + turbine whine (1850 Hz)
        let bpf_mod = 0.5 * (1.0 + (2.0 * PI * 21.0 * t).sin());
        let turbine = (2.0 * PI * 1850.0 * t).sin() * 0.25;
        let broadband = ((n % 13) as f32 - 6.0) / 15.0;
        (broadband * bpf_mod) + turbine
    });

    assert!(out_sdr > 4.0, "Helicopter enhanced SDR must be > 4.0 dB");
    assert!(
        out_pesq >= in_pesq,
        "PESQ score must improve under rotor wash"
    );
}

#[test]
fn test_dataset_benchmark_infantry_toc_babble() {
    let (_, out_sdr, _, out_pesq) = run_noise_benchmark("INFANTRY_TOC_BABBLE", |_n, t| {
        // Interfering off-axis multi-talker frequencies (280 Hz, 520 Hz, 940 Hz, 1420 Hz)
        (2.0 * PI * 280.0 * t).sin() * 0.25
            + (2.0 * PI * 520.0 * t).sin() * 0.20
            + (2.0 * PI * 940.0 * t).sin() * 0.15
            + (2.0 * PI * 1420.0 * t).sin() * 0.10
    });

    assert!(out_sdr > 5.0, "Babble noise enhanced SDR must be > 5.0 dB");
    assert!(out_pesq >= 2.5, "PESQ MOS under babble must be acceptable");
}

#[test]
fn test_dataset_benchmark_artillery_gunfire_impulse() {
    let (_, out_sdr, _, out_pesq) = run_noise_benchmark("ARTILLERY_BLAST_IMPULSE", |n, _t| {
        // Periodic muzzle blast impulses every 1000 samples with exponential decay
        let period = 1000;
        let pos = n % period;
        if pos < 150 {
            let decay = (-(pos as f32) / 30.0).exp();
            decay * 0.8 * ((n % 5) as f32 - 2.0)
        } else {
            0.02 * ((n % 3) as f32 - 1.0)
        }
    });

    assert!(
        out_sdr > 6.0,
        "Gunfire impulse enhanced SDR must be > 6.0 dB"
    );
    assert!(
        out_pesq >= 2.5,
        "PESQ MOS under impulse noise must be acceptable"
    );
}

#[test]
fn test_dataset_benchmark_gtcrn_deep_filter_model() {
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
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(config);
    let mut model = GtcrnDeepFilterModel::new(num_bins, sample_rate);

    let total_hops = 100;
    let total_samples = total_hops * hop_size;

    let mut clean = Vec::with_capacity(total_samples);
    let mut noisy_m1 = Vec::with_capacity(total_samples);
    let mut noisy_m2 = Vec::with_capacity(total_samples);
    let mut enhanced = Vec::with_capacity(total_samples);

    for n in 0..total_samples {
        let t = n as f32 / sample_rate;
        let speech = (2.0 * PI * 220.0 * t).sin() * 0.40 + (2.0 * PI * 440.0 * t).sin() * 0.25;
        let noise = (2.0 * PI * 80.0 * t).sin() * 0.35 + (((n % 7) as f32 - 3.0) / 10.0);
        clean.push(speech);
        noisy_m1.push(speech + noise);
        noisy_m2.push(speech + noise * 0.9);
    }

    let mut out_frame = [0.0f32; 256];
    for h in 0..total_hops {
        let offset = h * hop_size;
        let mic1 = &noisy_m1[offset..offset + hop_size];
        let mic2 = &noisy_m2[offset..offset + hop_size];

        pipeline
            .process_hop(mic1, Some(mic2), &mut model, &mut out_frame)
            .expect("GTCRN process_hop must succeed");

        enhanced.extend_from_slice(&out_frame);
    }

    let delay = hop_size;
    let eval_start = 20 * hop_size;
    let eval_end = total_samples - delay;

    let in_sdr = compute_si_sdr(
        &clean[eval_start..eval_end],
        &noisy_m1[eval_start..eval_end],
    );
    let out_sdr = compute_si_sdr(
        &clean[eval_start..eval_end],
        &enhanced[(eval_start + delay)..(eval_end + delay)],
    );

    println!(
        "[GTCRN-cDF Benchmark] In SDR: {:.2} dB -> Out SDR: {:.2} dB (Gain: +{:.2} dB)",
        in_sdr,
        out_sdr,
        out_sdr - in_sdr
    );

    assert!(
        out_sdr > in_sdr,
        "GTCRN-cDF enhanced SDR ({:.2} dB) must exceed input SDR ({:.2} dB)",
        out_sdr,
        in_sdr
    );
    assert_eq!(model.algorithmic_lookahead_samples(), 0);
}
