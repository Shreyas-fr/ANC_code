# Contributor Collaboration Guide

This guide establishes the shared development and execution protocols for both team contributors working on the SIH 26052 Speech Enhancement codebase.

---

## 1. Quick Onboarding Checklist for Contributor 2

1. **Clone the Git Repository:**
   ```bash
   git clone https://github.com/Shreyas-fr/ANC_code.git
   cd ANC_code
   ```

2. **Set Up Python Environment:**
   ```bash
   python3 -m venv pc_venv
   source pc_venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Verify Installation & Imports:**
   ```bash
   python -c "import torch, torchaudio, onnxruntime, pystoi, pesq, soundfile; print('Core dependencies OK!')"
   ```

---

## 2. Managing Model Weights & Checkpoints

Because GitHub limits standard Git file sizes to 100 MB and warns at 50 MB, large binary checkpoints are excluded from Git commits via `.gitignore`.

### Required Checkpoints for Software Baseline B0:

| Checkpoint Name | Local File Location | Size | Required Checksum (SHA-256) |
| :--- | :--- | :---: | :--- |
| **DFN3 Step-500** | `runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt` | 8.30 MB | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` |
| **FullSubNet (Ep 58)** | `checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar` | 64.53 MB | `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0` |
| **GTCRN (DNS-3)** | `checkpoints/gtcrn_stage5/model_trained_on_dns3.tar` | 0.55 MB | `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79` |
| **Tract Engine** | `models/dfn3_step500_tract.tar.gz` | 7.63 MB | `99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d` |

### Checkpoint Verification Script:
Run the following command to verify your local model weights match the verified baseline bit-exact:
```bash
python -c "
import hashlib, os
def check(path, expected):
    if not os.path.exists(path):
        print(f'MISSING: {path}'); return
    h = hashlib.sha256(open(path, 'rb').read()).hexdigest()
    print(f'{\"MATCH\" if h == expected else \"MISMATCH\"}: {path}')

check('runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt', 'bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27')
check('checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar', '482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0')
check('checkpoints/gtcrn_stage5/model_trained_on_dns3.tar', 'a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79')
"
```

---

## 3. Dataset Policy & Handling

- **Development Datasets:**
  - `runs/sih26052_canonical_validation/` (590 canonical evaluation clips)
  - `data/track1_independent_200/` (200-clip independent development set)
  - `data/multichannel_30mm/` (30mm mic-spacing spatial test recordings)
- **Sealed Evaluation Dataset:**
  - `data/SIH_GOLD_TEST/` is strictly sealed. Do NOT copy, read, decode, or score it.

---

## 4. Hardware Deployment Targets

1. **Development Host:**
   - Apple Silicon (M-series) / Linux x86_64 for rapid prototyping, offline benchmarking, and model training.
2. **Target Edge Device:**
   - Raspberry Pi 5 (Quad-core Broadcom BCM2712 Cortex-A76 @ 2.4 GHz).
   - Low latency budget: Frame size $\le 32\text{ ms}$, Hop size $\le 16\text{ ms}$.
   - End-to-end processing RTF must remain $< 0.5$ on Pi 5.
