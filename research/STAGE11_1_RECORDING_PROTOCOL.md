# SIH 26052 — Stage 11.1: Audio Recording Protocol Specification

**Document Version:** 1.0.0 · **Date:** 2026-11-13  
**Status:** Operational Protocol Specification · **Pre-Collection Phase**  
**Execution Boundary:** Standard operating procedure for laboratory acoustic capture. Requires formal ethics approval and hardware qualification prior to physical execution.

---

## 1. Acoustic Environment & Facility Qualification

### 1.1 Acoustic Enclosure Specifications
All clean speech recording must occur within a certified double-wall acoustic isolation booth meeting the following strict criteria:
- **Reverberation Time ($RT_{60}$):** $\le 120\text{ ms}$ uniformly across all octave bands from $125\text{ Hz}$ to $8\text{ kHz}$.
- **Ambient Acoustic Noise Floor:** $\le 25\text{ dBA SPL}$ (slow weighting); $\le 30\text{ dBC SPL}$; meeting Noise Criterion **NC-20** across all 1/3-octave frequency bands.
- **Air Handling & HVAC:** Ultra-quiet baffled ventilation; airflow velocity at participant head $< 0.1\text{ m/s}$ to prevent aerodynamic convection noise on microphone capsules.

### 1.2 Pre-Session Acoustic Qualification Procedure
Prior to seating any participant in a recording session, the operator must execute the following acoustic verification:
1. **Ambient Noise Measurement:**
   - Mount a Class 1 Sound Level Meter (IEC 61672-1) at the designated participant head position.
   - Record ambient equivalent continuous sound level ($L_{\text{Aeq}}$) for $60\text{ seconds}$.
   - If $L_{\text{Aeq}} > 25.0\text{ dBA}$, identify external acoustic or electrical intrusion; do not proceed until resolved.
2. **Reverberation Verification ($RT_{60}$):**
   - Execute a synchronized logarithmic sine sweep ($20\text{ Hz}$ to $20\text{ kHz}$ over $10\text{ seconds}$) through a calibrated omnidirectional loudspeaker.
   - Capture the room impulse response (RIR) using the laboratory measurement microphone.
   - Calculate Schroeder backward integration to derive $T_{20}$ and $T_{30}$; extrapolate $RT_{60}$.
   - Confirm $RT_{60}(f) \le 120\text{ ms}$ for octave centers $125\text{ Hz}, 250\text{ Hz}, 500\text{ Hz}, 1\text{ kHz}, 2\text{ kHz}, 4\text{ kHz}, 8\text{ kHz}$.

---

## 2. Hardware Signal Chain & Gain Staging

```
+---------------------------------------------------------------------------------------------------------+
|                                    SYNCHRONOUS AUDIO SIGNAL CHAIN                                       |
+--------------------------+--------------------+--------------------------------+------------------------+
| Transducer               | Physical Rigging   | Preamplifier / ADC             | Archival Storage       |
+--------------------------+--------------------+--------------------------------+------------------------+
| Ch 1: Close-Talking Mic  | Headset boom mount | Discrete Class-A preamp        | Linear PCM             |
| (Condenser Cardioid)     | 45 deg, 2.5 cm     | 24-bit / 48.0 kHz synchronous  | Broadcast WAV (BWF)    |
|                          |                    | EIN < -128 dBu, THD+N < 0.001% | Mono / Uncompressed    |
+--------------------------+--------------------+--------------------------------+------------------------+
| Ch 2: Earcup Ref Mic     | Outer earcup shell | Synchronous shared ADC clock   | Linear PCM             |
| (Omni / Boundary)        | 10 cm displacement | Zero inter-channel phase drift | Broadcast WAV (BWF)    |
|                          |                    | Phase skew < 10 microseconds   | Mono / Uncompressed    |
+--------------------------+--------------------+--------------------------------+------------------------+
| Ch 3: Lab Measurement    | Free-field stand   | Fixed calibrated gain          | Calibration Reference  |
| (Class 1 Free-field)     | 30 cm on-axis      | 94.0 dB SPL = -20.0 dBFS       | Linear PCM             |
+--------------------------+--------------------+--------------------------------+------------------------+
```

