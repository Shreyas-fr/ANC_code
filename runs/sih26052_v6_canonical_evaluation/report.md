# SIH 26052 DeepFilterNet3 V6 Canonical Evaluation Report

**Decision:** Do **not** deploy any V6 checkpoint. Keep the existing **Deployed Step-500** model as the active deployment candidate.

## 1. Training Run Evidence

- **Kaggle Kernel:** `shreyasdivekar/deepfilternet3-v6-sih26052` (Notebook source: `antigravity/notebooks/v6/deepfilternet3_v6_sih26052.ipynb`)
- **Controlled Experiment Change:** Preserves V5's source-group exclusions, target-aligned RIR policy, loss objective, augmentations, model initialization, optimizer (`AdamW`, `lr=1e-5`), and train/val sizes, while fixing the V4/V5 speech-row sampler (`self.speech[i % len(self.speech)]`) to sample randomly from all eligible training speech rows on every access, with checkpoints every 250 steps through step 1,500.
- **Hardware & Runtime:** Dual Tesla T4 (`GPU: Tesla T4 | count: 2`), PyTorch `2.11.0+cu130`, `deepfilterlib 0.5.6`, upstream DeepFilterNet3 (`48000 Hz`, `2,135,484` parameters).
- **Attached Datasets, Schema & Leakage Controls:**
  - `shreyasdivekar/anc-sih-training-data`
  - `panavpayappagoudar/sih-26-processed-audio` (`metadata.csv` verified with required schema columns `['audio_class', 'dataset_source', 'internal_path']`)
  - `shreyasdivekar/sih26052-canonical-exclusions` (`canonical_exclusions.csv`: `3,686` rows loaded, `333` matching rows removed; `121,991` remaining metadata rows)
  - Source-group SHA-256 90/10 split: `{'drone': (246, 27), 'environment': (22455, 2495), 'gunfire': (1305, 145), 'speech': (85950, 7368), 'vehicle': (1800, 200)}`
  - Train mixtures = `7,200`; fixed validation mixtures = `512` (`Validation identity check: True`; determinism verified across `[0, 1, 42, 100]`; train preflight verified 40 consecutive finite samples).
  - **Distinct training speech rows sampled:** `20,961` across 1,500 optimizer steps (`batch_size=16`, 24,000 draws out of 85,950 eligible rows), confirming full-pool coverage compared to V4/V5's 7,200-row cap.
  - `gold_test_read: false` (`SIH_GOLD_TEST` was not mounted, read, or trained on).
- **Optimizer Steps & Validation Curve:**
  - Loss objective: `complex_l1 + 0.25*magnitude_l1 + 0.01*SI-SDR_loss + 0.2*MR-STFT`.
  - Nonzero `sisdr_loss` logged throughout training (`step=25`: `11.1747`, `step=250`: `9.3989`, `step=500`: `5.6811`, `step=1000`: `3.7836`, `step=1500`: `-2.6290`).
  - Synthetic validation loss decreased monotonically: `250: 1.214091`, `500: 1.150399`, `750: 1.135196`, `1000: 1.118661`, `1250: 1.110985`, `1500: 1.106590` (`best_validation_loss = 1.1065895035862923`). Consequently `best.hk` is byte-identical to `step-1500.hk`.
- **Retrieved Artifacts (`kaggle_output/dfn3_v6_sih26052/`):**
  - Run log: `kaggle_output/dfn3_v6_sih26052/deepfilternet3-v6-sih26052.log`
  - Training report: `kaggle_output/dfn3_v6_sih26052/dfn3_v6_sih26052/training_report.json`
  - Checkpoints (`step-{250,500,750,1000,1250,1500}.{hk,pt}` and `best.{hk,pt}`) under `kaggle_output/dfn3_v6_sih26052/dfn3_v6_sih26052/`

## 2. Frozen Canonical Evaluation Protocol

