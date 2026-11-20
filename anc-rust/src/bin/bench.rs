//! Real-time latency, throughput, and RTF micro-benchmarking suite for SIH 26052.

use anc_rust::dsp::{MvdrConfig, WindowType};
use anc_rust::model::TractEnhancer;
use anc_rust::streaming::{PipelineConfig, TacticalAncPipeline};
use clap::Parser;
use std::time::Instant;

#[derive(Parser, Debug)]
#[command(
    name = "anc-bench",
    author,
    version,
    about = "SIH 26052 Latency & RTF Benchmark"
)]
struct Args {
    #[arg(long, default_value_t = 512)]
    n_fft: usize,

    #[arg(long, default_value_t = 128)]
    hop_size: usize,

    #[arg(long, default_value_t = 16000)]
    sample_rate: usize,

    #[arg(long, default_value_t = 500)]
    iterations: usize,

    #[arg(long, default_value = "asymmetric")]
    window: String,
}

fn main() {
    let args = Args::parse();

    println!("============================================================");
    println!("  SIH 26052 REAL-TIME EMBEDDED LATENCY & RTF BENCHMARK");
    println!("============================================================");
    println!("Target Platform: Embedded ARM Cortex-A76 / x86_64 Host");
    println!(
        "Configuration: n_fft={}, hop_size={}, fs={} Hz",
        args.n_fft, args.hop_size, args.sample_rate
    );

    let window_type = if args.window == "asymmetric" {
        WindowType::AsymmetricLowLatency
    } else {
        WindowType::Hann
    };

    let pipeline_config = PipelineConfig {
        n_fft: args.n_fft,
        hop_size: args.hop_size,
        sample_rate: args.sample_rate as f32,
        window_type,
        enable_mvdr: true,
        enable_agc: true,
        enable_limiter: true,
        mvdr_config: MvdrConfig {
            num_bins: args.n_fft / 2 + 1,
            sample_rate: args.sample_rate as f32,
            ..Default::default()
        },
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(pipeline_config);
    let mut model = TractEnhancer::new_fallback("Analytic-Wiener-Fallback", args.n_fft / 2 + 1, 32);

    let hop_duration_ms = (args.hop_size as f32 / args.sample_rate as f32) * 1000.0;
    let framing_latency_ms = match window_type {
        WindowType::AsymmetricLowLatency => {
            (args.n_fft as f32 * 0.25 / args.sample_rate as f32) * 1000.0
        }
        _ => (args.n_fft as f32 / args.sample_rate as f32) * 1000.0,
    };

    let mic1_in = vec![0.1f32; args.hop_size];
    let mic2_in = vec![0.1f32; args.hop_size];
    let mut out = vec![0.0f32; args.hop_size];

    // Warm-up cycles
    for _ in 0..50 {
        let _ = pipeline.process_hop(&mic1_in, Some(&mic2_in), &mut model, &mut out);
    }

    println!(
        "\nExecuting {} streaming iteration steps...",
        args.iterations
    );
    let mut latencies_us = Vec::with_capacity(args.iterations);

    let t_start = Instant::now();
    for _ in 0..args.iterations {
        let step_t0 = Instant::now();
        let _ = pipeline.process_hop(&mic1_in, Some(&mic2_in), &mut model, &mut out);
        latencies_us.push(step_t0.elapsed().as_micros() as u64);
    }
    let total_elapsed = t_start.elapsed();

    latencies_us.sort_unstable();
    let p50 = latencies_us[latencies_us.len() * 50 / 100] as f32 * 0.001;
    let p95 = latencies_us[latencies_us.len() * 95 / 100] as f32 * 0.001;
    let p99 = latencies_us[latencies_us.len() * 99 / 100] as f32 * 0.001;
    let max = *latencies_us.last().unwrap() as f32 * 0.001;

    let total_audio_ms = args.iterations as f32 * hop_duration_ms;
    let total_compute_ms = total_elapsed.as_secs_f32() * 1000.0;
    let rtf = total_compute_ms / total_audio_ms;

    // Projected total capture-to-playout round-trip latency
    // Latency = Framing + Compute + Double-buffered I/O (e.g. 2 x 4 ms)
    let io_buffer_ms = 8.0f32;
    let total_roundtrip_ms = framing_latency_ms + p99 + io_buffer_ms;

    println!("\n------------------ BENCHMARK RESULTS ------------------");
    println!(
        "Hop Frame Duration:        {:.2} ms ({} samples)",
        hop_duration_ms, args.hop_size
    );
    println!("STFT Framing Latency:      {:.2} ms", framing_latency_ms);
    println!("Inference Compute (Median):{:.3} ms", p50);
    println!("Inference Compute (P95):   {:.3} ms", p95);
    println!("Inference Compute (P99):   {:.3} ms", p99);
    println!("Inference Compute (Max):   {:.3} ms", max);
    println!(
        "Real-Time Factor (RTF):    {:.4} (Headroom: {:.1}x real-time)",
        rtf,
        1.0 / rtf.max(1e-4)
    );
    println!(
        "Projected Roundtrip Delay: {:.2} ms (Gate: <= 35.0 ms)",
        total_roundtrip_ms
    );

    if total_roundtrip_ms <= 35.0 {
        println!("\n>>> QUALIFICATION GATE STATUS: [PASS] (<= 35.0 ms)");
    } else {
        println!(
            "\n>>> QUALIFICATION GATE STATUS: [FAIL] ({:.2} ms > 35.0 ms)",
            total_roundtrip_ms
        );
        println!("    Recommendation: To pass 35 ms, switch from symmetric 512-window to");
        println!("    asymmetric low-latency window or 256/128 framing.");
    }
    println!("============================================================");
}
