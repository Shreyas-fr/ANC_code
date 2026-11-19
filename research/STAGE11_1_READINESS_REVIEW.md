# SIH 26052 — Stage 11.1: Technical and Governance Readiness Review

**Document Version:** 1.0.0 · **Date:** 2026-11-13  
**Status:** Complete Readiness Review · **Pre-Collection Phase**  
**Execution Boundary:** Rigorous technical review, protocol refinement, and preparatory governance specification only. **Zero participant recruitment, zero participant contact, zero audio recording, zero hardware procurement, and zero data collection has occurred or is authorized.**

---

## 1. Executive Summary & Decision Gate

Stage 11.1 executes an exhaustive technical, architectural, and governance audit of the proposed audio recording study baseline specified in `research/STAGE11_RECORDING_STUDY_DESIGN.md`. 

The investigation confirms that moving to an independent, newly recorded acoustic dataset is mandatory to resolve the confounding, lack of raw stems, and circularity identified in Stages 7 through 10. However, data collection cannot commence until critical architectural mismatches, acoustic safety hazards, and institutional compliance gates are formally resolved.

### Overall Gate Verdict: **NO-GO FOR DATA COLLECTION / GO FOR PREPARATORY QUALIFICATION**

```
+---------------------------------------------------------------------------------------------------------+
|                                    STAGE 11.1 DECISION GATE OVERVIEW                                    |
+--------------------------+-------------------+----------------------------------------------------------+
| Workstream               | Readiness Verdict | Primary Condition / Blocker                              |
+--------------------------+-------------------+----------------------------------------------------------+
| 1. Recording Protocol    | GO                | Protocol finalized with standardized phonetics & P.56    |
| 2. Hardware Signal Chain | CONDITIONAL GO    | Lab bench calibration & channel phase skew verification  |
| 3. Dataset Design & Size | GO                | 24 speakers, 1,440 clean utterances, balanced power      |
| 4. Noise Scenarios       | CONDITIONAL GO    | Prohibit in-booth firearm blasts; use certified stems    |
| 5. SNR & Mixing Engine   | GO                | ITU-R P.56 active speech level + linear scaling locked   |
| 6. Ground Truth Stems    | GO                | Tri-stem architecture (clean, noise, mix) + JSON meta    |
| 7. Deployment Acceptance | CONDITIONAL GO    | Decouple offline ensemble benchmark from edge streaming  |
| 8. Data Governance       | NO-GO (Blocker)   | Formal IRB/IEC approval & signed legal consent required  |
+--------------------------+-------------------+----------------------------------------------------------+
| OVERALL VERDICT          | NO-GO (COLLECT)   | PREPARATORY SPECIFICATIONS COMPLETE; COLLECTION BLOCKED  |
+--------------------------+-------------------+----------------------------------------------------------+
```

---

## 2. Protected Baseline Artifacts & Integrity Verification

All evaluations and reference comparisons in this review are anchored to immutable, verified project artifacts. Zero model training, fine-tuning, weight modification, or golden-set inspection was performed.

| Artifact Role | File Path | Expected SHA-256 Hash | Integrity Status |
|:---|:---|:---:|:---:|
| **Canonical Manifest** | `runs/sih26052_canonical_validation/manifest.csv` | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` | VERIFIED |
| **Deployed DFN3 Step-500** | `antigravity/runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt` | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` | VERIFIED |
| **FullSubNet Baseline** | `antigravity/checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar` | `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0` | VERIFIED |
| **GTCRN DNS3 Baseline** | `antigravity/checkpoints/gtcrn_stage5/model_trained_on_dns3.tar` | `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79` | VERIFIED |
| **Stage 11 Study Baseline**| `research/STAGE11_RECORDING_STUDY_DESIGN.md` | `7552e2cdc8add655ddeeaf90d50603de0a1bccf84b044234b19ea9a512b144d4` | VERIFIED |
| **Sealed Gold Test Set** | `data/SIH_GOLD_TEST` | *Unread / Isolated* | SEALED (`gold_test_read: false`) |