### 2.1 Acoustic Calibration Procedure
Every recording day must begin and end with an acoustic calibration run:
1. Seat the acoustic calibrator (Class 1, generating $94.0\text{ dB SPL} \pm 0.2\text{ dB}$ at $1,000\text{ Hz}$) onto the laboratory measurement microphone and the reference microphone.
2. Record a $10\text{ second}$ continuous calibration tone.
3. Adjust analog preamplifier gain such that $94.0\text{ dB SPL}$ maps to exactly **$-20.0\text{ dBFS}$ RMS** in the digital recording software.
4. Lock all analog preamplifier gain dials with physical collars or tamper-evident tape. Software digital trim, auto-gain control (AGC), noise gates, and dynamic limiters are **strictly prohibited**.
5. Save calibration files as `CAL_<SESSION_ID>_PRE.wav` and `CAL_<SESSION_ID>_POST.wav`.

### 2.2 Transducer Positioning & Geometry
- **Channel 1 (Primary Vocal Microphone):**
  - Type: High-fidelity miniature electret/condenser cardioid microphone mounted on a rigid, adjustable boom arm attached to the participant's headset.
  - Position: Lateral displacement $45^\circ$ from the sagittal plane, distance exactly $2.5\text{ cm}$ ($\pm 0.2\text{ cm}$) from the oral commissure (corner of the lips).
  - Acoustic Rationale: Avoids direct aerodynamic plosive wind blasts ("p", "t", "b") while maintaining a high direct-to-reverberant acoustic ratio and SNR ($> 45\text{ dB}$ above electrical/ambient floor).
- **Channel 2 (Secondary Reference Microphone):**
  - Type: Calibrated wideband omnidirectional capsule integrated flush into the external shell of the right earcup ($10.0\text{ cm}$ physical displacement from Channel 1).
  - Purpose: Records simultaneous ambient acoustic field and speech leakage for future multi-channel ANC research.
- **Channel 3 (Laboratory Reference Microphone):**
  - Type: 1/2-inch Class 1 free-field measurement microphone mounted on an isolated floor boom at a distance of $30.0\text{ cm}$ on-axis ($0^\circ$) from the participant's mouth, with acoustic pop-screen.

---

## 3. Participant Protocol & Speech Elicitation

### 3.1 Participant Preparation & Briefing
1. Participant seated in an ergonomically stable, non-squeaking chair inside the booth.
2. Headset fitted securely to head; boom arm measured with a non-reflective positioning caliper to confirm $2.5\text{ cm}$ distance and $45^\circ$ angle.
3. Participant provided with an anti-glare tablet displaying prompt scripts at eye level. Paper scripts are prohibited to prevent paper rustle artifacts.
4. Participant briefed to maintain consistent head posture and avoid touching the headset or cable during phonation.

### 3.2 Speech Elicitation Structure (60 Utterances per Speaker)
Each participant completes three distinct recording blocks:

#### Block A: Standardized Phonetically Balanced Read Speech (40 Utterances)
- **Harvard / IEEE Sentences (30 Utterances):**
  - Selected from standard phonetically balanced IEEE lists (e.g., *"The birch canoe slid on the smooth planks."*, *"Glue the sheet to the dark blue background."*).
  - Covers complete phoneme distribution of standard English with balanced consonant-vowel transitions.
- **Tactical / Operational Military Communications (10 Utterances):**
  - Standardized phonetic alphabet and tactical radio command phrases (e.g., *"Bravo Two, verify coordinates grid Seven-Niner-Sierra, over."*, *"Maintain visual contact on convoy heading zero-three-zero."*).
  - Evaluates performance on critical target domain phraseology.

#### Block B: Spontaneous & Elicited Speech (20 Utterances)
- **Task-Oriented Picture Descriptions (10 Utterances):**
  - Participant describes complex visual action photographs for $15–20\text{ seconds}$, segmented into natural utterances of $3.0–6.0\text{ seconds}$.
- **Direction & Instruction Giving (5 Utterances):**
  - Participant explains route directions or operational procedures in their own natural syntax and cadence.
- **Continuous Counting & Digit Strings (5 Utterances):**
  - Utterances consisting of continuous 7-digit strings and military grid references spoken at natural conversational pace.

#### Block C: Controlled Vocal Effort Variation
The 60 utterances must be distributed across three calibrated vocal effort levels:
1. **Conversational Effort (40 Utterances):** Natural speaking voice ($60–65\text{ dBA}$ at $1\text{ m}$).
2. **Projected / Raised Effort (10 Utterances):** Simulating loud field communication over distance or engine background ($70–75\text{ dBA}$ at $1\text{ m}$).
3. **Low / Quiet Effort (10 Utterances):** Controlled, low-intensity communication ($50–55\text{ dBA}$ at $1\text{ m}$).

