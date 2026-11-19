# SIH 26052 — Stage 11.2: Institutional Ethics Review Dossier & Study Protocol

**Protocol Identifier:** SIH-26052-STG11-P01 · **Version:** 1.0.0 · **Date:** 2026-11-13  
**Status:** Institutional Review Board (IRB / IEC) Formal Submission Dossier  
**Execution Boundary:** Pre-recruitment ethics filing. **Zero participant contact or recruitment authorized** until this dossier receives formal institutional approval and an official clearance certificate.

---

## 1. Study Administrative Information

- **Study Title:** Independent Acoustic Evaluation and Rigorous Benchmarking of Embedded Deep Neural Speech Enhancement and Active Noise Cancellation Architectures (SIH 26052).
- **Principal Investigator (PI):** Lead Research Scientist, Audio & Embedded Machine Learning Laboratory.
- **Sponsoring Body:** Smart India Hackathon (SIH 26052) AICTE / Ministry of Education Consortium.
- **Oversight Body:** Institutional Review Board (IRB) / Institutional Ethics Committee (IEC).
- **Regulatory Framework:** 
  - ICMR National Ethical Guidelines for Biomedical and Health Research Involving Human Participants (2017).
  - General Data Protection Regulation (GDPR, EU 2016/679) Article 9 (Processing of Biometric Data).
  - Digital Personal Data Protection Act (DPDP Act 2023, India) Sections 6 & 7.

---

## 2. Study Rationale, Purpose & Scientific Objectives

### 2.1 Background
Tactical communications and voice interfaces in defense, emergency services, and aviation environments are severely degraded by high-energy ambient acoustic noise (diesel engine rumble, aircraft/drone blade-pass tones, industrial ventilation, and impulsive mechanical shocks). Deep learning speech enhancement models offer significant promise, but current systems suffer from catastrophic performance collapse at low input signal-to-noise ratios ($\le 0\text{ dB}$).

### 2.2 Objective of Current Protocol
This protocol establishes an independent, pristine acoustic recording study to evaluate four frozen candidate speech enhancement systems without data leakage or circularity:
1. Primary Ensemble (15% DFN3 + 70% FullSubNet + 15% GTCRN).
2. Secondary Ensemble (20% DFN3 + 60% FullSubNet + 20% GTCRN).
3. Standalone FullSubNet epoch 58 baseline.
4. Deployed DFN3 Step-500 production baseline.

---

## 3. Participant Selection, Recruitment & Demographics

### 3.1 Target Cohort Size
- **Total Participants:** $24$ adult volunteers ($12$ female, $12$ male).
- **Age Distribution:** $18$ to $60$ years of age.
- **Language & Accents:** English speakers spanning four balanced regional cohorts:
  1. Indian English (Northern / Western regional accents) — $6$ participants.
  2. Indian English (Southern / Eastern regional accents) — $6$ participants.
  3. General American / British English — $6$ participants.
  4. Non-native / Internationally accented English — $6$ participants.

### 3.2 Inclusion Criteria
1. Age $\ge 18$ and $\le 60$ years at the time of consent.
2. Self-reported normal hearing in both ears (no diagnosed sensorineural hearing loss).
3. Self-reported absence of acute speech or vocal tract pathologies (e.g., active dysphonia, severe stutter, vocal fold nodules).
4. Ability to read standard English text presented on an electronic display tablet.
5. Capacity to provide informed, autonomous written consent.

### 3.3 Exclusion Criteria
1. Individuals under $18$ years of age.
2. Vulnerable populations (e.g., incarcerated individuals, institutionalized persons, individuals under economic or hierarchical coercion).
3. Active acute upper respiratory tract infections (common cold, bronchitis, laryngitis) within 14 days prior to recording.
4. Professional relationship of direct subordinate dependency to the principal investigator (to prevent implicit coercion in academic settings).

---

## 4. Detailed Study Procedures & Acoustic Exposure

### 4.1 Physical Setting
All recording activities occur inside a certified double-wall acoustic isolation booth ($RT_{60} \le 120\text{ ms}$, ambient background floor $< 25\text{ dBA SPL}$) equipped with filtered airflow ventilation.

