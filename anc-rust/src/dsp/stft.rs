//! Real-time causal streaming Short-Time Fourier Transform (STFT) and Inverse STFT (ISTFT).
//!
//! Designed for zero-heap-allocation streaming on embedded ARM/x86 targets.

use std::sync::Arc;
use num_complex::Complex32;
use rustfft::{Fft, FftPlanner};

use super::window::{compute_synthesis_window, generate_analysis_window, WindowType};

/// Stateful streaming STFT and ISTFT processor.
pub struct StreamingStft {
    pub n_fft: usize,
    pub hop_size: usize,
    pub num_bins: usize,

    analysis_window: Vec<f32>,
    synthesis_window: Vec<f32>,

    fft_forward: Arc<dyn Fft<f32>>,
    fft_inverse: Arc<dyn Fft<f32>>,

    // Buffers for zero-allocation streaming execution
    time_scratch_in: Vec<Complex32>,
    time_scratch_out: Vec<Complex32>,
    fft_scratch: Vec<Complex32>,

    // Sliding input history: size = n_fft
    input_history: Vec<f32>,

    // Overlap-Add reconstruction accumulator: size = n_fft
    ola_accumulator: Vec<f32>,
}

impl StreamingStft {
    /// Creates a new StreamingStft instance.
    pub fn new(n_fft: usize, hop_size: usize, window_type: WindowType) -> Self {
        assert!(n_fft.is_power_of_two(), "n_fft must be a power of two");
        assert!(hop_size <= n_fft, "hop_size must be <= n_fft");

        let mut planner = FftPlanner::<f32>::new();
        let fft_forward = planner.plan_fft_forward(n_fft);
        let fft_inverse = planner.plan_fft_inverse(n_fft);

        let analysis_window = generate_analysis_window(window_type, n_fft);
        let synthesis_window = compute_synthesis_window(&analysis_window, hop_size);

        let scratch_len = fft_forward.get_inplace_scratch_len()
            .max(fft_inverse.get_inplace_scratch_len());

        let num_bins = n_fft / 2 + 1;

        Self {
            n_fft,
            hop_size,
            num_bins,
            analysis_window,
            synthesis_window,
            fft_forward,
            fft_inverse,
            time_scratch_in: vec![Complex32::default(); n_fft],
            time_scratch_out: vec![Complex32::default(); n_fft],
            fft_scratch: vec![Complex32::default(); scratch_len],
            input_history: vec![0.0f32; n_fft],
            ola_accumulator: vec![0.0f32; n_fft],
        }
    }

    /// Resets all internal buffers and temporal history to silence.
    pub fn reset(&mut self) {
        self.input_history.fill(0.0);
        self.ola_accumulator.fill(0.0);
        self.time_scratch_in.fill(Complex32::default());
        self.time_scratch_out.fill(Complex32::default());
    }

    /// Analysis: Pushes `hop_size` time-domain samples and computes the single-sided complex STFT spectrum.
    ///
    /// `input_hop`: exactly `hop_size` samples.
    /// `output_spec`: slice of length `num_bins` (n_fft / 2 + 1).
    pub fn analyze(&mut self, input_hop: &[f32], output_spec: &mut [Complex32]) {
        assert_eq!(input_hop.len(), self.hop_size, "input_hop length mismatch");
        assert_eq!(output_spec.len(), self.num_bins, "output_spec length mismatch");

        // 1. Shift input history left by hop_size
        let shift = self.n_fft - self.hop_size;
        self.input_history.copy_within(self.hop_size..self.n_fft, 0);
        self.input_history[shift..self.n_fft].copy_from_slice(input_hop);

        // 2. Window the frame into scratch buffer
        for i in 0..self.n_fft {
            self.time_scratch_in[i] = Complex32::new(
                self.input_history[i] * self.analysis_window[i],
                0.0,
            );
        }

        // 3. Compute in-place forward FFT
        self.fft_forward.process_with_scratch(
            &mut self.time_scratch_in,
            &mut self.fft_scratch,
        );

        // 4. Copy non-redundant positive frequencies (0..=n_fft/2)
        output_spec.copy_from_slice(&self.time_scratch_in[0..self.num_bins]);
    }

