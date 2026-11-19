# SIH 26052 DeepFilterNet3 V8 Canonical Evaluation Report

**Decision:** Do **not** deploy any V8 checkpoint. Keep the existing **Deployed Step-500** model as the active deployment candidate.

## 1. Training Run Evidence

- **Kaggle Kernel:** `shreyasdivekar/deepfilternet3-v8-sih26052` (Notebook source: `antigravity/notebooks/v8/deepfilternet3_v8_sih26052.ipynb`, metadata: `antigravity/notebooks/v8/kernel-metadata.json`)
- **Controlled Experiment Change:** Repeats the V7 conservative fine-tuning recipe (`AdamW lr=1e-6, weight_decay=1e-4`), V6 full-pool random speech-row sampler, canonical exclusions, source-group splits, V5 target-aligned RIR policy, clipping augmentation, loss objective, initialization, and 25-step checkpoint interval, extending training from 250 steps to **500 optimizer steps**.
- **Hardware & Runtime:** Dual Tesla T4 (`GPU: Tesla T4 | count: 2`), upstream DeepFilterNet3 (`48000 Hz`, `2,135,484` parameters).
- **Attached Datasets & Leakage Controls:**
  - `shreyasdivekar/anc-sih-training-data`, `panavpayappagoudar/sih-26-processed-audio`, `shreyasdivekar/sih26052-canonical-exclusions`
  - Canonical exclusions (`canonical_exclusions.csv`): `3,686` rows loaded, `333` matching rows removed; `121,991` remaining metadata rows.
  - Source-group SHA-256 90/10 split: `{'drone': (246, 27), 'environment': (22455, 2495), 'gunfire': (1305, 145), 'speech': (85950, 7368), 'vehicle': (1800, 200)}`.
  - Train mixtures = `7,200`; fixed validation mixtures = `512` (`Validation identity check: True`; validation determinism verified across `[0, 1, 42, 100]`; train preflight verified 40 consecutive finite samples).
  - **Distinct training speech rows sampled:** `7,629` across 500 optimizer steps from `85,950` eligible rows (`feature_state_reset: before every waveform`).
  - `gold_test_read: false` (`SIH_GOLD_TEST` was not mounted, read, or trained on).
- **Optimizer Steps & Validation Curve:**
  - Loss objective: `complex_l1 + 0.25*magnitude_l1 + 0.01*SI-SDR_loss + 0.2*MR-STFT`.
  - Nonzero `sisdr_loss` logged throughout (`step=25`: `12.8156`, `step=250`: `16.6262`, `step=375`: `6.3639`, `step=500`: `14.8630`).
  - Synthetic validation loss improved monotonically every 25 steps from `1.448274` (step 25) to `1.329953` (step 500, `best_validation_loss = 1.3299525436013937`). Consequently `best.hk` is byte-identical to `step-500.hk`.
- **Retrieved Artifacts (`kaggle_output/dfn3_v8_sih26052/`):**
  - Run log: `kaggle_output/dfn3_v8_sih26052/deepfilternet3-v8-sih26052.log`
  - Training report: `kaggle_output/dfn3_v8_sih26052/dfn3_v8_sih26052/training_report.json`
  - Checkpoints (`step-{25..500}.{hk,pt}` every 25 steps and `best.{hk,pt}`) under `kaggle_output/dfn3_v8_sih26052/dfn3_v8_sih26052/`

## 2. Frozen Canonical Evaluation Protocol

- **Script:** `./pc_venv/bin/python ./antigravity/scripts/evaluate_dfn3_canonical.py`
- **Canonical Benchmark:** `590` clips (`antigravity/runs/sih26052_canonical_validation`), manifest SHA-256 `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`, fresh DeepFilterNet3 state per clip, default post-processing (`atten_lim_db = null`, `post_gain_db = 0.0`).
- **Strict Targets:** Output SNR > `15.0` dB, STOI > `0.85`, PESQ-WB > `2.5`, plus per-clip joint pass rate.
- **Checkpoint Loading & Runtime Caveat:** All 21 `.hk` files (`step-25..500.hk` and `best.hk`) passed strict loading via `hk.load_file` and `model.load_state_dict(..., strict=True)`. Local evaluation emitted the SciPy/NumPy compatibility warning (`NumPy 1.26.4`); all 590 clips completed cleanly across all 20 step checkpoints (`valid_counts = 590` for every metric).

