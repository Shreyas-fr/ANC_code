//! Offline WAV batch speech enhancement and objective validation tool.

use clap::Parser;
use hound::{WavReader, WavSpec, WavWriter};
use std::path::PathBuf;
use std::time::Instant;

use anc_rust::dsp::{MvdrConfig, WindowType};
use anc_rust::metrics::{compute_explicit_snr, compute_si_sdr};
use anc_rust::model::{
    AdaptiveSpectralEnhancer, Dfn3Enhancer, FrozenEnsemble, FullSubNetEnhancer, GtcrnEnhancer,
    SpeechEnhancer, TractEnhancer,
};
use anc_rust::streaming::{PipelineConfig, TacticalAncPipeline};

#[derive(Parser, Debug)]
#[command(
    name = "anc-process",
    author,
    version,
    about = "Batch Speech Enhancement & Objective Validation"
)]
struct Args {
    #[arg(short, long)]
    input: PathBuf,

    #[arg(short, long)]
    output: PathBuf,

    #[arg(short, long)]
    clean_ref: Option<PathBuf>,

    #[arg(long)]
    onnx_model: Option<PathBuf>,

    #[arg(long, default_value = "ensemble")]
    model: String,

    #[arg(long, default_value_t = 512)]
    n_fft: usize,

    #[arg(long, default_value_t = 256)]
    hop_size: usize,

    #[arg(long)]
    aggressive_snr: bool,

    #[arg(long)]
    spectral: bool,

    #[arg(long)]
    enable_agc: bool,

    #[arg(long)]
    enable_limiter: bool,

    #[arg(long)]
    enable_doa: bool,

    #[arg(long)]
    enable_pitch_comb: bool,

    #[arg(long)]
    enable_ashp: bool,

    #[arg(long)]
    enable_dereverb: bool,

    #[arg(long)]
    no_align_delay: bool,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = Args::parse();

    println!("Loading audio from: {:?}", args.input);
    let mut reader = WavReader::open(&args.input)?;
    let spec = reader.spec();
    let sample_rate = spec.sample_rate as f32;
    let channels = spec.channels as usize;

