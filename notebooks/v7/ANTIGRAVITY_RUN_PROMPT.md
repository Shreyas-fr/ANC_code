# Antigravity run request: V7 SIH 26052

Run the locally prepared controlled ablation:

- Notebook: `antigravity/notebooks/v7/deepfilternet3_v7_sih26052.ipynb`
- Kaggle metadata: `antigravity/notebooks/v7/kernel-metadata.json`
- Kernel: `shreyasdivekar/deepfilternet3-v7-sih26052`
- Expected accelerator: dual Tesla T4
- Expected changes from V6: AdamW learning rate only changes from `1e-5` to `1e-6`; stop at 250 steps and save checkpoints every 25 steps.

## Required run procedure

1. Push the exact V7 notebook and metadata. Confirm that the three existing training, processed-audio, and canonical-exclusion datasets remain attached and that GPU T4×2 is enabled.
2. Run the notebook to completion. If setup, data validation, or GPU preflight fails, stop and report the exact failure; do not bypass source exclusions or substitute missing data.
3. Confirm the run report shows `gold_test_read: false`, 85,950 eligible train speech rows, V6 random full-pool speech sampling, `lr=1e-6`, 250 optimizer steps, and finite/nonzero training losses. Retrieve the log, report, and every `.hk`/`.pt` checkpoint to `kaggle_output/dfn3_v7_sih26052/`.
4. Verify each `.hk` checkpoint loads strictly with `hk.load_file`; record hashes and confirm optimizer steps at 25, 50, 75, 100, 125, 150, 175, 200, 225, and 250.
5. Evaluate all ten checkpoints on the local frozen 590-clip canonical benchmark using the established evaluator, fresh DeepFilterNet3 state per clip, manifest SHA-256 `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`, and default post-processing. Compare each with both Deployed Step-500 and the pretrained reference using paired per-clip bootstrap results.
6. Do not promote a checkpoint based on synthetic validation loss. If every early checkpoint is materially worse than the deployed model, stop the experiment; do not spend more steps extending V7.
7. Write `antigravity/runs/sih26052_v7_canonical_evaluation/report.md` with exact metrics, paired confidence intervals, hashes, training controls, and limitations. Update `antigravity/MASTER_SIH_COMPLIANCE.md` only from retrieved and locally evaluated evidence. Keep the SIH gold set unmounted and unread throughout.

