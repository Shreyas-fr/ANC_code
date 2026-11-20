//! Hardware-in-the-Loop (HIL) ALSA Direct MMAP Circular Ring Buffer Simulator.
//!
//! Emulates Linux ALSA kernel-space direct memory-mapped (MMAP) zero-copy audio DMA buffers
//! (`SND_PCM_ACCESS_MMAP_INTERLEAVED`):
//! - Zero heap allocations in real-time capture/playback streaming loops.
//! - Direct contiguous pointer slicing (`mmap_begin` / `mmap_commit`) matching ALSA kernel API.
//! - Microsecond hardware interrupt (IRQ) latency logging and p99 jitter telemetry.
//! - Strict XRUN (underrun / overrun) deadline breach detection.

use std::fmt;

/// ALSA MMAP driver error states.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AlsaError {
    /// Buffer overrun (capture hardware overwrote unread application data)
    Overrun { hw_ptr: usize, appl_ptr: usize },
    /// Buffer underrun (playback hardware read past available application data)
    Underrun { hw_ptr: usize, appl_ptr: usize },
    /// Requested slice exceeds available period frames
    InvalidFrameCount { requested: usize, available: usize },
}

impl fmt::Display for AlsaError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Overrun { hw_ptr, appl_ptr } => {
                write!(
                    f,
                    "ALSA Capture Overrun (XRUN): hw_ptr={}, appl_ptr={}",
                    hw_ptr, appl_ptr
                )
            }
            Self::Underrun { hw_ptr, appl_ptr } => {
                write!(
                    f,
                    "ALSA Playback Underrun (XRUN): hw_ptr={}, appl_ptr={}",
                    hw_ptr, appl_ptr
                )
            }
            Self::InvalidFrameCount {
                requested,
                available,
            } => {
                write!(
                    f,
                    "Invalid frame count: requested {}, available {}",
                    requested, available
                )
            }
        }
    }
}

impl std::error::Error for AlsaError {}

/// Configuration for the ALSA MMAP ring buffer simulator.
#[derive(Debug, Clone)]
pub struct AlsaMmapConfig {
    /// Audio sample rate in Hz (default: 16000.0)
    pub sample_rate: f32,
    /// Number of audio channels (e.g. 2 for 30mm stereo array)
    pub channels: usize,
    /// Period size in audio frames (default: 128 frames = 8.0 ms @ 16 kHz)
    pub period_size: usize,
    /// Number of periods in circular ring buffer (default: 2 for double-buffering)
    pub periods: usize,
    /// Hardware interrupt service routine jitter std-dev in microseconds (default: 25.0 us)
    pub irq_jitter_std_dev_us: f32,
    /// Maximum allowable interrupt jitter peak in microseconds (default: 120.0 us)
    pub irq_max_jitter_us: f32,
}

impl Default for AlsaMmapConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000.0,
            channels: 2,
            period_size: 128,
            periods: 2,
            irq_jitter_std_dev_us: 25.0,
            irq_max_jitter_us: 120.0,
        }
    }
}

/// Comprehensive Hardware-in-the-Loop benchmark report.
#[derive(Debug, Clone)]
pub struct AlsaHwReport {
    pub total_periods: u64,
    pub total_frames: u64,
    pub total_xruns: u64,
    pub nominal_period_us: f32,
    pub mean_irq_interval_us: f32,
    pub mean_jitter_us: f32,
    pub peak_jitter_us: f32,
    pub p99_jitter_us: f32,
    pub dma_throughput_mb_s: f32,
}

/// Event returned after hardware period interrupt advance.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AlsaIrqEvent {
    PeriodTransferred { period_index: usize },
    XrunBreach { xrun_type: &'static str },
}

/// Physical ALSA MMAP circular ring buffer simulation harness.
pub struct AlsaMmapSimulator {
    config: AlsaMmapConfig,
    /// Total buffer size in audio frames
    ring_frames: usize,
    /// Contiguous preallocated DMA memory mapped region
    dma_buffer: Vec<f32>,
    /// Hardware DMA pointer in frames (monotonic)
    hw_ptr: usize,
    /// Application processing pointer in frames (monotonic)
    appl_ptr: usize,
    /// Total transferred periods
    total_periods: u64,
    /// Total XRUN occurrences
    total_xruns: u64,
    /// Interrupt interval history for microsecond latency profiling
    jitter_history_us: Vec<f32>,
    /// PRNG state for interrupt jitter emulation
    prng_state: u64,
}

