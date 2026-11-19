# SIH 26052: evidence-led plan to close the speech-enhancement gap

**Updated:** 2026-11-13  
**Status:** V6–V9 completed and evaluated; V10 experiment brief prepared, but no V10 run or outcome is claimed.  
**Selection rule:** Keep `SIH_GOLD_TEST` unmounted and unread. Use the existing frozen 590-clip set as the current development/model-selection benchmark, while recognizing that repeated comparisons make it unsuitable as an independent final test.

## What the project results say

The current deployed Step-500 checkpoint is the strongest candidate measured so far (13.47 dB output SNR, 0.885 STOI, 2.232 PESQ-WB, 161/590 joint passes). The full-set target gaps are 1.53 dB SNR and 0.268 PESQ-WB. V4 and V5 then showed a strong training/selection mismatch: synthetic validation loss improved through step 3,000 while canonical quality peaked early and deteriorated. V5's target-aligned RIR change barely improved V4.

Reviewing the executed V5 notebook exposed a specific data-sampling defect shared with V4. `train_ds` has length 7,200 and `clean` is selected with `self.speech[i % len(self.speech)]`. The V5 run had 85,950 eligible training speech rows, but each pass through the 7,200-item dataset selected only metadata rows 0–7,199. Repeated passes changed crops/noise, but never selected the other training speech rows. This can narrow speaker/content diversity and is the first controlled change to make. V6 randomizes the speech-row selection from the whole already split training pool and logs how many distinct rows it sampled. It preserves V5's model, loss, optimizer, RIR/clipping policy, noise/SNR sampler, source exclusions, and validation construction so the main causal change is the speech-row sampler.

## Evidence from external work

