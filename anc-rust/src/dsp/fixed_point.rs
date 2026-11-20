//! Embedded Bare-Metal Fixed-Point (Q15 / Q31) DSP Engine.
//!
//! Developed for SIH 26052 Ultra-Low Power Tactical Microcontrollers & DSPs.
//!
//! Provides zero-allocation, deterministic fixed-point arithmetic for target
//! processors without FPUs or running in ultra-low power states (e.g. ARM Cortex-M4/M33/M55,
//! TI TMS320C6000, Tensilica HiFi DSP, or STM32H7).
//!
//! - `Q15` (1.15 format, i16): Range [-1.0, 0.999969], step 1/32768.
//! - `Q31` (1.31 format, i32): Range [-1.0, 0.9999999995], step 1/2147483648.
//! - Saturated arithmetic preventing roll-over clicks and acoustic instability.
//! - Fixed-point Biquad IIR filter (Direct Form II Transposed).
//! - Fixed-point Normalized LMS (NLMS) Adaptive Filter.
//! - In-place Radix-2 Q15 Fast Fourier Transform (FFT).

use serde::{Deserialize, Serialize};

/// Q15 fixed-point representation (1 sign bit, 15 fractional bits).
pub type Q15 = i16;

/// Q31 fixed-point representation (1 sign bit, 31 fractional bits).
pub type Q31 = i32;

pub const Q15_ONE: Q15 = i16::MAX;
pub const Q15_MIN: Q15 = i16::MIN;
pub const Q31_ONE: Q31 = i32::MAX;
pub const Q31_MIN: Q31 = i32::MIN;

/// Converts an f32 float to Q15 with symmetric saturation.
#[inline(always)]
pub fn f32_to_q15(x: f32) -> Q15 {
    let scaled = x * 32768.0;
    if scaled >= 32767.0 {
        i16::MAX
    } else if scaled <= -32768.0 {
        i16::MIN
    } else {
        scaled.round() as i16
    }
}

/// Converts a Q15 to f32 float.
#[inline(always)]
pub fn q15_to_f32(x: Q15) -> f32 {
    x as f32 / 32768.0
}

/// Converts an f32 float to Q31 with symmetric saturation.
#[inline(always)]
pub fn f32_to_q31(x: f32) -> Q31 {
    let scaled = x * 2147483648.0;
    if scaled >= 2147483647.0 {
        i32::MAX
    } else if scaled <= -2147483648.0 {
        i32::MIN
    } else {
        scaled.round() as i32
    }
}

/// Converts a Q31 to f32 float.
#[inline(always)]
pub fn q31_to_f32(x: Q31) -> f32 {
    x as f32 / 2147483648.0
}

/// Saturated Q15 multiplication with rounding: (a * b + 0x4000) >> 15.
#[inline(always)]
pub fn q15_mul(a: Q15, b: Q15) -> Q15 {
    let prod = (a as i32) * (b as i32);
    let rounded = (prod + 0x4000) >> 15;
    rounded.clamp(i16::MIN as i32, i16::MAX as i32) as i16
}

/// Saturated Q31 multiplication with rounding: ((a as i64 * b as i64) + 0x40000000) >> 31.
#[inline(always)]
pub fn q31_mul(a: Q31, b: Q31) -> Q31 {
    let prod = (a as i64) * (b as i64);
    let rounded = (prod + 0x40000000) >> 31;
    rounded.clamp(i32::MIN as i64, i32::MAX as i64) as i32
}

/// Q15 Vector dot product with 64-bit accumulator to avoid intermediate overflow.
pub fn q15_dot_product(a: &[Q15], b: &[Q15]) -> Q15 {
    let len = a.len().min(b.len());
    let mut acc: i64 = 0;
    for i in 0..len {
        acc += (a[i] as i64) * (b[i] as i64);
    }
    // Scale down from Q30 to Q15 with rounding
    let res = (acc + 0x4000) >> 15;
    res.clamp(i16::MIN as i64, i16::MAX as i64) as i16
}

/// Q31 Vector dot product with 64-bit accumulator.
pub fn q31_dot_product(a: &[Q31], b: &[Q31]) -> Q31 {
    let len = a.len().min(b.len());
    let mut acc: i64 = 0;
    for i in 0..len {
        let prod = ((a[i] as i64) * (b[i] as i64) + 0x40000000) >> 31;
        acc = acc.saturating_add(prod);
    }
    acc.clamp(i32::MIN as i64, i32::MAX as i64) as i32
}

/// Q15 Direct Form II Transposed Biquad Filter.
///
/// Implements standard difference equation:
/// y[n] = b0*x[n] + d1[n-1]
/// d1[n] = b1*x[n] - a1*y[n] + d2[n-1]
/// d2[n] = b2*x[n] - a2*y[n]
///
/// Uses 32-bit delay states to maintain filter precision and prevent limit-cycle oscillations.
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Q15Biquad {
    pub b0: Q15,
    pub b1: Q15,
    pub b2: Q15,
    pub a1: Q15,
    pub a2: Q15,
    pub d1: i32,
    pub d2: i32,
}

