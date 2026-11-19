# SIH 26052: Dual-Microphone Speech Enhancement & Noise Cancellation

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Baseline: B0 Ensemble](https://img.shields.io/badge/Baseline-B0%20Ensemble-green.svg)](#software-baseline-b0)

Real-time, edge-deployable speech enhancement system developed for Smart India Hackathon (SIH 26052). The project targets non-stationary, high-noise environments (defense, tactical, vehicular, and industrial) utilizing dual-microphone spatial filtering combined with low-latency deep neural network streaming ensembles.

---

## 1. Selected Software Baseline: B0 Ensemble

The authoritative, validated production software baseline for this project is the **B0 Ensemble**.

### Architecture Overview

```
Dual-Mic Input [Mic 1, Mic 2]
         │
         ▼
 ┌─────────────────────────────────┐
 │ Causal MVDR Spatial Frontend    │ (Steering vector calibration & covariance tracking)
 └─────────────────────────────────┘
         │
         ▼ Beamformed Mono Stream
 ┌────────────────────────────────────────────────────────┐
 │ Three-Model Streaming Neural Ensemble                  │
 │                                                        │
 │  ├─ DeepFilterNet3 (DFN3 Step-500)       [Weight: 15%] │
 │  ├─ FullSubNet (Epoch 58)                [Weight: 70%] │
 │  └─ GTCRN (DNS-3 Pretrained)             [Weight: 15%] │
 └────────────────────────────────────────────────────────┘
         │
         ▼
 Enhanced Speech Output
```

### Verified Baseline Components & Checksums

All baseline checkpoints are frozen and verified bit-exact via SHA-256:

| Component | Path | Size | SHA-256 Checksum |
| :--- | :--- | :---: | :--- |
| **DFN3 Step-500** | `runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt` | 8.30 MB | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` |
| **FullSubNet (Ep 58)** | `checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar` | 64.53 MB | `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0` |
| **GTCRN (DNS-3)** | `checkpoints/gtcrn_stage5/model_trained_on_dns3.tar` | 0.55 MB | `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79` |
| **Tract Engine Export**| `models/dfn3_step500_tract.tar.gz` | 7.63 MB | `99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d` |
| **Canonical 590 Manifest**| `runs/sih26052_canonical_validation/manifest.csv` | 0.14 MB | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` |

---

## 2. Critical Architectural Distinction: B0 vs. UL-UNAS

> [!IMPORTANT]
> **Production Baseline vs. Experimental Candidate:**
> - **B0 Ensemble** is the validated software baseline.
> - The files located in `deploy/pi5/` and evaluated in Stages 11.2.58B-U through 11.2.58B-X represent **UL-UNAS experimental deployment files**, NOT Software Baseline B0.
> - UL-UNAS is an exploratory single-model candidate under research evaluation. It does not replace B0.

---

## 3. Repository Structure

```
.
├── configs/            # Configuration files for training, inference, and beamforming
├── docs/               # Technical documentation, latency models, and mathematical proofs
├── MASTER_SIH_COMPLIANCE.md # Authoritative compliance log and verification registry
├── models/             # Model architectures and exported Tract/ONNX engines
├── notebooks/          # Exploratory research and diagnostic analysis notebooks
├── research/           # Research papers, survey logs, and theoretical derivations
├── runs/               # Validation run logs, evaluation metrics, and canonical manifests
├── scripts/            # Evaluation runners, diagnostic tools, and export scripts
├── src/
│   ├── enhance/        # Core neural enhancement models and stateful wrappers
│   ├── audio/          # STFT, feature extraction, and audio I/O pipelines
│   └── beamformer/     # Causal MVDR and spatial covariance estimators
├── tests/              # Unit tests and regression test suites
└── third_party/        # Third-party implementations (FullSubNet, DeepFilterNet, GTCRN)
```

---

## 4. Getting Started

### Prerequisites
- Python 3.10+ (tested on Python 3.10, 3.11, and 3.14)
- Libsndfile & FFmpeg
- (Optional for Tract/Rust inference) Rust toolchain (`cargo`, `rustc`)

### Environment Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Shreyas-fr/ANC_code.git
   cd ANC_code
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv pc_venv
   source pc_venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

### Running Inference & Verification

To verify the B0 ensemble components against the canonical validation set:
```bash
python scripts/evaluate_dfn3_canonical.py
```

To run offline dual-microphone enhancement:
```bash
python scripts/run_full_evaluation.py
```

---

## 5. Governance & Integrity Rules

1. **`GOLD_TEST_READ = NO`**:
   The gold test set (`data/SIH_GOLD_TEST/`) is strictly sealed and protected. No automated script, evaluation harness, or contributor may read, decode, hash, or score against it during active development.
2. **Deterministic Checkpoint Integrity**:
   Frozen checkpoints in `runs/` and `checkpoints/` must not be retrained, modified, or overwritten.
3. **Collaboration Protocol**:
   Please review [CONTRIBUTING.md](CONTRIBUTING.md) and [COLLABORATION.md](COLLABORATION.md) before submitting code.
