# SIH 26052 — Stage 8 Three-Model Ensemble Feasibility

**Status:** fixed, offline diagnostic simulations complete. No training, inference, unrestricted weight search, gold-set access, Kaggle/Pi access, promotion, or deployment occurred. The protected Step-500 model remains unchanged.

## Method and predeclared configurations

Phase A/B verified 590 waveform predictions per model and common 16 kHz / mono / 48,000-sample grids. Phase B had two ambiguous pairwise Step-500 / FullSubNet correlation clips (IDs 162, 436); they remain included and flagged with no shifting, phase correction, or exclusion. Predictions were joined by canonical `val_index`, read from the saved float WAVs, and combined sample-for-sample. All 4,720 ensemble outputs remain float WAV; no clipping or peak normalization was applied.

Predeclared tests: D1 raw equal thirds; D2 weights (0.20/0.60/0.20), (0.25/0.50/0.25), (0.15/0.70/0.15); D3 all three equal-weight pairs; plus one D1 amplitude-policy diagnostic. D4 was not run. The amplitude-policy diagnostic applies only fixed global scalar factors from Phase B's output-only median RMS values, making each model's median clip RMS equal to `0.05011982079309145`, then averages in equal thirds: Step-500 `1.045618`, FullSubNet `0.968214`, GTCRN `1.000000`. No clip-specific normalization or clean-reference/metric-based scaling was used. It is an in-sample amplitude diagnostic, not a deployable calibration.

Scoring used the unchanged `scripts/evaluate_dfn3_canonical.py::metrics` implementation (SHA-256 `66e448cc47b0ae60846399d803d8f6321068c5e4a9faa18f6ebb09305219b16a`) and the same clean/noisy references as the frozen canonical evaluation. Paired confidence intervals used `scripts/compare_dfn3_canonical.py`, 2,000 paired bootstrap resamples, seed 26052. All three baselines' stored per-clip metrics were previously reproduced exactly in Stage 8A.

These are objective metrics only; no human listening panel or speech-distortion annotation was conducted. Eight fixed configurations and multiple paired comparisons were examined on a repeatedly used benchmark without a multiplicity correction, so the apparent best variant is selection-exposed and exploratory.

## Overall results

| Model / variant | Mean SNR | Mean SI-SDR | Mean STOI | Mean PESQ-WB | Joint pass |
|---|---:|---:|---:|---:|---:|
| step500 | 13.467 | 12.363 | 0.88469 | 2.23229 | 161/590 (27.3%) |
| fullsubnet | 14.904 | 13.700 | 0.90258 | 2.51335 | 218/590 (36.9%) |
| gtcrn | 13.844 | 12.489 | 0.88135 | 2.11494 | 144/590 (24.4%) |
| d1_equal_333_raw | 14.716 | 13.800 | 0.90602 | 2.55155 | 223/590 (37.8%) |
| d1_equal_333_rms_matched | 14.747 | 13.786 | 0.90594 | 2.54891 | 223/590 (37.8%) |
| d2_fs60_raw | 14.997 | 13.974 | 0.90728 | 2.58932 | 226/590 (38.3%) |
| d2_fs50_raw | 14.917 | 13.942 | 0.90724 | 2.58327 | 226/590 (38.3%) |
| d2_fs70_raw | 15.041 | 13.965 | 0.90686 | 2.58526 | 227/590 (38.5%) |
| d3_step500_fullsubnet_5050_raw | 14.716 | 13.795 | 0.90645 | 2.56352 | 218/590 (36.9%) |
| d3_step500_gtcrn_5050_raw | 14.120 | 13.183 | 0.89711 | 2.35318 | 189/590 (32.0%) |
| d3_fullsubnet_gtcrn_5050_raw | 14.770 | 13.635 | 0.90258 | 2.52343 | 216/590 (36.6%) |

The highest observed joint pass among the fixed actual variants is **d2_fs70_raw** at 227/590 (38.5%). It passes more clips than FullSubNet alone (218/590), but this is a diagnostic result on a repeatedly used benchmark, not independent validation. No model or weight set is selected for deployment. Only D2 0.15/0.70/0.15 has mean SNR above 15 dB (`15.041 dB`); this does not mean the joint target is universally met.

All mixtures are unclipped FLOAT WAVs. Some exceed the usual PCM peak of 1.0:

| Variant | Maximum absolute peak | Files with peak >1.0 |
|---|---:|---:|
| d1_equal_333_raw | 1.004331 | 2 |
| d1_equal_333_rms_matched | 1.008207 | 2 |
| d2_fs60_raw | 1.015058 | 2 |
| d2_fs50_raw | 1.010956 | 2 |
| d2_fs70_raw | 1.019160 | 6 |
| d3_step500_fullsubnet_5050_raw | 1.004802 | 1 |
| d3_step500_gtcrn_5050_raw | 0.998884 | 0 |
| d3_fullsubnet_gtcrn_5050_raw | 1.025364 | 6 |

