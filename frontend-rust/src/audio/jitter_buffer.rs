//! Thread-safe JitterBuffer with prebuffering, overflow trimming, and smooth crossfades.
//!
//! Developed for DRDO SIH 26052 Live Defence Dashboard.

use std::sync::{Arc, Mutex};

/// Dynamic ring buffer for real-time audio playback.
pub struct JitterBuffer {
    buffer: Vec<f32>,
    read_pos: usize,
    write_pos: usize,
    count: usize,
    capacity: usize,

    target_samples: usize,
    max_samples: usize,
    sample_rate: u32,

    prebuffer: bool,
    is_holding: bool,
    need_fade_in: bool,
    last_sample: f32,
    fade_samples: usize,

    pub underrun_events: u64,
    pub underrun_samples: u64,
    pub overflow_count: u64,
    pub prebuffer_events: u64,
}

impl JitterBuffer {
    pub fn new(sample_rate: u32, target_ms: u32, max_ms: u32, prebuffer: bool) -> Self {
        let target_samples = (target_ms as f64 * 0.001 * sample_rate as f64) as usize;
        let max_samples = (max_ms as f64 * 0.001 * sample_rate as f64).max(target_samples as f64 + 1.0) as usize;
        let capacity = max_samples + 8192;

        Self {
            buffer: vec![0.0f32; capacity],
            read_pos: 0,
            write_pos: 0,
            count: 0,
            capacity,
            target_samples,
            max_samples,
            sample_rate,
            prebuffer,
            is_holding: prebuffer,
            need_fade_in: false,
            last_sample: 0.0,
            fade_samples: 32,
            underrun_events: 0,
            underrun_samples: 0,
            overflow_count: 0,
            prebuffer_events: if prebuffer { 1 } else { 0 },
        }
    }

    /// Pushes incoming audio PCM samples into the jitter buffer.
    pub fn write(&mut self, samples: &[f32]) {
        if samples.is_empty() {
            return;
        }

        let mut samples_to_write = samples;
        if samples.len() > self.max_samples {
            self.overflow_count += (samples.len() - self.max_samples) as u64;
            samples_to_write = &samples[samples.len() - self.max_samples..];
        }

        for &s in samples_to_write {
            self.buffer[self.write_pos] = s;
            self.write_pos = (self.write_pos + 1) % self.capacity;
        }
        self.count += samples_to_write.len();

        // Trim back to target buffer size if overflowed
        if self.count > self.max_samples {
            let drop = self.count - self.target_samples;
            self.read_pos = (self.read_pos + drop) % self.capacity;
            self.count = self.target_samples;
            self.overflow_count += drop as u64;
        }

        // Release holding state if prebuffering threshold met
        if self.is_holding && self.count >= self.target_samples {
            self.is_holding = false;
            self.need_fade_in = self.last_sample != 0.0;
        }
    }

    /// Reads audio samples for the soundcard driver callback.
    pub fn read(&mut self, out: &mut [f32]) {
        let requested = out.len();
        if self.is_holding {
            out.fill(0.0);
            return;
        }

        let available = self.count.min(requested);
        for i in 0..available {
            out[i] = self.buffer[self.read_pos];
            self.read_pos = (self.read_pos + 1) % self.capacity;
        }
        self.count -= available;

        // Apply smooth fade-in if recovering from silence/underrun
        if self.need_fade_in && available > 0 {
            let fade_len = self.fade_samples.min(available);
            for i in 0..fade_len {
                let factor = i as f32 / fade_len as f32;
                out[i] *= factor;
            }
            self.need_fade_in = false;
        }

        // Handle underrun
        if available < requested {
            self.underrun_events += 1;
            self.underrun_samples += (requested - available) as u64;

            // Fade out the tail of real samples if present to avoid clicks
            if available > 0 {
                let fade_len = self.fade_samples.min(available);
                for i in 0..fade_len {
                    let factor = (fade_len - 1 - i) as f32 / fade_len as f32;
                    let idx = available - fade_len + i;
                    out[idx] *= factor;
                }
                self.last_sample = 0.0;
            } else {
                self.last_sample = 0.0;
            }

            // Fill remainder with silence
            out[available..].fill(0.0);

            // Re-enter prebuffer holding state if configured
            if self.prebuffer {
                self.is_holding = true;
                self.prebuffer_events += 1;
            }
        } else if available > 0 {
            self.last_sample = out[available - 1];
        }
    }

    /// Current buffered audio duration in milliseconds.
    pub fn buffer_ms(&self) -> f32 {
        (self.count as f32 / self.sample_rate as f32) * 1000.0
    }

    /// Resets the buffer state.
    pub fn reset(&mut self) {
        self.read_pos = 0;
        self.write_pos = 0;
        self.count = 0;
        self.is_holding = self.prebuffer;
        self.need_fade_in = false;
        self.last_sample = 0.0;
    }
}

pub type SharedJitterBuffer = Arc<Mutex<JitterBuffer>>;
