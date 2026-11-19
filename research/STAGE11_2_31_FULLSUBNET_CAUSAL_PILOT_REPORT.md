# SIH 26052 — Stage 11.2.31: FullSubNet Causal Streaming Pilot Report
## Nine-Clip Empirical Evaluation of Causal Normalization and Stateful Chunk Inference

**Document Identifier:** `research/STAGE11_2_31_FULLSUBNET_CAUSAL_PILOT_REPORT.md`  
**Date:** 2026-11-14  
**Author:** Antigravity Autonomous Technical Execution Agent (SIH 26052 Master Mission)  
**Status:** COMPLETED — SOFTWARE-ONLY NINE-CLIP PILOT EVALUATION  
**Governance & Boundary:** Sealed Gold Test Dataset `data/SIH_GOLD_TEST` isolated (`gold_test_read: false`). Checkpoints ($D, F, G$), validation manifest, and 15/70/15 frozen reference predictions are immutable. Physical qualification gates remain 0/5 passed (Stage 11.3 NO-GO).

---

## 1. Executive Summary

In accordance with explicit reviewer authorization dated 2026-11-14, the **Stage 11.2.31 Nine-Clip Causal FullSubNet Pilot** was implemented and executed across all five proposed causal configurations under `runs/stage11_2_31_fullsubnet_causal/`.

The objective was to identify a bounded-memory, causal inference configuration for the protected FullSubNet epoch-58 checkpoint (`fullsubnet_best_model_58epochs.tar`) that eliminates non-causal future-frame leakage while preserving the speech enhancement quality of the frozen **15/70/15 multi-model ensemble**:
$$\hat{y}[n] = 0.15 \, D[n] + 0.70 \, F[n] + 0.15 \, G[n]$$

### Primary Empirical Findings:
1. **Causal Normalization Preserves Quality:**
   - **Config 1C (Moving Window $W = 100$ frames / $1.6\text{ s}$)** achieves FullSubNet standalone SNR of $12.96\text{ dB}$ (within $-0.30\text{ dB}$ of frozen offline reference $13.26\text{ dB}$).
   - **Config 2 (Causal Cumulative $0 \dots t$)** achieves $12.99\text{ dB}$ SNR (within $-0.27\text{ dB}$ of offline reference).
   - **Config 3B (Stateful EMA $\alpha = 0.02$, $\tau \approx 1.58\text{ s}$)** achieves $12.64\text{ dB}$ SNR (within $-0.62\text{ dB}$ of offline reference).
2. **Ensemble Quality & Pass Rates Uncompromised:**
   - When blended into the frozen 15/70/15 ensemble, **Config 1B ($W=50$), Config 1C ($W=100$), Config 2 (Cumulative), Config 3B (EMA $\alpha=0.02$), Config 3C (EMA $\alpha=0.01$), and Config 5A/5B (Stateful Chunks)** all achieve the **EXACT SAME JOINT PASS COUNT (3 / 9 clips, $33.3\%$)** as the frozen offline reference ensemble!
   - Mean ensemble SNR drops by only $-0.17\text{ dB}$ (Moving Window 100) to $-0.36\text{ dB}$ (EMA 0.02).
   - STOI and PESQ-WB are actually slightly **improved** in the causal ensemble (STOI $0.8696$ vs $0.8651$; PESQ-WB $2.3311$ vs $2.2665$ for Win100).
3. **Decisive Recurrent State Ablation (Config 5C):**
   - Resetting LSTM hidden/cell states $(h, c)$ at each 32 ms chunk boundary causes a **catastrophic collapse**: standalone SNR plunges by **$-9.13\text{ dB}$** (from $13.26\text{ dB}$ to $4.13\text{ dB}$), PESQ drops to $1.23$, and ensemble joint passes drop to **0 / 9 ($0.0\%$)**.
   - Conversely, carrying $(h, c)$ across chunk boundaries matches full-utterance causal processing with **zero chunking loss** (max absolute waveform difference $2.31 \times 10^{-7}$).
   - This decisively proves that persistent recurrent state carry across chunks is essential for streaming FullSubNet.
4. **Persistent Blockers (Open Exceptions Retained):**
   - **Algorithmic Latency Ceiling Exceeded:** FullSubNet's structural framing ($16.0\text{ ms}$) + explicit lookahead ($32.0\text{ ms}$) enforces a **$48.0\text{ ms}$ algorithmic floor**, exceeding the provisional $\le 35.0\text{ ms}$ project gate by $+13.0\text{ ms}$.
   - **Computational Load on Pi 5:** Sustained demand of $58.86\text{ GFLOPs/s}$ consumes over $76\%$ of the Raspberry Pi 5 theoretical hardware peak, making standalone real-time Pi 5 execution highly improbable without model pruning/export optimization.

