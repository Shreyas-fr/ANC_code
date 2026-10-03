# DeepFilterNet3 V2 Deduplication & Data Integrity Report

**Date:** 2026-10-02 09:34:53  
**Raw Kaggle Dataset Entries:** `122,324`  
**Deduplicated Entries Remaining:** `122,324`  
**Target Manifest:** `DFN3_V2_SIH_DEFENCE_AUGMENTED_manifest.csv`  

---

## 1. Deduplication Breakdown

* **Total Raw Entries:** `122,324`
* **Excluded Filename Overlaps with Existing Project:** `0`
* **Excluded Exact SHA256 Leakage Matches:** `0`
* **Excluded Internal Duplicate SHA256 Matches:** `0`
* **Final Retained Unique Entries:** `122,324`

---

## 2. Deduplicated Category Distribution

| Category | File Count | Percentage of V2 Dataset | Role in Training Mixture |
| :--- | :---: | :---: | :--- |
| **Clean Speech (VCTK)** | `88,328` | `72.2%` | Clean Speech Source |
| **Clean Speech (LibriSpeech)** | `5,323` | `4.4%` | Clean Speech Source |
| **Complex Noisy Speech (MS-SNSD)** | `24,374` | `19.9%` | Noisy Speech Mixture Source |
| **Vehicle Engine Noise** | `2,000` | `1.6%` | **Defence Vehicle Noise** |
| **Firearms / Gunshot Audio** | `1,450` | `1.2%` | **Defence Impulsive Gunfire** |
| **Environmental Noise (DEMAND)** | `576` | `0.5%` | Background Environmental Noise |
| **Drone Audio** | `273` | `0.2%` | **Defence Aerial Drone Noise** |

---

## 3. Data Leakage Verification

* **Canonical 590 Validation Set (`runs/sih26052_canonical_validation/`):** **`0` matches** (Verified 100% disjoint)
* **Gold Test Set 100 (`data/SIH_GOLD_TEST/`):** **`0` matches** (Verified 100% disjoint)
* **Held-out IoBT Gunfire Test Split:** **`0` matches** (Verified 100% disjoint)
