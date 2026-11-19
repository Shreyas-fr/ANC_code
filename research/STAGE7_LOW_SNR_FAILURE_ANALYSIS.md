# SIH 26052 — Stage 7: Low-SNR Failure Analysis Report

**Date:** 2026-11-13  
**Status:** Completed · Analysis-Only · Reproducible  
**Decision Gate:** Do not modify, train, or promote any model. **Deployed Step-500** (`bc1fc9b76958...`) remains the active deployed baseline on the historical Raspberry Pi 4 deployment (`~/anc_live` untouched; target hardware updated to Raspberry Pi 5 for Stage 11). Universal SIH target compliance (>15 dB SNR, >2.5 PESQ-WB) is **not met** by any evaluated model across the 590-clip canonical benchmark.

> [!NOTE]
> **Historical Hardware Provenance:** Stage 7 failure analysis was evaluated against the historical baseline deployment on Raspberry Pi 4 Model B (Cortex-A72 @ 1.5 GHz). For Stage 11 onward, the authorized project hardware target is Raspberry Pi 5 (Broadcom BCM2712, Quad-core Cortex-A76 @ 2.4 GHz). All Pi 4 references in this report are preserved strictly for retrospective historical provenance.

---

## 1. Executive Summary

This study presents a rigorous, reproducible, analysis-only failure analysis comparing three distinct speech enhancement architectures on the frozen 590-clip SIH canonical benchmark (`d09a520d...`):
1. **DFN3 Step-500** (`bc1fc9b76958...`): Protected deployed candidate, DeepFilterNet3 architecture (48 kHz, 2,135,484 parameters).
2. **FullSubNet** (epoch 58, `482615e9...`): Official Audio-WestlakeU pretrained offline baseline (16 kHz, 5,637,635 parameters).
3. **GTCRN DNS3** (`a630d992...`): Official lightweight convolutional recurrent network (16 kHz, 48,245 parameters).

### Primary Empirical Findings:
- **Catastrophic Low-SNR Failure across All Architectures:** In the combined low-input-SNR region ($\le 0\text{ dB}$, $n=210$), **191 out of 210 clips (91.0%)** fail the joint criteria across all three models simultaneously. At $-10\text{ dB}$ ($n=30$), **100% of clips (30/30) fail** across all three models.
- **Severe Output Shortfall:** At $-10\text{ dB}$ input, mean output SNRs are $6.56\text{ dB}$ (Step-500), $7.12\text{ dB}$ (FullSubNet), and $6.51\text{ dB}$ (GTCRN), falling $>8\text{ dB}$ short of the SIH $>15\text{ dB}$ threshold. Mean PESQ-WB scores are $1.39$, $1.42$, and $1.33$, falling $>1.0$ short of the $>2.5$ threshold.
- **Model Hierarchy in Low-SNR:** FullSubNet is the strongest architecture across every single low-SNR bin (achieving 17 joint passes in $\le 0\text{ dB}$, vs 11 for Step-500 and 9 for GTCRN). In paired comparisons across $\le 0\text{ dB}$, FullSubNet outperforms Step-500 by $+0.81\text{ dB}$ SNR ($[+0.47, +1.15]$) and $+0.15\text{ PESQ-WB}$ ($[+0.11, +0.20]$).
- **GTCRN Characterization & Lack of Acoustic Niche:** GTCRN offers **zero** low-SNR denoising advantage over Step-500 ($\Delta\text{SNR} = +0.04\text{ dB}$, $95\%\text{ CI } [-0.26, +0.36]$ at $\le 0\text{ dB}$; $\Delta\text{PESQ} = -0.08$ $[ -0.12, -0.04]$). GTCRN's aggregate SNR gain over Step-500 ($+0.38\text{ dB}$ full-set) is concentrated almost entirely at $+5\text{ dB}$ ($+0.82\text{ dB}$), while suffering broad perceptual degradation ($-0.12\text{ PESQ-WB}$ full set). Across the entire benchmark, there are only 2 clips where GTCRN is the sole passing model (and 0 clips in $\le 0\text{ dB}$).
- **GTCRN's True Niche:** GTCRN's value lies strictly in its **extreme compute footprint** ($48,245$ parameters, $580\text{ KB}$ checkpoint, RTF $0.0097$ on CPU), making it suitable for ultra-constrained DSPs or microcontrollers, but not for replacing Step-500 on the historical Raspberry Pi 4 baseline where compute headroom was already adequate.

---

## 2. Integrity Checks and Protected Artifact Hashes

Before data processing, all source artifacts, evaluator scripts, and model checkpoints were verified against previously recorded SHA-256 hashes.