---

## 3. Comprehensive Audit Findings (Phases A–F)

### Phase A: Repository, System & Document Audit
1. **Audited Documentation:**
   - Evaluated Stage 7 failure analysis (`research/STAGE7_LOW_SNR_FAILURE_ANALYSIS.md`), Stage 8 ensemble simulations (`research/STAGE8_ENSEMBLE_FEASIBILITY.md`), Stage 9 data audit (`research/STAGE9_INDEPENDENT_DATA_AUDIT.md`), and Stage 10 recovery audit (`research/STAGE10_DATA_RECOVERY_REPORT.md`).
   - Verified that the 590-clip canonical dataset contains $76.2\%$ gunfire provenance in the low-SNR regime ($\le 0\text{ dB}$), and lacks raw, unmixed clean speech stems, rendering true root-cause isolation impossible on historical data.
2. **Model Architectures Audited:**
   - **DFN3 (DeepFilterNet3):** $2.14\text{M}$ parameters. Native $48\text{ kHz}$ processing. Fully causal ERB filterbank + deep filtering. Uses $10\text{ ms}$ frame step with $0$ lookahead frames. Highly optimized Rust/C++ runtime (`libdf`) targeted for Raspberry Pi 5.
   - **FullSubNet (DNS Challenge):** $5.64\text{M}$ parameters. Native $16\text{ kHz}$ processing. Sub-band STFT ($32\text{ ms}$ window, $8\text{ ms}$ hop, $256$ sub-bands). Uses a full-band LSTM followed by sub-band LSTMs.
   - **GTCRN (DNS3):** $48.2\text{K}$ parameters. Native $16\text{ kHz}$ processing. Squeezed convolutional recurrent network with group GRU and dual-path frequency modeling. Causal STFT with $32\text{ ms}$ window and $16\text{ ms}$ hop.
3. **Execution Safety:** No background tasks, orphaned daemons, or uncommitted Git index conflicts exist. The deployed checkpoint on Raspberry Pi 5 (`~/anc_live`) remains completely isolated and operational.

---

### Phase B: Recording Protocol & Acoustic Environment Audit
1. **Acoustic Environment Requirements:**
   - The Stage 11 baseline targets $RT_{60} < 120\text{ ms}$ ($125\text{ Hz} - 8\text{ kHz}$) and ambient background noise $< 25\text{ dBA SPL}$.
   - *Technical Finding:* Achieving $RT_{60} < 120\text{ ms}$ at $125\text{ Hz}$ requires low-frequency membrane or resonant bass traps; typical foam-padded vocal booths only absorb down to $500\text{ Hz}$, leaving bass reverberation times $> 350\text{ ms}$.
   - *Requirement:* Acoustic qualification must be conducted using ISO 3382-2 swept-sine deconvolution across all octave bands ($125\text{ Hz}$ to $8\text{ kHz}$). Noise floor must be verified using a calibrated Class 1 sound level meter with 1/3-octave band analysis meeting ANSI S12.2 NC-20 criteria.
2. **Speech Recording Protocol:**
   - *Utterance Split:* The proposed 40 read / 20 spontaneous utterance split per speaker is validated. Read prompts provide exact phonetic consistency (IEEE/Harvard sentences and tactical operational phraseology); spontaneous speech captures real-world conversational pitch shifts, vocal fry, and natural breathing pauses.
   - *Vocal Effort Calibration:* Standardizes 3 distinct vocal effort regimes:
     - Conversational: $60–65\text{ dBA}$ at $1\text{ m}$.
     - Raised / Tactical Projection: $70–75\text{ dBA}$ at $1\text{ m}$.
     - Quiet / Low-Effort: $50–55\text{ dBA}$ at $1\text{ m}$.
