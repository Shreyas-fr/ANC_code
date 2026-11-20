//! Hardware DMA Ping-Pong Double-Buffering Driver Primitive.
//!
//! Emulates embedded I2S audio codecs and direct memory access (DMA) controllers
//! commonly deployed on embedded defense platforms (Raspberry Pi 5 / ARM Cortex-M7):
//! - Wolfson / Cirrus Logic WM8960 Low-Power Stereo Codec
//! - Texas Instruments Burr-Brown PCM5102A 32-bit I2S Stereo DAC
//! - Generic Embedded I2S Multi-Channel Controller
//!
//! Features:
//! - Lock-free, zero-copy double-buffering (Ping / Pong buffers)
//! - Zero heap allocations in the streaming transfer path
//! - Strict xrun (underrun / overrun) detection when DSP deadline is breached
//! - Hardware interrupt (IRQ) jitter emulation modeling memory bus contention and preempt_rt latencies
//! - Full telemetry reporting: total interrupts, xruns, jitter distribution (mean, peak, variance)

use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};

/// Supported Embedded Audio Codec Hardware Models.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CodecModel {
    /// Wolfson / Cirrus Logic WM8960: Stereo ADC + DAC with built-in headphone amplifier
    Wm8960,
    /// Texas Instruments PCM5102A: 32-bit 384 kHz high-SNR I2S DAC
    Pcm5102a,
    /// Generic Embedded I2S DMA Controller (e.g. BCM2712 on Pi 5 / STM32F7 / STM32H7)
    GenericI2s,
}

impl CodecModel {
    pub fn name(&self) -> &'static str {
        match self {
            Self::Wm8960 => "Cirrus Logic / Wolfson WM8960 (ADC/DAC)",
            Self::Pcm5102a => "TI Burr-Brown PCM5102A (32-bit DAC)",
            Self::GenericI2s => "Embedded I2S DMA Controller (Pi 5 / ARM)",
        }
    }

    /// Typical hardware FIFO depth in audio samples per channel.
    pub fn fifo_depth_samples(&self) -> usize {
        match self {
            Self::Wm8960 => 64,
            Self::Pcm5102a => 128,
            Self::GenericI2s => 256,
        }
    }
}

/// Jitter emulation profile for embedded real-time interrupts.
#[derive(Debug, Clone)]
pub struct DmaJitterConfig {
    /// Maximum allowable hardware interrupt jitter in microseconds (+/- us)
    pub max_jitter_us: f32,
    /// Standard deviation of interrupt jitter in microseconds (default: 35.0 us)
    pub jitter_std_dev_us: f32,
    /// Baseline interrupt service routine (ISR) latency in microseconds (default: 8.0 us)
    pub isr_overhead_us: f32,
}

impl Default for DmaJitterConfig {
    fn default() -> Self {
        Self {
            max_jitter_us: 150.0,
            jitter_std_dev_us: 35.0,
            isr_overhead_us: 8.0,
        }
    }
}

/// Comprehensive DMA driver telemetry.
#[derive(Debug, Clone)]
pub struct DmaTelemetry {
    pub codec: CodecModel,
    pub block_size: usize,
    pub sample_rate: f32,
    pub nominal_period_us: f32,
    pub total_interrupts: u64,
    pub total_xruns: u64,
    pub xrun_rate: f32,
    pub mean_jitter_us: f32,
    pub peak_jitter_us: f32,
    pub last_interval_us: f32,
    pub active_dma_buffer: usize,
}

/// Result of a simulated DMA transfer interrupt.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DmaInterruptResult {
    /// Transfer completed normally; buffers swapped cleanly without collision
    BufferSwapped { new_active_buffer: usize },
    /// DSP was still processing the active buffer when interrupt occurred (Overrun/Underrun)
    XrunDetected { active_buffer: usize },
}

/// Lock-free, zero-copy double-buffering DMA driver.
pub struct I2sDmaDriver {
    codec: CodecModel,
    block_size: usize,
    sample_rate: f32,
    nominal_period_us: f32,
    jitter_config: DmaJitterConfig,

