# SIH 26052 Deployment Validation Status

**Status:** No new deployment was performed. The existing Deployed Step-500 checkpoint remains the candidate and its active Pi service was not contacted or changed during this work.

| Validation item | Status | Evidence/notes |
|---|---|---|
| Offline canonical Step-500 replay | Passed | 590 clips; exact per-clip match to saved reference; manifest SHA-256 `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`. |
| Offline FullSubNet replay | Passed | CPU wall RTF 0.131 on this host; no Pi inference implication. |
| Simulated streaming, current model | Historical evidence only | Prior project artifacts describe streaming replay; not rerun here. |
| Simulated streaming, FullSubNet | Not tested | Offline Laplace normalization and two-frame look-ahead require a purpose-built latency/state design. |
| Pi p50/p95/p99/max timing | Not measured in this work | No Pi connection. |
| Configured buffering and actual mic-to-headphone latency | Not measured in this work | Must measure with connected live capture and playback path; model RTF is not end-to-end latency. |
| Deadline misses, late fallbacks, dropped frames, reconnects | Not measured in this work | Requires Pi streaming soak and event logging. |
| CPU, memory, temperature, throttling | Not measured in this work | Requires target hardware. |
| Live microphone capture and headset playback | Not tested in this work | No audio was transmitted to another device. |
| Five-minute/long soak | Not run | Deployment gate remains open. |
| Output clipping/discontinuities under real playback | Not tested | Requires capture and output loopback review. |

**Decision:** Do not deploy FullSubNet or any newly evaluated artifact based on offline quality alone. Keep the current Step-500 route unchanged. No model in this report meets the full-set mean SNR target, and no end-to-end Pi acceptance claim is made.
