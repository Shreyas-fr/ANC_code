//! Adaptive Filter Convergence Time Profiler and Stability Monitor.
//!
//! Tracks real-time adaptation dynamics and calculates convergence time in milliseconds
//! across all core adaptive DSP filters:
//! 1. MVDR Adaptive Covariance Matrix (Recursive sample matrix inversion)
//! 2. GSC Adaptive Blocking & Noise Cancelling Filter
//! 3. AFC Decoupled Shadow Filter (Background-to-foreground weight transfer & ERLE)
//! 4. Kalman Filter DOA Tracking (State estimation variance stabilization)
//! 5. WPE Multi-Channel Linear Prediction Dereverberator
//!
//! Convergence Criteria:
//! An adaptive filter is declared converged when its normalized gradient/error metric enters
//! within a steady-state tolerance band $\delta$ and dwells stably for a continuous window
//! $T_{\text{dwell}}$ (e.g. $\ge 50\text{ ms}$).
//!
//! Strictly zero heap allocations during real-time tracking.

use std::fmt;

/// Supported adaptive filter categories in the ANC pipeline.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum FilterType {
    /// MVDR Adaptive Spatial Covariance Matrix
    MvdrCovariance,
    /// Generalized Sidelobe Canceller (GSC) Adaptive Blocking Filter
    GscBlocking,
    /// Acoustic Feedback Cancellation (AFC) Shadow Filter
    AfcShadow,
    /// Extended Kalman Filter Direction-of-Arrival (DOA) Tracker
    KalmanDoa,
    /// Weighted Prediction Error (WPE) Dereverberation Filter
    WpeDereverb,
}

impl fmt::Display for FilterType {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::MvdrCovariance => write!(f, "MVDR Covariance"),
            Self::GscBlocking => write!(f, "GSC Blocking Filter"),
            Self::AfcShadow => write!(f, "AFC Shadow Filter"),
            Self::KalmanDoa => write!(f, "Kalman DOA Tracker"),
            Self::WpeDereverb => write!(f, "WPE Dereverberator"),
        }
    }
}

/// State of an individual adaptive filter.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConvergenceState {
    /// Adaptation in progress; steady-state not yet attained
    Adapting,
    /// Within tolerance band, accumulating required dwell frames
    DwellConfirming,
    /// Fully converged within tolerance band
    Converged,
    /// Filter diverged or gradient norm exceeded stability limits
    Diverged,
}

/// Configuration for individual filter convergence tracking.
#[derive(Debug, Clone)]
pub struct FilterConvergenceConfig {
    /// Target convergence tolerance $\delta$ (e.g. 0.05 = 5% relative variance)
    pub tolerance: f32,
    /// Required continuous dwell time in milliseconds (default: 50.0 ms)
    pub dwell_time_ms: f32,
    /// Maximum allowable metric value before flagging divergence (default: 100.0)
    pub divergence_ceiling: f32,
    /// Sample rate in Hz (default: 16000.0)
    pub sample_rate: f32,
    /// Frame / block hop size in samples (default: 128 = 8.0 ms)
    pub hop_size: usize,
}

impl Default for FilterConvergenceConfig {
    fn default() -> Self {
        Self {
            tolerance: 0.05,
            dwell_time_ms: 50.0,
            divergence_ceiling: 100.0,
            sample_rate: 16000.0,
            hop_size: 128,
        }
    }
}

/// Diagnostic snapshot of a single filter's convergence profile.
#[derive(Debug, Clone, Copy, Default)]
pub struct FilterConvergenceStatus {
    /// Convergence state
    pub is_converged: bool,
    /// Time taken to converge in milliseconds (0.0 if not yet converged)
    pub convergence_time_ms: f32,
    /// Current normalized metric value
    pub current_metric: f32,
    /// Steady-state average value after convergence
    pub steady_state_value: f32,
    /// Total elapsed tracking time in milliseconds
    pub elapsed_time_ms: f32,
    /// Whether divergence was detected
    pub has_diverged: bool,
}