1. The official DeepFilterNet repository supports constructing separate speech/noise/RIR datasets and training through its `df/train.py` pipeline. The project uses a custom training notebook instead, so dataset sampling and validation behavior need explicit audits. [DeepFilterNet training documentation](https://github.com/Rikorose/DeepFilterNet#training)
2. Microsoft's DNS research found that broader, continuous SNR sampling and level diversity can improve regularization, but level augmentation must be paired with loss normalization to avoid degrading results. This supports a later controlled SNR/level ablation, not changing everything in the first follow-up. [Braun & Tashev, *Data Augmentation and Loss Normalization for Deep Noise Suppression*](https://arxiv.org/abs/2008.06412)
3. The Microsoft DNS repository provides a proven clean/noise/RIR synthesis pipeline and checksum lists, but its current fullband corpus is very large (the README lists hundreds of GB of clean speech and noise). Use it only if a small, licensed and relevant subset can be staged; it is generic communication noise, not a replacement for artillery/armored-vehicle recordings. [Microsoft DNS Challenge repository](https://github.com/microsoft/DNS-Challenge)
4. MAD is an accessible military-event resource with gunshot, shelling/explosion, vehicle, helicopter, fighter, and speech classes, but its paper describes an audio-classification dataset extracted from videos, not aligned clean/noisy speech enhancement pairs. Treat verified noise-only excerpts as candidate augmentation after VAD/manual review; the paper's CC-BY license applies to the article, and third-party/source-video rights must be checked independently before redistribution or use. [MAD paper and data records](https://www.nature.com/articles/s41597-024-03511-w), [authors' GitHub repository](https://github.com/kaen2891/military_audio_dataset)
5. A learned PESQ surrogate has shown a PESQ gain in a specific published experiment, but that does not establish improvement on this project's noise mix or SNR. It should be a later small ablation after sampling/generalization is improved, with STOI/SNR guardrails and listening checks. [IEEE Signal Processing Society summary of Quality-Net](https://signalprocessingsociety.org/publications-resources/ieee-signal-processing-letters/2021/01/learning-learned-loss-function-speech-enhancement-quality-net-improve-perceptual-evaluation-speech)

## Experiment sequence

### V6: fix speech coverage only — completed, sampler hypothesis rejected as primary cause

- Notebook: `notebooks/v6/deepfilternet3_v6_sih26052.ipynb`.
- Keep the V5 optimizer (`AdamW`, `1e-5`), objective, augmentation, source split, dataset size, and fixed validation set.
- Sample a random training speech row on each dataset access. Keep validation speech sampling deterministic.
- Log unique speech-row count to the run report.
- Stop at 1,500 steps and save every 250 steps to reveal early degradation more clearly than the V4/V5 500-step schedule.
- Evaluate checkpoints 250–1,500 locally on all 590 canonical clips with the existing pinned manifest and identical model path. Compare paired per-clip deltas against deployed Step-500 and pretrained DFN3. Promote nothing based on internal synthetic loss alone.

**Observed:** V6 sampled 20,961 distinct speech rows from 85,950 eligible rows across 1,500 steps. Despite that coverage, `step-250.hk` scored 9.34 dB SNR / 1.706 PESQ-WB / 7.1% joint pass; its paired deltas versus deployed Step-500 were −4.13 dB SNR and −0.526 PESQ-WB (95% CIs excluded zero). SNR then declined monotonically to 6.71 dB at step 1,500 while synthetic validation loss fell from 1.2141 to 1.1066. The narrow sampler was real, but fixing it did not solve the canonical regression. No V6 checkpoint is promoted. Full results are in `sih26052_v6_canonical_evaluation/report.md`.

### V7: conservative learning-rate ablation — completed

- Notebook: `notebooks/v7/deepfilternet3_v7_sih26052.ipynb`; run report: `sih26052_v7_canonical_evaluation/report.md`.
- It held V6's full-pool sampler, data, losses, augmentation, validation, and initialization fixed; AdamW LR was lowered from `1e-5` to `1e-6`.
- Canonical metrics rose through step 250. The best V7 checkpoint reached 12.71 dB SNR, 0.869 STOI, 2.154 PESQ-WB, and 147/590 joint passes. It beat pretrained DFN3 but trailed deployed Step-500 by 0.75 dB SNR and 0.079 PESQ-WB (paired 95% CIs exclude zero). V7 stopped at step 250 per its run instruction; no checkpoint was promoted.
- This supports the conclusion that LR `1e-5` caused much of the earlier destructive drift, but it does not prove LR is the only issue.

### V8: extend conservative-LR horizon — completed

- Notebook/run evidence: `notebooks/v8/deepfilternet3_v8_sih26052.ipynb`, `runs/sih26052_v8_canonical_evaluation/report.md`.
- Extending the V7 `1e-6` recipe through 500 steps improved SNR/SI-SDR/STOI through step 475 (`12.98 dB`, `11.65 dB`, `0.876`), but PESQ and joint pass peaked at step 225 (`2.154`, `148/590 = 25.1%`) then declined. Every V8 checkpoint still trailed deployed Step-500; no promotion.

### V9: remove mixture-only clipping — completed, clipping rejected as primary cause

- Notebook: `notebooks/v9/deepfilternet3_v9_sih26052.ipynb`; run report: `runs/sih26052_v9_canonical_evaluation/report.md`.
- Held V8's `1e-6` LR, 500-step horizon, full-pool sampler (`7,629` distinct rows sampled), exclusions, source-group split, RIR, and loss fixed; set `microphone_clipping_probability = 0.0`.
- **Observed:** Removing clipping slightly helped early perceptual quality (peak PESQ-WB `2.166` at `step-300.hk` vs V8 `2.154` at step 225; peak joint pass `148/590 = 25.1%` at `step-250.hk`). However, the fundamental tradeoff persisted: SNR/SI-SDR/STOI peaked late at `step-475.hk` (`12.97 dB` SNR, `11.69 dB` SI-SDR, `0.876` STOI) while PESQ dropped to `2.124` by step 500 despite falling validation loss (`1.3289`). Every V9 checkpoint trailed Deployed Step-500 on all four metrics (paired 95% CIs below zero). No V9 checkpoint is promoted.

### Prioritized next ablation: continuous SNR sampling & sequence-level loss normalization

Because neither speech pool coverage (V6) nor mixture clipping (V9) resolved the gap to Deployed Step-500:
1. **Continuous SNR & Level Normalization (V10 priority):** Replace the 7 discrete SNR points (`[-10, -5, 0, 5, 10, 15, 20]` dB) with continuous uniform sampling across `[-10, +20]` dB, paired with sequence-level loss normalization to prevent high-energy mixture gradients from dominating learning (supported by Braun & Tashev, Microsoft DNS).
2. **Layer-constrained fine-tuning:** Test freezing early convolutional / feature extraction layers or adding an L2 penalty to pretrained weights to prevent encoder drift while adapting higher-level spectral masking.

### V10 preparation (not yet run)

The V9 result did not meet the goal, so V10 is planned to test continuous SNR sampling and sequence-level active-speech loss normalization together, motivated by Braun & Tashev's published DNS study. The paired intervention is intended to prevent level-dependent losses from over-weighting high-energy sequences while broadening SNR exposure; that paper is evidence for testing the method, not evidence that it will improve this SIH benchmark.

The V10 run brief is `notebooks/v10/ANTIGRAVITY_RUN_PROMPT.md`. It explicitly freezes DeepFilterNet3's architecture, upstream implementation, feature configuration, and deployed Step-500 checkpoint. Fine-tuned weights are experimental only. No alternate model from GitHub/Hugging Face is being substituted. The run must be prepared and evaluated on the canonical development benchmark before any promotion decision; SIH gold stays isolated. [Braun & Tashev, Microsoft Research](https://www.microsoft.com/en-us/research/publication/data-augmentation-and-loss-normalization-for-deep-noise-suppression/).

1. **Conservative fine-tuning with layer constraints:** V7/V8 established `lr=1e-6` as better than `1e-5`; if V9 does not close the gap, test freezing selected early layers or an explicit penalty toward pretrained weights. Compare against V9 at matched optimizer steps.
2. **SNR/level distribution:** replace the seven discrete SNR values with continuous sampling (initial range -10 to +20 dB), then normalize level-dependent waveform losses at sequence level. Keep a separate categorical report by SNR so gains on easier conditions cannot conceal low-SNR harm.
3. **Perceptual refinement:** only after acoustic generalization improves, test a differentiable PESQ surrogate or metric-guided fine-tune with a small weight and explicit SNR/STOI floors. Do not optimize PESQ directly on the same frozen benchmark used to report the final result.
4. **Noise data:** use real recorded target-domain noise, group-split by original recording/video/session, VAD-screen to remove embedded speech, and verify source rights. MAD can help fill event classes, but classification-only clips are not paired speech targets and its public paper does not grant blanket rights to every source video.

## Model promotion and reporting gates

- No V4/V5 model is promoted; the deployed Step-500 candidate remains the baseline.
- A candidate must improve the paired canonical comparison and satisfy the project's defined means and per-clip pass reporting. Report each SNR bin and source class; do not hide severe-condition regressions in an aggregate.
- Validate real-time inference and listening quality after model selection. The current Pi evidence has late fallbacks in the five-minute stream and has no headset playback/end-to-end delay result.
- Keep the gold set sealed until the architecture, checkpoint, inference parameters, and deployment configuration are frozen. Only then run one final authorized gold evaluation.

