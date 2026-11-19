# SIH 26052 — Stage 11.1: Hardware Requirements & Equipment Specification

**Document Version:** 1.0.0 · **Date:** 2026-11-13  
**Status:** Hardware Specification & Bill of Materials · **Pre-Procurement Phase**  
**Execution Boundary:** Technical benchmarking and qualification standards. **Zero hardware procurement or physical purchasing authorized** prior to institutional approval.

---

## 1. Overview & Architectural Bill of Materials (BOM)

To capture pristine, uncolored ground truth audio with zero phase distortion, inter-channel clock drift, or electrical contamination, the recording signal chain must meet strict laboratory measurement standards (IEC 61672-1 / ANSI S1.4).

```
+---------------------------------------------------------------------------------------------------------+
|                                    STAGE 11.1 HARDWARE SYSTEM ARCHITECTURE                              |
+--------------------------+---------------------+-------------------------------+------------------------+
| Acoustic Environment     | Transducer Tier     | Preamplifier & ADC Tier       | Calibration Reference  |
+--------------------------+---------------------+-------------------------------+------------------------+
| Double-walled booth      | Ch 1: Boom Headset  | 8-ch Synchronous Interface    | Class 1 Calibrator     |
| RT60 < 120 ms (all oct)  | Ch 2: Earcup Ref    | EIN < -128 dBu (A-weighted)   | 94.0 dB SPL +- 0.2 dB  |
| Noise floor < 25 dBA SPL | Ch 3: Class 1 Free  | Phase drift < 10 microseconds | 1,000 Hz sine ref      |
| NC-20 compliant          | 48 kHz / 24-bit PCM | Hardware locked preamps       | Daily pre/post checks  |
+--------------------------+---------------------+-------------------------------+------------------------+
```

### Table 1.1: Complete Hardware Specification & Bill of Materials

| Component ID | Description / Role | Reference Models (or Equivalent) | Critical Specification Threshold |
|:---|:---|:---|:---|
| **ENV-01** | Acoustic Isolation Booth | WhisperRoom MDL 102126E / StudioBricks Pro / IAC Acoustics | $RT_{60} \le 120\text{ ms}$ ($125\text{ Hz} - 8\text{ kHz}$); $L_{\text{Aeq}} \le 25\text{ dBA SPL}$; NC-20 |
| **MIC-01** | Primary Vocal Close-Talking Mic | DPA 4466 CORE / Shure Beta 54 / Countryman H6 Headset | Pre-polarized condenser; Cardioid; Max SPL $\ge 137\text{ dB}$; THD $< 1\%$ at $130\text{ dB SPL}$ |
| **MIC-02** | Secondary Headset Reference Mic | DPA 4060 CORE / Countryman B3 Omnidirectional | Omnidirectional miniature condenser; Sensitivity matched; Max SPL $\ge 134\text{ dB}$ |
| **MIC-03** | Laboratory Measurement Reference | Brüel & Kjær Type 4189 / Earthworks M30 / GRAS 46AE | Class 1 1/2-inch free-field condenser; Flat response $\pm 1.0\text{ dB}$ ($20\text{ Hz} - 20\text{ kHz}$) |
| **ADC-01** | Multichannel Synchronous Audio ADC | RME Fireface UCX II / Sound Devices MixPre-10 II | 24-bit / 48.0 kHz linear PCM; EIN $<-128.5\text{ dBu}$; THD+N $< 0.0008\%$; Inter-channel skew $< 5\ \mu\text{s}$ |
| **CAL-01** | Acoustic Sound Calibrator | Brüel & Kjær Type 4231 / Larson Davis CAL200 | Class 1 (IEC 60942); Output $94.00\text{ dB SPL} \pm 0.20\text{ dB}$ at $1,000.0\text{ Hz} \pm 1\%$ |
| **SLM-01** | Sound Level Meter / Analyzer | Larson Davis SoundTrack LxT / NTi Audio XL2 | Class 1 (IEC 61672-1); 1/1 & 1/3-octave real-time filter bands ($20\text{ Hz} - 20\text{ kHz}$) |
| **RIG-01** | Non-Reflective Positioning Rig | Custom 3D-printed bracket + Delrin positioning caliper | Fixed $45^\circ$ angle, $2.5\text{ cm} \pm 0.2\text{ cm}$ boom spacing gauge; non-resonant |
| **HED-01** | Hardware Target Headset | boAt Rockerz 512 ANC (Production Evaluation Unit) | Passive acoustic isolation verification + real-time loopback validation |

