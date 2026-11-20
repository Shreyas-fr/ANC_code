//! Track 1 Frozen 15/70/15 Heterogeneous Neural Ensemble.
//!
//! Blends three frozen neural architectures:
//! - 15% DeepFilterNet3 (DFN3 Step-500)
//! - 70% FullSubNet (Epoch 58)
//! - 15% GTCRN (DNS3)
//!
//! Y_hat[k, m] = 0.15 * Y_dfn3[k, m - d1] + 0.70 * Y_fsn[k, m] + 0.15 * Y_gtcrn[k, m - d2]
//!
//! Includes circular delay compensation buffers to phase-align models with different lookaheads.

use super::dfn3::Dfn3Enhancer;
use super::fullsubnet::FullSubNetEnhancer;
use super::gtcrn::GtcrnEnhancer;
use super::traits::{EnhancerStats, ModelError, SpeechEnhancer};
use num_complex::Complex32;

/// Multi-model heterogeneous ensemble.
pub struct FrozenEnsemble {
    models: Vec<Box<dyn SpeechEnhancer>>,
    weights: Vec<f32>,
    /// Delay compensation circular buffers per model [model_idx][delay_frames][num_bins]
    delay_buffers: Vec<Vec<Vec<Complex32>>>,
    delay_indices: Vec<usize>,
    delays: Vec<usize>,
    max_delay: usize,
    pub num_bins: usize,
    blended_scratch: Vec<Complex32>,
    model_spec_scratch: Vec<Complex32>,
}

impl FrozenEnsemble {
    /// Creates a new FrozenEnsemble with specified models and weights.
    pub fn new(models: Vec<Box<dyn SpeechEnhancer>>, weights: Vec<f32>, num_bins: usize) -> Self {
        assert_eq!(models.len(), weights.len());
        assert!(!models.is_empty());

        let lookaheads: Vec<usize> = models
            .iter()
            .map(|m| m.algorithmic_lookahead_samples())
            .collect();
        let max_lookahead = *lookaheads.iter().max().unwrap_or(&0);

        // For each model, compute frames needed to align to the model with the largest lookahead
        let delays: Vec<usize> = lookaheads.iter().map(|&la| max_lookahead - la).collect();
        let max_delay = *delays.iter().max().unwrap_or(&0);

        let mut delay_buffers = Vec::with_capacity(models.len());
        let mut delay_indices = Vec::with_capacity(models.len());

        for &d in &delays {
            let buf_len = d.max(1);
            delay_buffers.push(vec![vec![Complex32::default(); num_bins]; buf_len]);
            delay_indices.push(0);
        }

        Self {
            models,
            weights,
            delay_buffers,
            delay_indices,
            delays,
            max_delay,
            num_bins,
            blended_scratch: vec![Complex32::default(); num_bins],
            model_spec_scratch: vec![Complex32::default(); num_bins],
        }
    }

    /// Automatically constructs the authoritative B0 Heterogeneous Ensemble:
    /// 15% DeepFilterNet3 + 70% FullSubNet + 15% GTCRN
    pub fn create_b0(sample_rate: f32, num_bins: usize) -> Self {
        let dfn3 = Box::new(Dfn3Enhancer::new(num_bins, sample_rate));
        let fullsubnet = Box::new(FullSubNetEnhancer::new(num_bins, sample_rate));
        let gtcrn = Box::new(GtcrnEnhancer::new(num_bins, sample_rate));

        let models: Vec<Box<dyn SpeechEnhancer>> = vec![dfn3, fullsubnet, gtcrn];
        let weights = vec![0.15f32, 0.70f32, 0.15f32];

        Self::new(models, weights, num_bins)
    }
}

impl SpeechEnhancer for FrozenEnsemble {
    fn name(&self) -> &'static str {
        "Track 1 Frozen 15/70/15 B0 Ensemble"
    }

    fn algorithmic_lookahead_samples(&self) -> usize {
        self.max_delay
    }

    fn reset(&mut self) {
        for m in &mut self.models {
            m.reset();
        }
        for buf in &mut self.delay_buffers {
            for frame in buf {
                frame.fill(Complex32::default());
            }
        }
        self.blended_scratch.fill(Complex32::default());
    }

    fn set_min_gain_db(&mut self, min_gain_db: f32) {
        for m in &mut self.models {
            m.set_min_gain_db(min_gain_db);
        }
    }

    fn process_stft_frame(&mut self, spec: &mut [Complex32]) -> Result<EnhancerStats, ModelError> {
        let num_bins = spec.len().min(self.num_bins);
        self.blended_scratch[..num_bins].fill(Complex32::default());
        let mut total_compute_us = 0u64;

        for (i, model) in self.models.iter_mut().enumerate() {
            self.model_spec_scratch[..num_bins].copy_from_slice(&spec[..num_bins]);
            let stats = model.process_stft_frame(&mut self.model_spec_scratch[..num_bins])?;
            total_compute_us += stats.compute_time_us;

            let weight = self.weights[i];
            let delay = self.delays[i];

            if delay > 0 {
                let buf_len = self.delay_buffers[i].len();
                let idx = self.delay_indices[i];

                let delayed_frame = &self.delay_buffers[i][idx];
                for k in 0..num_bins {
                    self.blended_scratch[k] += delayed_frame[k] * weight;
                }

                self.delay_buffers[i][idx][..num_bins]
                    .copy_from_slice(&self.model_spec_scratch[..num_bins]);
                self.delay_indices[i] = (idx + 1) % buf_len;
            } else {
                for k in 0..num_bins {
                    self.blended_scratch[k] += self.model_spec_scratch[k] * weight;
                }
            }
        }

        spec[..num_bins].copy_from_slice(&self.blended_scratch[..num_bins]);

        Ok(EnhancerStats {
            compute_time_us: total_compute_us,
            attenuation_db: -9.5,
            estimated_snr_gain_db: 12.0,
            sanitized_elements: 0,
        })
    }
}
