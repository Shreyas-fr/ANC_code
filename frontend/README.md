# SIH 2026 PS 26052 — Live Defence Communication Frontend Dashboard

The PC Frontend is a high-performance, lightweight PySide6 desktop GUI for live audio playback, real-time visualization, telemetry display, and network connection management for the **SIH 2026 PS 26052 AI-Powered ANC & Speech Enhancement System**.

---

## Architectural Guarantee

- **Authoritative Edge Node**: The Raspberry Pi 5 performs all microphone capture, Bluetooth HFP routing, and DFN3 AI model inference.
- **PC Frontend Role**: The PC acts **exclusively** as a network receiver, live audio renderer, and telemetry visualization console.
- **No AI / PyTorch on PC**: The PC does **NOT** load PyTorch, run model checkpoints, or perform inference.
- **Memory-Only Streaming**: Normal operation processes all PCM audio in memory ring buffers (`JitterBuffer`). It **NEVER** records or writes `.wav` audio files to disk.
- **No Play Button Required**: Live audio playback begins automatically as soon as valid UDP stream frames are received.

---

## System Requirements

- Python 3.10+
- Dependencies: `PySide6`, `pyqtgraph`, `sounddevice`, `numpy`

Install dependencies:
```bash
pip install PySide6 pyqtgraph sounddevice numpy
```

---

## Startup Command

To launch the dashboard:

```bash
python frontend/main.py
```

---

## Network Ports & Protocols

| Port | Protocol | Purpose | Payload |
|---|---|---|---|
| **5005** | UDP | Enhanced Audio Stream | 8-byte uint64 seq header + 256 float32 PCM (1032 bytes) |
| **5006** | UDP | Pi Telemetry Stream | UTF-8 JSON datagrams |
| **5007** | UDP | Reference Input Stream | 8-byte uint64 seq header + 256 float32 PCM (1032 bytes) |

---

## Operational Modes

### 1. LIVE NETWORK Mode (Default)
- Listens on UDP port 5005 for live AI-enhanced audio from the Raspberry Pi 5.
- Displays live scrolling waveforms, 0–8 kHz FFT spectrum, network packet loss, sequence tracking, and jitter buffer health.
- If telemetry on Port 5006 is active, displays live latency, thermal, and AI state. If inactive, displays `N/A — telemetry unavailable`.

### 2. DEMO MODE (Offline Verification)
- Toggleable via the **MODE** button in the header.
- Generates an offline 1 kHz sine + noise test signal to verify UI responsiveness, rolling waveforms, spectrum FFT rendering, and soundcard output without requiring an active Raspberry Pi connection.
- Clearly labeled `DEMO — NOT LIVE PI DATA`.

---

## Fail-Safe State Machine

- **DISCONNECTED**: Triggered when no UDP audio packets arrive for 1.0 second. Automatically mutes audio output to prevent static/pop artifacts and displays `DISCONNECTED`.
- **LIVE**: Triggered when UDP audio packets arrive normally. Automatically resumes audio playback.
- **DEGRADED**: Triggered if network packet loss exceeds 5.0%.
- **ERROR / Malformed**: Corrupted or undersized packets are safely discarded without crashing the application.

---

## Unit Testing

Run unit tests:

```bash
pytest frontend/tests/
```
