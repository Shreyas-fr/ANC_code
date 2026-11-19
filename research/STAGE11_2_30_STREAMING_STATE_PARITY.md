# Stage 11.2.30 — Stateful Tract frame parity trace

**Date:** 2026-11-14  
**Status:** PARTIAL — identified a recurrent startup-history mismatch on the traced clip; startup correction and end-to-end waveform impact remain unverified. Not fixed or promoted.  
**Scope:** Fixed canonical development clip 93, 300 frames at 48 kHz, one fresh `DfTract` instance. No gold, Pi, live audio, upload, training, package installation, checkpoint change, or deployment change.

## Finding

Stage 11.2.29 showed that sequence-level PyTorch and exported ONNX encoder/decoder graphs agree closely. This stage fed the same 48 kHz mono clip through the isolated native `DfTract` frame-by-frame path and recorded its per-call encoder tensors.

The libDF input features agree bit-for-bit with Stage 11.2.28's Python 0.5.6 feature arrays: all 300 ERB feature frames (300×32) and complex feature frames (300×96×2) are exactly equal. This rules out feature-array values as the cause in this clip.

Using the configured two-frame lookahead mapping (`native frame i` against Python `frame i−2`) and excluding the first 50 native calls as startup, the native and Python convolutional encoder maps `e0`–`e3` and `c0` match to near machine precision (largest RMSE **1.59e-7**, largest absolute difference **6.88e-12**). The encoder's post-GRU embedding does not: RMSE **0.0280**, maximum absolute difference **0.358**, correlation **0.9855**. Its `lsnr` head output differs by RMSE **3.219 dB**, mean native-minus-Python **−2.679 dB**, maximum absolute difference **11.510 dB** (correlation **0.9899**).

Applying the protected Python `lsnr_fc` weights to the native embedding reproduces the native `lsnr` trace within **1.15e-5** maximum absolute error. A follow-up isolated the apparent recurrent mismatch. Full-sequence PyTorch GRU versus explicit one-frame PyTorch GRU with carried hidden state matches at RMSE **6.01e-8**; resetting hidden state each frame differs (RMSE **0.15785**). Reconstructed native GRU inputs match Python GRU inputs with the two-frame lookahead mapping after startup (RMSE **1.65e-7**, max absolute **6.88e-12**). Most importantly, running the protected PyTorch GRU with persistent hidden state on the exact reconstructed native inputs reproduces the native embeddings (RMSE **9.41e-8**, max absolute **1.72e-12**).

These controls falsify a different GRU implementation/weights and a per-frame hidden-state reset as causes for this clip. The earlier `0.0280` embedding delta compared recurrent outputs at a two-frame-shifted index without matching the recurrent history at sequence start. The remaining parity question is the stream-boundary contract: pairing the two lookahead frames, initial state, emitted frame IDs, and final flush consistently. This does not yet explain the end-to-end waveform metric difference; that causal link remains unmeasured. Stage 11.2.29's sequence-graph parity remains true.

The native GRU input trace confirms a startup mismatch: native frames 0–3 do not match the corresponding Python frames, while native frame 4 onward matches Python frame `t−2` to ~3e-7 RMSE. The first four native GRU inputs are nevertheless consumed by the stateful recurrent path. A sequence reference made from Python GRU inputs 0–1 followed by the native inputs from frame 4 onward matches the Python full-sequence output to **7.93e-8 RMSE**. The current native embedding sequence compared with that aligned reference (native frames 4–297 vs Python frames 2–295) differs by **0.0377 RMSE**, despite native matching PyTorch when both consume the same native sequence. This is direct evidence that the startup prehistory changes the recurrent trajectory on this clip. The precise mechanism producing the first four nonmatching inputs and the right streaming startup policy remain to be established; the test does not prove end-to-end waveform causality.

For reference, the naive shifted-output embedding RMSE remains nonzero through the clip: **0.0663** (frames 2–9), **0.0674** (10–24), **0.0744** (25–49), **0.0217** (50–99), **0.0213** (100–199), and **0.0358** (200–297). Do not use that naive shifted comparison alone as a GRU implementation verdict.

The earlier local-SNR difference (RMSE **3.219 dB**) was also computed under the unpaired shifted recurrent history and is not evidence of a proven local-SNR defect. Do not promote the current native binary. The full-set approximately 0.10 dB residual and fixed-clip waveform difference are not causally explained by this trace.

## Method and files

