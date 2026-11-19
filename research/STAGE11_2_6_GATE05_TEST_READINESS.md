# SIH 26052 — Stage 11.2.6: Gate 05 Physical Test Readiness Specification

**Document Version:** 1.0.0 · **Date:** 2026-11-13  
**Status:** Protocol Frozen · **Gate 05 Remains LOCKED (0/5 Cleared)**  
**Target Hardware:** Raspberry Pi 5 Model B (Broadcom BCM2712, Quad-core Cortex-A76 @ 2.4 GHz)  
**Safety Scope:** Test harness design, mathematical definitions, execution procedures, and data schemas. **Zero physical Pi 5 testing has occurred or is authorized in this turn.**

---

## 1. Executive Summary & Objective

This specification establishes the complete, standardized testing protocol for **Gate 05 (Physical Raspberry Pi 5 Reproduction)** prior to physical execution. It defines:
1. Exact hardware, operating system, cooling, and electrical bench requirements.
2. Standardized test signal generation and digital loopback impulse testing for measuring algorithmic latency ($\tau_{\text{algo}}$).
3. Standard operating procedure (SOP) for dual-channel oscilloscope physical round-trip latency ($\tau_{\text{roundtrip}}$) measurement.
4. Continuous 60-minute real-time streaming soak test procedure with $1\text{ Hz}$ thermal, memory, and throttling telemetry.
5. Machine-readable data schemas and formal evidence requirements for the Gate 05 sign-off artifact (`evidence/PI5_PHYSICAL_BENCH_REPORT.pdf`).

---

## 2. Hardware Bench Configuration & Environmental Baseline

Physical qualification must be conducted on genuine Raspberry Pi 5 hardware complying with the frozen specification:

```
+---------------------------------------------------------------------------------------------------------------+
|                               RASPBERRY PI 5 BENCH HARDWARE SPECIFICATION                                     |
+--------------------------+----------------------------------------------------+-------------------------------+
| Subsystem                | Required Specification                             | Compliance Verification Method|
+--------------------------+----------------------------------------------------+-------------------------------+
| System-on-Chip (SoC)     | Broadcom BCM2712 (16nm TSMC process)               | /proc/device-tree/model       |
| CPU Cores                | Quad-core ARM Cortex-A76 @ 2.4 GHz (ARMv8.2-A)     | lscpu; max_freq = 2400000     |
| CPU Caches               | 512 KB per-core L2; 2 MB shared L3 cache           | lscpu; sysfs cache topology   |
| System Memory            | 4 GB or 8 GB LPDDR4X-4267 SDRAM (>17 GB/s bw)      | free -m; /proc/meminfo        |
| Cooling System           | Official Raspberry Pi Active Cooler (PWM fan)      | Hardware inspection           |
| Power Delivery           | Official 27W USB-C PD Supply (5.1V / 5.0A DC)      | vcgencmd get_throttled = 0x0  |
| Operating System         | Raspberry Pi OS Lite 64-bit (Debian 12 Bookworm)   | /etc/os-release; uname -r     |
| Kernel Page Size         | 16 KB kernel page size                             | getconf PAGESIZE (returns 16k)|
| CPU Governor             | performance across all 4 cores                     | cpufreq-info; sysfs governor  |
| Process Priority         | Real-time FIFO priority: chrt -f 95                | chrt -p [pid]                 |
| Audio Interface          | Class-compliant USB Audio 2.0 ADC/DAC (RP1 USB 3.0)| lsusb; arecord -l; aplay -l   |
| Headset Transducer       | boAt Rockerz 512 (Boom mic + circumaural earcups)  | Physical equipment audit      |
| Acoustic Test Fixture    | IEC 60318-4 ear simulator + ITU-T P.51 mouth       | Laboratory calibration record |
| Digital Storage Scope    | Dual-channel DSO (>= 100 MHz, >= 1 GSa/s, 10x probe)| Metrology calibration cert    |
+--------------------------+----------------------------------------------------+-------------------------------+
```

---

## 3. Test Battery 1: Model Export & Native Compilation Readiness

Before physical bench benchmarking begins, the deployment artifacts must be compiled and verified bit-exact:

### 3.1 Model Checkpoint Export
1. Verify SHA-256 of candidate checkpoint:
   * Target: `antigravity/runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt`
   * Required SHA-256: `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27`
2. Run parameterized export script:
   ```bash
   python3 scripts/export_step500_to_tract.py \
       --checkpoint antigravity/runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt \
       --output-tar models/dfn3_step500_tract.tar.gz
   ```
3. Record SHA-256 of resulting `models/dfn3_step500_tract.tar.gz`.

### 3.2 Native Rust Build on ARM64 Target
1. On the physical Raspberry Pi 5 running 64-bit OS:
   ```bash
   cd antigravity/runs/sih26052_rpi_deployment_audit/runs/dfn3_pi_optimization/DeepFilterNet
   RUSTFLAGS="-C target-cpu=cortex-a76" cargo build --release --bin enhance_wav --features tract,timings
   ```
