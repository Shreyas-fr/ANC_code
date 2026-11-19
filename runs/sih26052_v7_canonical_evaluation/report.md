# SIH 26052 DeepFilterNet3 V7 Canonical Evaluation Report

**Decision:** Do **not** deploy any V7 checkpoint. Keep the existing **Deployed Step-500** model as the active deployment candidate, and stop V7 at step 250 as instructed (`ANTIGRAVITY_RUN_PROMPT.md`).

## 1. Training Run Evidence

- **Kaggle Kernel:** `shreyasdivekar/deepfilternet3-v7-sih26052` (Notebook source: `antigravity/notebooks/v7/deepfilternet3_v7_sih26052.ipynb`, metadata: `antigravity/notebooks/v7/kernel-metadata.json` with `title` aligned to `"DeepFilterNet3 V7 SIH26052"` so Kaggle resolved the exact slug)
- **Controlled Experiment Change:** Preserves V6's full-pool random speech-row sampler, canonical exclusions, source-group splits, V5 target-aligned RIR policy, clipping augmentation, loss objective, and initialization, changing **only** AdamW learning rate from `1e-5` to `1e-6` and saving checkpoints every 25 steps through step 250.
- **Hardware & Runtime:** Dual Tesla T4 (`GPU: Tesla T4 | count: 2`), PyTorch `2.11.0+cu130`, `deepfilterlib 0.5.6`, upstream DeepFilterNet3 (`48000 Hz`, `2,135,484` parameters).
- **Attached Datasets, Schema & Leakage Controls:**
  - `shreyasdivekar/anc-sih-training-data`
  - `panavpayappagoudar/sih-26-processed-audio` (`metadata.csv` verified with required schema columns `['audio_class', 'dataset_source', 'internal_path']`)
  - `shreyasdivekar/sih26052-canonical-exclusions` (`canonical_exclusions.csv`: `3,686` rows loaded, `333` matching rows removed; `121,991` remaining metadata rows)
  - Source-group SHA-256 90/10 split: `{'drone': (246, 27), 'environment': (22455, 2495), 'gunfire': (1305, 145), 'speech': (85950, 7368), 'vehicle': (1800, 200)}`
  - Train mixtures = `7,200`; fixed validation mixtures = `512` (`Validation identity check: True`; determinism verified across `[0, 1, 42, 100]`; train preflight verified 40 consecutive finite samples).
  - **Distinct training speech rows sampled:** `3,896` across 250 optimizer steps (`batch_size=16`, 4,000 draws from 85,950 eligible rows).
  - `gold_test_read: false` (`SIH_GOLD_TEST` was not mounted, read, or trained on).
- **Optimizer Steps & Validation Curve:**
  - Loss objective: `complex_l1 + 0.25*magnitude_l1 + 0.01*SI-SDR_loss + 0.2*MR-STFT`.
  - Nonzero `sisdr_loss` logged throughout training (`step=25`: `12.8181`, `step=100`: `21.4972`, `step=175`: `10.6562`, `step=250`: `16.7211`).
  - Synthetic validation loss improved monotonically every 25 steps:
    `25: 1.448337`, `50: 1.443309`, `75: 1.436396`, `100: 1.422536`, `125: 1.413297`, `150: 1.402466`, `175: 1.394883`, `200: 1.387854`, `225: 1.381151`, `250: 1.373552` (`best_validation_loss = 1.3735516462475061`). Consequently `best.hk` is byte-identical to `step-250.hk`.
- **Retrieved Artifacts (`kaggle_output/dfn3_v7_sih26052/`):**
  - Run log: `kaggle_output/dfn3_v7_sih26052/deepfilternet3-v7-sih26052.log`
  - Training report: `kaggle_output/dfn3_v7_sih26052/dfn3_v7_sih26052/training_report.json`
  - Checkpoints (`step-{25,50,75,100,125,150,175,200,225,250}.{hk,pt}` and `best.{hk,pt}`) under `kaggle_output/dfn3_v7_sih26052/dfn3_v7_sih26052/`

## 2. Frozen Canonical Evaluation Protocol

- **Script:** `./pc_venv/bin/python ./antigravity/scripts/evaluate_dfn3_canonical.py`
- **Canonical Benchmark:** `590` clips (`antigravity/runs/sih26052_canonical_validation`), manifest SHA-256 `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`, fresh DeepFilterNet3 state per clip, default post-processing (`atten_lim_db = null`, `post_gain_db = 0.0`).
- **Strict Targets:** Output SNR > `15.0` dB, STOI > `0.85`, PESQ-WB > `2.5`, plus per-clip joint pass rate.
- **Checkpoint Loading & Runtime Caveat:** All 11 `.hk` checkpoints (`step-25..250.hk` and `best.hk`) loaded strictly via `hk.load_file`. Local evaluation emitted the SciPy/NumPy compatibility warning (`NumPy 1.26.4`); all 590 clips completed and wrote outputs for all 10 step checkpoints.

