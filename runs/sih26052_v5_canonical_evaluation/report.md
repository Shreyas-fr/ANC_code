# SIH 26052 DeepFilterNet3 V5 Canonical Evaluation Report

**Decision:** Do **not** deploy any V5 checkpoint. Keep the existing **Deployed Step-500** model as the active deployment candidate.

## 1. Training Run Evidence

- **Kaggle Kernel:** `shreyasdivekar/deepfilternet3-v5-sih26052` (Notebook source: `antigravity/notebooks/v5/deepfilternet3_v5_sih26052.ipynb`)
- **Hardware & Runtime:** Dual Tesla T4 (`GPU: Tesla T4 | count: 2`), PyTorch `2.11.0+cu130`, `deepfilterlib 0.5.6`, upstream DeepFilterNet3 (`48000 Hz`, `2,135,484` parameters).
- **Attached Datasets & Leakage Controls:**
  - `shreyasdivekar/anc-sih-training-data`
  - `panavpayappagoudar/sih-26-processed-audio` (`metadata.csv` verified with required schema columns `['audio_class', 'dataset_source', 'internal_path']`)
  - `shreyasdivekar/sih26052-canonical-exclusions` (`canonical_exclusions.csv`: `3,686` rows loaded, `333` matching rows removed; `121,991` remaining metadata rows)
  - Source-group SHA-256 90/10 split: `{'drone': (246, 27), 'environment': (22455, 2495), 'gunfire': (1305, 145), 'speech': (85950, 7368), 'vehicle': (1800, 200)}`
  - Train mixtures = `7,200`; fixed validation mixtures = `512` (`Validation identity check: True`; determinism verified across `[0, 1, 42, 100]`; train preflight verified 40 consecutive finite samples).
  - Target-aligned RIR augmentation (`synthetic_rir_probability = 0.2`, `microphone_clipping_probability = 0.15`): `"target includes the same reverberant speech used in the noisy mixture"`.
  - Feature normalization state reset before every waveform.
  - `gold_test_read: false` (no `SIH_GOLD_TEST` data mounted, read, or trained on).
- **Optimizer Steps & Validation Curve:**
  - Loss objective: `complex_l1 + 0.25*magnitude_l1 + 0.01*SI-SDR_loss + 0.2*MR-STFT`.
  - Nonzero `sisdr_loss` logged throughout training (e.g., step 25: `5.9176`, step 500: `9.3923`, step 1500: `2.3255`, step 3000: `1.8096`).
  - Synthetic validation loss decreased monotonically: `500: 1.196669`, `1000: 1.155869`, `1500: 1.136842`, `2000: 1.123326`, `2500: 1.112464`, `3000: 1.103654` (`best_validation_loss = 1.1036544721573591`). Consequently `best.hk` is byte-identical to `step-3000.hk`.
- **Retrieved Artifacts (`kaggle_output/dfn3_v5_sih26052/`):**
  - Run log: `kaggle_output/dfn3_v5_sih26052/deepfilternet3-v5-sih26052.log`
  - Training report: `kaggle_output/dfn3_v5_sih26052/dfn3_v5_sih26052/training_report.json`
  - Checkpoints (`step-{500..3000}.{hk,pt}` and `best.{hk,pt}`) under `kaggle_output/dfn3_v5_sih26052/dfn3_v5_sih26052/`

## 2. Frozen Canonical Evaluation Protocol

- **Script:** `./pc_venv/bin/python ./antigravity/scripts/evaluate_dfn3_canonical.py`
- **Canonical Benchmark:** `590` clips (`antigravity/runs/sih26052_canonical_validation`), manifest SHA-256 `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`, fresh DeepFilterNet3 state per clip, default post-processing (`atten_lim_db = null`, `post_gain_db = 0.0`).
- **Strict Targets:** Output SNR > `15.0` dB, STOI > `0.85`, PESQ-WB > `2.5`, plus per-clip joint pass rate (all three simultaneously).
- **Checkpoint Loading & Runtime Caveat:** Every `.hk` checkpoint loaded strictly via `hk.load_file` prior to evaluation. Local evaluation emitted the SciPy/NumPy compatibility warning (`NumPy 1.26.4`); all 590 clips completed and wrote outputs for all 6 checkpoints.

## 3. Full-Set Canonical Results (`n = 590`)

| Model / Checkpoint | Checkpoint SHA-256 (prefix) | Output SNR | SI-SDR | STOI | PESQ-WB | All-three pass |
|---|---|---:|---:|---:|---:|---:|
| **Deployed Step-500 (reference baseline)** | `bc1fc9b76958` | **13.47 dB** | **12.36 dB** | **0.885** | **2.232** | **161/590 (27.3%)** |
| Pretrained DFN3 reference | `—` | 11.61 dB | 10.89 dB | 0.869 | 2.127 | 120/590 (20.3%) |
| V4 best (`step-500.hk`) | `—` | 11.42 dB | 9.67 dB | 0.863 | 1.739 | 41/590 (6.9%) |
| **V5 `step-500.hk` (best V5 checkpoint)** | `0a23fbf24c7e` | **11.53 dB** | **9.88 dB** | **0.867** | **1.788** | **48/590 (8.1%)** |
| V5 `step-1000.hk` | `08877afa2680` | 10.25 dB | 8.41 dB | 0.851 | 1.647 | 36/590 (6.1%) |
| V5 `step-1500.hk` | `e9ecd650445c` | 7.45 dB | 6.02 dB | 0.826 | 1.595 | 25/590 (4.2%) |
| V5 `step-2000.hk` | `6e8be13f4e72` | 6.52 dB | 5.41 dB | 0.822 | 1.592 | 23/590 (3.9%) |
| V5 `step-2500.hk` | `f6198cac56c1` | 6.34 dB | 5.30 dB | 0.821 | 1.583 | 23/590 (3.9%) |
| V5 `step-3000.hk` / `best.hk` | `c041efd5ec53` | 6.19 dB | 5.22 dB | 0.820 | 1.574 | 22/590 (3.7%) |