    let samples: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => reader.samples::<f32>().map(|s| s.unwrap()).collect(),
        hound::SampleFormat::Int => {
            let max_val = (1 << (spec.bits_per_sample - 1)) as f32;
            reader
                .samples::<i32>()
                .map(|s| s.unwrap() as f32 / max_val)
                .collect()
        }
    };

    let total_frames = samples.len() / channels;
    let mut mic1 = Vec::with_capacity(total_frames);
    let mut mic2 = if channels >= 2 {
        Some(Vec::with_capacity(total_frames))
    } else {
        None
    };

    for chunk in samples.chunks_exact(channels) {
        mic1.push(chunk[0]);
        if let Some(ref mut m2) = mic2 {
            m2.push(chunk[1]);
        }
    }

    println!(
        "Audio loaded: {} frames, {} channels, {} Hz ({:.2} s)",
        total_frames,
        channels,
        sample_rate,
        total_frames as f32 / sample_rate
    );

    let num_bins = args.n_fft / 2 + 1;

    let pipeline_config = PipelineConfig {
        n_fft: args.n_fft,
        hop_size: args.hop_size,
        sample_rate,
        window_type: WindowType::Hann,
        enable_mvdr: mic2.is_some(),
        enable_agc: args.enable_agc,
        enable_limiter: args.enable_limiter,
        aggressive_snr: args.aggressive_snr,
        enable_doa_tracking: args.enable_doa,
        enable_pitch_comb: args.enable_pitch_comb,
        enable_ashp: args.enable_ashp,
        enable_dereverb: args.enable_dereverb,
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
            weight_smoothing: 0.60,
            ..Default::default()
        },
        ..Default::default()
    };

    let mut pipeline = TacticalAncPipeline::new(pipeline_config);

    let mut model: Box<dyn SpeechEnhancer> = if let Some(ref onnx_path) = args.onnx_model {
        println!("Loading custom ONNX neural model: {:?}", onnx_path);
        Box::new(TractEnhancer::load_from_onnx(
            onnx_path,
            "Tract-ONNX",
            num_bins,
            32,
            0,
        )?)
    } else if args.spectral || args.model.to_lowercase() == "spectral" {
        println!("Using Decision-Directed Adaptive ERB Spectral Enhancer.");
        Box::new(AdaptiveSpectralEnhancer::new(num_bins, 32, sample_rate))
    } else {
        match args.model.to_lowercase().as_str() {
            "gtcrn" => {
                println!("Using GTCRN DNS-3 Neural Speech Enhancer (tract-onnx).");
                Box::new(GtcrnEnhancer::new(num_bins, sample_rate))
            }
            "fullsubnet" => {
                println!("Using FullSubNet Epoch 58 Neural Speech Enhancer (tract-onnx).");
                Box::new(FullSubNetEnhancer::new(num_bins, sample_rate))
            }
            "dfn3" => {
                println!("Using DeepFilterNet3 Step-500 Neural Speech Enhancer (tract-onnx).");
                Box::new(Dfn3Enhancer::new(num_bins, sample_rate))
            }
            _ => {
                println!("Using Authoritative B0 Heterogeneous Ensemble (15% DFN3 + 70% FullSubNet + 15% GTCRN).");
                Box::new(FrozenEnsemble::create_b0(sample_rate, num_bins))
            }
        }
    };

    if args.aggressive_snr {
        println!("Aggressive Max SNR Optimization Mode: ENGAGED");
        pipeline.set_aggressive_snr(true, Some(model.as_mut()));
        model.set_aggressive_snr(true);
    }

    let mut enhanced_output = Vec::with_capacity(total_frames);
    let mut hop_out = vec![0.0f32; args.hop_size];

    let t0 = Instant::now();
    let num_hops = total_frames / args.hop_size;

    for i in 0..num_hops {
        let start = i * args.hop_size;
        let end = start + args.hop_size;
        let m1_slice = &mic1[start..end];
        let m2_slice = mic2.as_ref().map(|m| &m[start..end]);

        let _ = pipeline.process_hop(m1_slice, m2_slice, model.as_mut(), &mut hop_out)?;
        enhanced_output.extend_from_slice(&hop_out);
    }

    let elapsed = t0.elapsed();
    let rtf = elapsed.as_secs_f32() / (total_frames as f32 / sample_rate);

    println!(
        "Processing complete in {:.2} s (RTF: {:.4}, {:.1}x real-time)",
        elapsed.as_secs_f32(),
        rtf,
        1.0 / rtf.max(1e-4)
    );

    // Account for framing delay (256 samples / 1 hop) to ensure phase alignment
    let delay = if args.no_align_delay {
        0
    } else {
        pipeline.algorithmic_delay_samples()
    };

    let mut aligned_output = Vec::with_capacity(total_frames);
    if delay > 0 && enhanced_output.len() > delay {
        aligned_output.extend_from_slice(&enhanced_output[delay..]);
        // Pad tail with zeros to preserve exact file length
        aligned_output.resize(total_frames, 0.0);
    } else {
        aligned_output.extend_from_slice(&enhanced_output);
        aligned_output.resize(total_frames, 0.0);
    }

    // Save output WAV
    let out_spec = WavSpec {
        channels: 1,
        sample_rate: spec.sample_rate,
        bits_per_sample: 32,
        sample_format: hound::SampleFormat::Float,
    };
    let mut writer = WavWriter::create(&args.output, out_spec)?;
    for &sample in &aligned_output {
        writer.write_sample(sample)?;
    }
    writer.finalize()?;
    println!("Enhanced audio written to: {:?}", args.output);

    // Objective scoring if clean reference is provided
    if let Some(ref clean_path) = args.clean_ref {
        println!(
            "\nCalculating objective metrics against clean reference: {:?}",
            clean_path
        );
        let mut clean_reader = WavReader::open(clean_path)?;
        let clean_spec = clean_reader.spec();
        let clean_samples: Vec<f32> = match clean_spec.sample_format {
            hound::SampleFormat::Float => {
                clean_reader.samples::<f32>().map(|s| s.unwrap()).collect()
            }
            hound::SampleFormat::Int => {
                let max_val = (1 << (clean_spec.bits_per_sample - 1)) as f32;
                clean_reader
                    .samples::<i32>()
                    .map(|s| s.unwrap() as f32 / max_val)
                    .collect()
            }
        };

        let eval_len = clean_samples.len().min(aligned_output.len());
        if eval_len > 0 {
            let c_eval = &clean_samples[..eval_len];
            let e_eval = &aligned_output[..eval_len];
            let n_eval = &mic1[..eval_len];

            let in_sisdr = compute_si_sdr(c_eval, n_eval);
            let out_sisdr = compute_si_sdr(c_eval, e_eval);
            let in_snr = compute_explicit_snr(c_eval, n_eval);
            let out_snr = compute_explicit_snr(c_eval, e_eval);

            println!("Input SI-SDR:     {:.2} dB", in_sisdr);
            println!(
                "Output SI-SDR:    {:.2} dB (Delta: {:+.2} dB)",
                out_sisdr,
                out_sisdr - in_sisdr
            );
            println!("Input SNR:        {:.2} dB", in_snr);
            println!(
                "Output SNR:       {:.2} dB (Delta: {:+.2} dB)",
                out_snr,
                out_snr - in_snr
            );
        }
    }

    Ok(())
}
