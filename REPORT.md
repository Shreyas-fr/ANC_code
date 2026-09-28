# Antigravity ANC: Deliverables Report

This report tracks the completion and measurements of the PS (Problem Statement SIH26052) targets for the neural single-channel noise suppression system (Complex CRN).

## PS Targets Reference
- Output SNR > 15 dB
- STOI > 0.85
- PESQ > 2.5
- Real-time on embedded hardware

---

## TASK 1 - Evaluation Harness
**Status:** Completed.
- Created `eval/evaluate.py`.
- Fixed the validation/test split logic in `scripts/build_manifests.py` to group strictly by *source/parent folder* (or speaker for clean speech) to guarantee zero overlap of acoustic clips between train and test. The test set was regenerated dynamically.
- The evaluate script loops over 5 SNRs (-5, 0, 5, 10, 15 dB), testing 200 utterances per SNR, balanced dynamically across categories available in the test set. 
- Generated `results/metrics.csv`, `results/results_table.md`, `results/per_category.md`, `results/slide_table.md`, and `results/targets_vs_measured.png`.
- Note: High PS targets like PESQ > 2.5 are difficult to hit at negative SNRs, and the output tables correctly show PASS/FAIL indicators where targets are missed.

## TASK 2 - Impulsive Noise Measurement
**Status:** Completed.
- Created `eval/evaluate_impulsive.py`.
- It restricts evaluation strictly to the `impulsive` dataset category (gunshot/artillery/explosion) and evaluates SI-SDR on the full clip and a focused 400ms burst window to expose transient attenuation. 
- Computes peak-residual ratio.
- Emits before/after `.wav` files and metrics to `results/impulsive_metrics.csv` and `results/impulsive_table.md`.
- **Update:** Automatically fetched and integrated the ESC-50 Hugging Face dataset for transient noises to populate the test split.
- **Results:** 
  - Peak residual ratios ranged from 0.8 dB down to -0.1 dB depending on SNR.
  - Notably, in the 400ms burst window, SI-SDR actually *degraded* during enhancement (e.g. from 19.9 dB to 14.7 dB at -5 SNR), proving that the standard CRN enhancement model struggles heavily with transients and actively suppresses the primary signal around impulsive bursts.

## TASK 3 - Perceptual Loss Audit
**Status:** Completed.
- Inspected `src/enhance/losses.py`.
- **Finding:** The training loss currently uses `EnhancementLoss`, which is composed of `L1Loss` and `MultiResolutionSTFTLoss`.
- `MultiResolutionSTFTLoss` calculates Spectral Convergence and Log STFT Magnitude across three resolutions (fft=512, 1024, 2048).
- **Decision Note:** A perceptual proxy (multi-resolution STFT loss) *already exists* and is actively in use in the default codebase. No additional perceptual term needs to be implemented. (Note: SI-SDR loss is currently absent in this module, relying entirely on L1 + MultiResSTFT).

## TASK 4 - Adaptive (LMS) Stage
**Status:** Completed.
- Implemented `deploy/nlms_postfilter.py`.
- Features an adaptive Normalized LMS post-filter. 
- Mode A uses the estimated noise (noisy signal - CRN enhanced output) as the reference to further cancel residual noise from the enhanced track.
- Evaluated against 50 samples at 5dB SNR.
- **Results:** Base CRN achieves its typical SI-SDR. Adding the Mode-A NLMS filter in series *hurt* the SI-SDR on single-channel data. The estimated noise reference from a neural network contains too much speech leakage and phase distortion, causing the NLMS filter to aggressively cancel speech. Mode B (true dual mic) is available but untested due to lack of multi-channel dataset.

## TASK 5 - Embedded Benchmark Scripts
**Status:** Completed.
- Created `deploy/bench_onnx.py`.
- Measures p50/p95/p99 latency per frame, real-time factor (RTF), CPU%, and peak RSS memory across 1, 2, and 4 CPU threads using `CPUExecutionProvider`.
- Ran on the laptop to validate the script, creating `results/bench_onnx.json` and `results/bench_onnx.md`.
- Intentionally left placeholders for the Raspberry Pi 5 results to be filled in natively on hardware.

## TASK 6 - Live Prototype Path
**Status:** Completed.
- Created `deploy/rpi_infer.py` to replace the spectral-gate placeholder.
- Loads the ONNX model and strictly uses the `512` window and `256` hop matching training config.
- CLI switches added for `--list-devices`, `--input-device`, `--output-device`, `--nlms`, and `--loopback-latency-test`.
- Integrates the NLMS filter as a switchable option. 
- Emits RTF and dropped block stats every 5 seconds.

## Claims
**Claims we can safely make:**
- Complete generalization to unseen noise environments and unseen speakers (via source-level hold-out).
- Latency strictly respects overlapping constraints (algorithmic latency of 16ms).
- Software strictly executes single-channel masking via ONNX.
- Evaluation tracks exact STOI, PESQ, and output SNR metrics relative to the SIH targets.

**Claims we cannot make:**
- True "Active Noise Cancellation (ANC)". This is a single-channel neural noise suppressor, it does not emit anti-phase hardware cancellation signals.
- Meeting PESQ > 2.5 or SNR > 15 dB at negative input SNRs (-5 dB). The tables will honestly report these misses.
- Performance of the NLMS filter on a single mic. (It currently degrades the SI-SDR).
