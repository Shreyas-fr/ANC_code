# Stage 11.2.25 — Native Resampler Root Cause and Parity Recovery

**Status: ROOT CAUSE IDENTIFIED; parity substantially recovered in a controlled offline path; native deployment fix not yet integrated or qualified.**

## Objective and safeguards

This stage investigated the Stage 11.2.23 gap between the protected DFN3 Step-500 Python and Rust/Tract paths. The checkpoint, Tract archive, canonical manifest, evaluator and saved predictions were preserved. No training, tuning, promotion, gold access, Kaggle access, Pi access, participant activity or upload occurred. The frozen 590-clip set remains development data. New results are diagnostics, not independent confirmation.

Protected hashes before and after the full-set experiment:

| Artifact | SHA-256 | Result |
|---|---|---|
| Canonical manifest | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` | unchanged |
| DFN3 Step-500 checkpoint | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` | unchanged |
| Step-500 Tract archive | `99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d` | unchanged |

## Root-cause investigation

The Python canonical evaluator upsamples each 16 kHz input with `scipy.signal.resample_poly(x, 3, 1)` and downsamples the enhanced 48 kHz signal with `resample_poly(y, 1, 3)`. The packaged native CLI instead uses libDF's `transforms::resample`, which uses Rubato `FftFixedInOut<f32>` with a 2,048-sample chunk. The evaluator and runtime otherwise use matching 48 kHz model geometry, no attenuation limit, post-filter disabled, and independent utterance state. Python calls `df_state.reset()` and the model resets its GRU state; the native CLI calls `DfTract::reset()` between files. The Tract archive was exported with strict loading of the exact Step-500 checkpoint.

Delay compensation was checked separately. The native CLI's `--compensate-delay` removes 1,440 samples at 48 kHz (30 ms: 10 ms STFT plus 20 ms model lookahead). In the 590-clip output comparison, the uncompensated 16 kHz waveform after dropping its first 480 samples matched the compensated output with mean RMSE `7.90e-6`, median RMSE `2.85e-6`, mean correlation `0.999999926`, and minimum per-clip correlation `0.999995581`. This confirms the crop is functioning as intended. Scoring the uncompensated waveform against time-zero clean references is misaligned and is not a valid quality comparison.

## Targeted 2×2 resampler isolation

Nine clips were predeclared: one manifest clip from each of the seven target-SNR bins (`0, 1, 2, 4, 6, 7, 33`) plus the two previously flagged alignment IDs (`162, 436`). The same frozen native model processed 48 kHz inputs in all four conditions. The input and output resamplers were varied independently. Each output was compared with the clean reference on the common first 47,520 samples using the unchanged `scripts/evaluate_dfn3_canonical.py::metrics` function.

| Input upsampler | Output downsampler | Mean SNR | Mean SI-SDR | Mean STOI | Mean PESQ-WB |
|---|---|---:|---:|---:|---:|
| SciPy polyphase | SciPy polyphase | 8.7151 | 3.5280 | 0.797470 | 1.76514 |
| SciPy polyphase | Rubato FFT | 8.7130 | 3.5309 | 0.797469 | 1.76415 |
| Rubato FFT | SciPy polyphase | 7.4254 | 1.5720 | 0.796953 | 1.68110 |
| Rubato FFT | Rubato FFT | 7.4213 | 1.5686 | 0.796953 | 1.67808 |

At fixed output resampler, changing **input upsampling** from Rubato to SciPy improved SNR by `1.290–1.292 dB` and SI-SDR by `1.956–1.962 dB`. At fixed input resampler, changing **output downsampling** moved means by at most `0.0041 dB` SNR, `0.0034 dB` SI-SDR, `0.000001` STOI and `0.0031` PESQ. Thus the input-side Rubato resampler is the dominant cause in this controlled diagnostic; output downsampling is negligible at this sample size.

The standalone Rubato helper was matched against the original CLI pathway on these clips: helper `Rubato-up/Rubato-down` means differ from Stage 11.2.23 by under `0.0002 dB` SNR, `0.0001 dB` SI-SDR, `0.00005` STOI and `0.00004` PESQ. Its implementation follows libDF's chunk size, zero padding, extra flush chunk and centered crop. It was built offline with cached Rubato `0.14.1`; no network or package installation was used. The first Cargo attempt tried writing into the global cache and was denied by the filesystem sandbox; the successful build redirected Cargo's writable home to `/private/tmp/stage25-cargo-home`.

## Full 590-clip controlled resampling comparison

For a full-set confirmation, canonical 16 kHz noisy inputs were converted to 48 kHz float WAVs with SciPy polyphase, processed by the unchanged native Tract executable with the protected archive, default per-file state reset and delay compensation, then downsampled to 16 kHz with SciPy polyphase. The native CLI writes PCM16 WAV at its output sample rate before the SciPy downsample. Python reference audio was cropped to the same 47,520 samples and rescored with the unchanged canonical metric function. The full-set paired CIs use 2,000 clip bootstrap resamples, seed 26052; they do not account for speaker/noise-session clustering.

| Metric | Native Tract with SciPy resampling | Saved Python Step-500, same crop | Paired delta (95% CI) |
|---|---:|---:|---:|
| Output SNR | 13.3582 dB | 13.4640 dB | `-0.1057` [`-0.1681`, `-0.0390`] dB |
| SI-SDR | 12.3060 dB | 12.3518 dB | `-0.0458` [`-0.1226`, `+0.0319`] dB |
| STOI | 0.88478 | 0.88441 | `+0.00037` [`-0.00064`, `+0.00154`] |
| PESQ-WB | 2.23743 | 2.23891 | `-0.00148` [`-0.01070`, `+0.00902`] |
| Joint pass (>15 dB, >0.85, >2.5) | 158/590 (26.78%) | 161/590 (27.29%) | — |

