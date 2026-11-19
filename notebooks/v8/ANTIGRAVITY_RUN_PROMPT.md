# Antigravity run request: V8 SIH 26052

Run the prepared V8 conservative-LR horizon study:

- Notebook: `antigravity/notebooks/v8/deepfilternet3_v8_sih26052.ipynb`
- Metadata: `antigravity/notebooks/v8/kernel-metadata.json`
- Kernel: `shreyasdivekar/deepfilternet3-v8-sih26052`
- Accelerator: dual Tesla T4
- Training: AdamW `lr=1e-6`, 500 steps, checkpoints every 25 steps.

Keep the three existing training, processed-audio, and canonical-exclusions datasets attached. Do not mount or read `SIH_GOLD_TEST`. If GPU/data/exclusion preflight fails, stop and report the error; do not bypass it.

After successful completion, retrieve the run log, training report, and all `.hk`/`.pt` artifacts to `kaggle_output/dfn3_v8_sih26052/`. Strictly load all 20 `.hk` checkpoints with `hk.load_file`; record hashes and verify that the report states the expected optimizer and 500 updates.

Evaluate every checkpoint on the frozen 590-clip benchmark with manifest SHA-256 `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`, fresh model state per clip, and default post-processing. Generate paired per-clip bootstrap comparisons to Deployed Step-500 and pretrained DFN3. Do not promote based on synthetic validation loss alone; keep Deployed Step-500 active unless a V8 checkpoint exceeds it on the frozen benchmark and passes edge gates. Write `antigravity/runs/sih26052_v8_canonical_evaluation/report.md` and update the compliance report from retrieved and evaluated evidence only.