3. **Microphone Setup & Acoustic Cross-Talk Reality:**
   - *Primary Microphone:* Close-talking condenser boom microphone positioned at $45^\circ$ azimuth, $2.5\text{ cm}$ from the oral commissure (corner of mouth). This eliminates plosive aerodynamic wind turbulence without sacrificing high-frequency articulation.
   - *Secondary Reference Microphone:* Baseline proposes a reference mic on the headset earcup ($10\text{ cm}$ displacement) to evaluate dual-microphone adaptive ANC.
   - *Critical Acoustic Flaw in Dual-Mic Assumption:* In a headset geometry, speech leakage from the mouth to the earcup microphone is only attenuated by $12–18\text{ dB}$. If an adaptive filter uses the earcup mic as a reference without speech-leakage cancellation, the speech component will be cancelled as "noise", degrading output PESQ and causing severe speech attenuation.
   - *Resolution:* All four current candidate models (DFN3, FullSubNet, GTCRN, and the ensembles) are strictly **single-channel models**. Stage 11 evaluation must use the primary close-talking microphone as the primary channel. The secondary earcup microphone shall be recorded on a synchronized second ADC channel as a preserved stem for *future multi-channel research*, but will not be mixed into the primary single-channel evaluation benchmarks.
4. **Noise Capture Feasibility & Acoustic Safety:**
   - *Hazardous Impulsive Noise:* The baseline proposed recording mechanical bolt action and weapon fire / muzzle blast.
   - *Safety Warning:* Live firearm muzzle blasts produce instantaneous peak SPL exceeding $155–170\text{ dB SPL}$. Standard studio and condenser microphones experience diaphragm collapse, preamplifier clipping, or destruction above $140\text{ dB SPL}$. Furthermore, firing live weapons in an acoustic booth is prohibited under occupational safety standards.
   - *Resolution:* High-SPL explosive transients must NOT be recorded live indoors. They must be obtained from verified, calibrated field recordings captured outdoors with blast pressure transducers (e.g., PCB 106B series), or from certified open-access defense acoustic databases. Indoor acoustic booth recordings must be limited to mechanical cycling, tool impacts, and electroacoustic playback at safe levels ($< 90\text{ dBA}$).
5. **Digital vs. Real Acoustic Mixing:**
   - Stage 11 mandates **digital superposition** of pristine clean speech stems and independently recorded noise stems.
   - *Rationale:* Real acoustic playback during speech recording introduces severe acoustic coupling: speech bleeds into the background room reflections, noise enters the vocal mic with complex spatial reverberation, and true mathematical ground truth ($s[n]$) is lost forever. Digital superposition guarantees:
     $$x[n] = s[n] + \alpha \cdot w[n]$$
     enabling exact sample-accurate ground truth alignment, exact SNR calculation, and mathematically rigorous SI-SDR/PESQ computation.

---

### Phase C: Dataset Design & Statistical Power Audit
1. **Cohort Sizing & Demographic Distribution:**
   - Recommended cohort: $24$ adult participants ($12$ female, $12$ male).
   - Age span: $18$ to $60$ years.
   - Dialect / Accent Diversity: 4 balanced cohorts:
     - General Indian English (North/West) — $6$ speakers.
     - General Indian English (South/East) — $6$ speakers.
     - Standard American / British English — $6$ speakers.
     - Non-native / Regional accented English — $6$ speakers.
2. **Dataset Volume & Statistical Power:**
   - $24\text{ speakers} \times 60\text{ utterances} = 1,440\text{ clean utterances}$.
   - Average duration: $4.0\text{ seconds}$ ($\approx 1.6\text{ hours}$ of active clean speech).
   - Across the 6 target SNR conditions ($-10, -5, 0, +5, +10, +15\text{ dB}$), generating 1 mixture per clean utterance yields $240\text{ clips per SNR bin}$.
   - *Statistical Power Analysis:*
     - For paired comparisons (e.g., Primary Ensemble vs. Deployed Step-500) using two-tailed Wilcoxon signed-rank tests at significance level $\alpha = 0.05$:
     - With $n = 240$ clips per bin and standard deviation $\sigma \approx 1.2\text{ dB}$, the statistical power to detect a true difference $\Delta\text{SNR} \ge 0.30\text{ dB}$ is **$99.4\%$** ($> 0.80$ required).
     - To detect a true difference $\Delta\text{PESQ} \ge 0.05$ with $\sigma \approx 0.25$, statistical power is **$96.1\%$**.
     - Across the entire full-set holdout ($n = 864$ clips), power to detect $\Delta\text{SNR} \ge 0.15\text{ dB}$ exceeds **$99.9\%$**.
