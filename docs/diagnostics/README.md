# ANC Edge: Real-Time DeepFilterNet3 on Raspberry Pi 5

This repository contains the deployment codebase for running DeepFilterNet3 (fine-tuned) in real-time on a Raspberry Pi 5. It includes the frontend PC receiver GUI and the Pi-side asynchronous network sender.

## Architecture

* **Pi Backend (`pi_sender_v2.py` / `dfn3_paced2.py`)**: Runs headless on the Pi. It captures Bluetooth audio from a headset, processes it through the customized DFN3 model in 500ms block windows (pacing 256-sample chunks), and streams the enhanced audio out via UDP.
* **Mac Frontend (`frontend/main.py`)**: A PyQt6 GUI that receives the UDP audio stream, manages jitter, and plays back the enhanced audio while displaying real-time telemetry.

## Hardware Optimization & Results

During our 6-minute, memory-resident concurrent stress test, we validated the Pi 5's capability to sustain the deep learning workload natively without DSP hardware or external accelerators. 

**Honest Load Test Results (1-Thread DFN3 + UDP Streamer):**

| Metric | Result | Notes |
| :--- | :--- | :--- |
| **Max Compute Time** | `424.6 ms` | Stays safely below the 500 ms block deadline. |
| **Median Compute Time** | `213.2 ms` | Running comfortably at ~0.4x real-time (1 thread). |
| **Power (EXT5V_V)** | `4.78V (Min)` / `5.03V (Max)` | Stable voltage via standard 5V/3A Apple brick. |
| **Thermal (Max Temp)** | `60.9 °C` | No active cooling needed; well below 82°C throttle limit. |
| **Throttling Events** | `0x0` | Zero under-voltage or thermal throttling occurred. |
| **Memory Available** | `1.3 GB` | Perfectly stable footprint with zero memory leaks. |
| **Dropped Frames** | `0` | Out of 18,737 frames sent, zero network drops. |
| **Stream Jitter** | `0.02 ms (Max)` | Sub-millisecond jitter over Wi-Fi. |

## Quick Start

1. **Start the Frontend (Mac)**
```bash
cd "anc sih"
./pc_venv/bin/python frontend/main.py
```

2. **Start the Backend (Raspberry Pi)**  
   Connect your Bluetooth headset first, then:
   ```bash
   /home/shreyas/env/bin/python ~/sih26052_edge/anc_fix_v2/anc_fix/pi_sender_v2.py \
       --mode dfn3 \
       --target-ip <MAC_IP> \
       --name-match Rockerz
   ```
   To find your Mac's IP: `ipconfig getifaddr en0`

3. **Modes**

   | Mode | Description |
   | :--- | :--- |
   | `--mode dfn3` | Full AI noise cancellation via DeepFilterNet3 (default) |
   | `--mode raw` | Bypass model — stream raw mic audio for testing/latency check |
   | `--mode resampled` | Resample-only (stateful FIR, no AI) |

## Project Structure

```
anc sih/
├── frontend/                   # Mac GUI receiver
│   ├── main.py                 # Entry point
│   ├── audio/                  # Jitter buffer & playback
│   ├── network/                # UDP audio & telemetry receivers
│   ├── ui/                     # PyQt6 widgets (waveform, spectrum, telemetry)
│   ├── config/frontend_config.json
│   └── tests/                  # Frontend unit tests (7 passing)
├── sih26052_edge/              # Pi-side code
│   └── anc_fix_v2/anc_fix/
│       ├── pi_sender_v2.py     # Main sender: BT capture → DFN3 → UDP
│       ├── streaming_core.py   # AudioChain, BlockBackend, IdentityBackend
│       └── dfn3_enhance.py     # DFN3 model wrapper
├── dfn3_paced2.py              # Standalone paced inference tester (in-memory)
├── power_logger.sh             # 1Hz power/thermal CSV logger (writes to /dev/shm)
├── run_s2.sh                   # Concurrent stress-test orchestration script
├── final_model/                # Frozen production model
│   ├── model.hk
│   └── FINAL_DFN3_MODEL_INFO.md
└── README.md
```

## Testing

The frontend test suite uses `pytest` and requires no model files or Bluetooth hardware:

```bash
./pc_venv/bin/python -m pip install numpy pytest
./pc_venv/bin/python -m pytest frontend/tests/ -q
```

Expected output: **7 passed in ~0.2s**

Tests cover:
- `test_jitter_buffer.py` — jitter buffer fill/drain/overflow behaviour
- `test_packet_parser.py` — UDP frame header parsing (8-byte seq + 1024-byte f32 payload)
- `test_sequence_tracking.py` — out-of-order, duplicate, and gap detection

## Dependencies

**Mac (frontend)**
```
PySide6 / PyQt6
numpy < 2.0
soundfile
```

**Raspberry Pi (backend)**
```
torch (Pi 5 wheel)
deepfilternet 0.5.6
numpy < 2.0
soundfile
pipewire / wireplumber (for Bluetooth audio capture via pw-record)
```

## Known Constraints

- **USB-PD not negotiated**: The Apple 35W brick provides 5V/3A via standard negotiation (not USB-PD PDO). The Pi 5 operates stably within this budget at 1-thread inference.
- **Bootloader update available**: EEPROM is at May 2026; a Sep 2026 update is pending (`sudo rpi-eeprom-update`).
- **All runtime logs in `/dev/shm/`**: Avoid writing to the USB drive during inference — prior testing revealed I/O-induced deadlines from USB flush latency. All power CSVs and JSON reports stay in memory-only paths.
- **1-thread only for production**: 2-thread stages increased compute headroom but added scheduling jitter. 1-thread at `--block-ms 500 --context-ms 300` is the validated production configuration.
