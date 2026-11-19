# Stage 11.2.20 — Low-Latency Pipeline Optimization and Deadline Analysis

## Verdict

**The small-queue, 16 ms chunk configuration reduced queue delay in the tested synthetic GTCRN host path, but the project is not real-time qualified and the 35 ms target is not established.** In the final 4-second threaded run, the tight profile's measured source-to-playout latency was mean 35.11 ms, p95 36.74 ms, p99 37.84 ms, maximum 47.94 ms. The ideal software sample-clock estimate was p99 30.12 ms; the host sink scheduler had p99 deadline lateness 7.28 ms. This is a software-only GTCRN result on the development Mac, not a Pi 5 result, not the deployed DFN3 Step-500 path, and not proof of the system target.

## Why Stage 11.2.19 showed a 51 ms processing p99

Stage 11.2.19 deliberately used mixed chunks from 160 to 4,096 samples and a consumer model running at half the sample rate with an added 200 ms stall every 13 chunks. Its 51.26 ms p99 is a **per-call processing duration across different chunk sizes**, not a fixed 16 ms frame deadline. A 4,096-sample call represents 256 ms of input and performs many frame steps in one call.

The Stage 11.2.20 controlled profile shows the expected scaling: with 4,096-sample chunks, mean/p99 call time was 33.25/34.53 ms (mean RTF 0.133); with 256-sample chunks (16 ms), mean/p99 was 2.13/2.51 ms (mean RTF 0.133). The earlier 51.26 ms result is higher than this run's 4,096-sample p99 and is consistent with single-run host scheduling/load variation. It should be retained as an observed tail, not treated as a stable model constant. Smaller caller chunks reduce absolute call duration but do not materially change per-audio-second compute cost.

The Stage 11.2.19 queue ages in the hundreds of milliseconds were also produced under its intentionally slow 0.5x consumer and bursty producer. They are useful stress evidence, but they are not a latency estimate for the normal-rate GTCRN path.

## Implementation and experiment

The experiment uses the pinned GTCRN model and Stage 11.2.17 stateful adapter unchanged. A CPU profiler tested 64, 128, 256, 512, 1,024, 2,048 and 4,096 sample calls on seeded synthetic signals. The concurrent path used an actual paced synthetic producer thread, the actual GTCRN inference consumer thread and a software playback sink scheduled against absolute sample-clock deadlines. Absolute deadlines avoid adding one host sleep overshoot per audio block. Producer, consumer and sink ran concurrently; capture backpressure retained and retried chunks. No canonical audio, ensemble waveform, gold data, network, or physical device was used.

A synthetic adapter preflight for 4 seconds of fixed 256-sample hop-aligned chunks produced exactly 64,000 output samples. Ordinary output blocks were at most 256 samples; the final flush produced 512. The concurrent study used those **workload-specific measured reservations** (256 ordinary, 512 final); these are not a general upper bound for arbitrary chunking. Each of the three fixed queue profiles then processed the actual GTCRN stream.

## Chunk-size profile

| Input chunk | Chunk period | Mean call | p99 call | Mean RTF | Per-call deadline misses |
|---:|---:|---:|---:|---:|---:|
| 64 samples | 4 ms | 0.535 ms | 2.193 ms | 0.134 | 1/1,000 |
| 128 samples | 8 ms | 1.135 ms | 4.284 ms | 0.142 | 0/500 |
| 256 samples | 16 ms | 2.130 ms | 2.506 ms | 0.133 | 0/250 |
| 512 samples | 32 ms | 4.510 ms | 7.319 ms | 0.141 | 0/125 |
| 1,024 samples | 64 ms | 8.435 ms | 8.637 ms | 0.133 | 0/63 |
| 2,048 samples | 128 ms | 16.685 ms | 17.263 ms | 0.135 | 0/32 |
| 4,096 samples | 256 ms | 33.246 ms | 34.532 ms | 0.133 | 0/16 |

This profile is a single host run; the small sample counts for 2,048 and 4,096-sample calls make their p99 estimates coarse. RTF is normalized compute time per audio duration. A per-call miss means measured call time exceeded that call's input duration; it does not establish end-to-end latency.

## Continuous threaded host results

All profiles used the same four-second synthetic source at 16 kHz, mono, with 256-sample (16 ms) chunks. Queue profiles differ only in configured queue capacities; measured workload-specific output reservations were fixed at 256 samples for ordinary calls and 512 for final flush. Values below are from final run `r8`.

