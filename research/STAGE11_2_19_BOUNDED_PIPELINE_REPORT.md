# Stage 11.2.19 — Bounded Producer–Consumer Pipeline Report

## Decision

**Host-side bounded producer-consumer pipeline verified under the tested synthetic workloads.** This result is limited to the host simulation and software tests described below. It is not Raspberry Pi 5 qualified, real-time qualified, 35 ms end-to-end compliant, headset-ready, independently validated, or evidence of speech-quality equivalence to the frozen ensemble.

## Scope and safeguards

Implemented a bounded host pipeline around the existing Stage 11.2.17/11.2.18 GTCRN stateful adapter. The only generated signal data was deterministic synthetic audio at 16 kHz mono. The actual GTCRN checkpoint was loaded for the synthetic stress and session-reset checks; weights and inference behavior were not changed. No training, canonical benchmark inference, live audio, hardware, ALSA, network transfer, or gold-set access was performed.

Before/after protected hashes match for DFN3 Step-500, FullSubNet epoch 58, GTCRN DNS3, the canonical manifest, frozen ensemble summary/per-clip ledger, V10 config/candidate checkpoint, and the Stage 17 adapter. The deployed Step-500 Tract archive was unavailable and was not substituted. Hashes are in the run metadata at [run_metadata.json](../runs/stage11_2_19_bounded_audio_pipeline/run_20261114_r10/run_metadata.json).

## Architecture and contracts

- `SyntheticProducer` emits timestamped chunks with a deterministic nonuniform chunk pattern and configurable ten-chunk bursts.
- The capture and playback FIFOs are bounded in samples, preserve FIFO sample timestamps, expose occupancy/high-water/age telemetry, and reject writes that exceed capacity.
- The producer owns a pending chunk until accepted. On a full capture queue, the pipeline returns `BACKPRESSURE`; the producer retries the same chunk after capacity becomes available. No silent drop-oldest behavior is used.
- If the producer cannot pause or retry, the session is terminated and each discarded input/output interval is recorded as a discontinuity. Recovery starts a new session at an explicit sample index after adapter reset.
- Invalid, non-mono, non-finite, complex, zero-length, or oversized input is rejected before adapter state changes. Calls respect the adapter's 4,096-sample maximum.
- Before processing, playback capacity is reserved for the current chunk plus the adapter's declared output tail (512 samples for this adapter). If the reservation is unavailable, the consumer pauses before mutating adapter state.
- Consumer exceptions fail the session, account pending input/output intervals, reset adapter state, and require an explicit new session.
- Queue age and processing percentiles retain at most 4,096 observations; streaming counts, sums, and maxima remain exact. The event-level CSV is an audit log and scales with the number of events.

## Test matrix and results

`test_bounded_pipeline.py` passed **20/20** deterministic unit tests, including queue-capacity boundaries and one-sample/chunk beyond capacity; FIFO ordering; timestamp gaps; normal and burst operation; slow/stalled consumer backpressure; capture/playback saturation; invalid and oversized inputs; unpausable overflow and exact loss ranges; consumer exception and recovery; reset with pending queues; repeated-session isolation; 2,000-chunk operation; and bounded telemetry retention after 5,000 observations.

The runner also passed four explicit policy probes: same-chunk capture retry; unpausable capture overflow with exact interval accounting and restart; playback saturation propagating backpressure; and consumer exception/reset/recovery. The session-isolation probe using a stateful fake adapter passed. With the actual GTCRN adapter, session B after reset was bit-identical to a fresh adapter on the same synthetic input (`max_abs_diff_vs_fresh_adapter = 0.0`).

The 20-second actual-adapter soak completed **320,000 samples (20.0 seconds)**. A deterministic bursty producer was paired with a simulated 0.5× consumer plus a 200 ms stall every 13 consumed chunks and a 16 kHz playback sink. Results:

| Measurement | Capture | Playback |
|---|---:|---:|
| Fixed capacity | 8,192 samples (512 ms) | 8,192 samples (512 ms) |
| Time-weighted mean occupancy | 3,265.39 samples | 2,937.94 samples |
| High-water occupancy | 8,160 samples | 4,096 samples |
| Mean observed dequeue age | 238.46 ms | 113.64 ms |
| p95 / p99 dequeue age | 450.00 / 493.36 ms | 256.00 / 256.00 ms |
| Maximum observed item age | 556.00 ms | 256.00 ms |

The producer generated 183 chunks at 16 kHz with pattern `[1024, 256, 2048, 512, 4096, 160, 320, 3072, 2048, 4096]`, arranged in ten-chunk bursts every 0.6 s with 1 ms spacing. Eight capture backpressure events occurred, totaling 265 ms from first blocked offer to successful retry. Playback backpressure did not occur in this soak; its propagation path was exercised by the separate policy probe. No overflow loss occurred in the soak.

