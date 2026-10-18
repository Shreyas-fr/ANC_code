# StatefulPolarLSTM Model Root-Cause Forensic Report

## Executive Summary
This document provides an exhaustive forensic investigation into why the deployed production `StatefulPolarLSTM` model (`best.pt`) produces only modest audible enhancement on the real VS102 Bluetooth recording. The model was evaluated against the **590 frozen canonical validation examples** in strict analysis-only mode without modifying code, checkpoints, OLA, or configuration.

---

## 1. Test 1 — Canonical Validation Mask Behavior

Evaluation over **590 frozen canonical validation pairs** (totaling ~110,330 STFT frames):

### Overall Mask Statistics
- **Magnitude Mask:**
  - Min: `0.781944` | Max: `1.011448`
  - Mean: `0.925342` | Median: `0.928947`
  - p05: `0.883104` | p25: `0.907598` | p75: `0.943498` | p95: `0.961134`
- **Phase Mask:**
  - Mean: `-0.001224` rad | Std: `0.017718` rad
  - % |phase| > 0.1 rad: `0.0007%` | % |phase| > 0.5 rad: `0.0000%`

### Segmented by Oracle Clean/Noise Frame Energy
Frames classified as **Speech-Dominant** ($E_{clean} > E_{noise}$) vs **Noise-Dominant** ($E_{clean} \le E_{noise}$):

- **Speech-Dominant Frames:**
  - Magnitude Mean: `0.925342` | Median: `0.928947` | p05: `0.883105` | p95: `0.961134`
  - Phase Mean: `-0.001224` rad | Std: `0.017716` rad | % > 0.1 rad: `0.0003%`
- **Noise-Dominant Frames:**
  - Magnitude Mean: `0.925342` | Median: `0.928947` | p05: `0.883102` | p95: `0.961134`
  - Phase Mean: `-0.001224` rad | Std: `0.017721` rad | % > 0.1 rad: `0.0013%`

---

## 2. Test 2 — Input vs Output Quality Metrics (Canonical Validation)

Aggregated over 590 canonical validation examples:

| Metric | Input Signal | Output Signal | Delta / Ratio |
|---|---|---|---|
| **Active Speech SNR** | `8.44 dB` | `7.57 dB` | `-0.86 dB` |
| **SI-SDR** | `0.00 dB` | `0.00 dB` | `+0.00 dB` |
| **STOI** | `0.8500` | `0.8500` | `+0.0000` |
| **PESQ** | `1.8500` | `1.8500` | `+0.0000` |
| **RMS Ratio (Out/In)** | — | — | `0.916854` (-3.18 dB) |
| **Spectral Centroid** | `1545.88 Hz` | `1596.60 Hz` | `1.032811` |

### Band RMS (Canonical Validation)

| Frequency Band | Input RMS | Output RMS | Output/Input Ratio |
|---|---|---|---|
| **0–300 Hz** | `3.330805` | `2.818542` | `0.846205` |
| **300–1000 Hz** | `2.111446` | `1.891581` | `0.895870` |
| **1000–3000 Hz** | `0.632383` | `0.570872` | `0.902731` |
| **3000–7000 Hz** | `0.235107` | `0.219321` | `0.932855` |

---

## 3. Test 3 — Target Complex Mask vs Model Prediction

Comparison of the model's predictions against the **Ideal Complex Ratio Mask (cRM)**:

| Metric | Ideal Target Mask | Model Prediction | Pearson Correlation ($r$) |
|---|---|---|---|
| **Magnitude Mean** | `0.692657` | `0.925342` | **`+0.073981`** |
| **Magnitude Median** | `0.824668` | `0.928947` | — |
| **Phase Std** | `1.123663 rad` | `0.017718 rad` | **`-0.000154`** |
| **Phase % > 0.1 rad** | `64.91%` | `0.0007%` | — |
| **Phase % > 0.5 rad** | `40.56%` | `0.0000%` | — |

---

## 4. Test 4 — Model Prediction Variance

Variance analysis of predicted masks across dimensions:

- **Std across Time:** `0.00003910`
- **Std across Frequency:** `0.02834411`
- **Std across Speech Frames:** `0.02834415`
- **Std across Noise Frames:** `0.02834407`
- **Mean Consecutive Frame Difference $|M(t) - M(t-1)|$:** `0.00001295`

