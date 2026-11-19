# GTCRN Stage 6 — Canonical Evaluation Report

**Date:** 2026-11-13 · **Status:** Completed, 590/590 clips scored · **Decision:** Do not promote or replace Step-500. GTCRN loses to FullSubNet on all four paired metrics and has fewer joint passes than Step-500.

## Executive results

All three models use the same frozen 590-clip manifest (`d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`), existing canonical metric implementation, and identical joint criteria: output SNR `>15 dB`, STOI `>0.85`, PESQ-WB `>2.5`.

| Model | Mean SNR (dB) | Mean SI-SDR (dB) | Mean STOI | Mean PESQ-WB | Joint pass |
|---|---:|---:|---:|---:|---:|
| Protected DFN3 Step-500 | 13.4670 | 12.3629 | 0.88469 | 2.23229 | 161/590 (27.3%) |
| **GTCRN official DNS3** | **13.8437** | **12.4887** | **0.88135** | **2.11494** | **144/590 (24.4%)** |
| FullSubNet epoch 58 (offline) | 14.9038 | 13.7000 | 0.90258 | 2.51335 | 218/590 (36.9%) |

GTCRN's mean SNR is 0.377 dB above Step-500, with a paired interval above zero; SI-SDR and STOI intervals include zero, PESQ-WB is lower, and the joint-pass count falls by 17 clips. Against FullSubNet, all four GTCRN paired intervals are below zero. GTCRN's aggregate mean SNR remains below the SIH `>15 dB` target; universal compliance is not met.

## Paired bootstrap comparisons

`candidate - reference`; 2,000 paired resamples, seed 26052, percentile confidence intervals, using unchanged `scripts/compare_dfn3_canonical.py`.

| Comparison | Δ SNR dB (95% CI) | Δ SI-SDR dB (95% CI) | Δ STOI (95% CI) | Δ PESQ-WB (95% CI) |
|---|---:|---:|---:|---:|
| GTCRN − Step-500 | +0.377 `[+0.126, +0.626]` | +0.126 `[-0.149, +0.430]` | -0.00334 `[-0.00712, +0.00062]` | -0.117 `[-0.148, -0.086]` |
| GTCRN − FullSubNet epoch 58 | -1.060 `[-1.301, -0.833]` | -1.211 `[-1.435, -0.957]` | -0.02123 `[-0.02338, -0.01902]` | -0.398 `[-0.428, -0.369]` |

## GTCRN results by target input-SNR bin

| Target input SNR | n | Output SNR dB | SI-SDR dB | STOI | PESQ-WB | Joint pass |
|---:|---:|---:|---:|---:|---:|---:|
| -10 | 30 | 6.508 | 3.049 | 0.6792 | 1.3337 | 0/30 (0.0%) |
| -5 | 63 | 9.891 | 8.241 | 0.8038 | 1.6507 | 2/63 (3.2%) |
| 0 | 117 | 11.145 | 9.641 | 0.8488 | 1.7438 | 7/117 (6.0%) |
| 5 | 137 | 13.630 | 12.315 | 0.8899 | 2.0147 | 17/137 (12.4%) |
| 10 | 121 | 15.622 | 14.625 | 0.9217 | 2.3536 | 36/121 (29.8%) |
| 15 | 86 | 18.374 | 17.321 | 0.9490 | 2.6905 | 54/86 (62.8%) |
| 20 | 36 | 19.657 | 18.984 | 0.9613 | 2.9892 | 28/36 (77.8%) |

Individual GTCRN criterion counts on all clips: SNR `>15 dB`, 224/590 (38.0%); STOI `>0.85`, 437/590 (74.1%); PESQ-WB `>2.5`, 171/590 (29.0%). All 590 rows have finite values for all four metrics.

## Runtime, size, and memory

- Official DNS3 checkpoint: 579,819 bytes (566.2 KiB); SHA-256 `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79`.
- Learned PyTorch parameter count: 48,245. The upstream README reports 48.2K when it includes fixed ERB filter weights.
- Hardware/runtime: CPU on macOS 26.6.2, Apple arm64; Python 3.10.22 / PyTorch 1.11.0 / NumPy 1.24.4 / soundfile 0.12.1.
- 590 clips / 1,770 s audio. Summed STFT + model + inverse-STFT time: 17.242 s; inference-only RTF `0.009741`. Inference loop including WAV read/write: 17.942 s; loop RTF `0.010137`. Checkpoint/model initialization was 0.0164 s and is reported separately.
- Peak process RSS: 136,855,552 bytes (about 130.5 MiB), including Python, PyTorch, checkpoint, model, and inference buffers. This is a process peak, not model-only memory.
- These are local CPU measurements; they do not establish Raspberry Pi or live headset latency.

## Method and implementation boundary

Inference used only the official source pinned to commit `502ebfab64da7c4a9af78dcb9c6ceef1ebb01c73` and its DNS3 pretrained checkpoint. Input contract was finite mono 16 kHz float32; STFT used 512 FFT/window, 256 hop, square-root Hann; checkpoint loaded with `strict=True`; each clip was passed separately with no persistent recurrent state. `torch.istft(length=len(input))` preserved the input sample count for hop-misaligned lengths. No weights, model settings, evaluator code, benchmark files, or scoring rules were changed.

