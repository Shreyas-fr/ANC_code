# DeepFilterNet3 V2 Training & Comparative Evaluation Report

**Date:** 2026-10-02 11:27:44  
**Target Architecture:** DeepFilterNet3 V2 (48 kHz Native)  
**Baseline Model:** Current Fine-Tuned DeepFilterNet3 (`kaggle_output/deepfilternet3_hknt/model.hk`)  
**Final Decision:** **`V2_NOT_BETTER_THAN_CURRENT`**

---

## 1. Executive Summary

This report presents the authoritative evaluation of **DeepFilterNet3 V2**, fine-tuned on Kaggle GPU using the newly audited, deduplicated defence-augmented dataset (`DFN3_V2_SIH_DEFENCE_AUGMENTED_manifest.csv`).

---

## 2. Model Checkpoint & SHA256 Verification

* **Best V2 Checkpoint:** `model_v2_best.hk`
* **SHA256 Hash:** `592112570596bde39bcac2f18df34edeebb14dada3aa8124b13c47e5a495ef20`
* **HK Round-Trip Check:** **PASSED STRICTLY**

---

## 3. Canonical 590 Validation Performance

| Model | Mean SNR (dB) | Mean SI-SDR (dB) | SI-SDR Delta vs Input | % SI-SDR Improved |
| :--- | :---: | :---: | :---: | :---: |
| **Noisy Input** | `6.49` | `6.03` | 0.00 dB | N/A |
| **Current Fine-Tuned DFN3 (`model.hk`)** | `7.27` | `8.45` | `+2.42` dB | `75.8%` |
| **New DeepFilterNet3 V2 (`model_v2_best.hk`)** | **`1.33`** | **`4.97`** | **`+-1.06` dB** | **`52.7%`** |

---

## 4. Gunfire Subset Performance (`IoBT_GUNFIRE`)

| Model | Input SI-SDR | Output SI-SDR | SI-SDR Delta | % Improved |
| :--- | :---: | :---: | :---: | :---: |
| **Current Fine-Tuned DFN3 (`model.hk`)** | `5.02` dB | `8.33` dB | `+3.32` dB | `78.7%` |
| **New DeepFilterNet3 V2 (`model_v2_best.hk`)** | `5.02` dB | **`4.94` dB** | **`+-0.08` dB** | **`54.1%`** |

---

## 5. Gold Test Performance (100 Frozen Examples)

* **Gold Manifest SHA256:** `46236aef9af38056e08f296ac8c498dac888a85fb4b1ff9f371879c49670b0c9` (VERIFIED)
* **Current Fine-Tuned DFN3 Mean SI-SDR:** `-46.00` dB
* **New DeepFilterNet3 V2 Mean SI-SDR:** `-46.27` dB

---

## 6. Paired Statistical Tests (V2 vs Current DFN3)

* **Wilcoxon Signed-Rank Test p-value:** `5.4941e-80`
* **95% Bootstrap Confidence Interval for Mean Delta SI-SDR (V2 - V1):** `[-3.75, -3.22]` dB

---

## 7. Final Recommendation

```
V2_NOT_BETTER_THAN_CURRENT
```

### Production Guardrails:
* Zero production files (`sih26052_edge/models/best.pt`, `anc_stream.py`, system services) were modified or replaced.