---

## 2. Transducer Technical Requirements

### 2.1 Primary Close-Talking Vocal Microphone (MIC-01)
- **Acoustic Principle:** Pressure gradient pre-polarized condenser.
- **Directional Pattern:** Cardioid.
  - Front-to-back rejection: $\ge 15.0\text{ dB}$ at $1.0\text{ kHz}$ to reject vocal tract reflections off clothing and chest.
- **Frequency Response:**
  - $40\text{ Hz} to 18,000\text{ Hz} \pm 2.0\text{ dB}$.
  - Gentle proximity roll-off ($< -3.0\text{ dB}$ below $100\text{ Hz}$) to counter close-talking bass boost.
- **Dynamic Range & Acoustic Overload:**
  - Maximum Sound Pressure Level: $\ge 137.0\text{ dB SPL}$ peak for $< 1.0\%$ THD.
  - Equivalent Self-Noise: $\le 26.0\text{ dBA SPL}$.
  - Dynamic Range: $\ge 111.0\text{ dB}$.
- **Mounting & Rigging:**
  - Integral flexible gooseneck boom coupled to a bilateral headband.
  - Removable micro-cellular acoustic foam pop-filter (density $30\text{ kg/m}^3$) to suppress vocal puff aerodynamics.

### 2.2 Secondary Earcup Reference Microphone (MIC-02)
- **Acoustic Principle:** Pressure-operated pre-polarized omnidirectional condenser.
- **Mounting Position:** Integrated flush onto the exterior baffle of the right ear shell ($10.0\text{ cm} \pm 0.5\text{ cm}$ lateral displacement from the primary boom capsule).
- **Acoustic Rationale & Cross-Talk Constraints:**
  - Designed to capture ambient environmental acoustic pressure incident on the listener's head.
  - *Measured Transfer Function:* Mouth-to-earcup speech leakage attenuation is $-15.0\text{ dB} \pm 3.0\text{ dB}$ across $500\text{ Hz} - 4\text{ kHz}$.
  - Must remain strictly independent of the single-channel evaluation audio feed.

### 2.3 Laboratory Free-Field Measurement Microphone (MIC-03)
- **Standard:** Class 1 conformant to IEC 61672-1 and ANSI S1.4.
- **Capsule Diameter:** 1/2-inch (12.7 mm) or 1/4-inch (6.35 mm).
- **Polar Pattern:** True omnidirectional (free-field equalized).
- **Frequency Range:** $10\text{ Hz} to 30,000\text{ Hz} \pm 1.0\text{ dB}$.
- **Calibration Coupling:** Standard 1/2-inch mechanical coupler collar for direct insertion into CAL-01 acoustic calibrator.

---

## 3. Preamplifier & Audio Interface Requirements (ADC-01)

Multi-channel synchronization and low electrical noise are critical to prevent phase jitter and spurious background hiss:

1. **Synchronous Multichannel Sampling:**
   - All input channels must be converted by discrete ADCs driven by a **single shared master crystal oscillator**.
   - Use of separate USB microphones or multi-device aggregate audio drivers is **strictly forbidden** (prevents inter-channel clock drift of $10–50\text{ ppm}$ which destroys phase-aligned adaptive filtering).
   - Maximum allowable inter-channel phase skew: $< 5.0\ \mu\text{s}$ at $10\text{ kHz}$ ($< 18^\circ$ phase difference).
2. **Equivalent Input Noise (EIN):**
   - $\le -128.5\text{ dBu}$ at maximum gain ($150\ \Omega$ source impedance, A-weighted, $20\text{ Hz} - 20\text{ kHz}$).
   - Ensures that electrical preamplifier hiss remains $> 20\text{ dB}$ below the acoustic booth ambient floor.
3. **Total Harmonic Distortion + Noise (THD+N):**
   - $\le 0.0008\%$ ($-102\text{ dB}$) at $1.0\text{ kHz}$, $-1.0\text{ dBFS}$ digital output.
4. **Preamplifier Gain Control & Repeatability:**
   - Digitally controlled analog stepped preamplifiers with exact $0.5\text{ dB}$ or $1.0\text{ dB}$ gain increments, OR precision analog potentiometers secured with locking set-screws.
   - Preamplifier gain settings logged numerically in session manifests.

---

## 4. Acoustic Environment & Calibration Rig

