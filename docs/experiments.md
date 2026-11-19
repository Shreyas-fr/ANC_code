# SIH26052 Architecture Experiments & Provenance

## 1. Overview
This document records the experimental neural network architectures, adaptive filtering baselines, and ablation studies explored during project SIH26052 prior to freezing **DeepFilterNet3 (48 kHz)** as the canonical production candidate.

All models in this document are categorized as **NON-CANONICAL EXPERIMENTAL ARTIFACTS**. Their training logs, configuration YAMLs, and evaluation reports are preserved under `experiments/`.

---

## 2. Experimental Architecture 1: Polar-D / Stateful PolarLSTM

### Model Description
- **Native Sample Rate:** 16,000 Hz (16 kHz)
- **Parameters:** ~1,448,962 (1.45M)
- **Mechanism:** Causal STFT (window 512, hop 256 / 16 ms) parameterizing a polar complex mask via magnitude compression and phase angle correction through recurrent LSTM layers.
- **Artifacts:** `src/enhance/stateful_polar_lstm.py`, `experiments/runs/sih26052_polar_v2_25k/`.

### Findings & Root Cause Analysis
- **Acoustic Reverberation Artifact:** In continuous 60-second live audio streaming tests on the Raspberry Pi 5, the model exhibited a pronounced, audible 16.00 ms reverberant echo (cross-correlation peak at 16 ms with correlation coefficient 26.54).
- **Root Cause:** Persistent recurrent LSTM hidden states carried forward previous frame speech energy across continuous block boundaries without exponential decay, bleeding phonetic envelopes into subsequent quiet frames.
- **Outcome:** **RETIRED**. The model was deemed unusable for defense communications due to degradation of speech intelligibility under conversational speech.

---

## 3. Experimental Architecture 2: Complex CRN (Convolutional Recurrent Network)

### Model Description
- **Native Sample Rate:** 16 kHz
- **Mechanism:** Complex STFT encoder-decoder with 2D convolutional encoder layers, bidirectional LSTM bottleneck, and complex transposed convolutional decoder layers predicting complex ratio masks.
- **Artifacts:** `src/enhance/complex_crn.py`, `experiments/runs/sih26052_baseline/`.

### Findings
- **High Compute Overhead:** Processing a single 16 ms frame required >28 ms on a single Cortex-A76 core of the Raspberry Pi 5, causing massive deadline misses and buffer overflow in real-time streaming.
- **Impulsive Noise Inability:** In impulsive noise evaluation (`eval/evaluate_impulsive.py`), the model failed on sudden transients (gunfire, muzzle blasts, explosions). In a 400 ms burst window around impulses, SI-SDR degraded from 19.9 dB to 14.7 dB at -5 dB input SNR, actively attenuating speech consonants.
- **Outcome:** **RETIRED**.

---

## 4. Experimental Model 3: DeepFilterNet3 v2 (Defence-Augmented)

### Model Description
- Attempted to augment the initial DeepFilterNet3 checkpoint by fine-tuning on defense noise datasets (IoBT gunfire, artillery, engine rumblings).
- **Artifacts:** `experiments/dfn3_v2_rejected/`.

### Findings & Audit
- Rigorous source verification and deduplication audits (`docs/diagnostics/source_overlap_report.md` and `docs/diagnostics/dedup_report.md`) revealed source data leakage between the newly ingested training splits and the canonical validation clips.
- When evaluated on strictly held-out non-overlapping gold test sets, DFN3 v2 did not outperform the initial fine-tuned DFN3 candidate.
- **Outcome:** **REJECTED (`V2_NOT_BETTER_THAN_CURRENT`)** to preserve audit validity and prevent test-set contamination.

---

## 5. Negative Result: Adaptive NLMS Post-Filter on Single-Channel Audio

### Implementation
- Implemented in `deploy/nlms_postfilter.py` as an adaptive Normalized Least Mean Squares (NLMS) filter in series after the neural enhancement stage.
- **Mode A (Single Mic):** Synthesized noise reference by subtracting neural enhanced output from the raw input: $d(t) = \text{raw}(t) - \text{enhanced}(t)$.

### Experimental Results
- Tested across 50 samples at 5 dB SNR.
- **Result:** Adding the NLMS post-filter in series **consistently degraded** SI-SDR compared to the standalone neural model (exact delta not recorded).
- **Reason:** In single-microphone operation, the estimated noise reference from the neural network contains residual speech leakage and phase distortion. The NLMS filter treats this speech energy as noise and aggressively cancels legitimate voice formants.
- **Outcome:** Documented as an explicit **NEGATIVE RESULT**. Mode B (true dual-microphone acoustic reference path) remains architecturally supported in code but untested due to lack of multi-channel hardware recordings.

---

## 6. Training Loss & Sampling Ablations Summary

| Run Directory | Study Focus | Key Takeaway |
| :--- | :--- | :--- |
| `experiments/runs/sih26052_loss_ablation/` | Multi-Res STFT vs L1 Loss | Multi-resolution spectral loss is critical to prevent spectral hole-punching. |
| `experiments/runs/sih26052_sisdr_loss_25k/` | Direct SI-SDR Optimization | Time-domain SI-SDR loss alone causes phase jitter without ERB band weighting. |
| `experiments/runs/sih26052_sampling_ablation/` | Gunfire Heavy vs Mixed 50 | 50/50 mix of speech and impulsive noise stabilizes GRU hidden states. |
| `experiments/runs/sih26052_small_overfit/` | Overfit Diagnostic | Validated backpropagation gradients and network capacity. |
