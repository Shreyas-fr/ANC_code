//! Lock-Free Full-Duplex Audio Stream Coordinator Linking Capture DMA and Render DAC.
//!
//! In high-performance tactical edge systems (Raspberry Pi 5 with I2S audio codec / ALSA),
//! full-duplex operation requires deterministic microsecond coupling between the ADC capture
//! stream and the DAC playback stream:
//! 1. Atomic lock-free circular ring buffers decouple the hardware IRQ / DMA callbacks from the
//!    DSP processing loop without any mutex contention or heap allocations.
//! 2. Continuous round-trip loopback latency tracking ensuring compliance with the SIH <= 35 ms budget.
//! 3. Hardware clock drift measurement and XRUN (Capture Overrun / Render Underrun) detection.
//! 4. Pre-allocated scratch buffers ensuring strictly ZERO HEAP ALLOCATIONS in the real-time audio loop.

use rtrb::{Consumer, Producer, RingBuffer};

/// Configuration for the Full-Duplex Stream Coordinator.
#[derive(Debug, Clone)]
pub struct DuplexConfig {
    /// Audio sample rate in Hz (default: 16000.0)
    pub sample_rate: f32,
    /// DSP block / hop size in audio frames (default: 128 frames = 8.0 ms @ 16 kHz)
    pub block_size: usize,
    /// Ring buffer capacity in frames (default: 1024 frames = 64.0 ms)
    pub ring_capacity: usize,
    /// Pre-buffering delay in frames before render begins (default: 256 frames = 16.0 ms)
    pub prebuffer_frames: usize,
}

impl Default for DuplexConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000.0,
            block_size: 128,
            ring_capacity: 1024,
            prebuffer_frames: 256,
        }
    }
}

/// Real-time diagnostic telemetry from the Duplex Stream Coordinator.
#[derive(Debug, Clone, Copy, Default)]
pub struct DuplexTelemetry {
    /// Total frames ingested by capture DMA
    pub frames_captured: u64,
    /// Total frames consumed by render DAC
    pub frames_rendered: u64,
    /// Capture buffer overrun count (ADC pushed faster than DSP consumed)
    pub capture_overruns: u64,
    /// Render buffer underrun count (DAC starved because DSP was late)
    pub render_underruns: u64,
    /// Current fill level of capture buffer in frames
    pub capture_fill_level: usize,
    /// Current fill level of render buffer in frames
    pub render_fill_level: usize,
    /// End-to-end estimated loopback latency in milliseconds
    pub loopback_latency_ms: f32,
    /// Clock drift between capture and render in samples
    pub drift_samples: i64,
    /// Whether prebuffering has completed and the stream is actively flowing
    pub is_flowing: bool,
}

/// Zero-allocation Full-Duplex Stream Coordinator.
pub struct DuplexStreamCoordinator {
    config: DuplexConfig,
    capture_prod: Producer<f32>,
    capture_cons: Consumer<f32>,
    render_prod: Producer<f32>,
    render_cons: Consumer<f32>,
    scratch_in: Vec<f32>,
    scratch_out: Vec<f32>,
    frames_captured: u64,
    frames_rendered: u64,
    capture_overruns: u64,
    render_underruns: u64,
    is_flowing: bool,
}

impl DuplexStreamCoordinator {
    /// Creates a new DuplexStreamCoordinator with pre-allocated lock-free ring buffers.
    pub fn new(config: DuplexConfig) -> Self {
        let (capture_prod, capture_cons) = RingBuffer::new(config.ring_capacity);
        let (render_prod, render_cons) = RingBuffer::new(config.ring_capacity);
        let scratch_in = vec![0.0f32; config.block_size];
        let scratch_out = vec![0.0f32; config.block_size];

        Self {
            config,
            capture_prod,
            capture_cons,
            render_prod,
            render_cons,
            scratch_in,
            scratch_out,
            frames_captured: 0,
            frames_rendered: 0,
            capture_overruns: 0,
            render_underruns: 0,
            is_flowing: false,
        }
    }

    /// Ingests captured raw audio samples from ADC / DMA interrupt into the capture ring buffer.
    ///
    /// If the capture ring buffer is full, increments `capture_overruns` and drops excess samples.
    /// Strictly zero heap allocations.
    pub fn push_capture(&mut self, samples: &[f32]) -> usize {
        let mut pushed = 0;
        for &s in samples {
            match self.capture_prod.push(s) {
                Ok(()) => pushed += 1,
                Err(_) => {
                    self.capture_overruns += 1;
                }
            }
        }
        self.frames_captured += pushed as u64;
        pushed
    }

    /// Pulls processed audio samples for the render DAC.
    ///
    /// If the render buffer does not have enough samples, pads with silence (0.0)
    /// and increments `render_underruns`.
    /// Strictly zero heap allocations.
    pub fn pull_render(&mut self, output: &mut [f32]) -> usize {
        let mut pulled = 0;
        for out in output.iter_mut() {
            if self.is_flowing {
                match self.render_cons.pop() {
                    Ok(val) => {
                        *out = val;
                        pulled += 1;
                    }
                    Err(_) => {
                        *out = 0.0;
                        self.render_underruns += 1;
                    }
                }
            } else {
                *out = 0.0;
            }
        }
        self.frames_rendered += pulled as u64;
        pulled
    }