### 4.1 Acoustic Isolation Enclosure (ENV-01)
- **External Sound Transmission Loss:**
  - $R' \ge 35\text{ dB}$ at $125\text{ Hz}$.
  - $R' \ge 48\text{ dB}$ at $500\text{ Hz}$.
  - $R' \ge 55\text{ dB}$ at $1\text{ kHz}$ to $8\text{ kHz}$.
- **Internal Absorption & Reverberation Control:**
  - Perforated steel or fabric interior panels over high-density acoustic mineral wool ($60–100\text{ kg/m}^3$).
  - Corner bass traps installed to ensure $RT_{60} \le 120\text{ ms}$ at $125\text{ Hz}$.
- **Vibration Isolation:**
  - Floating floor system with elastomeric or pneumatic isolators providing mechanical decoupling from building floor vibrations ($< 10\text{ Hz}$ resonance).

### 4.2 Acoustic Calibrator (CAL-01)
- **Standard:** IEC 60942:2017 Class 1.
- **Reference Output:** $94.00\text{ dB SPL} \pm 0.20\text{ dB}$ (re $20\ \mu\text{Pa}$) at $1,000.0\text{ Hz} \pm 1.0\%$.
- **Total Harmonic Distortion:** $\le 1.0\%$.
- **Calibration Traceability:** Valid, unexpired factory calibration certificate traceable to national metrology institutes (NIST, NPL, or PTB).

---

## 5. Hardware Qualification & Acceptance Checklist

Before any participant enters the facility, the recording technician and principal investigator must execute and sign this hardware verification checklist:

```
PRE-RECORDING HARDWARE QUALIFICATION CHECKLIST
Facility: ______________________  Date: ______________  Operator: __________________

[ ] 1. ACOUSTIC BOOTH AMBIENT NOISE:
    - SLM mounted at participant head position (MIC-03).
    - 60-second Leq recorded with HVAC on.
    - Measured LAeq: _______ dBA  (Threshold: <= 25.0 dBA)                  [ PASS / FAIL ]
    - Measured LCeq: _______ dBC  (Threshold: <= 30.0 dBC)                  [ PASS / FAIL ]

[ ] 2. REVERBERATION TIME (RT60):
    - Schroeder backwards integration across 125 Hz - 8 kHz octave bands.
    - RT60 @ 125 Hz: _____ ms  (Threshold: <= 120 ms)                       [ PASS / FAIL ]
    - RT60 @ 500 Hz: _____ ms  (Threshold: <= 120 ms)                       [ PASS / FAIL ]
    - RT60 @ 1 kHz:  _____ ms  (Threshold: <= 120 ms)                       [ PASS / FAIL ]
    - RT60 @ 4 kHz:  _____ ms  (Threshold: <= 120 ms)                       [ PASS / FAIL ]

[ ] 3. ACOUSTIC CALIBRATION & GAIN STAGING:
    - CAL-01 coupled to MIC-03. Output: 94.0 dB SPL @ 1 kHz.
    - Preamp gain adjusted to exact -20.0 dBFS RMS digital level.
    - CAL-01 coupled to MIC-01. Output: 94.0 dB SPL @ 1 kHz.
    - Preamp gain adjusted to exact -20.0 dBFS RMS digital level.
    - Physical gain locks / tamper seals applied.                           [ PASS / FAIL ]

[ ] 4. INTER-CHANNEL TIME SYNCHRONIZATION:
    - 5 kHz tone played into Ch 1 and Ch 2 simultaneously via splitter.
    - Cross-correlation analysis performed on raw recorded buffers.
    - Measured inter-channel phase skew: _____ microseconds (Threshold: < 5 us) [ PASS / FAIL ]

[ ] 5. SYSTEM NOISE & ELECTRICAL GROUNDING:
    - Inputs terminated with 150 Ohm shielded dummy load.
    - Preamp gain set to operational position.
    - Measured digital noise floor: _______ dBFS (Threshold: <= -85.0 dBFS)  [ PASS / FAIL ]
    - Zero ground loops, zero 50/60 Hz hum harmonics detected on FFT.       [ PASS / FAIL ]

[ ] 6. BOOM RIGGING INTEGRITY:
    - Headset boom arm tested for mechanical creep under 50 g lateral load.
    - Caliper confirms 2.5 cm distance and 45 deg angle repeatability.     [ PASS / FAIL ]

QUALIFICATION VERDICT: [ ] APPROVED FOR RECORDING    [ ] REJECTED (REPAIR REQUIRED)
Technician Signature: _______________________  Date: ________________________
PI Signature:        _______________________  Date: ________________________
```

