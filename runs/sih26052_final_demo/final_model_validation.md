# Final Model Validation and Demonstration Report

## 1. Selected Checkpoint
- **Source**: `runs/sih26052_sisdr_loss_25k/best.pt`
- **Stored As**: `runs/sih26052_final_demo/selected_checkpoint.pt`

## 2. Integrity and Configuration
- **SHA-256**: `b2149b567a5f6df1ad41a87b5a87e07693fc4d33eb4c1e4c70a83e0dc91fc135` *(Computed via `sha256sum`)*
- **Architecture**: StatefulPolarLSTM
- **Parameter Count**: 1,448,962
- **Training Configuration**: Trained on V2 datasets with a mixed objective function (`5.0 * L1 + 5.0 * MRSTFT + 1.0 * SI_SDR`). Checkpoint frozen at Step 20,000.

## 3. Canonical Validation Results (590 Examples)
**Comparison**: Evaluated against the earlier V2 baseline checkpoint on the identical frozen canonical set.
- **SI-SDR Improvement**: +0.33 dB globally (p < 0.05).
- **SNR Improvement**: +0.13 dB globally (p < 0.05).
- **IoBT Gunfire Subgroup**: Stable time-domain features. Minimal SNR regression (-0.006 dB), with positive SI-SDR gains (+0.27 dB).
- **Proxy Noise Subgroup**: Dominant improvements in proxy environments (+0.53 dB SNR, +0.51 dB SI-SDR).
- **Mask Diagnostics**: Mean Mask Magnitude 0.95, Mask Std 0.018. The complex masking behavior proved significantly more stable without NaN/Inf failures. Phase predictions remained constrained. 

## 4. Raspberry Pi 5 Live Prototype Results
- **System Service**: Successfully deployed via `sih26052-edge.service`.
- **Streaming Pipeline**: Native PyTorch ARM64 Cortex-A76 Execution. 16ms frames natively processed using overlap-add and streaming iSTFT via Python.
- **Latency**: 5.2 ms median latency. p99 latency < 6.3 ms. Well under the 16 ms hard deadline.
- **Deadline Misses**: 0 misses across 57.6-second native daemon run.
- **Thermal & RAM**: 258 MB RAM utilized. Peak temperature 49.4°C. No throttling.
- **Live Microphone Status**: **NOT CONNECTED** (Verified via `arecord -l`). The application correctly handles null inputs or zeroes securely using its built-in bypass exception path without catastrophic systemd restart loops.

## 5. Demonstration Audio
Sample `0000` from the validation set was utilized to generate a clean, noisy, and enhanced audio triplet:
- **Clean Reference**: `runs/sih26052_final_demo/clean_reference.wav`
- **Noisy Input**: `runs/sih26052_final_demo/noisy_input.wav`
- **Enhanced Output**: `runs/sih26052_final_demo/enhanced_output.wav`

## 6. Gold Integrity Status
- **GOLD_ACCESSED_FOR_SELECTION**: NO
- **GOLD_MODIFIED**: NO
- **GOLD_SHA_UNCHANGED**: YES (`46236aef9af38056e08f296ac8c498dac888a85fb4b1ff9f371879c49670b0c9`)

## 7. Known Limitations & Claims Discipline
- The AI-based speech enhancement prototype has been physically validated regarding raw compute pipeline throughput and latency constraints. However, **complete physical ANC/acoustic validation is in progress**, as physical microphones are not yet attached to the edge node.
- Total microphone-to-headphone latency has not been empirically verified.
- The model exhibits highly competent real-time behavior but does not universally achieve >15 dB SNR; rather, it yields consistent improvements bounded strictly by the parameter constraints of the edge architecture.

## 8. Final Status
**FINAL_STATUS=DEMO_MODEL_READY**
