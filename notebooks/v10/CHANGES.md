# SIH 26052: V10 Replica Baseline (R0) and Single-Variable Ablation Plan

**Document Path:** `antigravity/notebooks/v10/CHANGES.md`  
**Date:** 2026-11-13  
**Status:** R0 completed on Kaggle (Version 4), artifacts retrieved, all 20 checkpoints evaluated, and reports updated. A1–A5 have not been run.  
**Target:** Pinpoint the exact change between V3.4 (Deployed Step-500) and V4–V9 that caused canonical quality degradation, and produce a candidate that strictly beats Deployed Step-500.

### R0 push history

Kaggle Versions 1 and 2 failed before training (archive-only path assumption/empty category split; then CPU/CUDA mismatch in the SI-SDR preflight). Version 3 was canceled before completion. Version 4 used the corrected mounted-file/archive reader, category-covered leakage-safe split, and device-aligned SI-SDR preflight; it completed 1,000 optimizer steps. Artifacts are in `kaggle_output/dfn3_v10_r0_sih26052/`; all 21 `.hk` checkpoints were strictly loaded and all 20 step checkpoints were evaluated. No deployed weights were changed.

---

## 1. Recipe Diff: V3.4 (Deployed Step-500) vs V9

Comparison between executed V3.4 (`training/finetune_dfn3_v3_4_kaggle.ipynb`, commit `5de1c4f`) and V9 (`notebooks/v9/deepfilternet3_v9_sih26052.ipynb`):

| Component / Parameter | V3.4 (Deployed Step-500) | V9 (Ablation Run) | Impact Analysis |
|---|---|---|---|
| **SI-SDR loss weight (`lambda_sisdr`)** | `0.3` | `0.01` | **30x lower in V9.** V3.4 heavily weighted time-domain SI-SDR to enforce waveform fidelity; V9 barely weighted it (`0.01`). |
| **Multi-resolution STFT loss** | `None (0.0)` | `0.2 * MR-STFT` | V9 introduced MR-STFT (FFTs 512, 1024, 2048) combining spectral convergence and log-magnitude L1. |
| **Reverb augmentation (synthetic RIR)** | `0% (none)` | `20% synthetic RIR` | V9 applied synthetic exponentially decaying RIRs; V3.4 trained on clean speech without synthetic room response. |
| **Clipping augmentation** | `0% (none)` | `0% (clipping_prob=0.0)` | Identical (V8 used 15% mixture clipping; V9 disabled it). |
| **Speech level calibration** | `[-35.0, -15.0] dBFS` uniform | `Unit RMS (0 dBFS)` | **Major difference.** V3.4 calibrated speech target RMS to realistic dynamic range; V9 normalized speech to unit RMS (extremely loud). |
| **Peak normalization** | Symmetric (`scale = 0.99 / peak`) | Asymmetric (`common_scale = max(1.0, peak)`) | V3.4 scaled clean, noise, and noisy identically; V9 capped at 1.0 only if peak exceeded 1.0. |
| **Clip length** | `144,000` samples (3.0 s @ 48 kHz) | `96,000` samples (2.0 s @ 48 kHz) | V3.4 gave the model 3.0 s of temporal context per clip vs 2.0 s in V9. |
| **Batch size** | `16` | `16` | Identical. |
| **Gunfire noise fraction** | `60% gunfire` (13% drone, 14% veh, 13% env) | `25% uniform` (25% each category) | V3.4 biased 60% of noise draws toward gunfire; V9 sampled all 4 categories uniformly. |
| **Mixing modes / SNR bins** | 5% clean, 10% near-clean, 85% discrete `[-10..25] dB` | 100% discrete `[-10..20] dB` weighted | V3.4 trained on zero-noise identity, near-clean ($[30, 40]\text{ dB}$), and $+25\text{ dB}$ bin. |
| **Training speech sampler** | `self.speech[i % len(self.speech)]` with shuffled dataset indices | `rng.randrange(len(self.speech))` | V3.4 did **not** simply use the first N rows: its shuffled dataset had 192,000 indices and training consumed the first 96,000. R0 now preserves the same index-space size and modulo sampler for its 1,000-step horizon; unique speech rows actually drawn are recorded. V9 draws uniformly with replacement across the full pool. |
| **Warmup steps** | `500` steps (linear $0 \to 10^{-5}$) | `0` steps | V3.4 warmed up over 500 steps; V9 initialized immediately at full LR. |
| **Learning rate & schedule** | Cosine decay ($10^{-5} \to 5\times 10^{-7}$ over 6k steps) | Constant $10^{-6}$ throughout 500 steps | V3.4 peaked at $10^{-5}$ at step 500 with cosine decay; V9 ran at flat $10^{-6}$. |
| **Gradient clipping (max norm)** | `0.5` | `1.0` | V3.4 clipped gradients more aggressively ($0.5$ vs $1.0$). |
| **Validation set & metric** | 100 fixed mixtures, composite score | 512 fixed mixtures, loss objective | V3.4 scored side-by-side with pretrained reference on actual metrics; V9 tracked loss. |
| **Optimizer** | `AdamW(lr=1e-5, weight_decay=1e-4)` | `AdamW(lr=1e-6, weight_decay=1e-4)` | Peak LR was $10^{-5}$ in V3.4 vs $10^{-6}$ in V9. |
| **Model initialization** | Pretrained reference weights | Pretrained reference weights | Identical (upstream DeepFilterNet3 reference). |