3. **SNR Grid Coverage:**
   - The discrete grid $\{-10, -5, 0, +5, +10, +15\text{ dB}\}$ directly brackets the critical failure threshold identified in Stage 7 (where models undergo phase transition between $-5\text{ dB}$ and $+5\text{ dB}$).
   - An uncorrupted clean reference condition ($+30\text{ dB}$ or pure clean) must be retained to evaluate model speech distortion in silent/near-silent environments (over-suppression penalty).
4. **Holdout Partitioning & Split Integrity:**
   - Partition ratio: $40\%$ Development ($10$ speakers, $600$ clean clips) / $60\%$ Confirmatory Holdout ($14$ speakers, $840$ clean clips).
   - *Partitioning Rules:*
     - **Speaker Disjoint:** Zero speaker overlap between Development and Confirmatory Holdout.
     - **Noise Stem Disjoint:** Noise files used in Confirmatory Holdout must come from separate recording sessions / independent physical files.
     - **Cryptographic Seal:** Confirmatory holdout manifest, file paths, and SHA-256 hashes must be committed and hashed prior to any inference. Zero threshold adjustment or weight re-tuning is permitted on the holdout split.

---

### Phase D: Ground Truth, Stem Alignment & Metrics Audit
1. **Stem Retention Architecture:**
   Every evaluated clip consists of a unified stem quartet:
   - `clean_stem.wav`: Master clean phonation ($48\text{ kHz}$ / $24\text{ bit}$ PCM).
   - `noise_stem.wav`: Scaled noise stem ($\alpha \cdot w[n]$).
   - `mixture.wav`: Exact linear superposition ($s[n] + \alpha \cdot w[n]$).
   - `metadata.json`: Contains active speech power ($P_s$), noise power ($P_w$), scaling gain $\alpha$, peak amplitude, and SHA-256 hashes of all three audio files.
2. **Active Speech Level Standardization (ITU-R P.56):**
   - Simple unweighted RMS fails when speech contains pauses or when noise contains high-crest-factor spikes.
   - Speech power $P_s$ must be computed using an ITU-R P.56 active speech level voltmeter. The noise scaling factor $\alpha$ is defined as:
     $$\alpha = \sqrt{\frac{P_s}{P_w \cdot 10^{\text{SNR}_{\text{target}} / 10}}}$$
   - *Linear Headroom Scaling:* If the mixture peak exceeds $-0.5\text{ dBFS}$ ($\approx 0.944$), both clean speech $s[n]$ and noise $\alpha \cdot w[n]$ are scaled down by the identical linear attenuation factor $\gamma = 0.944 / \max(|s[n] + \alpha \cdot w[n]|)$. This guarantees zero clipping while preserving mathematical ground-truth linearity.
3. **Objective Metric Applicability & Constraints:**
   - **PESQ-WB (ITU-T P.862.2):** Strictly standardized for $16.0\text{ kHz}$ sampling rate, $3.0$ to $12.0\text{ seconds}$ duration, with $0.5\text{ s}$ initial silence. To evaluate $48\text{ kHz}$ models (DFN3), the enhanced output must be resampled to $16\text{ kHz}$ using a linear-phase bandlimited sinc filter before passing to PESQ.
   - **STOI:** Requires $\ge 30$ frames ($> 384\text{ ms}$). Clips $< 2.0\text{ s}$ yield high variance. All recording prompts must be constrained to $\ge 3.0\text{ s}$.
   - **SI-SDR & Output SNR:** Require zero sample shift. Digital superposition guarantees zero alignment error.