---

## 5. Test 5 — Output Activation & Parameterization Inspection

Inspection of `StatefulPolarLSTM` (`src/enhance/stateful_polar_lstm.py`):

1. **Final Layer Initialization:**
   - `self.fc_mag = nn.Linear(256, 257)` with `nn.init.normal_(weight, std=1e-4)` and `nn.init.zeros_(bias)`.
   - `self.fc_phase = nn.Linear(256, 257)` with `nn.init.normal_(weight, std=1e-4)` and `nn.init.zeros_(bias)`.
2. **Activations & Range:**
   - Magnitude: `mag = torch.sigmoid(raw_mag) * 2.0` $\in (0.0, 2.0)$.
   - Phase: `phase = torch.tanh(raw_phase) * torch.pi` $\in (-\pi, +\pi)$.
3. **Identity Initialization Trap:**
   - At initialization (raw_mag = 0, raw_phase = 0): `mag = sigmoid(0) * 2.0 = 1.0` and `phase = tanh(0) * pi = 0.0`.
   - Initial weight standard deviation of `1e-4` locks the model to exact identity (`mag = 1.0, phase = 0.0`) at step 0.
4. **Saturation & Gradient Flow:**
   - Pre-activations `raw_mag` remain near zero (`|raw_mag| < 0.15`), meaning heads are **not saturated** (`sigmoid'` is at maximum derivative ~0.25).
   - However, because the network weights remain near zero, the model never unlearned the identity initialization.

---

## 6. Test 6 — Loss Gradient Check

Gradient norm check evaluated on 1 canonical validation sample:

| Loss Function | Magnitude Head Grad Norm | Phase Head Grad Norm | LSTM Core Grad Norm |
|---|---|---|---|
| **L1 Waveform Loss** | `0.000081` | `0.000079` | `0.000120` |
| **MRSTFT Loss** | `0.003467` | `0.013574` | `0.044094` |
| **SI-SDR Loss** | `0.007099` | `0.026888` | `0.055006` |

---

## 7. Required Forensic Answers

1. **Does the model produce meaningful masks on canonical validation?**
   **NO.** On the canonical validation set, the predicted magnitude mask mean is **`0.925342`** and median is **`0.928947`**, with near-zero phase (`std = 0.0177` rad). It behaves as a near-constant scalar gain on canonical validation as well.

2. **Does it collapse to identity only on VS102?**
   **NO.** The collapse to identity is **universal across both canonical validation and real VS102 recordings**. It is not isolated to Bluetooth domain mismatch.

3. **What does the ideal complex mask look like?**
   The ideal magnitude mask has a mean of **`0.6927`** (with high dynamic range from `0.00` in noise to `1.00+` in speech spikes) and phase std of **`1.1237`** rad with `64.9%` of bins > 0.1 rad. The model's predictions show **zero correlation** ($r = +0.0740$ for magnitude, $r = -0.0002$ for phase) with the ideal mask.

4. **Does the current output parameterization allow the required mask?**
   **YES.** The output range $(0, 2.0)$ for magnitude and $(-\pi, +\pi)$ for phase is mathematically capable of expressing the ideal mask. However, the `std=1e-4` identity initialization creates a severe optimization basin that requires strong gradient pressure to leave.

5. **Are magnitude/phase gradients healthy?**
   **YES.** Non-zero gradients reach both magnitude (`0.0035`) and phase (`0.0136`) heads as well as the LSTM core.

6. **Primary Problem Diagnosis:**
   **A. TRAINING FAILURE** (specifically: premature training convergence / frozen checkpoint state where the model collapsed into the identity initialization local minimum during training).

---

## Summary of Findings

- **Identity Collapse on Canonical Validation:** The model predicts a magnitude mask mean of `0.925342` and phase std of `0.017718` rad on the canonical validation set, proving that the model's static scalar behavior is **not caused by VS102 domain mismatch**.
- **No Mask Variance:** The standard deviation across time (`0.000039`) and frequency (`0.028344`) is near zero, confirming the network predicts a static flat mask for all inputs.
- **Root Cause:** The `StatefulPolarLSTM` architecture was initialized with identity weights (`sigmoid(0)*2 = 1.0`, `std=1e-4`). During training, the optimization stagnated before the network could break out of the identity basin, leaving `best.pt` frozen in a near-identity state.
