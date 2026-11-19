# SIH 26052 DeepFilterNet3 V9 Canonical Evaluation Report

**Decision:** Do **not** deploy any V9 checkpoint. Keep the existing **Deployed Step-500** model as the active deployment candidate.

## 1. Training Run Evidence

- **Kaggle Kernel:** `shreyasdivekar/deepfilternet3-v9-sih26052` (Notebook source: `antigravity/notebooks/v9/deepfilternet3_v9_sih26052.ipynb`, metadata: `antigravity/notebooks/v9/kernel-metadata.json`)
- **Controlled Experiment Change (Clipping Ablation):** Repeats the V8 recipe (`AdamW lr=1e-6, weight_decay=1e-4`, 500 optimizer steps, 25-step checkpoint interval, V6 full-pool speech sampler, canonical exclusions, source-group splits, V5 target-aligned RIR policy, loss objective, and initialization) while **disabling mixture-only clipping augmentation** (`microphone_clipping_probability = 0.0`, previously 0.15 in V4–V8).
- **Hardware & Runtime:** Dual Tesla T4 (`GPU: Tesla T4 | count: 2`), upstream DeepFilterNet3 (`48000 Hz`, `2,135,484` parameters, PyTorch 2.1.0+cu130, deepfilterlib 0.5.6).
- **Attached Datasets & Leakage Controls:**
  - `shreyasdivekar/anc-sih-training-data`, `panavpayappagoudar/sih-26-processed-audio`, `shreyasdivekar/sih26052-canonical-exclusions`.
  - Canonical exclusions (`canonical_exclusions.csv`): `3,686` rows loaded, `333` matching rows removed; `121,991` remaining metadata rows.
  - Source-group SHA-256 90/10 split: `{'drone': (246, 27), 'environment': (22455, 2495), 'gunfire': (1305, 145), 'speech': (85950, 7368), 'vehicle': (1800, 200)}`.
  - Train mixtures = `7,200`; fixed validation mixtures = `512` (`Validation identity check: True`; validation determinism verified across `[0, 1, 42, 100]`; train preflight verified 40 consecutive finite samples).
  - **Distinct training speech rows sampled:** `7,629` across 500 optimizer steps from `85,950` eligible rows (`feature_state_reset: before every waveform`).
  - `gold_test_read: false` (`SIH_GOLD_TEST` was not mounted, read, or trained on).
- **Optimizer Steps & Validation Curve:**
  - Loss objective: `complex_l1 + 0.25*magnitude_l1 + 0.01*SI-SDR_loss + 0.2*MR-STFT`.
  - Nonzero `sisdr_loss` logged throughout (`step=25`: `12.7831`, `step=250`: `16.5921`, `step=375`: `6.3541`, `step=500`: `14.8214`).
  - Synthetic validation loss improved monotonically every 25 steps from `1.448184` (step 25) to `1.328938` (step 500, `best_validation_loss = 1.3289379961788654`). Consequently `best.hk` is byte-identical to `step-500.hk`.
- **Retrieved Artifacts (`kaggle_output/dfn3_v9_sih26052/`):**
  - Run log: `kaggle_output/dfn3_v9_sih26052/deepfilternet3-v9-sih26052.log`
  - Training report: `kaggle_output/dfn3_v9_sih26052/dfn3_v9_sih26052/training_report.json`
  - Checkpoints (`step-{25..500}.{hk,pt}` every 25 steps and `best.{hk,pt}`) under `kaggle_output/dfn3_v9_sih26052/dfn3_v9_sih26052/`

## 2. Frozen Canonical Evaluation Protocol

- **Script:** `./pc_venv/bin/python ./antigravity/scripts/evaluate_dfn3_canonical.py`
- **Canonical Benchmark:** `590` clips (`antigravity/runs/sih26052_canonical_validation`), manifest SHA-256 `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`, fresh DeepFilterNet3 state per clip, default post-processing (`atten_lim_db = null`, `post_gain_db = 0.0`).
- **Strict Targets:** Output SNR > `15.0` dB, STOI > `0.85`, PESQ-WB > `2.5`, plus per-clip joint pass rate.
- **Checkpoint Loading & Verification:** All 21 `.hk` files (`step-25..500.hk` and `best.hk`) passed strict loading via `hk.load_file` and `model.load_state_dict(..., strict=True)`. All 590 clips completed cleanly across all 20 step checkpoints (`valid_counts = 590` for every metric).