    /// Executes one DSP processing block if sufficient capture frames are available.
    ///
    /// Pulls `block_size` samples into pre-allocated scratch memory, passes them to `dsp_op`,
    /// and pushes the resulting `scratch_out` into the render ring buffer.
    /// Handles initial prebuffering to ensure jitter resilience.
    /// Strictly zero heap allocations.
    pub fn step_dsp<F>(&mut self, mut dsp_op: F) -> bool
    where
        F: FnMut(&[f32], &mut [f32]),
    {
        let block_size = self.config.block_size;
        if self.capture_cons.slots() < block_size {
            return false;
        }

        // 1. Pop block_size samples from capture ring buffer
        for s in self.scratch_in.iter_mut() {
            *s = self.capture_cons.pop().unwrap_or(0.0);
        }

        // 2. Execute zero-allocation DSP operation in-place
        dsp_op(&self.scratch_in, &mut self.scratch_out);

        // 3. Push processed samples into render ring buffer
        for &s in self.scratch_out.iter() {
            if self.render_prod.push(s).is_err() {
                // Render buffer full (overrun on render stage)
                self.capture_overruns += 1;
            }
        }

        // Check if prebuffering threshold has been reached to begin playout
        if !self.is_flowing && self.render_cons.slots() >= self.config.prebuffer_frames {
            self.is_flowing = true;
        }

        true
    }

    /// Returns the current real-time diagnostic telemetry.
    pub fn telemetry(&self) -> DuplexTelemetry {
        let cap_fill = self.capture_cons.slots();
        let ren_fill = self.render_cons.slots();
        let total_buffered = cap_fill + ren_fill;
        let latency_ms = (total_buffered as f32 / self.config.sample_rate) * 1000.0;
        let drift = self.frames_captured as i64 - self.frames_rendered as i64;

        DuplexTelemetry {
            frames_captured: self.frames_captured,
            frames_rendered: self.frames_rendered,
            capture_overruns: self.capture_overruns,
            render_underruns: self.render_underruns,
            capture_fill_level: cap_fill,
            render_fill_level: ren_fill,
            loopback_latency_ms: latency_ms,
            drift_samples: drift,
            is_flowing: self.is_flowing,
        }
    }

    /// Resets all buffers, counters, and streaming states.
    pub fn reset(&mut self) {
        while self.capture_cons.pop().is_ok() {}
        while self.render_cons.pop().is_ok() {}
        self.scratch_in.fill(0.0);
        self.scratch_out.fill(0.0);
        self.frames_captured = 0;
        self.frames_rendered = 0;
        self.capture_overruns = 0;
        self.render_underruns = 0;
        self.is_flowing = false;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_duplex_stream_normal_flow_and_latency() {
        let config = DuplexConfig {
            sample_rate: 16000.0,
            block_size: 128,
            ring_capacity: 1024,
            prebuffer_frames: 256,
        };
        let mut duplex = DuplexStreamCoordinator::new(config);

        // Feed 512 capture samples
        let input_audio = vec![0.5f32; 512];
        let pushed = duplex.push_capture(&input_audio);
        assert_eq!(pushed, 512);

        // Process 3 blocks (3 * 128 = 384 samples)
        let mut processed_blocks = 0;
        while duplex.step_dsp(|inp, out| {
            for (i, o) in inp.iter().zip(out.iter_mut()) {
                *o = *i * 2.0; // Simple DSP gain
            }
        }) {
            processed_blocks += 1;
        }
        assert_eq!(processed_blocks, 4);

        let telem = duplex.telemetry();
        assert!(telem.is_flowing);
        assert!(telem.loopback_latency_ms > 0.0);
        assert!(telem.loopback_latency_ms <= 35.0); // Within SIH round-trip budget

        // Pull 256 render samples
        let mut output_audio = vec![0.0f32; 256];
        let pulled = duplex.pull_render(&mut output_audio);
        assert_eq!(pulled, 256);
        for s in output_audio {
            assert!((s - 1.0).abs() < 1e-4);
        }
    }

    #[test]
    fn test_duplex_stream_underrun_detection() {
        let config = DuplexConfig {
            sample_rate: 16000.0,
            block_size: 128,
            ring_capacity: 512,
            prebuffer_frames: 128,
        };
        let mut duplex = DuplexStreamCoordinator::new(config);

        // Feed 128 samples and step DSP once to start flowing
        let inp = vec![0.2f32; 128];
        duplex.push_capture(&inp);
        duplex.step_dsp(|i, o| o.copy_from_slice(i));

        // Pull more than available (256 frames requested, only 128 available)
        let mut out = vec![0.0f32; 256];
        let pulled = duplex.pull_render(&mut out);
        assert_eq!(pulled, 128);

        let telem = duplex.telemetry();
        assert!(telem.render_underruns > 0);
    }
}
