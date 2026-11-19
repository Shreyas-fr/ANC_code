# SIH 26052 — Stage 11: Recording Study Preparation & Independent Validation Protocol

**Status:** Study Specification & Review Design · **Pre-Collection Phase**  
**Execution Boundary:** Planning, protocol specification, and data governance design only. **No participant recruitment, no participant contact, no audio recording, no hardware procurement, and no data collection has begun.** All activities require formal institutional, ethics, and legal sign-off before commencement.  
**Baseline & Frozen Candidate Status:**  
- **Deployed Reference:** DFN3 Step-500 (`bc1fc9b76958...`) remains unchanged and active on Raspberry Pi 5 (`~/anc_live` untouched).  
- **Primary Research Candidate:** Three-model ensemble (DFN3 Step-500 15% + FullSubNet epoch 58 70% + GTCRN DNS3 15%).  
- **Secondary Research Candidate:** Three-model ensemble (DFN3 Step-500 20% + FullSubNet epoch 58 60% + GTCRN DNS3 20%).  
- **Standalone Benchmark Candidate:** FullSubNet epoch 58 (official pretrained weights).  
- **Sealed Benchmark:** `SIH_GOLD_TEST` remains isolated and unread (`gold_test_read: false`).  
- **Development Freeze:** Zero weight tuning, hyperparameter search, or threshold optimization on the 590-clip canonical set.

---

## 1. Study Objective & Motivation

Stages 5 through 10 established that architectural iterations on the repeatedly used 590-clip canonical benchmark have reached diminishing returns:
1. All single-channel models fail catastrophically at $\le 0\text{ dB}$ input SNR ($100\%$ failure at $-10\text{ dB}$; $>91\%$ failure across $\le 0\text{ dB}$).
2. The canonical benchmark lacks verifiable source recording IDs (`clean_source_id`, `noise_source_id`, `rir_source_id` are `N/A`) and has severe confounding ($76.2\%$ of low-SNR clips derive from a single gunfire provenance source).
3. The historical training sets cannot be fully proven disjoint from candidate public datasets due to unevidenced remote Kaggle snapshots.

Therefore, **the most urgent technical requirement is not another model training run, but an independent, reproducible, rigorously governed audio recording study.**

Stage 11 establishes the complete technical and governance specification to collect a pristine, non-gold, provenance-verified audio corpus designed specifically to test the four frozen systems without circularity or test-set leakage.

---

## 2. Workstream Specifications

```
+---------------------------------------------------------------------------------------------------+
|                                  STAGE 11 WORKSTREAM ARCHITECTURE                                 |
+--------------------------+--------------------------+--------------------------+------------------+
| 1. Recording Protocol    | 2. Equipment & Chain     | 3. Dataset Design        | 4. Noise Matrix  |
| - Acoustic enclosure     | - Measurement mic (cal)  | - 20-30 consenting spkrs | - Stationary     |
| - Dual-mic headset jig   | - 24-bit/48kHz interface | - Balanced phonetics     | - Non-stationary |
| - Read & spontaneous     | - 94 dB SPL calibrator   | - Read + Spontaneous     | - Impulsive/Arms |
+--------------------------+--------------------------+--------------------------+------------------+
| 5. SNR & Mixing Engine   | 6. Ground Truth Stem     | 7. Data Governance       | 8. Split Freeze  |
| - ITU-R P.56 active lev  | - Clean reference stem   | - IRB / Ethics protocol  | - Speaker-holdout|
| - Grid: -10 to +15 dB    | - Isolated noise stem    | - Informed consent form  | - Session-holdout|
| - Retained linear gain   | - Real acoustic capture  | - GDPR/DPDP pseudonyms   | - SHA-256 sealed |
+--------------------------+--------------------------+--------------------------+------------------+
```

### Workstream 1: Recording Protocol
- **Acoustic Environment:** Acoustically treated booth/enclosure meeting ANSI S12.2 / ISO 1999 criteria ($RT_{60} < 120\text{ ms}$ across $125\text{ Hz} - 8\text{ kHz}$; ambient background noise $< 25\text{ dBA}\text{ SPL}$).
- **Speech Capture Procedure:**
  - **Read Speech:** Standardized, phonetically balanced phoneme sets (e.g., Harvard/IEEE sentences, TIMIT-style phonetically rich scripts, and operational military/tactical radio phraseology).
  - **Spontaneous Speech:** Task-oriented dialogue, unscripted scenario descriptions, and continuous count sequences to evaluate natural prosodic variation, vocal effort shifts, and conversational pauses.
  - **Vocal Effort Levels:** Documented calibration across normal conversational ($60–65\text{ dBA}$ at 1 meter), raised/projected ($70–75\text{ dBA}$), and simulated stress speech.
- **Physical Rigging & Geometry:**
  - Fixed boom-microphone headset mount placed at standardized angle ($45^\circ$) and distance ($2.5\text{ cm}$ from the oral cavity corner to prevent plosive breath pops).
  - Synchronized secondary reference microphone placed on the outer headset earcup ($10\text{ cm}$ displacement) to capture ambient incident noise for dual-microphone adaptive cancellation studies.