## Paired comparisons against FullSubNet epoch 58

Differences are candidate minus FullSubNet; brackets are 95% paired bootstrap CIs.

| Variant | SNR dB (95% CI) | SI-SDR dB (95% CI) | STOI (95% CI) | PESQ-WB (95% CI) |
|---|---|---|---|---|
| d1_equal_333_raw | SNR -0.187 [-0.327, -0.050] | SI-SDR +0.100 [-0.045, +0.253] | STOI +0.003 [+0.002, +0.005] | PESQ-WB +0.038 [+0.019, +0.058] |
| d2_fs60_raw | SNR +0.093 [+0.016, +0.167] | SI-SDR +0.274 [+0.187, +0.368] | STOI +0.005 [+0.004, +0.006] | PESQ-WB +0.076 [+0.062, +0.090] |
| d2_fs70_raw | SNR +0.137 [+0.083, +0.190] | SI-SDR +0.265 [+0.199, +0.335] | STOI +0.004 [+0.003, +0.005] | PESQ-WB +0.072 [+0.060, +0.084] |
| d3_step500_fullsubnet_5050_raw | SNR -0.188 [-0.329, -0.050] | SI-SDR +0.095 [-0.043, +0.234] | STOI +0.004 [+0.003, +0.005] | PESQ-WB +0.050 [+0.032, +0.068] |
| d3_step500_gtcrn_5050_raw | SNR -0.784 [-0.996, -0.577] | SI-SDR -0.517 [-0.718, -0.295] | STOI -0.005 [-0.007, -0.003] | PESQ-WB -0.160 [-0.187, -0.133] |
| d3_fullsubnet_gtcrn_5050_raw | SNR -0.134 [-0.247, -0.029] | SI-SDR -0.065 [-0.191, +0.081] | STOI +0.000 [-0.001, +0.001] | PESQ-WB +0.010 [-0.005, +0.026] |

The two 60–70% FullSubNet-favored mixes have positive paired intervals for all four metrics versus FullSubNet, with only modest joint-pass gains (8–9 additional clips). Raw equal thirds improves STOI and PESQ-WB versus FullSubNet but loses mean SNR; its SI-SDR interval includes zero. Equal median-RMS matching changes raw equal-thirds SNR by only about +0.031 dB and does not change the 223 joint passes. Paired amplitude-matched minus raw equal-thirds CIs (all 590): snr_db +0.0306 [+0.0246, +0.0366] | si_sdr_db -0.0132 [-0.0170, -0.0093] | stoi -0.0001 [-0.0001, -0.0001] | pesq_wb -0.0026 [-0.0032, -0.0020]. The intervals are tight but effect sizes are tiny; this amplitude policy is not a material ensemble gain.

## Combined target-SNR ≤0 dB region

This subgroup has 210 clips. Means and joint pass counts:

| Model / variant | n | SNR | SI-SDR | STOI | PESQ-WB | Joint pass |
|---|---:|---:|---:|---:|---:|---:|
| step500 | 210 | 10.065 | 8.242 | 0.81499 | 1.74012 | 11/210 |
| fullsubnet | 210 | 10.879 | 9.250 | 0.83905 | 1.89354 | 17/210 |
| gtcrn | 210 | 10.107 | 8.279 | 0.81110 | 1.65728 | 9/210 |
| d1_equal_333_raw | 210 | 11.009 | 9.661 | 0.84674 | 1.98056 | 20/210 |
| d1_equal_333_rms_matched | 210 | 11.029 | 9.655 | 0.84669 | 1.97993 | 20/210 |
| d2_fs60_raw | 210 | 11.135 | 9.711 | 0.84738 | 1.99007 | 17/210 |
| d2_fs50_raw | 210 | 11.112 | 9.729 | 0.84777 | 1.99308 | 19/210 |
| d2_fs70_raw | 210 | 11.124 | 9.651 | 0.84635 | 1.97858 | 18/210 |
| d3_step500_fullsubnet_5050_raw | 210 | 11.007 | 9.655 | 0.84747 | 1.98599 | 16/210 |
| d3_step500_gtcrn_5050_raw | 210 | 10.587 | 9.134 | 0.83475 | 1.84105 | 14/210 |
| d3_fullsubnet_gtcrn_5050_raw | 210 | 10.887 | 9.351 | 0.84006 | 1.91873 | 15/210 |