## 3. Full-Set Canonical Results (`n = 590`)

| Model / Checkpoint | SHA-256 (prefix) | Output SNR | SI-SDR | STOI | PESQ-WB | All-three pass |
|---|---|---:|---:|---:|---:|---:|
| **Deployed Step-500 (baseline)** | `bc1fc9b76958` | **13.47 dB** | **12.36 dB** | **0.885** | **2.232** | **161/590 (27.3%)** |
| Pretrained DFN3 reference | `cc2bb32273b8` | 11.61 dB | 10.89 dB | 0.869 | 2.127 | 120/590 (20.3%) |
| V8 `step-25.hk` | `9170dddfda3a` | 12.21 dB | 10.90 dB | 0.863 | 2.116 | 136/590 (23.1%) |
| V8 `step-50.hk` | `92bb3bda4439` | 12.22 dB | 10.87 dB | 0.862 | 2.121 | 139/590 (23.6%) |
| V8 `step-75.hk` | `b5af7436992b` | 12.27 dB | 10.93 dB | 0.864 | 2.125 | 134/590 (22.7%) |
| V8 `step-100.hk` | `b4f65a6dcdae` | 12.38 dB | 11.00 dB | 0.864 | 2.138 | 141/590 (23.9%) |
| V8 `step-125.hk` | `f63cafd2de69` | 12.48 dB | 11.13 dB | 0.866 | 2.150 | 144/590 (24.4%) |
| V8 `step-150.hk` | `352673f2e673` | 12.50 dB | 11.17 dB | 0.866 | 2.153 | 145/590 (24.6%) |
| V8 `step-175.hk` | `444bb1874af4` | 12.54 dB | 11.19 dB | 0.867 | 2.153 | 145/590 (24.6%) |
| V8 `step-200.hk` | `c7c6fd84ec31` | 12.62 dB | 11.28 dB | 0.868 | 2.153 | 146/590 (24.7%) |
| **V8 `step-225.hk` (peak PESQ & joint pass)** | `7b950a3ee28b` | **12.67 dB** | **11.35 dB** | **0.869** | **2.154** | **148/590 (25.1%)** |
| V8 `step-250.hk` | `e14a25447a46` | 12.71 dB | 11.37 dB | 0.869 | 2.153 | 146/590 (24.7%) |
| V8 `step-275.hk` | `7d0eb8aaf6e9` | 12.74 dB | 11.38 dB | 0.870 | 2.147 | 141/590 (23.9%) |
| V8 `step-300.hk` | `31b378abe3e7` | 12.82 dB | 11.45 dB | 0.870 | 2.150 | 141/590 (23.9%) |
| V8 `step-325.hk` | `54fb88d07a92` | 12.82 dB | 11.44 dB | 0.871 | 2.142 | 136/590 (23.1%) |
| V8 `step-350.hk` | `56c537b7b91f` | 12.83 dB | 11.46 dB | 0.871 | 2.142 | 136/590 (23.1%) |
| V8 `step-375.hk` | `2d751a93bda1` | 12.85 dB | 11.49 dB | 0.872 | 2.138 | 136/590 (23.1%) |
| V8 `step-400.hk` | `b4eba49287cd` | 12.87 dB | 11.51 dB | 0.873 | 2.130 | 133/590 (22.5%) |
| V8 `step-425.hk` | `c840281ad5d9` | 12.90 dB | 11.55 dB | 0.874 | 2.130 | 130/590 (22.0%) |
| V8 `step-450.hk` | `d7d625b1a0a4` | 12.94 dB | 11.59 dB | 0.875 | 2.125 | 128/590 (21.7%) |
| **V8 `step-475.hk` (peak SNR/SI-SDR/STOI)** | `3ca25e3c62d6` | **12.98 dB** | **11.65 dB** | **0.876** | **2.127** | **132/590 (22.4%)** |
| **V8 `step-500.hk` / `best.hk`** | `0f4da0975b33` | **12.93 dB** | **11.59 dB** | **0.875** | **2.116** | **123/590 (20.8%)** |

