//! Signal-to-Noise Ratio (SNR) and SI-SDR mathematical evaluation metrics.

/// Computes Scale-Invariant Signal-to-Distortion Ratio (SI-SDR) in dB.
///
/// Guarded against negative projections and near-zero energy terms.
pub fn compute_si_sdr(clean: &[f32], est: &[f32]) -> f32 {
    let n = clean.len().min(est.len());
    if n == 0 {
        return 0.0;
    }

    // Zero-mean normalization
    let mean_clean = clean[..n].iter().sum::<f32>() / n as f32;
    let mean_est = est[..n].iter().sum::<f32>() / n as f32;

    let mut dot_prod = 0.0f32;
    let mut energy_clean = 0.0f32;

    for i in 0..n {
        let c = clean[i] - mean_clean;
        let e = est[i] - mean_est;
        dot_prod += c * e;
        energy_clean += c * c;
    }

    if energy_clean <= 1e-8 {
        return 0.0;
    }

    // Optimal scaling factor: alpha = <est, clean> / ||clean||^2
    let alpha = dot_prod / energy_clean;
    if alpha <= 0.0 {
        return -30.0; // Negative correlation penalty
    }

    let mut energy_target = 0.0f32;
    let mut energy_error = 0.0f32;

    for i in 0..n {
        let c = clean[i] - mean_clean;
        let e = est[i] - mean_est;
        let target = alpha * c;
        let err = e - target;
        energy_target += target * target;
        energy_error += err * err;
    }

    if energy_error <= 1e-8 {
        return 50.0; // Perfect reconstruction cap
    }

    10.0 * (energy_target / energy_error).max(1e-8).log10()
}

/// Computes explicit Euclidean SNR: 10 * log10(||clean||^2 / ||est - clean||^2).
pub fn compute_explicit_snr(clean: &[f32], est: &[f32]) -> f32 {
    let n = clean.len().min(est.len());
    if n == 0 {
        return 0.0;
    }

    let mut clean_energy = 0.0f32;
    let mut err_energy = 0.0f32;

    for i in 0..n {
        let c = clean[i];
        let e = est[i];
        clean_energy += c * c;
        let diff = e - c;
        err_energy += diff * diff;
    }

    if err_energy <= 1e-8 {
        return 60.0;
    }
    if clean_energy <= 1e-8 {
        return -60.0;
    }

    10.0 * (clean_energy / err_energy).log10()
}

/// Computes Active Speech Level using energy histogram thresholding (P.56 approximation).
pub fn compute_active_speech_level(waveform: &[f32], frame_len: usize) -> f32 {
    if waveform.len() < frame_len {
        let sum_sq: f32 = waveform.iter().map(|&x| x * x).sum();
        return sum_sq / waveform.len().max(1) as f32;
    }

    let mut max_energy = 0.0f32;
    let mut frame_energies = Vec::with_capacity(waveform.len() / frame_len);

    for chunk in waveform.chunks_exact(frame_len) {
        let pwr = chunk.iter().map(|&x| x * x).sum::<f32>() / frame_len as f32;
        if pwr > max_energy {
            max_energy = pwr;
        }
        frame_energies.push(pwr);
    }

    let threshold = max_energy * 0.001; // -30 dB below peak
    let active_energies: Vec<f32> = frame_energies.into_iter().filter(|&e| e > threshold).collect();

    if active_energies.is_empty() {
        return 1e-6;
    }
    active_energies.iter().sum::<f32>() / active_energies.len() as f32
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_si_sdr_identical() {
        let x: Vec<f32> = (0..1000).map(|i| (i as f32 * 0.1).sin()).collect();
        let score = compute_si_sdr(&x, &x);
        assert!(score > 40.0, "Expected high SI-SDR for identical signal, got {}", score);
    }

    #[test]
    fn test_si_sdr_scaled() {
        let x: Vec<f32> = (0..1000).map(|i| (i as f32 * 0.1).sin()).collect();
        let scaled: Vec<f32> = x.iter().map(|&v| v * 2.5).collect();
        let score = compute_si_sdr(&x, &scaled);
        assert!(score > 40.0, "SI-SDR must be scale-invariant, got {}", score);
    }
}
