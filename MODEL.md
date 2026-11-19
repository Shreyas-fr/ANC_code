# ANC Model Specifications & Verification Registry (SIH 26052)

**Authoritative Software Baseline:** **B0 Ensemble**  
**Target Hardware:** Embedded Linux / Raspberry Pi 5 (Cortex-A76)  
**Sample Rate:** 16 kHz (MVDR / FullSubNet / GTCRN) and 48 kHz (DFN3 Tract)  
**Status:** Validated Host Software Baseline (Host Measured; Physical Pi 5 Real-Time Validation: **Pending/Unverified**)

---

## 1. Selected Software Baseline: B0 Ensemble

The production software baseline for this project is the **B0 Ensemble**, consisting of a causal dual-microphone MVDR spatial frontend followed by a weighted streaming three-model neural ensemble.

```
Dual-Mic Input [Mic 1, Mic 2] (16 kHz / 48 kHz)
                     │
                     ▼
       ┌───────────────────────────┐
       │   Causal Dual-Mic MVDR    │  Spatial filtering & covariance tracking
       └───────────────────────────┘
                     │
                     ▼ Beamformed Stream
       ┌────────────────────────────────────────────────────────┐
       │             Three-Model Streaming Ensemble             │
       │                                                        │
       │   1. DeepFilterNet3 (DFN3 Step-500)      Weight: 15%   │
       │   2. FullSubNet (Epoch 58)               Weight: 70%   │
       │   3. GTCRN (DNS-3 Pretrained)            Weight: 15%   │
       └────────────────────────────────────────────────────────┘
                     │
                     ▼
            Enhanced Speech Output
```

### Ensemble Performance on Canonical 590 Validation Set [MEASURED ON HOST]
- **SI-SDR:** 13.28 dB
- **Local SNR:** 14.52 dB
- **STOI:** 0.8924
- **PESQ-WB:** 2.220
- **Pass Rates:** >15 dB SNR: 253/590 clips; All 3 thresholds met: 162/590 clips

---

## 2. Checkpoint Verification Registry & Provenance

All model weights for Baseline B0 are frozen and strictly preserved. Their bit-exact SHA-256 checksums and acquisition instructions are detailed below:

| Model Component | Checkpoint File Path | Size (Bytes) | Size (MB) | SHA-256 Checksum | Provenance & Source |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **DFN3 Step-500** | `runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt` | 8,704,788 | 8.30 MB | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` | Fine-tuned DFN3 checkpoint extracted from Raspberry Pi deployment test. Trained on SIH-26 augmented dataset. |
| **FullSubNet (Ep 58)** | `checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar` | 67,669,069 | 64.53 MB | `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0` | FullSubNet best model after 58 training epochs on DNS Challenge dataset. |
| **GTCRN (DNS-3)** | `checkpoints/gtcrn_stage5/model_trained_on_dns3.tar` | 579,819 | 0.55 MB | `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79` | Pretrained GTCRN causal speech enhancement model trained on DNS Challenge 3. |
| **DFN3 Tract Engine** | `models/dfn3_step500_tract.tar.gz` | 7,995,509 | 7.63 MB | `99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d` | Exported Tract ONNX graph bundle optimized for embedded ARM64/NEON inference. |
| **Canonical Manifest** | `runs/sih26052_canonical_validation/manifest.csv` | 141,708 | 0.14 MB | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` | Ground-truth metadata for the 590 canonical evaluation clips. |

---

## 3. Explicit Candidate Disclaimers

### 3.1 Experimental UL-UNAS Package
- The files located in `deploy/pi5/` and the evaluation stages in Stage 11.2.58B-U/V/W/X represent **UL-UNAS experimental deployment exploration**, NOT Software Baseline B0.
- UL-UNAS is an exploratory single-model candidate (IEEE TASLP 2026, Rong et al.). On the 40-speaker independent holdout set, the B0 ensemble outperforms UL-UNAS.
- UL-UNAS is retained for experimental reference only. It does not replace B0.

### 3.2 Real-Time Raspberry Pi 5 Status
- **Host Performance:** Verified and measured on Apple Silicon host.
- **Physical Pi 5 Real-Time Status:** The full three-model B0 ensemble has **NOT** passed physical Raspberry Pi 5 real-time testing. Real-time Pi 5 benchmarks have only been confirmed for the single-model DFN3 Tract engine (RTF $\approx 0.18$). The multi-model ensemble is projected to require optimization or pipelined compute before real-time Pi 5 deployment is achieved.

---

## 4. Instructions for Contributor 2

### Acquiring and Verifying Weights

Because GitHub warns above 50 MB and blocks files above 100 MB, large binary checkpoints are excluded from standard Git tracking via `.gitignore`. Contributor 2 can obtain the model checkpoints from the project release bundle or team cloud storage and place them in the corresponding paths:

```bash
# Verify integrity of all B0 model files:
python -c "
import hashlib, os, sys

checkpoints = [
    ('runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt', 'bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27'),
    ('checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar', '482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0'),
    ('checkpoints/gtcrn_stage5/model_trained_on_dns3.tar', 'a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79'),
    ('models/dfn3_step500_tract.tar.gz', '99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d')
]

all_ok = True
for path, expected in checkpoints:
    if not os.path.exists(path):
        print(f'MISSING: {path}')
        all_ok = False
        continue
    h = hashlib.sha256(open(path, 'rb').read()).hexdigest()
    if h == expected:
        print(f'BIT-EXACT MATCH: {path}')
    else:
        print(f'MISMATCH ({path}): got {h}')
        all_ok = False

if not all_ok:
    sys.exit(1)
print('ALL B0 CHECKPOINTS VERIFIED BIT-EXACT!')
"
```
