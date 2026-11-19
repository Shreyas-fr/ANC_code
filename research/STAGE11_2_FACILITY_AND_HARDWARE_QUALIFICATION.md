# SIH 26052 — Stage 11.2: Facility & Hardware Bench Qualification Plan

**Document Version:** 1.0.0 · **Date:** 2026-11-13  
**Status:** Laboratory Qualification & Hardware Acceptance Protocol · **Pre-Collection Phase**  
**Execution Boundary:** Standard operating procedure for physical acoustic and hardware qualification. **Review estimates regarding Raspberry Pi compute and latency are formally classified as desk findings pending bench reproduction.**

---

## 1. Overview & Qualification Objectives

Before any human participant enters the recording booth, and before any candidate model is cleared for physical edge deployment, two mandatory bench qualification gates must be executed:
1. **Acoustic Facility & Signal Chain Qualification:** Verifying that booth reverberation ($RT_{60} \le 120\text{ ms}$), background noise floor ($< 25\text{ dBA}$), ADC noise ($<-128.5\text{ dBu}$), and inter-channel synchronization ($< 5\ \mu\text{s}$) meet laboratory standards.
2. **Raspberry Pi 5 Physical Bench Reproduction:** Transitioning theoretical compute projections and earlier legacy estimates into empirically measured, reproducible numbers on physical **Raspberry Pi 5** hardware (Broadcom BCM2712, Quad-core Cortex-A76 @ 2.4 GHz). Pi 5 capability cannot be inferred from Pi 4 benchmark figures; physical measurements are required.

---

## 2. Acoustic Booth Certification Protocol

```
+---------------------------------------------------------------------------------------------------------+
|                                    ACOUSTIC BOOTH MEASUREMENT HARNESS                                   |
+--------------------------+---------------------+-------------------------------+------------------------+
| 1. Excitation Source     | 2. Enclosure Field  | 3. Class 1 Transducer         | 4. Analysis Engine     |
+--------------------------+---------------------+-------------------------------+------------------------+
| Calibrated omni source   | Sealed booth volume | B&K Type 4189 / GRAS 46AE     | Schroeder integration  |
| Logarithmic sine sweep   | HVAC running        | Free-field on-axis            | RT60 per octave band   |
| 20 Hz to 20 kHz (10 s)   | 0.1 m/s airflow     | 1/3-octave real-time analyzer | NC-20 curve compliance |
+--------------------------+---------------------+-------------------------------+------------------------+
```

### 2.1 Reverberation Time ($RT_{60}$) Test Procedure (ISO 3382-2)
1. Position a calibrated omnidirectional dodecahedron loudspeaker at the center of the recording booth.
2. Position the Class 1 measurement microphone at the designated participant head position ($1.2\text{ m}$ elevation).
3. Play a 10-second logarithmic sine sweep ($20\text{ Hz}$ to $20\text{ kHz}$) at $85\text{ dBA SPL}$.
4. Deconvolve the recorded response to obtain the Room Impulse Response (RIR), $h[t]$.
5. Compute the energy decay curve via Schroeder backward integration:
   $$E(t) = \int_{t}^{\infty} h^2(\tau) d\tau$$
6. Derive $T_{20}$ (time for energy to decay from $-5\text{ dB}$ to $-25\text{ dB}$) and extrapolate $RT_{60} = 3 \times T_{20}$.
7. Repeat across three spatial microphone positions; average the results.
8. **Acceptance Threshold:** $RT_{60}(f) \le 120\text{ ms}$ across all octave bands: $125\text{ Hz}, 250\text{ Hz}, 500\text{ Hz}, 1\text{ kHz}, 2\text{ kHz}, 4\text{ kHz}, 8\text{ kHz}$.

### 2.2 Ambient Noise Floor & Noise Criterion (NC) Test Procedure
1. Mount the Class 1 sound level meter at the participant ear position.
2. Ensure booth door is sealed and HVAC ventilation is operating at normal recording speed.
3. Record continuous equivalent sound level ($L_{\text{Aeq}}$) and 1/3-octave band spectrum for $120\text{ seconds}$.
4. **Acceptance Thresholds:**
   - Broadband: $L_{\text{Aeq}} \le 25.0\text{ dBA SPL}$; $L_{\text{Ceq}} \le 30.0\text{ dBC SPL}$.
   - 1/3-Octave Bands: Measured sound pressure levels must fall strictly below the **NC-20** noise criterion curve from $63\text{ Hz}$ to $8\text{ kHz}$.

