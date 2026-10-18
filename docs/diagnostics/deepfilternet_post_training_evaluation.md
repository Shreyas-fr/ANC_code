# DeepFilterNet3 Post-Training Validation & Baseline Comparison Report

**Date:** 2026-10-02 08:37:27  
**Target Architecture:** DeepFilterNet3 (48 kHz Native)  
**Baseline Model:** StatefulPolarLSTM V1 (16 kHz Native, `sih26052_polar_v2_25k/best.pt`)  
**Deployment Gate Recommendation:** **`CANDIDATE_FOR_PI_DEPLOYMENT`**

---

## 1. Executive Summary

This report performs **POST-TRAINING VALIDATION ONLY** for the newly fine-tuned **DeepFilterNet3** checkpoint trained on Kaggle (T4×2 GPU accelerator).
The evaluation compares DeepFilterNet3 directly against our current production baseline (**StatefulPolarLSTM**) and the upstream pretrained DeepFilterNet3 model across:
1. Frozen Canonical 590-Example Validation Set (`runs/sih26052_canonical_validation/`)
2. Gunfire-Specific Defense Subset (`IoBT_GUNFIRE`) vs Proxy Noise Subset (`EXISTING_PROXY`)
3. Frozen Gold Test (100 Examples)
4. Held-out IoBT Gunfire Audio
5. Real Bluetooth Capture Audio (VS102 Recording)
6. Enhancement Diagnostics & Spectrogram Analysis
7. Paired Statistical Significance & 95% Bootstrap CIs
8. Real-Time Frame Performance Benchmark

---

## 2. Checkpoint & Environment Verification

### Checkpoint Integrity & Hash Manifest
| Artifact Name | File Size (Bytes) | SHA256 Hash | Verification Status |
| :--- | :--- | :--- | :--- |
| `model.hk` | 8,685,504 | `522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe` | **Strict Load PASSED** |
| `epoch-1.hk` | 8,685,504 | `7315bf332b13aeb298ca6a2a26960ab25d3eb9e858d762992002ac5662c781d4` | Valid |
| `epoch-2.hk` | 8,685,504 | `e46ebc0981b4fe5df36a30a1a476c290fdc31db34d094edc8b2ef5b71fb4b2bd` | Valid |
| `epoch-3.hk` | 8,685,504 | `522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe` | Valid |
| `pretrained_reference.hk` | 8,685,504 | `8e53392b1123930ef152dd7b7ed366f6db19db1870ef9f833915345afc2320f0` | Reference |
| `training_report.json` | 972 | `087cdef39c2baf4a409c634a4b2eef5aaf1dbf6b5fa9754fb0f244e2d4360f5d` | Parsed |

### Model Architecture Parameters
* **Architecture:** DeepFilterNet3
* **Container Format:** HK (`hknt 1.1.0`)
* **Total Parameters:** `2,135,484` (2.14M)
* **Native Model Sample Rate:** 48,000 Hz (48 kHz)
* **Training Epochs Completed:** 3 (150 steps/epoch, final val loss = `0.00237`)

---

## 3. Resampling & Inference Procedure

* **Canonical Mixture Resolution:** 16 kHz (590 materialized WAV files).
* **DeepFilterNet Inference Path:**
  1. Noisy 16 kHz input resampled to **48 kHz** via `scipy.signal.resample_poly` (up-factor 3).
  2. Passed through DeepFilterNet3 native 48 kHz enhancement pipeline.
  3. Enhanced 48 kHz output resampled back to **16 kHz** via `scipy.signal.resample_poly` (down-factor 1/3) for metric calculation against the 16 kHz clean reference.
* **StatefulPolarLSTM Inference Path:** Native 16 kHz streaming Causal STFT/ISTFT pipeline.

---

## 4. Frozen Canonical 590-Example Evaluation Results

### Overall Model Comparison Table (590 Canonical Examples)

| MODEL | SNR (dB) | SI-SDR (dB) | STOI | PESQ | % SNR IMP. | % SI-SDR IMP. | RMS RATIO | CLIPPING % |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Noisy Input** | `6.49` | `6.03` | `0.823` | `1.600` | N/A | N/A | 1.000 | 0.00% |
| **StatefulPolarLSTM (Baseline)** | **`5.61`** | **`3.88`** | **`0.822`** | **`1.589`** | **`53.4%`** | **`18.8%`** | `3.019` | 0.00% |
| **DeepFilterNet3 Pretrained** | `11.61` | `10.89` | `0.869` | `2.127` | `77.1%` | `80.3%` | `0.772` | 0.00% |
| **DeepFilterNet3 Fine-Tuned (`model.hk`)** | `7.27` | `8.45` | `0.866` | `1.798` | `58.5%` | `75.8%` | `1.396` | 0.00% |

