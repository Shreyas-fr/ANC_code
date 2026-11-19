# Antigravity run request: V9 SIH 26052 clipping ablation

Run the prepared V9 ablation:

- Notebook: `antigravity/notebooks/v9/deepfilternet3_v9_sih26052.ipynb`
- Metadata: `antigravity/notebooks/v9/kernel-metadata.json`
- Kaggle kernel: `shreyasdivekar/deepfilternet3-v9-sih26052`
- Accelerator: dual Tesla T4
- Training: 500 steps, AdamW `lr=1e-6`, checkpoint every 25 steps; mixture-only clipping probability 0.

Keep the same training, processed-audio, and canonical-exclusions datasets attached. Confirm exclusions and source-group split before training. Do not mount/read `SIH_GOLD_TEST`. Stop if any preflight fails; do not bypass it.

Retrieve the run log, report, and all `.hk`/`.pt` checkpoints to `kaggle_output/dfn3_v9_sih26052/`. Verify all 21 `.hk` files strictly with `hk.load_file` and `load_state_dict(strict=True)`, confirm 500 updates, the 0 clipping probability, sampled speech row count, and `gold_test_read: false`.

Run `evaluate_dfn3_canonical.py` for every 25-step checkpoint on the frozen 590-clip benchmark, manifest SHA-256 `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`, using fresh state per clip and default post-processing. Produce paired bootstrap comparisons to Deployed Step-500 and pretrained DFN3. Do not promote based only on synthetic validation loss. Keep Deployed Step-500 unless V9 beats it on the frozen benchmark and passes edge gates. Save a truthful report under `antigravity/runs/sih26052_v9_canonical_evaluation/report.md` and update `MASTER_SIH_COMPLIANCE.md` only after retrieval/evaluation.
