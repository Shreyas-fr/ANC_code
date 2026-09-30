# Evidence Note: Thermal Telemetry During 60-Second Run

## 1. Source Files & Synchronized Logging
- **Primary Source:** [runs/sih26052_rpi_deployment_audit/60s_runtime_metrics.csv](file:///d:/ANC_code/runs/sih26052_rpi_deployment_audit/60s_runtime_metrics.csv) (column `temp_c`)
- **Supplementary Thermal Log:** [runs/sih26052_rpi_deployment_audit/thermal_monitoring.csv](file:///d:/ANC_code/runs/sih26052_rpi_deployment_audit/thermal_monitoring.csv)
- **Deployment Summary:** [runs/sih26052_rpi_deployment_audit/final_service_validation.md](file:///d:/ANC_code/runs/sih26052_rpi_deployment_audit/final_service_validation.md)
- **Telemetry Query Implementation:** [runs/sih26052_rpi_deployment_audit/app/monitor.py](file:///d:/ANC_code/runs/sih26052_rpi_deployment_audit/app/monitor.py) (`vcgencmd measure_temp` and `vcgencmd get_throttled`)

## 2. Telemetry Methodology
During the 60-second continuous streaming execution on the Raspberry Pi 5 (`sih26052-edge.service`), the `PerformanceMonitor` asynchronously polled the Broadcom BCM2712 SoC thermal sensor every ~5.0–6.4 seconds via the native Raspberry Pi firmware command `vcgencmd measure_temp`.

## 3. Measured Thermal & System State
- **Initial SoC Temperature (t = 0.0s):** **46.1°C**
- **Peak SoC Temperature (t = 45.2s):** **49.4°C**
- **Final SoC Temperature (t = 51.6s):** **48.8°C**
- **Total Temperature Rise (ΔT):** **+3.3°C**
- **Hardware Throttling Status:** **`throttled=0x0`** (Zero throttling, no undervoltage, no thermal capping)
- **CPU Clock Frequency:** **2400 MHz (Stable)**
- **System RAM Footprint:** **257.7 MB – 258.0 MB (Constant)**
- **Safety Headroom:** **25.6°C below warning threshold** (75°C warning limit configured in `config.json`, 85°C critical shutdown limit)

## 4. Generated Artifact
- **Presentation Graph:** [results/ppt_temperature_60s.png](file:///d:/ANC_code/results/ppt_temperature_60s.png)
