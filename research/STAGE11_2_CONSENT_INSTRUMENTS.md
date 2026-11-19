# SIH 26052 — Stage 11.2: Participant Consent Instruments & Legal Notices

**Document Identifier:** SIH-26052-STG11-DOC-CONSENT · **Version:** 1.0.0 · **Date:** 2026-11-13  
**Status:** Operational Consent Documents · **Pre-Recruitment Phase**  
**Execution Boundary:** Standardized legal and ethical instruments for human participant voice recording under GDPR Article 9 and India Digital Personal Data Protection (DPDP) Act 2023.

---

## 1. Participant Information Sheet (PIS)

### Study Title: Independent Acoustic Evaluation of Neural Speech Enhancement (SIH 26052)

#### Invitation & Overview
You are invited to take part in a scientific research study conducted by the Audio & Embedded Machine Learning Laboratory. Before you decide whether to participate, it is important for you to understand why the research is being conducted and what it will involve. Please read the following information carefully.

#### What is the purpose of this study?
In high-noise environments—such as aviation, tactical vehicles, and industrial operations—speech communication is severely degraded by ambient acoustic noise. We are evaluating advanced artificial intelligence algorithms designed to clean speech audio in real time. To test these systems accurately without bias, we are recording an independent dataset of natural human speech across diverse speakers, accents, and speaking styles.

#### Why have I been invited?
You have been invited because you are an adult aged 18 to 60 with normal hearing and speech, and you speak English. We are seeking 24 participants with balanced gender and diverse regional English accents.

#### Do I have to take part?
No. Your participation is completely voluntary. It is entirely up to you to decide whether to participate. If you decide to take part, you will be given this information sheet to keep and will be asked to sign an Informed Consent Form. If you decide not to take part, or if you change your mind later and withdraw, it will not affect your legal rights, employment, or academic standing in any way.

#### What will happen to me if I take part?
You will visit our audio laboratory for a single recording session lasting approximately **60 to 90 minutes**:
1. You will be seated in an acoustically treated, quiet vocal isolation booth.
2. We will fit a lightweight headset with a small boom microphone placed near the corner of your lips.
3. You will read a set of standard English sentences displayed on a silent tablet.
4. You will describe a series of photographs and state numerical sequences in your own natural speaking voice.
5. You will speak at three comfortable volume levels: normal conversation, slightly raised voice, and quiet voice.
6. A mandatory 10-minute rest break with water will be provided halfway through the session.

#### Are there any risks or discomforts?
This study involves **minimal risk**. The sound levels inside the booth and in your headset are quiet and well within standard occupational safety limits ($< 75\text{ dBA}$). You may experience slight vocal fatigue, which is mitigated by our structured breaks and hydration.

#### What are the benefits of taking part?
While there is no direct personal clinical benefit to you, your contribution will advance open scientific research on life-saving communications systems for defense and emergency services. You will receive a formal certificate of research participation and modest compensation for your time and travel.

#### How will my voice data and privacy be protected?
Under international privacy regulations (GDPR and the DPDP Act 2023), voice recordings are considered **biometric data**. We take your privacy with extreme seriousness:
- **No Personal Identifiers:** Your name, contact details, and personal identity will never appear on audio recordings, file names, or published research papers.
- **Pseudonymization:** You will be assigned a random alphanumeric code (e.g., `SPK_A01`).
- **Encrypted Air-Gapped Vault:** The document linking your name to this code will be stored on an encrypted, password-protected hardware drive stored in a locked physical safe, completely disconnected from the internet.
- **Content Screening:** Any inadvertent mention of personal names, places, or private data during speaking will be excised immediately from the recording.
- **Zero Commercial Resale:** Your voice audio will never be sold to data brokers, will never be used for commercial advertising, and will never be used to train unauthorized voice-cloning models.

#### What happens if I change my mind (Right of Withdrawal)?
You have the unconditional right to withdraw from the study at any time prior to the dataset being cryptographically sealed and published. If you choose to withdraw, simply notify the Principal Investigator in writing or email. All raw and processed audio recordings of your voice will be immediately and permanently deleted, and you will be issued a formal Certificate of Destruction.

