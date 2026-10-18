# Experimental Models & Architectures

## Overview
This directory contains experimental checkpoints, architecture prototypes, and ablation runs conducted during SIH26052 research.

## Non-Canonical Models
- **Polar-D / Stateful PolarLSTM**:
  - Evaluated on polar coordinate representations (magnitude mask + phase estimation).
  - Retired due to persistent recurrent state reverberation artifact (16 ms cross-correlation echo).
- **Complex CRN (Convolutional Recurrent Network)**:
  - Complex STFT enhancement network.
  - Retired due to computational overhead exceeding single-core real-time deadlines on Raspberry Pi 5.
- **DeepFilterNet3 v2 (Rejected Candidate)**:
  - Rejected due to source data leakage / overlap audit.

Canonical model is **DeepFilterNet3 (48 kHz)** frozen in `final_model/FINAL_DFN3_MODEL_INFO.md`.
