//! Synthetic Tactical Test Signal Generator.
//!
//! Provides diagnostic signal injection for instant soundcard / hardware verification:
//! - Off: normal pass-through
//! - 1 kHz Pilot Tone: 1000 Hz continuous sinusoid at -12.0 dBFS (checks frequency alignment & harmonic THD)
//! - Acoustic Dirac Impulse: Periodic 1-sample impulse train every 500 ms (tests transient blanker & latency)
//! - Calibrated Pink Noise: 1/f shaped noise at -20.0 dBFS (validates subband ERB filtering & Wiener gain)

use std::f32::consts::PI;

/// Selectable hardware test signals.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TestSignalMode {
    Off,
    Sine1kHz,
    Impulse,
    PinkNoise,
}

impl TestSignalMode {
    pub fn name(&self) -> &'static str {
        match self {
            Self::Off => "TEST: OFF",
            Self::Sine1kHz => "1 kHz SINE (-12 dBFS)",
            Self::Impulse => "DIRAC IMPULSE (500 ms)",
            Self::PinkNoise => "PINK NOISE (-20 dBFS)",
        }
    }
}

/// Zero-allocation Synthetic Test Signal Generator.
pub struct TestSignalGenerator {
    pub mode: TestSignalMode,
    sample_rate: f32,
    phase: f32,
    impulse_counter: usize,
    // 3-pole Voss-McCartney pink noise filter states
    b0: f32,
    b1: f32,
    b2: f32,
    rng_state: u64,
}

impl TestSignalGenerator {
    /// Creates a new TestSignalGenerator.
    pub fn new(sample_rate: f32) -> Self {
        Self {
            mode: TestSignalMode::Off,
            sample_rate,
            phase: 0.0,
            impulse_counter: 0,
            b0: 0.0,
            b1: 0.0,
            b2: 0.0,
            rng_state: 0x1234_5678_9ABC_DEF0,
        }
    }

    /// Sets active test signal mode.
    pub fn set_mode(&mut self, mode: TestSignalMode) {
        self.mode = mode;
        self.phase = 0.0;
        self.impulse_counter = 0;
    }

    /// Returns whether test signal injection is active.
    pub fn is_active(&self) -> bool {
        self.mode != TestSignalMode::Off
    }

    #[inline]
    fn next_white_noise(&mut self) -> f32 {
        self.rng_state ^= self.rng_state << 13;
        self.rng_state ^= self.rng_state >> 7;
        self.rng_state ^= self.rng_state << 17;
        let u = (self.rng_state & 0x00FF_FFFF) as f32 / 16777216.0;
        u * 2.0 - 1.0
    }

    /// Generates test signal samples into the given buffer.
    pub fn generate(&mut self, buffer: &mut [f32]) {
        if self.mode == TestSignalMode::Off {
            return;
        }

        let phase_inc = 2.0 * PI * 1000.0 / self.sample_rate;
        let impulse_period = (self.sample_rate * 0.5) as usize; // 500 ms

        match self.mode {
            TestSignalMode::Off => {}
            TestSignalMode::Sine1kHz => {
                // -12 dBFS = 0.251 amplitude
                for s in buffer.iter_mut() {
                    *s = self.phase.sin() * 0.251;
                    self.phase += phase_inc;
                    if self.phase > 2.0 * PI {
                        self.phase -= 2.0 * PI;
                    }
                }
            }
            TestSignalMode::Impulse => {
                // Single 0.95 peak impulse every 500 ms
                for s in buffer.iter_mut() {
                    *s = if self.impulse_counter == 0 { 0.95 } else { 0.0 };
                    self.impulse_counter = (self.impulse_counter + 1) % impulse_period;
                }
            }
            TestSignalMode::PinkNoise => {
                // Voss-McCartney 3-pole pink noise approximation (-20 dBFS ~ 0.1 amplitude)
                for s in buffer.iter_mut() {
                    let white = self.next_white_noise();
                    self.b0 = 0.99765 * self.b0 + white * 0.0990460;
                    self.b1 = 0.96300 * self.b1 + white * 0.2965164;
                    self.b2 = 0.57000 * self.b2 + white * 1.0526913;
                    let pink = self.b0 + self.b1 + self.b2 + white * 0.1848;
                    *s = (pink * 0.035).clamp(-1.0, 1.0);
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_signal_generator_injection() {
        let mut gen = TestSignalGenerator::new(16000.0);
        let mut buf = vec![0.0f32; 512];

        // 1. Off mode: buffer remains zeros
        gen.generate(&mut buf);
        assert!(buf.iter().all(|&x| x == 0.0));

        // 2. 1 kHz Sine mode: generates sine wave
        gen.set_mode(TestSignalMode::Sine1kHz);
        gen.generate(&mut buf);
        let max_amp = buf.iter().map(|x| x.abs()).fold(0.0f32, f32::max);
        assert!(
            (max_amp - 0.251).abs() < 0.02,
            "Expected ~0.251 amp, got {}",
            max_amp
        );

        // 3. Dirac Impulse mode: produces an impulse at sample 0
        gen.set_mode(TestSignalMode::Impulse);
        gen.generate(&mut buf);
        assert_eq!(buf[0], 0.95);
        assert!(buf[1..].iter().all(|&x| x == 0.0));

        // 4. Pink Noise mode: produces energy
        gen.set_mode(TestSignalMode::PinkNoise);
        gen.generate(&mut buf);
        let rms = (buf.iter().map(|&x| x * x).sum::<f32>() / buf.len() as f32).sqrt();
        assert!(
            rms > 0.02 && rms < 0.20,
            "Expected pink noise RMS ~0.1, got {}",
            rms
        );
    }
}
