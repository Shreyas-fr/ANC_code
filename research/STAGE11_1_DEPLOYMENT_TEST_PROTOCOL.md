# SIH 26052 — Stage 11.1: Edge Deployment Acceptance Test Protocol

**Document Version:** 1.1.0 · **Date:** 2026-11-13  
**Status:** Embedded Testing & Acceptance Protocol · **Pre-Execution Phase**  
**Execution Boundary:** Testing procedures for Raspberry Pi 5 deployment. The deployed production checkpoint (`bc1fc9b76958...`) on `~/anc_live` remains frozen and untouched during all test authoring.

---

## 1. Deployment Objectives & Candidate Model Classification

The final deployment objective of SIH 26052 is to deliver real-time, low-latency noise suppression on an embedded **Raspberry Pi 5** edge processor coupled to the boAt Rockerz 512 ANC hardware headset.

> **CRITICAL ARCHITECTURAL DIRECTIVE:**  
> The target deployment hardware is **Raspberry Pi 5 (Broadcom BCM2712, Quad-core ARM Cortex-A76 @ 2.4 GHz)**. All earlier references to Raspberry Pi 4 are superseded. Furthermore, Pi 5 capability cannot be inferred from Pi 4 benchmark figures; empirical bench measurements on actual Pi 5 hardware are mandatory before declaring deployment qualified.

Based on the architectural audit in `STAGE11_1_READINESS_REVIEW.md`, models are formally categorized into two distinct evaluation tracks to resolve the compute and streaming incompatibilities of complex offline architectures.

### Table 1.1: Candidate Model Testing Classification Matrix

| Model Candidate | Architectural Profile | Track Classification | Edge Playout Test Eligibility | Rationale & Constraints |
|:---|:---|:---:|:---:|:---|
| **DFN3 Step-500** | $2.14\text{M}$ params; $48\text{ kHz}$; Causal ERB filterbank; $10\text{ ms}$ hop | **Track B (Edge Streaming)** | **MANDATORY** | Production baseline; proven native C++/Rust streaming runtime; RTF $0.43–0.45$. |
| **GTCRN DNS3** | $48.2\text{K}$ params; $16\text{ kHz}$; Causal group GRU; $16\text{ ms}$ hop | **Track B (Edge Streaming)** | **ELIGIBLE** | Ultra-lightweight; causal STFT framing; estimated RTF $0.18–0.25$; streaming compatible. |
| **FullSubNet Epoch 58** | $5.64\text{M}$ params; $16\text{ kHz}$; 2-frame lookahead; Sub-band LSTM | **Track A (Offline Only)** | **EXCLUDED** | Non-causal `offline_laplace_norm`; algorithmic latency $>48\text{ ms}$; CPU RTF $> 1.8$ on ARM. |
| **Primary Ensemble (15/70/15)** | Multi-rate composite (DFN3 + FullSubNet + GTCRN) | **Track A (Offline Only)** | **EXCLUDED** | Compute barrier: 3 concurrent neural backbones exceed Cortex-A76 CPU/threading limits; memory and buffer collapse. |
| **Secondary Ensemble (20/60/20)**| Multi-rate composite (DFN3 + FullSubNet + GTCRN) | **Track A (Offline Only)** | **EXCLUDED** | Compute barrier: Exceeds real-time threshold; serves strictly as offline distillation teacher. |

---

## 2. Edge Hardware Platform & Operating Environment

All deployment acceptance testing must be executed on a standardized Raspberry Pi 5 test bench configured as follows:

- **Compute Hardware:** Raspberry Pi 5 Model B (4GB or 8GB LPDDR4X).
  - SoC: Broadcom BCM2712, Quad-core ARM Cortex-A76 (ARM v8.2-A) 64-bit SoC @ $2.4\text{ GHz}$ ($512\text{KB}$ per-core L2 caches, $2\text{MB}$ shared L3 cache).
  - I/O Southbridge: Raspberry Pi RP1 custom I/O controller (managing PCIe 2.0, dual USB 3.0, Gigabit Ethernet, and GPIO).
  - System Memory: $4\text{GB}$ or $8\text{GB}$ LPDDR4X-4267 SDRAM (providing $>17\text{ GB/s}$ memory bandwidth).
  - Storage: High-endurance Industrial A2 microSD card or M.2 NVMe SSD via PCIe Hat+.
  - Cooling: Official Raspberry Pi Active Cooler (aluminum heatsink with temperature-controlled variable-speed PWM blower fan).
  - Power Supply: Official Raspberry Pi $27\text{W}$ USB-C PD power supply ($5.1\text{V} / 5.0\text{A}$) providing full $1.6\text{A}$ downstream USB current.
