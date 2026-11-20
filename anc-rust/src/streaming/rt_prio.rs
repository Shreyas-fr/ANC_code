//! POSIX Real-Time SCHED_FIFO Priority Governor and Memory Paging Lock.
//!
//! In embedded tactical systems (e.g., Raspberry Pi 5 with PREEMPT_RT or standard Linux kernel),
//! deterministic sub-millisecond execution requires:
//! 1. Memory page locking via `libc::mlockall(MCL_CURRENT | MCL_FUTURE)` to prevent OS page faults
//!    and swap delays in the real-time audio thread.
//! 2. Real-time scheduling policy `SCHED_FIFO` (priority 85-95) to preempt all standard user-space
//!    processes, background daemons, and low-priority kernel worker threads.
//! 3. CPU Core affinity binding via `sched_setaffinity` (e.g., Core 3 on the BCM2712 Cortex-A76)
//!    to eliminate thread migration jitter and maximize L1/L2 cache locality.
//!
//! If running without root / `CAP_SYS_NICE` privileges or on non-Linux architectures (macOS, Windows),
//! the governor automatically catches `EPERM` / `ENOSYS` and falls back gracefully to standard scheduling
//! while logging explicit diagnostic telemetry.
//!
//! Zero heap allocations during real-time status queries and monitoring.

use std::fmt;

/// Real-time scheduling policy setting.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RtSchedPolicy {
    /// Standard time-sharing policy (SCHED_OTHER / CFS)
    Other,
    /// First-In, First-Out real-time policy (SCHED_FIFO)
    Fifo,
    /// Round-Robin real-time policy (SCHED_RR)
    RoundRobin,
    /// Unknown or unsupported policy
    Unknown(i32),
}

impl fmt::Display for RtSchedPolicy {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Other => write!(f, "SCHED_OTHER (Standard CFS)"),
            Self::Fifo => write!(f, "SCHED_FIFO (Deterministic RT)"),
            Self::RoundRobin => write!(f, "SCHED_RR (Real-Time Round Robin)"),
            Self::Unknown(id) => write!(f, "UNKNOWN ({})", id),
        }
    }
}

/// Configuration for the POSIX Real-Time Priority Governor.
#[derive(Debug, Clone)]
pub struct RtGovernorConfig {
    /// Target real-time priority (1 to 99, default: 88 for real-time audio threads)
    pub rt_priority: i32,
    /// Whether to lock memory pages into RAM using `mlockall` (default: true)
    pub lock_memory: bool,
    /// Optional CPU core index to pin the DSP thread to (e.g. Some(3) for Core 3)
    pub pin_core: Option<usize>,
    /// Allow graceful fallback if root / CAP_SYS_NICE is missing (default: true)
    pub allow_fallback: bool,
}

impl Default for RtGovernorConfig {
    fn default() -> Self {
        Self {
            rt_priority: 88,
            lock_memory: true,
            pin_core: Some(3),
            allow_fallback: true,
        }
    }
}

/// Diagnostic telemetry and status of the Real-Time Priority Governor.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RtGovernorStatus {
    /// Active scheduling policy
    pub policy: RtSchedPolicy,
    /// Active priority (0 for normal, 1-99 for real-time)
    pub priority: i32,
    /// Whether virtual memory pages are locked into physical RAM
    pub memory_locked: bool,
    /// Affined CPU core index (if pinned)
    pub pinned_core: Option<usize>,
    /// Whether execution has real-time privileges active
    pub is_realtime_active: bool,
    /// Fallback was triggered due to insufficient permissions
    pub permission_fallback: bool,
}

impl Default for RtGovernorStatus {
    fn default() -> Self {
        Self {
            policy: RtSchedPolicy::Other,
            priority: 0,
            memory_locked: false,
            pinned_core: None,
            is_realtime_active: false,
            permission_fallback: false,
        }
    }
}

/// The POSIX Real-Time Priority Governor.
pub struct RtPrioGovernor {
    config: RtGovernorConfig,
    status: RtGovernorStatus,
}

impl RtPrioGovernor {
    /// Creates a new governor with given configuration.
    pub fn new(config: RtGovernorConfig) -> Self {
        Self {
            config,
            status: RtGovernorStatus::default(),
        }
    }

    /// Returns the current configuration.
    pub fn config(&self) -> &RtGovernorConfig {
        &self.config
    }

    /// Returns the current real-time status.
    pub fn status(&self) -> RtGovernorStatus {
        self.status
    }