## 3. Full-Set Canonical Results (`n = 590`)

| Model / Checkpoint | SHA-256 (prefix) | Output SNR | SI-SDR | STOI | PESQ-WB | All-three pass |
|---|---|---:|---:|---:|---:|---:|
| **Deployed Step-500 (baseline)** | `bc1fc9b76958` | **13.47 dB** | **12.36 dB** | **0.885** | **2.232** | **161/590 (27.3%)** |
| Pretrained DFN3 reference | `cc2bb32273b8` | 11.61 dB | 10.89 dB | 0.869 | 2.127 | 120/590 (20.3%) |
| V9 `step-25.hk` | `c34486b53c2e` | 12.22 dB | 10.93 dB | 0.863 | 2.118 | 137/590 (23.2%) |
| V9 `step-50.hk` | `7e6ff4aa6b7f` | 12.23 dB | 10.92 dB | 0.863 | 2.123 | 141/590 (23.9%) |
| V9 `step-75.hk` | `f3f750b1ae65` | 12.27 dB | 10.97 dB | 0.864 | 2.127 | 133/590 (22.5%) |
| V9 `step-100.hk` | `b2c7fceff5d8` | 12.40 dB | 11.06 dB | 0.865 | 2.141 | 138/590 (23.4%) |
| V9 `step-125.hk` | `f1e26323f2f2` | 12.46 dB | 11.15 dB | 0.867 | 2.150 | 142/590 (24.1%) |
| V9 `step-150.hk` | `3ebecece50d7` | 12.46 dB | 11.16 dB | 0.867 | 2.155 | 144/590 (24.4%) |
| V9 `step-175.hk` | `3d03c65f8712` | 12.51 dB | 11.21 dB | 0.867 | 2.158 | 144/590 (24.4%) |
| V9 `step-200.hk` | `4947c05af3a5` | 12.58 dB | 11.29 dB | 0.868 | 2.163 | 145/590 (24.6%) |
| V9 `step-225.hk` | `c8b2df7998ae` | 12.63 dB | 11.36 dB | 0.870 | 2.166 | 145/590 (24.6%) |
| **V9 `step-250.hk` (peak joint pass)** | `7c1a643c4cb4` | **12.67 dB** | **11.38 dB** | **0.870** | **2.165** | **148/590 (25.1%)** |
| V9 `step-275.hk` | `d16f0ac5a01f` | 12.72 dB | 11.42 dB | 0.871 | 2.160 | 143/590 (24.2%) |
| **V9 `step-300.hk` (peak PESQ-WB)** | `46322ddce103` | **12.80 dB** | **11.50 dB** | **0.872** | **2.166** | **144/590 (24.4%)** |
| V9 `step-325.hk` | `4a7ad989dcbd` | 12.79 dB | 11.49 dB | 0.872 | 2.159 | 139/590 (23.6%) |
| V9 `step-350.hk` | `d1022d8afaa0` | 12.81 dB | 11.51 dB | 0.872 | 2.156 | 137/590 (23.2%) |
| V9 `step-375.hk` | `bd7f105d5335` | 12.84 dB | 11.55 dB | 0.873 | 2.151 | 137/590 (23.2%) |
| V9 `step-400.hk` | `37336888ff08` | 12.85 dB | 11.55 dB | 0.874 | 2.139 | 137/590 (23.2%) |
| V9 `step-425.hk` | `ecac305990d5` | 12.89 dB | 11.61 dB | 0.875 | 2.139 | 136/590 (23.1%) |
| V9 `step-450.hk` | `0d5133f1dfaa` | 12.95 dB | 11.66 dB | 0.876 | 2.132 | 134/590 (22.7%) |
| **V9 `step-475.hk` (peak SNR/SI-SDR)** | `f9d3e77a0814` | **12.97 dB** | **11.69 dB** | **0.876** | **2.138** | **136/590 (23.1%)** |
| **V9 `step-500.hk` / `best.hk`** | `abf471812f37` | **12.93 dB** | **11.64 dB** | **0.876** | **2.124** | **129/590 (21.9%)** |

