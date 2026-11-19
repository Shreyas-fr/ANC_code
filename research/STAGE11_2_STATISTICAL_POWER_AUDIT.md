# SIH 26052 — Stage 11.2: Independent Statistical Power & Multiple-Testing Audit

**Document Version:** 1.0.0 · **Date:** 2026-11-13  
**Status:** Methodological & Statistical Review · **Pre-Collection Phase**  
**Execution Boundary:** Independent verification of statistical assumptions, sample sizing, empirical variance, and family-wise error rate control.

---

## 1. Executive Summary & Purpose of Audit

During the Stage 11.1 readiness review, preliminary sample sizing suggested that $n = 240$ clips per SNR bin would achieve $>99\%$ statistical power for paired comparisons at $\alpha = 0.05$. 

This audit provides an independent, rigorous re-evaluation of that claim using:
1. **Empirical Paired Variance:** Extracted directly from the 590-clip canonical validation benchmarks in Stage 7 (`STAGE7_PAIRED_COMPARISONS.csv`) and Stage 8 (`STAGE8_ENSEMBLE_PAIRED_COMPARISONS.csv`).
2. **Multiple-Comparison Corrections:** Rigorous evaluation under Family-Wise Error Rate (FWER via Bonferroni and Holm-Bonferroni) and False Discovery Rate (FDR via Benjamini-Hochberg) across candidate model comparisons and metric combinations.
3. **Effect Size Calibration:** Explicit identification of the Minimum Detectable Effect (MDE) at $80\%$ and $90\%$ statistical power.

### Key Finding:
- The initial Stage 11.1 assumption of $\sigma_{\Delta} \approx 1.2\text{ dB}$ was overly optimistic; the true empirical paired standard deviation observed across models is **$\sigma_{\Delta\text{SNR}} = 2.45 - 3.21\text{ dB}$** and **$\sigma_{\Delta\text{PESQ}} = 0.32 - 0.42$**.
- At $n = 240$ per bin, subtle differences ($\Delta\text{SNR} \le 0.30\text{ dB}$ or $\Delta\text{PESQ} \le 0.05$) are **underpowered** ($<50\%$ power) under strict study-wide FWER control.
- However, for operationally meaningful effect sizes ($\Delta\text{SNR} \ge 0.75\text{ dB}$ and $\Delta\text{PESQ} \ge 0.10$), $n = 240$ per bin provides **$>89.5\%$ power under the strictest study-wide Bonferroni correction**, and **$>99\%$ power under FDR control**. For the observed gains of FullSubNet/Ensemble over Step-500 ($\Delta\text{SNR} = +1.44\text{ dB}$, $\Delta\text{PESQ} = +0.28$), statistical power is **$100.0\%$**.

---

## 2. Empirical Variance Bounds from Canonical Benchmarks

In paired acoustic evaluations, the test statistic depends on the variance of the paired differences:
$$\sigma_{\Delta}^2 = \operatorname{Var}(Y_{\text{cand}} - Y_{\text{ref}}) = \sigma_{\text{cand}}^2 + \sigma_{\text{ref}}^2 - 2 \rho \sigma_{\text{cand}} \sigma_{\text{ref}}$$

Using the 95% bootstrap confidence intervals from Stage 7 and Stage 8:
$$\sigma_{\Delta} \approx \frac{\text{CI}_{\text{upper}} - \text{CI}_{\text{lower}}}{2 \times 1.96} \times \sqrt{N}$$

### Table 2.1: Empirical Paired Standard Deviation ($\sigma_{\Delta}$) by Stratum

| Stratum / SNR Bin | Clip Count ($N$) | FullSubNet vs Step-500 ($\sigma_{\Delta\text{SNR}}$) | FullSubNet vs Step-500 ($\sigma_{\Delta\text{PESQ}}$) | GTCRN vs Step-500 ($\sigma_{\Delta\text{SNR}}$) | GTCRN vs Step-500 ($\sigma_{\Delta\text{PESQ}}$) |
|:---|:---:|:---:|:---:|:---:|:---:|
| **$-10\text{ dB}$ Bin** | $30$ | $2.620\text{ dB}$ | $0.212$ | $3.030\text{ dB}$ | $0.221$ |
| **$-5\text{ dB}$ Bin** | $63$ | $2.590\text{ dB}$ | $0.317$ | $2.215\text{ dB}$ | $0.218$ |
| **$0\text{ dB}$ Bin** | $117$ | $2.446\text{ dB}$ | $0.382$ | $1.984\text{ dB}$ | $0.301$ |
| **$+5\text{ dB}$ Bin** | $137$ | $3.101\text{ dB}$ | $0.418$ | $2.310\text{ dB}$ | $0.342$ |
| **Low-SNR Aggregate ($\le 0\text{ dB}$)** | $210$ | $2.506\text{ dB}$ | $0.341$ | $2.241\text{ dB}$ | $0.288$ |
| **Full Set Aggregate** | $590$ | $3.208\text{ dB}$ | $0.407$ | $2.512\text{ dB}$ | $0.354$ |