### Workstream 2: Equipment & Signal Chain Specifications
- **Primary Vocal Microphones:**
  - Laboratory Reference: Class 1 1/2-inch free-field condenser microphone (e.g., Brüel & Kjær 4189 or Earthworks M30), flat frequency response ($\pm 1\text{ dB}$ from $20\text{ Hz}$ to $20\text{ kHz}$).
  - Tactical / Operational Interface: Military-grade dynamic or electret noise-cancelling boom microphone matching field headset impedance.
- **Audio Interface & ADC:**
  - Professional multi-channel audio interface with ultra-low equivalent input noise ($<-128\text{ dBu}$ A-weighted, THD+N $<0.001\%$).
  - Master Archival Format: Uncompressed linear PCM, $48.0\text{ kHz}$ sampling rate, $24\text{ bits}$ depth.
- **Acoustic Calibration Chain:**
  - Class 1 acoustic calibrator generating $94.0\text{ dB}\text{ SPL} \pm 0.2\text{ dB}$ at $1,000\text{ Hz}$ applied before and after every recording session.
  - Fixed analog preamplifier gain steps; software digital attenuation prohibited during raw acquisition.

### Workstream 3: Dataset Design & Participant Allocation
- **Cohort Size:** 20 to 30 consenting adult speakers.
- **Demographic Balance:** Balanced gender distribution ($50\%$ female, $50\%$ male), diverse adult age distribution ($18–60$), and multiple native and non-native regional English dialect groups.
- **Volume & Allocation:**
  - Minimum 60 distinct utterances per speaker ($40$ read sentences, $20$ spontaneous phrases).
  - Average utterance duration: $3.0$ to $6.0\text{ seconds}$.
  - Target speech volume: $\sim 1,500$ clean utterances ($\approx 2.0\text{ hours}$ of active clean phonation).
- **Session Structure:** Multi-session capture over separate days to capture intra-speaker vocal variation and acoustic setup repeatability.

### Workstream 4: Operational Noise Scenarios
Independent noise fields captured or lawfully licensed with complete acoustic documentation:
1. **Stationary Backgrounds:** Heavy diesel engine idle, HVAC ventilation, continuous wind buffeting ($15–30\text{ km/h}$).
2. **Non-Stationary / Operational:** Multi-rotor drone flyby/hover ($4\text{k} - 8\text{k}\text{ RPM}$ harmonic blade pass frequencies), tracked vehicle interior cabin rumble, crowded operations center babble.
3. **Impulsive & Transient:** Mechanical weapon bolt cycling, heavy impact/hammer drops, simulated muzzle blast/artillery acoustic signatures captured under strict safety protocols with wide-dynamic-range instrumentation (preventing pre-ADC analog clipping).

### Workstream 5: Predefined SNR Grid & Mixing Engine
- **Active Speech Level Standardization:** Speech level defined via ITU-R P.56 active speech level measurement ($L_{\text{speech}}$).
- **Target SNR Grid:** Exact, balanced discrete condition grid:
  $$\text{SNR}_{\text{target}} \in \{-10.0\text{ dB}, -5.0\text{ dB}, 0.0\text{ dB}, +5.0\text{ dB}, +10.0\text{ dB}, +15.0\text{ dB}\}$$
  Plus an uncorrupted near-clean reference condition ($+30\text{ dB}$ or clean).
- **Reproducible Scaling Gain Formulation:**
  For clean speech vector $s[n]$ with active power $P_s$ and noise vector $w[n]$ with RMS power $P_w$, the noise scaling factor $\alpha$ is computed as:
  $$\alpha = \sqrt{\frac{P_s}{P_w \cdot 10^{\text{SNR}_{\text{target}} / 10}}}$$
  $$x[n] = s[n] + \alpha \cdot w[n]$$
- **Headroom & Normalization Policy:** Mixture $x[n]$ monitored for peak headroom ($|x[n]| \le 0.99$). If peak exceeds $0.99$, symmetric global linear scaling is applied to both $s[n]$ and $\alpha \cdot w[n]$ identically, strictly preserving exact clean ground truth alignment without asymmetric clipping.

### Workstream 6: Ground Truth Stems & Derivatives
- **Retained Master Files:** Every evaluation example retains:
  1. `clean_stem.wav`: Raw active clean speech (unprocessed).
  2. `noise_stem.wav`: Scaled noise stem ($\alpha \cdot w[n]$).
  3. `mixture.wav`: Additive superposition ($x[n]$).
  4. `metadata.json`: Active speech power, unscaled noise power, exact $\alpha$, duration, sample rate, microphone ID, and SHA-256 hashes of all three audio files.
- **Deterministic Evaluation Derivatives:** Mono $16.0\text{ kHz}$ float32 derivatives generated using a single pre-declared bandlimited polyphase sinc resampler (`sox` or `torchaudio.transforms.Resample(orig_freq=48000, new_freq=16000, resampling_method="sinc_interpolation")`).

