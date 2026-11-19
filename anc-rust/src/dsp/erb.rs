//! 32-band Equivalent Rectangular Bandwidth (ERB) Filterbank.
//!
//! Maps linear STFT frequency bins to human auditory perception sub-bands
//! matching DeepFilterNet3 and psychoacoustic models.

/// Converts frequency in Hz to ERB scale.
#[inline]
pub fn hz_to_erb(freq_hz: f32) -> f32 {
    21.4 * (0.00437 * freq_hz + 1.0).log10()
}

/// Converts ERB scale value to frequency in Hz.
#[inline]
pub fn erb_to_hz(erb: f32) -> f32 {
    ((10.0f32.powf(erb / 21.4)) - 1.0) / 0.00437
}

/// 32-band Auditory ERB Filterbank.
pub struct ErbFilterbank {
    pub num_bands: usize,
    pub num_bins: usize,
    pub sample_rate: f32,
    /// Triangle weights per band: band_index -> Vec<(bin_index, weight)>
    band_weights: Vec<Vec<(usize, f32)>>,
    /// Normalization factor per band
    band_norms: Vec<f32>,
    /// Interpolated reconstruction matrix: bin_index -> [(band1, w1), (band2, w2)]
    bin_to_bands: Vec<[(usize, f32); 2]>,
}

impl ErbFilterbank {
    pub fn new(num_bands: usize, num_bins: usize, sample_rate: f32) -> Self {
        let nyquist = sample_rate * 0.5;
        let erb_min = hz_to_erb(20.0);
        let erb_max = hz_to_erb(nyquist);

        // Center frequencies spaced equally on ERB scale
        let mut center_freqs = Vec::with_capacity(num_bands + 2);
        for i in 0..(num_bands + 2) {
            let erb_val = erb_min + (erb_max - erb_min) * (i as f32 / (num_bands + 1) as f32);
            center_freqs.push(erb_to_hz(erb_val));
        }

        let bin_hz = nyquist / (num_bins - 1) as f32;
        let mut band_weights = vec![Vec::new(); num_bands];
        let mut band_norms = vec![0.0f32; num_bands];

        for b in 0..num_bands {
            let f_low = center_freqs[b];
            let f_center = center_freqs[b + 1];
            let f_high = center_freqs[b + 2];

            let mut sum_w = 0.0f32;
            for k in 0..num_bins {
                let freq = k as f32 * bin_hz;
                let weight = if freq >= f_low && freq <= f_center {
                    (freq - f_low) / (f_center - f_low).max(1e-4)
                } else if freq > f_center && freq <= f_high {
                    (f_high - freq) / (f_high - f_center).max(1e-4)
                } else {
                    0.0
                };

                if weight > 1e-5 {
                    band_weights[b].push((k, weight));
                    sum_w += weight;
                }
            }
            band_norms[b] = sum_w.max(1e-4);
        }

        // Precompute bin-to-band interpolation for fast mask expansion
        let mut bin_to_bands = Vec::with_capacity(num_bins);
        for k in 0..num_bins {
            let freq = k as f32 * bin_hz;
            let mut lower_band = 0;
            for b in 0..(num_bands - 1) {
                if freq >= center_freqs[b + 1] {
                    lower_band = b;
                }
            }
            let upper_band = (lower_band + 1).min(num_bands - 1);
            let f1 = center_freqs[lower_band + 1];
            let f2 = center_freqs[upper_band + 1];
            let alpha = if (f2 - f1).abs() > 1e-4 {
                ((freq - f1) / (f2 - f1)).clamp(0.0, 1.0)
            } else {
                0.0
            };
            bin_to_bands.push([(lower_band, 1.0 - alpha), (upper_band, alpha)]);
        }

        Self {
            num_bands,
            num_bins,
            sample_rate,
            band_weights,
            band_norms,
            bin_to_bands,
        }
    }

    /// Computes ERB sub-band log-energy features from linear power spectrum.
    ///
    /// `power_spec`: slice of length `num_bins`.
    /// `erb_energies`: slice of length `num_bands`.
    pub fn extract_erb_energies(&self, power_spec: &[f32], erb_energies: &mut [f32]) {
        assert_eq!(power_spec.len(), self.num_bins);
        assert_eq!(erb_energies.len(), self.num_bands);

        for (b, weights) in self.band_weights.iter().enumerate() {
            let mut energy = 0.0f32;
            for &(k, w) in weights {
                energy += power_spec[k] * w;
            }
            erb_energies[b] = (energy / self.band_norms[b] + 1e-8).ln();
        }
    }

    /// Interpolates 32 ERB band gains back to linear STFT frequency bins.
    pub fn interpolate_band_gains(&self, erb_gains: &[f32], linear_gains: &mut [f32]) {
        assert_eq!(erb_gains.len(), self.num_bands);
        assert_eq!(linear_gains.len(), self.num_bins);

        for (k, &[(b1, w1), (b2, w2)]) in self.bin_to_bands.iter().enumerate() {
            linear_gains[k] = erb_gains[b1] * w1 + erb_gains[b2] * w2;
        }
    }
}
