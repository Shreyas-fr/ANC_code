# Verified Project Assets Manifest for SIH 2026 Presentation & Video

**Problem Statement:** SIH26052 — AI/ML-Enabled Adaptive Noise Cancellation for Defence Communication  
**Repository:** `Shreyas-fr/ANC_code`  
**Date:** September 30, 2026  
**Audit Standard:** Strict Experimental Evidence & Verification Hierarchy  

---

## 1. Inventory of Verified Assets in `assets/ppt_video/`

| Filename | What It Shows | Source Origin | Safe for PPT/Video? | Exact Verified Metrics | Claims NOT to Make |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`ppt_latency_60s.png`** | Per-window inference latency percentiles (p50, p95, p99, peak) vs. 16.0 ms real-time deadline across 60s stream | `runs/sih26052_rpi_deployment_audit/60s_runtime_metrics.csv` | **YES (Highly Recommended)** | • 3,600 frames (57.6s audio)<br>• Median p50: **5.63 ms**<br>• p95: **5.73 ms**<br>• Max Peak: **11.74 ms**<br>• Deadline Misses: **0 (0.00%)** | Do NOT claim 0 ms latency or that the model runs in zero time. Algorithmic framing is 16.0 ms. |
| **`ppt_temperature_60s.png`** | Raspberry Pi 5 SoC temperature (°C) trajectory during the 60s continuous streaming run | `runs/sih26052_rpi_deployment_audit/60s_runtime_metrics.csv` (`temp_c` via `vcgencmd`) | **YES (Recommended)** | • Initial: **46.1°C**<br>• Peak: **49.4°C** (Δ = +3.3°C)<br>• Throttling: **None (`0x0`)**<br>• Governor: **2400 MHz (Stable)** | Do NOT claim long-term multi-day thermal equilibrium under full enclosed chassis without quoting the 60s test window. |
| **`ppt_spectrogram_comparison.png`** | 3-Panel Spectrogram: Clean Reference vs. 10 dB Noisy Input vs. Enhanced Output | `results/spectrogram_10dB.png` (Canonical evaluation run) | **YES (Recommended)** | • Output SNR: **10.0 -> 12.69 dB** (+2.69 dB)<br>• STOI: **0.90 -> 0.9049** (PASS > 0.85)<br>• PESQ: **1.73 -> 2.04** (+0.30)<br>• SI-SDR Imp: **+2.47 dB** | Do NOT claim that this single utterance proves identical denoising across all unseen environments. |
| **`spectrogram_-5dB.png`** | 3-Panel Spectrogram: Clean Reference vs. -5 dB Heavy Noise Input vs. Enhanced Output | `results/spectrogram_-5dB.png` | **YES (Optional / Deep Dive)** | • Output SNR: **-5.0 -> 2.32 dB** (+7.32 dB)<br>• SI-SDR Imp: **+5.61 dB** | Do NOT claim PESQ > 2.5 is met at -5 dB (actual PESQ is 1.23, which is honestly documented). |
| **`targets_vs_measured.png`** | Bar chart comparing Problem Statement targets vs. measured results across all SNR tiers | `results/targets_vs_measured.png` | **YES (Recommended for Results Slide)** | • Full 6-tier SNR progression (-5 dB to 20 dB)<br>• 1,194 test evaluations | Do NOT claim all targets pass at negative SNRs. |
| **`ppt_latency_60s.csv`** | Numerical CSV table with per-window timestamps, cumulative frames, and percentiles | Generated from `runs/sih26052_rpi_deployment_audit/60s_runtime_metrics.csv` | **YES (For Data Tables)** | Matches all exact values of `ppt_latency_60s.png` | N/A |
| **`rpi_60s_runtime_metrics.csv`** | Raw telemetry CSV logged live on Raspberry Pi 5 under `sih26052-edge.service` | `runs/sih26052_rpi_deployment_audit/60s_runtime_metrics.csv` | **YES (Raw Evidence)** | Real-time Pi telemetry logs | N/A |
| **`sisdr_loss_paired_statistics.csv`** | Wilcoxon signed-rank paired statistical audit across 590 canonical pairs | `runs/sih26052_sisdr_loss_25k/paired_statistics.csv` | **YES (Key Statistics)** | • Canonical pairs: **590**<br>• Mean SI-SDR delta: **+0.334661342 dB**<br>• Mean SNR delta: **+0.128774128 dB**<br>• SI-SDR p-value: **3.49e-28**<br>• SNR p-value: **0.00441** | Do NOT claim massive multi-dB gains over V2 baseline; improvement is modest (+0.33 dB) but statistically significant across all 4 metrics. |
| **`rpi_service_status.txt`** | Live systemd terminal status of `sih26052-edge.service` active daemon on Pi | `runs/sih26052_rpi_deployment_audit/service_status.txt` | **YES (Terminal Evidence)** | • PID: 2527<br>• Active: running (systemd user daemon) | Do NOT claim this is a physical photograph; it is an authentic terminal log. |
| **`rpi_system_inventory.txt`** | Hardware audit showing Raspberry Pi 5 Model B Rev 1.1, 4-core Cortex-A76 @ 2.4 GHz | `runs/sih26052_rpi_deployment_audit/system_inventory.txt` | **YES (Hardware Evidence)** | • BCM2712 aarch64<br>• 2.0 GiB RAM<br>• Debian 13 trixie | N/A |
| **`interactive_diagram.html`** | Interactive HTML diagram visualizing the neural architecture, STFT/iSTFT pipeline, and user flow | Root `interactive_diagram.html` | **YES (Interactive Demo / Video)** | Stateful Polar-LSTM architecture & causal STFT framing | N/A |
| **`system_diagrams.md`** | Comprehensive Mermaid diagrams of neural architecture, streaming engine, and data splits | Root `system_diagrams.md` | **YES (Visual Reference)** | Architectural layout & tensor dimensions (514 -> 256 LSTM -> 514) | N/A |
| **`SIH_26052_Presentation.pptx`** | Generated multi-slide PowerPoint presentation tailored for SIH 2026 Problem Statement 26052 | Root `SIH_26052_Presentation.pptx` | **YES (Presentation Deck)** | Contains full project narrative, architecture, and validated metrics | Review team name placeholders before final delivery. |

