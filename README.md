# DRDO SIH 26052: High-Performance AI-Powered Active Noise Cancellation & Tactical Speech Enhancement

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Engine: Rust 2021](https://img.shields.io/badge/Engine-Rust%202021-orange.svg)](https://www.rust-lang.org/)
[![GUI: Eframe/Egui](https://img.shields.io/badge/GUI-Eframe%2Fegui%20(60FPS)-green.svg)](https://github.com/emilk/egui)
[![Latency Gate: PASSED](https://img.shields.io/badge/Latency%20Gate%20(<=35ms)-PASSED%20(16.01ms)-brightgreen.svg)](#real-time-latency--rtf-performance)
[![Platform: Raspberry Pi 5](https://img.shields.io/badge/Platform-Raspberry%20Pi%205%20(ARM%20Cortex--A76)-red.svg)](#embedded-deployment-on-raspberry-pi-5)

Real-time, ultra-low-latency dual-microphone tactical speech enhancement system designed for **Smart India Hackathon (SIH 26052)**. Engineered specifically for high-noise defense, combat vehicle, rotorcraft, and tactical radio environments.

The entire system—both the **embedded real-time edge processing engine** and the **live desktop mission control operator dashboard**—has been completely re-architected in **pure, zero-allocation, lock-free Rust**, eliminating Python GIL pauses, heap fragmentation, and non-deterministic OS jitter.

---

## System Architecture

```
                 TACTICAL DUAL-MICROPHONE ARRAY (30mm Spacing)
                       [ Mic 1 ]            [ Mic 2 ]
                           │                    │
                           ▼                    ▼
        ┌────────────────────────────────────────────────────────┐
        │       CAUSAL DUAL-MIC MVDR SPATIAL BEAMFORMER         │
        │  • Recursive Spatial Covariance Tracking (α = 0.98)   │
        │  • Regularized Analytic 2x2 Inversion (ε = 1e-5)      │
        │  • Directional Point-Source Null Steering             │
        └──────────────────────────┬─────────────────────────────┘
                                   │ Beamformed Mono Stream
                                   ▼
        ┌────────────────────────────────────────────────────────┐
        │       STREAMING ASYMMETRIC STFT / ISTFT ENGINE        │
        │  • Asymmetric Low-Latency Analysis Window (8ms look)  │
        │  • 512-pt FFT / 128-sample hop (8ms frame cadence)    │
        │  • Zero Heap Allocations in Streaming Hot Path        │
        └──────────────────────────┬─────────────────────────────┘
                                   │ Complex Spectrum
                                   ▼
        ┌────────────────────────────────────────────────────────┐
        │       PURE-RUST TRACT ONNX NEURAL FILTER RUNTIME      │
        │  • Order-5 Deep Complex Filter (DF) Spectral Shaping  │
        │  • 32-Band Equivalent Rectangular Bandwidth (ERB)     │
        │  • Track 1 Frozen 15/70/15 Neural Ensemble           │
        │  • Built-in Analytic Wiener Fallback Engine           │
        └──────────────────────────┬─────────────────────────────┘
                                   │ Enhanced PCM Samples
                                   ▼
        ┌────────────────────────────────────────────────────────┐
        │       TRULY CAUSAL AGC & SOFT-KNEE PEAK LIMITER       │
        │  • Running-RMS Envelope Tracker (τ_att=20ms, τ_rel=200ms)
        │  • Soft-Knee Tanh Limiter (prevents digital clipping) │
        └──────────────────────────┬─────────────────────────────┘
                                   │
                                   ▼
        ┌────────────────────────────────────────────────────────┐
        │       LOCK-FREE SPSC JITTER SCHEDULER & UDP WIRE      │
        │  • Smooth Cosine Crossfade Raw Audio Fallback         │
        │  • Cycle-Accurate ALSA/DAC Playout Synchronization    │
        │  • Non-Blocking UDP Telemetry & Audio Dispatch        │
        └───────┬──────────────────────┬──────────────────┬──────┘
                │ UDP 5005             │ UDP 5006         │ UDP 5007
                ▼ (Enhanced)           ▼ (Telemetry JSON) ▼ (Raw Reference)
 ┌────────────────────────────────────────────────────────────────────────┐
 │        NATIVE GPU-ACCELERATED DESKTOP OPERATOR DASHBOARD               │
 │  • Built with eframe / egui / egui_plot at 60 FPS                      │
 │  • Real-time CPAL soundcard audio streaming (zero disk I/O guarantee) │
 │  • Synchronized 3.0s dual waveforms (Raw in Amber, Enhanced in Cyan)   │
 │  • Live 0–8 kHz FFT power spectral density analyzer                    │
 │  • Hardware diagnostics, sequence tracking & fail-safe status machine  │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## Workspace Structure

The repository is structured as a unified Cargo workspace:

```
ANC/
├── Cargo.toml               # Workspace manifest (fat LTO, codegen-units=1, panic=abort)
├── anc-rust/                # Core Real-Time Edge Engine (Pi 5 / ARM Cortex-A76 & x86)
│   ├── Cargo.toml
│   └── src/
│       ├── dsp/             # MVDR, STFT/ISTFT, Asymmetric Windows, Polyphase FIR, AGC
│       ├── model/           # Tract ONNX Engine, Order-5 Complex Filter, ERB, Ensemble
│       ├── streaming/       # Lock-free SPSC ring buffers, Playout scheduler, Pipeline
│       ├── network/         # Bit-exact UDP wire protocol (ports 5005, 5006, 5007)
│       ├── metrics/         # SI-SDR, SNR, active speech levels, PMIC thermal reader
│       └── bin/
│           ├── edge.rs      # Standalone real-time daemon for Raspberry Pi 5 (`anc-edge`)
│           ├── bench.rs     # Micro-benchmark for latency, RTF, and gate check (`anc-bench`)
│           └── process.rs   # Batch audio evaluation and objective metrics CLI (`anc-process`)
├── frontend-rust/           # Operator Mission Control Desktop GUI
│   ├── Cargo.toml
│   └── src/
│       ├── audio/           # CPAL soundcard driver callback & anti-pop JitterBuffer
│       ├── network/         # UDP receiver threads with sequence tracking & timeout monitor
│       ├── dsp/             # 512-pt FFT power spectrum analyzer (0–8 kHz)
│       ├── ui/              # Dark tactical UI theme, waveforms, spectrum, telemetry cards
│       ├── app.rs           # Master eframe::App controller running at 60 FPS
│       └── main.rs          # CLI entry point (`anc-frontend`)
├── MASTER_SIH_COMPLIANCE.md # Authoritative Stage 11.2.58B-X audit and closure memo
└── models/                  # Checkpoint manifests and neural model artifacts
```

---

## Real-Time Latency & RTF Performance

Evaluated using `anc-bench` on 500 streaming iteration hops:

| Operational Configuration | STFT Framing Lookahead | Inference Compute (P99) | Hardware I/O Buffer | Total Roundtrip Delay | Qualification Gate ($\le 35.0\text{ ms}$) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Config A: Symmetric 512/256 Hann** | $32.00\text{ ms}$ | $0.007\text{ ms}$ | $8.00\text{ ms}$ | **$40.01\text{ ms}$** | ❌ **FAIL** ($> 35.0\text{ ms}$) |
| **Config B: Low-Latency 256/128** | $16.00\text{ ms}$ | $0.003\text{ ms}$ | $8.00\text{ ms}$ | **$24.00\text{ ms}$** | ✅ **PASS** (**$+11.0\text{ ms}$ margin**) |
| **Config C: Asymmetric 512/128** | **$8.00\text{ ms}$** | $0.009\text{ ms}$ | $8.00\text{ ms}$ | **$16.01\text{ ms}$** | ✅ **PASS** (**$+18.99\text{ ms}$ margin**) |

### Compute Performance & Headroom
- **Inference Compute Latency:** Median **`0.003 ms` (3 $\mu$s)**, Max `0.068 ms` (68 $\mu$s).
- **Real-Time Factor (RTF):** **`0.0003`** (**`3,482x` faster than real-time**).
- **Projected Raspberry Pi 5 (Cortex-A76):** $< 0.15\text{ ms}$ per frame ($< 1\%$ single-core CPU utilization).

---

## Objective Speech Enhancement Metrics

Evaluated on independent multi-channel tactical audio under severe noise conditions:

- **SI-SDR Gain:** **$+8.27\text{ dB}$** average improvement.
- **Explicit SNR Gain:** **$+7.28\text{ to }+9.23\text{ dB}$** average improvement.
- **Speech Intelligibility (STOI):** **$0.86\text{ to }0.88$**.
- **Perceptual Quality (PESQ-WB):** **$2.23\text{ to }2.44$**.
- **Directional Point-Source Nulling:** Dual-mic MVDR spatial nulling delivers a **$+2.38\text{ dB}$ Local SNR advantage** over single-channel neural networks.

---

## Build & Installation

### Prerequisites
- **Rust Toolchain:** Stable 1.80+ (`rustup default stable`)
- **System Audio/Graphics Libraries (Linux):**
  ```bash
  sudo apt-get update && sudo apt-get install -y libasound2-dev libx11-dev libxcb-render0-dev libxcb-shape0-dev libxcb-xfixes0-dev
  ```

### Build All Release Binaries
From the repository root:
```bash
cargo build --release
```

Compiled binaries will be available in `target/release/`:
- `anc-edge`: Edge real-time audio and telemetry daemon.
- `anc-bench`: Latency and RTF micro-benchmarking tool.
- `anc-process`: Batch file enhancement and objective scoring CLI.
- `anc-frontend`: Desktop GPU-accelerated operator dashboard.

---

## Usage Guide

### 1. Run the Latency & RTF Benchmark
Verify gate compliance on your hardware:
```bash
# Verify Asymmetric Low-Latency Window (16.01 ms total delay -> PASSES 35 ms gate)
cargo run --release -p anc-rust --bin anc-bench -- --window asymmetric --hop-size 128 --n-fft 512

# Verify Low-Latency 256/128 Framing (24.00 ms total delay -> PASSES 35 ms gate)
cargo run --release -p anc-rust --bin anc-bench -- --n-fft 256 --hop-size 128
```

### 2. Launch the Desktop Mission Control Dashboard
Start the GPU-accelerated desktop visualization console on your workstation:
```bash
cargo run --release -p anc-frontend
```

#### Run in Offline Demo Mode (No Hardware Needed)
Generates an internal 1 kHz test sine + noise signal to verify soundcard playback and UI plots:
```bash
cargo run --release -p anc-frontend -- --demo
```

### 3. Run the Embedded Edge Daemon (Raspberry Pi 5)
Deploy the standalone streaming daemon on the edge device:
```bash
# Stream live enhanced audio and telemetry to the operator workstation IP
cargo run --release -p anc-rust --bin anc-edge -- --target-ip 192.168.1.100
```

### 4. Process a WAV File & Calculate Objective Metrics
Enhance recorded stereo microphone files and score against clean reference:
```bash
cargo run --release -p anc-rust --bin anc-process -- \
  --input input_stereo.wav \
  --output enhanced_output.wav \
  --clean-ref clean_reference.wav
```

---

## Wire Protocol (SIH 26052)

| Port | Protocol | Format | Description |
| :---: | :---: | :---: | :--- |
| **5005** | UDP | Binary (1032 B) | **Enhanced Speech Output:** 8-byte uint64 sequence header + 256 float32 PCM samples (16 kHz mono). |
| **5006** | UDP | UTF-8 JSON | **Hardware & AI Telemetry:** Model name, compute time, RTF, core temp (°C), fallback counts. |
| **5007** | UDP | Binary (1032 B) | **Raw Reference Audio:** 8-byte uint64 sequence header + 256 float32 PCM samples. |

---

## Migration from Legacy Python Prototypes

The legacy Python prototypes (`edge/`, `sih26052_edge/`, and `frontend/`) have been **permanently retired and migrated** into this unified Rust workspace:
- **`edge/` & `sih26052_edge/`** $\to$ Replaced by **[anc-rust](anc-rust)** (zero heap allocations, sub-millisecond inference, polyphase Kaiser FIR resampling, causal MVDR).
- **`frontend/`** $\to$ Replaced by **[frontend-rust](frontend-rust)** (native 60 FPS egui dashboard, CPAL real-time audio playback, memory-only jitter buffer).

---

## License

This project is licensed under the [MIT License](LICENSE).
Developed for the Smart India Hackathon (SIH 26052).
