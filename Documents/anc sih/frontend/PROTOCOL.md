# SIH 2026 PS 26052 — Network Protocol Specification

This document defines the exact UDP network streaming and telemetry protocol between the **Raspberry Pi 5 (Edge AI Processing Device)** and the **PC Frontend (Live Playback & Telemetry Dashboard)**.

---

## Architecture Overview

```
[Bluetooth Microphone]
        ↓ (HFP PCM 16kHz)
[Raspberry Pi 5]
        ↓ (StatefulPolarLSTM AI Enhancement)
[UDP Network Sender]
        ↓
  -------------------------------------------------------------
  Port 5005 (UDP) | Enhanced Audio Stream (Binary)
  Port 5006 (UDP) | Pi System & AI Telemetry Stream (JSON)
  Port 5007 (UDP) | Reference Input Audio Stream (Binary Extension)
  -------------------------------------------------------------
        ↓
[PC Frontend Dashboard] → Speakers / Headphones
```

---

## 1. Enhanced Audio Stream Channel (Port 5005)

- **Transport**: UDP
- **Port**: `5005`
- **Sample Rate**: 16,000 Hz (16 kHz mono)
- **Frame Duration**: 16 ms (256 samples per packet)
- **Packet Structure**:
  - `Header` (8 bytes): Unsigned 64-bit little-endian integer (`uint64_t` / `<Q`), sequence number starting from 0.
  - `Payload` (1024 bytes): 256 contiguous 32-bit single-precision IEEE float (`float32` / `float`) PCM audio samples.
- **Total Packet Size**: `1032 bytes` (8 header + 1024 payload).

---

## 2. Telemetry Channel (Port 5006)

- **Transport**: UDP
- **Port**: `5006`
- **Format**: UTF-8 encoded JSON object per UDP datagram.
- **Sample Payload Structure**:

```json
{
  "timestamp": 1727785200.123,
  "frames_processed": 3750,
  "latency_ms": 11.45,
  "latency_median_ms": 11.20,
  "latency_p95_ms": 13.80,
  "latency_max_ms": 15.60,
  "state_resets": 0,
  "nan_inf_events": 0,
  "temperature_c": 54.2,
  "model_active": true,
  "bluetooth_connected": true
}
```

*Note: If telemetry on Port 5006 is inactive, the PC Frontend clearly displays `N/A — telemetry unavailable` rather than inventing false values.*

---

## 3. Reference Input Audio Stream Channel (Port 5007 Extension)

- **Transport**: UDP
- **Port**: `5007`
- **Format**: Same binary format as Port 5005 (8-byte uint64 sequence header + 256 float32 samples).
- **Purpose**: Optional protocol extension for transmitting raw pre-AI audio from the Pi to the PC for visualization only.

---

## Security & Performance Considerations

1. **No Disk I/O**: The PC Frontend processes all network audio streams entirely in memory ring buffers (`JitterBuffer`).
2. **Decoupled Architecture**: PyTorch inference is **never** executed on the PC; the Pi is the authoritative edge computing node.
