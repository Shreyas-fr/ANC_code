//! Real-time telemetry profiler and system hardware monitor.

use std::collections::VecDeque;
use std::fs;

/// Rolling latency and performance profiler.
pub struct PerformanceProfiler {
    window_size: usize,
    latencies_us: VecDeque<u64>,
    total_audio_time_us: u64,
    total_compute_time_us: u64,
}

impl PerformanceProfiler {
    pub fn new(window_size: usize) -> Self {
        Self {
            window_size,
            latencies_us: VecDeque::with_capacity(window_size),
            total_audio_time_us: 0,
            total_compute_time_us: 0,
        }
    }

    /// Records compute time for an audio block.
    pub fn record(&mut self, compute_us: u64, audio_chunk_us: u64) {
        if self.latencies_us.len() >= self.window_size {
            self.latencies_us.pop_front();
        }
        self.latencies_us.push_back(compute_us);

        self.total_compute_time_us += compute_us;
        self.total_audio_time_us += audio_chunk_us;
    }

    /// Real-Time Factor (RTF): compute_time / audio_time.
    /// RTF < 1.0 means faster than real-time.
    pub fn current_rtf(&self) -> f32 {
        if self.total_audio_time_us == 0 {
            return 0.0;
        }
        self.total_compute_time_us as f32 / self.total_audio_time_us as f32
    }

    /// Percentile compute latency in milliseconds (e.g. 50.0 for median, 99.0 for p99).
    pub fn percentile_ms(&self, pct: f32) -> f32 {
        if self.latencies_us.is_empty() {
            return 0.0;
        }
        let mut sorted: Vec<u64> = self.latencies_us.iter().copied().collect();
        sorted.sort_unstable();
        let idx = (((pct / 100.0) * sorted.len() as f32) as usize).min(sorted.len() - 1);
        sorted[idx] as f32 * 0.001
    }

    pub fn max_ms(&self) -> f32 {
        self.latencies_us.iter().copied().max().unwrap_or(0) as f32 * 0.001
    }
}

/// Reads Linux CPU/PMIC thermal sensor in Celsius.
pub fn read_system_temperature_c() -> f32 {
    let thermal_path = "/sys/class/thermal/thermal_zone0/temp";
    if let Ok(content) = fs::read_to_string(thermal_path) {
        if let Ok(temp_millicelsius) = content.trim().parse::<f32>() {
            return temp_millicelsius / 1000.0;
        }
    }
    45.0 // Fallback nominal ambient temperature
}
