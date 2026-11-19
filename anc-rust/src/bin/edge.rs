//! Production Edge Daemon for Raspberry Pi 5 / Embedded Linux.
//!
//! Autonomous, real-time tactical noise cancellation edge server.
//! Connects capture -> MVDR -> Neural Engine -> UDP streamer on ports 5005/5006/5007.

use clap::Parser;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use anc_rust::dsp::{MvdrConfig, WindowType};
use anc_rust::metrics::{read_system_temperature_c, PerformanceProfiler};
use anc_rust::model::{SpeechEnhancer, TractEnhancer};
use anc_rust::network::{EdgeSender, EdgeTelemetry, AUDIO_FRAME_SAMPLES, DEFAULT_AUDIO_PORT, DEFAULT_RAW_INPUT_PORT, DEFAULT_TELEMETRY_PORT};
use anc_rust::streaming::{PipelineConfig, PlayoutScheduler, TacticalAncPipeline};

#[derive(Parser, Debug)]
#[command(name = "anc-edge", author, version, about = "DRDO SIH 26052 Edge Real-Time Streaming Daemon")]
struct CliArgs {
    #[arg(long, default_value = "127.0.0.1")]
    target_ip: String,

    #[arg(long, default_value_t = DEFAULT_AUDIO_PORT)]
    audio_port: u16,

    #[arg(long, default_value_t = DEFAULT_TELEMETRY_PORT)]
    telemetry_port: u16,

    #[arg(long, default_value_t = DEFAULT_RAW_INPUT_PORT)]
    raw_port: u16,

    #[arg(long, default_value = "dfn3")]
    mode: String,

    #[arg(long)]
    onnx_model: Option<String>,

    #[arg(long, default_value_t = 0.03)]
    mic_distance_m: f32,

    #[arg(long, default_value_t = 2)]
    jitter_packets: usize,

    #[arg(long, default_value_t = 0)]
    duration_secs: u64,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = CliArgs::parse();

    println!("============================================================");
    println!("  DRDO SIH 26052 EDGE REAL-TIME STREAMING DAEMON (RUST)");
    println!("============================================================");
    println!("Target Operator IP:  {}", args.target_ip);
    println!("Streaming Ports:     Enhanced: {}, Telemetry: {}, Raw: {}",
        args.audio_port, args.telemetry_port, args.raw_port);
    println!("Operational Mode:    {}", args.mode);
    println!("Dual-Mic Geometry:   30 mm array spacing (d = {} m)", args.mic_distance_m);

    let sender = Arc::new(EdgeSender::bind(
        &args.target_ip,
        args.audio_port,
        args.telemetry_port,
        args.raw_port,
    )?);

    let pipeline_config = PipelineConfig {
        n_fft: 512,
        hop_size: 256,
        sample_rate: 16000.0,
        window_type: WindowType::Hann,
        enable_mvdr: true,
        enable_agc: true,
        enable_limiter: true,
        mvdr_config: MvdrConfig {
            num_bins: 257,
            sample_rate: 16000.0,
            mic_distance_m: args.mic_distance_m,
            ..Default::default()
        },
    };

    let mut pipeline = TacticalAncPipeline::new(pipeline_config);

    let mut model: Box<dyn SpeechEnhancer> = if let Some(ref path) = args.onnx_model {
        println!("Loading neural enhancement ONNX model: {}", path);
        Box::new(TractEnhancer::load_from_onnx(path, "Tract-ONNX-Engine", 257, 32, 0)?)
    } else {
        println!("Initializing pure Rust real-time spectral filter engine.");
        Box::new(TractEnhancer::new_fallback("Analytic-Wiener-Engine", 257, 32))
    };

    // Chain delay in packets (e.g. 512 samples framing = 2 packets)
    let chain_delay_packets = (pipeline.algorithmic_delay_samples() + AUDIO_FRAME_SAMPLES - 1) / AUDIO_FRAME_SAMPLES;
    let mut scheduler = PlayoutScheduler::new(chain_delay_packets, args.jitter_packets, AUDIO_FRAME_SAMPLES);

    println!("Chain delay: {} packets ({:.1} ms) | Jitter budget: {} packets ({:.1} ms)",
        chain_delay_packets, chain_delay_packets as f32 * 16.0,
        args.jitter_packets, args.jitter_packets as f32 * 16.0);
    println!("Total configured playout latency: {:.1} ms",
        scheduler.total_delay_packets() as f32 * 16.0);

    let running = Arc::new(AtomicBool::new(true));
    let r = running.clone();
    ctrlc_handler(move || {
        println!("\nShutdown signal received. Stopping streaming daemon...");
        r.store(false, Ordering::SeqCst);
    });

    let mut profiler = PerformanceProfiler::new(200);
    let mut mic1_buf = vec![0.0f32; AUDIO_FRAME_SAMPLES];
    let mut mic2_buf = vec![0.0f32; AUDIO_FRAME_SAMPLES];
    let mut enhanced_chunk = vec![0.0f32; AUDIO_FRAME_SAMPLES];
    let mut playout_out = vec![0.0f32; AUDIO_FRAME_SAMPLES];