#### Who has reviewed this study?
This study has been formally reviewed and approved by the Institutional Ethics Committee (Approval Certificate # IEC-2026-SIH26052).

#### Contact for Further Information
- **Principal Investigator:** Dr. Research Scientist · Email: `pi-audio@lab.institution.edu` · Tel: `+91-XX-XXXX-XXXX`
- **Data Protection Officer:** Institutional Privacy Board · Email: `dpo@institution.edu`
- **Ethics Committee Secretary:** Institutional Ethics Committee · Email: `iec@institution.edu`

---

## 2. Standardized Informed Consent Form (ICF)

**Participant Code:** `SPK_`___________ (To be completed by investigator)  
**Session ID:** `SESS_`_________  
**Date of Session:** ________________________

Please initial each box individually to confirm your agreement with the statement:

```
[   ] 1. INFORMATION SHEET REVIEW:
         I confirm that I have read and understood the Participant Information Sheet (v1.0)
         for the SIH 26052 Speech Enhancement Recording Study. I have had the opportunity
         to consider the information, ask questions, and have had them answered satisfactorily.

[   ] 2. VOLUNTARY PARTICIPATION:
         I understand that my participation is entirely voluntary and that I am free to withdraw
         at any time prior to the dataset publication milestone without giving any reason and
         without my legal, academic, or employment rights being affected.

[   ] 3. HIGH-FIDELITY VOICE RECORDING & BIOMETRICS:
         I expressly consent to the high-fidelity acoustic recording of my voice using close-talking
         boom, earcup, and reference microphones. I acknowledge that human voice recordings 
         constitute biometric personal data under applicable data protection legislation.

[   ] 4. CRYPTOGRAPHIC PSEUDONYMIZATION:
         I consent to my voice recordings being pseudonymized under a random code (e.g., SPK_A01).
         I understand that my real identity will be stored in an encrypted, air-gapped vault
         accessible exclusively to senior authorized research personnel.

[   ] 5. SCIENTIFIC RESEARCH & OPEN BENCHMARKS:
         I grant permission for my pseudonymized audio recordings and synthetic noisy mixtures
         to be used for non-commercial scientific research, academic publications, and public
         open-access benchmark datasets for speech enhancement evaluation.

[   ] 6. PROHIBITION OF COMMERCIAL VOICE CLONING:
         I understand that my voice recordings will not be sold to commercial brokers, will not be
         used for commercial advertising, and will not be used for commercial biometric impersonation.

[   ] 7. DATA RETENTION & SECURITY:
         I consent to the secure archival of my pseudonymized audio files on encrypted research
         servers for a period of up to five (5) years following the conclusion of the study.
```

**Participant Name (Printed):** ____________________________________________________  
**Participant Signature:** _______________________________________ **Date:** _____________

**Investigator Name (Printed):** ____________________________________________________  
**Investigator Signature:** ______________________________________ **Date:** _____________

---

## 3. Participant Withdrawal & Data Purging Protocol

```
+---------------------------------------------------------------------------------------------------------+
|                                  DATA WITHDRAWAL & PURGE WORKFLOW                                       |
+--------------------------+---------------------+-------------------------------+------------------------+
| 1. Notice Received       | 2. Vault Lookup     | 3. Cryptographic Search       | 4. Verified Wipe       |
+--------------------------+---------------------+-------------------------------+------------------------+
| Written request from     | Air-gapped vault    | Query filesystem for all files| Overwrite storage via  |
| participant email/letter | identifies SPK_XXX  | matching SPK_XXX and SHA-256  | DoD 5220.22-M 3-pass   |
| Logged in register       | Single operator     | Audio stems, mixes, manifests | Issue Cert of Destruct |
+--------------------------+---------------------+-------------------------------+------------------------+
```

### 3.1 Withdrawal Form Template
```
STUDY WITHDRAWAL NOTICE
Participant Code: SPK________   Original Date of Consent: ___________________
Reason for Withdrawal (Optional): ___________________________________________

I hereby formally exercise my right to withdraw from the SIH 26052 Recording Study. 
I request the immediate and irreversible deletion of all voice audio stems, derivative mixtures, 
and metadata records containing my voice recordings.

Participant Signature: ___________________________________ Date: ____________
Received by PI:         ___________________________________ Date: ____________
```

### 3.2 Formal Certificate of Destruction
```
CERTIFICATE OF DATA DESTRUCTION
Ref: SIH-26052-DESTRUCT-_______

This certifies that all audio recordings and associated metadata linked to Participant Code 
SPK________ have been permanently and irreversibly purged from all primary workstations, 
backup servers, and local cache storage.

Wipe Methodology: DoD 5220.22-M (3-Pass Cryptographic Overwrite)
Number of Audio Files Deleted: ________
Number of Manifest Records Removed: ________
Date of Verified Destruction: ______________
Lead System Administrator Signature: _________________________________________
Principal Investigator Signature:   _________________________________________
```