    /// Synthesis: Takes modified complex STFT spectrum and reconstructs exactly `hop_size` time-domain samples
    /// via causal overlap-add.
    ///
    /// `input_spec`: slice of length `num_bins` (n_fft / 2 + 1).
    /// `output_hop`: slice of length `hop_size` to receive synthesized audio.
    pub fn synthesize(&mut self, input_spec: &[Complex32], output_hop: &mut [f32]) {
        assert_eq!(input_spec.len(), self.num_bins, "input_spec length mismatch");
        assert_eq!(output_hop.len(), self.hop_size, "output_hop length mismatch");

        // 1. Reconstruct full Hermitian symmetric spectrum (0..n_fft)
        self.time_scratch_out[0..self.num_bins].copy_from_slice(input_spec);

        // Conjugate symmetry: X[N - k] = conj(X[k])
        let n = self.n_fft;
        for k in 1..(self.n_fft / 2) {
            self.time_scratch_out[n - k] = input_spec[k].conj();
        }

        // 2. Compute in-place inverse FFT
        self.fft_inverse.process_with_scratch(
            &mut self.time_scratch_out,
            &mut self.fft_scratch,
        );

        // 3. Scale by 1 / n_fft and apply synthesis window
        let inv_n = 1.0f32 / self.n_fft as f32;
        for i in 0..self.n_fft {
            let sample = self.time_scratch_out[i].re * inv_n;
            self.ola_accumulator[i] += sample * self.synthesis_window[i];
        }

        // 4. Extract first hop_size samples from accumulator as completed output
        output_hop.copy_from_slice(&self.ola_accumulator[0..self.hop_size]);

        // 5. Shift accumulator left by hop_size and zero the trailing tail
        self.ola_accumulator.copy_within(self.hop_size..self.n_fft, 0);
        let tail_start = self.n_fft - self.hop_size;
        self.ola_accumulator[tail_start..self.n_fft].fill(0.0);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_stft_perfect_reconstruction() {
        let n_fft = 512;
        let hop_size = 256;
        let mut stft = StreamingStft::new(n_fft, hop_size, WindowType::Hann);

        let total_samples = 4096;
        // Generate test signal: 440 Hz + 1000 Hz sine wave
        let mut test_signal = Vec::with_capacity(total_samples);
        for i in 0..total_samples {
            let t = i as f32 / 16000.0;
            let sample = 0.5 * (2.0 * std::f32::consts::PI * 440.0 * t).sin()
                + 0.3 * (2.0 * std::f32::consts::PI * 1000.0 * t).sin();
            test_signal.push(sample);
        }

        let mut reconstructed = Vec::with_capacity(total_samples);
        let mut spec = vec![Complex32::default(); stft.num_bins];
        let mut out_hop = vec![0.0f32; hop_size];

        for chunk in test_signal.chunks_exact(hop_size) {
            stft.analyze(chunk, &mut spec);
            stft.synthesize(&spec, &mut out_hop);
            reconstructed.extend_from_slice(&out_hop);
        }

        // Algorithmic delay of causal overlap-add: exactly 1 hop (hop_size)
        // because the second half of the analysis window in frame k overlaps
        // with the first half of the analysis window in frame k+1.
        let delay = hop_size;
        let test_len = total_samples - delay - n_fft;

        let original_slice = &test_signal[0..test_len];
        let reconstructed_slice = &reconstructed[delay..delay + test_len];

        let mut max_err = 0.0f32;
        for (a, b) in original_slice.iter().zip(reconstructed_slice.iter()) {
            let err = (a - b).abs();
            if err > max_err {
                max_err = err;
            }
        }

        assert!(
            max_err < 1e-4,
            "STFT round-trip error too large: max deviation = {}",
            max_err
        );
    }
}
