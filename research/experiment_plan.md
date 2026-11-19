# SIH 26052 Controlled Experiment Plan

**Plan only.** No experiment below is launched by this document. Stages 0–3 are already complete; do not repeat them.

## Shared acceptance rules

- Preserve the Step-500 checkpoint and frozen manifest (SHA-256 `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`). Never inspect the SIH gold test.
- For model comparisons, keep the 590-clip evaluator, metric normalization, sample-rate contract, per-clip state reset and paired comparison methodology unchanged. Record per-clip CSV, summary JSON, target-SNR bins, source-label group summaries, joint-pass count, paired CIs, hashes, environment and exact command.
- Report SNR, SI-SDR, STOI, PESQ-WB and per-clip joint pass. Improvement in one aggregate is not a promotion criterion. Low-SNR results must be visible.
- No training until the authorized source training corpus is available locally and provenance, permissions, exclusions and source-disjoint split integrity are verified. Never upload private corpus/checkpoints to cloud services.
- Any streaming or hardware claim needs its own tests. Model inference time is not end-to-end latency.

## E1 — GTCRN pretrained inference baseline (best next candidate; conditional)

**Question:** Can a small independently pretrained model retain or improve SIH quality while reducing compute cost?

**Gate:** Source revision, license, checkpoint hash, dependencies and input/output contract were inspected; the isolated environment and single-file smoke passed. The full canonical evaluation has completed; see `research/GTCRN_STAGE6_CANONICAL_REPORT.md`. Do not train or promote.

**Method:** Build a thin adapter to the existing evaluator only if its mono waveform and metric contract can be honored without changing scoring. Use fresh state for each clip; preserve alignment and sample count; fail on NaN/Inf. Evaluate all 590 once and compare against Step-500 and FullSubNet epoch 58 with paired 2,000-resample CIs (seed 26052). Record model/checkpoint hashes, parameter count, disk size, CPU wall-clock RTF and process peak RSS. Treat a separate upstream streaming function as a systems test, not as proof from offline file inference.

**Decision:** An improvement claim requires paired evidence and no important low-SNR regression. Deployment remains blocked until target hardware and end-to-end timing are separately approved and tested.

## E2 — FullSubNet streaming feasibility (research only)

No repeat of the offline baseline. Inspect frame dependencies, normalization and state boundaries. The current adapter has two-frame look-ahead and offline Laplace normalization; map algorithmic delay and bounded-state requirements. Determine whether upstream cumulative normalization has a compatible checkpoint and exactly how it changes output. Only with approval, prototype a separate streaming path and compare chunked output to its own offline reference at multiple chunk sizes, including startup/flush and reset behavior. Evaluate quality and latency separately. Do not call a block-size change a streaming conversion.

## E3 — AURA-style distillation (blocked)

Prerequisite: authorized local source corpus, verified provenance, exclusions and speaker/source-disjoint split. Establish compact student baseline first. Compare separately: (1) clean-target loss, (2) DFN3 teacher-output distillation, (3) intermediate features, (4) optional intelligibility-aware term. Use one loss change per run; retain paired clip-level records and report speech preservation and noise amplification as well as canonical metrics. Never train on validation/gold clips. FullSubNet as teacher is a separate later experiment, not mixed into the first ablation.

## E4 — NRSRNet-inspired residual restoration (blocked)

After E3 data gate, begin with frozen Step-500 front end and a bypassable restoration module. Use aligned clean targets from authorized training data. Measure whether restoration recovers speech detail or amplifies residual noise. Track PESQ/STOI/SNR/SI-SDR, per-SNR and per-source strata, speech distortion and noise gain. Require identity/bypass tests and low-SNR review before broader evaluation. Do not use canonical evaluation targets for fitting.

## E5 — Transient-aware enhancement (analysis before modeling)

First define annotated transient events independently of system outputs. For events and speech-overlap, measure detector precision/recall, onset/offset error, false alarms on plosives and non-transient speech, then examine residual noise and speech damage. Existing broad `IoBT_GUNFIRE` origin labels are not event annotations, and high energy is not a gunfire label. A descriptive report can be produced from authorized evaluation material without training, but no threshold/model selection may be tuned on the canonical set while presenting it as untouched validation. No live pipeline change in this plan.

## E6 — Dual-microphone GSC/NLMS (physical evidence blocked)

First require a synchronized physical two-channel set with channel calibration, microphone geometry, reference-noise relation, speech/double-talk regions and clock integrity. Without it, only a clearly labeled synthetic numerical prototype may check algorithm equations; it cannot establish real cancellation. For physical work, test NLMS/GSC, double-talk protection, divergence detection and safe bypass against held-out recordings. Do not integrate with live pipeline in this phase.

## Ordering

1. Stage 4 research documents (completed in this task).
2. After user approval, assess local artifact availability and run E1 only if all gates are met.
3. Separately document FullSubNet streaming feasibility; no Pi access.
4. E5 descriptive transient analysis only when labels/audio access and non-tuning protocol are defined.
5. Keep E3/E4 blocked until the authorized training source is present locally.
6. Keep physical dual-microphone work blocked until synchronized recordings and hardware approval exist.

