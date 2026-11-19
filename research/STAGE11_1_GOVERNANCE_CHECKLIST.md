# SIH 26052 — Stage 11.1: Data Governance, Ethics & Legal Compliance Checklist

**Document Version:** 1.0.0 · **Date:** 2026-11-13  
**Status:** Mandatory Governance Specification · **Pre-Recruitment Phase**  
**Execution Boundary:** Ethical and legal compliance requirements. **Zero participant recruitment, zero participant contact, zero audio recording, and zero data collection may begin until all approvals in Section 7 are formally executed.**

---

## 1. Governance Overview & Regulatory Framework

Human voice recordings constitute **biometric personal data** under international and national privacy frameworks:
- **General Data Protection Regulation (GDPR, Regulation (EU) 2016/679):** Article 9 (Processing of special categories of personal data / biometric data for uniquely identifying a natural person).
- **Digital Personal Data Protection Act (DPDP Act 2023, India):** Section 6 (Notice and Consent) and Section 7 (Processing for specified legitimate purposes).
- **Declaration of Helsinki & ICMR National Ethical Guidelines:** Human participant research standards governing voluntary participation, risk minimization, and confidentiality.

To ensure total legal, institutional, and scientific validity, data collection is locked behind an uncompromising governance firewall.

---

## 2. Institutional Review Board (IRB) / Ethics Committee Submission

Prior to contacting or screening any participant, the Principal Investigator must submit an Institutional Ethics Review application containing:

### 2.1 Required Application Documents
1. **Study Protocol Document:** Complete description of non-invasive acoustic recording procedures, acoustic booth specs, sound levels, and session lengths.
2. **Participant Information Sheet (PIS):** Plain-language explanation of study goals, rights, data handling, and zero commercial exploitation.
3. **Informed Consent Form (ICF):** Written consent document with explicit, itemized check-boxes for audio capture, research use, and pseudonymized archiving.
4. **Data Protection Impact Assessment (DPIA):** Technical documentation detailing the air-gapped cryptographic vault, pseudonymization algorithms, access controls, and deletion mechanisms.
5. **Acoustic Safety Certification:** Documentation proving that sound pressure levels generated inside the booth during recording remain strictly within occupational safety standards ($< 80\text{ dBA SPL}$).

---

## 3. Participant Information Sheet (PIS) & Informed Consent Structure

### 3.1 Participant Information Sheet (PIS) Outline
Every prospective participant must be provided with a written PIS containing the following mandatory sections:
- **Section 1: Purpose of Research:** Developing and evaluating robust active noise cancellation and speech enhancement technologies for defense and high-noise communications.
- **Section 2: Voluntary Participation:** Participation is entirely voluntary. Participants may decline to participate or discontinue at any time without penalty or loss of benefits.
- **Section 3: What Participation Involves:** A single 60–90 minute session in an acoustic isolation booth reading standardized sentences, describing pictures, and speaking at varying vocal effort levels while wearing a headset.
- **Section 4: Risks and Discomforts:** Minimal risk. Sound levels do not exceed normal conversational or speech projection levels. No invasive procedures or pharmaceuticals.
- **Section 5: Data Protection & Biometrics:** Voice recordings can inherently carry biometric traits. Audio will be pseudonymized using cryptographic codes (`SPK_A01`) with all personal identifiers removed.
- **Section 6: Use of Data:** Pseudonymized audio files will be used exclusively for non-commercial scientific research, benchmarking machine learning models, and publishing in peer-reviewed scientific literature.
- **Section 7: Right to Withdraw:** Participants have the right to request the complete deletion of their voice recordings at any time prior to dataset cryptographic freezing.
- **Section 8: Contact Information:** Contact details for the Principal Investigator, Institutional Data Protection Officer, and Institutional Ethics Review Committee.

### 3.2 Informed Consent Form (ICF) Mandatory Clauses
The ICF must contain explicit, non-bundled affirmation check-boxes requiring participant signature:

