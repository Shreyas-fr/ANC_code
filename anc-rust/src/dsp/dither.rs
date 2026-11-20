//! Dynamic Psychoacoustic Noise Shaping & TPDF Dither Engine.
//!
//! Provides zero-allocation Triangular Probability Density Function (TPDF) dither
//! coupled with Lipshitz-Vanderkooy / F-weighted psychoacoustic noise shaping for
//! 16-bit integer hardware quantization (ALSA, Raspberry Pi 5, Wolfson WM8960 / TI PCM5102A).
//!
//! Shifts quantization error power into spectral regions where the human ear
//! auditory threshold of quiet is high (> 6-14 kHz), yielding ~18-19 bit perceived dynamic range.

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum DitherMode {
    /// Direct rounding and clamping (no dither, produces correlated harmonic distortion during quiet pauses).
    None,
    /// Flat Triangular Probability Density Function (TPDF) dither (2 LSB peak-to-peak, white noise floor).
    TpdfFlat,
    /// TPDF dither with 2nd-order Lipshitz-Vanderkooy psychoacoustic noise shaping.
    #[default]
    TpdfLipshitz,
    /// TPDF dither with 3rd-order F-weighted psychoacoustic noise shaping.
    TpdfFWeighted,
}

/// Fast, deterministic, non-cryptographic 64-bit XorShift PRNG for zero-overhead real-time dither.
#[derive(Debug, Clone)]
struct XorShift64 {
    state: u64,
}

impl XorShift64 {
    #[inline(always)]
    fn new(seed: u64) -> Self {
        Self {
            state: if seed == 0 { 0x8a5cd789635d2dff } else { seed },
        }
    }

    #[inline(always)]
    fn next_u32(&mut self) -> u32 {
        let mut x = self.state;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.state = x;
        (x >> 32) as u32
    }

    /// Generates uniform sample in (-0.5, 0.5)
    #[inline(always)]
    fn next_uniform_sym(&mut self) -> f32 {
        (self.next_u32() as f32 / 4294967296.0) - 0.5
    }

    /// Generates standard TPDF dither sample in (-1.0, 1.0) with zero mean and variance = 1/6
    #[inline(always)]
    fn next_tpdf(&mut self) -> f32 {
        self.next_uniform_sym() - self.next_uniform_sym()
    }
}

/// Dynamic Psychoacoustic Noise Shaping & TPDF Dither Engine.
#[derive(Debug, Clone)]
pub struct DitherEngine {
    mode: DitherMode,
    rng: XorShift64,
    /// History of past quantization errors e[n-1], e[n-2], e[n-3]
    error_hist: [f32; 4],
    /// Noise shaping filter coefficients
    coeffs: [f32; 3],
    num_coeffs: usize,
    sample_rate: f32,
}

impl DitherEngine {
    /// Creates a new `DitherEngine` with the given mode and sample rate.
    pub fn new(mode: DitherMode, sample_rate: f32) -> Self {
        let mut engine = Self {
            mode,
            rng: XorShift64::new(0x4d595354455259), // Deterministic initial state
            error_hist: [0.0; 4],
            coeffs: [0.0; 3],
            num_coeffs: 0,
            sample_rate,
        };
        engine.update_coefficients();
        engine
    }

    /// Sets the dither mode dynamically.
    pub fn set_mode(&mut self, mode: DitherMode) {
        self.mode = mode;
        self.update_coefficients();
        self.reset();
    }

    /// Returns the current active dither mode.
    pub fn mode(&self) -> DitherMode {
        self.mode
    }

    /// Sample rate in Hz.
    pub fn sample_rate(&self) -> f32 {
        self.sample_rate
    }

    /// Resets filter history and error states.
    pub fn reset(&mut self) {
        self.error_hist = [0.0; 4];
    }

    fn update_coefficients(&mut self) {
        match self.mode {
            DitherMode::None | DitherMode::TpdfFlat => {
                self.coeffs = [0.0; 3];
                self.num_coeffs = 0;
            }
            DitherMode::TpdfLipshitz => {
                // Lipshitz-Vanderkooy 2nd-order minimally audible noise shaping:
                // H(z) = 1.623 z^-1 - 0.826 z^-2
                self.coeffs[0] = 1.623;
                self.coeffs[1] = -0.826;
                self.coeffs[2] = 0.0;
                self.num_coeffs = 2;
            }
            DitherMode::TpdfFWeighted => {
                // 3rd-order F-weighted psychoacoustic noise shaping:
                // H(z) = 2.033 z^-1 - 1.465 z^-2 + 0.385 z^-3
                self.coeffs[0] = 2.033;
                self.coeffs[1] = -1.465;
                self.coeffs[2] = 0.385;
                self.num_coeffs = 3;
            }
        }
    }