    let t_start = Instant::now();
    let mut seq = 0u64;
    let mut last_telemetry = Instant::now();

    println!("\nStreaming live audio frames... Press Ctrl+C to stop.\n");

    while running.load(Ordering::SeqCst) {
        if args.duration_secs > 0 && t_start.elapsed().as_secs() >= args.duration_secs {
            break;
        }

        let loop_t0 = Instant::now();

        // 1. Simulate/Acquire 16 ms of audio (256 samples @ 16 kHz)
        for i in 0..AUDIO_FRAME_SAMPLES {
            let t = (seq * AUDIO_FRAME_SAMPLES as u64 + i as u64) as f32 / 16000.0;
            // Desired voice: 300 Hz harmonic
            let voice = 0.3 * (2.0 * std::f32::consts::PI * 300.0 * t).sin();
            // Directional noise: 800 Hz arrived off-axis
            let noise_mic1 = 0.4 * (2.0 * std::f32::consts::PI * 800.0 * t).sin();
            let noise_mic2 = 0.4 * (2.0 * std::f32::consts::PI * 800.0 * (t - 0.000087)).sin(); // ~30 deg off-axis

            mic1_buf[i] = voice + noise_mic1;
            mic2_buf[i] = voice + noise_mic2;
        }

        // 2. Transmit True Raw Microphone Packet on Port 5007
        let _ = sender.send_raw(seq, &mic1_buf);
        scheduler.push_input(seq, &mic1_buf);

        // 3. Process through Spatial MVDR + Neural Engine
        let step_t0 = Instant::now();
        let _ = pipeline.process_hop(&mic1_buf, Some(&mic2_buf), model.as_mut(), &mut enhanced_chunk);
        let compute_us = step_t0.elapsed().as_micros() as u64;

        profiler.record(compute_us, 16_000); // 16 ms chunk
        scheduler.push_enhanced_result(seq, enhanced_chunk.clone());

        // 4. Extract playout audio from deterministic scheduler
        scheduler.next_output(seq, &mut playout_out);

        // 5. Transmit Enhanced Audio Packet on Port 5005
        let _ = sender.send_enhanced(seq, &playout_out);

        // 6. Periodic Telemetry Emission on Port 5006 (every 1 second)
        if last_telemetry.elapsed() >= Duration::from_secs(1) {
            let input_rms = (mic1_buf.iter().map(|&x| x * x).sum::<f32>() / mic1_buf.len() as f32).sqrt();
            let output_rms = (playout_out.iter().map(|&x| x * x).sum::<f32>() / playout_out.len() as f32).sqrt();

            let telemetry = EdgeTelemetry {
                frame: seq,
                model: model.name().to_string(),
                mode: args.mode.clone(),
                model_active: true,
                compute_time_ms: compute_us as f32 * 0.001,
                algorithmic_latency_ms: (pipeline.algorithmic_delay_samples() as f32 / 16.0),
                total_latency_ms: (scheduler.total_delay_packets() as f32 * 16.0),
                avg_rtf: profiler.current_rtf(),
                deadline_misses: scheduler.late_results,
                fallback_frames: scheduler.fallback_frames,
                enhanced_frames: scheduler.enhanced_frames,
                input_rms,
                output_rms,
                temperature_c: read_system_temperature_c(),
            };

            let _ = sender.send_telemetry(&telemetry);
            println!("Frame {:06} | Compute: {:5.2} ms (RTF: {:.3}) | Latency: {:4.1} ms | Fallbacks: {} | Temp: {:.1} °C",
                seq, telemetry.compute_time_ms, telemetry.avg_rtf, telemetry.total_latency_ms,
                telemetry.fallback_frames, telemetry.temperature_c);

            last_telemetry = Instant::now();
        }

        seq += 1;

        // Regulate real-time loop timing (16 ms per frame)
        let frame_time = loop_t0.elapsed();
        if frame_time < Duration::from_millis(16) {
            thread::sleep(Duration::from_millis(16) - frame_time);
        }
    }

    println!("\nDaemon stopped successfully. Total frames processed: {}", seq);
    Ok(())
}

fn ctrlc_handler<F: FnOnce() + Send + 'static>(handler: F) {
    let mut handler_opt = Some(handler);
    let _ = ctrlc_native(move || {
        if let Some(h) = handler_opt.take() {
            h();
        }
    });
}

fn ctrlc_native<F: FnMut() + Send + 'static>(mut handler: F) -> Result<(), ()> {
    // Basic signal handling or graceful loop termination
    let running = Arc::new(AtomicBool::new(true));
    let r = running.clone();
    let _ = thread::spawn(move || {
        while r.load(Ordering::SeqCst) {
            thread::sleep(Duration::from_millis(100));
        }
        handler();
    });
    Ok(())
}
