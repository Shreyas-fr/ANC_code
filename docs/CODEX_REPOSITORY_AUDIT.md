# SIH 26052 Repository Audit

**Audit date:** 2026-11-13  
**Scope:** Read-only Phase 0 inventory of the current workspace and the nested `antigravity/` Git repository.  
**Repository commit at audit:** `242e24c6fd803729314a5636d63ae0be235ce2e4` (`chore: remove stale edge audit logs and update .gitignore`).  
**Disposition:** Audit complete. No training, Kaggle operation, deployment operation, or gold-set access was performed for this audit.

## 1. Repository shape and working-tree state

- The workspace directory `/Users/shreyasdivekar/Documents/anc sih` is **not itself a Git repository**. The project Git repository is `/Users/shreyasdivekar/Documents/anc sih/antigravity`.
- The `antigravity` repository is on `main`, one commit ahead of `origin/main` at the audited commit.
- The working tree is substantially dirty: `REPORT.md` and `system_diagrams.md` are modified, and many run reports, notebooks, scripts, presentation files, and audit directories are untracked. The audit did not stage, revert, or rewrite anything. Before future implementation, preserve this state and inspect `git status`; do not use reset/clean or overwrite current work.
- The workspace contains both a legacy project layout at its root and the versioned `antigravity/` project. Use the latter as the code/repository root unless a file is explicitly documented as an external artifact (for example, downloaded Kaggle outputs under workspace-root `kaggle_output/`).

## 2. Existing working components

### DeepFilterNet3 and experiment artifacts

- The currently selected candidate is the fine-tuned DeepFilterNet3 Step-500 artifact copied from the Pi at `runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt`. Its SHA-256 is `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27`.
- A canonical full-set evaluation summary exists at `runs/sih26052_dfn3_canonical_step500/summary.json`. It reports 590 clips, mean output SNR `13.46698 dB`, SI-SDR `12.36288 dB`, STOI `0.88469`, PESQ-WB `2.23229`, and 161/590 joint passes (27.29%). These remain below the full-distribution SNR and PESQ targets.
- The frozen manifest at `runs/sih26052_canonical_validation/manifest.csv` hashes to `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`. The corresponding local canonical clean/noisy audio directories and per-example evaluation artifacts exist.
- DeepFilterNet3 V4–V10 checkpoints and canonical-evaluation outputs are present under workspace-root `kaggle_output/`. V10 R0 includes all 20 step checkpoints (50–1,000), per-clip CSVs, and summaries. The V10 R0 Step-500 `.hk` file is a distinct artifact (SHA-256 `57fedd5b608bb7a82e85c7573b0f921f427546a0321cc948182cb1c5695ba40c`) and is not the deployed Step-500 checkpoint.
- V10 R0 report and compliance notes state `gold_test_read: false`, no promotion, and that the deployed candidate remains active. The R0 result is near baseline; it does not satisfy the full-set SNR or PESQ targets. The canonical benchmark has prior model-selection exposure and should be treated as development data, not a fresh holdout.
- R0 seed-26053, seed-26054, and A1 notebook/configuration files are present under `notebooks/v10_r0_s26053/`, `notebooks/v10_r0_s26054/`, and `notebooks/v10_a1_sisdr001/`. Their matching local output directories under workspace-root `kaggle_output/` contain no files at audit time. A pasted status says the two seed kernels were pushed and running; that cloud status is user-provided and was not independently checked in Kaggle. Do not infer completion or retrieve artifacts until an authorized operator reports the runs complete.

### Evaluation infrastructure

- `scripts/evaluate_dfn3_canonical.py` is the existing canonical evaluator. It checks for exactly 590 manifest rows, validates mono 16 kHz aligned finite waveforms, resets libDF state per clip, computes output SNR/SI-SDR/STOI/PESQ-WB, and writes per-clip CSV plus summary JSON with manifest/checkpoint hashes and SNR strata.
- The evaluator includes a path guard that refuses paths containing `SIH_GOLD_TEST`. The audit did not open or read any file under that directory.
- `scripts/compare_dfn3_canonical.py` and `scripts/compare_dfn3_canonical_split.py` implement paired bootstrap comparisons and the even/odd/all partitions. The split comparison supports 2,000 resamples with seed 26052 and emits per-target-SNR summaries.
- `scripts/run_v10_r0_evaluation.py` handles R0 checkpoint checks/evaluation support. `scripts/evaluate_v10_r0_seeds.py` is present for seed aggregation. Existing output paths and the V10 R0 report identify these as current evaluation tooling; the audit did not execute them.
- Recommended existing evaluation commands (run from `antigravity/`, after verifying the working tree and local dependency environment):

  ```bash
  python scripts/evaluate_dfn3_canonical.py \
    --checkpoint ../kaggle_output/dfn3_v10_r0_sih26052/dfn3_v10_r0_sih26052/step-500.hk \
    --canonical-dir runs/sih26052_canonical_validation \
    --output-dir ../kaggle_output/dfn3_v10_r0_sih26052/canonical_eval_step500_rerun

  python scripts/compare_dfn3_canonical_split.py \
    --reference runs/sih26052_dfn3_canonical_step500/per_clip.csv \
    --candidate ../kaggle_output/dfn3_v10_r0_sih26052/canonical_eval_step500_rerun/per_clip.csv \
    --output ../kaggle_output/dfn3_v10_r0_sih26052/paired_step500_vs_deployed.json \
    --split all --bootstrap 2000 --seed 26052
  ```

  These are examples only; no command above was run during this audit.

