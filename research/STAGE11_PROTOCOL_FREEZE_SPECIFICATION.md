# SIH 26052 — Stage 11: Final Frozen Study Protocol Specification

**Protocol Specification Identifier:** SIH-26052-STG11-FREEZE-v1.0 · **Date:** 2026-11-13  
**Status:** Definitive Frozen Specification · **Pre-Collection Phase**  
**Execution Boundary:** Immutable protocol freeze. All experimental parameters, statistical endpoints, claim boundaries, and gating mechanisms are formally locked. **Zero participant recruitment, zero participant contact, zero audio recording, and zero data collection authorized.**

---

## 1. Executive Summary & Protocol Baseline

This document serves as the definitive, frozen master specification for the SIH 26052 Independent Audio Recording Study. It synthesizes and locks all technical resolutions, statistical proofs, and governance requirements established across Stages 11.1, 11.2, 11.2.1, and 11.2.2.

```
+---------------------------------------------------------------------------------------------------------+
|                                    STAGE 11 MASTER FROZEN ARCHITECTURE                                  |
+--------------------------+---------------------+-------------------------------+------------------------+
| 1. Candidate Systems     | 2. Dual-Track Scope | 3. Confirmatory Endpoints     | 4. Generalization Scope|
+--------------------------+---------------------+-------------------------------+------------------------+
| - Primary Ensemble       | Track A: Offline    | Co-Primary Conjunction (IUT): | - Speaker: PROVEN      |
|   (15% DFN / 70% FS / 15%| (Quality Benchmark) | Delta SNR > 0 AND             | - Noise: PROVEN        |
| - Secondary Ensemble     |                     | Delta PESQ > 0 @ alpha=0.05   | - Room Enclosure:      |
|   (20% DFN / 60% FS / 20%| Track B: Edge Pi 5  | N = 840 confirmatory clips    |   EXPLICITLY EXCLUDED  |
| - Standalone FullSubNet  | (Real-time stream   |                               | - Demographics/Dialect:|
| - Deployed Step-500      |  DFN3 and GTCRN on  | Secondary: Benjamini-Hochberg |   EXPLICITLY EXCLUDED  |
|                          |  Raspberry Pi 5)    |                               |                        |
+--------------------------+---------------------+-------------------------------+------------------------+
```

---

## 2. Frozen Candidate Models & Architecture Tracking

The four evaluated systems are frozen at their verified repository checkpoints:

| Model ID | Formal Candidate Name | Verified Artifact Checkpoint Path | Architecture & Sampling Rate | SHA-256 Checksum | Evaluation Track |
|:---:|:---|:---|:---:|:---:|:---:|
| **SYS_01** | **Primary Ensemble** | DFN3 (15%) + FullSubNet (70%) + GTCRN (15%) | Composite Multi-Rate | N/A (Composite) | Track A (Offline Quality) |
| **SYS_02** | **Secondary Ensemble**| DFN3 (20%) + FullSubNet (60%) + GTCRN (20%) | Composite Multi-Rate | N/A (Composite) | Track A (Offline Quality) |
| **SYS_03** | **Standalone FullSubNet**| `antigravity/checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar` | 5.64M params / 16 kHz | `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0` | Track A (Offline Quality) |
| **SYS_04** | **Deployed DFN3 Step-500**| `antigravity/runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt` | 2.14M params / 48 kHz | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` | Track A & Track B (Edge) |
| **SYS_05** | **GTCRN DNS3 Baseline**| `antigravity/checkpoints/gtcrn_stage5/model_trained_on_dns3.tar` | 48.2K params / 16 kHz | `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79` | Track B (Edge Playout) |

---

## 3. Frozen Statistical Testing Architecture

### 3.1 Primary Confirmatory Endpoint
- **Hypothesis Formulation:** Simultaneous superiority of Primary Ensemble (SYS_01) over Deployed Step-500 (SYS_04) on the 14-speaker confirmatory holdout ($N = 840$ clips):
  $$H_0: (\mu_{\Delta\text{SNR}} \le 0) \;\cup\; (\mu_{\Delta\text{PESQ}} \le 0)$$
  $$H_1: (\mu_{\Delta\text{SNR}} > 0) \;\cap\; (\mu_{\Delta\text{PESQ}} > 0)$$
- **Test Methodology:** One-sided paired Wilcoxon signed-rank test evaluated at level $\alpha = 0.05$ on both $\Delta\text{SNR}$ and $\Delta\text{PESQ}$.
- **Mathematical Multiplicity Protection:** Under the Berger (1982) Intersection-Union Principle, rejecting both sub-hypotheses at $\alpha = 0.05$ guarantees that the family-wise error rate is strictly bounded by $\alpha \le 0.05$ without any Bonferroni penalty.
- **Statistical Power:** Verified at **$100.00\%$** for the observed performance gain ($+1.44\text{ dB}$ SNR, $+0.28$ PESQ) on $N = 840$ holdout clips ($B = 10,000$ iterations).

### 3.2 Secondary Exploratory Endpoints
- **Stratified Bins & Candidate Ablations:** Secondary Ensemble (SYS_02), Standalone FullSubNet (SYS_03), and GTCRN (SYS_05) across discrete SNR bins ($-10, -5, 0, +5, +10, +15\text{ dB}$).
- **Multiplicity Control:** **Benjamini-Hochberg False Discovery Rate (FDR) at $q = 0.05$**.

---

## 4. Frozen Study Design & Claim Boundaries

### 4.1 Cohort & Partitioning Allocation
- **Total Cohort:** 24 consenting adult speakers (12 female, 12 male; 4 balanced regional English accents).
- **Development Set (40%):** 10 speakers ($600$ clean utterances). Used for baseline diagnostic calibration.
- **Confirmatory Holdout (60%):** 14 speakers ($840$ clean utterances). Strictly quarantined and cryptographically sealed prior to model inference.

### 4.2 Strict Claim Boundaries (What the Study Proves and Does Not Prove)
1. **Valid Confirmatory Claims:**
   - Global Model Superiority on Unseen Voices.
   - SNR-Stratified Robustness across discrete operational noise conditions.
   - Speaker-Independent Generalization (0% speaker overlap).
   - Noise-Session Generalization (0% noise stem overlap).
2. **Explicit Negative Scope (Prohibited Confirmatory Claims):**
   - **No Demographic or Gender Superiority Claims:** With only 7 female and 7 male holdout speakers, sample size is insufficient to claim statistically significant gender-specific performance differences. Subgroup breakdowns are descriptive only.
   - **No Regional Dialect / Accent Claims:** With 3–4 speakers per dialect cohort, dialect-specific interaction tests are underpowered ($<20\%$).
   - **No Room-Enclosure Transfer Claims:** Because all speech is captured in a single dry acoustic booth ($RT_{60} \le 120\text{ ms}$), the study proves enhancement in a controlled recording environment, NOT invariance across arbitrary reverberant rooms.

---

## 5. Frozen Acoustic & Signal Chain Specifications

1. **Acoustic Facility:** Certified double-wall booth meeting $RT_{60} \le 120\text{ ms}$ ($125\text{ Hz} - 8\text{ kHz}$) and ambient background noise $L_{\text{Aeq}} \le 25.0\text{ dBA}$ (NC-20 compliant).
2. **Transducer Placement:** Miniature condenser boom microphone rigidly locked at $45^\circ$ azimuth and $2.5\text{ cm} \pm 0.2\text{ cm}$ displacement from mouth corner. Secondary earcup microphone recorded on Channel 2 for future research but excluded from single-channel test feeds.
3. **Audio Interface & ADC:** Synchronous 24-bit / 48.0 kHz linear PCM, shared crystal master clock, $\text{EIN} \le -128.5\text{ dBu}$, inter-channel phase skew $< 5.0\ \mu\text{s}$.
4. **Calibration Standard:** Class 1 acoustic calibrator generating $94.00\text{ dB SPL} \pm 0.20\text{ dB}$ at $1,000\text{ Hz}$, calibrated to map to $-20.0\text{ dBFS}$ digital RMS before gain locking.
5. **Digital Mixing Engine:** Speech power measured via ITU-R P.56 active speech level voltmeter ($P_s$); symmetric linear attenuation ($\gamma$) applied if mixture peak exceeds $-0.5\text{ dBFS}$ ($0.944$), preserving mathematical linearity and zero clipping.
6. **Standard Resampler:** Deterministic Kaiser-windowed polyphase sinc resampler for 48 kHz $\to$ 16 kHz conversions ($>100\text{ dB}$ stopband attenuation, linear phase).

---

## 6. Frozen Qualification Gatekeeper & Exit Criteria

Stage 11.3 physical data collection remains locked behind the automated gatekeeper script (`scripts/verify_stage11_qualification_gates.py`) and the 5-gate qualification tracker (`research/STAGE11_2_1_QUALIFICATION_TRACKER.csv`):

```
+---------------------------------------------------------------------------------------------------------+
|                               FROZEN QUALIFICATION TRACKER (0/5 CLEARED)                                |
+----+----------------------------------+-------------------------+---------------------------------------+
| ID | Prerequisite Qualification Gate  | Current Status          | Evidentiary Artifact Requirement      |
+----+----------------------------------+-------------------------+---------------------------------------+
| 01 | Ethics Committee Approval        | LOCKED_PENDING_EVIDENCE | evidence/IEC_APPROVAL_CERTIFICATE.pdf |
| 02 | Legal & Consent Sign-Off         | LOCKED_PENDING_EVIDENCE | evidence/LEGAL_COUNSEL_ATTESTATION.pdf|
| 03 | Acoustic Booth Certification     | LOCKED_PENDING_EVIDENCE | evidence/BOOTH_ACOUSTIC_CERTIFICATE.pdf|
| 04 | ADC Hardware Qualification       | LOCKED_PENDING_EVIDENCE | evidence/ADC_BENCH_CALIBRATION_REPORT.pdf|
| 05 | Physical Raspberry Pi 5 Benchmark| LOCKED_PENDING_EVIDENCE | evidence/PI5_PHYSICAL_BENCH_REPORT.pdf|
+----+----------------------------------+-------------------------+---------------------------------------+
| VERDICT: FAIL-CLOSED GATEKEEPER ACTIVE (EXIT CODE 1) — ZERO COLLECTION AUTHORIZED                       |
+---------------------------------------------------------------------------------------------------------+
```

### Exit Criteria for Stage 11.3 Authorization:
Physical recruitment and collection may proceed **if and only if** `python3 scripts/verify_stage11_qualification_gates.py` returns exit code `0` after verifying valid evidence files and authentic cryptographic signatures for all 5 gates.

