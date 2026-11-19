//! Window functions and Overlap-Add (OLA) reconstruction utilities.

use std::f32::consts::PI;

/// Windowing types supported for STFT analysis and synthesis.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WindowType {
    /// Standard symmetric Hann window (standard for offline / balanced OLA).
    Hann,
    /// Hamming window with lower first sidelobe.
    Hamming,
    /// Asymmetric low-latency window with sharp rise and gradual exponential taper,
    /// designed to minimize lookahead and group delay.
    AsymmetricLowLatency,
}

/// Generates an analysis window of length `size`.
pub fn generate_analysis_window(window_type: WindowType, size: usize) -> Vec<f32> {
    match window_type {
        WindowType::Hann => {
            let mut w = Vec::with_capacity(size);
            let denom = (size - 1) as f32;
            for n in 0..size {
                let val = 0.5 * (1.0 - (2.0 * PI * n as f32 / denom).cos());
                w.push(val);
            }
            w
        }
        WindowType::Hamming => {
            let mut w = Vec::with_capacity(size);
            let denom = (size - 1) as f32;
            for n in 0..size {
                let val = 0.54 - 0.46 * (2.0 * PI * n as f32 / denom).cos();
                w.push(val);
            }
            w
        }
        WindowType::AsymmetricLowLatency => {
            // Asymmetric window: fast cosine rise over the first 25% of the window,
            // flat/tapered decay over the remaining 75%.
            // This concentrates energy toward the recent past, reducing effective algorithmic group delay.
            let mut w = Vec::with_capacity(size);
            let rise_len = size / 4;
            let decay_len = size - rise_len;
            for n in 0..size {
                if n < rise_len {
                    // Cosine quarter-wave rise
                    let val = (PI * n as f32 / (2.0 * rise_len as f32)).sin();
                    w.push(val);
                } else {
                    // Gradual cosine decay
                    let m = n - rise_len;
                    let val = (PI * 0.5 + PI * 0.5 * m as f32 / decay_len as f32).sin();
                    w.push(val.max(0.0));
                }
            }
            w
        }
    }
}

/// Computes the exact synthesis window satisfying the Constant Overlap-Add (COLA) condition
/// for an arbitrary analysis window and hop size.
///
/// w_s[n] = w_a[n] / sum_{m} (w_a[n - m*H]^2)
pub fn compute_synthesis_window(analysis_window: &[f32], hop_size: usize) -> Vec<f32> {
    let size = analysis_window.len();
    let mut denom = vec![0.0f32; size];

    // Compute sum of squared overlapping analysis windows in steady state
    let num_overlaps = (size + hop_size - 1) / hop_size;
    let center_frame = num_overlaps;

    for frame in 0..(num_overlaps * 2 + 1) {
        let frame_offset = (frame as isize - center_frame as isize) * hop_size as isize;
        for i in 0..size {
            let shifted = i as isize - frame_offset;
            if shifted >= 0 && (shifted as usize) < size {
                let w = analysis_window[shifted as usize];
                denom[i] += w * w;
            }
        }
    }

    let mut synthesis = Vec::with_capacity(size);
    for i in 0..size {
        let d = denom[i].max(1e-8);
        synthesis.push(analysis_window[i] / d);
    }
    synthesis
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hann_symmetry() {
        let win = generate_analysis_window(WindowType::Hann, 512);
        assert_eq!(win.len(), 512);
        assert!((win[0] - 0.0).abs() < 1e-6);
        assert!((win[511] - 0.0).abs() < 1e-6);
        assert!((win[256] - 1.0).abs() < 1e-3);
    }

    #[test]
    fn test_cola_reconstruction() {
        let hop = 256;
        let win_size = 512;
        let w_a = generate_analysis_window(WindowType::Hann, win_size);
        let w_s = compute_synthesis_window(&w_a, hop);

        // Verify steady state overlap
        let mut reconstructed = vec![0.0f32; hop];
        for k in 0..(win_size / hop) {
            let offset = k * hop;
            for i in 0..hop {
                reconstructed[i] += w_a[offset + i] * w_s[offset + i];
            }
        }

        for &val in &reconstructed {
            assert!(
                (val - 1.0).abs() < 1e-4,
                "COLA reconstruction failed: expected 1.0, got {}",
                val
            );
        }
    }
}