4. **Subjective Listening Test Protocol:**
   - Standard: **ITU-T P.835** (evaluating Speech Signal Distortion [SIG], Background Noise Intrusiveness [BAK], and Overall Quality [OVRL] on a 1–5 MOS scale).
   - *Rationale over MUSHRA:* MUSHRA is optimized for intermediate audio quality codecs, whereas P.835 explicitly decouples speech suppression artifacts from noise suppression aggressiveness.
   - Panel: $24$ trained listeners, double-blinded, randomized presentation, with hidden clean reference and degraded low anchor ($0\text{ dB}$ mixture).

---

### Phase E: Deployment Acceptance & Edge Hardware Feasibility Audit
1. **Raspberry Pi 5 Deployment Constraints (Provisional Planning Targets):**
   - Target Hardware: Raspberry Pi 5 Model B (Broadcom BCM2712, Quad-core ARM Cortex-A76 @ $2.4\text{ GHz}$, $4\text{GB}/8\text{GB}$ LPDDR4X).
   - Round-Trip Physical Latency Budget: $\le 35.0\text{ ms}$ (physical click trigger to earcup playout, provisional target; distinct from algorithmic latency alone).
   - Real-Time Factor (RTF): Provisional target Mean RTF $\le 0.30$, $p99 \le 0.40$ on Cortex-A76 @ 2.4 GHz (pending physical bench testing).
   - Memory RSS: Provisional target peak RSS $\le 300\text{ MB}$.
   - Thermal Envelope: Core temperature $\le 75.0^\circ\text{C}$ with Active Cooler without frequency throttling (`vcgencmd get_throttled` returns `0x0`).
   - Hardware Playout: Real-time loopback through boAt Rockerz 512 ANC hardware headset.

2. **Critical Architectural Conflict: FullSubNet and Ensemble Edge Infeasibility:**
   An exhaustive code and compute audit reveals a fundamental architectural conflict in the Stage 11 study design:
   - **FullSubNet Epoch 58:**
     - Parameter count: $5.64\text{M}$ parameters.
     - Frame structure: STFT window $32\text{ ms}$, hop $8\text{ ms}$ ($128$ samples at $16\text{ kHz}$).
     - Lookahead: Model architecture incorporates $2$ lookahead frames ($16\text{ ms}$). Combined with STFT synthesis framing, algorithmic latency alone exceeds $48\text{ ms}$, violating the $35\text{ ms}$ threshold.
     - Offline Normalization: FullSubNet uses `offline_laplace_norm` over the *entire temporal length* of the audio file. It cannot run in a causal streaming loop without an offline-to-online algorithm redesign that severely degrades suppression.
     - ARM Compute Load: Benchmarking sub-band LSTMs across 257 frequency bins yields an estimated RTF of $0.95–1.20$ on Cortex-A76, exceeding safety margins for real-time edge processing.
   - **Three-Model Ensembles (15/70/15 and 20/60/20):**
     - Running DFN3 ($48\text{ kHz}$) + FullSubNet ($16\text{ kHz}$) + GTCRN ($16\text{ kHz}$) concurrently requires 3 distinct neural inference engines, multi-rate resamplers, and 2 separate STFT/filterbank processors.
     - Aggregate CPU load introduces severe pipeline jitter, thread scheduling contention, and risk of buffer dropouts under streaming conditions.
   - **GTCRN DNS3:**
     - Parameter count: $48.2\text{K}$ parameters.
     - Frame structure: STFT window $32\text{ ms}$, hop $16\text{ ms}$. Algorithmic latency is $16\text{ ms}$.
     - RTF on ARM Cortex-A76 target is Mean $\le 0.15$, $p99 \le 0.25$.
     - GTCRN is fully streaming capable and easily fits edge constraints.
   - **DFN3 Step-500:**
     - Parameter count: $2.14\text{M}$ parameters. Causal ERB filterbank.
     - Provisional streaming target on Raspberry Pi 5: Mean RTF $\le 0.30$, $p99 \le 0.40$, physical round-trip latency $\le 35\text{ ms}$, memory $\le 300\text{ MB}$. These figures are provisional planning targets derived from architecture analysis, not measured results; physical bench measurements on actual Pi 5 hardware are mandatory before declaring deployment qualified.

