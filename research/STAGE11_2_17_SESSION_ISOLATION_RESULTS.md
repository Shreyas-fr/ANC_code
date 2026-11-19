# Stage 11.2.17 — Session Isolation Results

## Method

The same loaded GTCRN model was used in three paths: Session A followed by explicit `reset_session()`, then Session B; Session B was also processed by a fresh adapter. A separate reused adapter was given a NaN-containing chunk, then a valid Session B. The runner compared both Session B waveforms using the frozen `atol=1e-5`, `rtol=1e-5` threshold. No project audio was used.

## Results

- Session A: 9,600 samples (0.6 s) of synthetic white noise; finalized and closed.
- Reset call: 6.25 microseconds on the host (observed); adapter initialization: 0.905 milliseconds (observed; does not include loading checkpoint/model).
- Session B: 12,800 samples (0.8 s) of synthetic speech-like signal.
- B after reset vs fresh adapter: same 12,800 output samples, zero-lag correlation `1.0`, lag search ±32 samples returned 0, RMSE `0`, max error `0`, `allclose=True`.
- Invalid 2-D chunk and invalid NaN chunk: each rejected with `ValueError` before state mutation; the state summary was unchanged after each. Subsequent valid Session B exactly matched a fresh adapter (RMSE `0`, max error `0`, `allclose=True`).
- Long soak: 20 seconds / 320,000 samples / 1,250 frames; completed without state growth proportional to session duration. At end, input ring held 257 samples and ISTFT overlap ring 256 samples. The final adapter ingests in 64-sample internal slices; maximum measured input ring was 576 samples, and the run asserts the limit `FFT + internal_push = 576`. Session remained open until normal caller finalization.

Raw evidence: `runs/stage11_2_17_gtcrn_streaming/run_20261114_r9/session_isolation.json` and `run_metadata.json`. These are host software results, not a reset-latency claim for other hardware.

## R11 oversized-input recovery follow-up

The adapter now caps a single caller chunk at 4,096 samples. R12 accepted exactly 4,096 samples and matched full-call inference (`RMSE 2.52e-8`, max error `3.28e-7`, within the frozen tolerance); it rejected 4,097 samples with `ValueError` and left the full session summary unchanged. A subsequent valid Session B matched a fresh adapter (`allclose=True`, zero RMSE/max error). Malformed shape and NaN rejections were also rechecked. Evidence: `runs/stage11_2_17_gtcrn_streaming/run_20261114_r12_chunkcap_boundary/session_isolation.json`.
