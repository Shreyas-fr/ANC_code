# DeepFilterNet3 Canonical Per-SNR Evaluation Table

- **Evaluated Checkpoint**: `final_model/model.hk` (SHA256 `522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe`)
- **Dataset**: SIH26052 Canonical 590-clip Validation Set
- **Date**: 2026-10-18 19:39:53

## Problem Statement (PS) Targets
- **Output SNR**: > 15.0 dB (explicit formula $10\log_{10}(\|\text{clean}\|^2 / \|\text{est} - \text{clean}\|^2)$)
- **STOI**: > 0.85
- **PESQ (wideband, 16 kHz)**: > 2.50

## Measured Per-SNR Results

| Input SNR (dB) | n | Noisy In SNR | DFN3 Out SNR (dB) | PS SNR (>15 dB) | Noisy STOI | DFN3 STOI | PS STOI (>0.85) | Noisy PESQ | DFN3 PESQ | PS PESQ (>2.5) | Noisy SI-SDR | DFN3 SI-SDR |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| -10.0 | 30 | -10.00 ± 0.00 | **-2.92 ± 3.82** | **FAIL** | 0.571 ± 0.152 | **0.648 ± 0.157** | **FAIL** | 1.089 ± 0.073 | **1.144 ± 0.113** | **FAIL** | -10.14 ± 0.27 | -4.48 ± 5.90 |
| -5.0 | 63 | -3.35 ± 13.00 | **1.49 ± 3.42** | **FAIL** | 0.694 ± 0.150 | **0.774 ± 0.131** | **FAIL** | 1.229 ± 0.488 | **1.385 ± 0.505** | **FAIL** | -3.28 ± 13.87 | 2.29 ± 4.63 |
| +0.0 | 117 | 0.85 ± 9.11 | **3.96 ± 2.57** | **FAIL** | 0.757 ± 0.124 | **0.826 ± 0.117** | **FAIL** | 1.236 ± 0.361 | **1.434 ± 0.376** | **FAIL** | 0.61 ± 9.85 | 5.45 ± 3.47 |
| +5.0 | 137 | 5.00 ± 0.00 | **6.95 ± 1.68** | **FAIL** | 0.826 ± 0.094 | **0.875 ± 0.085** | **PASS** | 1.420 ± 0.351 | **1.687 ± 0.364** | **FAIL** | 4.65 ± 1.79 | 9.24 ± 2.57 |
| +10.0 | 121 | 10.74 ± 8.06 | **8.51 ± 1.52** | **FAIL** | 0.891 ± 0.085 | **0.913 ± 0.074** | **PASS** | 1.806 ± 0.578 | **2.021 ± 0.467** | **FAIL** | 10.67 ± 8.72 | 11.38 ± 1.94 |
| +15.0 | 86 | 15.98 ± 9.01 | **10.31 ± 1.88** | **FAIL** | 0.936 ± 0.058 | **0.942 ± 0.050** | **PASS** | 2.130 ± 0.520 | **2.309 ± 0.478** | **FAIL** | 15.77 ± 9.23 | 13.50 ± 1.73 |
| +20.0 | 36 | 20.00 ± 0.00 | **10.64 ± 2.50** | **FAIL** | 0.958 ± 0.052 | **0.958 ± 0.042** | **PASS** | 2.580 ± 0.557 | **2.708 ± 0.507** | **PASS** | 19.80 ± 0.80 | 14.75 ± 1.24 |


## Overall Means Across All 590 Clips

- **Noisy Input**: Explicit SNR = 6.21 dB, Active SNR = 6.49 dB, SI-SDR = 6.03 dB, STOI = 0.823, PESQ = 1.600
- **DFN3 Enhanced**: Explicit SNR = 6.31 dB, Active SNR = 7.27 dB, SI-SDR = 8.45 dB, STOI = 0.866, PESQ = 1.798