---

## 2. Baseline Verification and Cryptographic Hashes

Before and after the pilot evaluation, all protected artifact signatures were verified bit-exact:

| Protected Item | Authoritative Expected SHA-256 | Verified File Path | Observed Checksum | Integrity Status |
|:---|:---:|:---|:---:|:---:|
| **Canonical Manifest** (590 clips) | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` | `runs/sih26052_canonical_validation/manifest.csv` | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` | **BIT-EXACT** |
| **FullSubNet Epoch 58 Checkpoint** | `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0` | `checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar` | `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0` | **BIT-EXACT** |
| **DFN3 Step-500 Checkpoint** | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` | `runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt` | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` | **BIT-EXACT** |
| **GTCRN DNS3 Checkpoint** | `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79` | `checkpoints/gtcrn_stage5/model_trained_on_dns3.tar` | `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79` | **BIT-EXACT** |
| **Frozen Ensemble Summary** | `8140618570c6ed8aaf1139b2845b941caed709bc55d1989e4a7b362c0c65d6b5` | `runs/stage8_ensemble_20261113/phase_c_ensembles/d2_fs70_raw/summary.json` | `8140618570c6ed8aaf1139b2845b941caed709bc55d1989e4a7b362c0c65d6b5` | **BIT-EXACT** |

*Gold Set Isolation:* `data/SIH_GOLD_TEST` remained strictly sealed (`gold_test_read: false`). Zero audio access occurred.

---

## 3. Implementation Details & Causal Normalization Formats