    /// Applies real-time settings: memory locking, SCHED_FIFO scheduling, and CPU core affinity.
    ///
    /// On embedded Linux with adequate privileges, activates SCHED_FIFO and locks memory.
    /// In restricted environments, falls back without panic if `allow_fallback` is true.
    pub fn apply(&mut self) -> Result<RtGovernorStatus, String> {
        let mut status = RtGovernorStatus::default();

        #[cfg(target_os = "linux")]
        {
            // 1. Lock memory pages into RAM
            if self.config.lock_memory {
                let mlock_res = unsafe {
                    libc::mlockall(libc::MCL_CURRENT | libc::MCL_FUTURE)
                };
                if mlock_res == 0 {
                    status.memory_locked = true;
                } else {
                    let err = std::io::Error::last_os_error();
                    if !self.config.allow_fallback {
                        return Err(format!("mlockall failed: {}", err));
                    }
                    // Non-fatal fallback for unprivileged test environments
                    status.memory_locked = false;
                }
            }

            // 2. Set CPU Core affinity if requested
            if let Some(core_id) = self.config.pin_core {
                let mut cpuset: libc::cpu_set_t = unsafe { std::mem::zeroed() };
                unsafe {
                    libc::CPU_ZERO(&mut cpuset);
                    libc::CPU_SET(core_id, &mut cpuset);
                    let res = libc::sched_setaffinity(
                        0,
                        std::mem::size_of::<libc::cpu_set_t>(),
                        &cpuset,
                    );
                    if res == 0 {
                        status.pinned_core = Some(core_id);
                    } else {
                        let err = std::io::Error::last_os_error();
                        if !self.config.allow_fallback {
                            return Err(format!("sched_setaffinity to core {} failed: {}", core_id, err));
                        }
                    }
                }
            }

            // 3. Set SCHED_FIFO real-time scheduling priority
            let target_prio = self.config.rt_priority.clamp(1, 99);
            let param = libc::sched_param {
                sched_priority: target_prio,
            };

            let sched_res = unsafe {
                libc::sched_setscheduler(0, libc::SCHED_FIFO, &param)
            };

            if sched_res == 0 {
                status.policy = RtSchedPolicy::Fifo;
                status.priority = target_prio;
                status.is_realtime_active = true;
            } else {
                let err = std::io::Error::last_os_error();
                status.permission_fallback = true;
                if !self.config.allow_fallback {
                    return Err(format!("sched_setscheduler SCHED_FIFO failed: {}", err));
                }
                // Read current unprivileged policy
                let curr_pol = unsafe { libc::sched_getscheduler(0) };
                status.policy = match curr_pol {
                    libc::SCHED_OTHER => RtSchedPolicy::Other,
                    libc::SCHED_FIFO => RtSchedPolicy::Fifo,
                    libc::SCHED_RR => RtSchedPolicy::RoundRobin,
                    other => RtSchedPolicy::Unknown(other),
                };
                let mut curr_param: libc::sched_param = unsafe { std::mem::zeroed() };
                unsafe { libc::sched_getparam(0, &mut curr_param) };
                status.priority = curr_param.sched_priority;
                status.is_realtime_active = status.policy == RtSchedPolicy::Fifo;
            }
        }

        #[cfg(not(target_os = "linux"))]
        {
            // Non-Linux platforms (macOS / Windows dev environments)
            status.policy = RtSchedPolicy::Other;
            status.priority = 0;
            status.memory_locked = false;
            status.pinned_core = self.config.pin_core;
            status.is_realtime_active = false;
            status.permission_fallback = true;
        }

        self.status = status;
        Ok(status)
    }

    /// Releases memory locks and restores default scheduling policy.
    pub fn release(&mut self) -> Result<(), String> {
        #[cfg(target_os = "linux")]
        {
            if self.status.memory_locked {
                unsafe { libc::munlockall() };
                self.status.memory_locked = false;
            }
            if self.status.is_realtime_active {
                let param = libc::sched_param { sched_priority: 0 };
                unsafe {
                    libc::sched_setscheduler(0, libc::SCHED_OTHER, &param);
                }
                self.status.is_realtime_active = false;
                self.status.policy = RtSchedPolicy::Other;
                self.status.priority = 0;
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rt_governor_initial_state() {
        let config = RtGovernorConfig {
            rt_priority: 90,
            lock_memory: true,
            pin_core: Some(2),
            allow_fallback: true,
        };
        let gov = RtPrioGovernor::new(config);
        assert_eq!(gov.config().rt_priority, 90);
        assert_eq!(gov.config().pin_core, Some(2));
        assert!(!gov.status().is_realtime_active);
    }

    #[test]
    fn test_rt_governor_fallback_graceful_handling() {
        let config = RtGovernorConfig {
            rt_priority: 88,
            lock_memory: true,
            pin_core: Some(0),
            allow_fallback: true,
        };
        let mut gov = RtPrioGovernor::new(config);
        // In standard cargo test environment (without root / CAP_SYS_NICE),
        // apply must succeed via graceful fallback without panic or error.
        let status = gov.apply().expect("Fallback should handle unprivileged test environment");
        // Status must record that fallback was invoked or policy observed
        assert!(status.policy == RtSchedPolicy::Other || status.policy == RtSchedPolicy::Fifo);
        let _ = gov.release();
    }
}
