# Kaggle run request: V10 replica baseline (R0)

The user has explicitly approved pushing and running V10 R0 on Kaggle. Use the reviewed artifacts:

- Notebook: `antigravity/notebooks/v10/deepfilternet3_v10_r0_sih26052.ipynb`
- Metadata: `antigravity/notebooks/v10/kernel-metadata.json`
- Kernel: `shreyasdivekar/deepfilternet3-v10-sih26052`
- Output: `/kaggle/working/dfn3_v10_r0_sih26052`
- Inputs: the three metadata-attached datasets only.

## Freeze and isolation requirements

- Keep the DeepFilterNet3 upstream v0.5.6 architecture, 48 kHz features, 2,135,484 parameter count, and pretrained initialization. No alternate model, layer, feature, or inference changes.
- Do not mount/read `SIH_GOLD_TEST`. Preserve canonical exclusion filtering and the deterministic source-group split; abort if exclusions, split, GPU, deterministic validation, or finite preflight checks fail.
- The deployed Step-500 checkpoint remains untouched and active. R0 checkpoints are experimental only; no automatic promotion.

## R0 recipe

Run the 1,000-step R0 recipe replica with checkpoints every 50 steps: AdamW, 500-step linear warmup to `1e-5`, cosine decay to `5e-7`, SI-SDR coefficient `0.3`, no MR-STFT, no synthetic RIR, no clipping, speech RMS calibration `[-35,-15] dBFS`, 3-second clips, V3.4 noise-category proportions and SNR distribution. The shuffled dataset uses the V3.4-sized 192,000-index space with sequential modulo speech sampling. R0 is a recipe replica inside the current leakage-safe harness, not an exact historical rerun.

## Artifacts and evaluation

Retrieve the full log, `training_report.json`, and all `.hk`/`.pt` checkpoints into `kaggle_output/dfn3_v10_r0_sih26052/`. Strictly load every `.hk` file and confirm 1,000 updates, checkpoints at steps 50–1,000, matched architecture/parameter count, expected loss and augmentation settings, sampler coverage, exclusions/split evidence, and `gold_test_read: false`.

Evaluate R0 checkpoints on the even-index development subset (295 clips) and compare against Deployed Step-500. The even/odd split is imbalanced, and the odd half is **not an untouched confirmation set** because V4–V9 used the full canonical set. Keep all canonical evaluation as development evidence; reserve SIH gold for one final run after model selection is frozen. If step 500 trails deployed by more than 0.3 dB, halt A1–A5 and investigate the data harness. Do not promote R0 or any later checkpoint based only on internal synthetic validation loss.

Update `CHANGES.md` and `MASTER_SIH_COMPLIANCE.md` with observed run/evaluation evidence only after artifact retrieval. Report failures and missing evidence explicitly.