- **Operating System & Kernel:**
  - OS: Raspberry Pi OS (64-bit), Debian GNU/Linux 12 (Bookworm) minimal headless.
  - Kernel: Linux 6.6.x-v8+ with 16KB kernel page size and CPU governor set to `performance` across all 4 Cortex-A76 cores.
- **Audio Interface & Peripheral:**
  - Standardized USB Audio Class 2.0 DAC/ADC interface with hardware ALSA direct drivers.
  - Hardware Headset: boAt Rockerz 512 ANC connected via wired $3.5\text{ mm}$ TRRS auxiliary loopback or USB interface.

---

## 3. Latency Definitions & Rigorous Measurement Protocol

> [!IMPORTANT]
> **Fundamental Distinction: Physical Round-Trip Latency vs. Algorithmic Latency Alone**  
> * **Algorithmic Latency ($\tau_{\text{algo}}$):** The mathematical lookahead, window framing, and synthesis overlap-add delay introduced strictly by the DSP/STFT framing ($10.0 - 20.0\text{ ms}$ for DFN3 depending on window centering and synthesis buffering, $16.0\text{ ms}$ for GTCRN). It assumes instantaneous I/O, infinite processor speed, zero operating system buffers, and zero acoustic propagation.
> * **Physical Round-Trip Latency ($\tau_{\text{roundtrip}}$):** The complete physical elapsed time from the instant an acoustic wavefront impinges on the boom microphone to the instant the processed acoustic waveform is radiated by the earcup speaker into the ear cavity. It encompasses all physical, electrical, operating system, buffer, inference, and conversion stages.

```
+-----------------------------------------------------------------------------------------------------------------------+
|                                    DETAILED PHYSICAL ROUND-TRIP LATENCY STACK (<= 35.0 ms BUDGET)                     |
+---+----------------------------+-----------------------+--------------------------------------------------------------+
| # | Latency Component          | Typical Duration      | Physical Mechanism & Interface Specification                 |
+---+----------------------------+-----------------------+--------------------------------------------------------------+
| 1 | Inbound Acoustic Flight    | tau_air_in  = 0.09 ms | Propagation from mouth reference point to mic (3 cm / 343 m/s)|
| 2 | Mic Transducer Delay       | tau_mic     = 0.05 ms | Electret capsule diaphragm displacement & FET pre-amp transit|
| 3 | ADC Delta-Sigma Filter     | tau_ADC     = 0.65 ms | Hardware ADC 64x oversampling decimation filter group delay  |
| 4 | ALSA Capture Buffer        | tau_ALSA_in = 2.67 ms | 128 samples @ 48 kHz (1 period) + USB 2.0 isochronous packet |
| 5 | Algorithmic Frame Hop      | tau_hop     = 10.0 ms | DFN3 480 samples @ 48 kHz analysis frame hop (total algo delay 10-20 ms)|
| 6 | Neural Inference Exec      | tau_infer   = 2.80 ms | Forward neural pass on Cortex-A76 quad-core (provisional est)|
| 7 | ALSA Playback Buffer       | tau_ALSA_out= 2.67 ms | 128 samples @ 48 kHz playback ring buffer + USB transmission |
| 8 | DAC Interpolation Filter   | tau_DAC     = 0.65 ms | Hardware DAC 8x interpolation filter & sigma-delta modulator |
| 9 | Headphone Driver Transit   | tau_amp_spk = 0.35 ms | Analog headphone amp slew & voice coil excursion delay       |
| 10| Outbound Acoustic Flight   | tau_air_out = 0.06 ms | Propagation across internal earcup cavity (2 cm / 343 m/s)   |
+---+----------------------------+-----------------------+--------------------------------------------------------------+
|   | NOMINAL COMPUTED SUM:      | tau_roundtrip = 20.09 ms                                                             |
|   | UPPER SAFETY CEILING:      | tau_roundtrip <= 35.0 ms (allows 14.9 ms OS thread jitter / buffer variation)|
+--------------------------------+--------------------------------------------------------------------------------------+
```