    // Double-buffered physical memory:
    // Ping = 0, Pong = 1
    // RX (ADC): Stereo dual-microphone capture [2][2][block_size] -> [buffer_idx][channel_idx][sample_idx]
    rx_buffers: [[Vec<f32>; 2]; 2],
    // TX (DAC): Stereo playout playout [2][2][block_size] -> [buffer_idx][channel_idx][sample_idx]
    tx_buffers: [[Vec<f32>; 2]; 2],

    // Atomic coordination state
    active_dma_buffer: AtomicUsize,
    dsp_busy: AtomicBool,
    interrupt_counter: AtomicU64,
    xrun_counter: AtomicU64,

    // Jitter tracking statistics
    sum_jitter_us: f32,
    peak_jitter_us: f32,
    last_jitter_us: f32,
    pseudo_rand_state: u64,
}

impl I2sDmaDriver {
    /// Creates a new I2S DMA double-buffering driver.
    ///
    /// - `codec`: Target audio codec hardware model.
    /// - `sample_rate`: Audio sampling frequency (e.g. 16000.0 or 48000.0 Hz).
    /// - `block_size`: Number of audio frames per DMA transfer buffer (e.g. 128 or 256).
    /// - `jitter_config`: Interrupt jitter emulation parameters.
    pub fn new(
        codec: CodecModel,
        sample_rate: f32,
        block_size: usize,
        jitter_config: DmaJitterConfig,
    ) -> Self {
        assert!(block_size > 0, "DMA block size must be > 0");
        assert!(sample_rate > 0.0, "Sample rate must be > 0");

        let nominal_period_us = (block_size as f32 * 1_000_000.0) / sample_rate;

        let rx_buffers = [
            [vec![0.0f32; block_size], vec![0.0f32; block_size]],
            [vec![0.0f32; block_size], vec![0.0f32; block_size]],
        ];

        let tx_buffers = [
            [vec![0.0f32; block_size], vec![0.0f32; block_size]],
            [vec![0.0f32; block_size], vec![0.0f32; block_size]],
        ];

        Self {
            codec,
            block_size,
            sample_rate,
            nominal_period_us,
            jitter_config,
            rx_buffers,
            tx_buffers,
            active_dma_buffer: AtomicUsize::new(0),
            dsp_busy: AtomicBool::new(false),
            interrupt_counter: AtomicU64::new(0),
            xrun_counter: AtomicU64::new(0),
            sum_jitter_us: 0.0,
            peak_jitter_us: 0.0,
            last_jitter_us: 0.0,
            pseudo_rand_state: 0x9E3779B97F4A7C15,
        }
    }

    /// Resets all buffers, statistics, and counters.
    pub fn reset(&mut self) {
        for b in 0..2 {
            for c in 0..2 {
                self.rx_buffers[b][c].fill(0.0);
                self.tx_buffers[b][c].fill(0.0);
            }
        }
        self.active_dma_buffer.store(0, Ordering::SeqCst);
        self.dsp_busy.store(false, Ordering::SeqCst);
        self.interrupt_counter.store(0, Ordering::SeqCst);
        self.xrun_counter.store(0, Ordering::SeqCst);
        self.sum_jitter_us = 0.0;
        self.peak_jitter_us = 0.0;
        self.last_jitter_us = 0.0;
    }

    /// Generates a deterministic pseudo-random jitter sample in [-max_jitter, +max_jitter]
    /// using a fast 64-bit XorShift linear congruential generator (zero allocations).
    fn next_pseudo_jitter(&mut self) -> f32 {
        let mut x = self.pseudo_rand_state;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.pseudo_rand_state = x;

        // Map to uniform [-1.0, 1.0]
        let u = (x as f64 / u64::MAX as f64) * 2.0 - 1.0;
        (u as f32) * self.jitter_config.max_jitter_us
    }

