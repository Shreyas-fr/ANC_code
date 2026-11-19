# Stage 11.2.26 — Native Polyphase Parity Candidate

**Status: RESAMPLER REGRESSION FIXED IN AN ISOLATED NATIVE CANDIDATE; SMALL PYTHON/TRACT QUALITY DIFFERENCE REMAINS; NOT A DEPLOYMENT RELEASE.**

## Scope and preservation

This stage implemented the Stage 11.2.25 resampler finding in a separate copy of the existing modified DeepFilterNet source tree. The original source checkout, deployed binary, protected Step-500 checkpoint, Tract archive, canonical manifest, canonical evaluator, Stage 8 frozen predictions, and 15/70/15 ensemble were not modified. The candidate binary is under `runs/stage11_2_26_native_polyphase_candidate_20261114/target/release/deep-filter` and is not installed or promoted.

The modified source snapshot is under `runs/stage11_2_26_native_polyphase_candidate_20261114/DeepFilterNet/`. It retains the prior checkout's local modifications while omitting its existing 5.9 GB `target`, `.git`, and model-cache trees. Only `transforms.rs` and the WAV CLI's resampling call sites were changed in that copy. The new conversion supports equal-rate pass-through and the project 16↔48 kHz pair; unsupported non-equal rates fail explicitly. The filter is the 61-tap Kaiser-windowed FIR used by SciPy `resample_poly` (cutoff 1/3, Kaiser beta 5, f32 coefficients, scaled by the up factor). The legacy Rubato function remains available for the other library routines.

Protected hashes were checked before and after the full run:

| Artifact | SHA-256 | Result |
|---|---|---|
| Canonical manifest | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` | unchanged |
| DFN3 Step-500 checkpoint | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` | unchanged |
| Tract archive | `99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d` | unchanged |

No gold set, Kaggle, Pi, live audio, participant data, or network was accessed. No model was trained or tuned, and no packages were installed. Cargo compiled offline from already cached dependencies with a temporary Cargo home.

## Verification of the resampler implementation

The first candidate subset run failed because its tap-window lower-bound calculation used the half-length rather than the final tap index. That output is preserved in `subset_native_outputs/` and `subset_comparison.csv`; it is invalid and excluded from all candidate results below. The implementation was corrected in the isolated source copy. A subsequent nine-clip validation, one clip per target-SNR bin plus IDs 162 and 436, returned exit code 0:

- Native integrated candidate versus Stage 11.2.25 SciPy-controlled native outputs: mean waveform correlation `0.99999977` (minimum `0.99999942`), mean RMSE `1.04e-5`.
- Mean metric differences over the nine clips were under `0.00024 dB` SNR, `0.000014 dB` SI-SDR, `0.000024` STOI and `0.0023` PESQ-WB.

The small PESQ difference is consistent with the different PCM quantization point: this candidate's CLI writes 16 kHz PCM16, while the Stage 11.2.25 control wrote 48 kHz PCM16 and then downsampled to float. The waveform match shows the new Rust conversion reproduces the external SciPy-resampling control closely.

## Full frozen-development comparison (`n = 590`)

The isolated candidate processed all 590 canonical inputs with the same protected Tract archive, per-clip state reset and 30 ms delay compensation. Native outputs are 16 kHz mono PCM16, 47,520 samples after delay compensation. The unchanged `scripts/evaluate_dfn3_canonical.py::metrics` function scored candidate outputs and saved Python Step-500 outputs on the same 47,520-sample crop. The paired comparison uses 2,000 clip-bootstrap resamples, seed 26052; it does not adjust for speaker/noise-session clustering.

| Metric | Native polyphase candidate | Saved Python Step-500, same crop | Candidate minus Python (95% CI) |
|---|---:|---:|---:|
| Output SNR | 13.3586 dB | 13.4640 dB | `-0.1053` [`-0.1677`, `-0.0387`] dB |
| SI-SDR | 12.3060 dB | 12.3518 dB | `-0.0458` [`-0.1226`, `+0.0319`] dB |
| STOI | 0.88475 | 0.88441 | `+0.00034` [`-0.00067`, `+0.00151`] |
| PESQ-WB | 2.23755 | 2.23891 | `-0.00136` [`-0.01068`, `+0.00915`] |
| Joint pass (>15 dB, >0.85, >2.5) | 159/590 (26.95%) | 161/590 (27.29%) | — |

The original Rubato path in Stage 11.2.23 scored 11.4753 dB SNR, 10.0651 dB SI-SDR, 0.87942 STOI, 2.18823 PESQ-WB and 111/590 joint passes on this common crop. The new native candidate recovers about `1.883 dB` SNR and `2.241 dB` SI-SDR relative to that path. Its metrics agree with the Stage 11.2.25 SciPy-controlled Tract run to rounding.

To investigate the remaining SNR gap, the Python Step-500 predictions were simulated as 16 kHz PCM16 using the CLI's `sample * i16::MAX` truncation rule. Quantization alone changed mean Python SNR by only `-0.0032 dB` (SI-SDR `-0.0005 dB`, STOI `-0.00006`, PESQ-WB `-0.0011`). Therefore output PCM16 quantization does not explain the remaining `-0.105 dB` native-versus-Python SNR difference. The residual is outside the resampling path; model graph numerics, STFT/features, recurrent lookahead alignment or synthesis remain to be compared directly. Do not label this exact numerical parity.