### 3.1 Formal Latency Definitions & Mathematical Formulation
1. **Algorithmic Latency ($\tau_{\text{algo}}$):**
   - The theoretical minimum delay imposed by the signal processing mathematics:
     $$\tau_{\text{algo}} = \frac{N_{\text{hop}} + N_{\text{lookahead}}}{f_s}$$
   - For DFN3: $N_{\text{hop}} = 480\text{ samples}$ ($10.0\text{ ms}$ at $48\text{ kHz}$), $N_{\text{lookahead}} = 0$. $\tau_{\text{algo}} = 10.0\text{ ms}$.
   - For GTCRN: $N_{\text{hop}} = 256\text{ samples}$ ($16.0\text{ ms}$ at $16\text{ kHz}$), $N_{\text{lookahead}} = 0$. $\tau_{\text{algo}} = 16.0\text{ ms}$.
   - For FullSubNet: $N_{\text{hop}} = 128\text{ samples}$ ($8.0\text{ ms}$), $N_{\text{lookahead}} = 2\text{ frames}$ ($16.0\text{ ms}$), synthesis windowing $\approx 24.0\text{ ms}$. $\tau_{\text{algo}} > 48.0\text{ ms}$ (violates edge budget).

2. **Physical Round-Trip Latency ($\tau_{\text{roundtrip}}$):**
   - The total measured latency encompassing all ten hardware, software, and acoustic stages:
     $$\tau_{\text{roundtrip}} = \tau_{\text{air\_in}} + \tau_{\text{mic}} + \tau_{\text{ADC}} + \tau_{\text{ALSA\_in}} + \tau_{\text{hop}} + \tau_{\text{infer}} + \tau_{\text{ALSA\_out}} + \tau_{\text{DAC}} + \tau_{\text{amp\_spk}} + \tau_{\text{air\_out}}$$
   - **Provisional Acceptance Criterion:** $\tau_{\text{roundtrip}} \le 35.0\text{ ms}$ ($p95$).

### 3.2 Dual-Channel Oscilloscope Latency Measurement Standard Operating Procedure (SOP)
To prevent reliance on software internal timestamps, latency must be measured objectively via physical instrumentation:

1. **Acoustic Test Environment & Fixture:**
   - Headset mounted on a standardized acoustic test fixture (IEC 60318-4 ear simulator / artificial ear coupler) inside the certified acoustic booth ($RT_{60} \le 120\text{ ms}$).
   - Calibrated artificial mouth transducer placed at standard ITU-T P.51 position ($30\text{ mm}$ distance, on-axis) to the Rockerz 512 boom microphone.
2. **Instrumentation Signal Chain:**
   - **Signal Generator:** High-precision arbitrary function generator producing a bandlimited acoustic Dirac impulse ($0.5\text{ ms}$ pulse width, $100\text{ Hz} - 16\text{ kHz}$, repetition period $1.0\text{ s}$).
   - **Oscilloscope Channel 1 (Reference Trigger $t_0$):** High-impedance passive probe ($10\times$, $<10\text{ pF}$) connected directly across the electrical input terminals of the artificial mouth transducer.
   - **Oscilloscope Channel 2 (Acoustic Playout $t_1$):** Calibrated $1/4$-inch measurement microphone (free-field flat to $40\text{ kHz}$) sealed inside the ear simulator coupler adjacent to the headset earcup driver.
3. **Triggering & Data Acquisition:**
   - Digital Storage Oscilloscope (DSO) configured for edge triggering on Channel 1 leading edge at 50% voltage threshold ($t_0 \equiv 0.000\text{ ms}$).
   - Sampling rate set to $\ge 1.0\text{ MSa/s}$ across both channels with a $100\text{ ms}$ acquisition window.
