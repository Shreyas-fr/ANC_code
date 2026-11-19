# Stage 11.2.23 — Native Tract Step-500 Canonical Parity Check

**Status:** 590 native outputs generated; parity discrepancy found; deployment quality parity is not established.

## Scope

This is a frozen-benchmark deployment diagnostic. The native macOS ARM64 `deep-filter` binary enhanced each of the 590 canonical noisy inputs using the hash-verified Step-500 Tract archive. Results were compared with the saved Stage 8 Python Step-500 predictions for the same IDs. No model selection, tuning, retraining, or promotion occurred. No gold data, Kaggle, Raspberry Pi, or external data were accessed.

The native command used `--compensate-delay`; the CLI removes 1,440 samples at 48 kHz (30 ms) and resamples back to 16 kHz. Thus each native file has 47,520 samples, while each saved Python reference has 48,000. This report compares the first 47,520 samples of the Python reference against the complete native output. It does not overwrite or revise the original 3-second metric results.

## Integrity and execution

- Canonical manifest SHA-256: `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`.
- Protected Step-500 checkpoint SHA-256: `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27`.
- Tract archive SHA-256: `99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d`.
- Native runtime SHA-256: `0352b86f9e9f0ce7e82b4f8cb0c1c0dba7df75945782a666b46f5c3de2f57879` (macOS arm64 Mach-O).
- Source checkout: DeepFilterNet/libDF 0.5.7-pre, commit `d375b2d8309e0935d165700c91da9de862a99c31`; the relevant source tree had pre-existing local modifications. Toolchain: rustc `1.99.0` / cargo `1.99.0`. Current source/config hashes are `enhance_wav.rs` `7074ac8d4e12e8cca289820ed3fb708271da2ae2d86c6d4f5fb2e33ef8eff11d`, `tract.rs` `19ff15d90e489ba8e72edd56bf3c0606dfb49dcfa588576578547e834dcbb857`, root `Cargo.lock` `f40f8667c456f82151bdfe6a2e875a7ae21661b5055affb0aeddacd318e10fa4`, and root `Cargo.toml` `a643ae2ebea97c6b1144d7d24239bd49833a03d9ddf0002581d3712010acfe1d`.
- One CLI process processed manifest IDs `0..589`; it did not use `--no-reset`. Source inspection confirms the current CLI resets `DfTract` before each subsequent file. Exit code: `0`; wall time: `225.75 s` for all clips, corresponding to batch wall RTF `0.1275` over 1,770 seconds of input (including per-file state reset and output I/O). This is a multi-file Mac measurement, not steady-state streaming RTF or Pi performance.
- Exactly 590 outputs were written, one per canonical ID; each is mono, 16 kHz, PCM16, 47,520 samples. `output_hashes.csv` records and allows verification of every output hash. The Stage 8 Python reference ledger was independently rechecked: all 590 hashes matched.
- The runtime emitted 288 `Possible clipping detected` warnings. In `tract.rs` this warning is triggered by the current input frame magnitude exceeding `0.9999`; it is not a count of clipped output files. No output files reached full-scale PCM, and this report does not interpret the warning as proof of output clipping.

The command arguments (including every manifest-ordered input file) are preserved in `runs/stage11_2_23_native_tract_canonical_parity_20261114/run_metadata.json`. The command form was:

```text
deep-filter --model ../models/dfn3_step500_tract.tar.gz --compensate-delay \
  --output-dir runs/stage11_2_23_native_tract_canonical_parity_20261114/native_predictions \
  <all 590 runs/sih26052_canonical_validation/noisy_audio/NNNN_noisy.wav files in manifest order>
```

## Waveform comparison

The reference is the actual saved float32 Stage 8 Step-500 prediction, not an approximate reconstruction. All per-file reference hashes matched its original ledger before comparison. Native PCM16 values were converted to float using `/32768`; no scaling, normalization, or additional time shift was applied.

| Measure | Result |
|---|---:|
| Clips / samples compared | 590 / 28,036,800 |
| Pooled Pearson correlation | 0.98268 |
| Mean per-clip Pearson correlation (median; 5th percentile; minimum) | 0.97970 (0.98993; 0.93302; 0.56400) |
| Pooled waveform SDR | 14.62 dB |
| Mean per-clip waveform SDR (median; 5th percentile; minimum) | 16.39 dB (16.94; 8.64; 1.51) |
| Mean per-clip RMSE (median; maximum) | 0.00842 (0.00699; 0.07816) |
| Pooled RMSE / MAE / maximum absolute error | 0.01092 / 0.00440 / 0.61006 |