### 3.3 Take Protocol & Artifact Screening
- The recording engineer monitors live audio via closed-back reference headphones and an active peak/RMS meter.
- **Retake Policy:** A take is rejected and re-recorded immediately if:
  - Pronunciation contains a stutter, cough, or false start.
  - Headset boom shifts or is brushed by hand/clothing.
  - Peak digital level exceeds $-3.0\text{ dBFS}$ (prevention of analog/ADC saturation).
- A minimum of $0.5\text{ seconds}$ of silent acoustic lead-in and $0.5\text{ seconds}$ of silent acoustic run-out must be maintained before and after each utterance phonation.

---

## 4. Digital Mixing Engine Specification

To guarantee zero cross-talk, exact mathematical ground truth, and reproducible condition generation, all evaluation mixtures are created using digital superposition of pristine master stems.

```
+---------------------------------------------------------------------------------------------------------+
|                                    DIGITAL MIXING ENGINE WORKFLOW                                       |
+--------------------------+---------------------+-------------------------------+------------------------+
| 1. Clean Speech Stem     | 2. Noise Stem       | 3. ITU-R P.56 Level Engine    | 4. Superposition       |
+--------------------------+---------------------+-------------------------------+------------------------+
| s[n]: 48 kHz / 24-bit    | w[n]: 48 kHz / 24-b | Compute active power P_s      | Mixture:               |
| Active duration 3-6 s    | Random segment      | Compute noise RMS power P_w   | x[n] = s[n] + a * w[n] |
| Zero clipping            | Independent file    | a = sqrt(P_s / (P_w * 10^0.1*SNR)) | Lin headroom check     |
+--------------------------+---------------------+-------------------------------+------------------------+
```

### 4.1 ITU-R P.56 Active Speech Level Calculation
Standard unweighted root-mean-square (RMS) over the entire waveform underestimates speech power because long inter-word pauses artificially deflate the denominator. Speech level must be computed via ITU-R P.56:
1. Let $s[n]$ be the clean speech discrete-time sequence of length $N$ at sampling rate $f_s = 48,000\text{ Hz}$.
2. Pass $s[n]$ through an envelope follower with attack time constant $\tau_{\text{att}} = 0.03\text{ s}$ ($30\text{ ms}$) and decay time constant $\tau_{\text{dec}} = 0.03\text{ s}$.
3. Calculate the active speech power $P_s$ exclusively over frames where the speech envelope exceeds the adaptive activity threshold ($15\text{ dB}$ below the mean active level):
   $$L_s = 10 \log_{10}(P_s) \quad [\text{dBFS}]$$

### 4.2 Noise Power & Target Scaling Factor ($\alpha$)
1. Let $w[n]$ be a random continuous slice of the selected noise recording possessing the identical sample length $N$ as $s[n]$.
2. Compute the unweighted RMS power of the noise slice over its full length:
   $$P_w = \frac{1}{N} \sum_{n=0}^{N-1} |w[n]|^2$$
3. For a designated target SNR in decibels ($\text{SNR}_{\text{target}} \in \{-10.0, -5.0, 0.0, +5.0, +10.0, +15.0\}\text{ dB}$), compute the linear noise scaling gain $\alpha$:
   $$\alpha = \sqrt{\frac{P_s}{P_w \cdot 10^{\text{SNR}_{\text{target}} / 10}}}$$

### 4.3 Superposition & Non-Clipping Headroom Normalization
1. Form the raw digital mixture vector:
   $$x_{\text{raw}}[n] = s[n] + \alpha \cdot w[n]$$
2. Evaluate the absolute peak amplitude of the raw mixture:
   $$M_{\text{peak}} = \max_{0 \le n < N} |x_{\text{raw}}[n]|$$
3. **Headroom Policy:**
   - If $M_{\text{peak}} \le 0.944$ (corresponding to $-0.5\text{ dBFS}$ true peak), set attenuation factor $\gamma = 1.0$.
   - If $M_{\text{peak}} > 0.944$, set attenuation factor:
     $$\gamma = \frac{0.944}{M_{\text{peak}}}$$
   - Apply $\gamma$ identically to both clean speech and scaled noise:
     $$s_{\text{norm}}[n] = \gamma \cdot s[n]$$
     $$w_{\text{norm}}[n] = \gamma \cdot (\alpha \cdot w[n])$$
     $$x[n] = s_{\text{norm}}[n] + w_{\text{norm}}[n]$$
   - *Mathematical Guarantee:* This symmetric scaling preserves the exact target SNR without altering the acoustic balance, avoids asymmetric peak clipping, and ensures that $s_{\text{norm}}[n]$ remains the mathematically perfect ground truth reference.

