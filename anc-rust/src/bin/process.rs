//! Offline WAV batch speech enhancement and objective validation tool.

use clap::Parser;
use hound::{WavReader, WavSpec, WavWriter};
use std::path::PathBuf;
use std::time::Instant;

use anc_rust::dsp::{MvdrConfig, WindowType};
use anc_rust::metrics::{compute_explicit_snr, compute_si_sdr};
use anc_rust::model::TractEnhancer;
use anc_rust::streaming::{PipelineConfig, TacticalAncPipeline};

#[derive(Parser, Debug)]
#[command(name = "anc-process", author, version, about = "Batch Speech Enhancement & Objective Validation")]
struct Args {
    #[arg(short, long)]
    input: PathBuf,

    #[arg(short, long)]
    output: PathBuf,

    #[arg(short, long)]
    clean_ref: Option<PathBuf>,

    #[arg(long)]
    onnx_model: Option<PathBuf>,

    #[arg(long, default_value_t = 512)]
    n_fft: usize,

    #[arg(long, default_value_t = 256)]
    hop_size: usize,
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
            reader.samples::<i32>().map(|s| s.unwrap() as f32 / max_val).collect()
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

    println!("Audio loaded: {} frames, {} channels, {} Hz ({:.2} s)",
        total_frames, channels, sample_rate, total_frames as f32 / sample_rate);

    let pipeline_config = PipelineConfig {
        n_fft: args.n_fft,
        hop_size: args.hop_size,
        sample_rate,
        window_type: WindowType::Hann,
        enable_mvdr: mic2.is_some(),
        enable_agc: true,
        enable_limiter: true,
        mvdr_config: MvdrConfig {
            num_bins: args.n_fft / 2 + 1,
            sample_rate,
            ..Default::default()
        },
    };

    let mut pipeline = TacticalAncPipeline::new(pipeline_config);

    let mut model = if let Some(ref onnx_path) = args.onnx_model {
        println!("Loading neural model from ONNX: {:?}", onnx_path);
        TractEnhancer::load_from_onnx(onnx_path, "Tract-ONNX", args.n_fft / 2 + 1, 32, 0)?
    } else {
        println!("Using Analytic Wiener filter fallback engine.");
        TractEnhancer::new_fallback("Analytic-Fallback", args.n_fft / 2 + 1, 32)
    };

    let mut enhanced_output = Vec::with_capacity(total_frames);
    let mut hop_out = vec![0.0f32; args.hop_size];

    let t0 = Instant::now();
    let num_hops = total_frames / args.hop_size;

    for i in 0..num_hops {
        let start = i * args.hop_size;
        let end = start + args.hop_size;
        let m1_slice = &mic1[start..end];
        let m2_slice = mic2.as_ref().map(|m| &m[start..end]);

        let _ = pipeline.process_hop(m1_slice, m2_slice, &mut model, &mut hop_out)?;
        enhanced_output.extend_from_slice(&hop_out);
    }

    let elapsed = t0.elapsed();
    let rtf = elapsed.as_secs_f32() / (total_frames as f32 / sample_rate);

    println!("Processing complete in {:.2} s (RTF: {:.4}, {:.1}x real-time)",
        elapsed.as_secs_f32(), rtf, 1.0 / rtf.max(1e-4));

    // Save output WAV
    let out_spec = WavSpec {
        channels: 1,
        sample_rate: spec.sample_rate,
        bits_per_sample: 32,
        sample_format: hound::SampleFormat::Float,
    };
    let mut writer = WavWriter::create(&args.output, out_spec)?;
    for &sample in &enhanced_output {
        writer.write_sample(sample)?;
    }
    writer.finalize()?;
    println!("Enhanced audio written to: {:?}", args.output);

    // Objective scoring if clean reference is provided
    if let Some(ref clean_path) = args.clean_ref {
        println!("\nCalculating objective metrics against clean reference: {:?}", clean_path);
        let mut clean_reader = WavReader::open(clean_path)?;
        let clean_spec = clean_reader.spec();
        let clean_samples: Vec<f32> = match clean_spec.sample_format {
            hound::SampleFormat::Float => clean_reader.samples::<f32>().map(|s| s.unwrap()).collect(),
            hound::SampleFormat::Int => {
                let max_val = (1 << (clean_spec.bits_per_sample - 1)) as f32;
                clean_reader.samples::<i32>().map(|s| s.unwrap() as f32 / max_val).collect()
            }
        };

        // Account for framing delay
        let delay = pipeline.algorithmic_delay_samples();
        if clean_samples.len() > delay && enhanced_output.len() > delay {
            let eval_len = (clean_samples.len() - delay).min(enhanced_output.len() - delay);
            let c_eval = &clean_samples[..eval_len];
            let e_eval = &enhanced_output[delay..delay + eval_len];
            let n_eval = &mic1[..eval_len];

            let in_sisdr = compute_si_sdr(c_eval, n_eval);
            let out_sisdr = compute_si_sdr(c_eval, e_eval);
            let in_snr = compute_explicit_snr(c_eval, n_eval);
            let out_snr = compute_explicit_snr(c_eval, e_eval);

            println!("Input SI-SDR:     {:.2} dB", in_sisdr);
            println!("Output SI-SDR:    {:.2} dB (Delta: {:+.2} dB)", out_sisdr, out_sisdr - in_sisdr);
            println!("Input SNR:        {:.2} dB", in_snr);
            println!("Output SNR:       {:.2} dB (Delta: {:+.2} dB)", out_snr, out_snr - in_snr);
        }
    }

    Ok(())
}