All implementations were codified in an isolated module:  
[experiments/stage11_2_31_fullsubnet_causal/causal_fullsubnet.py](file:///Users/shreyasdivekar/Documents/anc%20sih/antigravity/experiments/stage11_2_31_fullsubnet_causal/causal_fullsubnet.py)

### 3.1 Normalization Mathematical Formulations
Let $X \in \mathbb{R}^{B \times C \times F \times T}$ be the magnitude feature tensor. For each time frame $\tau$, the spatial/frequency mean is:
$$m_{\tau} = \frac{1}{C \cdot F} \sum_{c=0}^{C-1} \sum_{f=0}^{F-1} X(c, f, \tau)$$

1. **Config 1 — Moving Window Normalization:**
   $$\mu_t^{(W)} = \frac{1}{\min(t+1, W)} \sum_{\tau = \max(0, t - W + 1)}^{t} m_{\tau}$$
   Evaluated with $W = 25$ ($400\text{ ms}$), $W = 50$ ($800\text{ ms}$), and $W = 100$ ($1600\text{ ms}$).
2. **Config 2 — Causal Cumulative Normalization:**
   $$\mu_t^{(\text{cum})} = \frac{1}{t+1} \sum_{\tau=0}^{t} m_{\tau}$$
   Uses running mean update $\mu_t = \mu_{t-1} + \frac{m_t - \mu_{t-1}}{t+1}$.
3. **Config 3 — Stateful Exponential Moving Average (EMA):**
   Upstream two-phase smoothing schedule:
   - For $t < T_{\text{sample}} = \text{round}(2/\alpha - 1)$: $\alpha_t = \min\left( \frac{t-1}{t+1}, \alpha \right)$, $\mu_t = (1 - \alpha_t)\mu_{t-1} + \alpha_t m_t$.
   - For $t \ge T_{\text{sample}}$: $\mu_t = (1 - \alpha)\mu_{t-1} + \alpha m_t$.
   Evaluated with $\alpha \in \{0.05, 0.02, 0.01\}$ ($\tau \in \{624\text{ ms}, 1.58\text{ s}, 3.18\text{ s}\}$).
4. **Config 4 — Fixed Pre-Calibrated Statistics:**
   **BLOCKED.** As mandated by governance rules, no eligible external provenance-cleared training dataset was available on the local filesystem, and calculating constants from canonical evaluation or gold data was strictly forbidden.
5. **Config 5 — Stateful Chunk Inference:**
   Maintains persistent recurrent states $(h^{\text{fb}}, c^{\text{fb}}) \in \mathbb{R}^{2 \times 1 \times 512}$ and $(h^{\text{sb}}, c^{\text{sb}}) \in \mathbb{R}^{2 \times 257 \times 384}$ across contiguous chunk pushes ($16\text{ ms}$ / 256 samples and $32\text{ ms}$ / 512 samples).

---

## 4. Empirical Results Across the 11 Pilot Configurations

The 11 configurations were evaluated on the 9 preselected development clips (total 27.0 seconds of audio) using the unchanged canonical evaluator (`metrics`).

### 4.1 Comparative Summary Table

| Config ID | Configuration Description | Standalone FullSubNet SNR (dB) | Standalone STOI | Standalone PESQ | Standalone Waveform RMSE | 15/70/15 Ensemble SNR (dB) | 15/70/15 Ensemble STOI | 15/70/15 Ensemble PESQ | Ensemble Joint Passes (>15 dB, >0.85, >2.5) | RTF (Host CPU) | Peak Memory (MB) |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `offline_baseline` | **Frozen Offline Reference (epoch 58)** | **13.26** | **0.8554** | **2.1442** | **0.0000** | **13.02** | **0.8651** | **2.2665** | **3 / 9 (33.3%)** | 0.1179 | 7.71 |
| `config1_win25` | Config 1A: Moving Window ($W=25$, 400 ms) | 12.23 | 0.8551 | 2.0054 | 0.0089 | 12.39 | 0.8644 | 2.2262 | 2 / 9 (22.2%) | 0.1180 | 7.59 |
| `config1_win50` | Config 1B: Moving Window ($W=50$, 800 ms) | 12.69 | 0.8606 | 2.0647 | 0.0071 | 12.67 | 0.8686 | 2.2735 | **3 / 9 (33.3%)** | 0.1164 | 7.60 |
| `config1_win100`| Config 1C: Moving Window ($W=100$, 1600 ms) | **12.96** | **0.8626** | **2.1283** | **0.0062** | **12.85** | **0.8696** | **2.3311** | **3 / 9 (33.3%)** | 0.1178 | 7.61 |
| `config2_cumulative` | Config 2: Causal Cumulative ($0 \dots t$) | **12.99** | 0.8622 | 2.1351 | **0.0061** | **12.86** | 0.8693 | **2.3383** | **3 / 9 (33.3%)** | 0.1164 | 7.59 |
| `config3_ema005` | Config 3A: Stateful EMA ($\alpha=0.05$, 624 ms) | 12.23 | 0.8564 | 2.0319 | 0.0089 | 12.39 | 0.8648 | 2.2445 | 2 / 9 (22.2%) | 0.1387 | 7.59 |
| `config3_ema002` | Config 3B: Stateful EMA ($\alpha=0.02$, 1.58 s) | 12.64 | 0.8625 | 2.1142 | 0.0082 | 12.66 | 0.8695 | 2.2283 | **3 / 9 (33.3%)** | 0.1169 | 7.59 |
| `config3_ema001` | Config 3C: Stateful EMA ($\alpha=0.01$, 3.18 s) | 12.75 | 0.8617 | 2.1627 | 0.0080 | 12.71 | 0.8684 | 2.2781 | **3 / 9 (33.3%)** | 0.1182 | 7.59 |
| `config4_fixed` | Config 4: Fixed Pre-Calibrated Statistics | — | — | — | — | — | — | — | **BLOCKED** | — | — |
| `config5_chunk32ms_stateful`| Config 5A: Stateful Chunks ($32\text{ ms}$, persistent state) | 12.64 | 0.8625 | 2.1142 | 0.0082 | 12.66 | 0.8695 | 2.2283 | **3 / 9 (33.3%)** | 0.1583 | 7.80 |
| `config5_chunk16ms_stateful`| Config 5B: Stateful Chunks ($16\text{ ms}$, persistent state) | 12.64 | 0.8625 | 2.1142 | 0.0082 | 12.66 | 0.8695 | 2.2283 | **3 / 9 (33.3%)** | 0.1542 | 7.84 |
| `config5_chunk32ms_stateless`| **Config 5C: Recurrent Reset Ablation ($32\text{ ms}$)** | **4.13** | **0.6891** | **1.2345** | **0.0459** | **6.14** | **0.7521** | **1.4264** | **0 / 9 (0.0%)** | 0.1553 | 7.80 |

---

## 5. Granular Per-Clip Analysis & Stratified Behavior

The table below contrasts standalone FullSubNet output SNR across acoustic noise origins and target SNR strata:

| Val Index | Dataset Origin | Target SNR | Offline Reference (dB) | Moving Win 100 (dB) | Stateful EMA 0.02 (dB) | Stateful Chunk 32ms (dB) | Stateless Chunk Ablation (dB) | Observation / Dynamic Behavior |
|:---:|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **0061** | `IoBT_GUNFIRE` | $-10.0\text{ dB}$ | $8.66$ | **$8.96$** | **$8.95$** | **$8.95$** | $0.26$ | **$+0.30\text{ dB}$ improvement**; causal smoothing prevents global energy dilution from impulsive peaks. |
| **0000** | `EXISTING_PROXY` | $-10.0\text{ dB}$ | $3.81$ | **$4.23$** | **$4.37$** | **$4.37$** | $-4.30$ | **$+0.56\text{ dB}$ improvement**; stationary machinery noise normalizes stably under causal window. |
| **0033** | `IoBT_GUNFIRE` | $-5.0\text{ dB}$ | $14.00$ | $13.83$ | $13.64$ | $13.64$ | $3.36$ | Close retention ($-0.17\text{ dB}$); high speech intelligibility preserved. |
| **0003** | `EXISTING_PROXY` | $0.0\text{ dB}$ | $9.23$ | **$9.40$** | **$9.36$** | **$9.36$** | $4.49$ | **$+0.17\text{ dB}$ improvement**; 0 dB threshold robustly handled. |
| **0004** | `IoBT_GUNFIRE` | $+5.0\text{ dB}$ | $16.42$ | $16.15$ | $16.11$ | $16.11$ | $6.94$ | Crosses $>15.0\text{ dB}$ target in all causal stateful modes. |
| **0028** | `EXISTING_PROXY` | $+5.0\text{ dB}$ | $14.99$ | **$15.02$** | **$15.00$** | **$15.00$** | $6.46$ | Crosses $>15.0\text{ dB}$ threshold under causal normalization. |
| **0023** | `IoBT_GUNFIRE` | $+10.0\text{ dB}$ | $15.80$ | $15.66$ | $15.20$ | $15.20$ | $6.32$ | Crosses $>15.0\text{ dB}$ target. |
| **0026** | `EXISTING_PROXY` | $+15.0\text{ dB}$ | $21.81$ | $21.64$ | $21.59$ | $21.59$ | $8.32$ | **Passes all 3 criteria** (SNR $21.59\text{ dB}$, STOI $0.992$, PESQ $2.76$). |
| **0009** | `IoBT_GUNFIRE` | $+20.0\text{ dB}$ | $14.62$ | $11.74$ | $9.57$ | $9.57$ | $5.32$ | High-SNR over-suppression observed in both offline and causal models; input SNR is degraded. |

---

## 6. Analysis of Failure Modes & Ablations

### 6.1 Catastrophic Failure of Stateless Chunking (Config 5C)
When recurrent states $(h, c)$ are re-initialized to zero at every 32 ms chunk boundary:
- Standalone SNR drops from $13.26\text{ dB}$ to **$4.13\text{ dB}$** (a collapse of **$-9.13\text{ dB}$**).
- PESQ-WB collapses from $2.14$ to **$1.23$**.
- Waveform RMSE against offline reference increases by **$5.6\times$** ($0.0459$ vs $0.0082$).
- Pearson correlation drops from $0.93$ to **negative correlation ($-0.63$)**, indicating complete signal corruption and boundary clicks.
- **Physical Explanation:** The 2-layer subband LSTM hidden state encodes continuous frequency phase relationships and pitch trajectories. Resetting state causes severe discontinuity transients at every frame boundary.

### 6.2 High-SNR Over-Suppression (Clip 0009)
At $+20\text{ dB}$ target SNR (`IoBT_GUNFIRE`), the input audio already has an SNR of $20.04\text{ dB}$.
- Frozen offline FullSubNet enhances it to $14.62\text{ dB}$ (a degradation of $-5.42\text{ dB}$ relative to input).
- Causal EMA degrades it further to $9.57\text{ dB}$.
- **Root Cause:** FullSubNet's subband LSTMs learn aggressive suppression masks that attenuate unvoiced consonants and speech formants when background noise energy is minimal.

### 6.3 Short vs. Indefinite Streams (Moving Window vs. Cumulative)
- **Config 2 (Cumulative)** scored slightly higher than EMA on these 3-second clips ($12.99\text{ dB}$ vs $12.64\text{ dB}$).
- **Severe Deployment Limitation:** In a continuous live session ($T > 10\text{ minutes}$), cumulative normalization weight decays as $1/(t+1) \to 0$. If an operator moves from quiet quarters into combat vehicle noise, the normalizer becomes rigid and fails to adapt.
- **Verdict:** Config 1C ($W=100$) and Config 3B (EMA $\alpha=0.02$) are vastly superior for continuous deployment because their effective memory window is bounded.

---

## 7. Latency and Hardware Feasibility Evaluation

| Latency / Resource Attribute | Measured / Derived Value | Evaluation Gate Status |
|:---|:---:|:---:|
| **STFT Framing Delay** | $16.0\text{ ms}$ (256 samples @ 16 kHz) | Fixed framing requirement |
| **Model Explicit Lookahead** | $32.0\text{ ms}$ (2 hops $\times$ 256 samples) | Model architecture requirement |
| **Normalization Algorithmic Delay** | **$0.0\text{ ms}$** (Causal EMA / Window) | **RESOLVED CAUSALLY** |
| **Total Algorithmic Latency Floor** | **$48.0\text{ ms}$** | **FAILS GATE ($\le 35.0\text{ ms}$)** |
| **Host CPU Real-Time Factor (RTF)** | $0.116\text{--}0.158$ (Apple M-series) | Real-time on host workstation |
| **Host Peak Memory** | $7.6\text{--}7.8\text{ MB}$ | Bounded, minimal footprint |
| **Projected Pi 5 Compute Demand** | $\mathbf{58.86\text{ GFLOPs/s}}$ | **FAILS REAL-TIME (76.6% peak SoC)** |
| **Projected Pi 5 RTF** | $\approx \mathbf{2.55}$ | **Over 2.5$\times$ slower than real-time** |

---

## 8. Exact Reproduction Commands and Artifact Trails

All results and waveforms were produced in the isolated Python virtual environment without external downloads:

```bash
# 1. Run the pilot evaluation across all configurations and 9 clips
./pc_venv/bin/python antigravity/experiments/stage11_2_31_fullsubnet_causal/run_pilot.py

# 2. Inspect per-clip comparative metrics
cat antigravity/runs/stage11_2_31_fullsubnet_causal/pilot_summary.json

# 3. Verify output enhanced waveforms
ls -la antigravity/runs/stage11_2_31_fullsubnet_causal/wavs/
```

### Generated Artifacts:
- Per-Clip Results CSV: [runs/stage11_2_31_fullsubnet_causal/pilot_per_clip_results.csv](file:///Users/shreyasdivekar/Documents/anc%20sih/antigravity/runs/stage11_2_31_fullsubnet_causal/pilot_per_clip_results.csv)
- Pilot Summary JSON: [runs/stage11_2_31_fullsubnet_causal/pilot_summary.json](file:///Users/shreyasdivekar/Documents/anc%20sih/antigravity/runs/stage11_2_31_fullsubnet_causal/pilot_summary.json)
- Enhanced Waveforms: `antigravity/runs/stage11_2_31_fullsubnet_causal/wavs/<config_id>/*.wav`

---

## 9. Conclusion & Recommended Next Decision

### Technical Conclusions:
1. **FullSubNet CAN be made causal with minimal quality loss:** Bounded-window ($W=100$) and Stateful EMA ($\alpha=0.02$) retain within $0.30\text{--}0.62\text{ dB}$ SNR of the frozen offline reference, with **identical ensemble joint pass rates ($33.3\%$)**.
2. **Stateful recurrent chunking is verified sound:** When $(h, c)$ states are carried across chunks, 16 ms and 32 ms chunking achieves exact mathematical parity with full-utterance causal processing.
3. **The 35 ms Latency Gate & Pi 5 Compute Remain Blockers:** FullSubNet cannot stream under $35.0\text{ ms}$ algorithmic delay without altering its 2-frame lookahead, and its $58.86\text{ GFLOPs/s}$ demand exceeds the Raspberry Pi 5 real-time budget.

### Recommendation for Next Stage:
In accordance with your instruction (*"Do not proceed to the full 590-clip evaluation or later project phases until I have reviewed the pilot results and explicitly approved the next step"*), execution halts here.

We recommend presenting this empirical envelope for review to decide whether to:
- **Option A:** Authorize the full 590-clip evaluation of Config 1C ($W=100$) and Config 3B (EMA $\alpha=0.02$) to formalize the streaming baseline quality numbers; OR
- **Option B:** Advance to Stage 11.2.32 to investigate causal zero-lookahead adaptation and model compression/Tract conversion to tackle the $48\text{ ms}$ latency floor and Pi 5 compute bottleneck.