4. **Latency Extraction & Statistical Criteria:**
   - For each impulse $k$ ($1 \le k \le 100$), compute:
     - (a) Threshold Onset Time: Time of first arrival on Channel 2 reaching 50% of peak pressure amplitude ($\Delta t_k = t_{1,k} - t_{0,k}$).
     - (b) Cross-Correlation Delay: Time of cross-correlation maximum between Channel 1 and Channel 2 signals ($\arg\max_\tau R_{12}(\tau)$).
   - Compute aggregate distribution: Mean, $p90$, $p95$, $p99$, and Max.
   - **Pass Criteria:**
     - $p95(\tau_{\text{roundtrip}}) \le 35.0\text{ ms}$.
     - $\text{Max}(\tau_{\text{roundtrip}}) < 40.0\text{ ms}$.
     - Discrepancy between onset threshold and cross-correlation delay $< 1.0\text{ ms}$.

---

## 4. Compute, Thermal & Resource Acceptance Criteria (Provisional Planning Targets)

> [!WARNING]
> **Provisional Planning Targets (Not Measured Benchmark Results):**
> The compute, memory, and thermal thresholds listed in this section are **proposed acceptance criteria / provisional planning targets** derived from architectural modeling of Cortex-A76 clock speed ($2.4\text{ GHz}$) and IPC uplifts over Cortex-A72 ($1.5\text{ GHz}$). They do **not** represent measured physical benchmark results on Raspberry Pi 5. No physical Pi 5 benchmark has been performed in this preparatory phase. They must remain labeled as **provisional acceptance criteria** until justified and empirically validated on the physical device during Gate 05 qualification.

### 4.1 Real-Time Factor (RTF) — Provisional Acceptance Targets
- **Definition:** The ratio of CPU inference compute time ($T_{\text{compute}}$) to the physical duration of the audio block ($T_{\text{block}}$):
  $$\text{RTF} = \frac{T_{\text{compute}}}{T_{\text{block}}}$$
- **Instrumentation:** Instrument the streaming inference loop with high-resolution monotonic timestamps (`clock_gettime(CLOCK_MONOTONIC)`):
  ```c
  uint64_t t_start = get_monotonic_ns();
  model_process_frame(in_frame, out_frame);
  uint64_t t_end = get_monotonic_ns();
  double rtf = (double)(t_end - t_start) / (double)FRAME_DURATION_NS;
  ```
- **Provisional Acceptance Thresholds for Raspberry Pi 5:**
  - **Proposed Mean RTF:** $\le 0.30$ (provisional target; unverified on physical Pi 5).
  - **Proposed 99th Percentile RTF ($p99$):** $\le 0.40$ (provisional target; unverified on physical Pi 5).
  - **Proposed Maximum Block RTF:** $< 0.60$ (guarantees $> 40\%$ headroom against OS thread preemption).

### 4.2 System Resource & Thermal Envelope — Provisional Acceptance Targets
During continuous execution, background daemons must log system metrics every $1.0\text{ second}$:
- **Resident Set Size (RSS):** Monitored via `/proc/<pid>/statm`.
  - **Provisional Threshold:** Peak RSS $\le 300.0\text{ MB}$.
- **Core Thermal Profile:** Monitored via `/sys/class/thermal/thermal_zone0/temp`.
  - **Provisional Threshold:** Maximum steady-state core temperature $\le 75.0^\circ\text{C}$ in a $25^\circ\text{C}$ ambient environment (with official Active Cooler).
- **Hardware Throttling State:** Monitored via `vcgencmd get_throttled`.
  - **Provisional Threshold:** Return value must remain strictly `throttled=0x0` throughout testing (bit 0 = under-voltage, bit 1 = arm frequency capped, bit 2 = currently throttled, bit 3 = soft temperature limit).

---

## 5. Continuous 60-Minute Soak Test Procedure

To verify production stability, the candidate model must run uninterrupted under continuous real-time streaming load for 60 minutes.