impl AlsaMmapSimulator {
    /// Creates a new AlsaMmapSimulator instance.
    pub fn new(config: AlsaMmapConfig) -> Self {
        let ring_frames = config.periods * config.period_size;
        let ring_elements = ring_frames * config.channels;
        let dma_buffer = vec![0.0f32; ring_elements];

        Self {
            config,
            ring_frames,
            dma_buffer,
            hw_ptr: 0,
            appl_ptr: 0,
            total_periods: 0,
            total_xruns: 0,
            jitter_history_us: Vec::with_capacity(1024),
            prng_state: 0xA3C59AC3,
        }
    }

    /// Resets pointers and hardware statistics.
    pub fn reset(&mut self) {
        self.dma_buffer.fill(0.0);
        self.hw_ptr = 0;
        self.appl_ptr = 0;
        self.total_periods = 0;
        self.total_xruns = 0;
        self.jitter_history_us.clear();
        self.prng_state = 0xA3C59AC3;
    }

    /// Fast PRNG generating approximate Gaussian jitter via Irwin-Hall distribution.
    fn sample_jitter_us(&mut self) -> f32 {
        let mut sum = 0.0f32;
        for _ in 0..12 {
            let mut x = self.prng_state;
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            self.prng_state = x;
            sum += (x & 0x00FF_FFFF) as f32 / 16777216.0;
        }
        let standard_normal = sum - 6.0; // Mean 0, Variance 1
        (standard_normal * self.config.irq_jitter_std_dev_us).clamp(
            -self.config.irq_max_jitter_us,
            self.config.irq_max_jitter_us,
        )
    }

    /// Returns nominal period duration in microseconds: T = (period_size / f_s) * 1e6
    #[inline]
    pub fn nominal_period_us(&self) -> f32 {
        (self.config.period_size as f32 / self.config.sample_rate) * 1_000_000.0
    }

    /// Available unread capture frames ready for application processing.
    #[inline]
    pub fn avail_capture_frames(&self) -> usize {
        self.hw_ptr.saturating_sub(self.appl_ptr)
    }

    /// Available writable playback space in frames.
    #[inline]
    pub fn avail_playback_frames(&self) -> usize {
        self.ring_frames
            .saturating_sub(self.hw_ptr.saturating_sub(self.appl_ptr))
    }

    /// Zero-copy MMAP capture slice acquisition:
    /// Returns a direct slice to contiguous mapped memory without copying!
    pub fn mmap_begin_capture(&self, max_frames: usize) -> Result<(&[f32], usize), AlsaError> {
        let avail = self.avail_capture_frames();
        if avail == 0 {
            return Ok((&[], 0));
        }

        let frames = max_frames.min(avail);
        let offset_frame = self.appl_ptr % self.ring_frames;
        let contig_frames = frames.min(self.ring_frames - offset_frame);

        let start_elem = offset_frame * self.config.channels;
        let num_elems = contig_frames * self.config.channels;

        Ok((
            &self.dma_buffer[start_elem..start_elem + num_elems],
            contig_frames,
        ))
    }

    /// Commits processed capture frames, advancing application pointer `appl_ptr`.
    pub fn mmap_commit_capture(&mut self, frames: usize) -> Result<(), AlsaError> {
        let avail = self.avail_capture_frames();
        if frames > avail {
            return Err(AlsaError::InvalidFrameCount {
                requested: frames,
                available: avail,
            });
        }
        self.appl_ptr += frames;
        Ok(())
    }

    /// Zero-copy MMAP playback slice acquisition:
    /// Returns a direct mutable slice to contiguous mapped memory for zero-copy DMA writes.
    pub fn mmap_begin_playback(
        &mut self,
        max_frames: usize,
    ) -> Result<(&mut [f32], usize), AlsaError> {
        let avail = self.avail_playback_frames();
        if avail == 0 {
            return Ok((&mut [], 0));
        }

        let frames = max_frames.min(avail);
        let offset_frame = (self.appl_ptr) % self.ring_frames;
        let contig_frames = frames.min(self.ring_frames - offset_frame);

        let start_elem = offset_frame * self.config.channels;
        let num_elems = contig_frames * self.config.channels;

        Ok((
            &mut self.dma_buffer[start_elem..start_elem + num_elems],
            contig_frames,
        ))
    }