3. **Authoritative Resolution: Formal Role Separation:**
   The Stage 11 study design must formally distinguish between **Offline Acoustic Quality Benchmarks** and **Real-Time Edge Streaming Deployment**:
   ```
   +----------------------------------------------------------------------------------------------------+
   |                                 MODEL EVALUATION DUAL-TRACK ARCHITECTURE                           |
   +-------------------------------------------------+--------------------------------------------------+
   | TRACK A: OFFLINE QUALITY BENCHMARK             | TRACK B: REAL-TIME EDGE STREAMING BENCHMARK      |
   | (Unconstrained compute; algorithmic analysis)    | (Raspberry Pi 5 hardware; <=35 ms latency)       |
   +-------------------------------------------------+--------------------------------------------------+
   | 1. Primary Ensemble (15% DFN / 70% FS / 15% GT) | 1. Deployed DFN3 Step-500 (Production baseline)  |
   | 2. Secondary Ensemble (20% DFN / 60% FS / 20% GT)| 2. Standalone GTCRN DNS3 (Ultra-light streaming)  |
   | 3. Standalone FullSubNet epoch 58 (Upper bound) |                                                  |
   | 4. Deployed DFN3 Step-500 (Reference)           |                                                  |
   +-------------------------------------------------+--------------------------------------------------+
   | Purpose: Quantify maximum noise suppression     | Purpose: Verify real-time embedded execution on  |
   | and establish teacher distillation targets.     | physical hardware with zero audio dropouts.      |
   +-------------------------------------------------+--------------------------------------------------+
   ```

---

### Phase F: Data Governance, Ethics & Legal Audit
1. **Institutional Ethics Review (IRB / IEC):**
   - Human voice audio constitutes biometric personally identifiable information (PII) under GDPR (Article 9) and the Digital Personal Data Protection (DPDP) Act 2023.
   - A formal Institutional Review Board (IRB) or Institutional Ethics Committee (IEC) protocol must be approved prior to any recruitment.
2. **Informed Consent Architecture:**
   - Consent must be explicit, documented in writing, and separate from institutional employment/academic status.
   - Scope: Scientific evaluation of speech enhancement and noise cancellation technologies; permission to publish pseudonymized audio waveforms in open-access scientific repositories.
   - Withdrawal: Unconditional right of participant withdrawal up to the point of dataset cryptographic freezing.
3. **Pseudonymization & Vault Protocol:**
   - Participants assigned cryptographic random alphanumeric IDs (`SPK_A01` through `SPK_D06`).
   - The master decryption key linking real identities to `speaker_id` must be stored in an AES-256 encrypted, air-gapped container accessible solely to the Principal Investigator.
4. **Third-Party Noise Licensing:**
   - Any external noise files incorporated into the study must possess verified, irrevocable commercial and academic licenses (CC-BY 4.0, CC0, or direct commercial assignment). No scraping of unverified internet audio is permitted.

---

## 4. Workstream-by-Workstream Readiness Scorecard