These waveform distances show that high pooled correlation alone does not establish close parity: several clips differ substantially. The native output is quantized PCM16, while the reference is float32; quantization is a known difference, but does not explain the full observed spread by itself.

## Same-crop SNR and SI-SDR diagnostic

Because the available Python environments lack `soundfile`, `torch`, `pesq`, and `pystoi` as a compatible evaluation stack, the unchanged canonical evaluator could not be run. No packages were installed. The following two metrics were computed with the same active-speech power and SI-SDR formulas as `scripts/evaluate_dfn3_canonical.py::metrics`, applied to clean audio, the native output, and the Python reference truncated to the common 47,520-sample duration. These are **diagnostic common-crop values**, not replacements for the published full 3-second canonical results. STOI, PESQ-WB, joint-pass counts, and confidence intervals are not reported.

| Set / comparison | Output SNR | SI-SDR |
|---|---:|---:|
| Native Tract, common 47,520-sample crop | 11.475 dB | 10.065 dB |
| Saved Python Step-500 reference, same crop | 13.464 dB | 12.352 dB |
| Paired mean difference (native minus Python) | **-1.989 dB** | **-2.287 dB** |

| Target SNR bin | n | Native SNR | Python SNR, same crop | Δ SNR | Native SI-SDR | Python SI-SDR, same crop | Δ SI-SDR |
|---:|---:|---:|---:|---:|---:|---:|---:|
| -10 dB | 30 | 6.238 | 6.556 | -0.318 | 2.106 | 2.505 | -0.399 |
| -5 dB | 63 | 8.852 | 9.932 | -1.080 | 6.707 | 8.062 | -1.355 |
| 0 dB | 117 | 9.841 | 11.013 | -1.172 | 8.409 | 9.747 | -1.339 |
| 5 dB | 137 | 11.284 | 12.806 | -1.522 | 9.960 | 11.727 | -1.767 |
| 10 dB | 121 | 12.970 | 15.181 | -2.211 | 11.989 | 14.453 | -2.464 |
| 15 dB | 86 | 14.274 | 17.893 | -3.619 | 13.239 | 17.409 | -4.170 |
| 20 dB | 36 | 14.758 | 19.519 | -4.761 | 14.312 | 19.764 | -5.452 |

The degradation increases in the higher target-SNR groups. This is a meaningful warning that the packaged native inference does not currently reproduce the Python checkpoint's canonical output quality under this same-crop diagnostic. It is not evidence that the Step-500 checkpoint itself changed: the checkpoint and archive hashes match their protected values.

## Interpretation and next action

**Do not claim native deployment quality parity. Do not promote or modify the model.** Keep the protected Step-500 checkpoint and archive unchanged while investigating the inference-path difference (resampling, ONNX export/runtime numerics, framing/lookahead, and PCM serialization). Any correction must be followed by a newly named parity run and the full established metric stack; do not tune against this benchmark or silently update the original canonical results.

The full four-metric Tract-vs-PyTorch comparison remains incomplete because STOI/PESQ and the existing evaluator dependencies are unavailable in the local environments. Pi 5 execution, live ALSA streaming, physical latency, thermal soak, and headset qualification remain unverified. This run adds Mac-side offline inference evidence only.

## Addendum — full common-crop metric scoring (2026-11-14)

The dependency statement above was based on an incomplete environment search and is superseded by this addendum. The existing `../pc_venv` already contained the needed evaluator libraries; no packages were installed. The evaluator was imported with a process-local compatibility alias (`numpy.exceptions.RankWarning = numpy.RankWarning`) because installed pystoi expects the newer NumPy exception path. The unchanged `scripts/evaluate_dfn3_canonical.py::metrics` function was applied to the native output and the saved Python reference for all 590 clips on the identical first 47,520 samples. SciPy emitted its existing NumPy-version compatibility warning. The original 3-second Stage 8 results were not edited.

Command:

```text
../pc_venv/bin/python experiments/stage11_2_23_native_tract_parity/score_common_crop.py
../pc_venv/bin/python scripts/compare_dfn3_canonical.py --reference runs/stage11_2_23_native_tract_canonical_parity_20261114/common_crop_scoring/python/per_clip.csv --candidate runs/stage11_2_23_native_tract_canonical_parity_20261114/common_crop_scoring/native/per_clip.csv --output runs/stage11_2_23_native_tract_canonical_parity_20261114/common_crop_scoring/paired_native_vs_python.json --bootstrap 2000 --seed 26052
```

