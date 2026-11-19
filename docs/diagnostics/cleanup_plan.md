# SIH 26052 Project Cleanup Plan

**Date:** 2026-10-02  
**Initial Workspace Size:** `79.51 GB` (`81,414.07 MB`)  
**Post-Cleanup Workspace Size:** `79.13 GB` (`81,028.29 MB`)  
**Status:** **EXECUTED SAFELY (ZERO DATA LOSS)**

---

## 1. Inventory & Classification Matrix

| Path | Category / Description | Proposed Action | Executed Status | Rationale |
| :--- | :--- | :---: | :---: | :--- |
| `kaggle_output/deepfilternet3_hknt/model.hk` | Authoritative Fine-Tuned DFN3 Model | **KEEP** | **VERIFIED & FROZEN** | Authoritative model candidate (`8.45 dB` SI-SDR). |
| `runs/final_model/` | Frozen Model Archive Directory | **KEEP** | **CREATED & POPULATED** | Stores `model.hk`, `model.sha256`, and `FINAL_DFN3_MODEL_INFO.md`. |
| `final_model/` | Protected Model Root Folder | **KEEP** | **CREATED & POPULATED** | Duplicate root folder for frozen model reference. |
| `runs/sih26052_canonical_validation/` | Frozen Canonical 590 Validation Set | **KEEP** | **UNTOUCHED** | Authoritative 590-mixture validation dataset. |
| `data/SIH_GOLD_TEST/` | Frozen Gold Test Set (100 Mixtures) | **KEEP** | **UNTOUCHED** | Authoritative 100-mixture Gold test benchmark. |
| `runs/experiments/dfn3_v2_rejected/` | Rejected V2 Experiment Archive | **ARCHIVE** | **POPULATED** | Contains V2 model, training report, manifests, dedup report & `README.md`. |
| `runs/experiments/polar_lstm/` | PolarLSTM Research History | **KEEP** | **PRESERVED** | Preserves prior PolarLSTM model weights, logs, and diagnostic reports. |
| `runs/experiments/logs_archive/` | Historical Diagnostic Text Logs | **ARCHIVE** | **ARCHIVED (85 files)** | Consolidated 85 loose `diag*.txt`, `bt_*.txt`, and test log outputs. |
| `sih26052_edge/` | Raspberry Pi Production Code & Service | **KEEP** | **UNTOUCHED** | Protected edge deployment code, models, and service scripts. |
| `frontend/` | PC Frontend Application Codebase | **KEEP** | **UNTOUCHED** | Protected PySide6 PC frontend application. |
| `antigravity/` | Core Project Engine & Manifests | **KEEP** | **UNTOUCHED** | Preserves core scripts, dataset manifests, and evaluation code. |
| `__pycache__/` & `*.pyc` | Python Compilation Caches | **DELETE** | **DELETED (2,096 dirs)** | Temporary compiled python bytecode (`385.77 MB` freed). |

---

## 2. Safety & Verification Summary

* **Authoritative Model Integrity:** SHA256 `522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe` verified strictly.
* **Validation & Evidence Protection:** Canonical 590 set, Gold Test 100, dataset manifests, and provenance reports are 100% intact.
* **Raspberry Pi Guardrail:** Zero files modified under `sih26052_edge/`. Pi remains untouched.
