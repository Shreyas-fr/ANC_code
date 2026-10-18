# SIH26052 Edge Deployment Runtime

## Overview
This directory contains the Raspberry Pi 5 runtime configuration, PipeWire / ALSA audio interface scripts, and systemd service descriptors for autonomous edge AI noise suppression.

## Canonical Edge Code
- Real-time Pi streaming code is located under `edge/` in the main repository:
  - `edge/dfn3_stream.py`: Live 500 ms block + 300 ms context DFN3 processing.
  - `edge/dfn3_live_sender.py`: Network UDP audio sender and telemetry publisher.
  - `edge/streaming_core.py`: Circular buffer and stateful audio engine.
- System service descriptor: `edge/config/sih26052-edge.service`.
- Hardware audit logs and thermal benchmarks: `runs/sih26052_rpi_deployment_audit/`.

## Deployment Instructions
1. Install system dependencies on Pi 5: `pipewire`, `wireplumber`, `libsamplerate0`.
2. Copy `edge/` code and model to `~/sih26052_edge/`.
3. Enable systemd unit: `sudo systemctl enable --now sih26052-edge.service`.