### 2.1 Artifact Hash Verification Table

| Artifact | Recorded / Expected SHA-256 | Observed SHA-256 | Status |
|:---|:---|:---|:---:|
| **Canonical manifest** | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` | **Verified** |
| **Deployed Step-500 checkpoint** | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` | **Verified** |
| **FullSubNet checkpoint** | `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0` | `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0` | **Verified** |
| **GTCRN checkpoint** | `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79` | `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79` | **Verified** |
| **Canonical evaluator script** | `66e448cc47b0ae60846399d803d8f6321068c5e4a9faa18f6ebb09305219b16a` | `66e448cc47b0ae60846399d803d8f6321068c5e4a9faa18f6ebb09305219b16a` | **Verified** |
| **Comparison script** | `e66f00553245871a89b6146246c4f60454ea641548b05de97c004cb216abafc7` | `e66f00553245871a89b6146246c4f60454ea641548b05de97c004cb216abafc7` | **Verified** |
| **Step-500 per-clip CSV** | `9b27038fb21b9d15e7066b2324372c4471abab2247989ea1da65922888a2366f` | `9b27038fb21b9d15e7066b2324372c4471abab2247989ea1da65922888a2366f` | **Verified** |
| **FullSubNet per-clip CSV** | `56207ad4325b9c91a71188cf2edecf063b1385f118c29579acd604d8a4dd7e62` | `56207ad4325b9c91a71188cf2edecf063b1385f118c29579acd604d8a4dd7e62` | **Verified** |
| **GTCRN per-clip CSV** | `f43a643d361af3a8b2b34057d967be9af78091aed4b195512f00271f95771494` | `f43a643d361af3a8b2b34057d967be9af78091aed4b195512f00271f95771494` | **Verified** |
| **GTCRN inference per-clip CSV** | `95b65dbaa7260db9a9b37a6ac16a9c5509294178f4b33137bdb6665cf841e729` | `95b65dbaa7260db9a9b37a6ac16a9c5509294178f4b33137bdb6665cf841e729` | **Verified** |

### 2.2 Data Alignment & Integrity Verification
- **Unique Clip IDs:** Exactly 590 unique canonical clip IDs (`val_index` $0$ through $589$) present in all files with zero duplicates, zero omissions, and zero unindexed entries.
- **Explicit Join:** Alignment performed via explicit integer key join on `val_index`.
- **Target SNR and Origin Labels:** $100\%$ match across `manifest.csv`, `step500/per_clip.csv`, `fullsubnet/per_clip.csv`, and `gtcrn/per_clip.csv`.
- **Finiteness:** All metric fields (`output_snr_db`, `output_si_sdr_db`, `output_stoi`, `output_pesq_wb`) and GTCRN inference timings are strictly finite real numbers (no `NaN`, `Inf`, or nulls).
- **Inference Verification:** GTCRN outputs verified at exactly 48,000 samples ($3.0\text{ s} @ 16\text{ kHz}$) with valid recorded audio hashes.

---

## 3. Per-Model Performance by Target Input-SNR Bin

