//! Complete end-to-end Tactical ANC & Speech Enhancement Pipeline.
//!
//! Connects all stages in a high-performance, deterministic execution chain:
//! Dual-Mic Input (30mm) -> Causal MVDR -> STFT -> Neural Enhancer -> ISTFT -> AGC -> Limiter

use num_complex::Complex32;

use crate::dsp::{
    CausalAgc, CausalMvdrBeamformer, MvdrConfig, SoftLimiter, StreamingStft, TransientBlanker,
    TransientConfig, WindowType,
};
use crate::model::{EnhancerStats, SpeechEnhancer};

/// Configurable runtime parameters for the audio chain.
#[derive(Debug, Clone)]
pub struct PipelineConfig {
    pub n_fft: usize,
    pub hop_size: usize,
    pub sample_rate: f32,
    pub window_type: WindowType,
    pub enable_transient_blanker: bool,
    pub transient_config: TransientConfig,
    pub enable_mvdr: bool,
    pub enable_agc: bool,
    pub enable_limiter: bool,
    pub mvdr_config: MvdrConfig,
}

impl Default for PipelineConfig {
    fn default() -> Self {
        Self {
            n_fft: 512,
            hop_size: 256,
            sample_rate: 16000.0,
            window_type: WindowType::Hann,
            enable_transient_blanker: true,
            transient_config: TransientConfig::default(),
            enable_mvdr: true,
            enable_agc: true,
            enable_limiter: true,
            mvdr_config: MvdrConfig::default(),
        }
    }
}

/// End-to-end Tactical Speech Enhancement Pipeline.
pub struct TacticalAncPipeline {
    config: PipelineConfig,
    transient_mic1: TransientBlanker,
    transient_mic2: TransientBlanker,
    stft_mic1: StreamingStft,
    stft_mic2: StreamingStft,
    beamformer: CausalMvdrBeamformer,
    agc: CausalAgc,
    limiter: SoftLimiter,

    // Preallocated scratch buffers (zero heap allocations in process_hop)
    mic1_scratch: Vec<f32>,
    mic2_scratch: Vec<f32>,
    spec_mic1: Vec<Complex32>,
    spec_mic2: Vec<Complex32>,
}

impl TacticalAncPipeline {
    /// Creates a new TacticalAncPipeline.
    pub fn new(config: PipelineConfig) -> Self {
        let n_fft = config.n_fft;
        let hop_size = config.hop_size;
        let num_bins = n_fft / 2 + 1;

        let transient_mic1 = TransientBlanker::new(config.transient_config.clone());
        let transient_mic2 = TransientBlanker::new(config.transient_config.clone());
        let stft_mic1 = StreamingStft::new(n_fft, hop_size, config.window_type);
        let stft_mic2 = StreamingStft::new(n_fft, hop_size, config.window_type);
        let beamformer = CausalMvdrBeamformer::new(config.mvdr_config.clone());
        let agc = CausalAgc::new(config.sample_rate, -20.0, 20.0, 200.0, -6.0, 24.0);
        let limiter = SoftLimiter::default();

        Self {
            config,
            transient_mic1,
            transient_mic2,
            stft_mic1,
            stft_mic2,
            beamformer,
            agc,
            limiter,
            mic1_scratch: vec![0.0f32; hop_size],
            mic2_scratch: vec![0.0f32; hop_size],
            spec_mic1: vec![Complex32::default(); num_bins],
            spec_mic2: vec![Complex32::default(); num_bins],
        }
    }

    /// Resets all internal DSP histories.
    pub fn reset(&mut self) {
        self.transient_mic1.reset();
        self.transient_mic2.reset();
        self.stft_mic1.reset();
        self.stft_mic2.reset();
        self.beamformer.reset();
        self.agc.reset();
    }

    /// Algorithmic delay in samples introduced by streaming overlap-add framing.
    pub fn algorithmic_delay_samples(&self) -> usize {
        self.config.hop_size
    }

    /// Processes a single stereo hop (exactly `hop_size` samples for mic1 and mic2).
    ///
    /// - `mic1_in`: Primary speech microphone audio.
    /// - `mic2_in`: Secondary reference microphone audio (for MVDR spatial nulling).
    /// - `enhancer`: Active neural network or ensemble model.
    /// - `out`: Slice of `hop_size` samples receiving enhanced audio.
    pub fn process_hop(
        &mut self,
        mic1_in: &[f32],
        mic2_in: Option<&[f32]>,
        enhancer: &mut dyn SpeechEnhancer,
        out: &mut [f32],
    ) -> Result<EnhancerStats, crate::model::ModelError> {
        assert_eq!(mic1_in.len(), self.config.hop_size);
        assert_eq!(out.len(), self.config.hop_size);

        // 0. Concussion / Impulsive Transient Blanking (Zero Allocation)
        let mic1_slice = if self.config.enable_transient_blanker {
            self.mic1_scratch.copy_from_slice(mic1_in);
            self.transient_mic1.process(&mut self.mic1_scratch);
            &self.mic1_scratch[..]
        } else {
            mic1_in
        };

        // 1. STFT Analysis on Mic 1
        self.stft_mic1.analyze(mic1_slice, &mut self.spec_mic1);

        // 2. Spatial MVDR Beamforming (if mic2 is provided and enabled)
        if self.config.enable_mvdr {
            if let Some(m2) = mic2_in {
                if m2.len() == self.config.hop_size {
                    let mic2_slice = if self.config.enable_transient_blanker {
                        self.mic2_scratch.copy_from_slice(m2);
                        self.transient_mic2.process(&mut self.mic2_scratch);
                        &self.mic2_scratch[..]
                    } else {
                        m2
                    };
                    self.stft_mic2.analyze(mic2_slice, &mut self.spec_mic2);
                    self.beamformer.process_frame(&mut self.spec_mic1, &self.spec_mic2);
                }
            }
        }

        // 3. Neural Noise Suppression / Complex Spectral Masking
        let stats = enhancer.process_stft_frame(&mut self.spec_mic1)?;

        // 4. Inverse STFT Synthesis
        self.stft_mic1.synthesize(&self.spec_mic1, out);

        // 5. Causal AGC (Level stabilization)
        if self.config.enable_agc {
            self.agc.process_block(out);
        }

        // 6. Peak Limiting (Anti-clipping protection)
        if self.config.enable_limiter {
            self.limiter.process(out);
        }

        Ok(stats)
    }
}
