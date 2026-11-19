# SIH 26052 — Stage 8 Phase B: Waveform Compatibility and Alignment

**Status:** Audit complete. No ensemble waveform was created or scored. Existing prediction sets and baseline artifacts were read only.

## Data and file integrity

The exact canonical manifest was checked (`d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`). Each of the three output sets maps one-to-one to canonical IDs `0000` through `0589`:

| Set | Files | Sample rate | Channels | Samples / duration | File subtype | Per-file hashes verified |
|---|---:|---:|---:|---:|---|---:|
| DFN3 Step-500 | 590 | 16 kHz | 1 | 48,000 / 3.0 s | FLOAT | 590/590 |
| FullSubNet epoch 58 | 590 | 16 kHz | 1 | 48,000 / 3.0 s | FLOAT | 590/590 |
| GTCRN DNS3 | 590 | 16 kHz | 1 | 48,000 / 3.0 s | FLOAT | 590/590 |

All samples are finite. The WAV hashes matched each set’s pre-existing per-file ledger. The canonical noisy inputs were also checked: 590 IDs, 16 kHz mono, 48,000 samples, PCM_16. The audit did not read clean references and did not change, resample, shift, normalize, or rewrite any waveform.

## Timing and polarity checks

For each clip, zero-mean normalized full-signal cross-correlation was computed for each model pair and each model against the matching noisy mixture. A zero-padded NumPy FFT of length 131,072 provided linear correlation; the lag search covered ±2,048 samples (±128 ms). Positive lag means the first named signal is delayed relative to the second.

| Pair | Clips with best lag at 0 | Best-lag zero-correlation median (p01–p99) | Negative zero-lag correlations | Finding |
|---|---:|---:|---:|---|
| Step-500 vs FullSubNet | 588/590 | 0.986 (0.354–0.999) | 2 | Two low-correlation exceptions; details below |
| Step-500 vs GTCRN | 590/590 | 0.984 (0.577–0.999) | 0 | No observed delay or polarity inversion |
| FullSubNet vs GTCRN | 590/590 | 0.989 (0.667–0.999) | 0 | No observed delay or polarity inversion |
| Step-500 vs corresponding noisy input | 590/590 | 0.880 (0.287–0.999) | 0 | No observed delay or polarity inversion |
| FullSubNet vs corresponding noisy input | 590/590 | 0.884 (0.334–0.998) | 0 | No observed delay or polarity inversion |
| GTCRN vs corresponding noisy input | 590/590 | 0.885 (0.317–0.997) | 0 | No observed delay or polarity inversion |

The two Step-500 / FullSubNet exceptions are canonical IDs **162** and **436**. For these, the largest absolute correlation inside the ±128 ms window occurred near its positive boundary: ID 162 at `+2044` samples (`+127.75 ms`, correlation `-0.314`; zero-lag `-0.139`), and ID 436 at `+1978` samples (`+123.625 ms`, correlation `-0.332`; zero-lag `-0.194`). These are weak, negative peaks and do not establish a true delay or a polarity inversion. For both clips, Step-500 vs GTCRN and FullSubNet vs GTCRN had their best correlation at zero lag. Treat the direct Step-500 / FullSubNet waveform relationship for these two clips as **ambiguous**, rather than applying a per-clip shift or polarity correction.

**Phase B timing finding:** IDs and sample grids agree, and no systematic inter-model delay was observed. The pairwise checks support common sample timing for the three sets, with two weak-correlation exceptions between Step-500 and FullSubNet. Correlation measures similarity; different enhancement methods can legitimately change waveform phase and content, so high correlation is not assumed as a mixing prerequisite and low correlation alone is not treated as proof of misalignment.

## Amplitude convention

All three prediction sets are float WAVs; no file-level clipping or peak normalization was applied during inference. The table gives per-clip statistics:

| Set | RMS p01 / median / p99 | Peak absolute max | Files with peak ≥0.999 | Files with peak >1.0 | Median RMS / noisy RMS |
|---|---|---:|---:|---:|---:|
| Step-500 | 0.00516 / 0.04793 / 0.13215 | 0.97814 | 0 | 0 | 0.7845 |
| FullSubNet | 0.00597 / 0.05177 / 0.14548 | 1.03531 | 14 | 14 | 0.8508 |
| GTCRN | 0.00618 / 0.05012 / 0.14031 | 1.03550 | 3 | 2 | 0.8213 |

The noisy PCM_16 inputs have 282 clips at or above peak `0.999`. FullSubNet and GTCRN retain float samples above `1.0`; their stored files are not clipped, but conversion to bounded PCM or playback may clip unless an output policy is specified. Output RMS ratios vary per clip; there is no common model loudness normalization. No gain was applied in this audit.

## Interpretation and next gate

The three sets are structurally sample-compatible and show no systematic offset or global polarity inversion. Two low/negative Step-500 / FullSubNet correlations need to remain visible in any later analysis. Peak conventions also differ from bounded PCM expectations. Phase B did not test whether averaging improves quality, and this report makes no ensemble claim.

The audit used Python `3.14.7`, NumPy `1.26.4`, and SoundFile `0.14.0`. An initial `scipy.signal.correlate` attempt failed with exit code 1 due to the existing SciPy 1.18.1 / NumPy 1.26.4 compatibility issue (`ValueError: NoneType copy mode not allowed`). The successful audit uses NumPy FFT correlation and completed 590/590 with exit code 0. One subsequent probe command was first issued from the workspace parent, where its relative Python path did not exist (exit code 127); it read or changed no files, and the corrected command completed successfully. No project data or prediction files were altered by either failed command.

## Reproduction artifacts

- Audit command, from the `antigravity` project directory: `../pc_venv/bin/python scripts/audit_stage8_alignment.py --output-dir runs/stage8_ensemble_20261113/phase_b_alignment`
- Script: `scripts/audit_stage8_alignment.py`
- Per-clip pairwise lags/correlations: `runs/stage8_ensemble_20261113/phase_b_alignment/pairwise_waveform_alignment.csv`
- Summary metadata and amplitude checks: `runs/stage8_ensemble_20261113/phase_b_alignment/alignment_summary.json`
- Script SHA-256: `610e88af4506c77fcf9c47cde82f9e189290c9d0f834175f889cd3a1c0602f85`
- CSV SHA-256: `ad829d7ab6b152e68491ea66a5aafdb746377a373d9e3c4922a3e922d28e5ce0`
- JSON SHA-256: `f7064901a271c022ed491edbb0cdc4863d25416a2f1858df368ceedbf20c5763`

**No ensemble simulation, optimization, or model promotion was performed. Awaiting separate approval before Phase C.**
