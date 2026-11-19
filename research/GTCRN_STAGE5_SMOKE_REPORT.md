# GTCRN Stage 5 Environment and Smoke-Test Report

**Date:** 2026-11-13 · **Status:** Environment/import/load/single-file smoke passed. **Canonical 590-clip evaluation has not been run; user approval is required before it starts.**

## Scope and protected artifacts

This report covers only an isolated GTCRN environment and one authorized local non-gold sample. No training, tuning, canonical benchmark evaluation, Kaggle, Pi, or gold-test access occurred. No project data or checkpoints were uploaded. The existing evaluation environment remains Python 3.14.7 / PyTorch 2.14.1 / NumPy 1.26.4. Protected Step-500 checkpoint SHA-256 was rechecked as `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27`; it was not modified. Canonical manifest and evaluator were not modified.

## Source and model provenance

| Item | Verified value |
|---|---|
| Official repository | [Xiaobin-Rong/gtcrn](https://github.com/Xiaobin-Rong/gtcrn) |
| Immutable source commit | `502ebfab64da7c4a9af78dcb9c6ceef1ebb01c73` (`main` at fetch time) |
| License | Official `LICENSE`, MIT, SHA-256 `c467165e5860b4a7494ef4a6e2788e4115d95b5b8989bb5f86287089adddf794` |
| Source files fetched | `gtcrn.py`, `LICENSE`, `requirements.txt` only; all from the pinned commit |
| Source file hashes | `gtcrn.py`: `20bf0610702506fa45cd543454b84bbeb862d73c7c20a3f8d820fdc04da6099b`; `requirements.txt`: `c026bf264c0eefd4249c9c88380ccda331cb453c55228a6ba43fe44f12dd8428` |
| Source snapshot hash | `d1ad0784ec14ad9abe10b1a0e08e4a68ed9fb104c5e79c6729a305db55cebeac`; defined as SHA-256 over files in fixed order `gtcrn.py`, `LICENSE`, `requirements.txt`, concatenating UTF-8 relative path, NUL, ASCII byte length, NUL, then file bytes |
| Checkpoint | Official `checkpoints/model_trained_on_dns3.tar`, 579,819 bytes (566.2 KiB), DNS3-trained per upstream name/docs |
| Checkpoint SHA-256 | `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79` |
| Checkpoint archive keys | `epoch`, `model`, `optimizer` |
| Parameters loaded | 48,245 learned PyTorch parameters; upstream README additionally counts fixed ERB filter parameters for 48.2K total |

## Isolated environment

Environment path: `.venv_gtcrn/`. Its Python runtime is managed under `/private/tmp/gtcrn_python/` so the host Python and existing evaluation environment were left intact.

| Package | Installed version |
|---|---:|
| Python | 3.10.22 arm64 |
| PyTorch | 1.11.0 |
| NumPy | 1.24.4 |
| einops | 0.7.0 |
| soundfile | 0.12.1 |
| ptflops | 0.7 |
| cffi / pycparser / typing-extensions | 2.1.1 / 3.11 / 4.16.0 |

Versions follow the official `requirements.txt` pins. The repository does not declare a Python lower bound; the validated compatibility point is Python 3.10.22 + the exact PyTorch 1.11.0 pin (not a claim that this is the minimum possible Python version). All packages were installed only in `.venv_gtcrn`; no packages were added to the existing evaluator venv. Its package versions were checked again after setup and were unchanged.

## Smoke input and inference contract

- Input: repository-root `output_tactical.wav`, a pre-existing noncanonical project demo input referenced by `src/enhance/baseline_enhance.py`; not a gold file and not one of the 590 canonical clips.
- Sample SHA-256: `b4a53affa9c82178904b1bbc01e7409cf662a2e5ec2b537cc44de697b0e5b760`.
- Input sample rate/channels: 16,000 Hz / mono; duration 11.016 s; 176,256 samples.
- Source-path features: mono waveform → Torch STFT, FFT/window 512, hop 256, square-root Hann; `GTCRN` returns a two-component real/imaginary STFT tensor; inverse STFT reconstructs mono waveform.
- Import test: passed (`GTCRN` imported using official `gtcrn.py`).
- Checkpoint test: passed; `load_state_dict(..., strict=True)` returned `<All keys matched successfully>`; 271 state tensors.
- Smoke output: input waveform `(176256,)`; input STFT `(257, 689, 2)`; model output STFT `(257, 689, 2)`; enhanced waveform `(176256,)`; all output samples finite.
- CPU inference (STFT + model + inverse STFT) for this single 11.016 s file: 0.109426 s, RTF 0.009933. This one-file timing is only a smoke observation, not the benchmark RTF or hardware suitability claim.
- Peak process RSS reported by macOS `getrusage`: 170,246,144 bytes (~162.3 MiB), including Python, PyTorch, loaded checkpoint and model; not model-only memory.

### Boundary detail

The upstream demo calls `torch.istft` without an explicit output length. On this sample the default returned `(176128,)`, 128 samples shorter than the input because the input length is not a multiple of the 256-sample hop. The smoke wrapper passed `length=len(input)` to the same official inverse-STFT call, yielding exactly 176,256 finite output samples. This does not alter GTCRN weights, STFT frame content, metrics, or the evaluator; it preserves the waveform-length contract. This adapter boundary behavior should be reviewed before the canonical run.

PyTorch emitted its documented warning that future versions will require complex-valued `istft` input; under pinned PyTorch 1.11 the official two-channel real/imag representation worked successfully.

## Exact commands and results

- Source resolution: `git ls-remote https://github.com/Xiaobin-Rong/gtcrn.git HEAD refs/heads/main` returned the pinned SHA above. The first sandboxed attempt failed because DNS/network access was blocked; the approved read-only retry succeeded.
- Isolated runtime: `uv python install 3.10 --install-dir /private/tmp/gtcrn_python --cache-dir /private/tmp/gtcrn_uv_cache` installed CPython 3.10.22 arm64.
- Environment: `uv venv .venv_gtcrn --python /private/tmp/gtcrn_python/cpython-3.10.22-macos-aarch64-none/bin/python --no-project --cache-dir /private/tmp/gtcrn_uv_cache`.
- Requirements: `uv pip install --python .venv_gtcrn/bin/python --cache-dir /private/tmp/gtcrn_uv_cache -r third_party/gtcrn_stage5/requirements.txt` completed successfully.
- The initial `uv venv` attempt without explicit cache path failed with a permissions error accessing `~/.cache/uv`; it made no environment changes. Retrying with `/private/tmp` cache succeeded.
- `uv python install` created a convenience symlink at `~/.local/bin/python3.10`; it was removed after noticing it. The managed runtime remains under `/private/tmp`, and the isolated venv continues to use it directly.
- `python -m pip freeze` was unavailable because `uv venv` did not seed pip; package inventory was obtained successfully with `uv pip freeze` instead.
- The first smoke attempt asserted exact output length against upstream's default `istft` and failed as described above. The follow-up shape inspection confirmed the 128-sample shortfall; the final smoke using `length=len(input)` passed. All command failures/warnings are recorded here.

## Approval gate

Environment preparation and the authorized single-file smoke are complete. No 590-clip evaluation has been started. Review this report and approve the canonical evaluation before proceeding. The next stage would use this pinned model in an isolated adapter, keep the existing canonical manifest/evaluator methodology unchanged, and compare against both protected Step-500 and FullSubNet epoch 58.
