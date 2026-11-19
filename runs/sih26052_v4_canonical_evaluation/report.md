# SIH26052 DeepFilterNet3 V4 Training and Canonical Evaluation

**Evaluation date:** 2026-11-12  
**Training run:** `deepfilternet3-v4-sih26052-compliance-retraining`  
**Evaluation set:** frozen 590-clip canonical benchmark; manifest SHA-256 `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`

## Training evidence

The retrieved Kaggle log records 3,000 optimizer steps on dual Tesla T4 GPUs, validation every 500 steps, and `.hk` plus `.pt` checkpoint writes through step 3,000. The training report records an internal best validation loss of 1.10954 at step 3,000. The executed loss was complex L1 + 0.25 magnitude L1 + 0.01 SI-SDR loss + 0.2 multi-resolution STFT. Augmentation used synthetic reverberation (20%) and microphone clipping (15%). Feature state was reset before every waveform. Canonical exclusions were loaded before splitting: 3,686 exclusion rows matched and removed 333 metadata rows. Remaining rows were split by source groups. The report declares `gold_test_read: false`.

Runtime fixes in the completed run addressed the Python/NumPy RNG mismatch, Linux HK serialization, and missing JSON import. Training and validation sample preflights passed. The retrieved artifacts and log are under `kaggle_output/dfn3_v4_sih26052/`.

## Canonical model selection

All six saved optimizer checkpoints were evaluated with fresh libDF feature state on every clip. Each summary records the same frozen manifest hash above. No attenuation limit or post-gain was applied.

| Checkpoint | Mean output SNR (dB) | Mean SI-SDR (dB) | Mean STOI | Mean PESQ-WB | Clips passing all three |
|---|---:|---:|---:|---:|---:|
| Step 500 | 11.42 | 9.67 | 0.863 | 1.739 | 41/590 (6.9%) |
| Step 1000 | 10.52 | 8.36 | 0.833 | 1.594 | 34/590 (5.8%) |
| Step 1500 | 8.91 | 7.05 | 0.828 | 1.580 | 30/590 (5.1%) |
| Step 2000 | 7.42 | 4.71 | 0.796 | 1.458 | 18/590 (3.1%) |
| Step 2500 | 6.13 | 2.73 | 0.759 | 1.331 | 9/590 (1.5%) |
| Step 3000 / best internal validation | 4.81 | 0.60 | 0.725 | 1.295 | 5/590 (0.8%) |

V4 step 500 is the best of its checkpoints on this benchmark, but misses the overall mean SNR target (>15 dB) and PESQ-WB target (>2.5); it narrowly exceeds the STOI target (>0.85). It also underperforms the existing deployed DeepFilterNet3 Step-500 candidate on all four canonical means (13.47 dB SNR, 12.36 dB SI-SDR, 0.885 STOI, 2.232 PESQ-WB). Therefore, V4 is not selected for deployment. The existing Step-500 candidate remains the strongest measured full-distribution model, and it too does not meet all three full-set targets.

The sharp metric decline after step 500 shows that minimizing the internal training/validation loss did not select for the frozen dry canonical benchmark. The synthetic room-response branch is a plausible source of objective mismatch, but this evaluation alone does not establish causation. Further training should first align augmentation and target acoustics with the intended deployment distribution, then use the canonical benchmark only for checkpoint/model selection. Do not tune repeatedly against the frozen benchmark and present it as an independent test set.

## Reproduction

From `antigravity/`, run the following for each checkpoint, changing `step-NNNN` as needed:

```bash
../pc_venv/bin/python scripts/evaluate_dfn3_canonical.py \
  --checkpoint ../kaggle_output/dfn3_v4_sih26052/dfn3_v4_sih26052/step-500.hk \
  --output-dir ../kaggle_output/dfn3_v4_sih26052/canonical_eval_step500
```

Full per-clip metrics and summaries are in `kaggle_output/dfn3_v4_sih26052/canonical_eval_step*/` and `canonical_eval_best/`. The local evaluator emitted a SciPy/NumPy version compatibility warning; the checkpoint outputs were nevertheless produced for all 590 clips. Preserve that caveat when reproducing locally.