---

## 3. Audio Interface & ADC Bench Qualification Protocol

### 3.1 Preamplifier Equivalent Input Noise (EIN) Verification
1. Terminate ADC Channel 1, 2, and 3 inputs with precision $150\ \Omega$ metal-film resistors shielded inside metal XLR shells.
2. Set preamplifier gain to maximum operational setting ($+60\text{ dB}$).
3. Record $30\text{ seconds}$ of digital noise in 24-bit / 48 kHz linear PCM.
4. Calculate A-weighted digital RMS noise level ($L_{\text{RMS}}$ in dBFS).
5. Compute Equivalent Input Noise:
   $$\text{EIN} = L_{\text{RMS}} - \text{Gain} + V_{\text{clip\_dBu}} \quad [\text{dBu}]$$
6. **Acceptance Threshold:** $\text{EIN} \le -128.5\text{ dBu}$ (A-weighted, $150\ \Omega$ source).

### 3.2 Inter-Channel Phase Synchronization & Clock Jitter Verification
1. Feed a high-precision $5,000.0\text{ Hz}$ sine wave from an ultra-low-distortion analog signal generator into a passive 1-to-3 resistive splitter.
2. Connect splitter outputs to Channel 1 (Boom Mic input), Channel 2 (Earcup input), and Channel 3 (Measurement input) using matched-length ($1.0\text{ m}$) shielded cables.
3. Record a $10\text{ second}$ synchronous multi-channel file at 48.0 kHz / 24-bit.
4. Perform discrete cross-correlation between channels:
   $$R_{12}[k] = \sum_{n} x_1[n] x_2[n+k]$$
5. Calculate phase delay $\Delta \tau = \arg\max_k R_{12}[k] / f_s$.
6. **Acceptance Threshold:** Inter-channel time delay $\Delta \tau < 5.0\ \mu\text{s}$ (less than $0.25$ samples at 48 kHz, confirming true synchronous crystal clocking).

---

## 4. Raspberry Pi 5 Physical Bench Hardware Reproduction Protocol

> **CRITICAL METHODOLOGICAL MANDATE:**  
> The target deployment hardware for SIH 26052 is **Raspberry Pi 5** (Broadcom BCM2712, Quad-core Cortex-A76 @ 2.4 GHz). All prior estimates derived from legacy Raspberry Pi 4 benchmarks or desktop profiling are **Review Findings** that cannot be simply inferred or scaled. Physical bench measurements on actual Raspberry Pi 5 hardware are mandatory before declaring deployment qualified.

```
+---------------------------------------------------------------------------------------------------------+
|                                  PHYSICAL PI 5 BENCH TEST HARNESS                                       |
+--------------------------+---------------------+-------------------------------+------------------------+
| 1. Physical Hardware     | 2. Audio Subsystem  | 3. Hardware Instrumentation   | 4. Empirical Metrics   |
+--------------------------+---------------------+-------------------------------+------------------------+
| Raspberry Pi 5 Model B   | ALSA direct driver  | Dual-channel oscilloscope     | Physical click latency |
| Cortex-A76 @ 2.4 GHz     | 48 kHz / 24-bit PCM | High-res monotonic timestamps | Frame compute time RTF |
| 4GB/8GB LPDDR4X, Fan     | USB Audio Class 2   | Thermal zone sysfs logger     | Peak RSS & CPU %       |
| OS: 64-bit Bookworm      | Buffer: 256 samples | vcgencmd throttled register   | XRUNs over 60 minutes  |
+--------------------------+---------------------+-------------------------------+------------------------+
```

