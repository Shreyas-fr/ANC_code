# Evidence Note: Raspberry Pi Embedded Deployment & Hardware

## Visual Evidence Status
`NO DIRECT HARDWARE VISUAL EVIDENCE FOUND`

*Explanation:* An exhaustive scan of the repository confirmed that no photographic images (`.jpg`, `.png`), camera snapshots of the Raspberry Pi board/bench setup, or graphical terminal screenshot bitmaps are stored in the repository. In accordance with strict scientific validation rules, no artificial, placeholder, or AI-generated hardware photographs have been created.

---

## Direct Non-Visual Hardware & Deployment Evidence

While direct photographic evidence is absent, the repository contains extensive, authoritative, and reproducible text logs, system audit telemetry, ALSA device inventories, and systemd service runtime captures generated directly on the target hardware:

### 1. Target Hardware Inventory
- **Source File:** [runs/sih26052_rpi_deployment_audit/system_inventory.txt](file:///d:/ANC_code/runs/sih26052_rpi_deployment_audit/system_inventory.txt) & [runs/sih26052_rpi_deployment_audit/config/system_baseline.txt](file:///d:/ANC_code/runs/sih26052_rpi_deployment_audit/config/system_baseline.txt)
- **Device Model:** Raspberry Pi 5 Model B Rev 1.1
- **CPU Architecture:** aarch64 (Broadcom BCM2712, 4-core Cortex-A76 @ 2.4 GHz)
- **Total Memory:** 2.0 GiB RAM (1.6 GiB available)
- **Operating System:** Debian GNU/Linux 13 (trixie), Kernel: `Linux shreyas 6.18.50+rpt-rpi-2712 #1 SMP PREEMPT Debian 1:6.18.50-1+rpt1`

### 2. Live Systemd Daemon Service Output
- **Source File:** [runs/sih26052_rpi_deployment_audit/service_status.txt](file:///d:/ANC_code/runs/sih26052_rpi_deployment_audit/service_status.txt)
- **Service Name:** `sih26052-edge.service` (SIH26052 StatefulPolarLSTM ANC Edge Service)
- **Daemon Executable:** `/home/shreyas/env/bin/python /home/shreyas/sih26052_edge/app/anc_stream.py`
- **Daemon Status:** Active / Running under user slice `user-1000.slice`

### 3. ALSA Audio Hardware Mapping
- **Source File:** [runs/sih26052_rpi_deployment_audit/audio_device_inventory.txt](file:///d:/ANC_code/runs/sih26052_rpi_deployment_audit/audio_device_inventory.txt)
- **Captured Devices:** ALSA hardware sound cards, capture/playback nodes, and loopback audio interfaces configured for embedded real-time audio I/O.

### 4. Hardware Checkpoint Integrity Verification
- **Source File:** [runs/sih26052_rpi_deployment_audit/model_integrity.txt](file:///d:/ANC_code/runs/sih26052_rpi_deployment_audit/model_integrity.txt)
- **Deployed Checkpoint:** `/home/shreyas/sih26052_edge/models/best.pt`
- **Cryptographic SHA-256:** `b105b714b0ca510662050b4fc6e099a8e779d9042549486a79d8119708e51d9a` (Exact bit-level match with repository checkpoint `runs/sih26052_polar_v2_25k/best.pt`).
