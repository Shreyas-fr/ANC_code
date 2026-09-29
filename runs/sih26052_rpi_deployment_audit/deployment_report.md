# Raspberry Pi Edge Deployment Audit — SIH26052

## 1. System Inventory
* **Model**: Raspberry Pi 5 Model B Rev 1.1
* **CPU Architecture**: aarch64 (Cortex-A76)
* **CPU Cores**: 4
* **Available RAM**: 2.0 Gi total (1.6 Gi available)
* **OS**: Debian GNU/Linux 13 (trixie)
* **Kernel**: Linux shreyas 6.18.50+rpt-rpi-2712 #1 SMP PREEMPT Debian 1:6.18.50-1+rpt1 (2026-09-11) aarch64 GNU/Linux

## 2. Dependency Audit
* **Python**: 3.13.5
* **Inference Runtime**: PyTorch (1.14.0+cpu) locally on Pi (The existing ONNX pipeline was hardcoded for `ComplexCRN` and could not support `StatefulPolarLSTM` without major modifications to the ONNX export script. Thus, PyTorch CPU is used for direct performance measurement of the exact PyTorch checkpoint).

## 3. Model Integrity
* **Model Checkpoint**: `runs/sih26052_polar_v2_25k/best.pt`
* **Model Hash**: `b105b714b0ca510662050b4fc6e099a8e779d9042549486a79d8119708e51d9a`
* **Parameter Count**: 1,448,962

## 4. Benchmark Results
### Microbenchmark (1000 frames)
* **Median processing time**: 8.40 ms
* **p99 processing time**: 10.19 ms
* **Real-time Factor**: 1.63x
* **Deadline Miss Rate (>16ms)**: 0.20%

### Continuous Streaming (60 seconds / 3750 frames)
* **Total Stream Frames**: 3750
* **Dropped Frames / Deadline Misses**: 3 (0.08%)
* **State Reset Count**: 0
* **NaN/Inf Count**: 0

### Hardware Telemetry
* **Initial / Final Temp**: 44.4°C -> 51.0°C (No Thermal Throttling)
* **Frequency**: Stable at 2400 MHz
* **RAM Usage**: Increased from 258.1 MB to 402.5 MB (Stable after model load)

## 5. Final Classification
* **Status**: **DEPLOYABLE / FEASIBLE**
* **Conclusion**: The `StatefulPolarLSTM` completes inference well within the 16 ms budget natively on the Raspberry Pi 5 CPU without the need for ONNX/quantization, achieving a processing median of 8.4ms (RTF > 1.5). Streaming stability is excellent with a near-zero frame drop rate. Statefulness tests confirm numerical consistency with the PyTorch baseline.