### 4.1 Physical Test Bench Setup & Configuration
1. **Target Hardware:** Raspberry Pi 5 Model B (Broadcom BCM2712, 4 cores @ $2.4\text{ GHz}$, $4\text{GB}$ or $8\text{GB}$ LPDDR4X).
2. **Cooling State:** Official Raspberry Pi Active Cooler installed; ambient temperature maintained at $25.0^\circ\text{C} \pm 1.0^\circ\text{C}$.
3. **Power Supply:** Official Raspberry Pi $27\text{W}$ USB-C PD power supply ($5.1\text{V} / 5.0\text{A}$) to prevent under-voltage throttling.
4. **OS Configuration:** Raspberry Pi OS 64-bit Lite (Bookworm, 16KB kernel page size); CPU governor set to `performance` across all 4 cores (`cpufreq-set -g performance`).

### 4.2 Benchmark Execution Procedure
1. **Step 1: RTF & Execution Time Benchmark:**
   - Execute native streaming engine on 100 standardized speech mixture clips:
     ```bash
     python3 scripts/benchmark_pi_native.py \
         --model models/dfn3_step500_tract.onnx \
         --wavs test_corpus/ \
         --output runs/pi_bench_repro/dfn3_bench.csv
     ```
   - Measure per-frame compute duration using `clock_gettime(CLOCK_MONOTONIC_RAW)`.
   - Calculate empirical RTF distribution: Mean, Median, 95th percentile, and 99th percentile.
2. **Step 2: Physical Acoustic Loopback Latency Measurement (Dual-Channel DSO SOP):**
   - Mount boAt Rockerz 512 headset on an IEC 60318-4 ear simulator coupler with artificial mouth transducer positioned at $30\text{ mm}$ (on-axis) to the boom microphone.
   - Emit a bandlimited acoustic Dirac impulse ($0.5\text{ ms}$ pulse width, $100\text{ Hz} - 16\text{ kHz}$) repeated at $1.0\text{ s}$ intervals.
   - Connect Channel 1 of the Digital Storage Oscilloscope (DSO) via a $10\times$ passive probe directly across the artificial mouth input terminals (reference electrical trigger $t_0$).
   - Connect Channel 2 to a calibrated $1/4$-inch measurement microphone capsule sealed inside the ear simulator coupler adjacent to the headset earcup driver (acoustic return $t_1$).
   - Measure complete round-trip physical delay:
     $$\tau_{\text{roundtrip}} = \tau_{\text{air\_in}} + \tau_{\text{mic}} + \tau_{\text{ADC}} + \tau_{\text{ALSA\_in}} + \tau_{\text{hop}} + \tau_{\text{infer}} + \tau_{\text{ALSA\_out}} + \tau_{\text{DAC}} + \tau_{\text{amp\_spk}} + \tau_{\text{air\_out}}$$
   - Record 100 consecutive trials; compute Mean, $p90$, $p95$, $p99$, and Max.
   - Requirement: $p95(\tau_{\text{roundtrip}}) \le 35.0\text{ ms}$, $\text{Max} < 40.0\text{ ms}$.
3. **Step 3: 60-Minute Continuous Soak Test:**
   - Run streaming loopback continuously for 3,600 seconds under simulated high-noise input.
   - Log core temperature (`/sys/class/thermal/thermal_zone0/temp`), CPU usage, memory RSS, and throttling register (`vcgencmd get_throttled`) at $1\text{ Hz}$.

> [!WARNING]
> **Provisional Planning Targets (Not Measured Benchmark Results):**  
> All Raspberry Pi 5 performance figures listed in Table 4.1 are **provisional acceptance targets** derived from architectural modeling of Cortex-A76 clock speed ($2.4\text{ GHz}$) and IPC uplifts over Cortex-A72 ($1.5\text{ GHz}$). They do **not** represent measured benchmark results on Raspberry Pi 5. No physical Pi 5 benchmark has been conducted in this preparatory phase. They must remain labeled as **provisional acceptance criteria** until justified and empirically validated on physical hardware during Gate 05 qualification.

### Table 4.1: Empirical Bench Reproduction Target Register (Raspberry Pi 5)