---

## 5. Standardized Resampling Pipeline (48 kHz to 16 kHz)

Because FullSubNet and GTCRN operate natively at $16.0\text{ kHz}$ while DFN3 operates natively at $48.0\text{ kHz}$, cross-model comparisons require a standardized, bit-exact resampling protocol:

1. **Anti-Aliasing Filter Specification:**
   - Resampler: Bandlimited polyphase Kaiser-windowed sinc interpolation (filter order $N_{\text{filter}} = 128$, shape parameter $\beta = 8.5$).
   - Passband: $0\text{ Hz}$ to $7,200\text{ Hz}$ with passband ripple $< \pm 0.05\text{ dB}$.
   - Stopband Attenuation: $> 100.0\text{ dB}$ above $8,000\text{ Hz}$ (Nyquist frequency at $16\text{ kHz}$).
   - Phase Response: Strictly linear phase (constant group delay).
2. **Standard Implementation Reference:**
   ```python
   import torchaudio.transforms as T
   resampler_48k_to_16k = T.Resample(
       orig_freq=48000, 
       new_freq=16000, 
       resampling_method="sinc_interp_kaiser",
       lowpass_filter_width=64,
       rolloff=0.92,
       beta=8.5
   )
   ```
3. **Evaluation Rules:**
   - Inputs to FullSubNet and GTCRN are derived by resampling `mixture.wav` ($48\text{ kHz}$) to $16\text{ kHz}$ using this deterministic filter.
   - For objective PESQ-WB evaluation of DFN3 ($48\text{ kHz}$ output), the enhanced output is resampled to $16\text{ kHz}$ using this exact filter before passing to the ITU-T P.862.2 engine.

---

## 6. Archival Directory Structure & File Naming Conventions

All recorded and generated data must conform to the following directory hierarchy:

```
stage11_data/
├── master_raw/
│   └── SPK_A01/
│       └── SESS_01/
│           ├── SPK_A01_S01_U001_raw_ch1_vocal.wav
│           ├── SPK_A01_S01_U001_raw_ch2_earcup.wav
│           └── SPK_A01_S01_U001_raw_ch3_meas.wav
├── clean_stems/
│   └── SPK_A01_S01_U001_clean.wav
├── noise_stems/
│   ├── NOISE_STAT_DIESEL_01.wav
│   └── NOISE_NONSTAT_DRONE_01.wav
├── evaluation_corpus/
│   ├── mixtures/
│   │   ├── MIX_DEV_00001.wav
│   │   └── MIX_HLD_00001.wav
│   ├── clean_refs/
│   │   ├── REF_DEV_00001.wav
│   │   └── REF_HLD_00001.wav
│   ├── noise_scaled/
│   │   ├── NSE_DEV_00001.wav
│   │   └── NSE_HLD_00001.wav
│   └── metadata/
│       ├── MIX_DEV_00001.json
│       └── MIX_HLD_00001.json
└── manifests/
    ├── dev_manifest.csv
    └── holdout_manifest.csv
```

### 6.1 Per-Clip Metadata JSON Specification
Each evaluation clip must have an accompanying JSON metadata file (`<CLIP_ID>.json`) recording:
```json
{
  "clip_id": "MIX_HLD_00001",
  "speaker_id": "SPK_C04",
  "session_id": "SESS_02",
  "utterance_type": "read_harvard",
  "vocal_effort": "conversational",
  "target_snr_db": -5.0,
  "measured_speech_p56_dbfs": -22.41,
  "measured_noise_rms_dbfs": -18.15,
  "scaling_gain_alpha": 0.86542,
  "headroom_attenuation_gamma": 0.98500,
  "peak_amplitude_dbfs": -0.50,
  "duration_seconds": 4.25,
  "split": "holdout",
  "sample_rate_hz": 48000,
  "bit_depth": 24,
  "hashes": {
    "clean_stem_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "noise_stem_sha256": "4a5b6c...",
    "mixture_sha256": "9f8e7d..."
  }
}
```

