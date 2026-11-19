# SIH 26052 DeepFilterNet3 V10 Replica Baseline (R0) Canonical Evaluation Report

**Decision:** Keep the existing **Deployed Step-500** (`bc1fc9b76958...`) as the active deployment candidate on the Raspberry Pi. Do **not** promote any R0 checkpoint. Although R0 successfully reproduces and outperforms Deployed Step-500 on development data, full-set SIH targets (>15 dB SNR, >2.5 PESQ-WB) remain unmet across the full 590-clip benchmark, and promotion requires formal locked evaluation.

---

## 1. Executive Summary & Answer to Task 2

- **Question Answered:** Does an R0 replica of the V3.4 recipe, run inside the leak-safe V9 harness, reproduce Deployed Step-500 (~13.47 dB SNR / 2.232 PESQ-WB)? This is a recipe reproduction, not an exact historical rerun.
- **Finding:** **YES.** R0 at Step 500 achieves **13.6939 dB SNR** and **2.2322 PESQ-WB** on the full 590-clip benchmark, strictly beating Deployed Step-500 on SNR (+0.2269 dB, 95% CI [+0.1730, +0.2851]), SI-SDR (+0.1728 dB, 95% CI [+0.1050, +0.2400]), STOI (+0.0026, 95% CI [+0.0016, +0.0036]), and matching PESQ-WB (-0.0001, 95% CI [-0.0105, +0.0093]).
- **Recipe finding (not an isolated root cause):** R0 restores the V3.4 recipe package and returns development-benchmark quality to around or slightly above the deployed checkpoint. Because R0 changed several factors together (loss weighting, level calibration, SNR/noise mix, clip duration, sampler space, and LR schedule), it does **not** identify which individual V4–V9 change caused the regressions. A1–A5 single-variable runs would be needed for that attribution.
- **Optimal Checkpoint on Even Selection Split:** **R0 Step 550** achieves the highest performance on the Even Selection Set ($n=295$): SNR 13.6403 dB (+0.2311 dB), SI-SDR 12.5705 dB (+0.2499 dB), STOI 0.8901 (+0.0032), PESQ-WB 2.2597 (+0.0102), and Joint Pass 91/295 (30.85% vs Deployed's 29.49%).

---

**Benchmark exposure caveat:** V4–V9 checkpoints were evaluated on the full 590-clip benchmark, so both the even and odd index subsets have prior model-selection exposure. The odd subset below is a descriptive development subset, not an untouched confirmation set. The alternating split is also imbalanced by source and target SNR. Keep SIH gold isolated for the final locked evaluation.

## 2. Training Run Evidence

- **Kaggle Kernel:** `shreyasdivekar/deepfilternet3-v10-sih26052` (Version 4)
- **Local Notebook & Metadata:**
  - [deepfilternet3_v10_r0_sih26052.ipynb](file:///Users/shreyasdivekar/Documents/anc%20sih/antigravity/notebooks/v10/deepfilternet3_v10_r0_sih26052.ipynb)
  - [kernel-metadata.json](file:///Users/shreyasdivekar/Documents/anc%20sih/antigravity/notebooks/v10/kernel-metadata.json)
  - [ANTIGRAVITY_RUN_PROMPT.md](file:///Users/shreyasdivekar/Documents/anc%20sih/antigravity/notebooks/v10/ANTIGRAVITY_RUN_PROMPT.md)
  - [CHANGES.md](file:///Users/shreyasdivekar/Documents/anc%20sih/antigravity/notebooks/v10/CHANGES.md)
- **Hardware & Runtime:** Dual Tesla T4 GPUs (`GPU: Tesla T4 | count: 2`), runtime ~15 minutes (900 seconds) for 1,000 steps.
- **Model Architecture:** Upstream DeepFilterNet3 (`48000 Hz`, `2,135,484` parameters, PyTorch 2.1.0+cu130, deepfilterlib 0.5.6).
- **Attached Datasets & Isolation:**
  - `shreyasdivekar/anc-sih-training-data`, `panavpayappagoudar/sih-26-processed-audio`, `shreyasdivekar/sih26052-canonical-exclusions`.
  - Canonical exclusions (`canonical_exclusions.csv`): 3,686 rows loaded, 333 matching rows removed; 121,991 metadata rows remaining.
  - Source-group SHA-256 90/10 split: `{'drone': (246, 27), 'environment': (22455, 2495), 'gunfire': (1305, 145), 'speech': (85950, 7368), 'vehicle': (1800, 200)}`.
  - `gold_test_read: false` (`SIH_GOLD_TEST` was neither mounted nor read).
- **Deterministic Preflight Checks:**
  - Train preflight: 40 consecutive samples verified finite.
  - Validation determinism: Identical outputs across indices `[0, 1, 42]`.
  - SI-SDR preflight verification: Mean SI-SDR = **`71.92 dB`** on clean speech test (>30 dB threshold).
- **R0 Training Recipe Details:**
  - **Clip Length:** 144,000 samples (3.0 s @ 48 kHz).
  - **Speech Level Calibration:** Uniform random $[-35, -15]$ dBFS with symmetric peak normalization (`scale = 0.99 / peak` if `peak > 0.99`).
  - **Noise Bias:** 60% gunfire, 13% drone, 14% vehicle, 13% environment.
  - **SNR Distribution:** 5% zero-noise, 10% near-clean (30–40 dB), 85% discrete SNRs `[-10, -5, 0, 5, 10, 15, 20, 25]` dB.
  - **Augmentation:** 0% reverb (`synthetic_rir_probability = 0.0`), 0% clipping (`clipping_prob = 0.0`).
  - **Loss Objective:** `complex_l1 + 0.25 * magnitude_l1 + 0.3 * loss_sisdr` (NO MR-STFT).
  - **Optimizer:** AdamW, $\text{lr}_{\max} = 10^{-5}$, $\text{lr}_{\min} = 5 \times 10^{-7}$, 500-step linear warmup followed by 500-step cosine decay, gradient clipping 0.5, weight decay $10^{-4}$.
  - **Speech Sampler:** Sequential index modulo length over 192,000-index space (`distinct_train_speech_rows_sampled: 15,116`).
  - **Validation Loss Curve:** Best validation loss reached at step 650 (`-4.8705`).

---

## 3. Checkpoint Verification

- **Script:** Direct test via `hk.load_file` and PyTorch strict loading (`antigravity/scripts/run_v10_r0_evaluation.py`).
- **Results:** All 21 checkpoints (`step-50` through `step-1000` in increments of 50, plus `best.hk`) loaded strictly with 0 missing and 0 unexpected tensors.
- **Parameter Count:** Exactly `2,135,484` across all checkpoints.
- **Checkpoint Hashes (SHA-256):**
  - `step-50.hk`: `6935c40a71f6af763486e7271ae9c9a34a15e9fb26ddbfe269b9e9204a571380`
  - `step-100.hk`: `fc8351af83b82ae20e71bd85e57fe9b2a2a6d776bb24111dcfb8c9bca3deb29a`
  - `step-250.hk`: `a84023aaa74848aa44acf3ffbc8b1103dd3ab91ac16b6837eb75db105aeb7b89`
  - `step-500.hk`: `57fedd5b608bb7a82e85c7573b0f921f427546a0321cc948182cb1c5695ba40c`
  - `step-550.hk`: `bd95e3b3bb3c66b3108517065a0362daf69096d3c4606ba9f67c736fd9968183`
  - `step-650.hk`: `d6c045de59ada81a3b74d213dfe7c4c907d487482ba9e346ea14f371a1548546`
  - `best.hk`: `d6c045de59ada81a3b74d213dfe7c4c907d487482ba9e346ea14f371a1548546` (matches `step-650.hk`)
  - `step-700.hk`: `1f0dd0325967aaef2992535bb1ca53982b10bc002da7ce6d728e2fb0e6acc1a1`
  - `step-850.hk`: `34a24a9af899d7c627bb9b4cafdbfdf1d08d99a6f1a05bd7e13a447d06d314df`
  - `step-1000.hk`: `1cbb2e55b96cb69d015072e66f1717c3964ea7326568b2eeb98b945248a178a1`

---

## 4. Canonical Benchmark Progression Tables

Evaluated with [evaluate_dfn3_canonical.py](file:///Users/shreyasdivekar/Documents/anc%20sih/antigravity/scripts/evaluate_dfn3_canonical.py) and [compare_dfn3_canonical_split.py](file:///Users/shreyasdivekar/Documents/anc%20sih/antigravity/scripts/compare_dfn3_canonical_split.py) on manifest SHA-256 `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`. Fresh libDF state per clip.

### Table 4.1: Even Selection Set ($n=295$, Primary Development Filter)

| Checkpoint | Output SNR | SI-SDR | STOI | PESQ-WB | Joint Pass (>15dB, >0.85, >2.5) |
|---|---:|---:|---:|---:|---:|
| **Deployed Step-500 (Ref)** | **13.4092 dB** | **12.3206 dB** | **0.8869** | **2.2495** | **87/295 (29.49%)** |
| Pretrained DFN3 Ref | 11.4447 dB | 10.7641 dB | 0.8708 | 2.1336 | 60/295 (20.34%) |
| R0 Step 50 | 12.1827 dB | 11.3380 dB | 0.8761 | 2.1566 | 68/295 (23.05%) |
| R0 Step 100 | 12.7143 dB | 11.7449 dB | 0.8812 | 2.1812 | 68/295 (23.05%) |
| R0 Step 150 | 13.1511 dB | 12.0584 dB | 0.8861 | 2.2041 | 74/295 (25.08%) |
| R0 Step 200 | 13.2669 dB | 12.1496 dB | 0.8872 | 2.2189 | 79/295 (26.78%) |
| R0 Step 250 | 13.5101 dB | 12.3923 dB | 0.8902 | 2.2424 | 79/295 (26.78%) |
| R0 Step 300 | 13.5541 dB | 12.3934 dB | 0.8894 | 2.2526 | 83/295 (28.14%) |
| R0 Step 350 | 13.5196 dB | 12.3928 dB | 0.8897 | 2.2473 | 83/295 (28.14%) |
| R0 Step 400 | 13.5527 dB | 12.3962 dB | 0.8885 | 2.2434 | 84/295 (28.47%) |
| R0 Step 450 | 13.6403 dB | 12.4706 dB | 0.8893 | 2.2443 | 84/295 (28.47%) |
| **R0 Step 500 (Replica Target)** | **13.6200 dB** | **12.5109 dB** | **0.8896** | **2.2491** | **84/295 (28.47%)** |
| **R0 Step 550 (Peak Selection Candidate)** | **13.6403 dB** | **12.5705 dB** | **0.8901** | **2.2597** | **91/295 (30.85%)** |
| R0 Step 600 | 13.4042 dB | 12.2522 dB | 0.8849 | 2.2293 | 85/295 (28.81%) |
| R0 Step 650 (`best.hk`) | 13.5045 dB | 12.4005 dB | 0.8875 | 2.2544 | 89/295 (30.17%) |
| R0 Step 700 | 13.4895 dB | 12.4149 dB | 0.8877 | 2.2574 | 88/295 (29.83%) |
| R0 Step 750 | 13.6013 dB | 12.5230 dB | 0.8893 | 2.2570 | 87/295 (29.49%) |
| R0 Step 800 | 13.5780 dB | 12.5119 dB | 0.8896 | 2.2636 | 88/295 (29.83%) |
| **R0 Step 850 (Peak PESQ)** | **13.6220 dB** | **12.5342 dB** | **0.8895** | **2.2650** | **88/295 (29.83%)** |
| R0 Step 900 | 13.5820 dB | 12.5037 dB | 0.8893 | 2.2582 | 87/295 (29.49%) |
| R0 Step 950 | 13.5648 dB | 12.4610 dB | 0.8882 | 2.2560 | 87/295 (29.49%) |
| R0 Step 1000 | 13.5911 dB | 12.5115 dB | 0.8894 | 2.2614 | 89/295 (30.17%) |

---

### Table 4.2: Odd-index Development Subset (not held out) ($n=295$)

| Checkpoint | Output SNR | SI-SDR | STOI | PESQ-WB | Joint Pass (>15dB, >0.85, >2.5) |
|---|---:|---:|---:|---:|---:|
| **Deployed Step-500 (Ref)** | **13.5247 dB** | **12.4052 dB** | **0.8825** | **2.2151** | **74/295 (25.08%)** |
| Pretrained DFN3 Ref | 11.7688 dB | 11.0129 dB | 0.8663 | 2.1209 | 60/295 (20.34%) |
| R0 Step 50 | 12.2873 dB | 11.2345 dB | 0.8668 | 2.1328 | 69/295 (23.39%) |
| R0 Step 100 | 12.8144 dB | 11.6827 dB | 0.8742 | 2.1649 | 67/295 (22.71%) |
| R0 Step 250 | 13.4893 dB | 12.2189 dB | 0.8851 | 2.1874 | 67/295 (22.71%) |
| **R0 Step 500** | **13.7679 dB** | **12.5606 dB** | **0.8849** | **2.2152** | **75/295 (25.42%)** |
| **R0 Step 550** | **13.8021 dB** | **12.6583 dB** | **0.8852** | **2.2220** | **76/295 (25.76%)** |
| R0 Step 650 (`best.hk`) | 13.6746 dB | 12.4940 dB | 0.8826 | 2.2360 | 79/295 (26.78%) |
| R0 Step 700 | 13.6587 dB | 12.5008 dB | 0.8829 | 2.2301 | 83/295 (28.14%) |
| **R0 Step 850** | **13.8135 dB** | **12.6441 dB** | **0.8847** | **2.2406** | **79/295 (26.78%)** |
| R0 Step 1000 | 13.7782 dB | 12.6249 dB | 0.8844 | 2.2355 | 80/295 (27.12%) |

---

### Table 4.3: Full Benchmark Set ($n=590$)

| Checkpoint | Output SNR | SI-SDR | STOI | PESQ-WB | Joint Pass (>15dB, >0.85, >2.5) |
|---|---:|---:|---:|---:|---:|
| **Deployed Step-500 (Ref)** | **13.4670 dB** | **12.3629 dB** | **0.8847** | **2.2323** | **161/590 (27.29%)** |
| Pretrained DFN3 Ref | 11.6068 dB | 10.8885 dB | 0.8686 | 2.1272 | 120/590 (20.34%) |
| R0 Step 50 | 12.2350 dB | 11.2862 dB | 0.8715 | 2.1447 | 137/590 (23.22%) |
| R0 Step 100 | 12.7644 dB | 11.7138 dB | 0.8777 | 2.1731 | 135/590 (22.88%) |
| R0 Step 250 | 13.4997 dB | 12.3056 dB | 0.8877 | 2.2149 | 146/590 (24.75%) |
| **R0 Step 500 (Replica)** | **13.6939 dB** | **12.5357 dB** | **0.8872** | **2.2322** | **159/590 (26.95%)** |
| **R0 Step 550 (Peak Selection)** | **13.7212 dB** | **12.6144 dB** | **0.8876** | **2.2409** | **167/590 (28.31%)** |
| R0 Step 650 (`best.hk`) | 13.5896 dB | 12.4473 dB | 0.8851 | 2.2452 | 168/590 (28.47%) |
| R0 Step 700 | 13.5741 dB | 12.4578 dB | 0.8853 | 2.2438 | 171/590 (28.98%) |
| **R0 Step 850 (Peak PESQ)** | **13.7178 dB** | **12.5891 dB** | **0.8871** | **2.2528** | **167/590 (28.31%)** |
| R0 Step 1000 | 13.6847 dB | 12.5682 dB | 0.8869 | 2.2484 | 169/590 (28.64%) |

---

## 5. Paired Bootstrap Comparisons (2,000 Resamples, Seed 26052)

Generated via [compare_dfn3_canonical_split.py](file:///Users/shreyasdivekar/Documents/anc%20sih/antigravity/scripts/compare_dfn3_canonical_split.py):

### 5.1 R0 Step-500 vs Deployed Step-500
- **Even Selection Set ($n=295$):**
  - $\Delta\text{SNR} = +0.2108\text{ dB}$ (95% CI $[+0.1429, +0.2804]$) — **strictly positive**
  - $\Delta\text{SI-SDR} = +0.1903\text{ dB}$ (95% CI $[+0.1081, +0.2783]$) — **strictly positive**
  - $\Delta\text{STOI} = +0.0027$ (95% CI $[+0.0012, +0.0044]$) — **strictly positive**
  - $\Delta\text{PESQ-WB} = -0.0004$ (95% CI $[-0.0161, +0.0122]$) — **statistically indistinguishable**
- **Odd-index Development Subset (not held out) ($n=295$):**
  - $\Delta\text{SNR} = +0.2431\text{ dB}$ (95% CI $[+0.1522, +0.3353]$)
  - $\Delta\text{SI-SDR} = +0.1554\text{ dB}$ (95% CI $[+0.0408, +0.2734]$)
  - $\Delta\text{STOI} = +0.0024$ (95% CI $[+0.0013, +0.0037]$)
  - $\Delta\text{PESQ-WB} = +0.0001$ (95% CI $[-0.0153, +0.0132]$)
- **Full Benchmark Set ($n=590$):**
  - $\Delta\text{SNR} = +0.2269\text{ dB}$ (95% CI $[+0.1730, +0.2851]$)
  - $\Delta\text{SI-SDR} = +0.1728\text{ dB}$ (95% CI $[+0.1050, +0.2400]$)
  - $\Delta\text{STOI} = +0.0026$ (95% CI $[+0.0016, +0.0036]$)
  - $\Delta\text{PESQ-WB} = -0.0001$ (95% CI $[-0.0105, +0.0093]$)

### 5.2 R0 Step-550 (Selected Peak) vs Deployed Step-500
- **Even Selection Set ($n=295$):**
  - $\Delta\text{SNR} = +0.2311\text{ dB}$ (95% CI $[+0.1777, +0.2862]$)
  - $\Delta\text{SI-SDR} = +0.2499\text{ dB}$ (95% CI $[+0.1864, +0.3150]$)
  - $\Delta\text{STOI} = +0.0032$ (95% CI $[+0.0020, +0.0047]$)
  - $\Delta\text{PESQ-WB} = +0.0102$ (95% CI $[+0.0010, +0.0202]$) — **strictly positive across all 4 metrics!**
- **Odd-index Development Subset (not held out) ($n=295$):**
  - $\Delta\text{SNR} = +0.2773\text{ dB}$ (95% CI $[+0.2087, +0.3556]$)
  - $\Delta\text{SI-SDR} = +0.2531\text{ dB}$ (95% CI $[+0.1683, +0.3425]$)
  - $\Delta\text{STOI} = +0.0027$ (95% CI $[+0.0018, +0.0036]$)
  - $\Delta\text{PESQ-WB} = +0.0069$ (95% CI $[-0.0082, +0.0200]$)
- **Full Benchmark Set ($n=590$):**
  - $\Delta\text{SNR} = +0.2542\text{ dB}$ (95% CI $[+0.2114, +0.3044]$)
  - $\Delta\text{SI-SDR} = +0.2515\text{ dB}$ (95% CI $[+0.1971, +0.3025]$)
  - $\Delta\text{STOI} = +0.0029$ (95% CI $[+0.0022, +0.0038]$)
  - $\Delta\text{PESQ-WB} = +0.0086$ (95% CI $[+0.0005, +0.0170]$)

---

## 6. SIH Compliance & Governance Verdict

1. **Reproduction Gate:** PASSED. R0 is within $\pm 0.3$ dB of Deployed Step-500 (in fact $+0.2269$ dB above it).
2. **Gold Test Isolation:** PASSED. `gold_test_read: false` enforced. `SIH_GOLD_TEST` was never touched or mounted.
3. **Architecture Freeze:** PASSED. Upstream DeepFilterNet3 parameter count `2,135,484` and 48 kHz filter state frozen.
4. **Hardware & Active Deployment:** Active deployment on historical Raspberry Pi 4 baseline (`~/anc_live` untouched; target hardware updated to Raspberry Pi 5 for Stage 11). Deployed Step-500 remains active.
5. **Full-Set SIH Target Status:** UNMET. Full-set benchmark average SNR is $13.72$ dB (target $>15.0$ dB) and PESQ-WB is $2.24$ (target $>2.5$). Absolute full-set criteria are not satisfied.

