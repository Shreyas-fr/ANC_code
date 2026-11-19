# SIH 26052 — Stage 11.2.15: Benchmark Integrity and Statistical Validity Audit

**Audit Date:** November 13, 2026  
**Auditor:** Antigravity Forensic Audit Agent (SIH 26052 Technical Recovery)  
**Status:** COMPLETE (Methodological & Scientific Baseline Correction)  
**Classification:** Scientific Governance and Statistical Audit  

---

## Executive Summary

This forensic audit investigates the empirical foundations of SIH 26052's speech enhancement benchmarks, evaluation sets, and statistical validation claims. Two major scientific issues are addressed:
1. **Unprocessed Baseline Discrepancies**: The project literature contains three conflicting figures for the raw unprocessed noisy mixture baseline: **$4.29\text{ dB}$ SNR / $1.761$ PESQ**, **$6.49\text{ dB}$ / $6.21\text{ dB}$ SNR / $1.60$ PESQ**, and **$5.6\text{ dB}$ SNR**. This audit traces each number to its precise script and mathematical formula.
2. **Benchmark Circularity and Overfitting Risk**: The 590-clip canonical validation set (`runs/sih26052_canonical_validation/manifest.csv`) has been repeatedly utilized for candidate selection, hyperparameter tuning, loss function ablations, and ensemble weighting across more than 20 model variants. It is formally **reclassified as a development benchmark, NOT an independent confirmatory validation set**.
3. **Statistical Resampling Flaws**: Prior bootstrap power simulations in Stage 11.2 assumed independent and identically distributed (i.i.d.) clip sampling ($N = 590$ or $840$), completely ignoring **speaker clustering (24 participants)** and **noise-session correlation**. This severely overestimated statistical power and underestimated confidence intervals.

---

## 1. Forensic Trace of the Unprocessed Noisy Baselines

Three distinct figures for unprocessed noisy speech have appeared across project documents:

| Reported Baseline | Documents Where Found | Evaluation Dataset | Underlying Script & Formula | Methodological Cause | Forensic Status |
|:---|:---|:---|:---|:---|:---|
| **$4.29\text{ dB}$ SNR / $1.761$ PESQ** | `MASTER_SIH_COMPLIANCE.md` (Table 8), `STAGE11_2_3_SUMMARY.md` | 590-clip Canonical Validation Set | `scripts/evaluate_dfn3_canonical.py` using `active_speech_power()` | Calculates SNR using only active speech frames ($30\text{ ms}$ windows with power $> 0.1\%$ of peak speech power). Errors in silent pauses are excluded from speech power numerator. | **AUTHORITATIVE CANONICAL BASELINE** (Re-verified) |
| **$6.49\text{ dB}$ SNR ($6.21\text{ dB}$ Gunfire)** | `runs/sih26052_canonical_validation/evaluation/summary.csv`, `subgroup_metrics.csv` | 590-clip Canonical Validation Set | `src/enhance/evaluate.py` / `freeze_canonical_val.py` | Calculates global un-gated SNR: $10 \log_{10} \frac{\sum x^2}{\sum (y - x)^2}$. Includes low-energy speech tails and pauses in total power. Gunfire subset specifically averaged $6.29\text{ dB}$; Polar-D models produced $6.21\text{ dB}$. | **HISTORICAL UN-GATED METRIC** (Documented) |
| **$5.6\text{ dB}$ SNR** | `results/results_table.md`, `per_category.md` (Sep 29) | Early 1,200-clip synthetic dataset | `scripts/benchmark_pi.py` | Represents the **SI-SDR improvement at -5 dB input SNR** in early synthetic noise ablations; misquoted as baseline SNR in subsequent presentation slides. | **ERRONEOUS CITATION (RETRACTED)** |

### 1.1 Mathematical Reconciliation
- When evaluating 48 kHz / 16 kHz noisy speech, standard ITU-T P.56 speech voltmeter or active energy gating isolates pauses between phonemes. 
- In `scripts/evaluate_dfn3_canonical.py`:
  $$\text{SNR}_{\text{active}} = 10 \log_{10}\left(\frac{P_{\text{active\_speech}}}{P_{\text{error}}}\right) = \mathbf{4.29\text{ dB}}$$
  This accurately penalizes stationary and non-stationary background noise present during pauses and quiet vowels.
