# SIH 26052 — Stage 11.2: Noise Asset Licensing & Provenance Dossier

**Document Version:** 1.0.0 · **Date:** 2026-11-13  
**Status:** Legal & Provenance Documentation · **Pre-Collection Phase**  
**Execution Boundary:** Chain-of-title verification and copyright compliance for operational noise assets. **Zero unverified or scraped audio files may be incorporated into the evaluation corpus.**

---

## 1. Legal Framework for Acoustic Noise Assets

Environmental, vehicular, and mechanical acoustic recordings are subject to copyright, intellectual property, and database rights:
1. **Originality in Sound Recordings:** Under international copyright law (WIPO Performances and Phonograms Treaty, US Copyright Act Title 17, and Indian Copyright Act 1957 Section 13), sound recordings enjoy independent copyright protection separate from any underlying musical or literary composition.
2. **Dataset Redistribution Rights:** Most standard commercial sound effects (SFX) licenses grant end-user synchronization rights for media production (e.g., film, games) but **expressly prohibit redistributing raw audio stems** as part of machine learning datasets or public benchmarks.
3. **Chain of Title:** Every noise stem used in SIH 26052 must possess an unbroken, verifiable legal chain of title linking the recorded file to an approved, irrevocable open research license or a direct institutional assignment.

---

## 2. Permitted Noise Asset Categories & Requirements

To prevent copyright infringement, dataset invalidation, or legal takedown demands, all noise assets must fall strictly into one of the following four authorized categories:

```
+---------------------------------------------------------------------------------------------------------+
|                                  AUTHORIZED NOISE ASSET TIERS                                           |
+--------------------------+---------------------+-------------------------------+------------------------+
| Tier 1: In-House Capture | Tier 2: Public Dom. | Tier 3: Permissive Open Lic.  | Tier 4: Direct DTA     |
+--------------------------+---------------------+-------------------------------+------------------------+
| Recorded by project team | CC0 1.0 Universal   | CC-BY 4.0 / CDLA-Permissive   | Institutional Data     |
| Full project assignment  | Dedication to public| Full attribution preserved    | Transfer Agreement     |
| Original master uncomp.  | Zero copyright claim| Complete provenance recorded  | Perpetual research lic.|
+--------------------------+---------------------+-------------------------------+------------------------+
```

### Table 2.1: Authorized vs. Prohibited Noise Source Policy

| Source Classification | Legal Status | Permitted in Study? | Mandatory Compliance Condition |
|:---|:---|:---:|:---|
| **In-House Project Recording** | Full institutional copyright | **YES** | Field log signed by recording engineer; raw uncompressed WAV. |
| **Creative Commons Zero (CC0)** | Public Domain dedication | **YES** | Verifiable URL to CC0 dedication and author identity. |
| **Creative Commons Attribution (CC-BY 4.0)** | Permissive open license | **YES** | Full author attribution embedded in manifest and metadata.json. |
| **Institutional DTA / MOU** | Direct bilateral contract | **YES** | Signed Data Transfer Agreement on file with institutional legal counsel. |
| **Commercial SFX Libraries** | Proprietary commercial license | **PROHIBITED** | Commercial terms forbid dataset compilation and distribution. |
| **YouTube / Video Streaming Rips** | Third-party copyrighted media | **STRICTLY PROHIBITED** | Violation of platform terms; copyright infringement; lossy artifacts. |
| **Broadcast TV / Podcast Audio** | Third-party media broadcast | **STRICTLY PROHIBITED** | Unauthorized media extraction; unverified provenance. |

---

## 3. Acoustic Quality & Format Standards for Noise Stems

In addition to legal compliance, noise assets must satisfy stringent technical criteria to ensure valid acoustic modeling:

1. **Uncompressed PCM Master Format:**
   - All source noise files must be linear PCM Broadcast WAV format, $\ge 24\text{ bits}$, $\ge 48.0\text{ kHz}$ sampling rate.
   - **Absolute Ban on Lossy Codecs:** MP3, AAC, Ogg Vorbis, and Opus sources are **strictly prohibited**. Perceptual audio codecs discard sub-audible masked spectral components and introduce psychoacoustic phase smearing and pre-echo ringing that corrupt neural speech enhancement loss functions.
