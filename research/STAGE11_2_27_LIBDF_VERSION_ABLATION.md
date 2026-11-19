# Stage 11.2.27 — libDF Source-Version Ablation

**Status: QUIET-FRAME VERSION DIFFERENCE IDENTIFIED; RESIDUAL PYTHON/TRACT SNR GAP NOT EXPLAINED; NO DEPLOYMENT CHANGE.**

## Objective and safeguards

This stage tested whether the small residual between the Stage 11.2.26 isolated Rust/Tract polyphase candidate and saved Python DFN3 Step-500 predictions came from the native code snapshot being based on DeepFilterNet/libDF `0.5.7-pre`, while the Python evaluator environment uses DeepFilterNet/deepfilterlib `0.5.6`.

Only local, authorized canonical development data were used. The 590-clip canonical set is reused development/model-selection data and is not independent validation. No model training, tuning, ensemble-weight change, promotion, gold access, Kaggle, Pi, live audio, upload, participant activity, network access, or package installation occurred. The deployed binary, checkpoints, archive, manifest, evaluator, and frozen predictions were not modified.

## Source and environment evidence

- Installed Python environment: Python `3.14.7`, PyTorch `2.14.1`, DeepFilterNet `0.5.6`, deepfilterlib `0.5.6`, SciPy `1.18.1`, NumPy `1.26.4`. The evaluator emitted the pre-existing SciPy/NumPy compatibility warning.
- Python enhancement source is the installed DeepFilterNet `0.5.6` package; `deepfilterlib` reports `0.5.6` in package metadata.
- Isolated native source was archived from local Git tag `v0.5.6`, commit `978576aa8400552a4ce9730838c635aa30db5e61`. The Stage 11.2.26 current native source descends from commit `d375b2d8309e0935d165700c91da9de862a99c31`, with local edits and crate version `0.5.7-pre`.
- The v0.5.6 source candidate was compiled against the already cached Stage 11.2.26 dependency manifest/lock (Tract `0.21.4`) because the exact v0.5.6 dependency graph was not cached. Thus this is a **source-code ablation**, not a bit-exact reconstruction of the original Python extension build or a fully pinned v0.5.6 runtime. The candidate did not change the weights or the 61-tap native polyphase resampler.
- Candidate binary SHA-256: `8ded76940c54e76920df6821e75f1289ed50887f5cab0b45463a5e9b969fb8df`.

## Controlled run

The same 590 manifest-ordered 16 kHz mono inputs and protected Tract archive were used. Each v0.5.6-source clip ran in its own native process, ensuring pristine recurrent/STFT state despite that source version not exposing the later `DfTract::reset()` method. The Stage 11.2.26 candidate used the same protected archive and polyphase resampler. Both native paths used the existing 30 ms delay compensation and wrote 16 kHz PCM16 outputs. Python comparison values are the saved Step-500 reference cropped to the same first 47,520 samples. The unchanged `scripts/evaluate_dfn3_canonical.py::metrics` and `scripts/compare_dfn3_canonical.py` were used.

All 590 v0.5.6 candidate processes exited 0 and produced 590 finite outputs with the expected 16 kHz mono shape. Native full-run time was `240.52 s`. Protected hashes before/after:

| Artifact | SHA-256 | Result |
|---|---|---|
| Canonical manifest | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` | unchanged |
| DFN3 Step-500 checkpoint | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` | unchanged |
| Tract archive | `99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d` | unchanged |

## Results on the common 47,520-sample crop (`n=590`)

| Path | SNR | SI-SDR | STOI | PESQ-WB | Joint passes |
|---|---:|---:|---:|---:|---:|
| Python Step-500 reference | 13.46396 dB | 12.35176 dB | 0.884408 | 2.23891 | 161/590 (27.29%) |
| Native v0.5.6-source + polyphase | 13.36673 dB | 12.31291 dB | 0.884772 | 2.23659 | 160/590 (27.12%) |
| Native v0.5.7-pre + polyphase (Stage 11.2.26) | 13.35864 dB | 12.30599 dB | 0.884752 | 2.23755 | 159/590 (26.95%) |

Paired clip bootstrap, 2,000 resamples, seed `26052`:

| Comparison (candidate minus reference) | SNR | SI-SDR | STOI | PESQ-WB |
|---|---:|---:|---:|---:|
| v0.5.6-source vs Python | −0.09723 [−0.15967, −0.02832] dB | −0.03885 [−0.11484, +0.03953] dB | +0.000364 [−0.000655, +0.001519] | −0.002316 [−0.011548, +0.008454] |
| v0.5.6-source vs v0.5.7-pre | +0.00809 [−0.00094, +0.02307] dB | +0.00692 [−0.00032, +0.01698] dB | +0.000020 [−0.000009, +0.000062] | −0.000961 [−0.003231, +0.001614] |

All v0.5.6-source versus v0.5.7-pre intervals include zero. The v0.5.6-source candidate remains about `0.097 dB` lower in SNR than Python, and its paired SNR interval excludes zero. This version ablation therefore does **not** explain the residual aggregate gap.

## Localized code-path difference

The comparison identified exactly 22 clips whose v0.5.6-source and v0.5.7-pre PCM16 waveforms differ; their IDs are:

`6, 73, 106, 110, 124, 149, 171, 176, 240, 287, 306, 314, 326, 386, 414, 446, 450, 453, 461, 522, 587, 589`.