| Queue profile | Capture / playback capacity | Capture age p99 / max | Playback age p99 / max | Source-to-playout mean / p95 / p99 / max | Sample-clock latency p99 | Producer backpressure | Consumer playback backpressure |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Tight** | 512 / 512 samples (32 / 32 ms) | 3.27 / 15.32 ms | 27.96 / 33.47 ms | **35.11 / 36.74 / 37.84 / 47.94 ms** | **30.12 ms** | 0 events | 24 events, 36.13 ms total |
| Medium | 1,024 / 1,024 (64 / 64 ms) | 0.06 / 0.07 ms | 36.44 / 47.09 ms | 40.07 / 42.86 / 43.33 / 45.80 ms | 35.78 ms | 0 events | 0 events |
| Large | 8,192 / 8,192 (512 / 512 ms) | 0.06 / 0.51 ms | 37.25 / 47.39 ms | 41.23 / 43.97 / 44.32 / 46.59 ms | 36.57 ms | 0 events | 0 events |

“Source-to-playout” measures actual host time at sink delivery relative to the corresponding output sample's scheduled source time. “Sample-clock latency” uses the absolute configured sink sample clock. Host sink wake lateness in the tight profile was p99 7.28 ms, maximum 7.94 ms. The queue age is enqueue-to-sink-completion, so it includes the block's playback duration; it is not solely waiting time.

The tight profile had 250 inference calls, mean/p95/p99 processing 5.24/5.80/6.02 ms, maximum 10.94 ms, and zero calls above the 16 ms input period. Host RTF was 1.012 for the complete producer/inference/sink run. All profiles generated, accepted, processed and delivered exactly 64,000 samples, with zero loss, zero reordering, and output cursor 64,000. Queue high-water marks stayed within limits: tight capture 256/512 and playback 512/512 samples; medium capture 256/1,024 and playback 768/1,024; large capture 256/8,192 and playback 768/8,192.

The tight queue reduced the measured p99 host delivery latency by 5.50 ms versus medium and 6.49 ms versus large. It produced 24 brief consumer-side backpressure waits (36.13 ms cumulative) before inference, but no source backpressure or sample loss. Larger queues did not improve latency and permit more buffering. This supports the tight 32 ms/32 ms pair for this fixed synthetic GTCRN workload only. It does not define a device buffer setting.

## Regression tests and integrity

`test_concurrent_pipeline.py` passed **2/2 tests**. One exercised paced operation; the other deliberately slowed a fake consumer and verified that backpressure occurred without loss or reordering. Both checked queue capacity and exact 64,000-sample accounting. The real GTCRN threaded runs also passed exact input/output accounting for all three queue profiles.

Protected SHA-256 values matched before and after the experiment. See `run_metadata.json` in `runs/stage11_2_20_low_latency/run_20261114_r8/` for hashes, environment and command; `SHA256SUMS.txt` hashes source and evidence files. No protected checkpoint, manifest, or ensemble output was changed.

## Failed and superseded attempts

- Initial command invocations used incorrect working-directory/virtual-environment paths and exited nonzero before running experiments. The first unit-test fixture also requested a one-second stream that was not divisible into 256-sample chunks; it was changed to a four-second aligned stream.
- `r1` exited because its 16,000-sample warmup exceeded the adapter's 4,096-sample call limit; warmup was split into valid calls.
- `r2`–`r4` used an event replay that exposed generated outputs before modeled inference service completed; those latency figures are **not used**.
- `r5` correctly detected a 512-sample final flush that exceeded the initial 256-sample reserve. The final call now receives its own 512-sample reservation.
- `r6` used per-block relative sleeps and accumulated host scheduling overshoot, causing sink drift. Its timing figures are **not used**. `r7`/`r8` use absolute sample-clock deadlines and separately report host wake lateness.

These attempts are preserved under their run directories; the authoritative result is `r8`.

## Limitations and next step

This stage tests one fixed chunk cadence and synthetic signal, uses a producer allowed to wait on backpressure, and runs on the development Mac CPU. A real microphone cannot pause; if the downstream path falls behind, it needs an explicit hardware-buffer/overflow policy. The playback sink is a timer model, not ALSA, DMA, DAC, headset, or a physical Pi. Scheduler observations are single-run and host-specific. No speech-quality evaluation or model tuning was performed. The frozen 15/70/15 ensemble remains unchanged and was not used for this streaming test.

**Do not claim 35 ms system compliance.** The measured GTCRN synthetic host p99 is 37.84 ms (maximum 47.94 ms), and the project's deployed candidate is DFN3 Step-500 with a separately reported estimated physical latency of 49.5–54.5 ms and a 30 ms algorithmic delay. Raspberry Pi 5 performance, DFN3 Step-500 live latency, actual device buffering, and the full wired audio path remain outstanding. Next work should keep the model and ensemble frozen, use a real-time audio callback only after the existing authorization gates allow hardware access, and evaluate any software changes against the unchanged behavioral contracts before making target claims.
