//! Deep Complex Filter (DF) order-5 and ERB gain mask application.
//!
//! Reconstructs speech harmonics and preserves phase relationships
//! by applying learned complex filtering coefficients across temporal STFT history.

use num_complex::Complex32;

/// Deep Complex Filter (Order N = 5) processor.
pub struct DeepComplexFilter {
    pub order: usize,
    pub num_df_bins: usize,
    /// Complex history buffer: [order, num_df_bins]
    history: Vec<Vec<Complex32>>,
}

impl DeepComplexFilter {
    /// Creates a new DeepComplexFilter with given order (typically 5) and DF frequency bins (typically 96).
    pub fn new(order: usize, num_df_bins: usize) -> Self {
        Self {
            order,
            num_df_bins,
            history: vec![vec![Complex32::default(); num_df_bins]; order],
        }
    }

    /// Resets filter history to zeros.
    pub fn reset(&mut self) {
        for frame in &mut self.history {
            frame.fill(Complex32::default());
        }
    }

    /// Applies deep complex filtering and ERB linear gains to the STFT spectrum in-place.
    ///
    /// - `spec`: Current complex STFT frame [num_bins].
    /// - `linear_gains`: Per-bin real gains [num_bins] derived from ERB filterbank.
    /// - `df_coefficients`: Complex filter coefficients [order, num_df_bins].
    pub fn apply(
        &mut self,
        spec: &mut [Complex32],
        linear_gains: &[f32],
        df_coefficients: Option<&[Vec<Complex32>]>,
    ) {
        let num_bins = spec.len();
        let num_df = self.num_df_bins.min(num_bins);

        // 1. Shift temporal history: history[order-1] <- history[order-2] ...
        if self.order > 1 {
            for i in (1..self.order).rev() {
                let (left, right) = self.history.split_at_mut(i);
                right[0].copy_from_slice(&left[i - 1]);
            }
        }
        // Save current raw frame to history[0]
        self.history[0][..num_df].copy_from_slice(&spec[..num_df]);

        // 2. Apply Deep Complex Filtering to the lowest periodic frequencies (0..num_df)
        if let Some(coeffs) = df_coefficients {
            for k in 0..num_df {
                let mut filtered = Complex32::default();
                for l in 0..self.order.min(coeffs.len()) {
                    let c = coeffs[l][k];
                    let x_past = self.history[l][k];
                    filtered += c * x_past;
                }

                // Smoothly blend complex filter with ERB gain
                let erb_gain = linear_gains[k].clamp(0.0, 2.0);
                let gain_filtered = spec[k] * erb_gain;

                // Combined output: restored phase harmonics from DF + envelope suppression
                let out = 0.7 * filtered + 0.3 * gain_filtered;
                spec[k] = if out.re.is_finite() && out.im.is_finite() {
                    out
                } else {
                    spec[k] * erb_gain
                };
            }
        } else {
            // If DF coefficients are absent, apply ERB gains directly
            for k in 0..num_df {
                let g = linear_gains[k].clamp(0.0, 2.0);
                spec[k] *= g;
            }
        }

        // 3. For high frequencies (num_df..num_bins), apply real ERB envelope attenuation
        for k in num_df..num_bins {
            let g = linear_gains[k].clamp(0.0, 2.0);
            spec[k] *= g;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_df_passthrough() {
        let mut df = DeepComplexFilter::new(5, 32);
        let mut spec = vec![Complex32::new(1.0, 0.5); 64];
        let gains = vec![1.0f32; 64];

        // Apply with unity gains and no DF coefficients
        df.apply(&mut spec, &gains, None);

        assert_eq!(spec[0], Complex32::new(1.0, 0.5));
        assert_eq!(spec[35], Complex32::new(1.0, 0.5));
    }
}
