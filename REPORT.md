# Antigravity ANC: Deliverables Report

> **Historical prototype report.** This file describes an earlier Polar-D prototype and does not represent current SIH compliance. The current, evidence-backed project status is in [MASTER_SIH_COMPLIANCE.md](MASTER_SIH_COMPLIANCE.md). In particular, the 16 ms and ONNX statements below are not claims about the deployed DeepFilterNet3 Step-500 chain.

This report preserves implementation notes from the earlier single-channel noise-suppression prototype (Stateful Polar-D).

## PS Targets Reference
- Output SNR > 15 dB
- STOI > 0.85
- PESQ > 2.5
- Real-time on embedded hardware

---

## Historical Architecture: Polar-D (Stateful Polar LSTM)

The earlier prototype replaced the legacy Complex CRN with **Polar-D**, a stateful recurrent model that parameterizes a polar complex mask for single-channel causal execution on embedded hardware.

*See the dedicated [System Diagrams](system_diagrams.md) document for complete visual flowcharts covering the neural architecture, data training pipeline, and embedded user flows.*

---


## TASK 1 - Evaluation Harness
**Historical status:** Evaluation scripts were created; their measurements do not establish current SIH compliance.
- Created `eval/evaluate.py`.
- Fixed the validation/test split logic in `scripts/build_manifests.py` to group strictly by *source/parent folder* (or speaker for clean speech) to guarantee zero overlap of acoustic clips between train and test. The test set was regenerated dynamically.
- The evaluate script loops over 5 SNRs (-5, 0, 5, 10, 15 dB), testing 200 utterances per SNR, balanced dynamically across categories available in the test set. 
- Generated `results/metrics.csv`, `results/results_table.md`, `results/per_category.md`, `results/slide_table.md`, and `results/targets_vs_measured.png`.
- Note: High PS targets like PESQ > 2.5 are difficult to hit at negative SNRs, and the output tables correctly show PASS/FAIL indicators where targets are missed.

## TASK 2 - Impulsive Noise Measurement
**Historical status:** Impulsive-noise analysis was performed on the earlier model; do not treat it as current DeepFilterNet3 evidence.
- Created `eval/evaluate_impulsive.py`.
- It restricts evaluation strictly to the `impulsive` dataset category (gunshot/artillery/explosion) and evaluates SI-SDR on the full clip and a focused 400ms burst window to expose transient attenuation. 
- Computes peak-residual ratio.
- Emits before/after `.wav` files and metrics to `results/impulsive_metrics.csv` and `results/impulsive_table.md`.
- **Update:** Integrated impulsive noises from public research datasets (ESC-50).
- **Results:** 
  - Peak residual ratios ranged from 0.8 dB down to -0.1 dB depending on SNR.
  - Notably, in the 400ms burst window, SI-SDR actually *degraded* during enhancement (e.g. from 19.9 dB to 14.7 dB at -5 SNR), proving that the standard CRN enhancement model struggles heavily with transients and actively suppresses the primary signal around impulsive bursts.

## TASK 3 - Perceptual Loss Audit
**Historical status:** Loss audit applies to the earlier prototype, not the current Step-500 checkpoint.
- Inspected `src/enhance/losses.py`.
- **Finding:** The training loss currently uses `EnhancementLoss`, which is composed of `L1Loss` and `MultiResolutionSTFTLoss`.
- `MultiResolutionSTFTLoss` calculates Spectral Convergence and Log STFT Magnitude across three resolutions (fft=512, 1024, 2048).
- **Decision Note:** A perceptual proxy (multi-resolution STFT loss) *already exists* and is actively in use in the default codebase. No additional perceptual term needs to be implemented. (Note: SI-SDR loss is currently absent in this module, relying entirely on L1 + MultiResSTFT).

## TASK 4 - Adaptive (LMS) Stage
**Historical status:** The single-channel NLMS experiment degraded SI-SDR; true dual-microphone performance remains unverified.
- Implemented `deploy/nlms_postfilter.py`.
- Features an adaptive Normalized LMS post-filter. 
- Mode A uses the estimated noise (noisy signal - CRN enhanced output) as the reference to further cancel residual noise from the enhanced track.
- Evaluated against 50 samples at 5dB SNR.
- **Results:** Base CRN achieves its typical SI-SDR. Adding the Mode-A NLMS filter in series *hurt* the SI-SDR on single-channel data. The estimated noise reference from a neural network contains too much speech leakage and phase distortion, causing the NLMS filter to aggressively cancel speech. Mode B (true dual mic) is available but untested due to lack of multi-channel dataset.

## TASK 5 - Embedded Benchmark Scripts
**Historical status:** Benchmark tooling was created; its laptop results do not establish current Pi performance.
- Created `deploy/bench_onnx.py`.
- Measures p50/p95/p99 latency per frame, real-time factor (RTF), CPU%, and peak RSS memory across 1, 2, and 4 CPU threads using `CPUExecutionProvider`.
- Ran on the laptop to validate the script, creating `results/bench_onnx.json` and `results/bench_onnx.md`.
- Intentionally left placeholders for the Raspberry Pi 5 results to be filled in natively on hardware.

## TASK 6 - Live Prototype Path
**Historical status:** The Polar-D ONNX prototype is not the current deployed DeepFilterNet3 path.
- Created `deploy/rpi_infer.py` to replace the spectral-gate placeholder.
- Loads the ONNX model and strictly uses the `512` window and `256` hop matching training config.
- CLI switches added for `--list-devices`, `--input-device`, `--output-device`, `--nlms`, and `--loopback-latency-test`.
- Integrates the NLMS filter as a switchable option. 
- Emits RTF and dropped block stats every 5 seconds.

## Current Evidence Summary

See [MASTER_SIH_COMPLIANCE.md](MASTER_SIH_COMPLIANCE.md) for protocols, per-clip outputs, paired confidence intervals, Pi telemetry, and outstanding gates. Current measurements on the frozen 590-clip benchmark show Step-500 means of **13.47 dB SNR, 0.885 STOI, and 2.232 PESQ-WB**: the STOI mean passes, while the full-set SNR and PESQ means do not. A lower-latency 250 ms block candidate was measured on the Pi at 640 ms configured delay, with 2 late fallbacks in 18,779 frames; zero-miss real-time compliance is not established.

This remains a single-channel speech-enhancement system, not active anti-phase noise cancellation. The complete project does not yet verify universal quality-target compliance, true dual-microphone ANC, processed headset playback, or microphone-to-headphone latency.
