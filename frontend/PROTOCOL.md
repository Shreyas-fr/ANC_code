# UDP PROTOCOL DEFINITION
## SIH 2026 PS 26052

This document defines the strict UDP audio and telemetry protocol used between the Raspberry Pi AI edge device and the Mac PC visualization dashboard.

### 1. UDP 5005 (Enhanced Output Audio)
- **Role:** AI-denoised audio output stream.
- **Packet Size:** 1032 bytes
- **Header (Bytes 0-7):** 8-byte little-endian unsigned 64-bit integer (`uint64`). Represents a monotonically increasing sequence number (`seq`).
- **Payload (Bytes 8-1031):** 1024 bytes containing exactly 256 mono float32 PCM samples.
- **Sample Rate:** 16,000 Hz.
- **Cadence:** 1 packet every 16 ms (in a perfect real-time system).

### 2. UDP 5007 (Raw Input Audio)
- **Role:** Unprocessed reference microphone input.
- **Packet Size:** 1032 bytes
- **Header (Bytes 0-7):** 8-byte little-endian unsigned 64-bit integer (`uint64`). This sequence tracker is completely independent of UDP 5005.
- **Payload (Bytes 8-1031):** 1024 bytes containing exactly 256 mono float32 PCM samples.
- **Sample Rate:** 16,000 Hz.
- **Cadence:** 1 packet every 16 ms.

### 3. UDP 5006 (Telemetry JSON)
- **Role:** AI Engine Health and Telemetry.
- **Packet Size:** Variable (JSON String UTF-8)
- **Format:** Uncompressed JSON string.
- **Expected Fields (Optional):**
  - `model` (string): e.g., "DeepFilterNet3"
  - `backend` (string): e.g., "Rust/Tract"
  - `model_sha` (string): Checksum of active model
  - `model_active` (bool)
  - `bluetooth_connected` (bool)
  - `latency_ms` (float)
  - `latency_median_ms` (float)
  - `temperature_c` (float)
  - `state_resets` (int)
  - `nan_inf_events` (int)