Individual metric passes for key checkpoints:
- `step-250.hk` (peak joint pass): SNR > 15 dB `211/590 (35.8%)`, STOI > 0.85 `420/590 (71.2%)`, PESQ-WB > 2.5 `190/590 (32.2%)`, all three `148/590 (25.1%)`.
- `step-300.hk` (peak PESQ-WB): SNR > 15 dB `214/590 (36.3%)`, STOI > 0.85 `424/590 (71.9%)`, PESQ-WB > 2.5 `186/590 (31.5%)`, all three `144/590 (24.4%)`.
- `step-475.hk` (peak SNR / SI-SDR): SNR > 15 dB `215/590 (36.4%)`, STOI > 0.85 `433/590 (73.4%)`, PESQ-WB > 2.5 `177/590 (30.0%)`, all three `136/590 (23.1%)`.
- `step-500.hk` / `best.hk`: SNR > 15 dB `212/590 (35.9%)`, STOI > 0.85 `434/590 (73.6%)`, PESQ-WB > 2.5 `169/590 (28.6%)`, all three `129/590 (21.9%)`.

## 4. Full SHA-256 Checksums of Retrieved V9 Checkpoints

- `step-25.hk`: `c34486b53c2e30c22fe11b4dd3ecde303b74b1e38bf162b53ea145dee9472228` (`step-25.pt`: `f279c3a3a1cd54ee3ded82f103b8f8823349b7fe999a9c8258eba7b32b780364`)
- `step-50.hk`: `7e6ff4aa6b7f86ab025ef4d3ae092f7d6c30d642e78d1a8e3593ec27e5142842` (`step-50.pt`: `422d8be478a7a064bcf995c3069524152bfcb1a44fc60a02545f49cb0eba563c`)
- `step-75.hk`: `f3f750b1ae6540f90cc28d40cd16919202c3d26f3f5a7cae594df26d2f854d1b` (`step-75.pt`: `01d1f6d8c702f5f0d566c49f0d3192a356daad97c1ea4289eb3dddcf495132db`)
- `step-100.hk`: `b2c7fceff5d8965e0607a4102e2996ac8facd06b7011736131027d593672db13` (`step-100.pt`: `7f761f8a3cd534c03b5c9da2d2d8e082758ca652c7aaff9549c0386f53af51fd`)
- `step-125.hk`: `f1e26323f2f286cb4b330489944462f34e22b8bc9e9dc14c6a5946ec57410615` (`step-125.pt`: `5aeddc1372e4ad4ebeee6d9e3637da88001243f7c67f0bfe6c79155b403463c3`)
- `step-150.hk`: `3ebecece50d7c40730e3c1e8decafa75ffa341edafb8dbfa26d549eff4f3bbf9` (`step-150.pt`: `32f50ba8fcdab873adf47a722ffb9b4464b3ffe31ed2c3c9c0f972b0f5cf77d5`)
- `step-175.hk`: `3d03c65f87126d168a34f3fc7412be66057f54affd8a684a3686ac62a5c8a930` (`step-175.pt`: `0a332c904a7e0f1e98afaa35e2f3bd1ccba52e51fe93415618aab24f83459257`)
- `step-200.hk`: `4947c05af3a53dc3571034fb92e3b1bcb167734fd3603c612b8f606517f52a01` (`step-200.pt`: `17e6af7b13fd6c28cfbb4e876bfc2c3a52646c0dae6ce67606a6e57002a6c215`)
- `step-225.hk`: `c8b2df7998aef503ef5ce2f272544799fbbd60a7d9ee3416129d98f991fe9be4` (`step-225.pt`: `6980228a07f321d7f8509611b42ac5608002212b8538d8dffc77844dae5aea76`)
- `step-250.hk`: `7c1a643c4cb4b23c1d47a21170a67574b702bc336f1960394a8c5ba64599ae3e` (`step-250.pt`: `4cc494802319b6d0c375c043ebcabb3c92d7cf286cd502add4b28cfd324d9fc8`)
- `step-275.hk`: `d16f0ac5a01fa29f9956fcaba3f0328e3841c323ae8f6bab6c5384876c069c5d` (`step-275.pt`: `3a3d652970fa47f7930b92732b78c826f6fc44bde043e6b245eae683a818cdf5`)
- `step-300.hk`: `46322ddce1034e6b03b0399def8582d10a0ee3328678d3863eb336d283718879` (`step-300.pt`: `97e69dda41528c688a9557384a4ce9271b50b123bb05239b16e3396170a756d5`)
- `step-325.hk`: `4a7ad989dcbd284a47cde12463e0c314d02b3632deb30880b4b4e7746597920e` (`step-325.pt`: `7d9d49450c99a4418ce97438d75de6f39e62c19ae095aab6ef18956a59edadea`)
- `step-350.hk`: `d1022d8afaa0a8da5da3a794d059425902a7ac4231163ce53a13d7af972cf69c` (`step-350.pt`: `916ae1b3bed948510e489f6bd1249cfcf3c8ff4989f204cf6bd86e12a26c0baf`)
- `step-375.hk`: `bd7f105d53355d5ba0062adfb13dc9ba1643cc92f652fe443d85242f187c9fff` (`step-375.pt`: `95e515aa7e9100c45e7e023b4ec238397a89eb788697e5a43150bbbec40f1ac7`)
- `step-400.hk`: `37336888ff08e11869431bac66554cdfc82bef1af5b29e313239eaf3b92d3b45` (`step-400.pt`: `364e74f6b0d451ab0d7c3fc83313beec2873119d17175b34b7a986c0ffc0aa0a`)
- `step-425.hk`: `ecac305990d58a65d8ac34b2eb7adfe90d0436be3724d835cebe2fb742201f9d` (`step-425.pt`: `bcac441c9920f65d9a4aab7429d4c8ffe69fad6621c4f0d4b05551f4be63ce22`)
- `step-450.hk`: `0d5133f1dfaab765babacc766e1fded4178211ca993734c8ce62963910288b55` (`step-450.pt`: `4f1d13b9b4b51a03108a47c2776d585109b60565db98a1a855c35ea1c8b3eee3`)
- `step-475.hk`: `f9d3e77a0814e8fbe522cc936448c95214a9a2f78f0a8409bbdbda4c60c22a48` (`step-475.pt`: `5cec6171ba75d2994132dd8ab4157d920544964c4b03fa8dcb17b7dd0cd42dc6`)
- `step-500.hk` & `best.hk`: `abf471812f37188b349d84ae3e85597ebad6665c412cab6cf461934b309e6ffe` (`step-500.pt`: `cf01f18a0b998daab712b7176b3550c858d7d61cb4f03bd15899e423d4a1d45b`, `best.pt`: `30160f542ba7fef2c34461b982ebe53e9fa66337c112d5e89933c2c8ce243266`)

