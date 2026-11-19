# SIH 26052 — Stage 11.2: Pre-Collection Approval & Qualification Action Plan

**Document Version:** 1.0.0 · **Date:** 2026-11-13  
**Status:** Master Implementation Plan · **Pre-Collection Phase**  
**Execution Boundary:** Administrative, regulatory, and laboratory bench planning. **Zero participant recruitment, zero participant contact, zero audio recording, and zero data collection authorized.**

---

## 1. Stage 11.2 Objective & Executive Summary

Stage 11.2 translates the architectural resolutions from Stage 11.1 into an executable, legally compliant, and bench-qualified preparation package. This plan operationalizes the five core prerequisites required before data collection may be authorized in Stage 11.3:
1. Formal Institutional Review Board (IRB / IEC) ethics approval.
2. Participant information, consent instruments, and data privacy safeguards.
3. Rigorous re-calibration of statistical power and multiple-testing thresholds.
4. Laboratory acoustic booth and audio interface qualification.
5. Empirical reproduction of Raspberry Pi 5 edge compute and latency metrics.

---

## 2. Direct Reconciliation of Stage 11.1 Review Feedback

### 2.1 Statistical Power & Variance Reconciliation
- **User Finding:** The Stage 11.1 report's claim of $>99\%$ power at $n = 240$ per bin assumed an overly optimistic standard deviation ($\sigma \approx 1.2\text{ dB}$) and unadjusted single-comparison testing.
- **Stage 11.2 Resolution:** Extracted empirical paired variance from Stage 7 and Stage 8 benchmark data:
  - True empirical within-bin standard deviation is **$\sigma_{\Delta\text{SNR}} \approx 2.45 - 2.62\text{ dB}$** and **$\sigma_{\Delta\text{PESQ}} \approx 0.32 - 0.42$**.
  - Under rigorous family-wise error rate control across 12 within-bin tests ($\alpha = 0.00417$) and 72 study-wide tests ($\alpha = 0.000694$):
    - Subtle differences ($\Delta\text{SNR} \le 0.30\text{ dB}$ or $\Delta\text{PESQ} \le 0.05$) are **underpowered** ($<50\%$ power).
    - Substantial differences ($\Delta\text{SNR} \ge 0.75\text{ dB}$ and $\Delta\text{PESQ} \ge 0.10$) maintain **$>89.5\%$ power under study-wide Bonferroni**, and **$>99\%$ power under FDR**.
    - For the observed gains of FullSubNet over Step-500 ($\Delta\text{SNR} = +1.44\text{ dB}$, $\Delta\text{PESQ} = +0.28$), statistical power is **$100.0\%$**.
  - Documented comprehensively in [STAGE11_2_STATISTICAL_POWER_AUDIT.md](file:///Users/shreyasdivekar/Documents/anc%20sih/research/STAGE11_2_STATISTICAL_POWER_AUDIT.md).

### 2.2 Raspberry Pi 5 Hardware Figures Reconciliation
- **User Finding:** The Stage 11.1 report's claimed Pi CPU, RTF, and latency figures must be treated as review findings until reproduced on the actual hardware. Furthermore, the target platform is Raspberry Pi 5 (Broadcom BCM2712, Quad-core Cortex-A76 @ 2.4 GHz), and Pi 5 capability cannot be inferred from legacy Pi 4 benchmark figures.
- **Stage 11.2 Resolution:**
  - Formally re-classified all prior compute estimates as **Review Findings / Preliminary Hypotheses** pending empirical bench testing on Raspberry Pi 5.
  - Established a dedicated physical bench reproduction protocol for Raspberry Pi 5 with dual-channel oscilloscope latency timing, thermal sysfs logging, and a 60-minute automated soak test runner in [STAGE11_2_FACILITY_AND_HARDWARE_QUALIFICATION.md](file:///Users/shreyasdivekar/Documents/anc%20sih/research/STAGE11_2_FACILITY_AND_HARDWARE_QUALIFICATION.md).
  - Provisional target acceptance criteria on physical Pi 5 (provisional planning targets, not measured results): DFN3 Step-500 mean RTF $\le 0.30$ ($p99 \le 0.40$), physical round-trip latency $\le 35.0\text{ ms}$, RSS $\le 300\text{ MB}$, and 60-min soak zero ALSA XRUNs.
  - Physical execution is logged as an open qualification milestone (Gate 05) before Stage 11.3 clearance.

---

## 3. Workstream Execution Matrix & Deliverables Inventory

```
+---------------------------------------------------------------------------------------------------------+
|                                    STAGE 11.2 WORKSTREAM TRACKING MATRIX                                |
+----+--------------------------------+-----------------------------+---------------------+---------------+
| WS | Scope / Deliverable            | Responsible Role            | Artifact Reference  | Status        |
+----+--------------------------------+-----------------------------+---------------------+---------------+
| 1  | Statistical Power Audit        | Lead Methodologist          | STAGE11_2_STAT_...  | COMPLETE      |
| 2  | Institutional Ethics Dossier   | Principal Investigator      | STAGE11_2_APPR_...  | COMPLETE      |
| 3  | Participant Consent Instruments| Legal / Privacy Officer     | STAGE11_2_CONS_...  | COMPLETE      |
| 4  | Facility & Hardware Bench Plan | Acoustic & Embedded Leads   | STAGE11_2_FACI_...  | COMPLETE      |
| 5  | Noise Licensing Register       | IP / Contracts Officer      | STAGE11_2_NOIS_...  | COMPLETE      |
| 6  | Master Implementation Plan     | SIH Project Coordinator     | STAGE11_2_ACTI_...  | COMPLETE      |
+----+--------------------------------+-----------------------------+---------------------+---------------+
```

### Table 3.1: Deliverables Specification & File Links

| Deliverable Name | File Path | Focus Area | Status |
|:---|:---|:---|:---:|
| **Statistical Power Audit** | [STAGE11_2_STATISTICAL_POWER_AUDIT.md](file:///Users/shreyasdivekar/Documents/anc%20sih/research/STAGE11_2_STATISTICAL_POWER_AUDIT.md) | Empirical variance bounds, FWER/FDR corrections, MDE thresholds | Complete |
| **Ethics Review Dossier** | [STAGE11_2_APPROVAL_PACKAGE.md](file:///Users/shreyasdivekar/Documents/anc%20sih/research/STAGE11_2_APPROVAL_PACKAGE.md) | Formal IRB submission, inclusion/exclusion, safety SOPs | Complete |
| **Consent Instruments** | [STAGE11_2_CONSENT_INSTRUMENTS.md](file:///Users/shreyasdivekar/Documents/anc%20sih/research/STAGE11_2_CONSENT_INSTRUMENTS.md) | PIS text, ICF checkboxes, Withdrawal & Destruction certificates | Complete |
| **Bench Qualification Plan**| [STAGE11_2_FACILITY_AND_HARDWARE_QUALIFICATION.md](file:///Users/shreyasdivekar/Documents/anc%20sih/research/STAGE11_2_FACILITY_AND_HARDWARE_QUALIFICATION.md) | Booth $RT_{60}$, ADC EIN, Pi 5 hardware bench reproduction | Complete |
| **Noise Licensing Dossier** | [STAGE11_2_NOISE_LICENSING_DOSSIER.md](file:///Users/shreyasdivekar/Documents/anc%20sih/research/STAGE11_2_NOISE_LICENSING_DOSSIER.md) | Chain of title, CC-BY/CC0 verification, anti-scraping policy | Complete |
| **Master Action Plan** | [STAGE11_2_ACTION_PLAN.md](file:///Users/shreyasdivekar/Documents/anc%20sih/research/STAGE11_2_ACTION_PLAN.md) | Strategic coordination, reconciliation, transition gates | Complete |

---

## 4. Protected Baseline Artifacts & Integrity Verification

All models, evaluators, manifests, and deployment checkpoints remain completely frozen and untouched:

| Baseline Artifact | Path | SHA-256 Checksum | Verification Status |
|:---|:---|:---:|:---:|
| **Canonical Manifest** | `runs/sih26052_canonical_validation/manifest.csv` | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` | VERIFIED |
| **Deployed Step-500** | `antigravity/runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt` | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` | VERIFIED |
| **FullSubNet Epoch 58** | `antigravity/checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar` | `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0` | VERIFIED |
| **GTCRN DNS3 Baseline** | `antigravity/checkpoints/gtcrn_stage5/model_trained_on_dns3.tar` | `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79` | VERIFIED |
| **Stage 11 Baseline Spec**| `research/STAGE11_RECORDING_STUDY_DESIGN.md` | `144bc0a07fed1122e4e0ff8ad11881ed5e0f7f951fcd783a7b1ecdbccef95c68` | VERIFIED |
| **Gold Test Set** | `data/SIH_GOLD_TEST` | *Unread / Isolated* | SEALED (`gold_test_read: false`) |
| **Pi Production Runtime**| `~/anc_live` | *Unmodified / Isolated* | FROZEN |

---

## 5. Transition Criteria for Stage 11.3 (Authorization to Collect)

The project will not transition to active participant recruitment or data collection until the following five strict conditions are satisfied and signed off:

1. **IRB Approval Certificate:** Formal written certificate issued by the Institutional Ethics Committee.
2. **Legal & Licensing Sign-Off:** Written attestation from legal counsel confirming all participant consent instruments and noise asset licenses.
3. **Physical Booth Certification:** Calibrated measurement certificate confirming $RT_{60} \le 120\text{ ms}$ and $L_{\text{Aeq}} \le 25\text{ dBA}$.
4. **ADC Hardware Sign-Off:** Laboratory bench certificate confirming ADC EIN $\le -128.5\text{ dBu}$ and phase skew $< 5\ \mu\text{s}$.
5. **Physical Raspberry Pi 5 Reproduction:** Hardware benchmark report confirming DFN3 Step-500 achieves provisional acceptance criteria (measured mean RTF $\le 0.30$, $p99 \le 0.40$, and physical round-trip latency $\le 35\text{ ms}$) on physical Raspberry Pi 5 hardware (BCM2712 Cortex-A76 @ 2.4 GHz) without thermal throttling (`throttled=0x0`). Evidence artifact: `evidence/PI5_PHYSICAL_BENCH_REPORT.pdf`.