### Training and data pipeline

- The maintained Kaggle experiment notebooks, metadata, and run prompts are under `notebooks/`; V3.4 repaired and V4–V10 variants are present. V10 R0 is a multi-factor recipe replica using the current leak-safe data harness, not a byte-for-byte historical reproduction.
- The experiment reports document canonical exclusion filtering, source-group splits, and `gold_test_read: false`. The training datasets themselves are attached through Kaggle dataset inputs; the complete source corpus is not evidenced as locally available for a full local training run.
- Local manifests/configuration exist under `data/manifests/`, `data/clean_manifests/`, and `configs/`. `requirements.txt` lists core audio/ML dependencies but is not a fully pinned, reproducible lockfile. The audit did not download dependencies or datasets.
- There is no single unified, versioned training CLI/configuration covering all Kaggle notebook experiments; notebook source remains central to those runs. Future runs should preserve the reviewed notebook, metadata, seed, kernel version/log, attached dataset identifiers, and output checksums together.

### Deployment, streaming, and alternative models

- Raspberry Pi streaming/inference code and extensive run artifacts are under `runs/sih26052_rpi_deployment_audit/`; earlier application code also exists in `deploy/` and `edge_deployment_tests/`.
- Historical reports include a Polar-D service test with 3,600 frames and zero reported misses at a 16 ms frame budget. Separate DeepFilterNet3 native Tract audit data reports one deadline miss in 6,000 frames and thermal throttling; another Python streaming run reports late fallbacks. These are different implementations/configurations and must not be combined into a single real-time claim.
- The Pi service validation report documents a 60-second service test and model/config hashes, but it is a saved report, not a live check of current hardware or current service state. Full microphone-to-headphone latency and headset processed-audio playback remain unverified in the current compliance report. Do not access the Pi or alter `~/anc_live` as part of the next phases without separate authorization.
- Polar-D has source, checkpoints, and evaluation artifacts; its canonical quality results are below the DeepFilterNet3 Step-500 candidate.
- A single-channel `deploy/nlms_postfilter.py` exists, and project reports say it degraded SI-SDR. It is not a true dual-microphone adaptive ANC implementation. No verified synchronized dual-mic recordings or tested GSC subsystem were found in the maintained source tree.
- No FullSubNet adapter, trained FullSubNet checkpoint, residual speech restoration network, or integrated optional-stage pipeline was found. Those remain proposed work, not implemented capabilities.

## 3. Baseline and reproducibility facts

| Item | Audited evidence | Status |
|---|---|---|
| Deployed Step-500 checkpoint | Pi-copied local artifact SHA-256 `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` | Locally present; Pi state not live-verified |
| Frozen canonical manifest | SHA-256 `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`, 590 rows per saved evaluation | Locally present |
| Deployed benchmark result | SNR 13.467 dB, SI-SDR 12.363 dB, STOI 0.8847, PESQ-WB 2.2323, joint 161/590 | Saved summary present |
| R0 Step-500 checkpoint | SHA-256 `57fedd5b608bb7a82e85c7573b0f921f427546a0321cc948182cb1c5695ba40c` | Locally present; experimental, not promoted |
| SIH gold isolation | Evaluator path guard and prior run logs report no gold access | Guard/source inspected; gold content not accessed |
| Run-to-run noise floor | Additional seed notebooks exist; no matching retrieved output files locally | Not yet established from local artifacts |
| Live Pi service state | Saved historical validation only | Not verified live |

## 4. Gaps, risks, and unresolved inputs

