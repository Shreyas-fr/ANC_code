# PHASE 0 — FREEZE CURRENT STATE

**Date**: 2026-10-02

## 1. Current `dfn3_stream.py`
The script runs a simulation by feeding a 10s dummy audio array (48kHz) in 480-sample (10ms) chunks through the DeepFilterNet Python PyTorch CPU engine (`df.enhance`).

## 2. Model Hash
File: `runs/final_model/model.pt`
SHA256: `b2eb82f223fd394d42b086036b3b3a20c1e0d8fe20d8b404bed1b737e1871c3b`

## 3. Installed Environment (Raspberry Pi 5)
```text
DeepFilterLib      0.5.6
DeepFilterNet      0.5.6
torch              2.14.0+cpu
torchaudio         2.11.0+cpu
```

## 4. System Specs
Python version: 3.13.5
Architecture: aarch64 (ARM64)
OS: Debian 12 (Bookworm)

## 5. Current Benchmark Output
```text
10 s audio
1000 frames
90.96 s wall time
P95 22.19 ms
Max 133.97 ms
RTF ~2.2x
REAL-TIME FAILED
```

# PHASE 1 — PROFILE THE CURRENT IMPLEMENTATION

```text
=== PROFILING REPORT (ms) ===
pad             Median:   0.03 ms | P95:   0.08 ms
features        Median:   0.69 ms | P95:   1.02 ms
inference       Median:  84.91 ms | P95: 114.38 ms
complex_conv    Median:   0.03 ms | P95:   0.06 ms
istft           Median:   0.10 ms | P95:   0.19 ms
crop            Median:   0.02 ms | P95:   0.03 ms
total           Median:  85.84 ms | P95: 115.34 ms
```
The bottleneck is unquestionably the `PyTorch model execution` (inference). Feature extraction and Python overhead is negligible (< 1ms).

# PHASE 2 — NATIVE ENGINE CAPABILITIES

```text
Native engine available: YES (Rust tract/libDF via deep-filter CLI)
Model format required: .tar.gz containing ONNX files and config.ini
Conversion required: YES (PyTorch -> ONNX)
Conversion is lossless/official: YES (Using df.scripts.export)
48 kHz supported: YES
Streaming inference supported: YES
```