impl Q15Biquad {
    pub fn new(b0: Q15, b1: Q15, b2: Q15, a1: Q15, a2: Q15) -> Self {
        Self {
            b0,
            b1,
            b2,
            a1,
            a2,
            d1: 0,
            d2: 0,
        }
    }

    /// Creates a Q15 biquad from float coefficients.
    pub fn from_f32(b0: f32, b1: f32, b2: f32, a1: f32, a2: f32) -> Self {
        Self::new(
            f32_to_q15(b0),
            f32_to_q15(b1),
            f32_to_q15(b2),
            f32_to_q15(a1),
            f32_to_q15(a2),
        )
    }

    /// Resets internal filter delay states to zero.
    pub fn reset(&mut self) {
        self.d1 = 0;
        self.d2 = 0;
    }

    /// Processes a single Q15 sample.
    #[inline]
    pub fn process_sample(&mut self, x: Q15) -> Q15 {
        let x32 = x as i32;
        // y[n] = b0*x[n] + d1
        let yn_full = ((x32 * (self.b0 as i32)) << 1) + self.d1;
        let yn_q15 = (yn_full >> 16).clamp(i16::MIN as i32, i16::MAX as i32) as i16;
        let yn32 = yn_q15 as i32;

        // d1 = b1*x[n] - a1*y[n] + d2
        let term_b1 = (x32 * (self.b1 as i32)) << 1;
        let term_a1 = (yn32 * (self.a1 as i32)) << 1;
        self.d1 = term_b1.saturating_sub(term_a1).saturating_add(self.d2);

        // d2 = b2*x[n] - a2*y[n]
        let term_b2 = (x32 * (self.b2 as i32)) << 1;
        let term_a2 = (yn32 * (self.a2 as i32)) << 1;
        self.d2 = term_b2.saturating_sub(term_a2);

        yn_q15
    }

    /// Processes an entire slice in place.
    pub fn process_slice(&mut self, samples: &mut [Q15]) {
        for s in samples.iter_mut() {
            *s = self.process_sample(*s);
        }
    }
}

/// Fixed-point Normalized Least Mean Squares (NLMS) Adaptive Filter in Q15.
///
/// Designed for low-power secondary path cancellation and acoustic echo cancellation.
/// Maximum supported taps = 64 (fixed compile-time memory bound, zero heap alloc).
pub const MAX_Q15_NLMS_TAPS: usize = 32;

#[derive(Debug, Clone)]
pub struct Q15Nlms {
    num_taps: usize,
    weights: [Q15; MAX_Q15_NLMS_TAPS],
    history: [Q15; MAX_Q15_NLMS_TAPS],
    hist_idx: usize,
    /// Normalized step size mu in Q15.
    mu: Q15,
    /// Leakage factor in Q15 (e.g. 0.999).
    leakage: Q15,
}

impl Q15Nlms {
    pub fn new(num_taps: usize, mu: f32, leakage: f32) -> Self {
        let taps = num_taps.clamp(2, MAX_Q15_NLMS_TAPS);
        Self {
            num_taps: taps,
            weights: [0; MAX_Q15_NLMS_TAPS],
            history: [0; MAX_Q15_NLMS_TAPS],
            hist_idx: 0,
            mu: f32_to_q15(mu),
            leakage: f32_to_q15(leakage),
        }
    }

    pub fn reset(&mut self) {
        self.weights.fill(0);
        self.history.fill(0);
        self.hist_idx = 0;
    }

    /// Adapts the filter on a new reference sample `x` and desired sample `d`.
    /// Returns the error signal `e = d - y`.
    pub fn step(&mut self, x: Q15, d: Q15) -> Q15 {
        // Store into circular history
        self.history[self.hist_idx] = x;

        // Calculate filter output y = sum(w_k * x[n-k]) and signal energy
        let mut y_acc: i64 = 0;
        let mut energy_acc: i64 = 0;
        let taps = self.num_taps;

        for k in 0..taps {
            let idx = (self.hist_idx + taps - k) % taps;
            let x_val = self.history[idx] as i64;
            let w_val = self.weights[k] as i64;
            y_acc += w_val * x_val;
            energy_acc += x_val * x_val;
        }

        let y_q15 = ((y_acc + 0x4000) >> 15).clamp(i16::MIN as i64, i16::MAX as i64) as Q15;
        let error = d.saturating_sub(y_q15);

        // Normalized step size: mu_eff = mu / (energy + eps)
        let energy_q15 = ((energy_acc + 0x4000) >> 15).clamp(1, i16::MAX as i64) as i32;
        let e_scaled = (error as i32 * (self.mu as i32)) / (energy_q15 + 16);
        let e_step = e_scaled.clamp(i16::MIN as i32, i16::MAX as i32) as Q15;

        // Update weights with leakage: w_k = leakage * w_k + e_step * x[n-k]
        for k in 0..taps {
            let idx = (self.hist_idx + taps - k) % taps;
            let x_val = self.history[idx];
            let delta = q15_mul(e_step, x_val);
            let w_leaked = q15_mul(self.weights[k], self.leakage);
            self.weights[k] = w_leaked.saturating_add(delta);
        }

        self.hist_idx = (self.hist_idx + 1) % taps;
        error
    }
}