---

## 2. Audio & Video Demonstration Assets Status

### Audio Files
- **Status in Git Repository:** Binary `.wav` audio demonstration files (`clean_reference.wav`, `noisy_input.wav`, `enhanced_output.wav`) are generated dynamically or stored on edge device audio scratch paths (`/home/shreyas/sih26052_edge/audio/`). They are **not committed to the Git repository** to prevent repository bloat.
- **Spectrogram Visualizations:** The repository provides fully validated 3-panel spectrogram visualizations representing these exact audio pairs:
  - [ppt_spectrogram_comparison.png](file:///d:/ANC_code/assets/ppt_video/ppt_spectrogram_comparison.png) (10 dB SNR speech-in-noise)
  - [spectrogram_-5dB.png](file:///d:/ANC_code/assets/ppt_video/spectrogram_-5dB.png) (-5 dB SNR heavy noise)

### Live Bluetooth Microphone & Hardware Demonstration Status
- **Actual Hardware Test Status:** **DOCUMENTED & CONDUCTED ON PI HOST**
- **Hardware Verified:** Noise Buds VS102 Bluetooth earbuds (MAC: `E4:16:5F:F7:5D:47`) were paired and connected via Handsfree Profile (HFP, UUID: `0000111e`) to PipeWire node `46` (`bluez_input.E4:16:5F:F7:5D:47`) on the Raspberry Pi 5.
- **Streaming Verification:** Live AI processing was executed across 1,250–3,750 frames on the Pi, streaming live processed frames over network socket to a PC receiver ([live_ai_stream_report.md](file:///d:/ANC_code/edge_deployment_tests/live_ai_stream_report.md), [final_test2_report.md](file:///d:/ANC_code/edge_deployment_tests/final_test2_report.md)).
- **Video Recording Status:** **NO RECORDED MP4/WEBM VIDEO FILE EXISTS IN THE LOCAL REPOSITORY**.
  - *Discipline Directive:* The presentation and video should present the authentic systemd logs, architecture diagrams, and streaming reports, but should **NOT claim or show a pre-recorded camera video of the bench unless the presenter records one live during the presentation**.

---

## 3. Authoritative Verified Numbers (Final Audit)

| Metric / Parameter | Exact Verified Value | Authoritative Source |
| :--- | :--- | :--- |
| **Canonical Validation Pairs** | **590 pairs** (442 IoBT Gunfire + 148 Existing Proxy) | `runs/sih26052_sisdr_loss_25k/paired_statistics.csv` |
| **Mean SI-SDR Improvement (Delta)** | **+0.334661342 dB** (p = `3.49e-28`, Statistically Significant) | `runs/sih26052_sisdr_loss_25k/paired_statistics.csv` |
| **Mean SNR Improvement (Delta)** | **+0.128774128 dB** (p = `0.00441`, Statistically Significant) | `runs/sih26052_sisdr_loss_25k/paired_statistics.csv` |
| **Mean STOI Delta** | **+0.000054395** (p = `3.60e-21`, Statistically Significant) | `runs/sih26052_sisdr_loss_25k/paired_statistics.csv` |
| **Mean PESQ Delta** | **+0.004679598** (p = `2.43e-35`, Statistically Significant) | `runs/sih26052_sisdr_loss_25k/paired_statistics.csv` |
| **Model Parameters** | **1,448,962 (~1.45M)** | `runs/sih26052_polar_v2_25k/config.yaml`, `final_claim_audit.md` |
| **Raspberry Pi Processed Frames (60s Stream)** | **3,600 frames** (57.6s audio at 16 kHz) | `runs/sih26052_rpi_deployment_audit/60s_runtime_metrics.csv` |
| **Raspberry Pi Deadline Misses (>16 ms)** | **0 misses (0.00%)** | `runs/sih26052_rpi_deployment_audit/60s_runtime_metrics.csv` |
| **Median (p50) Inference Latency** | **5.63 ms** | `runs/sih26052_rpi_deployment_audit/60s_runtime_metrics.csv` |
| **95th Percentile (p95) Inference Latency** | **5.73 ms** | `runs/sih26052_rpi_deployment_audit/60s_runtime_metrics.csv` |
| **99th Percentile (p99) Inference Latency** | **6.30 ms** | `runs/sih26052_rpi_deployment_audit/60s_runtime_metrics.csv` |
| **Maximum (Peak) Inference Latency** | **11.74 ms** (100% within 16.0 ms budget) | `runs/sih26052_rpi_deployment_audit/60s_runtime_metrics.csv` |
| **SoC Peak Temperature** | **49.4°C** (Initial: 46.1°C, Δ = +3.3°C, `throttled=0x0`) | `runs/sih26052_rpi_deployment_audit/60s_runtime_metrics.csv` |