2. **Dynamic Range & Crest Factor Verification:**
   - The recording must have at least $12.0\text{ dB}$ of headroom below digital full scale ($0\text{ dBFS}$) to guarantee zero pre-ADC analog saturation or digital clipping.
3. **Continuous Minimum Length:**
   - Stationary and non-stationary continuous noise files must have a minimum continuous active duration of $\ge 30.0\text{ seconds}$ without loops or cross-fades, allowing random uncorrelated temporal slicing for mixture synthesis.

---

## 4. Operational Noise Provenance & Chain-of-Title Register

Every noise stem selected for the Stage 11 evaluation corpus must be documented in the master provenance register:

```csv
noise_id,noise_class,noise_scenario,source_category,source_repository_url,original_creator,license_type,license_url,sample_rate_hz,bit_depth,duration_sec,sha256_hash,legal_clearance_status
NOISE_STAT_01,stationary,diesel_engine_idle,Tier_1_In_House,internal_repo/field_rec_01,Audio_Lab_Team,Institutional_Assignment,internal://legal/assignment_2026,48000,24,120.50,9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e,APPROVED
NOISE_STAT_02,stationary,hvac_industrial,Tier_2_Public_Domain,https://freesound.org/s/XXXXX,AcousticResearcher,CC0_1.0,https://creativecommons.org/publicdomain/zero/1.0/,48000,24,64.20,7b6a5f4e3d2c1b0a9f8e9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c,APPROVED
NOISE_NONSTAT_01,non_stationary,drone_hover_4k_rpm,Tier_1_In_House,internal_repo/drone_hover_02,Audio_Lab_Team,Institutional_Assignment,internal://legal/assignment_2026,48000,24,95.00,1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e9f8e7d6c5b4a3f2e,APPROVED
NOISE_NONSTAT_02,non_stationary,vehicle_cabin_tracked,Tier_4_Direct_DTA,defense_acoustics_consortium/dta_04,Defense_Lab_Partner,DTA_Perpetual_Research,internal://contracts/DTA_2026_04,48000,24,180.00,8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b,APPROVED
NOISE_TRANS_01,transient_impulsive,heavy_tool_impact,Tier_1_In_House,internal_repo/tool_impacts_01,Audio_Lab_Team,Institutional_Assignment,internal://legal/assignment_2026,48000,24,45.00,5f4e3d2c1b0a9f8e9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6a,APPROVED
NOISE_TRANS_02,transient_impulsive,ballistic_blast_calibrated,Tier_4_Direct_DTA,ballistics_research_inst/range_rec,Range_Acoustic_Facility,DTA_Perpetual_Research,internal://contracts/DTA_2026_09,48000,24,30.00,3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c,APPROVED
```

---

## 5. Legal Clearance & Compliance Sign-Off

```
NOISE ASSET CHAIN-OF-TITLE LEGAL ATTESTATION
Study Identifier: SIH-26052-STG11   Review Date: ___________________
Institutional Legal Counsel: _______________________________________

I have reviewed the licensing documentation, provenance records, and chain-of-title certificates 
for all noise assets listed in the Master Provenance Register.

I hereby certify that:
1. All noise assets conform to Tier 1, 2, 3, or 4 authorized licensing criteria.
2. Zero copyrighted commercial sound libraries or scraped streaming media are included.
3. Attribution clauses (CC-BY 4.0) are fully preserved in dataset manifests and metadata.json.
4. Institutional research redistribution rights are legally verified and indemnified.

LEGAL CLEARANCE STATUS: [ ] APPROVED FOR RECORDING STUDY
                        [ ] REJECTED (UNVERIFIED ASSETS DETECTED)

Legal Officer Signature: _________________________________ Date: _______________
Principal Investigator:  _________________________________ Date: _______________
```

