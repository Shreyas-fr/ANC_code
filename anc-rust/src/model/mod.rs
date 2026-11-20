//! Neural network enhancement and ensemble inference models.

pub mod comfort_noise;
pub mod crn_int8;
pub mod ensemble;
pub mod filter;
pub mod npu_bridge;
pub mod spectral;
pub mod tract_engine;
pub mod traits;

pub use comfort_noise::{ComfortNoiseConfig, ComfortNoiseGenerator};
pub use crn_int8::{CrnInt8Postfilter, CRN_HIDDEN_DIM, CRN_NUM_BANDS};
pub use ensemble::FrozenEnsemble;
pub use filter::DeepComplexFilter;
pub use npu_bridge::{
    NpuAcceleratorBridge, NpuBackendType, NpuTelemetry, QuantizationScheme, QuantizedGemvEngine,
};
pub use spectral::AdaptiveSpectralEnhancer;
pub use tract_engine::TractEnhancer;
pub use traits::{EnhancerStats, ModelError, SpeechEnhancer};