/// Zero-allocation Tracker for an Individual Adaptive Filter.
pub struct SingleFilterTracker {
    config: FilterConvergenceConfig,
    state: ConvergenceState,
    elapsed_frames: usize,
    dwell_frames_needed: usize,
    dwell_frames_count: usize,
    convergence_frame: Option<usize>,
    prev_metric: f32,
    smoothed_metric: f32,
}

impl SingleFilterTracker {
    pub fn new(config: FilterConvergenceConfig) -> Self {
        let frame_ms = (config.hop_size as f32 / config.sample_rate) * 1000.0;
        let dwell_frames = (config.dwell_time_ms / frame_ms.max(1.0)).ceil() as usize;

        Self {
            config,
            state: ConvergenceState::Adapting,
            elapsed_frames: 0,
            dwell_frames_needed: dwell_frames.max(1),
            dwell_frames_count: 0,
            convergence_frame: None,
            prev_metric: 0.0,
            smoothed_metric: 0.0,
        }
    }

    /// Resets tracking to initial state (e.g. after acoustic scene change or disturbance).
    pub fn reset(&mut self) {
        self.state = ConvergenceState::Adapting;
        self.elapsed_frames = 0;
        self.dwell_frames_count = 0;
        self.convergence_frame = None;
        self.prev_metric = 0.0;
        self.smoothed_metric = 0.0;
    }

    /// Feeds a new frame metric value (e.g., $\|\Delta w\|^2$, residual power, or ERLE).
    /// Strictly zero heap allocations.
    pub fn update(&mut self, metric_val: f32) -> FilterConvergenceStatus {
        self.elapsed_frames += 1;

        if metric_val.is_nan() || metric_val > self.config.divergence_ceiling {
            self.state = ConvergenceState::Diverged;
        }

        if self.elapsed_frames == 1 {
            self.prev_metric = metric_val;
            self.smoothed_metric = metric_val;
        } else {
            self.smoothed_metric = 0.85 * self.smoothed_metric + 0.15 * metric_val;
        }

        // Relative delta between current metric and previous metric (or smoothed steady state)
        let delta = if self.elapsed_frames <= 1 {
            1.0
        } else {
            let step_delta = (metric_val - self.prev_metric).abs() / (metric_val.abs() + 1e-6);
            let smooth_delta =
                (metric_val - self.smoothed_metric).abs() / (self.smoothed_metric.abs() + 1e-6);
            step_delta.min(smooth_delta)
        };

        match self.state {
            ConvergenceState::Adapting => {
                if delta <= self.config.tolerance {
                    self.state = ConvergenceState::DwellConfirming;
                    self.dwell_frames_count = 1;
                }
            }
            ConvergenceState::DwellConfirming => {
                if delta <= self.config.tolerance {
                    self.dwell_frames_count += 1;
                    if self.dwell_frames_count >= self.dwell_frames_needed {
                        self.state = ConvergenceState::Converged;
                        if self.convergence_frame.is_none() {
                            self.convergence_frame = Some(self.elapsed_frames);
                        }
                    }
                } else {
                    // Broke out of tolerance band: restart dwell confirmation
                    self.state = ConvergenceState::Adapting;
                    self.dwell_frames_count = 0;
                }
            }
            ConvergenceState::Converged => {
                // If massive disruption occurs, un-converge
                if delta > self.config.tolerance * 4.0 {
                    self.state = ConvergenceState::Adapting;
                    self.dwell_frames_count = 0;
                    self.convergence_frame = None;
                }
            }
            ConvergenceState::Diverged => {}
        }

        self.prev_metric = metric_val;
        self.status()
    }

    /// Returns current status snapshot.
    pub fn status(&self) -> FilterConvergenceStatus {
        let frame_ms = (self.config.hop_size as f32 / self.config.sample_rate) * 1000.0;
        let elapsed_ms = self.elapsed_frames as f32 * frame_ms;
        let conv_ms = self
            .convergence_frame
            .map(|f| f as f32 * frame_ms)
            .unwrap_or(0.0);

        FilterConvergenceStatus {
            is_converged: self.state == ConvergenceState::Converged,
            convergence_time_ms: conv_ms,
            current_metric: self.prev_metric,
            steady_state_value: self.smoothed_metric,
            elapsed_time_ms: elapsed_ms,
            has_diverged: self.state == ConvergenceState::Diverged,
        }
    }
}