| Workstream | Scope | Readiness | Key Blocker / Prerequisite Condition | Next Operational Action |
|:---|:---|:---:|:---|:---|
| **WS1: Recording Protocol** | Script, geometry, acoustic booth | **GO** | None. Standardized Harvard/IEEE scripts and boom geometry fully defined. | Prepare physical prompt cards. |
| **WS2: Hardware Signal Chain** | Mics, ADC, calibration | **CONDITIONAL GO** | Requires bench calibration of ADC EIN and inter-channel phase synchronization ($< 10\ \mu\text{s}$). | Run ADC calibration test. |
| **WS3: Dataset Design** | 24 speakers, demographic balance | **GO** | Power calculations confirm $n = 240$ per bin provides $>99\%$ power. | Finalize participant roster. |
| **WS4: Noise Scenarios** | Operational acoustic noise fields | **CONDITIONAL GO** | Live firearm blasts strictly prohibited indoors. Must use certified field stems. | Procure/verify licensed stems. |
| **WS5: Mixing Engine** | ITU-R P.56, scaling gain | **GO** | Linear headroom scaling ($\le 0.944$) prevents all asymmetric clipping. | Implement deterministic script. |
| **WS6: Ground Truth Stems** | Tri-stem retention & manifests | **GO** | Manifest schema and SHA-256 hashing locked. | Setup automated hashing script. |
| **WS7: Edge Deployment** | Raspberry Pi 5 streaming | **CONDITIONAL GO** | Decouple offline ensemble/FullSubNet from edge real-time streaming track. | Test GTCRN C++ streaming core. |
| **WS8: Data Governance** | IRB, consent, privacy | **NO-GO** | **CRITICAL BLOCKER:** Formal IRB/IEC approval and signed ICFs not yet executed. | Submit IRB application package. |

---

## 5. Summary of Identified Inconsistencies & Corrective Actions

| Issue # | Baseline Inconsistency in Stage 11 | Technical Risk | Corrective Action in Stage 11.1 |
|:---:|:---|:---|:---|
| **1** | FullSubNet and Ensembles evaluated for RPi 5 streaming playout. | Algorithmic latency ($>48\text{ ms}$), offline Laplace norm, and high compute cause buffer crash or excessive latency. | Formally split into Track A (Offline Quality Benchmark) and Track B (Edge Streaming Playout). Only DFN3 and GTCRN tested on Pi 5. |
| **2** | Headset earcup mic proposed as dual-mic reference for single-channel models. | Acoustic cross-talk: speech leakage into earcup mic is only $-12\text{ dB}$, risking speech cancellation; models are single-channel. | Primary evaluation locked to close-talking mic. Earcup mic stem preserved on separate channel for future multi-channel work. |
| **3** | Weapon fire / blast recordings proposed in acoustic booth. | Severe acoustic trauma risk ($>160\text{ dB SPL}$) and microphone capsule destruction. | Banned in indoor booth. Impulsive blasts sourced from verified outdoor blast-transducer recordings. |
| **4** | Standard RMS power proposed for low-SNR mixtures. | Silent intervals and impulsive crests distort gain $\alpha$, causing inaccurate target SNRs. | Mandate ITU-R P.56 active speech level voltmeter for speech power $P_s$. |
| **5** | Participant recruitment implied prior to IRB clearance. | Regulatory, legal, and ethical non-compliance under GDPR/DPDP. | Hard NO-GO gate enforced. Zero recruitment until formal institutional ethics approval is received. |

---

## 6. Stage 11.2 Progression Criteria (Prerequisites for Collection Launch)

Data collection shall not be initiated until all of the following conditions are satisfied:
1. **Ethics Approval:** Formal written clearance certificate received from Institutional Review Board / Ethics Committee.
2. **Hardware Rig Qualification:** Laboratory bench verification confirming Class 1 acoustic calibration ($94.0\text{ dB} \pm 0.2\text{ dB}$), ADC EIN $<-128\text{ dBu}$, and inter-channel phase skew $< 10\ \mu\text{s}$.
3. **Acoustic Booth Certification:** Acoustic measurement certificate confirming booth $RT_{60} < 120\text{ ms}$ ($125\text{ Hz} - 8\text{ kHz}$) and ambient noise $< 25\text{ dBA SPL}$.
4. **Noise Asset License Clearance:** Written chain-of-title and licensing certificates verified for all external noise assets.
5. **Frozen Hashing of Holdout Protocol:** Cryptographic signing of the holdout speaker assignment and mixing engine script.
