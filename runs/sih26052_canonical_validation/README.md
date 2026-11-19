# Canonical V2 Validation Set (Frozen)

## Overview
The frozen canonical validation benchmark for SIH26052. It has 590 mixtures: 442 from the IoBT gunfire set and 148 from the existing proxy set, at target SNRs from -10 to +20 dB (30 at -10, 63 at -5, 117 at 0, 137 at 5, 121 at 10, 86 at 15, 36 at 20). Audio is stored at 16 kHz, 48000 samples (3 s) per clip. Per-clip source IDs are not recorded in the manifest (the source ID columns are N/A).

## Dataset Manifest & Integrity
- **Manifest**: `manifest.csv` (590 examples with ground truth speech and noise metadata).
- **Validation Dataset Hash**: `validation_dataset_hash.txt`.

## How to Regenerate or Evaluate
- To regenerate the mixture dataset: Run `python scripts/freeze_canonical_val.py` or use `scripts/dynamic_mixer.py --is_val=True`.
- To run canonical evaluation on a candidate model:
  ```bash
  python eval/evaluate.py --model <path_to_model> --manifest runs/sih26052_canonical_validation/manifest.csv
  ```