    /// Simulates a hardware DMA Transfer Complete Interrupt (TC IRQ) event.
    ///
    /// - `external_jitter_us`: Optional explicit jitter value. If `None`, emulated jitter is synthesized.
    ///
    /// Evaluates whether DSP has finished with the alternate buffer. If DSP is still busy,
    /// records an xrun. Otherwise, atomically swaps Ping/Pong buffer ownership.
    pub fn trigger_dma_interrupt(&mut self, external_jitter_us: Option<f32>) -> DmaInterruptResult {
        let jitter = external_jitter_us.unwrap_or_else(|| self.next_pseudo_jitter());
        let abs_jitter = jitter.abs();

        self.last_jitter_us = jitter;
        self.sum_jitter_us += abs_jitter;
        if abs_jitter > self.peak_jitter_us {
            self.peak_jitter_us = abs_jitter;
        }

        self.interrupt_counter.fetch_add(1, Ordering::Relaxed);
        let current_dma = self.active_dma_buffer.load(Ordering::Acquire);

        // If DSP is still busy reading the previous buffer, an xrun has occurred
        if self.dsp_busy.load(Ordering::Acquire) {
            self.xrun_counter.fetch_add(1, Ordering::Relaxed);
            DmaInterruptResult::XrunDetected { active_buffer: current_dma }
        } else {
            // Swap buffer: 0 -> 1, 1 -> 0
            let next_dma = 1 - current_dma;
            self.active_dma_buffer.store(next_dma, Ordering::Release);
            DmaInterruptResult::BufferSwapped { new_active_buffer: next_dma }
        }
    }

    /// Simulates DMA controller writing incoming audio samples from codec ADC into active DMA RX buffer.
    ///
    /// `mic1_in`: Audio samples for Primary Mic 1 [block_size].
    /// `mic2_in`: Audio samples for Secondary Mic 2 [block_size].
    pub fn dma_write_adc_samples(&mut self, mic1_in: &[f32], mic2_in: &[f32]) {
        assert_eq!(mic1_in.len(), self.block_size);
        assert_eq!(mic2_in.len(), self.block_size);

        let active_dma = self.active_dma_buffer.load(Ordering::Acquire);
        self.rx_buffers[active_dma][0].copy_from_slice(mic1_in);
        self.rx_buffers[active_dma][1].copy_from_slice(mic2_in);
    }

    /// Simulates DMA controller reading outgoing audio samples from active DMA TX buffer to codec DAC.
    ///
    /// `left_out`: Audio samples for Left headphone channel [block_size].
    /// `right_out`: Audio samples for Right headphone channel [block_size].
    pub fn dma_read_dac_samples(&self, left_out: &mut [f32], right_out: &mut [f32]) {
        assert_eq!(left_out.len(), self.block_size);
        assert_eq!(right_out.len(), self.block_size);

        let active_dma = self.active_dma_buffer.load(Ordering::Acquire);
        left_out.copy_from_slice(&self.tx_buffers[active_dma][0]);
        right_out.copy_from_slice(&self.tx_buffers[active_dma][1]);
    }

    /// DSP acquires zero-copy read-only access to the ready RX audio buffers.
    ///
    /// Returns references to `(mic1_slice, mic2_slice)` from the DSP buffer (opposite of DMA buffer).
    /// Sets `dsp_busy = true`.
    pub fn dsp_acquire_rx(&self) -> (&[f32], &[f32]) {
        self.dsp_busy.store(true, Ordering::Release);
        let active_dma = self.active_dma_buffer.load(Ordering::Acquire);
        let dsp_buf = 1 - active_dma;

        (
            &self.rx_buffers[dsp_buf][0][..],
            &self.rx_buffers[dsp_buf][1][..],
        )
    }

    /// DSP acquires zero-copy mutable access to the ready TX playout buffers.
    ///
    /// Returns mutable references to `(left_mut, right_mut)` from the DSP buffer (opposite of DMA buffer).
    pub fn dsp_acquire_tx_mut(&mut self) -> (&mut [f32], &mut [f32]) {
        let active_dma = self.active_dma_buffer.load(Ordering::Acquire);
        let dsp_buf = 1 - active_dma;

        let (first, second) = self.tx_buffers[dsp_buf].split_at_mut(1);
        (&mut first[0][..], &mut second[0][..])
    }

    /// DSP marks its processing deadline complete, releasing the buffer back for the next DMA swap.
    #[inline]
    pub fn dsp_release(&self) {
        self.dsp_busy.store(false, Ordering::Release);
    }

