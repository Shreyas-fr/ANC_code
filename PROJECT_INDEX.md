# SIH 26052 Project Index

## 1. Canonical Production Model

- **Architecture:** Fine-tuned DeepFilterNet3 (DFN3)
- **Status:** **AUTHORITATIVE CANONICAL CANDIDATE (FROZEN)**
- **Sample Rate:** 48,000 Hz (48 kHz Native)
- **Parameters:** 2,167,969
- **SHA256 Checksum:** `522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe`
- **Specification:** `MODEL.md` and `final_model/FINAL_DFN3_MODEL_INFO.md`
- **Model Checkpoint Path:** `final_model/model.hk`

---

## 2. Validation Benchmarks

### Canonical 590 Validation Set
- **Location:** `runs/sih26052_canonical_validation/`
- **Noisy Input SI-SDR:** 6.03 dB
- **DFN3 Output SI-SDR:** 8.45 dB (+2.42 dB improvement)
- **DFN3 STOI:** 0.866
- **DFN3 PESQ:** 1.798

### Gunfire Subset (IoBT Acoustic Warfare)
- **Noisy Gunfire SI-SDR:** 5.02 dB
- **DFN3 Gunfire SI-SDR:** 8.33 dB (+3.32 dB improvement)
- **Gunfire Improvement Rate:** 78.7%

### Frozen Gold Test (100 Mixtures)
- **Gold Manifest SHA256:** `46236aef9af38056e08f296ac8c498dac888a85fb4b1ff9f371879c49670b0c9`

---

## 3. Raspberry Pi 5 Edge Deployment

- **Location:** `edge/` (and service descriptors in `edge/config/` and `deploy/`)
- **Status:** **DEPLOYED & VALIDATED ON RASPBERRY PI 5 HARDWARE**
- **Validation Run:** 6-minute continuous in-memory concurrent stress test:
  - **Inference Time:** Median **213.2 ms**, Max **424.6 ms** per 500 ms audio block (Single Cortex-A76 thread).
  - **Thermal Profile:** Maximum **60.9 °C** (passive cooling, well under 82 °C throttle limit).
  - **Power Stability:** 4.78V min, 5.03V max on 5V/3A supply; **0x0 throttling events**.
  - **Network Transmission:** 18,737 UDP packets transmitted with **0 packet drops** and max jitter < 0.02 ms.

---

## 4. Operator Frontend GUI

- **Location:** `frontend/`
- **Status:** **PRODUCTION READY / FULLY TESTED**
- **Stack:** PySide6 / Qt GUI with dual-channel real-time spectrum & waveform visualization, circular jitter buffer, and UDP telemetry telemetry parser.
- **Unit Test Suite:** 16 passing tests in `frontend/tests/` (`pytest frontend/tests`).

---

## 5. Non-Canonical Model Experiments

All legacy architectures have been moved to `experiments/` and labeled as research artifacts:
- **Stateful PolarLSTM (16 kHz):** Retired due to persistent 16 ms recurrent state reverberation artifact.
- **Complex CRN:** Retired due to high compute latency (>28 ms/frame) and poor transient suppression.
- **DeepFilterNet3 v2 (Augmented):** Rejected due to source data overlap with validation sets.
- Full details documented in `docs/experiments.md`.

---

## 6. Authoritative Documentation

- `REPORT.md`: Authoritative deliverables, PS target metrics comparison, and claims audit.
- `README.md`: Unified top-level quick start, architecture overview, and project structure.
- `MODEL.md`: Checkpoint SHA256, storage locations, and verification commands.
- `docs/experiments.md`: Experimental architectures, failure analysis, and negative results.
- `CLEANUP_LOG.md`: Step-by-step audit of repository sanitization and restructuring.