## 3. Full-Set Canonical Results (`n = 590`)

| Model / Checkpoint | Checkpoint SHA-256 (prefix) | Output SNR | SI-SDR | STOI | PESQ-WB | All-three pass |
|---|---|---:|---:|---:|---:|---:|
| **Deployed Step-500 (baseline)** | `bc1fc9b76958` | **13.47 dB** | **12.36 dB** | **0.885** | **2.232** | **161/590 (27.3%)** |
| Pretrained DFN3 reference | `cc2bb32273b8` | 11.61 dB | 10.89 dB | 0.869 | 2.127 | 120/590 (20.3%) |
| V6 best (`step-250.hk`, `lr=1e-5`) | `8d7d8ca8f2ca` | 9.34 dB | 7.78 dB | 0.848 | 1.706 | 42/590 (7.1%) |
| V7 `step-25.hk` | `99896fc9364b` | 12.21 dB | 10.90 dB | 0.863 | 2.117 | 135/590 (22.9%) |
| V7 `step-50.hk` | `813321e9508f` | 12.22 dB | 10.87 dB | 0.862 | 2.121 | 139/590 (23.6%) |
| V7 `step-75.hk` | `3d7b77991b87` | 12.27 dB | 10.93 dB | 0.864 | 2.126 | 134/590 (22.7%) |
| V7 `step-100.hk` | `cc380ab5654e` | 12.38 dB | 10.99 dB | 0.864 | 2.138 | 141/590 (23.9%) |
| V7 `step-125.hk` | `c86fef93c3e3` | 12.47 dB | 11.13 dB | 0.866 | 2.149 | 144/590 (24.4%) |
| V7 `step-150.hk` | `1296c5d3d58a` | 12.50 dB | 11.16 dB | 0.866 | 2.153 | 146/590 (24.7%) |
| V7 `step-175.hk` | `39359f8cbc0f` | 12.54 dB | 11.19 dB | 0.867 | 2.152 | 145/590 (24.6%) |
| V7 `step-200.hk` | `7c23d7034670` | 12.62 dB | 11.28 dB | 0.868 | 2.157 | 146/590 (24.7%) |
| V7 `step-225.hk` | `1c53c1fd6db2` | 12.68 dB | 11.36 dB | 0.869 | 2.154 | 148/590 (25.1%) |
| **V7 `step-250.hk` / `best.hk`** | `c2aec8f11aa4` | **12.71 dB** | **11.37 dB** | **0.869** | **2.154** | **147/590 (24.9%)** |

Individual metric pass counts for V7 `step-250.hk`: SNR > 15 dB `212/590 (35.9%)`, STOI > 0.85 `422/590 (71.5%)`, PESQ-WB > 2.5 `188/590 (31.9%)`, all three `147/590 (24.9%)`.

## 4. Full SHA-256 Checksums of Retrieved V7 Checkpoints