| Performance Parameter | Legacy Pi 4 Finding (Historical) | Provisional Pi 5 Acceptance Criteria (Proposed Target, Not Measured) | Hardware Reproduction Status |
|:---|:---:|:---:|:---:|
| **DFN3 Step-500 Mean RTF** | $0.43 - 0.45$ (Pi 4) | $\le 0.30$ on Cortex-A76 @ 2.4 GHz (Provisional Target) | **PENDING PHYSICAL BENCH** |
| **DFN3 Step-500 $p99$ RTF** | $< 0.60$ (Pi 4) | $\le 0.40$ on Cortex-A76 @ 2.4 GHz (Provisional Target) | **PENDING PHYSICAL BENCH** |
| **GTCRN DNS3 Mean RTF** | $0.18 - 0.25$ (Pi 4) | $\le 0.15$ on Cortex-A76 @ 2.4 GHz (Provisional Target) | **PENDING PHYSICAL BENCH** |
| **GTCRN DNS3 $p99$ RTF** | $< 0.35$ (Pi 4) | $\le 0.25$ on Cortex-A76 @ 2.4 GHz (Provisional Target) | **PENDING PHYSICAL BENCH** |
| **Round-Trip Physical Latency** | $\approx 28.0\text{ ms}$ | $\le 35.0\text{ ms}$ acoustic-to-acoustic ($p95$) (Provisional Target) | **PENDING PHYSICAL BENCH** |
| **ALSA Buffer Underruns (XRUNs)**| $0$ | Exactly $0$ over $60\text{ minutes}$ | **PENDING PHYSICAL BENCH** |
| **Core Temperature Plateau** | $< 70.0^\circ\text{C}$ | $\le 75.0^\circ\text{C}$ with Active Cooler | **PENDING PHYSICAL BENCH** |
| **Hardware Throttling State** | `0x0` | Strictly `0x0` (zero under-voltage/capping) | **PENDING PHYSICAL BENCH** |
| **Peak Resident Memory (RSS)** | $< 180\text{ MB}$ | $\le 300.0\text{ MB}$ | **PENDING PHYSICAL BENCH** |

---

## 5. Physical Acceptance Sign-Off Certificate

```
LABORATORY FACILITY & HARDWARE ACCEPTANCE CERTIFICATE
Facility: ___________________________________  Date: ________________________
Chief Acoustic Engineer: ____________________  Lead Embedded Engineer: ______

[ ] 1. ACOUSTIC ENCLOSURE VERIFICATION:
    - Measured RT60 across 125 Hz - 8 kHz: ______ ms (<= 120 ms)         [ PASS / FAIL ]
    - Measured ambient noise floor:         ______ dBA (<= 25.0 dBA)      [ PASS / FAIL ]
    - Measured NC curve compliance:        NC-______  (<= NC-20)         [ PASS / FAIL ]

[ ] 2. ANALOG-TO-DIGITAL CONVERTER VERIFICATION:
    - Measured EIN (150 Ohm, A-weighted):   ______ dBu (<= -128.5 dBu)   [ PASS / FAIL ]
    - Measured inter-channel phase delay:  ______ us  (< 5.0 us)         [ PASS / FAIL ]
    - Calibrator 94.0 dB SPL digital level: ______ dBFS (-20.0 +- 0.2 dB) [ PASS / FAIL ]

[ ] 3. RASPBERRY PI 5 PHYSICAL BENCH REPRODUCTION:
    - DFN3 Step-500 Measured Mean RTF:     ______     (<= 0.30 on Pi 5)  [ PASS / FAIL ]
    - DFN3 Step-500 Measured p99 RTF:      ______     (<= 0.40 on Pi 5)  [ PASS / FAIL ]
    - Measured Acoustic Round-Trip Latency: ______ ms  (<= 35.0 ms)       [ PASS / FAIL ]
    - 60-Minute Soak XRUN Count:           ______     (Exactly 0)        [ PASS / FAIL ]
    - Maximum Steady-State Core Temp:      ______ deg (<= 75.0 deg C)    [ PASS / FAIL ]
    - Hardware Throttled Register:         ______     (Must be 0x0)      [ PASS / FAIL ]

QUALIFICATION VERDICT: [ ] FULL PASS — CERTIFIED FOR STAGE 11.3
                       [ ] HOLD — CORRECTIVE ACTION REQUIRED
Acoustic Lead Signature: __________________________ Date: ___________________
Embedded Lead Signature: __________________________ Date: ___________________
```

