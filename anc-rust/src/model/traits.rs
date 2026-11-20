//! Speech enhancer model traits and data structures.

use num_complex::Complex32;

/// Diagnostic telemetry and performance metrics returned per inference step.
#[derive(Debug, Clone, Default)]
pub struct EnhancerStats {
    /// Inference computation duration in microseconds
    pub compute_time_us: u64,
    /// Mean attenuation gain applied in dB
    pub attenuation_db: f32,
    /// Estimated signal-to-noise ratio improvement delta in dB
    pub estimated_snr_gain_db: f32,
    /// Count of clipped or non-finite elements caught
    pub sanitized_elements: usize,
}

/// Errors that can occur during neural model loading or inference.
#[derive(Debug)]
pub enum ModelError {
    Io(String),
    Inference(String),
    ShapeMismatch { expected: String, found: String },
    StateCorrupted,
}

impl std::fmt::Display for ModelError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(msg) => write!(f, "I/O error loading model: {}", msg),
            Self::Inference(msg) => write!(f, "Inference execution failed: {}", msg),
            Self::ShapeMismatch { expected, found } => {
                write!(f, "Shape mismatch: expected {}, found {}", expected, found)
            }
            Self::StateCorrupted => write!(f, "Model state corrupted"),
        }
    }
}

impl std::error::Error for ModelError {}

/// Unified interface for real-time speech enhancement models.
pub trait SpeechEnhancer: Send {
    /// Processes a single STFT complex spectrum frame in-place.
    fn process_stft_frame(&mut self, spec: &mut [Complex32]) -> Result<EnhancerStats, ModelError>;

    /// Resets recurrent memory states (e.g. GRU/LSTM hidden states) to zero.
    fn reset(&mut self);

    /// Returns the algorithmic lookahead of the model in audio samples.
    /// Strictly causal models return 0.
    fn algorithmic_lookahead_samples(&self) -> usize;

    /// Sets minimum attenuation floor in dB (optional tuning for adaptive enhancers).
    fn set_min_gain_db(&mut self, _min_gain_db: f32) {}

    /// Enables or disables shaped comfort noise injection during speech pauses.
    fn set_comfort_noise(&mut self, _enabled: bool) {}

    /// Sets diffuse field suppression scaling factors from spatial CDR estimation.
    fn set_diffuse_factors(&mut self, _alpha_factors: &[f32], _floor_factors: &[f32]) {}

    /// Enables or disables aggressive SNR optimization mode (dynamic pause floor deepening & deep harmonic comb).
    fn set_aggressive_snr(&mut self, _enabled: bool) {}

    /// Descriptive name of the model architecture.
    fn name(&self) -> &'static str;
}
