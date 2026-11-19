# DeepFilterNet3 Pi 5 Final Real-Time Audit

## 1. Objective
Perform the final long-duration stability validation of the native Rust/Tract DeepFilterNet3 implementation on the Raspberry Pi 5 to guarantee 10 ms strict real-time audio inference without deadline misses.

## 2. Environment
- **Pi Model:** Raspberry Pi 5 Model B Rev 1.1
- **OS:** Debian GNU/Linux 13 (trixie)
- **Kernel:** 6.18.50+rpt-rpi-2712
- **Architecture:** aarch64
- **CPU Count:** 4
- **Available RAM:** 2.0Gi
- **Rust Version:** rustc 1.99.0
- **Cargo Version:** cargo 1.99.0

## 3. Model Artifact
- **Tract Version:** 0.21.4
- **libDF Version:** 0.5.7-pre
- **DeepFilterNet Version:** 0.5.6
- **Model SHA256:** 375994cdfe2d29117d71341e9a3e4c7ff347827e6a83002d7b47eda36027a90e
- **Binary SHA256:** 1b8cd5a5dab1e828e92123b58464aaafe453f88d8641e456714ea109e7246203

## 4. Runtime Configuration
- **CPU Governor:** performance
- **CPU Frequencies (min/max):** 1.5 GHz / 2.4 GHz
- **Affinity:** taskset -c 3
- **Priority:** chrt -f 99
- **Frame Config:** 48 kHz, 480 samples/frame, 10 ms deadline, persistent GRU state.

## 5. 60-Second Test
- **Duration:** 60 seconds (6,000 frames)
- **Median:** 2.12 ms
- **P95:** 3.40 ms
- **P99:** 3.51 ms
- **Max:** 22.26 ms
- **Misses:** 1
- **RTF:** 0.222
- **Peak Temp:** 77.7'C
- **NaN/Inf:** 0
- **State Resets:** 0

## 6. 5-Minute Test
Skipped. The 60-second strict hard real-time gate failed.

## 7. Repeatability Test
Skipped.

## 8. Audio Integrity
The 60-second test output produced `dfn3_native_60s.wav` which exhibits no clipping, correct sample rate, correct channel count, and finite samples.

## 9. State Integrity
The Tract state correctly persisted throughout the 6,000 frames with 0 recorded state resets.

## 10. Thermal Behavior
- **Initial temperature:** 75.4'C
- **Peak temperature:** 77.7'C
- **Final temperature:** 77.7'C
- **Throttle detected:** YES (`throttled=0xf0000` recorded, indicating soft-temperature frequency capping occurred).
- **CPU frequency minimum:** 1.5 GHz
- **CPU frequency maximum:** 2.4 GHz

## 11. Performance Summary
| Test | Duration | Median | P95 | P99 | Max | Misses | RTF | Peak Temp |
|---|---|---|---|---|---|---|---|---|
| 60-Second | 60s | 2.12 ms | 3.40 ms | 3.51 ms | 22.26 ms | 1 | 0.222 | 77.7'C |

## 12. Hard Real-Time Gate
- **60-second gate:** FAIL
- **5-minute gate:** FAIL
- **Repeatability:** FAIL
- **Overall:** NOT_REALTIME_READY

## 13. Limitations
The following measurements were NOT recorded and should not be implied:
- microphone-to-speaker end-to-end latency
- Bluetooth latency
- UDP network latency
- PC playback latency

## 14. Production Recommendation
NATIVE_DFN3_REQUIRES_FURTHER_OPTIMIZATION
