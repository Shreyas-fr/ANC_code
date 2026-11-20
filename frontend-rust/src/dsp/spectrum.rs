//! Real-Time FFT Spectral Analyzer for SIH 26052 Dashboard.
//!
//! Computes 0–8 kHz magnitude response (dBFS) across audio frequencies.

use rustfft::{num_complex::Complex32, FftPlanner};
use std::sync::Arc;

pub struct SpectrumAnalyzer {
    n_fft: usize,
    sample_rate: f32,
    window: Vec<f32>,
    fft: Arc<dyn rustfft::Fft<f32>>,
    input_buffer: Vec<Complex32>,
    freq_bins: Vec<f64>,
}

impl SpectrumAnalyzer {
    pub fn new(n_fft: usize, sample_rate: f32) -> Self {
        let mut planner = FftPlanner::new();
        let fft = planner.plan_fft_forward(n_fft);

        // Precompute Hann window
        let window: Vec<f32> = (0..n_fft)
            .map(|i| {
                0.5 * (1.0 - (2.0 * std::f32::consts::PI * i as f32 / (n_fft - 1) as f32).cos())
            })
            .collect();

        // Frequency bins: 0 to fs/2
        let num_bins = n_fft / 2 + 1;
        let bin_hz = sample_rate as f64 / n_fft as f64;
        let freq_bins: Vec<f64> = (0..num_bins).map(|k| k as f64 * bin_hz).collect();

        Self {
            n_fft,
            sample_rate,
            window,
            fft,
            input_buffer: vec![Complex32::new(0.0, 0.0); n_fft],
            freq_bins,
        }
    }

    /// Computes power spectral density in dBFS from the most recent samples.
    pub fn compute_spectrum(&mut self, samples: &[f32], out_db: &mut [f64]) {
        let num_bins = self.n_fft / 2 + 1;
        if out_db.len() != num_bins {
            return;
        }

        let start_idx = if samples.len() >= self.n_fft {
            samples.len() - self.n_fft
        } else {
            0
        };

        // Window the incoming samples
        for i in 0..self.n_fft {
            let s = if start_idx + i < samples.len() {
                samples[start_idx + i] * self.window[i]
            } else {
                0.0
            };
            self.input_buffer[i] = Complex32::new(s, 0.0);
        }

        // Execute FFT in-place
        self.fft.process(&mut self.input_buffer);

        // Compute magnitude in dBFS
        let norm = 1.0 / self.n_fft as f32;
        for (out_val, input_val) in out_db
            .iter_mut()
            .take(num_bins)
            .zip(self.input_buffer.iter())
        {
            let mag = input_val.norm() * norm;
            let db = 20.0 * (mag.max(1e-5)).log10();
            *out_val = (db as f64).clamp(-90.0, 0.0);
        }
    }

    pub fn freq_bins(&self) -> &[f64] {
        &self.freq_bins
    }

    pub fn num_bins(&self) -> usize {
        self.n_fft / 2 + 1
    }

    pub fn sample_rate(&self) -> f32 {
        self.sample_rate
    }
}