*Empirical Modeling Baseline:* For conservative power analysis, we set **$\sigma_{\Delta\text{SNR}} = 2.50\text{ dB}$** (within-bin) / **$3.20\text{ dB}$** (full set), and **$\sigma_{\Delta\text{PESQ}} = 0.35$** (within-bin) / **$0.41$** (full set).

---

## 3. Multiple-Testing Correction Hierarchy

In Stage 11, three candidate models (Primary Ensemble, Secondary Ensemble, Standalone FullSubNet) are compared against the active reference (Deployed Step-500) across 4 objective metrics (SNR, SI-SDR, STOI, PESQ) over 6 SNR bins.

### 3.1 Hypothesis Family Definitions
1. **Per-Bin Family ($M = 12$ hypotheses):**
   - 3 candidate systems vs. Step-500 $\times$ 4 metrics within a single SNR bin.
   - Bonferroni corrected significance threshold:
     $$\alpha_{\text{per-bin}} = \frac{0.05}{12} \approx 0.004167$$
2. **Study-Wide Family ($M = 72$ hypotheses):**
   - 6 SNR bins $\times$ 12 tests per bin = 72 total hypothesis tests.
   - Bonferroni corrected significance threshold:
     $$\alpha_{\text{study-wide}} = \frac{0.05}{72} \approx 0.000694$$
3. **Full-Set Confirmatory Family ($M = 12$ hypotheses):**
   - Full holdout aggregate ($N = 840$ clips), 3 systems $\times$ 4 metrics. $\alpha = 0.004167$.

---

## 4. Exact Statistical Power Curves for Within-Bin Analysis ($n = 240$)

For a paired two-sided normal approximation with sample size $n$, standard error $\text{SE} = \sigma_{\Delta} / \sqrt{n}$, critical threshold $z_{\text{crit}} = \Phi^{-1}(1 - \alpha/2)$, and true mean difference $\Delta$:
$$\text{Power}(\Delta) = \Phi\left(\frac{|\Delta|}{\text{SE}} - z_{\text{crit}}\right) + \Phi\left(-\frac{|\Delta|}{\text{SE}} - z_{\text{crit}}\right)$$

### Table 4.1: Statistical Power for SNR Differences ($\sigma_{\Delta} = 2.50\text{ dB}$, $n = 240$ per bin)

| Delta SNR ($\Delta\text{SNR}$) | Effect Magnitude | Nominal $\alpha = 0.05$ | Per-Bin FWER ($M=12$, $\alpha=0.00417$) | Study-Wide FWER ($M=72$, $\alpha=0.000694$) | Status & Interpretation |
|:---:|:---:|:---:|:---:|:---:|:---|
| **$0.20\text{ dB}$** | Negligible | $23.6\%$ | $5.1\%$ | $1.5\%$ | Highly underpowered |
| **$0.30\text{ dB}$** | Small | $46.0\%$ | $15.7\%$ | $6.3\%$ | Underpowered |
| **$0.50\text{ dB}$** | Moderate | $87.3\%$ | $59.2\%$ | $38.5\%$ | Marginal under FWER |
| **$0.75\text{ dB}$** | Substantial | **$99.6\%$** | **$96.3\%$** | **$89.5\%$** | **Adequately powered ($\ge 80\%$)** |
| **$1.00\text{ dB}$** | Large | **$100.0\%$** | **$100.0\%$** | **$99.7\%$** | **Fully powered ($> 99\%$)** |
| **$1.44\text{ dB}$** | Observed FullSubNet Gain | **$100.0\%$** | **$100.0\%$** | **$100.0\%$** | **Fully powered ($100.0\%$)** |

### Table 4.2: Statistical Power for PESQ Differences ($\sigma_{\Delta} = 0.35$, $n = 240$ per bin)