| Accounting / continuity | Result |
|---|---:|
| Producer-generated / accepted / processed input | 320,000 / 320,000 / 320,000 samples |
| Generated / delivered output | 320,000 / 320,000 samples |
| Lost input / output | 0 / 0 samples |
| Rejected input / consumer failures / discontinuities | 0 / 0 / 0 |
| Output sample cursor | 320,000 (exact expected endpoint) |
| Adapter input ring maximum / overlap-add ring maximum | 545 / 512 samples |

Measured adapter processing wall time was mean 21.43 ms, p95 50.00 ms, p99 51.26 ms, maximum 73.20 ms across 183 chunks. This is host-side call duration on the recorded macOS ARM64 environment; it is not audio latency or a real-time guarantee.

## Memory evidence and limits

The measured process RSS high-water was 232,882,176 bytes; the stream baseline before the soak was 232,046,592 bytes, for an observed increase of 835,584 bytes during this 20-second run. Python `tracemalloc` peak during the soak was 557,623 bytes. RSS used `resource.getrusage(...).ru_maxrss`, a cumulative high-water sampler, not instantaneous RSS. PyTorch/model allocation, allocator caching, and host OS behavior contribute to RSS. Memory checkpoints and fixed queue/adapter ring bounds are in [memory_telemetry.csv](../runs/stage11_2_19_bounded_audio_pipeline/run_20261114_r10/memory_telemetry.csv).

The capture/playback audio storage and adapter input/OLA rings stayed within fixed limits during this run. This finite soak does not prove indefinite process-memory stability: event CSV rows and exact loss records scale with events, and a live integration would need bounded/rotated external audit logging. Queue capacity is a resource bound, not a deadline bound.

## Overflow, recovery, and session results

The policy table [overflow_recovery_results.csv](../runs/stage11_2_19_bounded_audio_pipeline/run_20261114_r10/overflow_recovery_results.csv) records all four probes as PASS. The unpausable case terminated its session and recorded 529 lost input samples in exact ranges `[0,256)`, `[256,512)`, `[512,529)`; output was not represented as uninterrupted. A new session beginning at sample 529 processed successfully. Reset with queued data and consumer-exception recovery are separately covered in the unit suite. Session results are in [session_isolation_results.csv](../runs/stage11_2_19_bounded_audio_pipeline/run_20261114_r10/session_isolation_results.csv) and [actual_gtcrn_session_reset.json](../runs/stage11_2_19_bounded_audio_pipeline/run_20261114_r10/actual_gtcrn_session_reset.json).

## Failures and reruns

The final successful evidence is run `r10`. Earlier nonzero attempts were:

| Attempt | Exit | Failure and correction |
|---|---:|---|
| Initial unittest invocation | 127 | Wrong virtual-environment relative path; corrected path then passed. |
| Runner retries before `r10` | 1 each | Missing optional `psutil` (used standard-library RSS instead); GTCRN adapter import path; sandbox denied `ps`; synthetic session fixture used different waveform phases; simulated clock moved backwards; playback reservation was initially too small; resulting sample-accounting failure; and hash ledger rejected an output path outside the repository. Each issue was corrected before the final run. |

These failures were not hidden or counted as passing evidence. After fixes, all 20 unit tests and complete run `r10` passed with exit code 0.

One preliminary attempt (`r8`) used a relative output path that resolved one directory above the repository. It wrote partial evidence to the parent workspace; it was not used for results and was left untouched. The completed evidence is under the repository's `runs/stage11_2_19_bounded_audio_pipeline/run_20261114_r10/` directory.

## Reproduction commands

From `experiments/stage11_2_19_bounded_audio_pipeline/`:

```sh
../../../pc_venv/bin/python -m unittest -q test_bounded_pipeline.py
../../../pc_venv/bin/python run_stage11_2_19.py \
  --output-dir ../../runs/stage11_2_19_bounded_audio_pipeline/run_20261114_r10 \
  --duration-s 20
```

The runner refuses to overwrite an existing run directory. Environment versions, seed, exact command, Git snapshot, protected hashes, adapter strict-load result, and scope limitations are recorded in `run_metadata.json`. Source and evidence-file hashes are recorded in `SHA256SUMS.txt`.

## Artifacts

- Pipeline, synthetic producer, tests, and runner: `experiments/stage11_2_19_bounded_audio_pipeline/`
- Final run evidence: `runs/stage11_2_19_bounded_audio_pipeline/run_20261114_r10/`
- Exact queue event telemetry: `queue_telemetry.csv`
- Memory checkpoints: `memory_telemetry.csv`
- Sample accounting: `pipeline_summary.json`
- Overflow/recovery and session isolation: the two CSVs above
- Reproducibility metadata and hashes: `run_metadata.json`, `SHA256SUMS.txt`

## Deployment readiness

**Not deployment-ready.** The result is limited to a host-side software pipeline with synthetic, flow-controlled producer input and a simulated playback sink. Physical capture devices may not honor backpressure; no ALSA, Pi 5, live headset, or end-to-end deadline was tested. The next stage should remain software-only unless separately authorized, and should define a bounded/rotated telemetry sink and device-specific overflow behavior before hardware qualification.