```
INFORMED CONSENT FORM - CLAUSE ARCHITECTURE

[ ] CLAUSE 1: STUDY UNDERSTANDING
    "I confirm that I have read and understood the Participant Information Sheet (v1.0) 
     for the SIH 26052 Speech Enhancement Recording Study. I have had the opportunity 
     to consider the information, ask questions, and have had these answered satisfactorily."

[ ] CLAUSE 2: VOLUNTARY CONSENT & WITHDRAWAL
    "I understand that my participation is voluntary and that I am free to withdraw at any time 
     prior to the dataset freezing milestone without giving any reason and without my legal 
     rights being affected. Upon withdrawal, all raw and processed recordings of my voice will 
     be permanently and securely deleted."

[ ] CLAUSE 3: AUDIO RECORDING & BIOMETRIC DATA
    "I expressly consent to the high-fidelity acoustic recording of my voice using boom, earcup, 
     and free-field microphones. I acknowledge that human voice recordings constitute biometric 
     data under applicable data protection laws."

[ ] CLAUSE 4: PSEUDONYMIZATION & CONFIDENTIALITY
    "I consent to my voice recordings being pseudonymized using a random alphanumeric identifier 
     (e.g., SPK_A01). I understand that my name, contact details, and identity linkage will be 
     stored in an encrypted, air-gapped vault accessible only to authorized senior investigators."

[ ] CLAUSE 5: RESEARCH ARCHIVING & SCIENTIFIC PUBLICATION
    "I grant permission for my pseudonymized audio recordings and derived synthetic acoustic 
     mixtures to be used for scientific research, academic presentations, peer-reviewed publications, 
     and public evaluation benchmarks for speech enhancement technology."

[ ] CLAUSE 6: NO COMMERCIAL RESALE
    "I understand that my voice recordings will not be sold to commercial brokers, will not be 
     used for commercial voice-cloning advertising, and will be preserved under non-commercial 
     academic research licenses."

Participant Name: ____________________________________________________
Participant Signature: ___________________________ Date: _____________
Witness / Investigator Signature: _________________ Date: _____________
```

---

## 4. Privacy, Pseudonymization & Air-Gapped Vault Protocol

```
+---------------------------------------------------------------------------------------------------------+
|                                    IDENTITY ISOLATION & PSEUDONYMIZATION                                |
+--------------------------+---------------------+-------------------------------+------------------------+
| 1. Physical Identity     | 2. Air-Gapped Vault | 3. Cryptographic Mapping      | 4. Public Corpus       |
+--------------------------+---------------------+-------------------------------+------------------------+
| Signed Consent Form      | Offline workstation | Master Salt + HMAC-SHA256     | Audio files & CSV meta |
| Direct PII (Name, Email) | AES-256-GCM storage | ID: SPK_A01, SPK_B02...       | Zero PII; Zero names   |
| Hardware physical safe   | Zero internet conn. | One-way irreversible to team  | Publicly sharable      |
+--------------------------+---------------------+-------------------------------+------------------------+
```

### 4.1 Pseudonymization Architecture
1. **Identifier Generation:**
   - Real participant names are never used in directory trees, filenames, or metadata.
   - Each participant is assigned a deterministic pseudo-random identifier based on HMAC-SHA256:
     $$\text{PseudoID} = \text{HMAC-SHA256}(\text{ParticipantUUID}, K_{\text{master}})[0..6]$$
   - Formatted as `SPK_<BLOCK><NUM>` (e.g., `SPK_A01`, `SPK_B04`).
2. **Air-Gapped Identity Vault:**
   - The master key $K_{\text{master}}$ and the identity mapping database are stored exclusively on an encrypted USB hardware security key (FIPS 140-2 Level 3 validated, AES-256 hardware encryption).
   - The key is locked inside a physical, fire-rated laboratory safe.
   - The machine used to manage identity keys must remain **permanently disconnected from local area networks and the internet (air-gapped)**.
3. **Acoustic Content Screening (PII Scrubbing):**
   - All recorded audio must be manually and programmatically screened to ensure participants did not inadvertently vocalize names, phone numbers, geographic locations, or private personal data during spontaneous speech blocks.
   - Any audio segment containing inadvertent disclosure of personal data must be permanently zeroed/excised immediately.

---

## 5. Third-Party Noise Asset Licensing & Chain of Title

If operational noise stems (such as drone harmonics, industrial machinery, or military vehicle cabin noise) are obtained from external repositories, the following verification protocol is legally mandatory:

### 5.1 Permitted Noise Asset Licenses
1. **Creative Commons Zero (CC0 1.0 Universal):** Public domain dedication; unrestricted commercial and research use.
2. **Creative Commons Attribution (CC-BY 4.0):** Permitted with full attribution metadata embedded in session manifests.
3. **Open Database License (ODbL 1.0) / CDLA-Permissive:** Permitted for acoustic benchmarking.
4. **Direct Institutional Research Assignment:** Written, signed institutional data transfer agreement (DTA) granting perpetual, non-exclusive research rights.

### 5.2 Prohibited Data Sources
- **Commercial Audio Libraries / Sound FX:** Files sourced without explicit, verifiable multi-seat research redistribution licenses (e.g., standard single-user sound FX licenses that forbid dataset distribution).
- **Web Scraping / YouTube Audio Extraction:** Audio ripped from YouTube, TikTok, broadcast TV, or copyrighted podcasts is strictly prohibited due to copyright infringement, unverified acoustic provenance, and lossy compression artifacts ($128\text{ kbps}$ MP3/AAC artifacts destroy high-frequency phase).

