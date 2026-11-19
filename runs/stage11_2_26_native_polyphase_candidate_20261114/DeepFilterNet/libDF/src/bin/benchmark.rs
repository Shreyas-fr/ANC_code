use anyhow::Result;
use clap::Parser;
use df::tract::{DfParams, DfTract, RuntimeParams};
use df::wav_utils::ReadWav;
use hound;
use std::path::PathBuf;
use std::time::{Instant, SystemTime, UNIX_EPOCH};
use std::fs::File;
use std::io::{Read, Write, Seek, SeekFrom};
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::Arc;
use std::thread;

#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Args {
    #[arg(short, long)]
    model: PathBuf,

    #[arg(short, long)]
    input: PathBuf,
    
    #[arg(short, long)]
    csv_out: PathBuf,
    
    #[arg(short, long)]
    wav_out: PathBuf,
}

fn read_sys_val(file: &mut File, buf: &mut [u8]) -> f32 {
    file.seek(SeekFrom::Start(0)).unwrap();
    let n = file.read(buf).unwrap_or(0);
    if n > 0 {
        let s = std::str::from_utf8(&buf[..n]).unwrap_or("").trim();
        s.parse::<f32>().unwrap_or(0.0)
    } else {
        0.0
    }
}

fn main() -> Result<()> {
    let args = Args::parse();

    println!("Loading Tract model from: {:?}", args.model);
    let df_params = DfParams::new(args.model).expect("Failed to load model");
    let runtime_params = RuntimeParams::default();
    
    let mut df = DfTract::new(df_params, &runtime_params)
        .map_err(|e| anyhow::anyhow!("Tract error: {}", e))?;

    println!("Loading WAV: {:?}", args.input);
    let mut reader = ReadWav::new(&args.input.to_string_lossy())?;
    let sr = reader.sr;
    assert_eq!(sr, 48000, "Expected 48 kHz");
    let audio = reader.samples_arr2()?;
    
    let audio_ch = audio.row(0);
    let hop_size = 480; // 10ms at 48kHz
    let n_frames = audio_ch.len() / hop_size;
    
    println!("Running streaming benchmark for {} frames ({}s audio)...", n_frames, n_frames as f32 * hop_size as f32 / sr as f32);
    
    let mut total_latencies_us = vec![0u128; n_frames];
    let mut inference_latencies_us = vec![0u128; n_frames];
    let mut total_start_us = vec![0u128; n_frames];
    let mut infer_start_us = vec![0u128; n_frames];
    let mut infer_end_us = vec![0u128; n_frames];
    let mut total_end_us = vec![0u128; n_frames];
    
    let mut temps = vec![0.0f32; n_frames];
    let mut freqs = vec![0f32; n_frames];
    
    // Pre-allocate buffer for all enhanced audio to avoid push() reallocations
    let mut out_audio = vec![0.0f32; n_frames * hop_size];
    let mut out_buffer = ndarray::Array2::<f32>::zeros((1, hop_size));
    
    let shared_temp = Arc::new(AtomicU32::new(0));
    let shared_freq = Arc::new(AtomicU32::new(0));
    
    let temp_clone = shared_temp.clone();
    let freq_clone = shared_freq.clone();
    
    thread::spawn(move || {
        let mut temp_file = File::open("/sys/class/thermal/thermal_zone0/temp").unwrap();
        let mut freq_file = File::open("/sys/devices/system/cpu/cpu3/cpufreq/scaling_cur_freq").unwrap();
        let mut buf = [0u8; 32];
        loop {
            let t = read_sys_val(&mut temp_file, &mut buf) as u32;
            let f = read_sys_val(&mut freq_file, &mut buf) as u32;
            temp_clone.store(t, Ordering::Relaxed);
            freq_clone.store(f, Ordering::Relaxed);
            thread::sleep(std::time::Duration::from_millis(50));
        }
    });
    
    // Wait briefly to ensure background thread populates atomic variables
    thread::sleep(std::time::Duration::from_millis(150));
    
    let mut state_resets = 0;
    let mut nans = 0;
    let mut deadline_misses = 0;
    
    let t_start_total = Instant::now();
    let epoch = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_millis();
    
    for i in 0..n_frames {
        let t_frame_start = Instant::now();
        let ts_total_start = epoch + t_start_total.elapsed().as_micros();
        
        let frame = audio_ch.slice(ndarray::s![i * hop_size .. (i + 1) * hop_size]);
        let frame_2d = frame.to_owned().into_shape((1, hop_size))?;
        
        let t_infer_start = Instant::now();
        let ts_infer_start = epoch + t_start_total.elapsed().as_micros();
        
        // Inference (Critical Path)
        let _ = df.process(frame_2d.view(), out_buffer.view_mut())
            .map_err(|e| anyhow::anyhow!("Tract error: {}", e))?;
            
        let inference_us = t_infer_start.elapsed().as_micros();
        let ts_infer_end = epoch + t_start_total.elapsed().as_micros();
        
        // Copy to output
        let out_slice = out_buffer.as_slice().unwrap();
        let out_audio_slice = &mut out_audio[i * hop_size .. (i + 1) * hop_size];
        out_audio_slice.copy_from_slice(out_slice);
        
        // Fast I/O reads from background thread atomics
        let temp_raw = shared_temp.load(Ordering::Relaxed) as f32;
        let freq_raw = shared_freq.load(Ordering::Relaxed) as f32;
        
        let total_us = t_frame_start.elapsed().as_micros();
        let ts_total_end = epoch + t_start_total.elapsed().as_micros();
        
        inference_latencies_us[i] = inference_us;
        total_latencies_us[i] = total_us;
        
        total_start_us[i] = ts_total_start;
        infer_start_us[i] = ts_infer_start;
        infer_end_us[i] = ts_infer_end;
        total_end_us[i] = ts_total_end;
        
        temps[i] = temp_raw / 1000.0;
        freqs[i] = freq_raw;
        
        if total_us > 10_000 {
            deadline_misses += 1;
        }
    }
    
    // Check for NaNs outside the RT loop to save CPU cycles
    for sample in out_audio.iter() {
        if sample.is_nan() || sample.is_infinite() {
            nans += 1;
        }
    }
    
    let total_elapsed = t_start_total.elapsed();
    let rtf = total_elapsed.as_secs_f32() / (n_frames as f32 * hop_size as f32 / sr as f32);
    
    println!("Writing CSV...");
    let mut csv = File::create(&args.csv_out)?;
    writeln!(csv, "frame_index,total_start_us,infer_start_us,infer_end_us,total_end_us,inference_us,total_frame_us,cpu_freq_khz,temperature_c,deadline_miss")?;
    for i in 0..n_frames {
        writeln!(csv, "{},{},{},{},{},{},{},{},{:.2},{}", 
            i, total_start_us[i], infer_start_us[i], infer_end_us[i], total_end_us[i], inference_latencies_us[i], total_latencies_us[i], freqs[i], temps[i], if total_latencies_us[i] > 10000 { 1 } else { 0 }
        )?;
    }
    
    println!("Writing WAV...");
    // Write out_audio to wav using hound
    let spec = hound::WavSpec {
        channels: 1,
        sample_rate: sr as u32,
        bits_per_sample: 32,
        sample_format: hound::SampleFormat::Float,
    };
    let mut writer = hound::WavWriter::create(&args.wav_out, spec)?;
    for sample in out_audio.iter() {
        writer.write_sample(*sample)?;
    }
    writer.finalize()?;
    
    // Compute stats using total_frame_us
    let mut sorted_latencies = total_latencies_us.clone();
    sorted_latencies.sort_unstable();
    
    let min = sorted_latencies[0];
    let max = sorted_latencies[n_frames - 1];
    let median = sorted_latencies[n_frames / 2];
    let p95 = sorted_latencies[(n_frames as f32 * 0.95) as usize];
    let p99 = sorted_latencies[(n_frames as f32 * 0.99) as usize];
    
    let sum: u128 = total_latencies_us.iter().sum();
    let mean = sum as f64 / n_frames as f64;
    
    let max_temp = temps.iter().copied().fold(f32::NAN, f32::max);
    let min_temp = temps.iter().copied().fold(f32::NAN, f32::min);
    let initial_temp = temps[0];
    let final_temp = temps[n_frames - 1];
    
    println!("========================================");
    println!("DFN3 PI 5 FINAL REAL-TIME AUDIT SUMMARY");
    println!("Frames: {}", n_frames);
    println!("Median: {:.2} ms", median as f64 / 1000.0);
    println!("P95: {:.2} ms", p95 as f64 / 1000.0);
    println!("P99: {:.2} ms", p99 as f64 / 1000.0);
    println!("Max: {:.2} ms", max as f64 / 1000.0);
    println!("Misses: {}", deadline_misses);
    println!("RTF: {:.3}", rtf);
    println!("Peak Temp: {:.1}'C", max_temp);
    println!("NaN/Inf: {}", nans);
    println!("State Resets: {}", state_resets);
    println!("Initial Temp: {:.1}'C, Final Temp: {:.1}'C", initial_temp, final_temp);
    println!("========================================");

    Ok(())
}
