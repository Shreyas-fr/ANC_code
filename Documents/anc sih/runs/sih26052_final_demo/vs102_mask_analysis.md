# VS102 Real Recording Mask Analysis Report

## Executive Summary
This document analyzes the behavior of the deployed production `StatefulPolarLSTM` model on the real Bluetooth recording `~/sih26052_edge/audio/shreyaswork_input.wav`. The evaluation was conducted in strict analysis-only mode without altering production code, checkpoint weights, OLA implementation, or systemd services.

---

## 1. Overall Mask Statistics

### Magnitude Mask
- **Min:** 0.806550
- **Max:** 0.999545
- **Mean:** 0.925343
- **Median:** 0.928947
- **p05:** 0.883101
- **p25:** 0.907598
- **p75:** 0.943496
- **p95:** 0.961137

### Phase Mask
- **Min:** -0.063912 rad
- **Max:** 0.089984 rad
- **Mean:** -0.001225 rad
- **Std:** 0.017708 rad
- **Percentage of bins with |phase| > 0.1 rad:** 0.0000%
- **Percentage of bins with |phase| > 0.5 rad:** 0.0000%

---

## 2. Segmented Mask Statistics (Speech-Active vs. Background)

**Frame Energy Threshold Used:** Frame RMS = `0.0100` (separates 1,549 high-energy speech-active frames from 2,201 low-energy background frames).

### High-Energy / Speech-Active Frames (N = 1,549, 41.3% of total)
- **Magnitude Mask:**
  - Min: 0.806550 | Max: 0.999545 | Mean: 0.925343 | Median: 0.928948
  - p05: 0.883102 | p25: 0.907598 | p75: 0.943497 | p95: 0.961136
- **Phase Mask:**
  - Min: -0.063912 rad | Max: 0.089984 rad | Mean: -0.001225 rad | Std: 0.017713 rad
  - % |phase| > 0.1 rad: 0.0000% | % |phase| > 0.5 rad: 0.0000%

### Low-Energy / Background Frames (N = 2,201, 58.7% of total)
- **Magnitude Mask:**
  - Min: 0.813310 | Max: 0.999282 | Mean: 0.925343 | Median: 0.928947
  - p05: 0.883101 | p25: 0.907598 | p75: 0.943496 | p95: 0.961138
- **Phase Mask:**
  - Min: -0.044178 rad | Max: 0.051428 rad | Mean: -0.001225 rad | Std: 0.017705 rad
  - % |phase| > 0.1 rad: 0.0000% | % |phase| > 0.5 rad: 0.0000%

---

## 3. Input vs Output Audio Signal Metrics

| Metric | Input Signal | Output Signal | Ratio (Output/Input) |
|---|---|---|---|
| **RMS** | 0.033544 | 0.023251 | 0.693130 (-3.18 dB) |
| **Peak** | 0.999969 | 0.847811 | 0.847837 |
| **Spectral Centroid** | 2077.36 Hz | 2079.45 Hz | 1.001005 |
| **Band RMS (0–300 Hz)** | 0.006208 | 0.004135 | 0.666188 |
| **Band RMS (300–1000 Hz)** | 0.014912 | 0.010250 | 0.687349 |
| **Band RMS (1000–3000 Hz)** | 0.023639 | 0.016346 | 0.691469 |
| **Band RMS (3000–7000 Hz)** | 0.012382 | 0.008775 | 0.708702 |

### Output/Input Energy Ratio
- **Energy Ratio:** `0.480429` (-3.18 dB)

---

## 4. Frequency Band Average Magnitude Masks

| Frequency Band | Overall Avg Mask | High-Energy Avg Mask | Low-Energy Avg Mask |
|---|---|---|---|
| **0–300 Hz** | 0.846129 | 0.846129 | 0.846129 |
| **300–1000 Hz** | 0.894584 | 0.894583 | 0.894584 |
| **1000–3000 Hz** | 0.907274 | 0.907274 | 0.907275 |
| **3000–7000 Hz** | 0.936333 | 0.936333 | 0.936333 |

---

## 5. Diagnosis

**Selected Diagnosis:** **A = model is predicting approximately identity masks**

### Empirical Evidence:
1. **Near-Identity Magnitude Mask:** The model predicts magnitude masks tightly clustered around **0.925** (mean = 0.925343, median = 0.928947, 95% of bins between 0.883 and 0.961). The minimum magnitude mask value across the entire 60-second file is 0.806550, meaning no frequency bin in any frame is ever suppressed by more than ~1.8 dB.
2. **Near-Zero Phase Mask:** The predicted phase mask is zero across the spectrum (mean = -0.001225 rad, std = 0.017708 rad). Exactly **0.0000%** of frequency bins exhibit a phase shift exceeding 0.1 radians.
3. **No Speech vs. Background Discrimination:** The magnitude mask for high-energy speech-active frames (mean = 0.925343) is **identical to 6 decimal places** to the magnitude mask for low-energy background frames (mean = 0.925343). The model applies the exact same scalar attenuation regardless of whether speech is present or absent.
4. **Preserved Spectral Centroid & Uniform Band Attenuation:** The output spectral centroid (2079.45 Hz) is virtually identical to the input spectral centroid (2077.36 Hz). All frequency bands undergo nearly identical scalar reduction (~0.66 to 0.70 RMS ratio).

**Conclusion:** The model acts essentially as a static scalar multiplier (~0.925 gain), failing to dynamically suppress noise or estimate non-trivial complex masks on the real VS102 Bluetooth recording.
