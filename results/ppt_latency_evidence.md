# Evidence Note: 60-Second Embedded Latency Experiment

## 1. Source Files & Configuration
- **Raw Measurements File:** [runs/sih26052_rpi_deployment_audit/60s_runtime_metrics.csv](file:///d:/ANC_code/runs/sih26052_rpi_deployment_audit/60s_runtime_metrics.csv)
- **Deployment Summary Report:** [runs/sih26052_rpi_deployment_audit/final_service_validation.md](file:///d:/ANC_code/runs/sih26052_rpi_deployment_audit/final_service_validation.md)
- **Streaming Pipeline Script:** [runs/sih26052_rpi_deployment_audit/app/anc_stream.py](file:///d:/ANC_code/runs/sih26052_rpi_deployment_audit/app/anc_stream.py)
- **Performance Monitor:** [runs/sih26052_rpi_deployment_audit/app/monitor.py](file:///d:/ANC_code/runs/sih26052_rpi_deployment_audit/app/monitor.py)
- **Runtime Configuration:** [runs/sih26052_rpi_deployment_audit/config/config.json](file:///d:/ANC_code/runs/sih26052_rpi_deployment_audit/config/config.json)

## 2. Experiment Details
- **Hardware Platform:** Raspberry Pi 5 Model B Rev 1.1 (Cortex-A76 @ 2.4 GHz, 4 Cores, 2.0 GiB RAM)
- **OS & Kernel:** Debian GNU/Linux 13 (trixie), Linux 6.18.50+rpt-rpi-2712 aarch64
- **Model Checkpoint:** `StatefulPolarLSTM` (`runs/sih26052_polar_v2_25k/best.pt`, 1,448,962 parameters, SHA-256: `b105b714b0ca510662050b4fc6e099a8e779d9042549486a79d8119708e51d9a`)
- **Execution Mode:** Background systemd daemon service (`sih26052-edge.service`)
- **Total Processed Frames:** 3,600 frames (9 windows × 400 frames/window)
- **Audio Duration Processed:** 57.6 seconds (at 16,000 Hz, hop size = 256 samples)
- **Elapsed Wall-Clock Duration:** 51.64 seconds

## 3. Measured Latency Metrics
- **Real-Time Frame Budget:** **16.0 ms** (exact algorithmic hop constraint: 256 samples / 16,000 Hz)
- **Median Window p50 Latency:** **5.63 ms** (Window p50 range: 5.33 ms to 5.66 ms, mean: 5.56 ms)
- **95th Percentile (p95) Latency:** **5.59 ms – 5.73 ms**
- **99th Percentile (p99) Latency:** **5.70 ms – 6.30 ms**
- **Peak / Maximum Measured Latency:** **11.74 ms** (Observed in Window 2; 100% within 16.0 ms budget)
- **Deadline Misses (> 16.0 ms):** **0 out of 3,600 frames (0.00%)**
- **Real-Time Factor (RTF) Headroom:** ~2.88× faster than real-time (35% budget consumption at p50, 73.4% at peak spike)

## 4. Generated Artifacts
- **Presentation Graph:** [results/ppt_latency_60s.png](file:///d:/ANC_code/results/ppt_latency_60s.png)
- **Formatted Data Table:** [results/ppt_latency_60s.csv](file:///d:/ANC_code/results/ppt_latency_60s.csv)

## 5. Reproducibility
- **Reproducible:** Yes. The streaming engine ([anc_stream.py](file:///d:/ANC_code/runs/sih26052_rpi_deployment_audit/app/anc_stream.py)) operates deterministically using PyTorch CPU tensor operations on Raspberry Pi 5.