### SI-SDR Verification in Logs & Preflights
- **V8 Log (`kaggle_output/dfn3_v8_sih26052/deepfilternet3-v8-sih26052.log`):** `sisdr_loss` was active and nonzero throughout (`step=25: 12.8156`, `step=50: 13.2966`, `step=250: 16.6262`, `step=500: 14.8630`). Preflight confirmed 40 consecutive finite samples; SI-SDR was NOT disabled.
- **V9 Log (`kaggle_output/dfn3_v9_sih26052/deepfilternet3-v9-sih26052.log`):** `sisdr_loss` was active and nonzero throughout (`step=25: 12.8239`, `step=50: 13.2979`, `step=250: 16.5921`, `step=500: 14.8214`). Preflight confirmed 40 consecutive finite samples; SI-SDR was NOT disabled.
- **V3.4 execution evidence limitation:** The cited `experiments/dfn3_v3_4_step500/validation_log.csv` is not present in this workspace. The available `antigravity/runs/kaggle_v3_1_error_output/dfn3_v3_4_output/validation_log.csv` is header-only. The repaired V3.4 notebook contains a branch that disables the SI-SDR term if the 50-clip reconstruction check is below 30 dB, but the executed check result is not available here. Treat the pasted step-500 loss values and claim that the branch passed as unverified until the original run log is restored.
- **Verified SI-SDR conclusion:** V8/V9 logs show nonzero SI-SDR loss. V3.4 source config sets weight 0.3 and source contains a conditional disable branch; source inspection alone cannot establish which branch ran. The nominal coefficient differs 30x, but total-loss scales also differ substantially because V9 adds MR-STFT.

---

## 2. Development Subsets (Even and Odd Index)

For new R0-era selection, the 590 canonical clips are partitioned by `val_index`:
- **Even-index subset (`n=295`):** Used as the R0 checkpoint selection view. It is development data, not an untouched selection set, because V4–V9 were previously evaluated over all 590 clips.
- **Odd-index subset (`n=295`):** Reported descriptively as a second development slice. It is **not** an independent confirmation set because V4–V9 already used the full benchmark. Preserve SIH gold for a one-time final evaluation after model selection is frozen.

The parity split is also imbalanced in source and target SNR (e.g. IoBT_GUNFIRE counts 212 even vs. 230 odd). Treat both subsets as descriptive development evidence, not unbiased holdout estimates.

### Baseline Benchmark Values on the Partitioned Sets

| Model / Checkpoint | Subset ($n$) | Mean SNR | Mean SI-SDR | Mean STOI | Mean PESQ-WB | Joint Pass Count |
|---|---|---:|---:|---:|---:|---:|
| **Deployed Step-500** | Full set ($590$) | 13.47 dB | 12.36 dB | 0.885 | 2.232 | 161/590 (27.3%) |
| **Deployed Step-500** | **Even Selection ($295$)** | **13.41 dB** | **12.32 dB** | **0.887** | **2.250** | **87/295 (29.5%)** |
| **Deployed Step-500** | **Odd development ($295$)** | **13.52 dB** | **12.41 dB** | **0.883** | **2.215** | **74/295 (25.1%)** |
| Pretrained DFN3 | Full set ($590$) | 11.61 dB | 10.89 dB | 0.869 | 2.127 | 120/590 (20.3%) |
| Pretrained DFN3 | Even Selection ($295$) | 11.44 dB | 10.76 dB | 0.871 | 2.134 | 60/295 (20.3%) |
| Pretrained DFN3 | Odd development ($295$) | 11.77 dB | 11.01 dB | 0.866 | 2.121 | 60/295 (20.3%) |

---

## 3. Replica Baseline: R0 Specification

Notebook: `antigravity/notebooks/v10/deepfilternet3_v10_r0_sih26052.ipynb`  
Metadata: `antigravity/notebooks/v10/kernel-metadata.json` (`shreyasdivekar/deepfilternet3-v10-sih26052`)

