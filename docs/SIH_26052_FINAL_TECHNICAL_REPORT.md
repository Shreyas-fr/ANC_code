# SIH 26052 — Evidence-Based Technical Status

**Prepared:** 2026-11-13  
**Repository:** `antigravity`, baseline Git HEAD `242e24c6fd803729314a5636d63ae0be235ce2e4` (working tree has pre-existing modifications and untracked artifacts).  
**Scope:** Phases 0–2 completed in this work; subsequent stages stopped at the specified data-availability gate. This is a status report, not a claim that the full system is complete.

## Executive status

The deployed DeepFilterNet3 Step-500 remains the active candidate. Its canonical reproduction exactly matches the saved per-clip reference on the frozen 590-clip set. The official pretrained FullSubNet comparison improves all four aggregate means and has paired bootstrap intervals above zero on this development benchmark, but it still misses the full-set mean SNR target and has no validated streaming or Pi path. Neither model meets every requested per-clip quality condition. No checkpoint was promoted and no Pi service was changed.

Low-SNR behavior is localized and reproducible. At target input SNR `-10 dB`, Step-500 averaged `6.56 dB` output SNR, `0.677` STOI, and `1.386` PESQ-WB; at `-5 dB`, these were `9.95 dB`, `0.804`, and `1.689`. FullSubNet improved these bins but still had 0/30 and 2/63 joint passes. The likely technical explanation is that, when speech is much weaker than noise, one microphone provides an ambiguous mixture and speech/noise occupy overlapping time-frequency regions. Suppression can lower error energy while deleting or distorting weak phonetic cues and leaving transient noise. These metrics support this explanation but do not isolate it as the sole cause; low-SNR cases are also heavily concentrated in gunfire-labeled clips.

## Verified benchmark results

Manifest SHA-256: `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`. Checkpoint selected for deployment: `runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt`, SHA-256 `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27`.

| Candidate | Output SNR | SI-SDR | STOI | PESQ-WB | Joint pass |
|---|---:|---:|---:|---:|---:|
| Deployed DFN3 Step-500 | 13.467 dB | 12.363 dB | 0.8847 | 2.2323 | 161/590 (27.3%) |
| Official FullSubNet epoch 58 | 14.904 dB | 13.700 dB | 0.9026 | 2.5133 | 218/590 (36.9%) |

For FullSubNet minus deployed Step-500, paired 2,000-resample CIs with seed 26052 were: SNR `+1.437 [1.181, 1.705] dB`; SI-SDR `+1.337 [1.059, 1.625] dB`; STOI `+0.0179 [0.0144, 0.0217]`; PESQ-WB `+0.2811 [0.2487, 0.3162]`. The full-set mean SNR is still under `15 dB`; therefore the system does not meet the complete SIH numeric target.

FullSubNet artifacts and seven input-SNR-bin table are documented in `docs/FULLSUBNET_BASELINE.md` and `runs/fullsubnet_baseline/`. The exact reproduced Step-500 result and low-SNR bins are documented in `docs/BASELINE_REPRODUCTION.md` and `runs/sih26052_candidate_step500_repro_20261113/`.

## Phase status and blockers

| Phase | Status | Evidence / limitation |
|---|---|---|
| 0. Repository audit | Complete | `docs/CODEX_REPOSITORY_AUDIT.md`; gold content was not read. |
| 1. Baseline/evaluator | Passed | 590 rows and frozen manifest hash; reproduced per-clip CSV checksum `9b27038fb21b9d15e7066b2324372c4471abab2247989ea1da65922888a2366f`; paired deltas exactly zero against saved reference. |
| 2. FullSubNet baseline | Passed offline | Adapter smoke and full canonical run exit 0. Evaluation was CPU-only; official model is offline/look-ahead and has no demonstrated streaming or Pi suitability. |
| 3. Low-SNR training | R0 three-seed noise floor complete; E2/E3 experiments blocked | Seed-26053/26054 checkpoints, logs, and canonical CSVs are now present locally and were included in `scripts/evaluate_v10_r0_seeds.py` (exit 0). See `docs/V10_R0_SEED_VARIATION.md`. Actual source-level training audio is still unavailable in this workspace. The plan prohibits uploading private data/notebooks/checkpoints and says to stop if required data is unavailable. No E2/E3 training or Kaggle operation was performed. |
| 4. Residual restoration | Not started | Depends on source-group training/validation audio that is unavailable locally and Phase 3 evidence. |
| 5. Dual-microphone ANC | Not started | No synchronized real two-channel recordings or test setup verified. Synthetic tests alone would not prove real ANC; sequential phase gate was not bypassed. |
| 6. Unified streaming pipeline | Not started | Must wait for individual stages to pass; FullSubNet's offline normalization/look-ahead is not a streaming-ready replacement. Existing Step-500 path remains untouched. |
| 7. Pi deployment/validation | Not run in this work | No Pi connection was made. Existing report describes a streaming prototype; current live state, actual mic-to-headphone latency, headset playback, and soak results were not revalidated. |
| 8. Evidence package | Status report produced; final acceptance remains open | This report, traceability, experiment register, and deployment-status document record what is and is not evidenced. |

## Three-seed noise-floor result

The full-set R0 mean ± sample SD across seeds 26052/26053/26054 is: step 300 SNR `13.579 ± 0.060 dB`, SI-SDR `12.416 ± 0.097 dB`, STOI `0.8878 ± 0.0014`, PESQ-WB `2.229 ± 0.007`; step 500 `13.686 ± 0.099`, `12.563 ± 0.086`, `0.8877 ± 0.0009`, `2.230 ± 0.007`; step 550 `13.626 ± 0.114`, `12.477 ± 0.135`, `0.8856 ± 0.0020`, `2.221 ± 0.020`; step 800 `13.661 ± 0.022`, `12.532 ± 0.040`, `0.8859 ± 0.0013`, `2.224 ± 0.019`. Full even/odd splits and joint pass counts are in `docs/V10_R0_SEED_VARIATION.md`. The 550–800 trajectory does not show a sustained collapse. The seed-26052 single-run Step-550 bump is not a robust gain across seeds.

## Safe next action

Make the authorized training corpus available locally, with exclusion/split integrity, before running E2 or E3; neither should be submitted to Kaggle or another external service. If that cannot be done without violating the no-upload rule, leave Phase 3–6 blocked and continue only with documentation or data-access planning. Keep the gold set sealed and Step-500 deployed.
