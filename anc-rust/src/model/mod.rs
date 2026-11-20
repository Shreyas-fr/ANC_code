//! Neural network enhancement and ensemble inference models.

pub mod comfort_noise;
pub mod crn_int8;
pub mod dfn3;
pub mod ensemble;
pub mod filter;
pub mod fullsubnet;
pub mod gtcrn;
pub mod npu_bridge;
pub mod spectral;
pub mod tract_engine;
pub mod traits;

pub use comfort_noise::{ComfortNoiseConfig, ComfortNoiseGenerator};
pub use crn_int8::{CrnInt8Postfilter, CRN_HIDDEN_DIM, CRN_NUM_BANDS};
pub use dfn3::{Dfn3Enhancer, DFN3_DF_BINS, DFN3_DF_ORDER, DFN3_NUM_BANDS, DFN3_NUM_BINS};
pub use ensemble::FrozenEnsemble;
pub use filter::DeepComplexFilter;
pub use fullsubnet::{FullSubNetEnhancer, NUM_FREQS as FULLSUBNET_NUM_FREQS};
pub use gtcrn::{
    GtcrnDeepFilterModel, GtcrnEnhancer, GtcrnTelemetry, GTCRN_DF_BINS, GTCRN_DF_ORDER,
    GTCRN_HIDDEN_DIM, GTCRN_NUM_BANDS, GTCRN_NUM_BINS,
};
pub use npu_bridge::{
    NpuAcceleratorBridge, NpuBackendType, NpuTelemetry, QuantizationScheme, QuantizedGemvEngine,
};
pub use spectral::AdaptiveSpectralEnhancer;
pub use tract_engine::TractEnhancer;
pub use traits::{EnhancerStats, ModelError, SpeechEnhancer};
