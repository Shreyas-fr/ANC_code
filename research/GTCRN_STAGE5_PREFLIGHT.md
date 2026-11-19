# GTCRN Stage 5 Preflight — Blocked Before Download

**Date:** 2026-11-13 · **Decision:** Stop before download, install, adapter implementation, or canonical evaluation. This is a preflight blocker report, not an evaluation report.

> **Historical note:** This records the pre-approval state. The user subsequently approved the isolated environment; the official source and checkpoint have since been fetched, the smoke passed, and the current status is in [GTCRN_STAGE5_SMOKE_REPORT.md](GTCRN_STAGE5_SMOKE_REPORT.md). The full canonical evaluation is still awaiting approval.

## Safety and repository state

- Nested repository HEAD remains `242e24c6fd803729314a5636d63ae0be235ce2e4`.
- The working tree was already dirty/untracked. Existing artifacts were preserved.
- The protected Step-500 file exists at `runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt`; its SHA-256 was read and matches the authorized hash `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27`. No writes were made to it.
- No GTCRN source/checkpoint is present in the local workspace. No files were downloaded; no packages were installed; no benchmark audio was opened; no training/cloud/Pi/gold activity occurred.

## Official source inspected

- Official project: [Xiaobin-Rong/gtcrn](https://github.com/Xiaobin-Rong/gtcrn), GitHub reports MIT license.
- Read-only pages inspected: repository tree, README, `infer.py`, `gtcrn.py`, `requirements.txt`, license, `checkpoints/`, and `stream/` directory.
- The repository is on branch `main` and has no published releases. The page reports 91 commits but the immutable current commit ID was not exposed in the read-only page/API responses available during this audit. Therefore an exact source revision is **not yet verified**. Pinning `main` by URL alone would not be reproducible.
- GTCRN files identified upstream: `gtcrn.py`, `infer.py`, `checkpoints/model_trained_on_dns3.tar`, `checkpoints/model_trained_on_vctk.tar`, and stream/ONNX files. The upstream README says current accounting is 48.2K parameters / 33.0 MMAC/s and notes the paper's earlier 23.7K / 39.6 MMAC/s counts. These are author descriptions, not local measurements.

## Checkpoint provenance and hash

- Proposed checkpoint: official repository file `checkpoints/model_trained_on_dns3.tar`, listed as **566 KB** in GitHub file metadata. The official inference example loads this file's `model` state dictionary. The filename and README identify it as DNS3-trained; exact training manifest/epoch are not stated in the inspected page.
- The public page does not display a SHA-256 checksum. Its local SHA-256 is therefore **not verified**. Computing it requires fetching the public checkpoint. The GTCRN license page is MIT, but checkpoint-specific provenance/checksum metadata is not separately supplied in the inspected files.
- Public upstream code and this small pretrained model can be fetched from the official GitHub repository without uploading any SIH/private data. That route does not itself violate the no-private-upload restriction. The source revision and model digest still must be captured after an authorized fetch.

## Input/output compatibility

- Official `infer.py` demonstrates mono waveform input read as float32, asserts `fs == 16000`, computes `torch.stft` with FFT/window 512 and hop 256 using `hann_window(512).pow(0.5)`, passes the complex-pair STFT to `GTCRN`, and reconstructs with matching `torch.istft`.
- The model returns an enhanced complex STFT; wrapper must inverse-transform and align output length before applying existing canonical metrics. Canonical data are mono 16 kHz, so the public inference sample-rate/channel contract matches at the waveform boundary. The exact STFT center/padding and short-clip behavior still need source-level adapter checks before scoring.
- Official `requirements.txt`: `einops==0.7.0`, `numpy==1.24.4`, `ptflops==0.7`, `soundfile==0.12.1`, `torch==1.11.0`. `gtcrn.py` imports `einops.rearrange`; `ptflops` is for complexity reporting rather than the shown inference call. `stream/` contains an ONNX route, but local `onnxruntime` is also absent.

## Local environment inspection

The existing evaluator environment `../pc_venv` has Python 3.14.7, torch 2.14.1, NumPy 1.26.4, soundfile 0.14.0, SciPy 1.18.1, `pystoi` 0.4.1 and `pesq` 0.0.4. It does **not** have `einops`, `ptflops`, `onnxruntime` or `psutil`. No import of GTCRN was attempted because its source is absent.

The official pin `torch==1.11.0` predates Python 3.14 support, and it conflicts with the installed torch version. The official model code's `einops` dependency is missing. The currently approved environment cannot run the official source as-is, and no compatibility test is possible without fetching source and resolving that dependency. The task explicitly says to stop when a required dependency/compatibility condition is unavailable and disallows package installation without separate approval.

## Blocker / next authorization needed

Stage 5 cannot proceed in the existing environment. To resume without changing the canonical evaluator environment, the user must separately approve one of:

1. Creating an isolated environment and installing the official inference dependencies (at minimum a compatible Python/PyTorch stack plus `einops`; optional `ptflops` only if needed for parameter/MAC accounting), then fetching the pinned official source and DNS3 checkpoint; or
2. Providing an already available isolated environment containing a verified compatible GTCRN stack and checkpoint.

After that gate, record immutable source revision, checkpoint SHA-256 and size, verify strict state-dict loading, then prepare the isolated adapter and run the existing 590-clip methodology once. Compare paired against Step-500 and FullSubNet, report SNR/SI-SDR/STOI/PESQ-WB, joint pass, all target-SNR bins, paired bootstrap CIs, model size, RTF and peak CPU memory. No model replacement or promotion is implied.

## Activity outcome

No nonzero command exits occurred. No evaluation or test was run. No reproducibility evaluation report is claimed; this preflight report records why the evaluation is blocked.