- **Script:** `./pc_venv/bin/python ./antigravity/scripts/evaluate_dfn3_canonical.py`
- **Canonical Benchmark:** `590` clips (`antigravity/runs/sih26052_canonical_validation`), manifest SHA-256 `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`, fresh DeepFilterNet3 state per clip, default post-processing (`atten_lim_db = null`, `post_gain_db = 0.0`).
- **Strict Targets:** Output SNR > `15.0` dB, STOI > `0.85`, PESQ-WB > `2.5`, plus per-clip joint pass rate.
- **Checkpoint Loading & Runtime Caveat:** Every `.hk` checkpoint loaded strictly via `hk.load_file`. Local evaluation emitted the SciPy/NumPy compatibility warning (`NumPy 1.26.4`); all 590 clips completed and wrote outputs for all 6 checkpoints.

## 3. Full-Set Canonical Results (`n = 590`)

| Model / Checkpoint | Checkpoint SHA-256 (prefix) | Output SNR | SI-SDR | STOI | PESQ-WB | All-three pass |
|---|---|---:|---:|---:|---:|---:|
| **Deployed Step-500 (baseline)** | `bc1fc9b76958` | **13.47 dB** | **12.36 dB** | **0.885** | **2.232** | **161/590 (27.3%)** |
| Pretrained DFN3 reference | `cc2bb32273b8` | 11.61 dB | 10.89 dB | 0.869 | 2.127 | 120/590 (20.3%) |
| V5 best (`step-500.hk`) | `0a23fbf24c7e` | 11.53 dB | 9.88 dB | 0.867 | 1.788 | 48/590 (8.1%) |
| **V6 `step-250.hk` (best V6 checkpoint)** | `8d7d8ca8f2ca` | **9.34 dB** | **7.78 dB** | **0.848** | **1.706** | **42/590 (7.1%)** |
| V6 `step-500.hk` | `d2d3aa16a816` | 7.04 dB | 5.72 dB | 0.825 | 1.608 | 36/590 (6.1%) |
| V6 `step-750.hk` | `bfa75094671e` | 6.91 dB | 5.63 dB | 0.823 | 1.605 | 33/590 (5.6%) |
| V6 `step-1000.hk` | `6d0f18bac27c` | 6.84 dB | 5.59 dB | 0.823 | 1.603 | 33/590 (5.6%) |
| V6 `step-1250.hk` | `f99052e208f8` | 6.77 dB | 5.55 dB | 0.823 | 1.601 | 31/590 (5.3%) |
| V6 `step-1500.hk` / `best.hk` | `13fc6e0a3af2` | 6.71 dB | 5.52 dB | 0.822 | 1.599 | 28/590 (4.7%) |

Individual metric pass counts for V6 `step-250.hk`: SNR > 15 dB `135/590 (22.9%)`, STOI > 0.85 `356/590 (60.3%)`, PESQ-WB > 2.5 `66/590 (11.2%)`, all three `42/590 (7.1%)`.

## 4. Full SHA-256 Checksums of Retrieved V6 Checkpoints

- `step-250.hk`: `8d7d8ca8f2caa29e01e31d524401fccf25c1b91edb3b315e1db81dc9dfabcd07` (`step-250.pt`: `041cb60ebe046ae6170e9b79f18ef6cb921990a99c5052aae12f31fc4e752017`)
- `step-500.hk`: `d2d3aa16a81696d9197f2ff82a92e08ee1aebe0ea2c86094ad6c47220d19cc3c` (`step-500.pt`: `1322f3e1704fe162cdc120f17479f0d1dd15647015118012d1fe35190a771633`)
- `step-750.hk`: `bfa75094671e0635afaaaf22dadc44587324e58df9fe2db74414aa2f015ee554` (`step-750.pt`: `8d7dacc07084554f6f819c5e3e1f756e2947ff6595bf35dcc96027946e09dfab`)
- `step-1000.hk`: `6d0f18bac27c28243ebb22bbc34e18ec0adc89316314cb5bfecbbdb695d642c3` (`step-1000.pt`: `eea64fa6f87bb7ef1485ec98bebc66295ceda27ca1b0d4b7e89e1d1cf8789bbe`)
- `step-1250.hk`: `f99052e208f8c6ee4a91b77a19c8b27fa93fa951c305f8f059eec908303e2758` (`step-1250.pt`: `801c17e302a997397ebb399790f6dcfb512b90441d582ee33d6959f14e349636`)
- `step-1500.hk` & `best.hk`: `13fc6e0a3af2d01f88f624e155fb34cb0e657b5f4059f5511d20dbd253f9ab29` (`step-1500.pt`: `19889f7da7964431856f24784300d13cbd841ba6567180b250948057a042b455`, `best.pt`: `68747a64b955d6d10b70ba71cb643737a3221d7cbca35dc6b48f71aa67153142`)