### 5.1 Test Execution Script
```bash
#!/bin/bash
# SIH 26052 - 60-Minute Edge Deployment Soak Test Runner
MODEL_NAME="dfn3_step500"
LOG_DIR="runs/deployment_tests/${MODEL_NAME}_soak_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"

echo "=== STARTING 60-MINUTE SOAK TEST: ${MODEL_NAME} ==="
echo "Logging metrics to ${LOG_DIR}"

# 1. Start continuous audio streaming daemon in background
./bin/anc_stream_runner \
    --model "checkpoints/${MODEL_NAME}.onnx" \
    --device "hw:1,0" \
    --samplerate 48000 \
    --framesize 480 \
    --log "${LOG_DIR}/stream_stats.csv" &
STREAM_PID=$!

# 2. Monitor loop for 3600 seconds (60 minutes)
for i in $(seq 1 3600); do
    TEMP=$(cat /sys/class/thermal/thermal_zone0/temp | awk '{print $1/1000}')
    THROTTLED=$(vcgencmd get_throttled)
    RSS_KB=$(ps -p $STREAM_PID -o rss= | tr -d ' ')
    CPU_PCT=$(ps -p $STREAM_PID -o %cpu= | tr -d ' ')
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ),${i},${TEMP},${THROTTLED},${RSS_KB},${CPU_PCT}" >> "${LOG_DIR}/system_health.csv"
    
    # Abort if process crashed
    if ! kill -0 $STREAM_PID 2>/dev/null; then
        echo "CRITICAL FAILURE: Streaming runner crashed at second ${i}!"
        exit 1
    fi
    sleep 1
done

# 3. Terminate stream gracefully
kill -SIGINT $STREAM_PID
wait $STREAM_PID

echo "=== SOAK TEST COMPLETED. ANALYZING LOGS ==="
python3 scripts/analyze_soak_log.py --dir "$LOG_DIR"
```

### 5.2 Pass/Fail Soak Test Verification Criteria
1. **Buffer Underruns (XRUNs):** Exactly **0** ALSA buffer underruns recorded in ALSA proc stats (`/proc/asound/card*/pcm*p/sub*/status`).
2. **Process Integrity:** Process uptime exactly $\ge 3,600\text{ seconds}$ with zero segmentation faults, memory leaks, or unhandled exceptions.
3. **Memory Stability:** RSS drift over 60 minutes $< 5.0\text{ MB}$ (confirming zero heap memory leaks in C++/Rust runtime).
4. **Thermal Stability:** Temperature curve asymptotes below $70.0^\circ\text{C}$; throttling register remains `0x0`.

---

## 6. Hardware Audio Loopback & Rockerz 512 Acceptance Test

```
+---------------------------------------------------------------------------------------------------------+
|                                    ACOUSTIC LOOPBACK TEST HARNESS                                       |
+--------------------------+---------------------+-------------------------------+------------------------+
| 1. Artificial Mouth /    | 2. Rockerz 512      | 3. Raspberry Pi 5 Edge Core   | 4. Measurement Mic     |
| Calibrated Loudspeaker   | Headset Mic Input   | Real-time DFN3 / GTCRN stream | Artificial Ear Coupler |
+--------------------------+---------------------+-------------------------------+------------------------+
| Plays standardized test  | Captures mixture    | Latency < 35 ms               | Captures acoustic      |
| battery (speech + noise) | Analog -> ADC       | RTF < 0.30; RSS < 300 MB      | playout inside earcup  |
+--------------------------+---------------------+-------------------------------+------------------------+
```

### 6.1 Test Setup
1. Mount the boAt Rockerz 512 ANC headset onto an ITU-T P.57 compliant artificial ear/head simulator (e.g., GRAS 45CB or KEMAR acoustic manikin).
2. Connect the headset boom microphone to the Raspberry Pi 5 USB audio interface input.
3. Connect the Raspberry Pi 5 audio output to the headset auxiliary input.
4. Position an external loudspeaker at $1.0\text{ meter}$ emitting calibrated operational noise ($80\text{ dBA SPL}$).
5. Position an artificial mouth speaker emitting calibrated speech sentences ($65\text{ dBA SPL}$).

### 6.2 Acoustic Loopback Acceptance Checklist
- [ ] **Acoustic Feedback Stability:** Ensure no regenerative acoustic feedback loop or whistling occurs between the earcup speaker and boom microphone under maximum operational volume.
- [ ] **Total Harmonic Distortion (Acoustic Output):** Measured acoustic THD $< 2.0\%$ across $200\text{ Hz} - 4\text{ kHz}$ at $85\text{ dBA SPL}$ output.
- [ ] **Dynamic Range Preservation:** Active noise cancellation does not suppress natural speech plosives below intelligibility thresholds; output STOI $\ge 0.85$.
- [ ] **Zero Artifact Audible Clicks:** Real-time playout audited by listening panel for buffer boundary discontinuity pops or robotic musical noise artifacts.