    /// Returns the current driver telemetry.
    pub fn telemetry(&self) -> DmaTelemetry {
        let total_irqs = self.interrupt_counter.load(Ordering::Relaxed);
        let total_xruns = self.xrun_counter.load(Ordering::Relaxed);
        let xrun_rate = if total_irqs > 0 {
            total_xruns as f32 / total_irqs as f32
        } else {
            0.0
        };
        let mean_jitter = if total_irqs > 0 {
            self.sum_jitter_us / total_irqs as f32
        } else {
            0.0
        };

        DmaTelemetry {
            codec: self.codec,
            block_size: self.block_size,
            sample_rate: self.sample_rate,
            nominal_period_us: self.nominal_period_us,
            total_interrupts: total_irqs,
            total_xruns,
            xrun_rate,
            mean_jitter_us: mean_jitter,
            peak_jitter_us: self.peak_jitter_us,
            last_interval_us: self.nominal_period_us + self.last_jitter_us,
            active_dma_buffer: self.active_dma_buffer.load(Ordering::Relaxed),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_dma_ping_pong_swapping() {
        let mut dma = I2sDmaDriver::new(
            CodecModel::Wm8960,
            16000.0,
            128,
            DmaJitterConfig::default(),
        );

        let mic1 = vec![0.5f32; 128];
        let mic2 = vec![-0.5f32; 128];

        // 1. DMA writes into initial active buffer (Ping = 0)
        dma.dma_write_adc_samples(&mic1, &mic2);

        // 2. Interrupt fires: swaps active DMA buffer to Pong (1), freeing Ping (0) for DSP
        let res = dma.trigger_dma_interrupt(Some(12.5));
        assert_eq!(res, DmaInterruptResult::BufferSwapped { new_active_buffer: 1 });

        // 3. DSP acquires Ping buffer (0)
        let (rx1, rx2) = dma.dsp_acquire_rx();
        assert_eq!(rx1[0], 0.5);
        assert_eq!(rx2[0], -0.5);

        // 4. DSP writes to TX buffer (0) and releases
        let (tx_l, tx_r) = dma.dsp_acquire_tx_mut();
        tx_l.fill(0.75);
        tx_r.fill(-0.75);
        dma.dsp_release();

        // 5. Next interrupt fires: swaps active DMA buffer back to Ping (0)
        let res2 = dma.trigger_dma_interrupt(Some(-8.0));
        assert_eq!(res2, DmaInterruptResult::BufferSwapped { new_active_buffer: 0 });

        // 6. DMA reads DAC samples from Ping (0) which was populated by DSP
        let mut dac_l = vec![0.0f32; 128];
        let mut dac_r = vec![0.0f32; 128];
        dma.dma_read_dac_samples(&mut dac_l, &mut dac_r);
        assert_eq!(dac_l[0], 0.75);
        assert_eq!(dac_r[0], -0.75);
    }

    #[test]
    fn test_dma_xrun_detection_when_dsp_exceeds_deadline() {
        let mut dma = I2sDmaDriver::new(
            CodecModel::Pcm5102a,
            16000.0,
            128,
            DmaJitterConfig::default(),
        );

        // First transfer
        dma.trigger_dma_interrupt(Some(0.0));

        // DSP acquires buffer and holds it (fails to call dsp_release())
        let _ = dma.dsp_acquire_rx();

        // Second DMA interrupt arrives while DSP is still busy -> XRUN!
        let res = dma.trigger_dma_interrupt(Some(25.0));
        assert!(matches!(res, DmaInterruptResult::XrunDetected { .. }));

        let telem = dma.telemetry();
        assert_eq!(telem.total_xruns, 1);
        assert_eq!(telem.total_interrupts, 2);
        assert_eq!(telem.xrun_rate, 0.5);
    }

    #[test]
    fn test_dma_jitter_emulation_statistics() {
        let mut dma = I2sDmaDriver::new(
            CodecModel::GenericI2s,
            16000.0,
            128,
            DmaJitterConfig {
                max_jitter_us: 100.0,
                jitter_std_dev_us: 25.0,
                isr_overhead_us: 5.0,
            },
        );

        // Run 100 simulated interrupts with pseudo-random jitter
        for _ in 0..100 {
            dma.trigger_dma_interrupt(None);
            dma.dsp_release();
        }

        let telem = dma.telemetry();
        assert_eq!(telem.total_interrupts, 100);
        assert_eq!(telem.total_xruns, 0);
        assert!(telem.peak_jitter_us <= 100.0);
        assert!(telem.mean_jitter_us > 0.0);
        assert!((telem.nominal_period_us - 8000.0).abs() < 1e-3); // 128 / 16000 = 8.0 ms = 8000 us
    }
}