- `step-25.hk`: `99896fc9364b4ec99583d3c2436b06634b895d737d98c003d627eb6a65a3081f` (`step-25.pt`: `8ce9914c0db5bbd8cd202c9e0531c1d210f40c0285d8d9e7b02b8bb26c92f6e3`)
- `step-50.hk`: `813321e9508fcff390e4c8e2af83ab26bcab1a0cd96d75f91921e2d01462c700` (`step-50.pt`: `1c5adc4ccaa830a316ccafedb1bea9f195578eefdef86a02757c3107ffad42cf`)
- `step-75.hk`: `3d7b77991b8774c5a680d396bb1039900b6d5b403e176365f28210b965d6afeb` (`step-75.pt`: `9d6cc29cd19fbf38741d65a3d36ee9b99865a051ff84301ffbdb2a976eabb974`)
- `step-100.hk`: `cc380ab5654e329918b9e85946ea3a8edcd65399d15a9a753646fd24d2875afb` (`step-100.pt`: `d7f610760cbd49a60ab6eba1f52d349e9972910cfa67cd65e088d406eddc783b`)
- `step-125.hk`: `c86fef93c3e3b823fd004682c2da0e17279d0c3bec5079d60ba505e5910f5262` (`step-125.pt`: `07bc68fe1b544ecf810eba15cecdc535a2f875abc7f2174b6d9f16ccb3ede25a`)
- `step-150.hk`: `1296c5d3d58aeda7427e707b7bfe65ded6c4596a0e2cfacd6ad85b0b0ccef08b` (`step-150.pt`: `759f6ba2cc08010b827d765f91ebb856277aabe6fa14a75928b8dfb78afcb35f`)
- `step-175.hk`: `39359f8cbc0f16e029656d9bf25a6e74295aab8a4f8ddf0b3d69d4676d64e252` (`step-175.pt`: `17a3bcab7f90b38c6143a78e8cca1de67463ddc7e7af58e7ece4cc0f4e65739d`)
- `step-200.hk`: `7c23d70346702c4b4c08d1528ab02812a07df5f32751ec7c71375f6d1e9f9029` (`step-200.pt`: `84e2fe457f8b79d79010af699b6df6c0daa26cf4bfbb00ef0b8dab0f00b8bc47`)
- `step-225.hk`: `1c53c1fd6db2482fac8af88806401b15276e9f7bf7432b0d3a9405c7aea84b72` (`step-225.pt`: `72c383278b6d73c6cf9d6b215d85c28491f463b40e0916d0515a983a7ed0ab70`)
- `step-250.hk` & `best.hk`: `c2aec8f11aa488be94ec7d9347ae86c58c51f4db0213b1a3d8a8f8657d9fa4ba` (`step-250.pt`: `b898bfc15fdf7e888c0dc0585b239b2ebfae73edb94411c8ca2aba8a9920cb02`, `best.pt`: `7da5553adb10104b77687ddf400f74f6231a678104ec48514b07bc1062b51724`)

## 5. Paired Bootstrap Comparison (2,000 resamples)

- **V7 `step-250.hk` vs Deployed Step-500 (`paired_step250_vs_deployed_step500.json`):**
  - Output SNR: `-0.75 dB` (95% CI `[-0.89, -0.62]`)
  - SI-SDR: `-0.99 dB` (95% CI `[-1.20, -0.80]`)
  - STOI: `-0.015` (95% CI `[-0.019, -0.012]`)
  - PESQ-WB: `-0.079` (95% CI `[-0.101, -0.057]`)
- **V7 `step-250.hk` vs Pretrained DFN3 (`paired_step250_vs_pretrained.json`):**
  - Output SNR: `+1.11 dB` (95% CI `[+0.92, +1.29]`)
  - SI-SDR: `+0.48 dB` (95% CI `[+0.27, +0.69]`)
  - STOI: `+0.001` (95% CI `[-0.002, +0.004]`)
  - PESQ-WB: `+0.026` (95% CI `[+0.006, +0.047]`)
- **V7 `step-225.hk` vs Deployed Step-500 (`paired_step225_vs_deployed_step500.json`):**
  - Output SNR: `-0.79 dB` (95% CI `[-0.92, -0.66]`), SI-SDR: `-1.01 dB` (`[-1.21, -0.81]`), STOI: `-0.015` (`[-0.018, -0.012]`), PESQ-WB: `-0.078` (`[-0.099, -0.057]`).
- **Measured `input_snr >= 9.6 dB` Subgroup (`n = 245`) for V7 `step-250.hk`:**
  - Mean Output SNR `16.26 dB`, SI-SDR `15.62 dB`, STOI `0.935`, PESQ-WB `2.624`, all-three pass `123/245 (50.2%)` — still below Deployed Step-500 (`16.87 dB`, `0.942`, `2.722`, `132/245 = 53.9%`).

## 6. Key Findings & Limitations

1. **Learning rate `1e-5` caused the V4–V6 catastrophic regression:** Holding V6's sampler, data, loss, and augmentations constant while changing only AdamW LR from `1e-5` to `1e-6` eliminated early regression: canonical quality climbed steadily from step 25 (`12.21 dB` SNR, `2.117` PESQ-WB) to step 250 (`12.71 dB` SNR, `2.154` PESQ-WB, `147/590` joint pass), outperforming Pretrained DFN3 by `+1.11 dB` SNR and `+0.026` PESQ-WB (CIs above zero).
2. **Still trails Deployed Step-500:** At step 250, V7 still trails Deployed Step-500 on all four canonical metrics (`-0.75 dB` SNR, `-0.99 dB` SI-SDR, `-0.015` STOI, `-0.079` PESQ-WB, `147/590` vs `161/590`). Per run instructions, V7 is stopped rather than extended automatically, and Deployed Step-500 remains active.
3. **Output Locations:** Full per-clip CSVs and summary JSONs are in `kaggle_output/dfn3_v7_sih26052/canonical_eval_step{25..250}/`, and paired bootstrap JSONs are in `antigravity/runs/sih26052_v7_canonical_evaluation/`.

