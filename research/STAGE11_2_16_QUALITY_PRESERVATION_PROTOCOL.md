# Stage 11.2.16 — Quality Preservation Protocol

## Frozen reference

The reference remains the existing raw float waveform sum: `0.15 * DFN3 Step-500 + 0.70 * FullSubNet epoch 58 + 0.15 * GTCRN DNS3`. Reference per-clip outputs and summary are immutable. The recorded 590-clip means are SNR 15.04124 dB, SI-SDR 13.96529 dB, STOI 0.906858, PESQ-WB 2.585263, with 227/590 (38.5%) joint passes. These are development results on a reused benchmark, not independent validation or a Pi result.

Reference artifact: `runs/stage8_ensemble_20261113/phase_c_ensembles/d2_fs70_raw/summary.json` and its `per_clip.csv` / float predictions. Maintain the canonical manifest SHA-256 `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`.

## Future candidate comparison (requires separate approval)

1. Freeze the candidate source, code, checkpoint and configuration hashes before evaluation. Use identical noisy inputs, canonical IDs and clean targets as the reference. Gold remains inaccessible.
2. Evaluate each component stream and any mixture using the unchanged canonical metric implementation: output SNR, SI-SDR, STOI, PESQ-WB, plus individual pass counts and joint count/rate at `SNR > 15 dB`, `STOI > 0.85`, `PESQ-WB > 2.5`.
3. Report per-clip paired differences and paired bootstrap confidence intervals. Report all 7 measured-input-SNR bins and the predeclared low-SNR subgroup (`target SNR <= 0 dB`, n=210) separately. Do not use the repeated canonical set as confirmatory evidence.
4. Preserve float outputs through scoring. Do not silently clip, peak-normalize, time-shift, or polarity-correct model outputs. If a single fixed delay is required by a streaming design, define it from architecture and timestamps before scoring, apply it uniformly, and report both raw and fixed-delay results. Keep canonical IDs 162 and 436 visible because Phase B marked their direct Step-500/FullSubNet waveform relation ambiguous.
5. Add chunk-boundary analysis: frame/hop-aligned and deliberately offset chunks, startup, silence-to-speech onset, speech offset, long silence, state reset, and consecutive sessions. Compare streamed output against the frozen offline per-clip output, with per-sample error, delay, discontinuities, and missing/duplicated sample counts. This is a development equivalence probe, not a new metric target.
6. The current canonical manifest does not provide event-level transient labels. For transient/impulsive noise, report source/origin strata where available, inspect clipping and onset/offset behavior, and obtain an independently labeled event set before making event-specific claims.
7. If suitable listeners and approved non-gold recordings are available, run a blinded, randomized listening comparison for intelligibility, naturalness, speech deletion, residual noise and transient artifacts. Do not recruit or collect recordings in this stage. Use consented authorized listeners, repeated controls, and predeclared rating questions in a later approved study.

The acceptance decision must separate: (a) canonical development regression, (b) independent validation, and (c) physical latency/real-time qualification. Passing one does not imply the others.
