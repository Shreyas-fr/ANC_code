# SIH26052 PPT Validation Evidence

## 1. Embedded Latency
Status: VERIFIED
Source: `runs/sih26052_rpi_deployment_audit/60s_runtime_metrics.csv`, `runs/sih26052_rpi_deployment_audit/final_service_validation.md`
Measured result: Peak latency of 11.74 ms, median p50 latency of 5.63 ms, and exactly 0 deadline misses (>16.0 ms) across 3,600 frames (57.6s audio) executed natively on Raspberry Pi 5 CPU.
Evidence artifact: [results/ppt_latency_60s.png](file:///d:/ANC_code/results/ppt_latency_60s.png), [results/ppt_latency_60s.csv](file:///d:/ANC_code/results/ppt_latency_60s.csv), [results/ppt_latency_evidence.md](file:///d:/ANC_code/results/ppt_latency_evidence.md)
Limitations: Evaluated on continuous 60-second streaming inference pipeline on Raspberry Pi 5 under standalone background systemd daemon execution.

## 2. Thermal Stability
Status: VERIFIED
Source: `runs/sih26052_rpi_deployment_audit/60s_runtime_metrics.csv` (`temp_c` column via `vcgencmd measure_temp`), `runs/sih26052_rpi_deployment_audit/thermal_monitoring.csv`
Measured result: Initial temperature 46.1°C, peak temperature 49.4°C (ΔT = +3.3°C), throttling status `throttled=0x0` (no throttling), operating 25.6°C below the 75°C safety warning threshold.
Evidence artifact: [results/ppt_temperature_60s.png](file:///d:/ANC_code/results/ppt_temperature_60s.png), [results/ppt_temperature_evidence.md](file:///d:/ANC_code/results/ppt_temperature_evidence.md)
Limitations: Logged over a 60-second streaming window in ambient room conditions; multi-hour stress testing in enclosed headset enclosures should be verified for long-term thermal equilibrium.

## 3. Audio Enhancement Example
Status: VERIFIED
Source: `results/spectrogram_10dB.png` (exported to `results/ppt_spectrogram_comparison.png`), `results/metrics.csv`, `results/results_table.md`
Measured result: Standardized 10 dB SNR test condition demonstrates +2.69 dB output SNR gain (10.0 -> 12.69 dB), STOI 0.90 -> 0.9049 (Target > 0.85 PASS), PESQ 1.73 -> 2.04 (+0.30 gain), and SI-SDR improvement of +2.47 dB.
Evidence artifact: [results/ppt_spectrogram_comparison.png](file:///d:/ANC_code/results/ppt_spectrogram_comparison.png), [results/ppt_audio_example_evidence.md](file:///d:/ANC_code/results/ppt_audio_example_evidence.md)
Limitations: A single 3-panel spectrogram comparison illustrates qualitative spectral noise reduction and harmonic speech preservation for an individual sample; aggregate performance must be referenced from the full 1,194-test suite.

## 4. Embedded Hardware Evidence
Status: PARTIALLY VERIFIED
Source: `runs/sih26052_rpi_deployment_audit/system_inventory.txt`, `runs/sih26052_rpi_deployment_audit/service_status.txt`, `runs/sih26052_rpi_deployment_audit/audio_device_inventory.txt`, `runs/sih26052_rpi_deployment_audit/config/system_baseline.txt`
Evidence artifact: [results/ppt_hardware_evidence.md](file:///d:/ANC_code/results/ppt_hardware_evidence.md)
Limitations: No photographic camera images (`.jpg`/`.png`) or graphical desktop screenshots of the physical Raspberry Pi hardware exist in the repository (`NO DIRECT HARDWARE VISUAL EVIDENCE FOUND`). Direct evidence is established exclusively via terminal execution logs, system telemetry, ALSA audio device topologies, and active systemd daemon captures.

## Evidence Classification

- **1. Embedded Latency:** VERIFIED
- **2. Thermal Stability:** VERIFIED
- **3. Audio Enhancement Example:** VERIFIED
- **4. Embedded Hardware Evidence:** PARTIALLY VERIFIED