| Delta PESQ ($\Delta\text{PESQ}$) | Effect Magnitude | Nominal $\alpha = 0.05$ | Per-Bin FWER ($M=12$, $\alpha=0.00417$) | Study-Wide FWER ($M=72$, $\alpha=0.000694$) | Status & Interpretation |
|:---:|:---:|:---:|:---:|:---:|:---|
| **$0.03$** | Negligible | $26.8\%$ | $6.4\%$ | $2.0\%$ | Highly underpowered |
| **$0.05$** | Small | $60.0\%$ | $25.7\%$ | $11.9\%$ | Underpowered |
| **$0.10$** | Moderate | **$99.3\%$** | **$94.1\%$** | **$85.0\%$** | **Adequately powered ($\ge 80\%$)** |
| **$0.15$** | Substantial | **$100.0\%$** | **$100.0\%$** | **$99.9\%$** | **Fully powered ($> 99\%$)** |
| **$0.20$** | Large | **$100.0\%$** | **$100.0\%$** | **$100.0\%$** | **Fully powered ($100.0\%$)** |
| **$0.28$** | Observed FullSubNet Gain | **$100.0\%$** | **$100.0\%$** | **$100.0\%$** | **Fully powered ($100.0\%$)** |

---

## 5. Statistical Power for Full Confirmatory Holdout ($N = 840$)

Across the entire 14-speaker confirmatory holdout ($N = 840$ clips), standard error contracts substantially ($\text{SE}_{\text{SNR}} = 3.20 / \sqrt{840} \approx 0.110\text{ dB}$; $\text{SE}_{\text{PESQ}} = 0.41 / \sqrt{840} \approx 0.0141$):

### Table 5.1: Confirmatory Holdout Aggregate Power ($N = 840$ clips)

| Metric | Target Difference ($\Delta$) | Nominal $\alpha = 0.05$ | Full-Set FWER ($M=12$, $\alpha=0.00417$) | Study-Wide FWER ($M=72$, $\alpha=0.000694$) |
|:---|:---:|:---:|:---:|:---:|
| **SNR** | $\Delta = 0.30\text{ dB}$ | $77.6\%$ | $44.1\%$ | $25.0\%$ |
| **SNR** | $\Delta = 0.50\text{ dB}$ | **$99.5\%$** | **$95.2\%$** | **$87.2\%$** |
| **SNR** | $\Delta = 0.75\text{ dB}$ | **$100.0\%$** | **$100.0\%$** | **$100.0\%$** |
| **SNR** | $\Delta = 1.00\text{ dB}$ | **$100.0\%$** | **$100.0\%$** | **$100.0\%$** |
| **PESQ** | $\Delta = 0.05$ | **$94.3\%$** | **$77.8\%$** | **$60.9\%$** |
| **PESQ** | $\Delta = 0.10$ | **$100.0\%$** | **$100.0\%$** | **$100.0\%$** |
| **PESQ** | $\Delta = 0.15$ | **$100.0\%$** | **$100.0\%$** | **$100.0\%$** |

---

## 6. Methodological Protocol Recommendations for Stage 11.2

To ensure that the study's statistical conclusions remain unassailable:

1. **Pre-Specify Primary vs. Secondary Endpoints:**
   - **Primary Confirmatory Endpoint:** Paired difference in Output SNR ($\Delta\text{SNR}$) and PESQ-WB ($\Delta\text{PESQ}$) between Primary Ensemble (15/70/15) and Deployed Step-500 on the full confirmatory holdout ($N = 840$). This restricts the primary hypothesis family to **$M = 2$**, yielding $\alpha_{\text{primary}} = 0.025$. At this threshold, power to detect $\Delta\text{SNR} \ge 0.40\text{ dB}$ is **$95.8\%$**.
2. **False Discovery Rate (FDR) for Exploratory Per-Bin Tests:**
   - Rather than overly conservative study-wide Bonferroni ($M = 72$, $\alpha = 0.000694$), per-bin comparisons must adopt **Benjamini-Hochberg FDR at $q = 0.05$**. This maintains statistical power $>90\%$ for $\Delta\text{SNR} \ge 0.50\text{ dB}$ while guaranteeing rigorous control over false discovery.
3. **Minimum Detectable Effect (MDE) Reporting:**
   - In all future evaluation reports, claims of "no significant difference" must explicitly report the MDE ($0.68\text{ dB}$ at $80\%$ power within individual bins) to prevent claiming equivalence when tests are merely underpowered.