Individual metric pass counts for V5 `step-500.hk`: SNR > 15 dB `172/590 (29.2%)`, STOI > 0.85 `409/590 (69.3%)`, PESQ-WB > 2.5 `71/590 (12.0%)`, all three `48/590 (8.1%)`.

## 4. Full SHA-256 Checksums of Retrieved V5 Checkpoints

- `step-500.hk`: `0a23fbf24c7e85b3ec95baa609981142e15e94418f83d64877da9304892e37e1` (`step-500.pt`: `92936b020ac70333a77ed984fd23c3c61ede79bf051293fef8bad90a5050e642`)
- `step-1000.hk`: `08877afa26802b452cd59415672a67aa51074504bb0c864fc5fe3ac9a2e569b2` (`step-1000.pt`: `e79c7ab22d14718757dc2187511433225ed2fef615d85f127f0e54bd961381be`)
- `step-1500.hk`: `e9ecd650445c3b2e9e2f6c262a1e1c1b69a3c61cc4bdee60c16db519feb55001` (`step-1500.pt`: `40b3503d2fa7763a3f4aabbf317697b651a8218d3db9abac1fab70031bf8342c`)
- `step-2000.hk`: `6e8be13f4e72aac0dc9549097e0c78713cda3fcb1cf9f42a9ffbfcc05126ceb1` (`step-2000.pt`: `34a486c0cabf49d56ac662704465c95fb6d7bdaebf4daf9dec4d86798e889065`)
- `step-2500.hk`: `f6198cac56c1140fc11fb7c3a0ce97b5c71710300ce0803f3d0ac5007551983e` (`step-2500.pt`: `d593bc2e5e7833a04f0c1beacc0002c485c3c642c397c4ecb110106d026b3f1d`)
- `step-3000.hk` & `best.hk`: `c041efd5ec53911c04fb979267a108fb72811f30ecab68b51ce11df4e2c2c2ea` (`step-3000.pt`: `a9798170571d9bfe9efcdbe5910539754db73ea1403f336946319f510dc6b1d6`, `best.pt`: `7cfd0b295a203a20e852da113e3661cceecd937f1fb1254959845046a973b`)

## 5. Paired Bootstrap Comparison (V5 `step-500.hk`, 2,000 resamples)

- **vs Pretrained DFN3 (`antigravity/runs/sih26052_v5_canonical_evaluation/paired_vs_pretrained.json`):**
  - Output SNR: `-0.08 dB` (95% CI `[-0.43, +0.25]`)
  - SI-SDR: `-1.01 dB` (95% CI `[-1.40, -0.64]`)
  - STOI: `-0.002` (95% CI `[-0.006, +0.003]`)
  - PESQ-WB: `-0.339` (95% CI `[-0.382, -0.295]`)
- **vs Deployed Step-500 (`antigravity/runs/sih26052_v5_canonical_evaluation/paired_vs_deployed_step500.json`):**
  - Output SNR: `-1.94 dB` (95% CI `[-2.21, -1.68]`)
  - SI-SDR: `-2.48 dB` (95% CI `[-2.84, -2.16]`)
  - STOI: `-0.018` (95% CI `[-0.021, -0.014]`)
  - PESQ-WB: `-0.444` (95% CI `[-0.482, -0.407]`)
- **Measured `input_snr >= 9.6 dB` Subgroup (`n = 245`):**
  - Mean Output SNR `15.54 dB`, SI-SDR `14.65 dB`, STOI `0.932`, PESQ-WB `2.188`, all-three pass `48/245 (19.6%)` — substantially below Deployed Step-500 (`16.87 dB` SNR, `0.942` STOI, `2.722` PESQ-WB, `132/245 = 53.9%`).

## 6. Key Findings & Limitations

1. **Target-aligned RIR gave only a marginal gain at step 500:** Relative to V4 `step-500.hk`, V5 `step-500.hk` improved by `+0.11 dB` SNR, `+0.21 dB` SI-SDR, `+0.004` STOI, `+0.049` PESQ-WB, and `48/590` vs `41/590` joint pass. That confirms dry-vs-reverberant target mismatch in the 20% RIR branch was a minor factor rather than the primary cause of V4's canonical regression.
2. **Severe train/val vs canonical benchmark divergence remains:** V5 validation loss decreased monotonically from `1.1967` (step 500) to `1.1037` (step 3000), while canonical SNR dropped monotonically from `11.53 dB` to `6.19 dB` and PESQ-WB dropped from `1.788` to `1.574`. As training progressed, `best.hk` (step 3000) became the worst checkpoint on real canonical mixtures.
3. **Output Locations:** Full per-clip CSVs and summary JSONs are stored in `kaggle_output/dfn3_v5_sih26052/canonical_eval_step{500,1000,1500,2000,2500,3000}/`, and paired bootstrap JSONs in `antigravity/runs/sih26052_v5_canonical_evaluation/`.
