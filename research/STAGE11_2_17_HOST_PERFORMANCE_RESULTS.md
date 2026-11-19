# Stage 11.2.17 — Host Performance Results

## Conditions

Host: macOS 26.6.2, arm64 Apple CPU; Python 3.14.7, PyTorch 2.14.1, NumPy 1.26.4, SoundFile 0.14.0; one PyTorch CPU thread. The streaming runner profiled 1,956 chunks across the six synthetic signals and five modes. No Pi, ALSA, audio interface or concurrent real-time workload was involved.

## Aggregate chunk profile

Across the 1,956 profiled chunks, mean execution was `3.887 ms`, p95 `7.986 ms`, p99 `22.589 ms`; 7 chunks exceeded their individual input-duration deadlines. Mean Python allocation delta was about `1,452 bytes/chunk`. Process peak RSS was `237,256,704 bytes` (~226 MiB), including Python/PyTorch/model and process baseline. Model loading took `32.5 ms` and is reported separately. Twenty seconds of continuous silence took `3.162 s` wall time (host-only; not a real-time guarantee).

For fixed 10, 16, 20 and 32 ms chunk schedules, every synthetic signal/mode row had zero deadline misses in the run. Irregular chunking had seven deadline misses across 243 chunks, concentrated in larger/longer-than-nominal chunks. Across all fixed-chunk rows, the highest p99 was 8.595 ms. A single host run under this limited synthetic workload does not establish scheduler tail behavior.

## Memory and buffering observations

The output queue is empty after each adapter call because finalized samples are returned synchronously. ISTFT overlap ring maximum was 512 samples in profile summaries. The final adapter ingests incoming chunks internally in 64-sample slices. The measured ring maximum was 576 samples (512-sample STFT frame context plus a 64-sample push), including the irregular schedule whose caller chunks were as large as 2,053 samples. This bounds adapter-owned input buffering; the prototype still has no external capture-queue cap or backpressure policy, and a large synchronous caller chunk can miss its deadline. The 20-second soak retained only 257 input and 256 overlap samples at the endpoint. It processed 1,250 frames.

`tracemalloc` records Python allocations, not all native PyTorch/NumPy allocations. Peak RSS is the better whole-process footprint observation, but includes libraries and model weights. The final run metadata pools the profile-row maxima and reports the 576-sample input-ring limit; `host_profile.csv` gives per-schedule detail.

## Deadline interpretation

The mean of the six signal-level 10 ms mode means was 2.108 ms per call, with the worst signal-level p99 at 4.213 ms; there were no deadline misses in this test matrix. Irregular chunks missed 7 of 243; overall pooled misses were 7/1,956. Deadline comparisons only compare Python call elapsed time against chunk audio duration. They exclude ALSA capture/playback buffering, codecs, scheduling contention, device I/O and end-to-end electrical latency. Therefore they do not establish real-time operation, a Pi 5 RTF, or the project 35 ms system target.

Raw evidence: `runs/stage11_2_17_gtcrn_streaming/run_20261114_r9/host_profile.csv`, `per_chunk_profile.csv`, and `run_metadata.json`.

## R11 re-profile after caller-chunk cap

With the adapter rejecting calls above 4,096 samples, the R12 run also checked the accepted boundary at exactly 4,096 samples. Its fresh 1,956-chunk profile measured mean `3.469 ms`, p95 `6.294 ms`, p99 `22.595 ms`, and 6 deadline misses. Mean Python allocation delta was `1,453 bytes/chunk`; peak RSS was `231,178,240 bytes` (~220.5 MiB). Max input ring remained 576 samples and max ISTFT overlap ring 512. The 20-second synthetic soak completed in `2.719 s`, processing 1,250 frames, without state growth proportional to duration. These numbers are a single host run and still exclude external capture queues, hardware I/O and scheduling contention. R12 raw evidence is in `runs/stage11_2_17_gtcrn_streaming/run_20261114_r12_chunkcap_boundary/`.
