//! Binaural and Spatial Stereo Headphone Playout Renderer.
//!
//! Provides acoustic spatial separation between clean speech (anchored in center)
//! and attenuated ambient noise (widened across the lateral soundstage)
//! to relieve listener cognitive fatigue and maximize speech intelligibility
//! via Binaural Masking Level Difference (BMLD).
//!
//! Includes integrated Transaural Cross-Talk Cancellation (XTC) and 3D positioning.

use super::xtc::{TransauralXtc, XtcConfig};

/// Configuration for the Binaural Spatial Renderer.
#[derive(Debug, Clone)]
pub struct BinauralConfig {
    /// Stereo widening factor for ambient noise (0.0 = mono center, 1.0 = standard wide, 1.5 = ultra-wide)
    pub ambient_width: f32,
    /// Gain applied to ambient noise in headphone mix (-30 dB to -6 dB, default: -18 dB / 0.125)
    pub ambient_gain: f32,
    /// Center speech gain (default: 1.0)
    pub speech_gain: f32,
    /// Sample rate in Hz (default: 16000.0)
    pub sample_rate: f32,
    /// Interaural time delay in samples (~5 samples @ 16 kHz = 0.3125 ms Haas delay)
    pub itd_samples: usize,
    /// Enable spatial stereo widening (false = dual mono)
    pub enabled: bool,
    /// Enable Transaural Cross-Talk Cancellation (XTC)
    pub enable_xtc: bool,
    /// Configuration for XTC engine
    pub xtc_config: XtcConfig,
}

impl Default for BinauralConfig {
    fn default() -> Self {
        Self {
            ambient_width: 1.0,
            ambient_gain: 0.125, // -18 dBFS ambient bleed for situational awareness
            speech_gain: 1.0,
            sample_rate: 16000.0,
            itd_samples: 5,
            enabled: true,
            enable_xtc: false,
            xtc_config: XtcConfig::default(),
        }
    }
}

/// Zero-allocation Binaural and Spatial Stereo Headphone Renderer.
pub struct BinauralSpatialRenderer {
    config: BinauralConfig,
    delay_line: [f32; 64],
    delay_write_ptr: usize,
    prev_left_lp: f32,
    prev_right_lp: f32,
    pub xtc: TransauralXtc,
}

impl BinauralSpatialRenderer {
    pub fn new(config: BinauralConfig) -> Self {
        let xtc = TransauralXtc::new(config.xtc_config.clone());
        Self {
            config,
            delay_line: [0.0f32; 64],
            delay_write_ptr: 0,
            prev_left_lp: 0.0,
            prev_right_lp: 0.0,
            xtc,
        }
    }

    pub fn set_enabled(&mut self, enabled: bool) {
        self.config.enabled = enabled;
    }

    pub fn is_enabled(&self) -> bool {
        self.config.enabled
    }

    pub fn set_xtc(&mut self, enabled: bool) {
        self.config.enable_xtc = enabled;
        self.xtc.set_enabled(enabled);
    }

    pub fn reset(&mut self) {
        self.delay_line.fill(0.0);
        self.delay_write_ptr = 0;
        self.prev_left_lp = 0.0;
        self.prev_right_lp = 0.0;
        self.xtc.reset();
    }

