# Next Steps — SIH 26052

**Current gate:** Stage 6 canonical evaluation is complete. Stop and wait for user review before any further experiment.

## Recommended next experiment

**E1: GTCRN pretrained inference-only canonical baseline** — completed; see `research/GTCRN_STAGE6_CANONICAL_REPORT.md`.

Why this is the best next information gain: GTCRN has an official lightweight implementation and the upstream repository lists pretrained checkpoints and a stream path. This could compare quality and computational footprint without committing scarce project training data. It addresses both the current low-SNR quality limit and future edge efficiency. Its public SIH four-condition construction-noise results are not sufficient evidence, and upstream CPU timing does not establish Pi suitability.

The official source and DNS3 checkpoint are pinned and locally hashed; the isolated environment passed import, strict load and one-file smoke, and the full canonical comparison is complete. Review the Stage 6 report. Do not upload private audio or train a replacement.

## Future work (requires separate review/approval)

- FullSubNet streaming feasibility: static review first; any streaming prototype needs separate tests for look-ahead, normalization, state reset, chunk boundaries, latency and quality. No Pi access is authorized.
- Transient failure analysis: requires an event annotation and non-tuning protocol; existing source labels are not transient-event labels.
- AURA distillation and NRSRNet-inspired restoration: remain blocked until the authorized source corpus is locally available with verified provenance and a leakage-safe split.
- Physical dual-microphone ANC: remains blocked until synchronized physical two-channel recordings and hardware validation are authorized.

## Continue to protect

- Active reference remains Step-500 with SHA-256 `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27`.
- Do not change the canonical manifest or evaluator silently.
- Do not access the gold test, upload private data, start training, access Kaggle, or touch the Pi under this task.
- Do not claim the SIH `>15 dB` output-SNR target or full system requirements are achieved. FullSubNet is the strongest completed offline comparison only.