Native candidate results by target-SNR bin:

| Target SNR | n | Output SNR | SI-SDR | STOI | PESQ-WB | Joint passes |
|---:|---:|---:|---:|---:|---:|---:|
| -10 dB | 30 | 6.646 | 2.748 | 0.677 | 1.378 | 0/30 |
| -5 dB | 63 | 9.913 | 8.073 | 0.804 | 1.694 | 3/63 |
| 0 dB | 117 | 11.002 | 9.839 | 0.856 | 1.867 | 9/117 |
| 5 dB | 137 | 12.753 | 11.741 | 0.892 | 2.150 | 20/137 |
| 10 dB | 121 | 15.021 | 14.346 | 0.928 | 2.508 | 45/121 |
| 15 dB | 86 | 17.607 | 17.139 | 0.950 | 2.836 | 53/86 |
| 20 dB | 36 | 19.209 | 19.440 | 0.962 | 3.102 | 29/36 |

## Runtime and known boundaries

- Candidate binary SHA-256: `5ade7a9624001859b9574a79a2ca9d08f0c341f3626aced28ccc5e60933e8b45` (macOS arm64 build).
- Full 590-file batch wall time: `223.94 s`, batch RTF `0.1265` over 1,770 s input. This is an offline Mac measurement, not streaming frame latency or Pi performance.
- The algorithm processes an entire array in the CLI and is not a stateful low-latency polyphase stream adapter. It is a canonical parity candidate only.
- The 590 clips remain repeatedly used development/model-selection data. The full-set clip bootstrap is not speaker-cluster adjusted and is not independent validation.
- Full-set mean SNR and PESQ remain below the project targets. This does not establish that the frozen 15/70/15 ensemble is deployable in real time.
- The candidate has not been built or measured on Raspberry Pi 5, connected to ALSA, or run with the live dual-microphone/ANC path.

## Commands and failures

Successful build command:

```text
CARGO_HOME=/private/tmp/stage26-cargo-home cargo build --offline --release -p deep_filter --bin deep-filter --no-default-features --features 'bin,tract,wav-utils,transforms' --manifest-path runs/stage11_2_26_native_polyphase_candidate_20261114/DeepFilterNet/Cargo.toml --target-dir runs/stage11_2_26_native_polyphase_candidate_20261114/target
```

Successful full-run command:

```text
../pc_venv/bin/python experiments/stage11_2_26_native_polyphase_candidate/run_full_candidate.py
```

The script then invoked the unchanged comparer with `--bootstrap 2000 --seed 26052`; both commands exited 0. Build warnings were four pre-existing Rust lifetime-syntax warnings in `tract.rs`; no compile errors remained.

Failures preserved for audit:

1. An early Cargo invocation using `/private/tmp/stage25-cargo-home` failed to locate the cached Git dependency offline. The build succeeded after creating a fresh temporary Cargo home and symlinking the already-present Cargo Git cache; no network access occurred.
2. First polyphase subset build exposed the tap-index bug described above. Its poor output was retained but excluded. The corrected v2 subset and 590-clip candidate both succeeded.
3. A rerun attempt that targeted the existing first subset output directory was refused by the script's overwrite guard; no files were overwritten.

## Verdict and next stage

**The input-side Rubato resampler was the dominant cause of the Stage 11.2.23 quality drop.** The isolated Rust polyphase candidate reproduces the SciPy-controlled native path across 590 development clips and substantially restores Python quality. The residual SNR difference is small but its clip-bootstrap interval excludes zero; direct Python/Tract internals have not been reconciled. The original deployed runtime remains unchanged and still contains Rubato in its 16↔48 kHz CLI path. Do not promote this candidate or claim exact parity.

Next software-only stage: inspect and compare frame-level analysis/features, recurrent/lookahead outputs, and synthesis between Python libDF and Rust/Tract on a small fixed non-gold sample to localize the remaining residual. Any proposed correction stays in an isolated candidate and must be re-scored against the frozen development set. Physical Pi 5 qualification, independent validation, synchronized dual-microphone ANC and the 15/70/15 live-streaming architecture remain open gates.

## Evidence files

- Full output WAV hashes: `runs/stage11_2_26_native_polyphase_candidate_20261114/output_hashes.csv`.
- Full paired per-clip metrics: `runs/stage11_2_26_native_polyphase_candidate_20261114/full_metrics/`.
- Run commands, runtime and protected hashes: `runs/stage11_2_26_native_polyphase_candidate_20261114/full_run_metadata.json`.
- Corrected subset check: `subset_v2_comparison.csv` and `subset_v2_run_metadata.json`.
- Build source snapshot and isolated binary: `runs/stage11_2_26_native_polyphase_candidate_20261114/DeepFilterNet/` and `target/release/deep-filter`.
- SHA-256 evidence ledger: `runs/stage11_2_26_native_polyphase_candidate_20261114/SHA256SUMS.txt`.