Individual metric passes for key checkpoints:
- `step-225.hk`: SNR > 15 dB `211/590 (35.8%)`, STOI > 0.85 `420/590 (71.2%)`, PESQ-WB > 2.5 `187/590 (31.7%)`, all three `148/590 (25.1%)`.
- `step-475.hk`: SNR > 15 dB `215/590 (36.4%)`, STOI > 0.85 `433/590 (73.4%)`, PESQ-WB > 2.5 `171/590 (29.0%)`, all three `132/590 (22.4%)`.
- `step-500.hk`: SNR > 15 dB `209/590 (35.4%)`, STOI > 0.85 `433/590 (73.4%)`, PESQ-WB > 2.5 `164/590 (27.8%)`, all three `123/590 (20.8%)`.

## 4. Full SHA-256 Checksums of Retrieved V8 `.hk` Checkpoints

- `step-25.hk`: `9170dddfda3afb1c042b84251c4563499bf1475514d45ce4b47d5ff9d3cb90e0`
- `step-50.hk`: `92bb3bda443935d2aa54bb1c296fd36b6d484823f77c9636a8b34a5b869626e1`
- `step-75.hk`: `b5af7436992bd6a346a756df49286ab404ae6065e69208d988dc4e5f2489919c`
- `step-100.hk`: `b4f65a6dcdae1459865ffad2e099c8e50766d0f0251d9a50e966a578b9a17ee8`
- `step-125.hk`: `f63cafd2de6969bbe0fd09723cde66fa536a8c15ff199f06938743177e4e0a77`
- `step-150.hk`: `352673f2e673ff07d509e68eec7629566ed9046254f9a11533122a30c4ca1419`
- `step-175.hk`: `444bb1874af4b47ebed3e4b8bb4c800ab6218ab920325c08c41540be51cea13e`
- `step-200.hk`: `c7c6fd84ec318d4f430b64462a3a295d96fa8a6152fc8386183c949ed25bb0b9`
- `step-225.hk`: `7b950a3ee28bb884662b01231fbb06e12b471cd1e4c8299863a7d0f8f6b5a902` (`step-225.pt`: `b3f9472489acea804050a8d4e36f08fe4d4484b4052f3acc17feb3923e507725`)
- `step-250.hk`: `e14a25447a46b5ba368c48900405fd66b3d171136dd80a133b7293ba91cafe33`
- `step-275.hk`: `7d0eb8aaf6e90b86d6035bf8c81568347d941eaef7c2a42535fa14dec8c43749`
- `step-300.hk`: `31b378abe3e714977b2f9223cdcc039e946fb60a5b4878c8e1ce581120676541`
- `step-325.hk`: `54fb88d07a92eb440d5d4e6e845e453804e9eb2021f02a689a0a1cd27d854a1b`
- `step-350.hk`: `56c537b7b91f556072dc58a60bd69140bcf3cdf8a596db68f4c811041265ab00`
- `step-375.hk`: `2d751a93bda1c22dbe5997e223cc4daf8d64e7ce32d5266a0b28b277eec2d296`
- `step-400.hk`: `b4eba49287cdb50dea2ce40c73a2d43ea80b3d3d9d1da068daa23de21a14389b`
- `step-425.hk`: `c840281ad5d90b28ccda36369a24ad3916f48a1f9472dd98d1e36b21f37b0a5d`
- `step-450.hk`: `d7d625b1a0a47aeea35a8e8442f68f557dcf2c36d7f43306d18181f25f98f68c`
- `step-475.hk`: `3ca25e3c62d6e8d146a26983fc91e66158b6f75325d5a8f066becaed66748fe1` (`step-475.pt`: `ed20b1113b4d51c3473506802a10aa8b1266b80a108872f4f90f5278a675b683`)
- `step-500.hk` & `best.hk`: `0f4da0975b3391b2e4743d8cb71315c9402e34533e52d05afb7f639db22e17f8` (`step-500.pt`: `47ba1dcf333eb8a8d97b96c6016ce160be0dd5d55549cd5866f0a15ca590bbeb`, `best.pt`: `3ae7c5863dda8094fdee6ab88423ca802f4d712e7b58da37608ef250e92a4041`)

## 5. Paired Bootstrap Comparison (2,000 Resamples)