R0 recreates the V3.4 training recipe inside the leak-safe V9 data harness; it is **not an exact historical rerun** because the source-group split, data I/O, and 1,000-step horizon differ from V3.4's 6,000 steps. It preserves V3.4's recipe choices and the 192,000-index shuffled dataset space for modulo speech sampling:
1. **Model & Architecture:** Upstream DeepFilterNet3 reference ($48\text{ kHz}$, $2,135,484$ parameters), pretrained initialization.
2. **Audio Mixing:** `mix_pair` with speech target level uniformly drawn in $[-35.0, -15.0]\text{ dBFS}$, noise scaled to exact SNR, symmetric peak normalization if peak $> 0.99$ (`scale = 0.99 / peak`).
3. **Clip Length:** $144,000$ samples ($3.0\text{ s}$ at $48\text{ kHz}$).
4. **Augmentations:** $0\%$ synthetic RIR, $0\%$ clipping (`clipping_prob = 0.0`).
5. **Noise Sampling:** $60\%$ gunfire, $13\%$ drone, $14\%$ vehicle, $13\%$ environment.
6. **SNR Schedule:** $5\%$ zero-noise, $10\%$ near-clean ($[30, 40]\text{ dB}$), $85\%$ discrete SNRs `[-10, -5, 0, 5, 10, 15, 20, 25]` dB.
7. **Loss Objective:** `complex_l1 + 0.25*magnitude_l1 + 0.3*loss_sisdr` (time-domain iSTFT SI-SDR loss with Vorbis window; NO MR-STFT).
8. **Optimizer & Schedule:** AdamW with $500$-step linear warmup ($0 \to 10^{-5}$) followed by cosine decay to $5\times 10^{-7}$ through step 1,000; weight decay $10^{-4}$, gradient clipping $0.5$.
9. **Checkpoint Cadence:** Saved every $50$ steps through step 1,000 (`step-{50..1000}.{hk,pt}` + `best.{hk,pt}`).
10. **Validation Gate:** Evaluate checkpoints on the even development subset ($n=295$) after retrieval. If R0 step 500 is more than 0.3 dB below Deployed Step-500, halt the subsequent A1–A5 sequence and investigate the harness. R0 itself completes as configured; the canonical benchmark is not attached to Kaggle.

---

## 4. Single-Variable Ablation Sequence (from R0)

Each run executes 1,000 steps with checkpoints every 50 steps, changing **exactly one variable** relative to R0:

- **A1 (`lambda_sisdr = 0.01`):** Keep all R0 settings fixed; change `lambda_sisdr` from $0.3$ to $0.01$ (as in V4–V9). Tests whether the 30x SI-SDR loss de-weighting caused the collapse.
- **A2 (`+ 0.2*MR-STFT`):** Keep all R0 settings fixed; add $0.2\times$ multi-resolution STFT loss (FFTs 512, 1024, 2048). Tests whether spectral loss over-regularization degraded speech transients.
- **A3 (`20% synthetic RIR`):** Keep all R0 settings fixed; enable 20% target-aligned exponentially decaying synthetic room response. Tests whether synthetic RIRs caused canonical mismatch.
- **A4 (`15% mixture clipping`):** Keep all R0 settings fixed; apply 15% mixture-only clipping augmentation. Tests whether V8 clipping caused perceptual regression.
- **A5 (`Full-pool speech sampler`):** Keep all R0 settings fixed; change speech sampler from sequential modulo indexing over the shuffled V3.4-sized index space to a uniform full-pool draw across eligible speech rows. Tests sampler effects; a canonical regression alone does not establish “phoneme drift.”

---

## 5. Improvement Runs (Post R0 / A1–A5)

Applied one at a time on top of R0:
- **B1:** `lambda_sisdr = 0.5` and `1.0`.
- **B2:** Step range extended to 1,000–3,000 steps with the R0 cosine schedule.
- **B3:** Continuous uniform training SNR in $[-10.0, +20.0]\text{ dB}$.

---

## 6. Execution & Safety Governance

- `GOLD_TEST_READ = NO` (`gold_test_read: false` enforced across all reports and scripts).
- `AUTO_PROMOTE = NO` (Deployed Step-500 remains active).
- `KAGGLE_PUSH_APPROVED = YES` for **R0 only**, based on the user's explicit instruction to approve V10 for Kaggle. This authorizes pushing/running the reviewed R0 notebook; it does not approve A1–A5, deployment, or model promotion.
- Device Safety: No weights copied to Raspberry Pi; Bluetooth MAC addresses masked to last two octets (`**:**:**:**:XX:YY`).