## 5. Paired Bootstrap Comparison (2,000 Resamples, seed 26052)

### V9 `step-250.hk` (peak joint pass rate)
- **vs Deployed Step-500 (`paired_step250_vs_deployed_step500.json`):**
  - Output SNR: `-0.79 dB` (95% CI `[-0.93, -0.66]`)
  - SI-SDR: `-0.98 dB` (`[-1.18, -0.79]`)
  - STOI: `-0.015` (`[-0.018, -0.012]`)
  - PESQ-WB: `-0.068` (`[-0.089, -0.046]`)
- **vs Pretrained DFN3 (`paired_step250_vs_pretrained.json`):**
  - Output SNR: `+1.07 dB` (`[+0.89, +1.24]`)
  - SI-SDR: `+0.50 dB` (`[+0.30, +0.69]`)
  - STOI: `+0.001` (`[-0.002, +0.004]`)
  - PESQ-WB: `+0.037` (`[+0.021, +0.055]`)

### V9 `step-300.hk` (peak PESQ-WB)
- **vs Deployed Step-500 (`paired_step300_vs_deployed_step500.json`):**
  - Output SNR: `-0.67 dB` (`[-0.80, -0.54]`)
  - SI-SDR: `-0.86 dB` (`[-1.06, -0.68]`)
  - STOI: `-0.013` (`[-0.016, -0.010]`)
  - PESQ-WB: `-0.066` (`[-0.086, -0.045]`)
- **vs Pretrained DFN3 (`paired_step300_vs_pretrained.json`):**
  - Output SNR: `+1.19 dB` (`[+1.00, +1.37]`)
  - SI-SDR: `+0.61 dB` (`[+0.41, +0.81]`)
  - STOI: `+0.003` (`[-0.000, +0.006]`)
  - PESQ-WB: `+0.039` (`[+0.019, +0.061]`)

### V9 `step-475.hk` (peak SNR / SI-SDR)
- **vs Deployed Step-500 (`paired_step475_vs_deployed_step500.json`):**
  - Output SNR: `-0.49 dB` (`[-0.63, -0.36]`)
  - SI-SDR: `-0.67 dB` (`[-0.86, -0.49]`)
  - STOI: `-0.009` (`[-0.012, -0.006]`)
  - PESQ-WB: `-0.094` (`[-0.115, -0.074]`)