- Native source is an isolated copy of the previously inspected DeepFilterNet 0.5.6 source used for Stage 11.2.28; only the copy under `runs/stage11_2_30_stream_state_trace_20261114/source/` was instrumented. The deployed binary and its source were not edited. For clip 93 this source version does not hit the documented low-power skip path.
- The existing protected Tract archive was loaded directly. Input was the existing fixed 48 kHz float WAV `runs/stage11_2_28_frontend_parity_20261114/inputs_shared/0093.wav`; the full 300×480 samples were processed one hop at a time.
- Stage 11.2.29 strictly loaded the protected Python checkpoint and saved its encoder tensors. Native per-frame `e0`–`e3`, `emb`, `c0`, `lsnr`, mask, and DF coefficients were dumped in an isolated trace directory.
- A time-axis layout error in the first analysis of channel-feature tensors was found and corrected: PyTorch feature maps are `[B,C,T,F]` while per-frame native buffers are appended in frame order. Results in this report use the corrected transpose and frame mapping. The initial unaligned whole-array measurements are not used as findings.
- A second fixed trace for clip 287 produced 267 model calls because its input includes low-power frames skipped by the 0.5.6 runtime. It is retained as evidence but excluded from this recurrent-state comparison because native call indices no longer equal source frame indices without an explicit skip map.

## Commands

```sh
CARGO_HOME=/private/tmp/stage26-cargo-home cargo build --offline --release \
  -p deep_filter --bin dump_model_trace --no-default-features \
  --features 'bin,tract,wav-utils,transforms' \
  --manifest-path runs/stage11_2_30_stream_state_trace_20261114/source/DeepFilterNet/Cargo.toml \
  --target-dir runs/stage11_2_30_stream_state_trace_20261114/target

DFN_STAGE30_TRACE_DIR="$PWD/runs/stage11_2_30_stream_state_trace_20261114/native_trace_0093_v3" \
  runs/stage11_2_30_stream_state_trace_20261114/target/release/dump_model_trace \
  ../models/dfn3_step500_tract.tar.gz \
  runs/stage11_2_28_frontend_parity_20261114/inputs_shared/0093.wav

../pc_venv/bin/python experiments/stage11_2_29_network_parity/trace_pytorch.py
../pc_venv/bin/python experiments/stage11_2_30_stream_state_trace/compare_encoder_states.py
../pc_venv/bin/python experiments/stage11_2_30_stream_state_trace/summarize_stream_trace.py
../pc_venv/bin/python experiments/stage11_2_30_stream_state_trace/explicit_pytorch_gru_state.py
```

Build history: two initial offline compile attempts exited `101` (ambiguous ndarray dimension type, then temporary WAV array lifetime); both were corrected in the isolated diagnostic source and the final offline release build succeeded. The first Python trace attempt exited `1` because `df.__init__` imported unavailable `torchaudio.backend`; the trace was corrected to load the model submodules without executing audio-helper package initialization. No installs were performed.

## Evidence

- Instrumented source and binary: `runs/stage11_2_30_stream_state_trace_20261114/source/`, `target/release/dump_model_trace`.
- Native 93 trace: `runs/stage11_2_30_stream_state_trace_20261114/native_trace_0093_v3/`.
- Native 287 trace (quiet frames skipped): `runs/stage11_2_30_stream_state_trace_20261114/native_trace_0287/`.
- Corrected per-output and shift diagnostics: `runs/stage11_2_30_stream_state_trace_20261114/encoder_state_comparison.json`.
- Fixed-map post-warmup metrics and protected hashes: `runs/stage11_2_30_stream_state_trace_20261114/streaming_state_summary.json`.
- Python outputs: `runs/stage11_2_29_network_parity_20261114/pytorch/`.
- Native/Python feature identity source: `runs/stage11_2_28_frontend_parity_20261114/python_features_py310/`.
- Recurrent isolation script and output: `experiments/stage11_2_30_stream_state_trace/explicit_pytorch_gru_state.py`, `runs/stage11_2_30_stream_state_trace_20261114/explicit_pytorch_gru_state_summary.json`; it also saves PyTorch replay embeddings, the reconstructed native GRU inputs, the Python GRU inputs, and an aligned startup reference beside the summary.

## Next action

In an isolated source copy, instrument the four startup GRU inputs and pulse/conv delay buffers to identify why they do not correspond to Python frames 0–1. Then test a candidate startup policy that produces the correct recurrent history while preserving the subsequent timestamp mapping and final flush. Compare internal tensors first, then end-to-end waveform on fixed non-gold clips. Keep the deployed binary and Step-500 protected.