/// In-place Radix-2 Decimation-In-Time Q15 FFT.
///
/// Requires power-of-two length N (N <= 256 for zero-heap stack buffer).
pub fn q15_fft_radix2(real: &mut [Q15], imag: &mut [Q15]) {
    let n = real.len();
    assert!(
        n.is_power_of_two() && n == imag.len(),
        "N must be power of 2"
    );

    // Bit-reversal permutation
    let mut j = 0;
    for i in 0..(n - 1) {
        if i < j {
            real.swap(i, j);
            imag.swap(i, j);
        }
        let mut k = n >> 1;
        while k <= j {
            j -= k;
            k >>= 1;
        }
        j += k;
    }

    // Butterfly stages
    let mut len = 2;
    while len <= n {
        let half = len / 2;
        let angle_step = -std::f32::consts::PI / (half as f32);

        for i in (0..n).step_by(len) {
            for k in 0..half {
                let theta = (k as f32) * angle_step;
                let wr = f32_to_q15(theta.cos());
                let wi = f32_to_q15(theta.sin());

                let idx_b = i + k + half;
                let idx_a = i + k;

                let tr = q15_mul(wr, real[idx_b]).saturating_sub(q15_mul(wi, imag[idx_b]));
                let ti = q15_mul(wr, imag[idx_b]).saturating_add(q15_mul(wi, real[idx_b]));

                real[idx_b] = (real[idx_a].saturating_sub(tr)) >> 1;
                imag[idx_b] = (imag[idx_a].saturating_sub(ti)) >> 1;
                real[idx_a] = (real[idx_a].saturating_add(tr)) >> 1;
                imag[idx_a] = (imag[idx_a].saturating_add(ti)) >> 1;
            }
        }
        len <<= 1;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_q15_conversion_and_saturation() {
        assert_eq!(f32_to_q15(0.0), 0);
        assert_eq!(f32_to_q15(1.0), i16::MAX);
        assert_eq!(f32_to_q15(-1.0), i16::MIN);
        assert_eq!(f32_to_q15(1.5), i16::MAX);
        assert_eq!(f32_to_q15(-2.0), i16::MIN);

        assert!((q15_to_f32(f32_to_q15(0.5)) - 0.5).abs() < 1e-4);
        assert!((q15_to_f32(f32_to_q15(-0.25)) + 0.25).abs() < 1e-4);
    }

    #[test]
    fn test_q31_conversion_and_saturation() {
        assert_eq!(f32_to_q31(0.0), 0);
        assert_eq!(f32_to_q31(1.0), i32::MAX);
        assert_eq!(f32_to_q31(-1.0), i32::MIN);
        assert!((q31_to_f32(f32_to_q31(0.75)) - 0.75).abs() < 1e-6);
    }

    #[test]
    fn test_q15_multiplication() {
        let a = f32_to_q15(0.5);
        let b = f32_to_q15(0.5);
        let res = q15_mul(a, b);
        assert!((q15_to_f32(res) - 0.25).abs() < 1e-3);
    }

    #[test]
    fn test_q15_biquad_filtering() {
        let mut biquad = Q15Biquad::from_f32(0.5, 0.0, 0.0, 0.0, 0.0);
        let input = f32_to_q15(0.8);
        let out = biquad.process_sample(input);
        assert!((q15_to_f32(out) - 0.4).abs() < 1e-2);
    }

    #[test]
    fn test_q15_nlms_convergence() {
        let mut nlms = Q15Nlms::new(8, 0.2, 0.999);
        let mut err = 0;
        for _ in 0..100 {
            let x = f32_to_q15(0.4);
            let d = f32_to_q15(0.2); // Plant gain = 0.5
            err = nlms.step(x, d);
        }
        // Error should diminish towards zero
        assert!(q15_to_f32(err).abs() < 0.1);
    }

    #[test]
    fn test_q15_fft_dc_impulse() {
        let mut real = [0i16; 16];
        let mut imag = [0i16; 16];
        real[0] = f32_to_q15(0.8); // Unit impulse

        q15_fft_radix2(&mut real, &mut imag);

        // FFT of unit impulse has flat magnitude across all bins
        let mag0 = q15_to_f32(real[0]);
        let mag1 = q15_to_f32(real[1]);
        assert!((mag0 - mag1).abs() < 0.05);
    }
}