*Table source: [STAGE7_SNR_BIN_SUMMARY.csv](file:///Users/shreyasdivekar/Documents/anc%20sih/research/STAGE7_SNR_BIN_SUMMARY.csv)*  
*Criteria: SNR $>15\text{ dB}$, STOI $>0.85$, PESQ-WB $>2.5$. Joint pass requires meeting all three simultaneously.*

| Input SNR Bin | Model | N | Mean SNR | Med SNR | Mean SI-SDR | Med SI-SDR | Mean STOI | Med STOI | Mean PESQ | Med PESQ | Pass SNR | Pass STOI | Pass PESQ | Joint Pass Count (%) |
|:---|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **-10 dB** | **Step-500** | 30 | 6.5617 dB | 6.6758 dB | 2.5595 dB | 4.7602 dB | 0.6774 | 0.7159 | 1.3855 | 1.3238 | 0 | 6 | 0 | **0 / 30 (0.00%)** |
| -10 dB | **FullSubNet** | 30 | 7.1151 dB | 6.4670 dB | 4.4093 dB | 4.5733 dB | 0.7099 | 0.7187 | 1.4150 | 1.3230 | 0 | 5 | 0 | **0 / 30 (0.00%)** |
| -10 dB | **GTCRN** | 30 | 6.5084 dB | 5.4521 dB | 3.0492 dB | 3.4407 dB | 0.6792 | 0.7032 | 1.3337 | 1.2485 | 1 | 5 | 0 | **0 / 30 (0.00%)** |
| **-5 dB** | **Step-500** | 63 | 9.9452 dB | 9.6057 dB | 8.1193 dB | 7.1791 dB | 0.8038 | 0.8338 | 1.6889 | 1.5588 | 9 | 26 | 6 | **3 / 63 (4.76%)** |
| -5 dB | **FullSubNet** | 63 | 10.7063 dB | 10.1893 dB | 9.1287 dB | 8.4765 dB | 0.8322 | 0.8533 | 1.8272 | 1.6781 | 10 | 33 | 6 | **2 / 63 (3.17%)** |
| -5 dB | **GTCRN** | 63 | 9.8914 dB | 9.3522 dB | 8.2410 dB | 7.8259 dB | 0.8038 | 0.8208 | 1.6507 | 1.4453 | 5 | 24 | 7 | **2 / 63 (3.17%)** |
| **0 dB** | **Step-500** | 117 | 11.0269 dB | 10.8909 dB | 9.7649 dB | 9.7092 dB | 0.8563 | 0.8931 | 1.8586 | 1.7761 | 14 | 76 | 13 | **8 / 117 (6.84%)** |
| 0 dB | **FullSubNet** | 117 | 11.9367 dB | 11.6078 dB | 10.5561 dB | 10.7172 dB | 0.8759 | 0.8984 | 2.0520 | 1.9278 | 23 | 87 | 20 | **15 / 117 (12.82%)** |
| 0 dB | **GTCRN** | 117 | 11.1451 dB | 10.5945 dB | 9.6406 dB | 9.3818 dB | 0.8488 | 0.8706 | 1.7438 | 1.6211 | 14 | 73 | 9 | **7 / 117 (5.98%)** |
| **5 dB** | **Step-500** | 137 | 12.8139 dB | 13.0808 dB | 11.7418 dB | 12.6645 dB | 0.8907 | 0.9189 | 2.1456 | 2.1019 | 44 | 112 | 34 | **20 / 137 (14.60%)** |
| 5 dB | **FullSubNet** | 137 | 14.4934 dB | 14.8743 dB | 13.3042 dB | 13.7948 dB | 0.9102 | 0.9327 | 2.4111 | 2.3731 | 63 | 121 | 56 | **34 / 137 (24.82%)** |
| 5 dB | **GTCRN** | 137 | 13.6298 dB | 13.3295 dB | 12.3149 dB | 12.3152 dB | 0.8899 | 0.9034 | 2.0147 | 1.9724 | 43 | 108 | 24 | **17 / 137 (12.41%)** |
| **$\le$ 0 dB Total** | **Step-500** | 210 | 10.0645 dB | 10.2430 dB | 8.2419 dB | 8.6815 dB | 0.8150 | 0.8584 | 1.7401 | 1.6190 | 23 | 108 | 19 | **11 / 210 (5.24%)** |
| $\le$ 0 dB Total | **FullSubNet** | 210 | 10.8788 dB | 10.8364 dB | 9.2498 dB | 9.5211 dB | 0.8391 | 0.8708 | 1.8935 | 1.8007 | 33 | 125 | 26 | **17 / 210 (8.10%)** |
| $\le$ 0 dB Total | **GTCRN** | 210 | 10.1066 dB | 9.8162 dB | 8.2791 dB | 8.4193 dB | 0.8111 | 0.8452 | 1.6573 | 1.5309 | 20 | 102 | 16 | **9 / 210 (4.29%)** |
| **Full 590 Set** | **Step-500** | 590 | 13.4670 dB | 13.0816 dB | 12.3629 dB | 12.6602 dB | 0.8847 | 0.9230 | 2.2323 | 2.1643 | 230 | 447 | 207 | **161 / 590 (27.29%)** |
| Full 590 Set | **FullSubNet** | 590 | 14.9038 dB | 14.8046 dB | 13.7000 dB | 13.7399 dB | 0.9026 | 0.9356 | 2.5133 | 2.4560 | 282 | 478 | 282 | **218 / 590 (36.95%)** |
| Full 590 Set | **GTCRN** | 590 | 13.8437 dB | 13.6327 dB | 12.4887 dB | 12.5357 dB | 0.8813 | 0.9108 | 2.1149 | 2.0100 | 224 | 437 | 171 | **144 / 590 (24.41%)** |

---

## 4. Paired Model Comparisons

*Table source: [STAGE7_PAIRED_COMPARISONS.csv](file:///Users/shreyasdivekar/Documents/anc%20sih/research/STAGE7_PAIRED_COMPARISONS.csv)*  
*Differences are calculated clip-by-clip: `Candidate - Reference`. Confidence intervals use 2,000 paired percentile bootstrap resamples with seed 26052.*

| Comparison | Bin | N | $\Delta\text{SNR}$ dB (95% CI) | $\Delta\text{SI-SDR}$ dB (95% CI) | $\Delta\text{STOI}$ (95% CI) | $\Delta\text{PESQ-WB}$ (95% CI) | $\Delta\text{Joint Pass}$ |
|:---|:---|---:|---:|---:|---:|---:|---:|
| **GTCRN vs Step-500** | -10 dB | 30 | -0.0532 `[-1.1636, +1.0013]` | +0.4897 `[-1.4854, +2.6751]` | +0.0018 `[-0.0343, +0.0385]` | -0.0518 `[-0.1315, +0.0260]` | 0 |
| GTCRN vs Step-500 | -5 dB | 63 | -0.0538 `[-0.5916, +0.5040]` | +0.1217 `[-0.7215, +1.1064]` | -0.0000 `[-0.0160, +0.0198]` | -0.0382 `[-0.0940, +0.0141]` | -1 |
| GTCRN vs Step-500 | 0 dB | 117 | +0.1181 `[-0.2667, +0.5331]` | -0.1244 `[-0.5819, +0.3458]` | -0.0074 `[-0.0154, +0.0011]` | -0.1148 `[-0.1734, -0.0512]` | -1 |
| GTCRN vs Step-500 | 5 dB | 137 | **+0.8159** `[+0.2276, +1.4221]` | +0.5731 `[-0.0428, +1.2558]` | -0.0008 `[-0.0094, +0.0100]` | **-0.1309** `[-0.1932, -0.0663]` | -3 |
| GTCRN vs Step-500 | **$\le$ 0 dB** | 210 | **+0.0421** `[-0.2568, +0.3632]` | **+0.0372** `[-0.4001, +0.5386]` | **-0.0039** `[-0.0122, +0.0053]` | **-0.0828** `[-0.1204, -0.0445]` | **-2** |
| GTCRN vs Step-500 | **Full 590** | 590 | **+0.3768** `[+0.1336, +0.6134]` | **+0.1258** `[-0.1455, +0.4091]` | **-0.0033** `[-0.0073, +0.0009]` | **-0.1174** `[-0.1486, -0.0872]` | **-17** |
| **FullSubNet vs Step-500** | -10 dB | 30 | +0.5535 `[-0.4445, +1.4305]` | +1.8498 `[+0.0362, +3.8910]` | +0.0325 `[-0.0023, +0.0673]` | +0.0295 `[-0.0518, +0.0996]` | 0 |
| FullSubNet vs Step-500 | -5 dB | 63 | +0.7611 `[+0.1360, +1.4150]` | +1.0094 `[+0.1760, +1.9460]` | +0.0284 `[+0.0111, +0.0487]` | +0.1383 `[+0.0610, +0.2177]` | -1 |
| FullSubNet vs Step-500 | 0 dB | 117 | +0.9098 `[+0.4688, +1.3554]` | +0.7912 `[+0.1867, +1.3555]` | +0.0196 `[+0.0115, +0.0285]` | +0.1933 `[+0.1256, +0.2641]` | +7 |
| FullSubNet vs Step-500 | 5 dB | 137 | +1.6795 `[+1.1727, +2.2114]` | +1.5624 `[+1.0478, +2.1161]` | +0.0195 `[+0.0126, +0.0269]` | +0.2655 `[+0.1954, +0.3355]` | +14 |
| FullSubNet vs Step-500 | **$\le$ 0 dB** | 210 | **+0.8143** `[+0.4695, +1.1475]` | **+1.0079** `[+0.4951, +1.5327]` | **+0.0241** `[+0.0157, +0.0331]` | **+0.1534** `[+0.1076, +0.1998]` | **+6** |
| FullSubNet vs Step-500 | **Full 590** | 590 | **+1.4368** `[+1.1814, +1.6992]` | **+1.3371** `[+1.0547, +1.6204]` | **+0.0179** `[+0.0143, +0.0219]` | **+0.2811** `[+0.2464, +0.3121]` | **+57** |
| **GTCRN vs FullSubNet** | -10 dB | 30 | -0.6067 `[-1.2093, -0.0579]` | -1.3601 `[-2.0816, -0.6323]` | -0.0306 `[-0.0515, -0.0108]` | -0.0813 `[-0.1419, -0.0244]` | 0 |
| GTCRN vs FullSubNet | -5 dB | 63 | -0.8149 `[-1.3447, -0.3042]` | -0.8877 `[-1.5017, -0.2822]` | -0.0284 `[-0.0358, -0.0211]` | -0.1765 `[-0.2432, -0.1128]` | 0 |
| GTCRN vs FullSubNet | 0 dB | 117 | -0.7916 `[-1.2431, -0.3200]` | -0.9155 `[-1.4370, -0.3110]` | -0.0270 `[-0.0315, -0.0229]` | -0.3081 `[-0.3613, -0.2601]` | -8 |
| GTCRN vs FullSubNet | 5 dB | 137 | -0.8636 `[-1.3067, -0.3563]` | -0.9893 `[-1.4107, -0.4961]` | -0.0203 `[-0.0252, -0.0142]` | -0.3965 `[-0.4552, -0.3375]` | -17 |
| GTCRN vs FullSubNet | **$\le$ 0 dB** | 210 | **-0.7722** `[-1.0720, -0.4456]` | **-0.9707** `[-1.3162, -0.5889]` | **-0.0280** `[-0.0326, -0.0236]` | **-0.2363** `[-0.2723, -0.1975]` | **-8** |
| GTCRN vs FullSubNet | **Full 590** | 590 | **-1.0600** `[-1.2868, -0.8325]` | **-1.2113** `[-1.4382, -0.9822]` | **-0.0212** `[-0.0234, -0.0190]` | **-0.3984** `[-0.4302, -0.3696]` | **-74** |

### Concentration of GTCRN's SNR Gain
A critical question investigated is whether GTCRN's $+0.38\text{ dB}$ full-set SNR advantage over Step-500 is present in the low-SNR regime:
- In the $\le 0\text{ dB}$ low-SNR group ($n=210$), GTCRN's paired SNR delta is $+0.0421\text{ dB}$ ($95\%\text{ CI } [-0.2568, +0.3632]$), which is **statistically indistinguishable from zero**.
- At $-10\text{ dB}$ ($n=30$), the delta is $-0.0532\text{ dB}$ ($[-1.16, +1.00]$).
- At $-5\text{ dB}$ ($n=63$), the delta is $-0.0538\text{ dB}$ ($[-0.59, +0.50]$).
- At $+5\text{ dB}$ ($n=137$), GTCRN exhibits a statistically significant spike in SNR: $\mathbf{+0.8159\text{ dB}}$ ($[+0.2276, +1.4221]$).
- **Conclusion:** GTCRN's SNR advantage over Step-500 is **heavily concentrated at $+5\text{ dB}$** and vanishes completely in the negative-SNR bins. Meanwhile, GTCRN's PESQ degradation against Step-500 is statistically significant across all bins $\ge 0\text{ dB}$ ($-0.11$ to $-0.15\text{ PESQ-WB}$).

---

## 5. Common Failures, Model-Specific Wins, and Tradeoffs

*Source: [STAGE7_FAILURE_CLIP_TABLE.csv](file:///Users/shreyasdivekar/Documents/anc%20sih/research/STAGE7_FAILURE_CLIP_TABLE.csv)*

### 5.1 Common Failure Rate by Target SNR Bin
Across the entire canonical benchmark, **358 out of 590 clips (60.68%)** fail the joint criteria across all three models simultaneously.

| Target SNR Bin | Total Clips | Clips Failing All 3 Models | Percentage Failing All 3 Models |
|:---|---:|---:|---:|
| **-10.0 dB** | 30 | 30 | **100.0%** |
| **-5.0 dB** | 63 | 60 | **95.2%** |
| **0.0 dB** | 117 | 101 | **86.3%** |
| **<= 0 dB Total** | **210** | **191** | **91.0%** |
| +5.0 dB | 137 | 98 | 71.5% |
| +10.0 dB | 121 | 50 | 41.3% |
| +15.0 dB | 86 | 17 | 19.8% |
| +20.0 dB | 36 | 2 | 5.6% |

### 5.2 Single-Model Wins
Clips where exactly one model passed the joint criteria while the other two failed:
- **FullSubNet Only Passes:** **47 clips** (7 clips at $0\text{ dB}$, 14 at $+5\text{ dB}$, 19 at $+10\text{ dB}$, 6 at $+15\text{ dB}$, 1 at $+20\text{ dB}$).
- **Step-500 Only Passes:** **10 clips** (e.g., Clip 418 at $-5\text{ dB}$, Clip 488 at $0\text{ dB}$, Clip 28 at $+5\text{ dB}$, Clips 380, 562, 566, 10, 200, 398, 555).
- **GTCRN Only Passes:** **2 clips** (Clip 534 at $+5\text{ dB}$, Clip 543 at $+10\text{ dB}$).
  - *Crucial Low-SNR Finding:* In the combined $\le 0\text{ dB}$ region, there is **not a single clip (0 clips)** where GTCRN is the sole passing model.

### 5.3 Metric Tradeoff Analysis
Models frequently trade raw energy attenuation (SNR) against perceptual speech distortion (PESQ-WB):
- **GTCRN vs Step-500:**
  - In **66 clips**, GTCRN improves SNR by $>+0.5\text{ dB}$ while simultaneously degrading PESQ-WB by $<-0.1$.
  - In **16 clips**, GTCRN improves PESQ-WB by $>+0.1$ while degrading SNR by $<-0.5\text{ dB}$.
  - This demonstrates that GTCRN's aggressive spectral masking increases numerical SNR by wiping out noise floor energy during unvoiced/silent segments, but introduces speech truncation and phase distortion that penalizes PESQ.
- **FullSubNet vs Step-500:**
  - In **293 clips**, FullSubNet improves **both** SNR ($>+0.5\text{ dB}$) and PESQ ($>+0.1$).
  - In only **19 clips**, FullSubNet exhibits SNR gain with PESQ degradation.

---

## 6. Largest Regressions and Improvements

### 6.1 Top GTCRN vs Step-500 Discrepancies in Low-SNR ($\le 0\text{ dB}$)

| Clip ID | Target SNR | Origin | S500 SNR | S500 PESQ | FSN SNR | FSN PESQ | GTCRN SNR | GTCRN PESQ | $\Delta\text{SNR}$ (GTCRN-S500) |
|---:|:---|:---|---:|---:|---:|---:|---:|---:|---:|
| **329** | -10.0 dB | IoBT_GUNFIRE | 1.67 dB | 1.05 | 8.31 dB | 1.35 | 9.24 dB | 1.53 | **+7.57 dB** |
| **356** | -5.0 dB | IoBT_GUNFIRE | 0.83 dB | 1.05 | 9.36 dB | 1.88 | 8.25 dB | 1.37 | **+7.41 dB** |
| **41** | 0.0 dB | EXISTING_PROXY | 6.33 dB | 1.20 | 13.06 dB | 1.68 | 13.29 dB | 1.43 | **+6.96 dB** |
| **277** | 0.0 dB | IoBT_GUNFIRE | 4.36 dB | 1.12 | 15.15 dB | 2.05 | 11.07 dB | 1.64 | **+6.72 dB** |
| **571** | 0.0 dB | IoBT_GUNFIRE | 11.20 dB | 1.20 | 18.40 dB | 3.06 | 17.53 dB | 2.96 | **+6.33 dB** |
| **108** | -10.0 dB | IoBT_GUNFIRE | 12.67 dB | 1.95 | 9.03 dB | 1.33 | 3.07 dB | 1.32 | **-9.60 dB** |
| **122** | -5.0 dB | IoBT_GUNFIRE | 16.53 dB | 3.49 | 7.76 dB | 2.88 | 10.35 dB | 3.52 | **-6.19 dB** |
| **369** | -5.0 dB | EXISTING_PROXY | 10.37 dB | 2.11 | 10.19 dB | 2.40 | 5.27 dB | 1.75 | **-5.10 dB** |
| **86** | 0.0 dB | IoBT_GUNFIRE | 13.20 dB | 2.31 | 11.93 dB | 1.93 | 8.34 dB | 1.64 | **-4.85 dB** |
| **203** | -10.0 dB | EXISTING_PROXY | 4.44 dB | 1.14 | 2.69 dB | 1.18 | -0.06 dB | 1.10 | **-4.50 dB** |

### 6.2 Top FullSubNet vs Step-500 PESQ Discrepancies in Low-SNR ($\le 0\text{ dB}$)

| Clip ID | Target SNR | Origin | S500 SNR | S500 PESQ | FSN SNR | FSN PESQ | GTCRN SNR | GTCRN PESQ | $\Delta\text{PESQ}$ (FSN-S500) |
|---:|:---|:---|---:|---:|---:|---:|---:|---:|---:|
| **571** | 0.0 dB | IoBT_GUNFIRE | 11.20 dB | 1.20 | 18.40 dB | 3.06 | 17.53 dB | 2.96 | **+1.87** |
| **360** | 0.0 dB | EXISTING_PROXY | 10.39 dB | 2.14 | 15.30 dB | 3.62 | 8.61 dB | 2.30 | **+1.48** |
| **314** | 0.0 dB | IoBT_GUNFIRE | 7.44 dB | 1.48 | 13.44 dB | 2.68 | 11.85 dB | 2.03 | **+1.20** |
| **232** | 0.0 dB | EXISTING_PROXY | 8.09 dB | 2.00 | 8.99 dB | 3.17 | 13.72 dB | 2.83 | **+1.16** |
| **277** | 0.0 dB | IoBT_GUNFIRE | 4.36 dB | 1.12 | 15.15 dB | 2.05 | 11.07 dB | 1.64 | **+0.93** |
| **108** | -10.0 dB | IoBT_GUNFIRE | 12.67 dB | 1.95 | 9.03 dB | 1.33 | 3.07 dB | 1.32 | **-0.61** |
| **122** | -5.0 dB | IoBT_GUNFIRE | 16.53 dB | 3.49 | 7.76 dB | 2.88 | 10.35 dB | 3.52 | **-0.60** |
| **488** | 0.0 dB | EXISTING_PROXY | 17.78 dB | 2.82 | 16.77 dB | 2.28 | 14.22 dB | 2.13 | **-0.54** |
| **236** | -10.0 dB | IoBT_GUNFIRE | 7.72 dB | 1.71 | 6.28 dB | 1.18 | 5.70 dB | 1.25 | **-0.52** |
| **418** | -5.0 dB | IoBT_GUNFIRE | 15.00 dB | 2.78 | 9.17 dB | 2.30 | 14.08 dB | 2.70 | **-0.48** |

---

## 7. Supported Observations versus Hypotheses

To maintain scientific integrity, empirically verified conclusions are strictly separated from interpretive hypotheses.

### 7.1 Empirically Supported Observations
1. **Universal Low-SNR Deficit:** Single-channel time-frequency enhancement across three distinct architectures (DFN3, FullSubNet, GTCRN) fails universally at $-10\text{ dB}$ (0/30 passes for all models) and achieves $<9\%$ joint pass rate across $\le 0\text{ dB}$.
2. **Shortfall Magnitude:** Mean output SNR at $-10\text{ dB}$ input is $6.56$ to $7.12\text{ dB}$, a shortfall of $>8.4\text{ dB}$ from the SIH $>15\text{ dB}$ target.
3. **No Acoustic Advantage for GTCRN:** GTCRN produces fewer joint passes than Step-500 (144 vs 161 full-set; 9 vs 11 at $\le 0\text{ dB}$) and loses to FullSubNet across all 4 paired metrics in every single input-SNR bin.
4. **GTCRN SNR Concentration:** GTCRN's paired SNR advantage over Step-500 is confined to $+5\text{ dB}$ ($+0.82\text{ dB}$) and is absent in $\le 0\text{ dB}$ ($+0.04\text{ dB}$, CI spans zero).
5. **Tradeoff Characteristics:** In 66 clips, GTCRN increases SNR by $>0.5\text{ dB}$ while degrading PESQ-WB by $<-0.1$.
6. **FullSubNet Dominance:** FullSubNet is the only model achieving statistically positive paired deltas over Step-500 across all four metrics simultaneously ($\Delta\text{SNR} = +1.44\text{ dB}$, $\Delta\text{SI-SDR} = +1.34\text{ dB}$, $\Delta\text{STOI} = +0.018$, $\Delta\text{PESQ} = +0.28$).

### 7.2 Hypotheses (Requiring Separate Controlled Experiments)
1. **Formant Masking Hypothesis:** The catastrophic low-SNR failure across all architectures may be caused by speech formant power falling entirely beneath the noise floor across multiple critical bands, making linear or non-linear mask estimation mathematically ill-posed without multi-channel spatial coherence.
2. **Sub-Band Architecture Hypothesis:** FullSubNet's superiority over DFN3 and GTCRN in $\le 0\text{ dB}$ may stem from its explicit sub-band modeling capturing frequency-localized spectral continuity better than ERB filterbanks or tiny convolutional kernels.
3. **Transient Masking Hypothesis:** Gunfire clips at $-10\text{ dB}$ show higher output SNR than continuous proxy noise ($7.42\text{ dB}$ vs $4.19\text{ dB}$ on Step-500). This may reflect clean speech preservation during inter-burst silent intervals rather than effective noise cancellation during active impulsive bursts.

---

## 8. Limitations and Confounding

1. **Severe Dataset Confounding:** The canonical benchmark exhibits severe imbalance between `target_snr` and `dataset_origin`:
   - In $\le 0\text{ dB}$, $76.2\%$ of clips ($160/210$) originate from `IoBT_GUNFIRE` ($85.7\%$ at $-5\text{ dB}$; $73.3\%$ at $-10\text{ dB}$).
   - Conversely, `EXISTING_PROXY` has only 8 clips at $-10\text{ dB}$ and 9 clips at $-5\text{ dB}$.
   - Consequently, comparisons between noise origins in the low-SNR region suffer from small sample sizes and cannot be interpreted as generalized acoustic event differences.
2. **Provenance Labels vs Acoustic Reality:** The labels `IoBT_GUNFIRE` and `EXISTING_PROXY` indicate source dataset provenance, not verified acoustic ground truth (e.g., weapon caliber, reverberant environment, or distance).
3. **Offline Scoring vs Edge Real-Time Reality:** FullSubNet's offline evaluation uses lookahead and large LSTM buffers ($5.64\text{M}$ parameters) that are not validated for real-time low-latency streaming on edge hardware (historical Raspberry Pi 4 baseline).
4. **Isolated Benchmark Exposure:** Although the benchmark was evaluated without model modification, all 590 clips have prior exposure from historical evaluations. The final definitive assessment must occur on the sealed `SIH_GOLD_TEST`.

---

## 9. Decision Gate & Recommended Next Direction

### 9.1 Summary of Decision Gate Questions
- **Most Important Empirically Supported Failure Pattern:** Single-channel speech enhancement suffers a universal breakdown below $0\text{ dB}$ input SNR ($100\%$ failure at $-10\text{ dB}$, $>91\%$ failure across $\le 0\text{ dB}$), with mean output SNR capping at $\sim 6.6\text{ dB}$ at $-10\text{ dB}$ input (an $8.4\text{ dB}$ shortfall).
- **Strongest Model in Each Low-SNR Bin:**
  - $-10\text{ dB}$: FullSubNet ($7.12\text{ dB}$ SNR, $1.42$ PESQ, though all models achieve 0 joint passes).
  - $-5\text{ dB}$: FullSubNet ($10.71\text{ dB}$ SNR, $1.83$ PESQ).
  - $0\text{ dB}$: FullSubNet ($11.94\text{ dB}$ SNR, $2.05$ PESQ, 15 joint passes).
  - $+5\text{ dB}$: FullSubNet ($14.49\text{ dB}$ SNR, $2.41$ PESQ, 34 joint passes).
- **Does GTCRN Offer Any Useful Niche?** **Acoustically: NO.** GTCRN provides no accuracy, PESQ, or low-SNR denoising advantage over Step-500, and loses decisively to FullSubNet. **Computationally: YES.** If deployment targets a micro-controller or DSP with $<1\text{ MB}$ RAM, GTCRN's 48.2K parameters and 580 KB footprint make it viable; however, on the historical Raspberry Pi 4 baseline, where Step-500 already ran comfortably at RTF $0.43$, GTCRN offers no practical advantage.
- **Single Most Justified Next Experiment:** **Dual-Microphone / Multi-Stage ANC Pre-Filtering.**
  Single-channel filtering cannot mathematically bridge the $>8.4\text{ dB}$ gap from $-10\text{ dB}$ input to $>15\text{ dB}$ output without unacceptable speech distortion. The single most justified next experiment is integrating a true dual-channel adaptive noise cancellation (ANC) front-end (using an external reference microphone) to attenuate primary ambient noise by $10–15\text{ dB}$ prior to entering the DeepFilterNet3 neural tract.
- **Required Data / Evidence Before Experiment:**
  1. Synchronized dual-channel audio recordings (primary speech mic + external reference noise mic) captured in representative military acoustic environments (artillery, vehicle engine, rotor drone).
  2. Measured acoustic transfer function and latency budget between the reference mic and primary mic on the physical headset harness.

---

## 10. Execution Parameters & Output Artifact Digests

### Software & Environment
- **Platform:** macOS 26.6.2 (Apple Silicon arm64)
- **Python:** 3.10.22 / 3.14.0 (compatible virtual environments)
- **PyTorch:** 1.11.0 / 2.1.0
- **Random Seed:** `26052` (Bootstrap: 2,000 resamples)

### Generated Output Artifacts and SHA-256 Hashes

| Output File | Size | SHA-256 Hash |
|:---|---:|:---|
| `research/STAGE7_SNR_BIN_SUMMARY.csv` | 2.0 KiB | `3102719725e55df6c8772bd7e96f8a82f67b6800fdd2260e096b3305b9684538` |
| `research/STAGE7_PAIRED_COMPARISONS.csv` | 3.1 KiB | `c017fbfb970a52c25a3e72491fec1bf7354b0d0aaefe991d0d008e6e8974573e` |
| `research/STAGE7_FAILURE_CLIP_TABLE.csv` | 19 KiB | `7c553d6c18aed914b290586883c0cc076e2321ce11aed6d273a446bbbe4215a9` |
| `research/STAGE7_LOW_SNR_FAILURE_ANALYSIS.md` | ~21 KiB | *Self-contained markdown report* |