These are exactly the same 22 clips with at least one 10 ms, 48 kHz input frame whose **mean-square power** is below `1e-7`. The other 568 waveforms matched. The source diff in `tract.rs` shows the behavior change:

- v0.5.6 returns zero output immediately for a low-power frame and skips that frame's analysis/model-state update.
- The local v0.5.7-pre source increments a quiet-frame counter and allows up to five such frames through inference; it zeros output only after more than five consecutive low-power frames. A non-low frame resets this counter.

Large clip-level waveform changes occurred on a small subset (for example IDs 6 and 287); the network's temporal state carries the effect beyond the affected frame. Across all 590 clips the mean metric changes remain small and not statistically clear. The quiet-frame behavior is a real reproducibility difference, but it is not the cause of the full residual SNR gap.

## Failures and command history

1. **Exit 101:** building the archived v0.5.6 dependency graph offline failed because Cargo could not find cached `educe` required by Tract `0.19.16`.
2. **Exit 101:** after temporarily updating only the Tract version and restricting workspace members, offline resolution failed on uncached `hashbrown 0.13.2` (and the initial full workspace also referenced uncached `iced_glow`). No network retry or install was attempted.
3. **Successful offline build (exit 0):** the isolated v0.5.6 source was retained, while its build manifest/lock was aligned to Stage 11.2.26's cached dependency set and only `libDF` was kept as a workspace member. Rust emitted compatibility/deprecation/lifetime warnings; compilation completed.
4. **Successful full inference (exit 0):** 590 fresh native processes, 590 WAVs, all return codes 0.
5. **Initial scoring/comparison script failed (exit 1):** it omitted the canonical manifest hash from its summary JSON, which the unchanged comparer requires. Corrected the run metadata and reran both paired comparisons successfully (exit 0). The scorer script was corrected so future fresh runs include the required manifest hash.

Successful command forms:

```text
CARGO_HOME=/private/tmp/stage26-cargo-home cargo build --offline --release -p deep_filter --bin deep-filter --no-default-features --features 'bin,tract,wav-utils,transforms' --manifest-path runs/stage11_2_27_libdf_version_ablation_20261114/DeepFilterNet/Cargo.toml --target-dir runs/stage11_2_27_libdf_version_ablation_20261114/target

../pc_venv/bin/python experiments/stage11_2_27_libdf_version_ablation/run_full_v056.py
../pc_venv/bin/python experiments/stage11_2_27_libdf_version_ablation/score_full_v056.py

../pc_venv/bin/python scripts/compare_dfn3_canonical.py --reference runs/stage11_2_27_libdf_version_ablation_20261114/metrics/python/per_clip.csv --candidate runs/stage11_2_27_libdf_version_ablation_20261114/metrics/v056/per_clip.csv --output runs/stage11_2_27_libdf_version_ablation_20261114/paired_v056_vs_python.json --bootstrap 2000 --seed 26052

../pc_venv/bin/python scripts/compare_dfn3_canonical.py --reference runs/stage11_2_27_libdf_version_ablation_20261114/metrics/python/per_clip.csv --candidate runs/stage11_2_27_libdf_version_ablation_20261114/metrics/v057/per_clip.csv --output runs/stage11_2_27_libdf_version_ablation_20261114/paired_v057_vs_python.json --bootstrap 2000 --seed 26052

../pc_venv/bin/python scripts/compare_dfn3_canonical.py --reference runs/stage11_2_27_libdf_version_ablation_20261114/metrics/v057/per_clip.csv --candidate runs/stage11_2_27_libdf_version_ablation_20261114/metrics/v056/per_clip.csv --output runs/stage11_2_27_libdf_version_ablation_20261114/paired_v056_vs_v057.json --bootstrap 2000 --seed 26052
```

## Verdict and next action

The Stage 11.2.25/26 input-resampler finding remains the dominant explanation for the original approximately 2 dB native regression. The libDF source-version change causes a reproducible quiet-frame branch difference in 22 clips but changes full-set SNR by only `+0.008 dB` versus v0.5.7-pre (paired CI crosses zero). The remaining approximately `0.10 dB` SNR gap to Python is unresolved.

Next diagnostic: on a tiny fixed non-gold subset, compare 48 kHz input framing, complex STFT frames, ERB and complex-normalized features, per-frame encoder/decoder outputs, recurrent/lookahead index mapping, and synthesized waveform frames between Python libDF 0.5.6 and the isolated native path. Keep any instrumentation in a new isolated copy. Do not modify the deployed runtime or claim parity until this residual is localized and a full comparison confirms the fix. Pi 5 qualification, real-time latency, ANC, and independent validation remain outstanding.

## Evidence paths

- Binary outputs and hashes: `runs/stage11_2_27_libdf_version_ablation_20261114/full_outputs_v056_source_hashes.csv`.
- Per-clip metric rows and summaries: `runs/stage11_2_27_libdf_version_ablation_20261114/metrics/{v056,v057,python}/`.
- Paired comparisons: `runs/stage11_2_27_libdf_version_ablation_20261114/paired_v056_vs_python.json`, `paired_v057_vs_python.json`, `paired_v056_vs_v057.json`.
- Per-clip waveform and metric deltas: `runs/stage11_2_27_libdf_version_ablation_20261114/waveform_v056_vs_v057_per_clip.csv`.
- Run metadata, source snapshot, binary and hash ledger: `runs/stage11_2_27_libdf_version_ablation_20261114/`.