/// Multi-filter convergence profiler tracking all adaptive subsystems simultaneously.
pub struct AdaptiveConvergenceProfiler {
    pub mvdr: SingleFilterTracker,
    pub gsc: SingleFilterTracker,
    pub afc: SingleFilterTracker,
    pub kalman: SingleFilterTracker,
    pub wpe: SingleFilterTracker,
}

impl AdaptiveConvergenceProfiler {
    /// Creates a profiler tracking MVDR, GSC, AFC, Kalman DOA, and WPE dereverberation.
    pub fn new(sample_rate: f32, hop_size: usize) -> Self {
        let base_cfg = FilterConvergenceConfig {
            sample_rate,
            hop_size,
            ..Default::default()
        };

        // Custom dwell and tolerance parameters matched to physical convergence bounds
        let mvdr_cfg = FilterConvergenceConfig {
            tolerance: 0.08,
            dwell_time_ms: 48.0,
            ..base_cfg.clone()
        };
        let gsc_cfg = FilterConvergenceConfig {
            tolerance: 0.05,
            dwell_time_ms: 40.0,
            ..base_cfg.clone()
        };
        let afc_cfg = FilterConvergenceConfig {
            tolerance: 0.06,
            dwell_time_ms: 48.0,
            ..base_cfg.clone()
        };
        let kalman_cfg = FilterConvergenceConfig {
            tolerance: 0.04,
            dwell_time_ms: 32.0,
            ..base_cfg.clone()
        };
        let wpe_cfg = FilterConvergenceConfig {
            tolerance: 0.07,
            dwell_time_ms: 64.0,
            ..base_cfg
        };

        Self {
            mvdr: SingleFilterTracker::new(mvdr_cfg),
            gsc: SingleFilterTracker::new(gsc_cfg),
            afc: SingleFilterTracker::new(afc_cfg),
            kalman: SingleFilterTracker::new(kalman_cfg),
            wpe: SingleFilterTracker::new(wpe_cfg),
        }
    }

    /// Resets all filter trackers.
    pub fn reset_all(&mut self) {
        self.mvdr.reset();
        self.gsc.reset();
        self.afc.reset();
        self.kalman.reset();
        self.wpe.reset();
    }

    /// Checks if all active adaptive filters have achieved convergence.
    pub fn all_converged(&self) -> bool {
        self.mvdr.status().is_converged
            && self.gsc.status().is_converged
            && self.afc.status().is_converged
            && self.kalman.status().is_converged
            && self.wpe.status().is_converged
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_single_filter_convergence_detection() {
        let cfg = FilterConvergenceConfig {
            tolerance: 0.05,
            dwell_time_ms: 24.0, // 3 frames @ 8.0 ms
            divergence_ceiling: 50.0,
            sample_rate: 16000.0,
            hop_size: 128,
        };
        let mut tracker = SingleFilterTracker::new(cfg);

        // Initially decaying adaptation
        tracker.update(10.0);
        tracker.update(5.0);
        tracker.update(2.5);
        tracker.update(1.2);
        assert!(!tracker.status().is_converged);

        // Stabilizes around ~1.0 across frames
        for _ in 0..25 {
            tracker.update(1.0);
        }

        let st = tracker.status();
        assert!(
            st.is_converged,
            "Filter should be declared converged after stable dwell"
        );
        assert!(st.convergence_time_ms > 0.0);
        assert!(!st.has_diverged);
    }

    #[test]
    fn test_single_filter_divergence_flag() {
        let cfg = FilterConvergenceConfig {
            divergence_ceiling: 20.0,
            ..Default::default()
        };
        let mut tracker = SingleFilterTracker::new(cfg);
        tracker.update(1.0);
        tracker.update(100.0); // Blow up beyond divergence ceiling
        assert!(tracker.status().has_diverged);
    }
}
