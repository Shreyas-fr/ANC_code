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