For the highest-joint fixed mix (d2_fs70_raw), the ≤0 dB subset has 18/210 joint passes versus FullSubNet's 17/210. Its means are SNR 11.124 dB, SI-SDR 9.651 dB, STOI 0.84635, PESQ-WB 1.97858. For D2 0.15/0.70/0.15 versus FullSubNet, paired ≤0 dB metric differences are: snr_db +0.245 [+0.178, +0.319] | si_sdr_db +0.402 [+0.287, +0.544] | stoi +0.007 [+0.006, +0.009] | pesq_wb +0.085 [+0.068, +0.103]. The fixed benchmark shows positive mean metric differences, but joint-pass improvement is only one clip and low-bin means remain well below the joint criteria; this is not a validated operational gain.

## SNR-bin and clipwise behavior

All seven target-SNR bins for three baselines and eight variants are in `research/STAGE8_ENSEMBLE_SNR_BINS.csv`. Paired deltas and intervals for every variant versus every standalone baseline, for both all 590 clips and the combined ≤0 dB subset, are in `research/STAGE8_ENSEMBLE_PAIRED_COMPARISONS.csv` (2,000 resamples, seed 26052). The clipwise diagnostic table counts all-four-metric improvements, SNR improvements paired with STOI/PESQ degradation, and cases worse than all standalone models: `research/STAGE8_ENSEMBLE_CLIPWISE_DIAGNOSTICS.csv`. For D2 0.15/0.70/0.15, all four metrics improve over FullSubNet on 304 clips; SNR improves while STOI or PESQ-WB declines on 96 clips. No variant is strictly worse on all four metrics than all three standalone models on any clip. IDs 162 and 436 are explicitly flagged for every variant in `research/STAGE8_ENSEMBLE_ALIGNMENT_FLAGS.csv`; no correction was applied.

## Oracle diagnostics (not achievable model outputs)

The standalone joint-pass counts are Step-500 161, FullSubNet 218, and GTCRN 144. An oracle that chooses any standalone model that passes all three criteria reaches **232/590 (39.3%)**. Per-clip best metric upper bounds:

| Metric | Oracle mean of per-clip maxima | Oracle median of per-clip maxima |
|---|---:|---:|
| snr_db | 15.65787 | 15.16009 |
| si_sdr_db | 14.48682 | 14.24697 |
| stoi | 0.90797 | 0.94001 |
| pesq_wb | 2.56148 | 2.50646 |

Which model supplied each per-clip metric maximum and the oracle joint result are in `research/STAGE8_ORACLE_DIAGNOSTICS.csv`. These values depend on clean-reference scores and are post hoc diagnostics, not implementable selection rules.

## Compute and deployment feasibility

Parameter counts from the verified model records are Step-500 2,135,484, FullSubNet 5,637,635, GTCRN 48,245; total **7,821,364 parameters**. Protected checkpoint storage is 76,953,676 bytes (73.39 MiB): Step-500 8,704,788, FullSubNet 67,669,069, GTCRN 579,819. A weighted ensemble must run every model whose weight is nonzero for each clip/block, then sum the outputs. All are already at 16 kHz, so this experiment needed no sample-rate conversion.

Measured prior standalone CPU inference-only RTFs on the Mac are Step-500 0.0158, FullSubNet 0.1104, GTCRN 0.0097; their arithmetic sum is about 0.1360. This is only a rough sequential estimate from separate runs/environments, not a combined runtime measurement. Prior peak process RSS observations were about 362 MiB, 847 MiB, and 131 MiB respectively; they cannot be summed into a reliable shared-process memory estimate. FullSubNet uses offline normalization and two-frame look-ahead, so direct streaming integration is not established. No Raspberry Pi, latency, live microphone, or real-time test was performed. **Real-time suitability is not claimed.**

## Eight decision questions

