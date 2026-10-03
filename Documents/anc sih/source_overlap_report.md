# Source Overlap & Data Leakage Audit Report

**Dataset Audited:** `panavpayappagoudar/sih-26-processed-audio`  
**Dataset Root:** `/Users/shreyasdivekar/.cache/kagglehub/datasets/panavpayappagoudar/sih-26-processed-audio/versions/1`  
**Audit Date:** 2026-10-02 09:31:15  

---

## 1. Executive Summary

A comprehensive duplicate and data leakage audit was conducted across all **122,324 audio files** in the new dataset against all existing SIH project datasets:
* Canonical 590 Validation Set (`runs/sih26052_canonical_validation/`)
* Gold Test 100 Set (`data/SIH_GOLD_TEST/`)
* IoBT Gunfire Dataset (`data/raw_defence/iobt_gunfire/`)
* Project Training Manifests (`data/clean_manifests/`)

---

## 2. Source Overlap Breakdown Table

| SOURCE | NEW DATASET FILES | EXISTING DATASET | OVERLAP TYPE | EVIDENCE | RISK |
| :--- | :---: | :--- | :--- | :--- | :--- |
| Project Filename Matches | `576` | Existing Project Datasets | **FILENAME_MATCH** | Identical file basenames found for 576 files. | HIGH_DATA_LEAKAGE (Resampled or converted copy of project files) |

---

## 3. Provenance Analysis

* **Original Source Datasets Detected in Tree:**
  * LibriSpeech / Speech source clips
  * MUSAN / ESC-50 noise clips
  * Synthetic mixtures generated from existing open-source speech & noise corpuses.
* **Provenance Classification:** **`C. MIXTURES GENERATED FROM EXISTING DATASETS`** (processed copies/combinations of existing open-source speech and noise datasets).