- In contrast, un-gated accumulation across the entire utterance yields $\mathbf{6.49\text{ dB}}$ globally, and $\mathbf{6.29\text{ dB}}$ on the gunfire subset.
- The authoritative canonical baseline for all Track A and Track B evaluations is officially locked as:
  $$\mathbf{4.29\text{ dB}\ \text{SNR}},\quad \mathbf{3.58\text{ dB}\ \text{SI-SDR}},\quad \mathbf{0.803\ \text{STOI}},\quad \mathbf{1.761\ \text{PESQ-WB}}$$

---

## 2. Re-Classification of the 590-Clip Canonical Benchmark

### 2.1 The Problem of Circular Model Selection
The 590-clip dataset (`runs/sih26052_canonical_validation/manifest.csv`, SHA-256 `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`) consists of 442 IoBT gunfire clips and 148 proxy noise clips. 

Historical code inspection shows that this exact set was used to:
1. Select between Polar-D V1, V2, Proxy-Only, Mixed-50, and Gunfire-Heavy checkpoints (Sep 29-30).
2. Tune the complex mask loss weights in `loss_ablation.py` (Sep 30).
3. Evaluate and select DeepFilterNet3 Step-500 against Step-550 and base DFN3 (Nov 9).
4. Perform the block size / context window sweep ($250\text{ ms}$ vs $500\text{ ms}$) in `evaluate_dfn3_streamed_canonical.py` (Nov 10).
5. Optimize the ensemble weights (0.15 Step-500 / 0.70 FullSubNet / 0.15 GTCRN) in `summarize_stage8_ensembles.py` (Nov 13).

### 2.2 Reclassification Finding
Because this dataset was used iteratively to guide architectural choices, select checkpoints, and tune ensemble blending weights, it is **statistically in-sample for model selection**. 

Reporting performance on the 590-clip set as "validated generalization" violates fundamental principles of machine learning validation. 
- **Former Label:** `CANONICAL VALIDATION SET`
- **Reclassified Label:** **`DEVELOPMENT BENCHMARK & MODEL SELECTION SET`**
- **Confirmatory Status:** `NON-CONFIRMATORY`

### 2.3 Status of the True Held-Out Gold Dataset
The project contains an isolated, sealed gold dataset:
- Location: `data/SIH_GOLD_TEST`
- SHA-256: `46236aef9af38056e08f296ac8c498dac888a85fb4b1ff9f371879c49670b0c9`
- Current Access State: **SEALED & UNTOUCHED** (`gold_test_read: false`).

No independent validation has yet occurred. Confirmatory validation can only take place when all models and hyperparameter selections are irrevocably frozen, and the sealed gold dataset is evaluated in a single, blind, audited run.

---

## 3. Statistical Validity Audit: Clustered Variance and Bootstrap Flaws

### 3.1 Failure of the i.i.d. Assumption in Speech Evaluation
In `scripts/reproduce_power_simulations.py`, statistical power was simulated by executing 10,000 bootstrap draws directly on individual clips:
```python
sample = rng.choice(pop, size=n_bin, replace=True)
```
This naive resampling treats each audio clip as an independent and identically distributed (i.i.d.) statistical unit. In reality, speech enhancement evaluation violates the i.i.d. assumption in two fundamental ways:
1. **Speaker Clustering**: Multiple clips originate from the same human speaker. In the Stage 11 qualification protocol, 840 clips are collected from only **24 participants** (averaging 35 clips per speaker). Clips from a single speaker share fundamental frequency $F_0$, vocal tract transfer functions, accent, and cadence.
2. **Noise-Session Clustering**: Multiple clips are mixed with the same background noise recording or share room impulse response (RIR) acoustic characteristics.

### 3.2 Effective Sample Size Reduction
When observations are clustered, the effective sample size $N_{\text{eff}}$ is defined by:
$$N_{\text{eff}} = \frac{N}{1 + (m - 1)\rho_{\text{ICC}}}$$
where:
- $N$ is the total number of clips ($N = 840$),
- $m$ is the average cluster size ($m = 840 / 24 = 35$ clips per speaker),
- $\rho_{\text{ICC}}$ is the Intraclass Correlation Coefficient (typically $0.15 - 0.35$ in acoustic speaker datasets).