- **vs Pretrained DFN3 (`paired_step475_vs_pretrained.json`):**
  - Output SNR: `+1.37 dB` (`[+1.16, +1.57]`)
  - SI-SDR: `+0.80 dB` (`[+0.58, +1.02]`)
  - STOI: `+0.008` (`[+0.004, +0.010]`)
  - PESQ-WB: `+0.011` (`[-0.014, +0.037]`)

### V9 `step-500.hk` / `best.hk` (final step / best synthetic loss)
- **vs Deployed Step-500 (`paired_step500_vs_deployed_step500.json`):**
  - Output SNR: `-0.54 dB` (`[-0.67, -0.40]`)
  - SI-SDR: `-0.73 dB` (`[-0.91, -0.54]`)
  - STOI: `-0.009` (`[-0.011, -0.006]`)
  - PESQ-WB: `-0.108` (`[-0.130, -0.089]`)
- **vs Pretrained DFN3 (`paired_step500_vs_pretrained.json`):**
  - Output SNR: `+1.32 dB` (`[+1.11, +1.53]`)
  - SI-SDR: `+0.75 dB` (`[+0.52, +0.96]`)
  - STOI: `+0.008` (`[+0.005, +0.010]`)
  - PESQ-WB: `-0.003` (`[-0.029, +0.022]`)

### Measured `input_snr >= 9.6 dB` Subgroup (`n = 245`)
- `step-250.hk`: Output SNR `16.18 dB`, SI-SDR `15.58 dB`, STOI `0.935`, PESQ-WB `2.648`, all-three `123/245 (50.2%)`.
- `step-300.hk`: Output SNR `16.31 dB`, SI-SDR `15.69 dB`, STOI `0.936`, PESQ-WB `2.641`, all-three `120/245 (49.0%)`.
- `step-475.hk`: Output SNR `16.46 dB`, SI-SDR `15.79 dB`, STOI `0.938`, PESQ-WB `2.593`, all-three `112/245 (45.7%)`.
- `step-500.hk`: Output SNR `16.42 dB`, SI-SDR `15.74 dB`, STOI `0.938`, PESQ-WB `2.577`, all-three `107/245 (43.7%)`.
- All checkpoints trail **Deployed Step-500** on this subgroup (`16.88 dB SNR`, `16.42 dB SI-SDR`, `0.942 STOI`, `2.722 PESQ-WB`, `132/245 = 53.9% pass`).

## 6. Key Findings & Next Step

1. **Ablation Effect of Removing Mixture-Only Clipping:**
   - Removing the 15% mixture clipping probability slightly helped perceptual quality early in training: peak PESQ-WB reached `2.1663` at step 300 (compared to `2.1544` at step 225 in V8), and the paired difference vs Pretrained DFN3 remained statistically significant (`+0.039` PESQ-WB, 95% CI `[+0.019, +0.061]`).
   - Peak joint pass rate was `148/590 (25.08%)` at step 250 (tied with V8 step 225).
2. **Persistent Trajectory Tradeoff:**
   - Removing clipping did **not** resolve the divergence between objective loss / synthetic validation and perceptual canonical metrics.
   - SNR, SI-SDR, and STOI continued rising monotonically through `step-475.hk` (`12.97 dB SNR`, `11.69 dB SI-SDR`, `0.876 STOI`), but PESQ-WB peaked between steps 200–300 (`2.163`–`2.166`) and dropped steadily to `2.124` by step 500, even as synthetic validation loss improved continuously from `1.448` to `1.329`.
3. **No V9 Checkpoint Beats Deployed Step-500:**
   - Every single V9 checkpoint trails Deployed Step-500 on full-set SNR, SI-SDR, STOI, and PESQ-WB with paired 95% bootstrap confidence intervals strictly excluding zero.
   - Therefore, **no V9 checkpoint is promoted**. Deployed Step-500 remains the active deployment candidate.
4. **Next Single-Variable Ablation:**
   - The data/training mismatch is not explained by the mixture-only clipping augmentation alone.
   - Per `runs/sih26052_research_and_v6_plan.md`, the next controlled ablation should target **continuous SNR sampling paired with sequence-level loss normalization**, addressing the discrete 7-step SNR quantization and unequal gradient weighting across signal levels.