2. Verify executable location: `target/release/enhance_wav`.
3. Record binary SHA-256 and confirm dynamic linking (`ldd target/release/enhance_wav`).

---

## 4. Test Battery 2: Digital Impulse Algorithmic Latency Test

This test measures the discrete sample delay introduced strictly by the mathematical STFT analysis-synthesis filterbank and neural forward pass, isolated from physical electroacoustics.

### 4.1 Signal Specification
* **Signal Type A (Dirac Click):** Sinc pulse windowed to $0.5\text{ ms}$ ($24\text{ samples}$ @ $48\text{ kHz}$), bandlimited to $[100\text{ Hz}, 16,000\text{ Hz}]$, Hann-tapered.
* **Signal Type B (Kronecker Delta):** Single discrete sample of amplitude $1.0$ at index $n_0$, surrounded by silence.
* **Sampling Rate:** Native $48,000\text{ Hz}$ mono PCM float32.
* **Pre-Impulse Silence:** $500\text{ ms}$ ($24,000\text{ samples}$).
* **Post-Impulse Silence:** $500\text{ ms}$ ($24,000\text{ samples}$).
* **Intra-Frame Alignment Offsets:** To evaluate phase-alignment sensitivity within a $480$-sample frame, test offsets $n_0 \in \{0, 120, 240, 360, 479\}$.

### 4.2 Test Procedure
1. Execute test script across 100 trials:
   ```bash
   python3 scripts/measure_digital_latency.py \
       --signal-type dirac_click \
       --trials 100 \
       --sample-rate 48000 \
       --hop-size 480 \
       --warmup-frames 50 \
       --output-csv runs/pi5_qualification/digital_latency_raw.csv \
       --output-json runs/pi5_qualification/digital_latency_summary.json
   ```
2. Warm up state: Stream 50 silent/dithered frames ($500\text{ ms}$) prior to measurement to initialize recursive normalizers.
3. Compute normalized cross-correlation between reference $x[n]$ and processed $y[n]$:
   $$R_{xy}[k] = \frac{\sum_n x[n] y[n + k]}{\sqrt{\sum_n x[n]^2 \sum_n y[n]^2}}, \quad k^* = \arg\max_k R_{xy}[k]$$
4. Compute discrete sample delay: $k^*$ samples.
5. Compute algorithmic latency: $\tau_{\text{algo}} = (k^* / 48000) \times 1000\text{ ms}$.
6. Confirm whether $\tau_{\text{algo}} = 10.00\text{ ms}$ ($480\text{ samples}$) or $20.00\text{ ms}$ ($960\text{ samples}$).

---

## 5. Test Battery 3: Physical Electroacoustic Round-Trip Latency SOP

This standard operating procedure objectively measures the total acoustic-to-acoustic latency using laboratory instrumentation, completely bypassing operating system software timestamp bias.

```
+---------------------------------------------------------------------------------------------------------------+
|                                    ACOUSTIC LOOPBACK MEASUREMENT RIG                                          |
|                                                                                                               |
|  [DSO Channel 1 Probe] <----+ (Electrical Trigger t0)                                                         |
|                             |                                                                                 |
|  [Dirac Click Generator] ---> [Artificial Mouth]                                                              |
|                                    | (Acoustic Wavefront, d = 3.0 cm)                                         |
|                                    v                                                                          |
|                           [Rockerz 512 Boom Mic]                                                              |
|                                    | (Analog Audio In)                                                        |
|                                    v                                                                          |
|                         [USB ADC / ALSA MMAP]                                                                 |
|                                    | (128-sample period @ 48k)                                                |
|                                    v                                                                          |
|                     [Raspberry Pi 5 Native DFN3 Stream]                                                       |
|                                    | (480-sample hop, Tract inference)                                        |
|                                    v                                                                          |
|                         [USB DAC / ALSA MMAP]                                                                 |
|                                    | (128-sample period @ 48k)                                                |
|                                    v                                                                          |
|                           [Headphone Driver]                                                                  |
|                                    | (Acoustic Playout, d = 2.0 cm)                                           |
|                                    v                                                                          |
|                         [IEC 60318-4 Coupler]                                                                 |
|                                    |                                                                          |
|  [DSO Channel 2 Probe] <----+ [Measurement Mic] (Acoustic Wavefront Arrival t1)                               |
+---------------------------------------------------------------------------------------------------------------+
```

### 5.1 Measurement SOP
1. Mount the boAt Rockerz 512 headset on the IEC 60318-4 ear simulator. Position the ITU-T P.51 artificial mouth at $30\text{ mm}$ on-axis to the boom microphone capsule.
2. Connect Channel 1 of the DSO ($10\times$ passive probe) directly across the mouth transducer input terminals. Set Channel 1 trigger to rising edge at $50\%$ amplitude ($t_0 \equiv 0.000\text{ ms}$).
3. Connect Channel 2 to the output of the calibrated $1/4$-inch measurement microphone pre-amplifier inside the ear simulator coupler.
4. Emit 100 bandlimited Dirac impulses ($0.5\text{ ms}$ pulse width, $100\text{ Hz} - 16\text{ kHz}$) repeated at $1.0\text{ s}$ intervals.
5. For each impulse $k \in \{1, \dots, 100\}$, DSO records waveform and computes:
   * $\Delta t_k = t_{1,k} - t_{0,k}$ (Leading edge onset arrival).
   * Cross-correlation delay peak between Channel 1 and Channel 2 digitized waveforms.
