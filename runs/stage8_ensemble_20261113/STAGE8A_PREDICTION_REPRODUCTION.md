# SIH 26052 — Stage 8A Prediction Reproduction

**Status:** Complete; stopped before Phase B as requested. No alignment checks or ensemble simulations were run.

## Scope and safeguards

Generated waveform predictions for the protected DFN3 Step-500 checkpoint and the verified FullSubNet epoch-58 checkpoint from the frozen 590-clip canonical manifest. Existing GTCRN DNS3 predictions were not regenerated. No training, tuning, package installation, upload, Kaggle access, gold-set access, Raspberry Pi access, deployment, model promotion, or evaluator/manifest/checkpoint modification occurred.

Protected SHA-256 values were checked before inference and after both runs:

| Artifact | SHA-256 before | SHA-256 after | Result |
|---|---|---|---|
| `runs/sih26052_canonical_validation/manifest.csv` | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` | Preserved |
| `runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt` (local protected checkpoint copy; no Pi access) | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` | Preserved |
| `checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar` | `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0` | `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0` | Preserved |

The metric implementation and evaluator sources remained unchanged. No existing evaluation directory or metric result was overwritten.

## Inference implementation and environment

- Repository commit: `242e24c6fd803729314a5636d63ae0be235ce2e4` (working tree was already dirty; no pre-existing changes were reverted).
- Python: `3.14.7`; PyTorch: `2.14.1`; NumPy: `1.26.4`; SciPy: `1.18.1`; SoundFile: `0.14.0`; torchaudio: `2.11.0`; libDF: `0.5.6`; pystoi: `0.4.1`; PESQ package imported successfully.
- Host: macOS arm64; CPU inference.
- Existing DFN3 inference method: `scripts/evaluate_dfn3_canonical.py::load_checkpoint` and `::enhance_one`; `atten_lim_db=None`, post-gain `0 dB`, and `df_state.reset()` per clip. DeepFilterNet3 base model was already cached locally; no download was needed.
- Existing FullSubNet inference method: `src.models.fullsubnet_adapter.FullSubNetAdapter.enhance`, CPU, mono 16 kHz, 512-point Hann STFT, 256 hop, LSTM, two-frame lookahead, offline Laplace normalization; each clip was processed independently.
- Both methods read the exact manifest rows and canonical mono 16 kHz inputs in manifest order. Predictions were serialized as float32 WAV and re-read before scoring. Scoring imported the unchanged `metrics()` from `scripts/evaluate_dfn3_canonical.py`.
- FullSubNet upstream checkout is pinned at `e97448375cd1e883276ad583317b1828318910dc`.

## Commands and outcomes

Run from `/Users/shreyasdivekar/Documents/anc sih/antigravity`:

```bash
../pc_venv/bin/python scripts/generate_stage8_predictions.py \
  --model dfn3 \
  --canonical-dir runs/sih26052_canonical_validation \
  --dfn3-checkpoint runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt \
  --output-dir runs/stage8_ensemble_20261113/step500_predictions
```

Completed all 590 clips successfully; final summary was written. No output directory existed before the run.

```bash
../pc_venv/bin/python scripts/generate_stage8_predictions.py \
  --model fullsubnet \
  --canonical-dir runs/sih26052_canonical_validation \
  --fullsubnet-checkpoint checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar \
  --output-dir runs/stage8_ensemble_20261113/fullsubnet_predictions
```

Completed all 590 clips successfully; final summary was written. No output directory existed before the run.

The runner is append-only and refuses existing output directories. It writes predictions directly into the requested directory, plus `per_clip.csv`, `prediction_files.csv` (one SHA-256 per WAV), and `generation_metadata.json`.

## Prediction integrity and metric reproduction

Both output sets contain exactly 590 files mapped one-to-one to canonical `val_index` IDs `0..589`. Every file is finite, mono, 16,000 Hz, 48,000 samples (3.0 s), and WAV subtype `FLOAT`; no sample-count alignment errors occurred. Independent post-run checks recomputed all 1,180 WAV hashes and matched `prediction_files.csv`.