- **V8 `step-225.hk` (peak PESQ & joint pass) vs Deployed Step-500 (`paired_step225_vs_deployed_step500.json`):**
  - Output SNR: `-0.79 dB` (95% CI `[-0.93, -0.66]`), SI-SDR: `-1.01 dB` (`[-1.22, -0.82]`), STOI: `-0.015` (`[-0.018, -0.012]`), PESQ-WB: `-0.078` (`[-0.099, -0.057]`).
- **V8 `step-225.hk` vs Pretrained DFN3 (`paired_step225_vs_pretrained.json`):**
  - Output SNR: `+1.07 dB` (`[+0.89, +1.24]`), SI-SDR: `+0.46 dB` (`[+0.26, +0.67]`), STOI: `+0.001` (`[-0.002, +0.004]`), PESQ-WB: `+0.027` (`[+0.008, +0.048]`).
- **V8 `step-475.hk` (peak SNR/SI-SDR/STOI) vs Deployed Step-500 (`paired_step475_vs_deployed_step500.json`):**
  - Output SNR: `-0.49 dB` (`[-0.63, -0.34]`), SI-SDR: `-0.72 dB` (`[-0.91, -0.53]`), STOI: `-0.009` (`[-0.012, -0.006]`), PESQ-WB: `-0.105` (`[-0.128, -0.085]`).
- **V8 `step-475.hk` vs Pretrained DFN3 (`paired_step475_vs_pretrained.json`):**
  - Output SNR: `+1.38 dB` (`[+1.15, +1.59]`), SI-SDR: `+0.76 dB` (`[+0.52, +0.99]`), STOI: `+0.007` (`[+0.004, +0.010]`), PESQ-WB: `+0.000` (`[-0.026, +0.027]`).
- **V8 `step-500.hk` vs Deployed Step-500 (`paired_step500_vs_deployed_step500.json`):**
  - Output SNR: `-0.53 dB` (`[-0.68, -0.39]`), SI-SDR: `-0.77 dB` (`[-0.96, -0.58]`), STOI: `-0.009` (`[-0.012, -0.007]`), PESQ-WB: `-0.116` (`[-0.139, -0.095]`).
- **Measured `input_snr >= 9.6 dB` Subgroup (`n = 245`):**
  - `step-225.hk`: Output SNR `16.19 dB`, SI-SDR `15.58 dB`, STOI `0.935`, PESQ-WB `2.629`, all-three `124/245 (50.6%)`.
  - `step-475.hk`: Output SNR `16.49 dB`, SI-SDR `15.78 dB`, STOI `0.938`, PESQ-WB `2.584`, all-three `108/245 (44.1%)`.
  - `step-500.hk`: Output SNR `16.45 dB`, SI-SDR `15.73 dB`, STOI `0.937`, PESQ-WB `2.570`, all-three `103/245 (42.0%)`.
  - All trail Deployed Step-500 (`16.87 dB`, `0.942`, `2.722`, `132/245 = 53.9%`).

## 6. Key Findings & Next Step

1. **Extending `lr=1e-6` to 500 steps does not surpass Deployed Step-500:** Even at its highest SNR (`step-475.hk`: `12.98 dB`), V8 still trails Deployed Step-500 (`-0.49 dB` SNR, `-0.72 dB` SI-SDR, `-0.009` STOI, `-0.105` PESQ-WB, paired 95% CIs below zero).
2. **Split peak and perceptual turnover after step 225:** While SNR, SI-SDR, and STOI continued rising through step 475 (`12.98 dB` / `11.65 dB` / `0.876`) and dipped slightly at step 500 (`12.93 dB` / `11.59 dB` / `0.875`), **PESQ-WB (`2.154`) and joint pass rate (`148/590 = 25.1%`) peaked at step 225** and declined monotonically afterward—dropping below Pretrained DFN3 (`2.127`) by steps 450–500 (`2.125 -> 2.116`) even though synthetic validation loss fell continuously to `1.3300`.
3. **Implication:** Further horizon extension of this same objective/augmentation mix is not sufficient. Next controlled single-variable ablations per `runs/sih26052_research_and_v6_plan.md` should target the data/loss mismatch itself: first removing mixture-only clipping augmentation, then testing continuous SNR with sequence-level loss normalization.

