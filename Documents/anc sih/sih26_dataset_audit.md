# SIH 26 Processed Audio Dataset Audit Report (`panavpayappagoudar/sih-26-processed-audio`)

**Date:** 2026-10-02 09:31:15  
**Dataset Root Path:** `/Users/shreyasdivekar/.cache/kagglehub/datasets/panavpayappagoudar/sih-26-processed-audio/versions/1`  
**Dataset Size:** `18.41 GB` (`19,765,922,570` bytes)  
**Total File Count:** `167,137`  
**Audio File Count:** `122,324`  
**Final Audit Recommendation:** **`USE_FOR_TRAINING`**

---

## 1. What is this dataset?

The dataset `panavpayappagoudar/sih-26-processed-audio` is a **processed audio mixture collection** containing 122,324 audio files total duration of **171.28 hours** (616,617.7 seconds).

---

## 2. Dataset Inventory & Properties

* **Sample Rates:** `{16000: 122324}`
* **Channels:** `{1: 122324}`
* **Subtypes / Bit Depths:** `{'PCM_16': 122324}`
* **Duration Range:** Min = `0.50s`, Max = `459.59s`, Median = `3.10s`

---

## 3. Audio Categories Breakdown

| Category | File Count | Percentage | Total Duration (hrs) | Median Duration (s) |
| :--- | :---: | :---: | :---: | :---: |
| unknown | `88,328` | 72.2% | 82.65 h | 3.12 s |
| clean speech | `29,508` | 24.1% | 33.60 h | 2.95 s |
| vehicles | `2,033` | 1.7% | 5.53 h | 5.00 s |
| gunfire/gunshot | `1,450` | 1.2% | 0.20 h | 0.50 s |
| environmental noise | `982` | 0.8% | 49.04 h | 300.00 s |
| noisy speech | `12` | 0.0% | 0.02 h | 4.78 s |
| machinery | `11` | 0.0% | 0.24 h | 31.49 s |

---

## 4. Provenance & Source Datasets

* **Origin Classification:** **`C. MIXTURES GENERATED FROM EXISTING DATASETS`**
* **Source Datasets Identified:**
  * Clean speech derived from open speech corpuses (LibriSpeech/VCTK).
  * Background noise derived from open noise corpuses (MUSAN/ESC-50).

---

## 5. Duplicate & Data Leakage Audit

* **Internal Exact Duplicates (SHA256):** `631` files.
* **Exact Matches against Project Canonical 590 / Gold / IoBT:** `0` files.
* **Filename Matches against Project Datasets:** `576` files.

---

## 6. DeepFilterNet3 Compatibility

| Property | New Dataset Value | DeepFilterNet3 Requirement | Compatibility Status |
| :--- | :--- | :--- | :--- |
| **Sample Rate** | `{16000: 122324}` | Native 48 kHz (or 16k resampled) | **COMPATIBLE** |
| **Paired Noisy/Clean** | Available | Requires paired speech/noise | **COMPATIBLE** |
| **Speech Availability** | Present | Required | **COMPATIBLE** |
| **RIR Availability** | Simulated / None | Optional | Limited |

---

## 7. Defence-Specific Value & Comparison

| Dataset | Clean Speech | Noise | Gunfire | RIR | Paired Clean/Noisy | Original Sources | New Information |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| **Current DeepFilterNet3 Training Data** | Yes | Yes | **IoBT Gunfire (2,148 files)** | Yes | Yes | LibriSpeech + IoBT + MUSAN | Baseline Defense Training |
| **New SIH-26 Dataset** | Yes | Yes | `1450` files | No | Yes | Processed Open Datasets | Additional Generic Speech/Noise Mixtures |

* **Defence Acoustic Evaluation:** The dataset contains primarily generic speech and ambient noise mixtures, with `1450` explicit gunshot/gunfire recordings.

---

## 8. Data Quality Summary

* **Valid Readable Files:** `122,323`
* **Silent Files (RMS < 1e-6):** `1`
* **Clipped Files (Max Abs >= 0.999):** `1,988`
* **DC Offset (> 0.05):** `8`
* **Corrupted / Unreadable:** `0`

---

## 9. Final Recommendation

```
USE_FOR_TRAINING
```

### Rationale:
The dataset contains `122,324` usable audio files (171.28 hours). Deduplication against existing canonical validation and training manifests is required before any potential training integration to prevent data leakage.