### 4.2 Sequence of Participant Tasks (Total Duration: 60–90 Minutes)
1. **Intake & Consent Briefing ($15\text{ minutes}$):** Review of Participant Information Sheet, Q&A with investigator, signing of Informed Consent Form.
2. **Fitting & Geometric Alignment ($5\text{ minutes}$):** Placement of lightweight headset boom microphone at $45^\circ$ azimuth and $2.5\text{ cm}$ distance from mouth corner.
3. **Recording Block A — Read Speech ($25\text{ minutes}$):** Participant reads 30 standardized Harvard/IEEE phonetically balanced sentences and 10 tactical radio phrases from a silent tablet.
4. **Hydration & Rest Break ($10\text{ minutes}$):** Participant offered water and encouraged to rest their vocal cords outside the booth.
5. **Recording Block B — Spontaneous & Elicited Speech ($20\text{ minutes}$):** Participant describes standard photographic scenarios, provides verbal route directions, and recites continuous digit strings.
6. **Debriefing & Study Conclusion ($5\text{ minutes}$):** Participant confirmed comfortable, provided copy of signed consent form, and issued reimbursement/token of appreciation.

---

## 5. Comprehensive Risk Assessment & Mitigation Plan

Under ICMR and international IRB guidelines, this study qualifies as **Minimal Risk** (the probability and magnitude of harm or discomfort anticipated are not greater than those ordinarily encountered in daily life).

### Table 5.1: Hazard Identification and Risk Mitigation

| Identified Hazard | Potential Impact | Severity | Probability | Mitigation Strategy | Residual Risk |
|:---|:---|:---:|:---:|:---|:---:|
| **Acoustic Overexposure** | Hearing fatigue, tinnitus | Moderate | Very Low | Ambient booth noise is $<25\text{ dBA}$. Any monitoring audio in headphones is hardware-limited to $<75\text{ dBA}$ (well below OSHA $85\text{ dBA}$ limit). | Negligible |
| **Vocal Strain / Fatigue** | Hoarseness, throat dryness | Low | Low | Mandatory 10-minute rest break; hydration provided; vocal effort limited to conversational and slightly projected levels. | Negligible |
| **Ergonomic Fatigue** | Neck strain from headset | Low | Low | Ultra-lightweight headset ($< 150\text{ g}$); adjustable ergonomic chair with lumbar support. | Negligible |
| **Biometric Privacy Breach** | Identification of voice | High | Low | Full cryptographic pseudonymization; air-gapped identity vault; strict prohibition of personal disclosures in speech. | Negligible |

---

## 6. Data Protection, Privacy & Pseudonymization Protocol

Human voice audio contains acoustic features that can constitute biometric data. The study implements defense-in-depth privacy protections:

1. **Deterministic Pseudonymization:**
   - Every participant is assigned an anonymous identifier (`SPK_A01` through `SPK_D06`).
   - The master linkage file connecting participant real names to `SPK_XXX` is stored on a hardware-encrypted, air-gapped flash drive stored in a fireproof physical laboratory safe.
2. **Acoustic PII Scrubbing:**
   - During recording, if a participant inadvertently states their name, address, or identifying details, that audio take is instantly deleted and re-recorded with generic text.
3. **Access Controls:**
   - Public research datasets contain only pseudonymized audio and metadata. The identity vault is accessible solely to the Principal Investigator and designated Data Protection Officer.
4. **Unconditional Right of Withdrawal:**
   - Participants retain the right to withdraw their voice data at any time prior to dataset cryptographic freezing. Upon written notice, all associated audio files will be purged and a Certificate of Destruction issued.

---

## 7. Institutional Review Board Document Checklist

The following documents accompany this submission dossier:
- [x] Appendix A: Participant Information Sheet (PIS v1.0)
- [x] Appendix B: Informed Consent Form (ICF v1.0)
- [x] Appendix C: Speech Recording Prompts & Script Catalog
- [x] Appendix D: Facility Acoustic Certification & Sound Level Meter Calibrations
- [x] Appendix E: Data Protection Impact Assessment (DPIA) & Vault Architecture
- [x] Appendix F: Investigator Curriculum Vitae & Research Credentials