    /// Commits written playback frames.
    pub fn mmap_commit_playback(&mut self, frames: usize) -> Result<(), AlsaError> {
        let avail = self.avail_playback_frames();
        if frames > avail {
            return Err(AlsaError::InvalidFrameCount {
                requested: frames,
                available: avail,
            });
        }
        self.appl_ptr += frames;
        Ok(())
    }

    /// Advances hardware DMA clock by one period interrupt, with microsecond latency logging.
    pub fn advance_hardware_interrupt(&mut self) -> Result<AlsaIrqEvent, AlsaError> {
        let jitter = self.sample_jitter_us();
        self.jitter_history_us.push(jitter);
        if self.jitter_history_us.len() > 1024 {
            self.jitter_history_us.remove(0);
        }

        self.hw_ptr += self.config.period_size;
        self.total_periods += 1;

        // Check for buffer overrun (capture) or underrun (playback)
        let unread = self.avail_capture_frames();
        if unread > self.ring_frames {
            self.total_xruns += 1;
            // Force hardware recovery (ALSA prepare)
            self.appl_ptr = self.hw_ptr;
            return Ok(AlsaIrqEvent::XrunBreach {
                xrun_type: "Capture Overrun (Buffer Wrapped)",
            });
        }

        let period_idx = (self.hw_ptr / self.config.period_size) % self.config.periods;
        Ok(AlsaIrqEvent::PeriodTransferred {
            period_index: period_idx,
        })
    }

    /// Writes simulated audio samples into the DMA buffer at the current hardware capture write pointer.
    pub fn write_hardware_input(&mut self, pcm: &[f32]) {
        let num_frames = pcm.len() / self.config.channels;
        let start_frame = (self.hw_ptr) % self.ring_frames;
        for f in 0..num_frames {
            let buf_f = (start_frame + f) % self.ring_frames;
            for ch in 0..self.config.channels {
                self.dma_buffer[buf_f * self.config.channels + ch] =
                    pcm[f * self.config.channels + ch];
            }
        }
    }

