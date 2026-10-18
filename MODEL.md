# Canonical Model Specification: DeepFilterNet3 (Fine-Tuned)

## 1. Overview
The canonical, authoritative model for SIH26052 (DRDO AI Noise Suppression on Raspberry Pi 5) is a fine-tuned **DeepFilterNet3 (DFN3)** neural filter operating at **48 kHz**.

All earlier experiments (Polar-D, Stateful PolarLSTM, Complex CRN) have been retired to `experiments/` due to recursive state feedback artifacts (16 ms acoustic reverberation) and high latency overhead.

---

## 2. Model Metadata & Integrity

| Parameter | Value |
| :--- | :--- |
| **Model Architecture** | DeepFilterNet3 (ERB Filterbank + Deep Complex Filtering) |
| **Sample Rate** | 48,000 Hz (48 kHz) |
| **Trainable Parameters** | 2,135,484 (`sum(p.numel() for p in model.parameters())`) |
| **Model Buffers** | 32,485 (ERB filterbank tables & STFT windows) |
| **Total Checkpoint Tensors** | 2,167,969 (total elements in `model.hk` checkpoint) |
| **Status** | **FROZEN — CANONICAL CANDIDATE** |
| **Binary Checksum (SHA256)** | `522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe` |
| **Weight Format** | `.hk` (Haiku / NumPy binary checkpoint) |

---

## 3. Storage Locations

The model binary `model.hk` (~8.7 MB) is excluded from git version control via `.gitignore` to prevent repository bloat. It resides in the following canonical locations:

- **Local Development / Evaluation**: `final_model/model.hk`
- **Raspberry Pi 5 Target**: `~/sih26052_edge/models/model.hk` (symlinked or referenced as `dfn3_final.hk`)
- **Training Artifact Source**: Kaggle output checkpoint (`deepfilternet3_hknt/model.hk`)

A matching checksum file is stored in `final_model/model.sha256`:
```
522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe  model.hk
```

---

## 4. Verification Instructions

To verify the integrity of the model file before deployment or evaluation, run:

```bash
# Direct SHA256 checksum:
shasum -a 256 final_model/model.hk

# Automated check using checksum file:
cd final_model && shasum -c model.sha256
```

Expected output:
```
522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe  final_model/model.hk
model.hk: OK
```

---

## 5. Architectural & Deployment Characteristics

- **Acoustic Domain**: Complex STFT spectrogram + 32 ERB sub-bands.
- **Deep Complex Filtering (DF)**: Predicts complex filter coefficients per ERB band to restore speech phases without distortion.
- **Pi 5 Deployment Configuration**: 
  - Audio chunking: **500 ms block** with **300 ms past context** (total window 800 ms).
  - Compute latency: Median **213.0 ms**, P95 **236.4 ms**, Max **424.6 ms** per 500 ms block on 1 Cortex-A76 core.
  - End-to-end latency: 500 ms (buffer accumulation) + 213 ms (median compute) = **~713 ms** (in batch-block streaming mode).
  - Algorithmic latency: **~16 ms** (only when operated frame-by-frame with streaming GRU state).