1. **Does raw equal averaging outperform each individual?** No. It clearly improves over Step-500 and GTCRN, but its SNR is below FullSubNet (paired Δ −0.187 dB, CI [−0.327, −0.050]); SI-SDR is inconclusive versus FullSubNet. STOI and PESQ-WB improve.
2. **Does FullSubNet-favored averaging perform better?** The 0.20/0.60/0.20 and 0.15/0.70/0.15 variants improve all four means over FullSubNet with paired intervals above zero. The gains are modest and exploratory; the 0.25/0.50/0.25 SNR CI includes zero.
3. **Does any pairwise variant outperform the three-model mix?** No pairwise mix beats the best predeclared three-model weighted mix on joint passes or all aggregate metrics. FullSubNet + GTCRN is near FullSubNet but has fewer joint passes; DFN3 + GTCRN is weaker.
4. **Are errors complementary enough to justify an ensemble?** There is evidence of complementary errors: fixed weighted mixes improve several metrics over FullSubNet and modestly increase joint passes. The benefit is small, and two Step-500/FullSubNet correlation exceptions remain flagged.
5. **How close is the best actual ensemble to the oracle?** Best actual is 227/590; oracle union is 232/590, a gap of 5 clips (0.8 percentage points).
6. **Is the gain meaningful at ≤0 dB?** Not clearly. Best actual has 18/210 vs FullSubNet 17/210, and mean low-bin SNR remains 11.12 dB. The paired subgroup intervals are provided before making any low-SNR claim.
7. **Is three-model compute justified?** Not yet. Fixed mixes show diagnostic gains, but require all nonzero-weight models, roughly 7.82M parameters / 73.4 MiB of checkpoints, and retain FullSubNet's offline limitations. No Pi/real-time evidence exists.
8. **Single best next experiment:** evaluate the predeclared `d2_fs70_raw` candidate on a new independent, non-gold validation set with a frozen amplitude policy and no weight retuning; include clips analogous to the flagged IDs and listen for speech distortion before considering hardware work.

## Commands, software, inputs and outputs

- Simulation command (from project root): `../pc_venv/bin/python scripts/run_stage8_ensemble_simulations.py --output-root runs/stage8_ensemble_20261113/phase_c_ensembles` (exit 0; 8 variants, 4,720 float WAVs, 24 paired comparison runs).
- Summary command: `../pc_venv/bin/python scripts/summarize_stage8_ensembles.py`.
- Paired comparison command pattern (run for each variant and each baseline): `../pc_venv/bin/python scripts/compare_dfn3_canonical.py --reference runs/<baseline>/per_clip.csv --candidate runs/stage8_ensemble_20261113/phase_c_ensembles/<variant>/per_clip.csv --output runs/stage8_ensemble_20261113/phase_c_ensembles/paired_comparisons/<variant>_vs_<baseline>.json --bootstrap 2000 --seed 26052` (all 24 exited 0; exact argument arrays are recorded in `run_record.json`).
- Software: Python `3.14.7`, PyTorch `2.14.1` (metric environment), NumPy `1.26.4`, SciPy `1.18.1`, SoundFile `0.14.0`, pystoi `0.4.1`, PESQ package. The prior GTCRN predictions were made in the recorded Python `3.10.22` / PyTorch `1.11.0` environment.
- Manifest SHA-256: `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`. The 1,770 source predictions were individually hash-verified against their existing ledgers before and after simulation; the protected checkpoints and manifest were not written.
- Protected checkpoint SHA-256 values: Step-500 `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27`; FullSubNet `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0`; GTCRN `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79`.
- Per-variant float WAVs, `per_clip.csv`, `prediction_files.csv` and `summary.json` are under `runs/stage8_ensemble_20261113/phase_c_ensembles/<variant>/`. Each output WAV SHA-256 is in its `prediction_files.csv`.
- Full artifact inventory with per-file output hashes: `runs/stage8_ensemble_20261113/phase_c_ensembles/PHASE_C_ARTIFACT_HASHES.csv` (SHA-256 `a2222826cc74863d856878fa76e60c82d8f044f859410aec4ce7715d039c16c7`). The inventory includes all 4,720 ensemble WAVs, source prediction hash ledgers, protected input hashes, source code, summaries, comparisons, and required CSV tables.
- Phase C run record (commands, source hashes, weights/scales, environment and exit codes): `runs/stage8_ensemble_20261113/phase_c_ensembles/run_record.json`.
- Existing NumPy/SciPy compatibility warning appeared during metric import; all scoring and paired comparisons completed. No simulation/scoring failures occurred.
- This canonical set was already used for model comparison and exploratory research. These variants are not independent validation; no weights are selected for deployment and no gold set was accessed.

## Required tables

- `research/STAGE8_ENSEMBLE_SUMMARY.csv`
- `research/STAGE8_ENSEMBLE_PAIRED_COMPARISONS.csv`
- `research/STAGE8_ENSEMBLE_SNR_BINS.csv`
- `research/STAGE8_ORACLE_DIAGNOSTICS.csv`
- Additional clipwise diagnostic: `research/STAGE8_ENSEMBLE_CLIPWISE_DIAGNOSTICS.csv`
- Alignment exception flags: `research/STAGE8_ENSEMBLE_ALIGNMENT_FLAGS.csv`

**Decision:** retain deployed Step-500. Phase C is diagnostic only. Stop here for review; no further training, tuning, inference, model changes, or deployment was performed.