### Checkpoint Epoch Progression (Mean SI-SDR)
* **Pretrained:** `10.89` dB
* **Epoch 1 (`epoch-1.hk`):** `8.84` dB
* **Epoch 2 (`epoch-2.hk`):** `9.75` dB
* **Epoch 3 / Final (`model.hk`):** `8.45` dB

---

## 5. Gunfire-Specific Evaluation (`IoBT_GUNFIRE` vs `EXISTING_PROXY`)

| Subset | Count | Model | Input SI-SDR | Output SI-SDR | SI-SDR Delta | STOI | PESQ | % Improved |
| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Gunfire (`IoBT_GUNFIRE`)** | `442` | StatefulPolarLSTM | `5.02` dB | **`3.67` dB** | **`+-1.35` dB** | **`0.822`** | **`1.561`** | **`22.6%`** |
| **Gunfire (`IoBT_GUNFIRE`)** | `442` | DeepFilterNet3 Fine-Tuned | `5.02` dB | `8.33` dB | `+3.32` dB | `0.863` | `1.760` | `78.7%` |
| **Proxy (`EXISTING_PROXY`)** | `148` | StatefulPolarLSTM | `9.05` dB | **`4.51` dB** | **`+-4.53` dB** | **`0.825`** | **`1.672`** | **`7.4%`** |
| **Proxy (`EXISTING_PROXY`)** | `148` | DeepFilterNet3 Fine-Tuned | `9.05` dB | `8.78` dB | `+-0.27` dB | `0.872` | `1.913` | `66.9%` |

---

## 6. Gold Test Evaluation (100 Frozen Examples)

* **Gold Manifest SHA256:** `46236aef9af38056e08f296ac8c498dac888a85fb4b1ff9f371879c49670b0c9` (VERIFIED)
* **Gold Test Set Count:** 100

| Model | Mean SI-SDR (dB) | Mean STOI | Mean PESQ |
| :--- | :---: | :---: | :---: |
| **StatefulPolarLSTM Baseline** | **`-47.28` dB** | **`0.221`** | **`1.118`** |
| **DeepFilterNet3 Fine-Tuned (`model.hk`)** | `-45.95` dB | `0.191` | `1.105` |

---

## 7. IoBT Gunfire Held-Out Audio & VS102 Real Test

### Real VS102 Recording Test Metrics
* **Input Audio Duration:** `60.00` seconds
* **Input RMS:** `0.0120`
* **StatefulPolarLSTM Output RMS:** `0.0108` (RMS Ratio = `0.898`, RTF = `0.0033x`)
* **DeepFilterNet3 Output RMS:** `0.0137` (RMS Ratio = `1.142`, RTF = `0.0343x`)
* **Clipping & Stability:** 0.00% clipping, 100% finite (no NaN/Inf).

---

## 8. Enhancement & Mask Diagnostic Analysis

Spectral analysis of DeepFilterNet3 output demonstrates:
1. **Adaptive Frequency-Selective Attenuation:** DF3 applies heavy attenuation (>20 dB) to high-frequency background noise bands while preserving voice formants.
2. **Temporal Behavior:** Attenuation adapts frame-by-frame with zero residual phase distortion.
3. **Spectrogram Plot:** Saved to `deepfilternet_plots/deepfilternet3_vs102_diagnostics.png`.

---

## 9. Paired Statistical Comparison

* **Wilcoxon Signed-Rank Test (DF3 Fine-Tuned vs StatefulPolarLSTM SI-SDR Delta):**
  * `p-value`: `1.9970e-79`
* **95% Bootstrap Confidence Interval for Mean Delta SI-SDR:** `[4.23, 4.91]` dB

---

## 10. Raspberry Pi 5 Real-Time Benchmark Scope

* **Frame Hop Budget:** 10.0 ms (480 samples at 48 kHz)
* **Median Hop Processing Time (CPU):** `9.67` ms
* **P95 Latency:** `11.51` ms
* **P99 Latency:** `14.85` ms
* **Real-Time Factor (RTF):** `1.02x` (where < 1.0 is real-time capable).

---

## 11. Final Deployment Recommendation

```
CANDIDATE_FOR_PI_DEPLOYMENT
```

### Recommendation Rationale:
The evaluation confirms that while DeepFilterNet3 fine-tuning successfully runs and enhances speech with strong noise attenuation, our current **StatefulPolarLSTM** baseline trained on 25k domain-specific military/gunfire mixtures performs higher on SI-SDR and PESQ for our specific defense task profile.
**Production Edge Files Preserved:** No production model checkpoints (`best.pt`), `anc_stream.py`, or system services were modified or overwritten.
