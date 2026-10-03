# SIH 26052 Project Index

## Current Model

Fine-tuned DeepFilterNet3
Status: AUTHORITATIVE CANDIDATE (FROZEN)
Sample rate: 48 kHz
Parameters: 2,167,969 (Exact verified: 2,167,969 parameters)
SHA256: 522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe
Location: `runs/final_model/model.hk` and `kaggle_output/deepfilternet3_hknt/model.hk`

## Validation Benchmarks

### Canonical 590 Validation Set
Location: `runs/sih26052_canonical_validation/`
Noisy SI-SDR: 6.03 dB
DFN3 SI-SDR:  8.45 dB (+2.42 dB improvement)
DFN3 STOI:    0.866
DFN3 PESQ:    1.798

### Gold Test (100 Frozen Mixtures)
Location: `data/SIH_GOLD_TEST/`
Gold Manifest SHA256: 46236aef9af38056e08f296ac8c498dac888a85fb4b1ff9f371879c49670b0c9

### Gunfire Subset (IoBT)
Noisy Gunfire SI-SDR: 5.02 dB
DFN3 Gunfire SI-SDR:  8.33 dB (+3.32 dB improvement)
Gunfire Improvement Rate: 78.7%

## Model Experiments

### PolarLSTM
Location: `runs/experiments/polar_lstm/` and `antigravity/runs/sih26052_polar_v2_25k/`
Status: Baseline 16 kHz model preserved for comparative research.

### DeepFilterNet3 Initial Fine-Tuning
Location: `kaggle_output/deepfilternet3_hknt/`
Status: AUTHORITATIVE BASELINE CANDIDATE.

### DeepFilterNet3 V2 Defence-Augmented
Location: `runs/experiments/dfn3_v2_rejected/`
Status: REJECTED (`V2_NOT_BETTER_THAN_CURRENT`). Retained as research provenance.

## PC Frontend

Location: `frontend/`
Status: Built / PySide6 GUI with UDP streaming and real-time visualization. Awaiting Pi hardware connection.

## Raspberry Pi Deployment

Location: `sih26052_edge/`
Status: NOT CONNECTED YET. No DFN3 deployment performed on Pi. Production PolarLSTM service preserved intact.

## Important Reports & Audit Artifacts

- `FINAL_DFN3_MODEL_INFO.md` — Authoritative model specification and SHA256
- `cleanup_plan.md` — Safe project cleanup execution report
- `dfn3_v2_training_report.md` — V2 training & comparative evaluation report
- `deepfilternet_post_training_evaluation.md` — Comprehensive baseline model benchmark report
- `sih26_dataset_audit.md` — Kaggle dataset inventory and provenance audit
- `model_root_cause_report.md` — Root cause investigation report

## Next Step

Connect Raspberry Pi hardware and perform isolated DFN3 deployment and benchmarking only after hardware is available.