The unchanged evaluator metric values match the previously stored baseline **exactly per clip** for all four metrics in both sets (maximum and mean absolute difference are zero):

| Model | Output SNR | SI-SDR | STOI | PESQ-WB | Joint pass | Compared baseline |
|---|---:|---:|---:|---:|---:|---|
| DFN3 Step-500 | 13.46698 dB | 12.36288 dB | 0.884690 | 2.232295 | 161/590 (27.29%) | `runs/sih26052_candidate_step500_repro_20261113/per_clip.csv` |
| FullSubNet epoch 58 | 14.90377 dB | 13.69998 dB | 0.902576 | 2.513348 | 218/590 (36.95%) | `runs/fullsubnet_baseline/per_clip.csv` |

These numbers reproduce the saved baselines; they do not assert that the system meets the universal `>15 dB` target.

## Runtime and memory

| Model | Inference time | Inference RTF | Generation + file I/O + scoring | End-to-end RTF | Peak process RSS |
|---|---:|---:|---:|---:|---:|
| DFN3 Step-500 | 28.00 s | 0.0158 | 53.01 s | 0.0299 | 379,682,816 B (362.0 MiB) |
| FullSubNet epoch 58 | 195.45 s | 0.1104 | 224.91 s | 0.1271 | 888,160,256 B (846.9 MiB) |

RTF uses the 1,770 seconds of canonical audio. Peak RSS is process-wide, not model-only memory.

## Artifact paths and SHA-256

| Artifact | SHA-256 |
|---|---|
| Generator `scripts/generate_stage8_predictions.py` | `55a8dac13a34edc2ee7adb7f6b5c0c128e85138e950db5eeb326f02d5e15a9af` |
| Canonical evaluator `scripts/evaluate_dfn3_canonical.py` | `66e448cc47b0ae60846399d803d8f6321068c5e4a9faa18f6ebb09305219b16a` |
| FullSubNet evaluator `scripts/evaluate_fullsubnet_canonical.py` | `167be032e9380e3f78f4c165f9856a9bfa0eb238c495fda9386a8212e1df85f0` |
| FullSubNet adapter `src/models/fullsubnet_adapter.py` | `e0aca3fc2aa95723f730dd01c1a993638f380ee464b75a5dcb9837c96c480502` |
| Step-500 `per_clip.csv` | `9b27038fb21b9d15e7066b2324372c4471abab2247989ea1da65922888a2366f` |
| Step-500 `prediction_files.csv` | `a9378cbb2dd4b4e8702fccafd1daa758a3499bfb54c7e1bdf9e8915fa9e8e6fb` |
| Step-500 `generation_metadata.json` | `87bdb4246dacd30106b1e52f484679e7061819cadaf9f63c9bb4b58494972928` |
| FullSubNet `per_clip.csv` | `56207ad4325b9c91a71188cf2edecf063b1385f118c29579acd604d8a4dd7e62` |
| FullSubNet `prediction_files.csv` | `e0f0eb56af5693b7ef14926d161676a8338885c426a1386148f7ec27f17747f1` |
| FullSubNet `generation_metadata.json` | `1ad4bec281594949d5b9cf746df2a4575ee31208ab04717933764c36a656d623` |

Each `prediction_files.csv` records the SHA-256, sample rate, channel count, sample count, duration, and canonical ID for every individual WAV under its model directory.

## Warnings and failures

- Both runs emitted the environment's existing SciPy/NumPy compatibility warning: SciPy reports a requirement for NumPy >=2.0 while NumPy 1.26.4 is installed. All 590 scores per model completed and exactly reproduced the baselines.
- The DFN3 library emitted `fatal: not a git repository` while logging model setup. The model then loaded from the existing cache, processed all clips, and returned a successful final summary; the message did not affect the run.
- No inference, scoring, integrity, or protected-hash failures occurred. Both commands completed successfully.

## Stop point

Stage 8A is complete. The generated sets are ready for review at:

- `runs/stage8_ensemble_20261113/step500_predictions/`
- `runs/stage8_ensemble_20261113/fullsubnet_predictions/`

No Phase B alignment checks or ensemble simulation has started. Awaiting explicit user approval before continuing.