For an empirical $\rho_{\text{ICC}} = 0.25$:
$$N_{\text{eff}} = \frac{840}{1 + (35 - 1) \times 0.25} = \frac{840}{1 + 8.5} = \frac{840}{9.5} \approx \mathbf{88.4}$$
The true statistical information content of 840 clips across 24 speakers is equivalent to **less than 90 independent observations**!

Treating $N = 840$ as independent artificially narrows confidence intervals by a factor of $\sqrt{9.5} \approx 3.1$, leading to false claims of extreme statistical power (>99%) and severely inflated Type I error rates.

### 3.3 Winner's Curse / Model Selection Bias
In Stage 8 and Stage 11, more than 20 candidate model variants and ensemble combinations were compared on the same 590 clips. Selecting the top-performing candidate (e.g. Primary Ensemble with $+1.86\text{ dB}$ SNR gain) without multiplicity adjustment introduces severe selection bias ("winner's curse"). The reported gain is an optimistic upper bound and will inevitably regress upon genuine held-out validation.

---

## 4. Authoritative Statistical Recovery Plan

To restore rigorous scientific validity for Stage 11 physical qualification, the statistical evaluation methodology must be overhauled:

### 4.1 Hierarchical Linear Mixed-Effects Model (LMM)
Primary hypothesis testing must be conducted using a Linear Mixed-Effects Model specifying random intercepts for human speakers and noise sessions:
$$\Delta Y_{ijk} = \beta_0 + \beta_1 \cdot \text{Treatment}_k + u_{\text{speaker}, i} + v_{\text{noise}, j} + \epsilon_{ijk}$$
where:
- $\Delta Y_{ijk}$ is the paired metric difference (e.g. $\text{SNR}_{\text{enhanced}} - \text{SNR}_{\text{unprocessed}}$),
- $\beta_0$ is the fixed overall enhancement effect,
- $u_{\text{speaker}, i} \sim \mathcal{N}(0, \sigma_{\text{speaker}}^2)$ accounts for speaker-level correlation,
- $v_{\text{noise}, j} \sim \mathcal{N}(0, \sigma_{\text{noise}}^2)$ accounts for background noise correlation,
- $\epsilon_{ijk} \sim \mathcal{N}(0, \sigma_{\epsilon}^2)$ is the residual error.

### 4.2 Clustered Block Bootstrap Resampling
When non-parametric confidence intervals are reported, resampling must be performed at the **speaker level**, not the clip level:
1. Resample 24 speakers with replacement from the pool of 24 participants.
2. Include all clips belonging to the selected speakers in the bootstrap replicate.
3. Compute the paired mean metric difference across the clustered replicate.
4. Repeat for $B = 10,000$ iterations to construct cluster-robust $95\%$ confidence intervals.

### 4.3 Multiplicity Control
All confirmatory tests must apply family-wise error rate (FWER) control via the **Holm-Bonferroni step-down procedure** or False Discovery Rate (FDR) control via **Benjamini-Hochberg** across all evaluated metrics (SNR, SI-SDR, STOI, PESQ) and acoustic sub-bins.

---

## 5. Summary of Controlled Terminology Updates

| Artifact / Concept | Historical Description | Controlled Status | Methodological Rule |
|:---|:---|:---:|:---|
| `runs/sih26052_canonical_validation/manifest.csv` | "Authoritative Canonical Validation Set" | **`DEVELOPMENT BENCHMARK`** | Strictly for development and model selection; not valid for final qualification claims. |
| `data/SIH_GOLD_TEST` | "Sealed Gold Test Set" | **`CONFIRMATORY HOLDOUT`** | Sealed until physical qualification; to be evaluated strictly once. |
| Parametric Power >99% | "Verified Study-Wide Statistical Power" | **`RETRACTED`** | Invalidated by un-clustered i.i.d. assumption and empirical variance underestimation. |
| Clustered Power Plan | "Proposed Speaker-Clustered LMM" | **`STATICALLY DERIVED`** | Authoritative protocol for future Stage 11 confirmatory analysis. |