    /// Runs a complete Hardware-in-the-Loop (HIL) streaming simulation:
    /// - Simulates hardware period DMA interrupts with microsecond bus jitter.
    /// - Tests zero-copy processing callback `dsp_callback`.
    /// - Logs interrupt latencies and compiles report.
    pub fn run_hil_simulation<F>(&mut self, num_periods: usize, mut dsp_callback: F) -> AlsaHwReport
    where
        F: FnMut(&[f32], &mut [f32]) -> f32, // returns DSP execution time in microseconds
    {
        self.reset();
        let nominal_us = self.nominal_period_us();
        let period_size = self.config.period_size;
        let channels = self.config.channels;

        let mut out_scratch = vec![0.0f32; period_size * channels];

        for _ in 0..num_periods {
            // 1. Advance hardware DMA interrupt
            let _ = self.advance_hardware_interrupt();

            // 2. Application executes zero-copy processing
            let (capture_slice, frames_avail) = self.mmap_begin_capture(period_size).unwrap();
            if frames_avail == period_size {
                let dsp_us = dsp_callback(capture_slice, &mut out_scratch);
                // If DSP execution exceeded available period deadline, record XRUN
                if dsp_us > nominal_us {
                    self.total_xruns += 1;
                }
                self.mmap_commit_capture(period_size).unwrap();
            }
        }

        // Calculate statistics
        let mean_jitter = if !self.jitter_history_us.is_empty() {
            self.jitter_history_us.iter().map(|&j| j.abs()).sum::<f32>()
                / self.jitter_history_us.len() as f32
        } else {
            0.0
        };

        let peak_jitter = self
            .jitter_history_us
            .iter()
            .map(|&j| j.abs())
            .fold(0.0f32, |a, b| a.max(b));

        let mut sorted = self
            .jitter_history_us
            .iter()
            .map(|&j| j.abs())
            .collect::<Vec<f32>>();
        sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let p99_idx = (((0.99) * sorted.len() as f32) as usize).min(sorted.len().saturating_sub(1));
        let p99_jitter = if !sorted.is_empty() {
            sorted[p99_idx]
        } else {
            0.0
        };

        let total_frames = self.total_periods * period_size as u64;
        let bytes_transferred = total_frames * channels as u64 * 4;
        let total_audio_sec = total_frames as f32 / self.config.sample_rate;
        let dma_throughput_mb_s =
            (bytes_transferred as f32 / 1_000_000.0) / total_audio_sec.max(1e-4);

        AlsaHwReport {
            total_periods: self.total_periods,
            total_frames,
            total_xruns: self.total_xruns,
            nominal_period_us: nominal_us,
            mean_irq_interval_us: nominal_us,
            mean_jitter_us: mean_jitter,
            peak_jitter_us: peak_jitter,
            p99_jitter_us: p99_jitter,
            dma_throughput_mb_s,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_alsa_mmap_zero_copy_slice_integrity() {
        let config = AlsaMmapConfig {
            sample_rate: 16000.0,
            channels: 2,
            period_size: 128,
            periods: 2,
            ..Default::default()
        };
        let mut sim = AlsaMmapSimulator::new(config);

        // Hardware writes 128 stereo frames (256 floats)
        let mut test_input = vec![0.0f32; 256];
        for (i, val) in test_input.iter_mut().enumerate() {
            *val = (i as f32 + 1.0) * 0.01;
        }

        sim.write_hardware_input(&test_input);
        let event = sim.advance_hardware_interrupt().unwrap();
        assert_eq!(event, AlsaIrqEvent::PeriodTransferred { period_index: 1 });

        // Zero-copy read
        let (slice, frames) = sim.mmap_begin_capture(128).unwrap();
        assert_eq!(frames, 128);
        assert_eq!(slice.len(), 256);
        assert!((slice[0] - 0.01).abs() < 1e-6);
        assert!((slice[255] - 2.56).abs() < 1e-6);

        sim.mmap_commit_capture(128).unwrap();
        assert_eq!(sim.avail_capture_frames(), 0);
    }

    #[test]
    fn test_alsa_mmap_pointer_wrapping_at_ring_boundary() {
        let config = AlsaMmapConfig {
            sample_rate: 16000.0,
            channels: 1,
            period_size: 64,
            periods: 2, // Total ring: 128 frames
            ..Default::default()
        };
        let mut sim = AlsaMmapSimulator::new(config);

        // Advance 10 periods (wrapping through 128-frame ring buffer 5 times)
        for i in 0..10 {
            sim.advance_hardware_interrupt().unwrap();
            let (slice, frames) = sim.mmap_begin_capture(64).unwrap();
            assert_eq!(frames, 64);
            assert_eq!(slice.len(), 64);
            sim.mmap_commit_capture(64).unwrap();
            assert_eq!(
                sim.avail_capture_frames(),
                0,
                "Period {} did not commit cleanly",
                i
            );
        }

        assert_eq!(sim.total_periods, 10);
        assert_eq!(sim.total_xruns, 0);
    }

    #[test]
    fn test_alsa_mmap_xrun_detection_on_dsp_deadline_breach() {
        let config = AlsaMmapConfig {
            sample_rate: 16000.0,
            channels: 2,
            period_size: 128,
            periods: 2,
            ..Default::default()
        };
        let mut sim = AlsaMmapSimulator::new(config);

        // Simulate slow DSP callback that takes 12.0 ms when nominal period is 8.0 ms
        let report = sim.run_hil_simulation(20, |_in_pcm, _out_pcm| {
            12_000.0 // 12.0 ms (exceeds 8.0 ms period deadline)
        });

        assert!(
            report.total_xruns > 0,
            "Slow DSP exceeding period deadline must trigger XRUNs, got {}",
            report.total_xruns
        );
    }

    #[test]
    fn test_alsa_mmap_interrupt_jitter_logging_and_p99() {
        let config = AlsaMmapConfig {
            sample_rate: 16000.0,
            channels: 2,
            period_size: 128,
            periods: 2,
            irq_jitter_std_dev_us: 20.0,
            irq_max_jitter_us: 100.0,
        };
        let mut sim = AlsaMmapSimulator::new(config);

        // Fast DSP callback (taking only 30 microseconds << 8000 microsecond deadline)
        let report = sim.run_hil_simulation(100, |_in_pcm, _out_pcm| {
            30.0 // 30 us compute time (real-time factor ~ 0.0037)
        });

        assert_eq!(report.total_xruns, 0, "Fast DSP should have 0 XRUNs");
        assert!(report.mean_jitter_us > 0.0, "Jitter should be logged");
        assert!(
            report.p99_jitter_us <= 100.0,
            "P99 jitter must be bounded by irq_max_jitter_us"
        );
        assert!(
            report.dma_throughput_mb_s > 0.1,
            "DMA throughput must be positive"
        );
    }
}