1. **Git hygiene:** Many important experiment artifacts are untracked and the repository has pre-existing modifications. Any future code work must leave unrelated files and generated evidence untouched, and must not stage broad directories by default.
2. **Historical reproducibility:** Kaggle notebook executions depend on external dataset mounts and container versions. Local metadata and reports are useful evidence but do not make the runs fully reproducible offline.
3. **Seed-noise estimate:** The three-seed noise floor cannot be computed until seed-26053 and seed-26054 outputs are actually retrieved, verified, and evaluated identically. The pasted “RUNNING” status is not a local artifact.
4. **Benchmark exposure:** V4–V10 and prior comparisons used the 590-clip canonical set. Paired bootstrap intervals quantify paired clip uncertainty for those comparisons, not fresh-run variation or unbiased external generalization. Keep gold sealed until selection and configuration are frozen.
5. **Targets and data coverage:** Full-set SNR and PESQ targets remain unmet. Available labels do not prove adequate recorded artillery, helicopter, or armored-vehicle speech/noise coverage. Source audio rights and local availability need explicit audit before new data acquisition.
6. **Streaming/deployment:** Pi reports describe different software/hardware paths. Current device state, end-to-end acoustic latency, processed headset playback, and real two-microphone ANC are not verified by the local audit.
7. **Dependency management:** Core dependencies are broadly specified rather than locked; model loading depends on DeepFilterNet/libDF/Torch compatibility and the upstream model cache or network access.
8. **Project scope ambiguity:** The workspace root and nested Git repo coexist, and files/reports use both root-relative and `antigravity/`-relative paths. Future scripts should state their expected working directory and use explicit paths.

## 5. Proposed implementation sequence and gates

This audit does not authorize implementation beyond Phase 0. Recommended order, following the supplied implementation specification:

1. **Phase 1 — evaluation reproducibility:** Reconcile the canonical evaluator and wrappers without duplicating metric code; capture checkpoint/config/commit/manifest hashes and runtime metadata; reproduce Step-500 from an existing local artifact; document exact environment and the per-SNR/pass conventions. Gate: 590 rows, matching manifest hash, no gold path, reproducible paired deltas.
2. **Phase 2 — independent FullSubNet baseline:** First inspect official license, dependencies, preprocessing, sample rate, checkpoint provenance, and inference support. Implement only an isolated adapter if these inputs and a usable pretrained artifact are available. Gate: aligned mono 16 kHz output accepted by the unchanged canonical evaluator.
3. **Phase 3 — controlled training:** Wait for the two R0 seed outputs to be retrieved and the three-seed SD to be computed. Then run one-variable changes with frozen architecture, excluded data, split, and evaluation; no model promotion. Prioritize the already specified continuous-SNR and sequence-level-loss work as separate experiments.
4. **Phase 4 — residual restoration:** Prototype offline with the deployed Step-500 model frozen and an identity/bypass path. Gate on paired canonical improvement, audio artifact review, and compute profile before streaming consideration.
5. **Phase 5 — true dual-mic ANC:** Do not claim implementation until synchronized two-channel data or hardware is available. Synthetic stereo tests can validate numerical behavior only; real ANC remains explicitly untested until physical two-channel validation.
6. **Phase 6 — unified pipeline:** Preserve the current Step-500 single-channel route as default, add independently bypassable stages and explicit state handling, and test chunk continuity/fallbacks offline.
7. **Phase 7 — Pi deployment:** Prepare a separate deployment package only after offline gates pass. No Pi service/model change without separate explicit approval. Measure inference deadlines separately from actual microphone-to-headphone latency and headset playback.
8. **Phase 8 — final evidence:** Update requirement traceability and technical report from verified artifacts, distinguish offline/Pi/live/playback evidence, and keep gold sealed until a final selection is locked.

## 6. Audit actions and boundaries

- Read repository status, source inventory, configs, evaluator/comparison code, reports, and selected artifact hashes.
- Hash-checked the canonical manifest, local deployed candidate artifact, and local R0 Step-500 artifact.
- Did **not** read any SIH gold files; did not run evaluators or tests; did not install dependencies; did not inspect Kaggle account state; did not push or start training; did not contact or modify the Raspberry Pi; did not change any model or service configuration.
- Created this Phase 0 report only. No files were staged or committed.

## Phase 2 follow-up — 2026-11-13

The statements above about the missing FullSubNet adapter/checkpoint describe the Phase 0 audit snapshot. Phase 2 subsequently added `src/models/fullsubnet_adapter.py`, `scripts/evaluate_fullsubnet_canonical.py`, and an isolated MIT-licensed vendor subset under `third_party/fullsubnet_vendor/`; the public upstream repository was pinned at `e97448375cd1e883276ad583317b1828318910dc`. The official epoch-58 checkpoint was obtained from the public upstream release and evaluated across the frozen 590-clip set. See `docs/FULLSUBNET_BASELINE.md` for the adapter settings, hashes, results, and limits. The Phase 0 statements about missing training audio, no real dual-mic inputs, and no verified live hardware state remain applicable.