6. Record all 100 delay values in `runs/pi5_qualification/physical_latency_raw.csv`.
7. **Acceptance Criteria:**
   * $p95(\tau_{\text{roundtrip}}) \le 35.0\text{ ms}$
   * $\text{Max}(\tau_{\text{roundtrip}}) < 40.0\text{ ms}$
   * Discrepancy between onset and correlation peak $< 1.0\text{ ms}$ across all trials.

---

## 6. Test Battery 4: 60-Minute Continuous Real-Time Streaming Soak Test

The soak test validates long-term computational stability, thermal equilibrium, and zero audio buffer dropouts under sustained operational load.

### 6.1 Execution SOP
1. Verify system environment prerequisites:
   * Ambient temperature: $25.0^\circ\text{C} \pm 1.0^\circ\text{C}$.
   * CPU governor: `performance` on all cores.
   * Power supply: 27W USB-C PD connected; `vcgencmd get_throttled` returns `0x0`.
2. Prepare standardized high-noise test corpus (concatenated IoBT gunfire, engine, and environmental noise at $-5\text{ dB}$ to $+10\text{ dB}$ SNR).
3. Start background $1\text{ Hz}$ telemetry logging:
   ```bash
   python3 scripts/run_pi5_qualification_bench.py \
       --duration-seconds 3600 \
       --output-json runs/pi5_qualification/PI5_PHYSICAL_BENCH_REPORT.json
   ```
4. Start native streaming engine:
   ```bash
   chrt -f 95 taskset -c 2,3 target/release/enhance_wav \
       --model models/dfn3_step500_tract.tar.gz \
       --input /dev/stdin --output /dev/stdout
   ```
5. Monitor for exactly 3,600 consecutive seconds (60.0 minutes).

### 6.2 Acceptance Thresholds Register

```
+---------------------------------------------------------------------------------------------------------------+
|                            60-MINUTE CONTINUOUS SOAK ACCEPTANCE THRESHOLDS                                    |
+--------------------------+-----------------------+------------------------------------+-----------------------+
| Performance Parameter    | Proposed Target       | Classification                     | Verification Source   |
+--------------------------+-----------------------+------------------------------------+-----------------------+
| DFN3 Step-500 Mean RTF   | Mean RTF <= 0.30      | Provisional Planning Target        | Frame latency CSV log |
| DFN3 Step-500 p99 RTF    | p99 RTF <= 0.40       | Provisional Planning Target        | Frame latency CSV log |
| DFN3 Maximum Frame RTF   | Max RTF < 0.60        | Provisional Planning Target        | Frame latency CSV log |
| ALSA Buffer Underruns    | Exactly 0 XRUNs       | Formally Approved Requirement      | /proc/asound/.../xrun |
| Hardware Throttling      | Strictly 0x0          | Formally Approved Requirement      | vcgencmd get_throttled|
| Peak Memory Usage (RSS)  | RSS <= 300.0 MB       | Formally Approved Requirement      | /proc/[pid]/statm     |
| Thermal Plateau          | Core temp <= 75.0 C   | Provisional Planning Target        | thermal_zone0/temp    |
| Audio Waveform Integrity | Zero NaN / Inf / clip | Formally Approved Requirement      | Output WAV inspection |
+--------------------------+-----------------------+------------------------------------+-----------------------+
```

---

## 7. Machine-Readable Evidence Schema & Sign-Off Requirements

To satisfy Gate 05, the embedded lead must produce:
1. `runs/pi5_qualification/digital_latency_raw.csv` (100 digital impulse trials).
2. `runs/pi5_qualification/physical_latency_raw.csv` (100 oscilloscope measurements).
3. `runs/pi5_qualification/soak_telemetry_1hz.csv` (3,600 telemetry points: timestamp, core temp, RSS, throttling hex, XRUN count).
4. `runs/pi5_qualification/PI5_PHYSICAL_BENCH_REPORT.json` (Structured machine-readable summary).
5. `evidence/PI5_PHYSICAL_BENCH_REPORT.pdf` (Formal signed report containing oscilloscope scope-capture screenshots, calibration certificates, and authorized digital signature by `Embedded_Lead`).

### Programmatic Gatekeeper Verification Rule:
The automated gatekeeper script (`scripts/verify_stage11_qualification_gates.py`) will automatically verify:
* File exists: `evidence/PI5_PHYSICAL_BENCH_REPORT.pdf`.
* File is non-empty ($>10,240\text{ bytes}$).
* SHA-256 matches tracker register.
* Signed by authorized role (`Embedded_Lead`).
* Status updated to `PASSED` in `research/STAGE11_2_1_QUALIFICATION_TRACKER.csv`.

Until that evidence is independently produced and verified, Gate 05 remains **LOCKED**.

