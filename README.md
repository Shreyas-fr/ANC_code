# SIH26052 — AI Noise Suppression on Raspberry Pi 5

**DRDO Problem Statement SIH26052:** Real-Time AI-Based Active Noise Suppression for Tactical Communications on Embedded Hardware (Raspberry Pi 5).

---

## 1. System Architecture

The system operates as an autonomous edge-to-operator tactical communication pipeline:

```
[ Tactical Environment ]
          │ (Acoustic Noise: Gunfire, Artillery, Engine Rumble)
          ▼
 [ Bluetooth / ALSA Mic ]
          │ (16 kHz / 48 kHz PCM)
          ▼
[ Raspberry Pi 5 (Edge) ] ── (Inference: DeepFilterNet3 48 kHz, 1 Thread)
   ├── PipeWire Capture
   ├── Block Backend (500ms block + 300ms context)
   └── UDP Network Streamer
          │
          │ UDP (Port 5005: Enhanced Audio | Port 5006: Telemetry | Port 5007: Raw)
          ▼
 [ Operator Dashboard ] (PC Frontend)
   ├── Jitter Ring Buffer (In-memory, zero disk writes)
   ├── Real-Time Rolling Waveforms & 0-8 kHz FFT Spectrum
   ├── Telemetry Monitor (Latency, Thermals, Packet Loss)
   └── Soundcard Playback (Automatic fail-safe mute on disconnect)
```

- **Authoritative Edge Node (Raspberry Pi 5):** Executes all audio capture, resampling, and DeepFilterNet3 neural inference natively on the Cortex-A76 CPU.
- **Operator Frontend (PC):** Lightweight PySide6 visualization dashboard and low-latency audio renderer. The PC performs **zero AI computation**.

---

## 2. Canonical Model: DeepFilterNet3 (48 kHz)

- **Architecture:** DeepFilterNet3 (Complex ERB Filterbank + Deep Complex Filtering)
- **Parameters:** 2,167,969 (Exact verified count)
- **Sample Rate:** 48,000 Hz (48 kHz Native)
- **Status:** **CANONICAL FROZEN CANDIDATE**
- **SHA256 Checksum:** `522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe`
- **Specification:** See [`MODEL.md`](MODEL.md) for verification procedures (`shasum -a 256 final_model/model.hk`).
- *Note:* Earlier experimental architectures (Polar-D / Stateful PolarLSTM and Complex CRN) have been retired to `experiments/` due to acoustic reverberation artifacts and high compute overhead. See [`docs/experiments.md`](docs/experiments.md).

---

## 3. Quick Start

### Step 1: Launch Operator Frontend (PC / Mac)
```bash
# Activate frontend environment
source frontend/venv/bin/activate  # or use system python with PySide6
python frontend/main.py
```
*Dependencies:* `PySide6`, `pyqtgraph`, `sounddevice`, `numpy`.

### Step 2: Launch Autonomous Edge Sender (Raspberry Pi 5)
```bash
# Set destination PC IP address
export SIH_PC_IP="<OPERATOR_PC_IP>"

# Launch autonomous live streaming with DFN3 enhancement
python edge/pi_sender_v2.py \
    --mode dfn3 \
    --target-ip "$SIH_PC_IP" \
    --name-match Rockerz
```

### Operational Modes
| Mode Flag | Behavior |
| :--- | :--- |
| `--mode dfn3` | Full neural noise suppression via DeepFilterNet3 (Default) |
| `--mode raw` | Direct microphone passthrough for latency calibration |
| `--mode resampled` | Polyphase FIR resampler without neural filtering |

---

## 4. Hardware Stress Test Validation (Raspberry Pi 5)

During continuous 6-minute in-memory stress testing on Raspberry Pi 5 hardware (running headless on a single Cortex-A76 core with standard 5V/3A supply), the canonical DFN3 pipeline demonstrated rock-solid real-time stability:

| Metric | Measured Value | Operational Assessment |
| :--- | :---: | :--- |
| **Median Compute Time** | `213.2 ms` | Comfortably runs at ~0.43x real-time per 500 ms block |
| **Max Compute Time** | `424.6 ms` | Safely below the 500 ms block deadline |
| **Peak Operating Temp** | `60.9 °C` | Passive cooling; well below the 82.0 °C throttle threshold |
| **Supply Voltage (EXT5V)** | `4.78V - 5.03V` | Stable voltage; **0x0 throttling events** registered |
| **Network Transmission** | `18,737 frames` | **0 packet drops**; maximum jitter < 0.02 ms |
| **Memory Footprint** | `~1.3 GB free` | Zero memory leaks; all runtime buffers reside in `/dev/shm` |

---

## 5. Latency Characteristics

- **Deployed End-to-End Latency:** **~790 ms** (576 ms measured chain delay + 213 ms median compute time). In the deployed 500 ms-block configuration, throughput is prioritized over low latency to ensure zero deadline misses on embedded hardware.
- **Model Algorithmic Latency:** **~16 ms** (STFT hop length: 256 samples at 16 kHz or 10 ms at 48 kHz). This latency is achievable only when operating in sample-by-sample streaming mode without block windowing.

---

## 6. Repository Layout

```
.
├── src/                # Core neural network models & DSP modules
├── eval/               # Validation & benchmark evaluation harnesses
├── scripts/            # Training, audio mixing, and audit scripts
├── deploy/             # Embedded benchmarks and NLMS postfilter
├── edge/               # Raspberry Pi 5 streaming, capture, & hardware code
├── frontend/           # PySide6 operator GUI & unit tests
├── configs/            # Runtime & model configuration files
├── results/            # Benchmark metrics, CSVs, and spectrograms
├── docs/               # System documentation & visual diagrams
│   ├── diagnostics/    # Hardware and forensic diagnostic logs
│   ├── system_diagrams.md
│   └── experiments.md  # Non-canonical model documentation
├── experiments/        # Historical Polar-D, CRN, and ablation runs
├── assets/             # Media, audio recordings, and plots
├── final_model/        # Frozen canonical model descriptor & SHA256
├── MODEL.md            # Authoritative model specification
├── PROJECT_INDEX.md    # Component status & benchmark index
├── REPORT.md           # Formal deliverables & claims report
└── CLEANUP_LOG.md      # Sanitization & migration audit log
```

---

## 7. Verification & Tests

### Frontend Unit Tests
Verify the complete packet parsing, sequence tracking, and circular jitter buffer state machine:
```bash
pytest frontend/tests/
# Expected: 16 passed
```

### Model Integrity Check
Verify the frozen model checkpoint checksum against the authoritative hash:
```bash
shasum -a 256 final_model/model.hk
# Expected: 522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe
```