## 5. Paired Bootstrap Comparison (2,000 resamples)

- **V6 `step-250.hk` vs Deployed Step-500 (`paired_step250_vs_deployed_step500.json`):**
  - Output SNR: `-4.13 dB` (95% CI `[-4.56, -3.68]`)
  - SI-SDR: `-4.58 dB` (95% CI `[-5.04, -4.11]`)
  - STOI: `-0.036` (95% CI `[-0.041, -0.032]`)
  - PESQ-WB: `-0.526` (95% CI `[-0.570, -0.484]`)
- **V6 `step-250.hk` vs Pretrained DFN3 (`paired_step250_vs_pretrained.json`):**
  - Output SNR: `-2.27 dB` (95% CI `[-2.76, -1.78]`)
  - SI-SDR: `-3.11 dB` (95% CI `[-3.61, -2.60]`)
  - STOI: `-0.020` (95% CI `[-0.025, -0.015]`)
  - PESQ-WB: `-0.421` (95% CI `[-0.470, -0.369]`)
- **V6 `step-500.hk` vs Deployed Step-500 (`paired_step500_vs_deployed_step500.json`):**
  - Output SNR: `-6.43 dB` (95% CI `[-6.90, -5.95]`)
  - SI-SDR: `-6.65 dB` (95% CI `[-7.14, -6.16]`)
  - STOI: `-0.060` (95% CI `[-0.065, -0.054]`)
  - PESQ-WB: `-0.624` (95% CI `[-0.670, -0.581]`)
- **Measured `input_snr >= 9.6 dB` Subgroup (`n = 245`) for V6 `step-250.hk`:**
  - Mean Output SNR `15.10 dB`, SI-SDR `14.02 dB`, STOI `0.923`, PESQ-WB `2.134`, all-three pass `41/245 (16.7%)` — below Deployed Step-500 (`16.87 dB`, `0.942`, `2.722`, `132/245 = 53.9%`).

## 6. Key Findings & Next Ablations

1. **Full speech pool coverage did not resolve the regression:** V6 sampled `20,961` distinct training speech rows, yet canonical metrics still regressed rapidly before step 250 (`9.34 dB` SNR, `1.706` PESQ-WB) and fell monotonically through step 1,500 (`6.71 dB` SNR, `1.599` PESQ-WB) while synthetic validation loss fell (`1.2141 -> 1.1066`).
2. **Proceeding along `sih26052_research_and_v6_plan.md`:** Isolate the remaining factors one at a time in controlled ablations:
   - Lower-LR conservative fine-tuning (`1e-6` or selective layer freezing) with early checkpoints.
   - Removing unaligned mixture-only clipping augmentation (15% peak clipping without clipping the target).
   - Continuous SNR sampling paired with sequence-level loss normalization.
3. **Output Locations:** Full per-clip CSVs and summary JSONs are stored in `kaggle_output/dfn3_v6_sih26052/canonical_eval_step{250,500,750,1000,1250,1500}/`, and paired bootstrap JSONs in `antigravity/runs/sih26052_v6_canonical_evaluation/`.