The original Rubato-native Stage 11.2.23 common-crop result was 11.4753 dB SNR, 10.0651 dB SI-SDR, 0.87942 STOI, 2.18823 PESQ-WB and 111/590 joint passes. Replacing the resampling pair recovers most of the observed difference. The new end-to-end common-crop comparison is close, but not exact: the SNR paired CI remains below zero by about 0.04–0.17 dB. SI-SDR, STOI and PESQ-WB CIs include zero. This residual SNR difference is not yet attributed to PCM quantization, numerical differences in the ONNX/Tract graph, or another implementation detail; those remain hypotheses.

Native output results by target-SNR bin in the full SciPy-resampling diagnostic:

| Target SNR | n | Output SNR | SI-SDR | STOI | PESQ-WB | Joint passes |
|---:|---:|---:|---:|---:|---:|---:|
| -10 dB | 30 | 6.646 | 2.748 | 0.677 | 1.379 | 0/30 |
| -5 dB | 63 | 9.913 | 8.073 | 0.804 | 1.694 | 3/63 |
| 0 dB | 117 | 11.002 | 9.839 | 0.856 | 1.867 | 9/117 |
| 5 dB | 137 | 12.753 | 11.741 | 0.892 | 2.149 | 20/137 |
| 10 dB | 121 | 15.021 | 14.346 | 0.928 | 2.508 | 45/121 |
| 15 dB | 86 | 17.606 | 17.139 | 0.950 | 2.836 | 52/86 |
| 20 dB | 36 | 19.208 | 19.440 | 0.962 | 3.103 | 29/36 |

This full-set run is a controlled engineering diagnostic on a reused development benchmark, not independent validation. It does not establish real-time performance. The SciPy resampler was applied outside the native runtime; the protected `deep-filter` binary still uses Rubato. Therefore **do not describe the deployment binary as parity-corrected or promote it**.

## Reproduction commands

```text
../pc_venv/bin/python experiments/stage11_2_24_native_delay_diagnostic/run_native_no_delay.py
../pc_venv/bin/python experiments/stage11_2_24_native_delay_diagnostic/score_native_no_delay.py
../pc_venv/bin/python scripts/compare_dfn3_canonical.py --reference runs/stage11_2_24_native_delay_compensation_diagnostic_20261114/metrics/python_reference/per_clip.csv --candidate runs/stage11_2_24_native_delay_compensation_diagnostic_20261114/metrics/native/per_clip.csv --output runs/stage11_2_24_native_delay_compensation_diagnostic_20261114/metrics/paired_native_no_delay_vs_python.json --bootstrap 2000 --seed 26052
CARGO_HOME=/private/tmp/stage25-cargo-home cargo build --offline --release --manifest-path experiments/stage11_2_25_resampler_impact/rust_resampler/Cargo.toml --target-dir runs/stage11_2_25_resampler_isolation_20261114/rust_target
../pc_venv/bin/python experiments/stage11_2_25_resampler_impact/run_resampler_isolation.py
../pc_venv/bin/python experiments/stage11_2_25_resampler_impact/analyze_resampler_factorial.py
../pc_venv/bin/python experiments/stage11_2_25_resampler_impact/run_full_scipy_comparison.py
```

The Stage 11.2.24 no-delay output was a timing diagnostic only. As expected, the uncompensated waveform scores poorly when compared at time zero; after the 30 ms crop it matches the Stage 11.2.23 compensated waveform closely. Do not interpret the uncompensated score as a model-quality result.

## Evidence and verdict

- Nine-clip factorial and resampled outputs: `runs/stage11_2_25_resampler_isolation_20261114/factorial/` and `per_clip_diagnostic.csv`.
- Full-set 48 kHz inputs, native outputs, float outputs, paired metrics, logs and hashes: `runs/stage11_2_25_resampler_isolation_20261114/full_scipy_comparison/`.
- No-delay alignment diagnostic: `runs/stage11_2_24_native_delay_compensation_diagnostic_20261114/`.
- Machine-readable frozen-artifact and qualification inventory: `research/STAGE11_2_25_BASELINE_REGISTER.csv`.
- Baseline evaluator and comparison program: `scripts/evaluate_dfn3_canonical.py` and `scripts/compare_dfn3_canonical.py` (unchanged).

**Verdict:** The dominant Stage 11.2.23 quality loss is the native **input Rubato resampling path**, not a changed checkpoint or a global output delay. SciPy resampling around unchanged Tract inference nearly restores Python-level quality over all 590 development clips. A production-safe, stateful native polyphase replacement still needs implementation, integration, a fresh full parity run, and real Raspberry Pi 5 timing qualification. Preserve all current artifacts until that separate candidate passes review.

## Integrated native candidate follow-up — Stage 11.2.26

Stage 11.2.26 implemented an isolated Rust CLI candidate with the SciPy-compatible 61-tap polyphase resampler and evaluated it on all 590 development clips. The candidate reproduced the external SciPy-controlled Tract outputs with mean waveform RMSE `1.05e-5` and mean per-clip correlation `0.99999982`. Mean metrics were 13.359 dB SNR / 12.306 dB SI-SDR / 0.88475 STOI / 2.238 PESQ-WB, 159/590 joint passes. The remaining Python-versus-Tract SNR difference is -0.105 dB (95% clip-bootstrap CI [-0.168, -0.039]); simulated PCM16 quantization of Python outputs changes mean SNR by only -0.003 dB and cannot account for it. The original deployment binary remains unchanged; this candidate is not a stateful streaming resampler and was not tested on Pi. See `research/STAGE11_2_26_NATIVE_POLYPHASE_PARITY_CANDIDATE.md`.