### Workstream 7: Data Governance, Privacy & Licensing
- **Institutional Ethics Review (IRB / Institutional Ethics Committee):** Study design submitted to the appropriate institutional oversight body.
- **Informed Consent Architecture:**
  - Written, informed participant consent covering voice audio capture, acoustic speech enhancement evaluation, retention periods, and non-commercial research use.
  - Express right of withdrawal prior to dataset freezing.
- **Privacy & Anonymization:**
  - Absolute ban on personally identifiable information (PII) in filenames, audio content, or public reports.
  - Cryptographic pseudonymization: Speakers assigned random IDs (`SPK_A01`, `SPK_B02`). Salted identity mapping keys stored in an air-gapped, encrypted vault accessible only to the principal investigator.
- **Intellectual Property & Licensing:**
  - All speech captured under explicit project-owned assignment.
  - All noise recordings validated for research redistribution licenses (e.g., CC-BY-4.0, direct commercial assignment) with complete chain-of-title documentation.

### Workstream 8: Split Integrity & Independence Guarantee
- **Disjoint Partitioning Policy:**
  - **Zero Speaker Overlap:** Speakers partitioned into disjoint subsets: Development/Tuning ($40\%$) and Confirmatory Holdout ($60\%$). No speaker in the confirmatory set may appear in any training, validation, or hyperparameter selection pool.
  - **Zero Noise Source Overlap:** Noise sessions strictly segregated; holdout noise stems recorded in separate physical environments/days from development noise.
- **Cryptographic Seal:**
  - Manifest of the confirmatory set frozen and SHA-256 hashed before model inference begins.
  - Zero post-collection threshold adjustment or weight re-tuning permitted.

---

## 3. Post-Collection Evaluation Protocol

Once the dataset is collected, verified, and sealed, the evaluation will run as a single-pass, blinded execution comparing exactly four systems:

### 3.1 Frozen Candidate Systems
1. **Primary Ensemble:** DFN3 Step-500 ($15\%$) + FullSubNet epoch 58 ($70\%$) + GTCRN DNS3 ($15\%$).
2. **Secondary Ensemble:** DFN3 Step-500 ($20\%$) + FullSubNet epoch 58 ($60\%$) + GTCRN DNS3 ($20\%$).
3. **Standalone FullSubNet:** Epoch 58 (official weights, 16 kHz).
4. **Deployed DFN3 Step-500:** Current production baseline (`bc1fc9b76958...`, 48 kHz).

### 3.2 Evaluation Metrics & Gates
- **Objective Metrics:** Output SNR (dB), SI-SDR (dB), STOI, and PESQ-WB evaluated against the pristine clean speech stem.
- **Compliance Gates:**
  - Full-Set Mean SNR $> 15.0\text{ dB}$.
  - Full-Set Mean PESQ-WB $> 2.50$.
  - Joint Pass Rate across criteria ($\text{SNR} > 15\text{ dB} \land \text{STOI} > 0.85 \land \text{PESQ} > 2.5$).
  - Low-SNR Breakdown: Explicit reporting on $-10\text{ dB}$, $-5\text{ dB}$, and $0\text{ dB}$ strata.
- **Blinded Subjective Listening Panel:**
  - MUSHRA-style (MUltiple Stimuli with Hidden Reference and Anchor) listening assessment conforming to ITU-R BS.1534.
  - Evaluators blinded to model identity, scoring speech naturalness, background noise intrusiveness, and artifact severity.

### 3.3 Hardware Feasibility & Edge Playout Gate
Following independent acoustic validation, the top-performing candidate must pass the physical Raspberry Pi 5 deployment audit against these provisional acceptance criteria (provisional planning targets, pending physical bench testing):
1. End-to-end physical round-trip latency ($\le 35.0\text{ ms}$ budget from acoustic click trigger to earcup playout).
2. RTF $\le 0.30$ (mean), $p99 \le 0.40$ on quad-core Cortex-A76 ($2.4\text{ GHz}$). Pi 5 capability cannot be inferred from legacy Pi 4 benchmarks; physical measurements on actual Pi 5 hardware are required.
3. Memory RSS $\le 300\text{ MB}$.
4. Sustained 60-minute continuous streaming with zero ALSA buffer underruns (XRUNs = 0), zero dropped blocks, and core thermal equilibrium below $75^\circ\text{C}$ (`throttled=0x0`).
5. Real acoustic loopback through the boAt Rockerz 512 ANC hardware headset.

---

## 4. Execution Governance & Decision Summary

| Governance Principle | Status | Enforcement Mechanism |
|:---|:---:|:---|
| **Model Retraining** | **FROZEN** | No model training or fine-tuning permitted in Stage 11. |
| **Active Deployment** | **FROZEN** | DFN3 Step-500 remains active on Raspberry Pi 5. |
| **Ensemble Configurations** | **FROZEN** | Weights locked at 15/70/15 and 20/60/20. No search allowed. |
| **Gold Benchmark** | **SEALED** | `SIH_GOLD_TEST` remains untouched (`gold_test_read: false`). |
| **Canonical Set** | **FROZEN** | No further optimization on the 590-clip development benchmark. |
| **Participant Acquisition** | **HOLD** | Requires formal institutional ethics review and legal sign-off. |