    /// Quantizes 32-bit floating point audio [-1.0, 1.0] to 16-bit signed integer [-32768, 32767]
    /// with zero heap allocations.
    pub fn quantize_i16(&mut self, input: &[f32], output: &mut [i16]) {
        assert_eq!(input.len(), output.len());
        const SCALE: f32 = 32767.0;

        for (in_samp, out_samp) in input.iter().zip(output.iter_mut()) {
            let x_scaled = (*in_samp * SCALE).clamp(-32768.0, 32767.0);

            let (dither, shaped_input) = match self.mode {
                DitherMode::None => (0.0f32, x_scaled),
                DitherMode::TpdfFlat => (self.rng.next_tpdf(), x_scaled),
                DitherMode::TpdfLipshitz | DitherMode::TpdfFWeighted => {
                    let d = self.rng.next_tpdf();
                    let mut feedback = 0.0f32;
                    for k in 0..self.num_coeffs {
                        feedback += self.coeffs[k] * self.error_hist[k];
                    }
                    (d, x_scaled + feedback)
                }
            };

            let target = shaped_input + dither;
            let q = target.round().clamp(-32768.0, 32767.0);
            let error = shaped_input - q;

            // Update error history
            if self.num_coeffs > 0 {
                self.error_hist[2] = self.error_hist[1];
                self.error_hist[1] = self.error_hist[0];
                self.error_hist[0] = error;
            }

            *out_samp = q as i16;
        }
    }

    /// Simulates 16-bit quantization and noise shaping in-place on 32-bit float audio [-1.0, 1.0].
    /// Useful for hearing the dithered signal in the floating point pipeline.
    pub fn process_f32(&mut self, input: &[f32], output: &mut [f32]) {
        assert_eq!(input.len(), output.len());
        const SCALE: f32 = 32767.0;
        const INV_SCALE: f32 = 1.0 / 32767.0;

        for (in_samp, out_samp) in input.iter().zip(output.iter_mut()) {
            let x_scaled = (*in_samp * SCALE).clamp(-32768.0, 32767.0);

            let (dither, shaped_input) = match self.mode {
                DitherMode::None => (0.0f32, x_scaled),
                DitherMode::TpdfFlat => (self.rng.next_tpdf(), x_scaled),
                DitherMode::TpdfLipshitz | DitherMode::TpdfFWeighted => {
                    let d = self.rng.next_tpdf();
                    let mut feedback = 0.0f32;
                    for k in 0..self.num_coeffs {
                        feedback += self.coeffs[k] * self.error_hist[k];
                    }
                    (d, x_scaled + feedback)
                }
            };

            let target = shaped_input + dither;
            let q = target.round().clamp(-32768.0, 32767.0);
            let error = shaped_input - q;

            if self.num_coeffs > 0 {
                self.error_hist[2] = self.error_hist[1];
                self.error_hist[1] = self.error_hist[0];
                self.error_hist[0] = error;
            }

            *out_samp = q * INV_SCALE;
        }
    }
}

impl Default for DitherEngine {
    fn default() -> Self {
        Self::new(DitherMode::TpdfLipshitz, 16000.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_xorshift_tpdf_statistical_distribution() {
        let mut rng = XorShift64::new(123456789);
        let n = 100_000;
        let mut sum = 0.0f64;
        let mut sum_sq = 0.0f64;

        for _ in 0..n {
            let v = rng.next_tpdf() as f64;
            assert!((-1.0..=1.0).contains(&v), "TPDF out of bounds: {}", v);
            sum += v;
            sum_sq += v * v;
        }

        let mean = sum / n as f64;
        let variance = (sum_sq / n as f64) - (mean * mean);

        // Theoretical mean = 0.0, theoretical variance = 1/6 ~= 0.16667
        assert!(mean.abs() < 0.01, "TPDF mean not near zero: {}", mean);
        assert!(
            (variance - (1.0 / 6.0)).abs() < 0.01,
            "TPDF variance not near 1/6: {}",
            variance
        );
    }

    #[test]
    fn test_quantize_i16_clamping_and_integrity() {
        let mut engine = DitherEngine::new(DitherMode::TpdfLipshitz, 16000.0);
        let input = [-2.0f32, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0];
        let mut output = [0i16; 7];

        engine.quantize_i16(&input, &mut output);

        // Clamping check
        assert_eq!(output[0], -32768);
        assert!(output[1] <= -32760);
        assert!(output[6] >= 32766);
    }

    #[test]
    fn test_noise_shaping_spectral_shift_toward_high_frequencies() {
        let n = 4096;
        let mut engine_flat = DitherEngine::new(DitherMode::TpdfFlat, 16000.0);
        let mut engine_shaped = DitherEngine::new(DitherMode::TpdfLipshitz, 16000.0);

        // Quantize absolute silence to measure quantization noise spectrum
        let silence = vec![0.0f32; n];
        let mut flat_out = vec![0.0f32; n];
        let mut shaped_out = vec![0.0f32; n];

        engine_flat.process_f32(&silence, &mut flat_out);
        engine_shaped.process_f32(&silence, &mut shaped_out);

        // High-pass filter via first-difference to measure high frequency noise content
        let mut flat_hf_pwr = 0.0f32;
        let mut shaped_hf_pwr = 0.0f32;
        for i in 1..n {
            let diff_flat = flat_out[i] - flat_out[i - 1];
            let diff_shaped = shaped_out[i] - shaped_out[i - 1];
            flat_hf_pwr += diff_flat * diff_flat;
            shaped_hf_pwr += diff_shaped * diff_shaped;
        }

        // Shaped dither must have significantly higher energy in high-frequency spectral region (above Nyquist/2)
        assert!(
            shaped_hf_pwr > flat_hf_pwr * 1.5,
            "Psychoacoustic noise shaping failed to shift error to HF: shaped={}, flat={}",
            shaped_hf_pwr,
            flat_hf_pwr
        );
    }
}