Enhanced outputs were saved as float32 WAVs. Scoring imported `metrics()` and manifest guard/hash helpers directly from the unchanged `scripts/evaluate_dfn3_canonical.py`; paired comparisons used the unchanged `scripts/compare_dfn3_canonical.py`. The evaluator hash remained `66e448cc47b0ae60846399d803d8f6321068c5e4a9faa18f6ebb09305219b16a`; comparator hash remained `e66f00553245871a89b6146246c4f60454ea641548b05de97c004cb216abafc7`.

## Commands

Run from `/Users/shreyasdivekar/Documents/anc sih/antigravity`:

```bash
.venv_gtcrn/bin/python scripts/infer_gtcrn_canonical.py \
  --canonical-dir runs/sih26052_canonical_validation \
  --output-dir runs/gtcrn_dns3_canonical_20261113

../pc_venv/bin/python scripts/score_gtcrn_canonical.py \
  --canonical-dir runs/sih26052_canonical_validation \
  --run-dir runs/gtcrn_dns3_canonical_20261113

../pc_venv/bin/python scripts/compare_dfn3_canonical.py \
  --reference runs/sih26052_candidate_step500_repro_20261113/per_clip.csv \
  --candidate runs/gtcrn_dns3_canonical_20261113/per_clip.csv \
  --output runs/gtcrn_dns3_canonical_20261113/paired_vs_deployed_step500.json \
  --bootstrap 2000 --seed 26052

../pc_venv/bin/python scripts/compare_dfn3_canonical.py \
  --reference runs/fullsubnet_baseline/per_clip.csv \
  --candidate runs/gtcrn_dns3_canonical_20261113/per_clip.csv \
  --output runs/gtcrn_dns3_canonical_20261113/paired_vs_fullsubnet_epoch58.json \
  --bootstrap 2000 --seed 26052
```

The inference runner used `--no-overwrite` behavior by refusing a nonempty output directory. No model training or tuning was performed.

## Artifact paths and SHA-256

| Artifact | Path | SHA-256 |
|---|---|---|
| Per-clip metrics | `runs/gtcrn_dns3_canonical_20261113/per_clip.csv` | `f43a643d361af3a8b2b34057d967be9af78091aed4b195512f00271f95771494` |
| Aggregate and SNR-bin summary | `runs/gtcrn_dns3_canonical_20261113/summary.json` | `e79002a889f515e0e074d8505af5f29fed8792d7f1c3bbc99fa9d1482d048c61` |
| Per-clip inference times and output hashes | `runs/gtcrn_dns3_canonical_20261113/inference_per_clip.csv` | `95b65dbaa7260db9a9b37a6ac16a9c5509294178f4b33137bdb6665cf841e729` |
| Runtime and environment metadata | `runs/gtcrn_dns3_canonical_20261113/inference_runtime.json` | `42c2875066176ce1b0b337ea16d29ae19d42d050b7991eb1ac50e21d51dd22c8` |
| Paired CI vs Step-500 | `runs/gtcrn_dns3_canonical_20261113/paired_vs_deployed_step500.json` | `abba0d32b4c6018ddec8f7a224874be0da382cd05365db9d57ee8a4da5c2e94e` |
| Paired CI vs FullSubNet | `runs/gtcrn_dns3_canonical_20261113/paired_vs_fullsubnet_epoch58.json` | `b7aaa08b967f1693c7d92a68818e39f0541d073b07a7eb937370e2e8ef110c4e` |
| 590 enhanced float WAVs | `runs/gtcrn_dns3_canonical_20261113/predictions/` | Individual hashes are recorded per row in `inference_per_clip.csv`; 590 files, 113,327,200 bytes total |

Pinned source snapshot SHA-256 is `d1ad0784ec14ad9abe10b1a0e08e4a68ed9fb104c5e79c6729a305db55cebeac` (definition in Stage 5 smoke report).

## Protected-artifact verification and failures

| Artifact | Before | After | Status |
|---|---|---|---|
| Canonical manifest | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` | same | Preserved |
| Step-500 checkpoint | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` | same | Preserved |
| FullSubNet epoch-58 checkpoint | `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0` | same | Preserved |
| Canonical evaluator source | `66e448cc47b0ae60846399d803d8f6321068c5e4a9faa18f6ebb09305219b16a` | same | Unmodified |
| Paired comparison source | `e66f00553245871a89b6146246c4f60454ea641548b05de97c004cb216abafc7` | same | Unmodified |

Failures/warnings:

1. The first inference command stopped at its source-integrity guard before opening any audio because the runner initially sorted the files while the recorded source digest used a fixed order. The source files were unchanged; the hash-order convention was reconciled, verified against the Stage 5 record, and the full run then completed.
2. PyTorch 1.11 emitted its warning that a future version will require complex `istft` input; inference completed with the official real/imaginary STFT representation.
3. Scoring emitted the existing SciPy/NumPy compatibility warning (`SciPy` expects NumPy >=2.0 while the established scoring environment has NumPy 1.26.4). All 590 scores completed and were finite.

No gold set, Kaggle, Pi, private upload, training, or tuning was used. Step-500 remains the deployed candidate; no model was promoted or replaced.