    /// Renders clean mono speech and ambient background into interleaved stereo [L, R, L, R, ...].
    ///
    /// If `ambient_in` is None, subtle spatial decorrelation is applied to create an expansive
    /// stereo soundstage without voice coloration (Mid-Side sum L + R = 2 * speech).
    #[allow(clippy::chunks_exact_to_as_chunks)]
    pub fn render_interleaved(
        &mut self,
        speech_in: &[f32],
        ambient_in: Option<&[f32]>,
        stereo_out: &mut [f32],
    ) {
        let n = speech_in.len();
        assert!(stereo_out.len() >= n * 2);

        if !self.config.enabled {
            // Dual mono pass-through using 4-wide aligned chunk iterations for auto-vectorization
            let chunks_in = speech_in.chunks_exact(4);
            let rem_in = chunks_in.remainder();
            let mut chunks_out = stereo_out.chunks_exact_mut(8);

            for (cin, cout) in chunks_in.zip(chunks_out.by_ref()) {
                cout[0] = cin[0];
                cout[1] = cin[0];
                cout[2] = cin[1];
                cout[3] = cin[1];
                cout[4] = cin[2];
                cout[5] = cin[2];
                cout[6] = cin[3];
                cout[7] = cin[3];
            }
            let rem_out = chunks_out.into_remainder();
            for (i, &s) in rem_in.iter().enumerate() {
                rem_out[i * 2] = s;
                rem_out[i * 2 + 1] = s;
            }
            return;
        }

        let itd = self.config.itd_samples.clamp(1, 32);
        let width = self.config.ambient_width;
        let amb_gain = self.config.ambient_gain;
        let speech_gain = self.config.speech_gain;
        let cap = self.delay_line.len();

        for i in 0..n {
            let s = speech_in[i] * speech_gain;

            let amb = if let Some(amb_slice) = ambient_in {
                if i < amb_slice.len() {
                    amb_slice[i] * amb_gain
                } else {
                    0.0
                }
            } else {
                // Self-decorrelation from speech ambience: delayed sample
                let read_idx = (self.delay_write_ptr + cap - itd) % cap;
                let delayed_sample = self.delay_line[read_idx];
                (s - delayed_sample) * 0.25 * width
            };

            // Push sample into circular delay line
            self.delay_line[self.delay_write_ptr] = s;
            self.delay_write_ptr = (self.delay_write_ptr + 1) % cap;

            // Ambient noise is placed in stereo Side channel:
            // Left receives Mid + Side
            // Right receives Mid - Side
            let side = amb * width;
            let left_raw = s + side;
            let right_raw = s - side;

            // Head shadow filter (gentle 1st-order 4 kHz lowpass on contralateral side channel)
            let alpha_lp = 0.45f32;
            self.prev_left_lp = alpha_lp * self.prev_left_lp + (1.0 - alpha_lp) * left_raw;
            self.prev_right_lp = alpha_lp * self.prev_right_lp + (1.0 - alpha_lp) * right_raw;

            stereo_out[i * 2] = (left_raw * 0.85 + self.prev_left_lp * 0.15).clamp(-1.0, 1.0);
            stereo_out[i * 2 + 1] = (right_raw * 0.85 + self.prev_right_lp * 0.15).clamp(-1.0, 1.0);
        }

        // Apply Transaural Cross-Talk Cancellation if enabled
        if self.config.enable_xtc {
            self.xtc.process_interleaved(&mut stereo_out[..n * 2]);
        }
    }

    /// Positions a 3D tactical audio source at azimuth `azimuth_deg` [-180.0, +180.0].
    pub fn position_source_3d(
        &mut self,
        mono_in: &[f32],
        azimuth_deg: f32,
        stereo_out: &mut [f32],
    ) {
        self.xtc
            .position_source_3d(mono_in, azimuth_deg, stereo_out);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_binaural_renderer_dual_mono_when_disabled() {
        let mut renderer = BinauralSpatialRenderer::new(BinauralConfig {
            enabled: false,
            ..Default::default()
        });

        let speech = vec![0.5f32; 100];
        let mut stereo = vec![0.0f32; 200];
        renderer.render_interleaved(&speech, None, &mut stereo);

        for i in 0..100 {
            assert_eq!(stereo[i * 2], 0.5);
            assert_eq!(stereo[i * 2 + 1], 0.5);
        }
    }

    #[test]
    fn test_binaural_renderer_spatial_separation() {
        let mut renderer = BinauralSpatialRenderer::new(BinauralConfig {
            enabled: true,
            ambient_width: 1.0,
            ambient_gain: 0.5,
            speech_gain: 1.0,
            ..Default::default()
        });

        let speech = vec![0.6f32; 100];
        let ambient = vec![0.2f32; 100];
        let mut stereo = vec![0.0f32; 200];
        renderer.render_interleaved(&speech, Some(&ambient), &mut stereo);

        // Verify that Left and Right differ due to directional Side channel placement
        let mut diff_sum = 0.0f32;
        for i in 10..90 {
            diff_sum += (stereo[i * 2] - stereo[i * 2 + 1]).abs();
        }
        assert!(
            diff_sum > 0.1,
            "Stereo channels must show spatial separation for ambient noise"
        );
    }
}