| Common-crop result (n=590) | Native Tract | Saved Python Step-500 | Paired delta, native minus Python (95% clip bootstrap CI) |
|---|---:|---:|---:|
| Output SNR | 11.4753 dB | 13.4640 dB | -1.9887 [-2.1721, -1.8077] dB |
| SI-SDR | 10.0651 dB | 12.3518 dB | -2.2866 [-2.4971, -2.0705] dB |
| STOI | 0.87942 | 0.88441 | -0.00499 [-0.00660, -0.00333] |
| PESQ-WB | 2.18823 | 2.23891 | -0.05068 [-0.06453, -0.03664] |
| Joint pass (>15 dB, >0.85, >2.5) | 111/590 (18.81%) | 161/590 (27.29%) | — |

The paired intervals are clip-level percentile bootstrap intervals; they do not account for speaker/noise-session clustering and are diagnostic only. The common-crop Python numbers differ from the previously reported full-duration baseline because the last 480 samples (30 ms) are excluded from both model outputs for parity. Neither set of values replaces the original 48,000-sample evaluation.

Native output SNR by target-SNR bin was -10 dB: 6.238 (n=30), -5 dB: 8.852 (63), 0 dB: 9.841 (117), 5 dB: 11.284 (137), 10 dB: 12.970 (121), 15 dB: 14.274 (86), and 20 dB: 14.758 (36). The corresponding paired native-minus-Python SNR changes were -0.318, -1.080, -1.172, -1.522, -2.211, -3.619, and -4.761 dB. The comparison reinforces the prior finding: the native inference path does not reproduce the Python output quality, even though it loads the protected archive successfully. No model or evaluator was changed.

Detailed per-clip four-metric rows and aggregate summaries are in `runs/stage11_2_23_native_tract_canonical_parity_20261114/common_crop_scoring/{native,python}/`; paired results are in `common_crop_scoring/paired_native_vs_python.json`. A supplemental checksum ledger covers these results and the updated reports.

## Follow-up root-cause status — Stage 11.2.25

The mismatch is now substantially explained. A controlled 2×2 resampler experiment found that replacing the native input Rubato FFT upsampler with SciPy polyphase recovered about 1.29 dB SNR and 1.96 dB SI-SDR on nine predeclared clips, while changing the output downsampler had negligible effect. A full 590-clip diagnostic using SciPy-compatible resampling around the unchanged Tract model scored 13.358 dB SNR / 12.306 dB SI-SDR / 0.88478 STOI / 2.23743 PESQ-WB, versus the Python common-crop reference at 13.464 / 12.352 / 0.88441 / 2.23891. The SNR delta is small but its clip-level bootstrap interval remains below zero; the other three intervals include zero. This SciPy path is experimental host-side pre/post-processing, not an integrated native runtime fix. The deployed native binary still uses Rubato; do not call parity fixed or promote it. See `research/STAGE11_2_25_NATIVE_RESAMPLER_ROOT_CAUSE.md`.

## Follow-up integrated candidate — Stage 11.2.26

An isolated Rust native candidate now embeds the 61-tap SciPy-equivalent 16↔48 kHz polyphase filter. Its full 590-clip results agree with the prior SciPy-controlled Tract output (`13.359 dB` SNR, `12.306 dB` SI-SDR, `0.88475` STOI, `2.238` PESQ-WB, `159/590` joint passes). Relative to the saved Python common-crop reference, the remaining differences are `-0.105 dB` SNR (clip-bootstrap CI `[-0.168, -0.039]`), `-0.046 dB` SI-SDR (CI crosses zero), `+0.00034` STOI and `-0.00136` PESQ-WB (both CIs cross zero). Quantizing the Python reference to PCM16 changes mean SNR by only `-0.003 dB`, so it does not explain the residual. The original deployment binary and source are untouched; this candidate is not a streaming resampler or Pi-tested release. Do not claim exact parity or promote. Stage 11.2.26 report: `research/STAGE11_2_26_NATIVE_POLYPHASE_PARITY_CANDIDATE.md`.

## Evidence paths

- Native WAVs and logs: `runs/stage11_2_23_native_tract_canonical_parity_20261114/`
- Per-file hashes: `output_hashes.csv`
- Per-clip waveform parity: `waveform_parity_per_clip.csv`
- Waveform summary: `waveform_parity_summary.json`
- Common-crop SNR/SI-SDR: `common_crop_metrics.csv` and `common_crop_metrics_summary.json`
- Full invocation, timing, and protected hashes: `run_metadata.json`
- SHA-256 inventory: `SHA256SUMS.txt`