### 5.3 License Verification Register
Every external noise asset incorporated into the study must be entered into `STAGE11_NOISE_PROVENANCE_REGISTER.csv` with:
- Unique Noise ID (`NOISE_XXXX`)
- Source URL / Institutional Repository
- Original Author / Creator
- License Type (with link to official legal text)
- Date of Acquisition
- Verifying Legal Officer Signature

---

## 6. Data Retention, Access Control & Withdrawal Protocol

1. **Storage Security & Access Levels:**
   - Master raw audio ($48\text{ kHz}$ / $24\text{ bit}$) stored on an encrypted, access-logged Network Attached Storage (NAS) volume restricted to authorized study personnel via public-key authentication.
   - Public evaluation derivatives ($16\text{ kHz}$ / $48\text{ kHz}$ float32) published with SHA-256 manifest verification.
2. **Retention Period:**
   - Master raw stems retained for a maximum of **5 years** following project completion, after which all biometric clean speech stems shall be securely purged using DoD 5220.22-M cryptographic file wiping, unless an extension is granted under a new ethics protocol.
3. **Withdrawal Protocol:**
   - If a participant exercises their legal right to withdraw prior to dataset freezing:
     - The investigator retrieves the pseudonym mapping from the air-gapped vault.
     - All raw recordings, clean stems, and synthetic mixtures associated with `SPK_XXX` are located via SHA-256 hashes and deleted across all primary and backup storage arrays.
     - A formal Certificate of Destruction is generated and provided to the participant within 30 calendar days.

---

## 7. Pre-Collection Governance Sign-Off Matrix

**Data collection may not begin under any circumstances until all eight sign-offs below are formally executed and on file.**

```
PRE-COLLECTION GOVERNANCE SIGN-OFF MATRIX
Study ID: SIH-26052-STG11  Target Collection Window: ____________________

+----+----------------------------------+-----------------------------+-----------+------------+
| #  | Governance Milestone             | Authorized Signatory        | Decision  | Date       |
+----+----------------------------------+-----------------------------+-----------+------------+
| 1  | Institutional Ethics Approval    | Chair, Ethics Committee     | [ ] PASS  |            |
|    | (IRB Protocol # _______________) |                             | [ ] HOLD  | ___________|
+----+----------------------------------+-----------------------------+-----------+------------+
| 2  | Legal & Privacy Compliance       | Institutional Legal Counsel | [ ] PASS  |            |
|    | (GDPR / DPDP Compliance Cert)    | / Data Protection Officer   | [ ] HOLD  | ___________|
+----+----------------------------------+-----------------------------+-----------+------------+
| 3  | Participant Information & ICF    | Lead Ethics Coordinator     | [ ] PASS  |            |
|    | (Standardized Consent Form v1.0) |                             | [ ] HOLD  | ___________|
+----+----------------------------------+-----------------------------+-----------+------------+
| 4  | Air-Gapped Vault Security Audit  | Head of IT Infrastructure   | [ ] PASS  |            |
|    | (Hardware AES-256 Validation)    |                             | [ ] HOLD  | ___________|
+----+----------------------------------+-----------------------------+-----------+------------+
| 5  | Acoustic Safety & SPL Review     | Laboratory Safety Officer   | [ ] PASS  |            |
|    | (Booth Noise & Calibrator Cert)  |                             | [ ] HOLD  | ___________|
+----+----------------------------------+-----------------------------+-----------+------------+
| 6  | Noise Asset Licensing Clearance  | IP & Contracts Officer      | [ ] PASS  |            |
|    | (Complete Chain-of-Title Audit)  |                             | [ ] HOLD  | ___________|
+----+----------------------------------+-----------------------------+-----------+------------+
| 7  | Raspberry Pi Deployment Boundary | Lead Embedded Engineer      | [ ] PASS  |            |
|    | (Track A/B Decoupling Verified)  |                             | [ ] HOLD  | ___________|
+----+----------------------------------+-----------------------------+-----------+------------+
| 8  | Final Study Authorization        | Principal Investigator      | [ ] PASS  |            |
|    | (Master Release to Collect)      | (SIH 26052 Project Lead)    | [ ] HOLD  | ___________|
+----+----------------------------------+-----------------------------+-----------+------------+

CURRENT STAGE 11.1 GOVERNANCE STATUS:
[ ] ALL MILESTONES SIGNED — AUTHORIZED TO RECRUIT AND COLLECT
[X] PENDING SIGN-OFFS — HARD NO-GO ENFORCED (PREPARATION ONLY)
```

