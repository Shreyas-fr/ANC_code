# SIH 26052 Research Status

**As of:** 2026-11-13 · **Authorized stage:** Stage 6 GTCRN canonical evaluation · **Decision:** Stage 6 complete; Step-500 stays protected, and stop for user review before further experiments.

## Current system and benchmark

The protected active reference is single-channel DeepFilterNet3 Step-500, checkpoint SHA-256 `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27`. It remains unchanged and is not promoted or replaced here. The frozen canonical validation manifest has 590 mono 16 kHz pairs and SHA-256 `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`. The SIH gold test has not been accessed.

| Model / evidence | Output SNR | SI-SDR | STOI | PESQ-WB | Joint pass (SNR>15, STOI>.85, PESQ>2.5) |
|---|---:|---:|---:|---:|---:|
| Deployed Step-500, reproduced | 13.467 dB | 12.363 dB | .8847 | 2.2323 | 161/590 (27.3%) |
| FullSubNet official epoch 58, offline | 14.904 dB | 13.700 dB | .9026 | 2.5133 | 218/590 (36.9%) |

FullSubNet's paired difference from Step-500 has 95% bootstrap CIs above zero on all four metrics, but its mean SNR remains below 15 dB; the full SIH target is not met. It was CPU-evaluated offline, with two-frame look-ahead and offline normalization. There is no evidence here that it is a live or Pi replacement.

FullSubNet source-label analysis finds positive paired mean changes in both `EXISTING_PROXY` (n=148) and `IoBT_GUNFIRE` (n=442). Those source labels are uneven across input-SNR levels and do not annotate transient events. The hardest low-SNR joint-pass rates remain 0/30 at -10 dB and 2/63 at -5 dB for FullSubNet; Step-500 gives 0/30 and 3/63. The pattern is consistent with single-channel speech/noise overlap, suppression of weak speech cues, residual transient interference and domain mix, but those factors have not been causally separated.

## Phases

| Stage | Status | Evidence / boundary |
|---|---|---|
| 0 Repository audit | Complete | `docs/CODEX_REPOSITORY_AUDIT.md`; nested repo baseline HEAD `242e24c6fd803729314a5636d63ae0be235ce2e4`; preserve pre-existing working tree. |
| 1 Baseline reproduction | Passed | `docs/BASELINE_REPRODUCTION.md`; CSV byte-identical to reference. |
| 2 FullSubNet offline baseline | Passed for offline comparison | `docs/FULLSUBNET_BASELINE.md`; no promotion or streaming claim. |
| 3 R0 three-seed variation | Complete | `docs/V10_R0_SEED_VARIATION.md`; at steps 300/500/550/800 full-set SNR is 13.579±.060 / 13.686±.099 / 13.626±.114 / 13.661±.022 dB. Three-seed SD is a rough screen, not a confidence interval; no sustained post-550 collapse. |
| 4 External model research / implementation audit | Complete in this task | Six documents under `research/` plus FullSubNet source-label section appended. No model evaluation/training was launched. |
| 5 GTCRN pretrained inference | Environment and one-file smoke passed | `research/GTCRN_STAGE5_SMOKE_REPORT.md`; official source pinned, DNS3 checkpoint hashed, strict load passed. |
| 6 GTCRN canonical inference evaluation | Complete (590/590) | `research/GTCRN_STAGE6_CANONICAL_REPORT.md`; lower than FullSubNet on all four metrics, no promotion. Step-500 and manifest hashes unchanged. |
| 6b FullSubNet streaming feasibility | Proposed research only | Current evaluated path has offline Laplace normalization and two-frame look-ahead. A different cumulative-normalization variant would be a separate operating point. No stream test or Pi measurement made here. |
| 7 Transient analysis | Proposed, protocol needed | Existing labels are not event annotations. Need event onset/offset, speech overlap, false alarms on plosives and a no-tuning protocol. |
| 8 AURA distillation | Blocked | No authorized source-level training audio locally; no training initiated. |
| 9 Residual restoration | Blocked | Same data gate; no official runnable NRSRNet implementation/checkpoint verified. |
| 10 Dual-microphone ANC | Blocked for physical validation | No verified synchronized physical dual-channel dataset. Single-channel DFN3 is not reference-mic ANC. |
| 11 Unified pipeline | Deferred | Individual stream/model stages have not passed independent gates. |
| 12 Raspberry Pi validation | Not performed | No Pi access or deployment authorized. |

## External implementation audit

- **GTCRN:** Official MIT source pinned at `502ebfab64da7c4a9af78dcb9c6ceef1ebb01c73`; only `gtcrn.py`, `LICENSE`, and `requirements.txt` were fetched. Official DNS3 checkpoint is present with SHA-256 recorded in `research/GTCRN_STAGE5_SMOKE_REPORT.md`. Isolated Python 3.10.22/PyTorch 1.11.0 environment and one-file smoke passed. The 590-clip report is complete at `research/GTCRN_STAGE6_CANONICAL_REPORT.md`; all four paired metric CIs vs FullSubNet are below zero. The SIH model-benchmarks repository's small four-condition construction-noise report is not canonical-comparable and its visible runner does not reproduce the GTCRN results.
- **Project AURA:** README self-reports compact CRN distillation and quantization work. Its code/checkpoint behavior was not fully inspected; README mentions speaker overlap in a pair-level split, and its Pi claim is planned rather than measured. Treat its quality/latency values as unverified project claims.
- **FullSubNet:** Local pinned MIT source, config, adapter and official epoch-58 checkpoint were inspected and evaluated. Current evaluated path is offline and look-ahead; no Pi or headset evidence.
- **NRSRNet:** Paper proposes two-stage reduction/restoration. No author-owned runnable repo/checkpoint was verified; parameter count, sample rate, latency and training recipe details remain unverified.
- **DRDO-ANC:** Public README is self-report; its exploration does not establish a synchronized physical reference-mic path in this workspace.

## Data and integrity gates

The authorized source-level training audio is unavailable locally. Therefore no further training or distillation can proceed. Do not substitute canonical evaluation audio for training, use gold, upload data/checkpoints/notebooks, access Kaggle, or access/modify the Pi under this task. Stage 5 fetched only the approved official GTCRN source files and DNS3 checkpoint into the isolated project paths. No existing model, checkpoint, manifest, or evaluator was modified; two new evaluation-only scripts were added. The pre-existing dirty/untracked worktree was preserved; no commit was created.

## Best next experiment

GTCRN E1 is complete; see `research/GTCRN_STAGE6_CANONICAL_REPORT.md`. Stop for review before any further experiment. FullSubNet remains the strongest completed offline comparison; Step-500 remains the protected deployed candidate.

## Research and evaluation reports

- `research/model_research_assessment.md`
- `research/experiment_plan.md`
- `research/reproducibility_register.md`
- `research/external_repository_audit.md`
- `research/implementation_gap_analysis.md`
- `research/next_steps.md`
- `research/SIH26052_RESEARCH_STATUS.md`
- `docs/FULLSUBNET_BASELINE.md` (append-only source-label results section)

**Stage 6 completed. Await user review before any further experiment.**
