# Stage 11.2.28 — Python/Rust libDF Front-End Parity

**Status: FRONT-END BINDING PARITY REPRODUCED EXACTLY ON THREE FIXED CLIPS; PYTORCH/TRACT NETWORK PARITY REMAINS OPEN.**

## Objective and safeguards

Compare the pre-neural DFN3 path between Python libDF and Rust `DFState`: input frames, complex STFT, ERB features, normalized complex features, and analysis-synthesis reconstruction. This stage did not compare, tune, or replace model weights. It used only three fixed canonical development clips (IDs `6`, `93`, and `287`) and the frozen 48 kHz input arrays. The canonical set remains reused development data, not independent validation.

No gold, Kaggle, Pi, live audio, participant data, upload, model training, package installation, evaluator change, checkpoint change, or deployment change occurred. A Python binding was built into the isolated Stage 11.2.28 artifact directory and loaded through `PYTHONPATH`; the existing `.venv_gtcrn` environment was not modified.

## Environment and method

- Python binding: DeepFilterLib/libDF `0.5.6` source tag `v0.5.6`, commit `978576aa8400552a4ce9730838c635aa30db5e61`, compiled locally for the existing Python `3.10.22` environment (`NumPy 1.24.4`, `soundfile 0.12.1`). PyO3 `0.19.2`, NumPy Rust binding `0.19.0`.
- Rust diagnostic: `DFState` from the same archived `0.5.6` source tree, built offline against the already cached Stage 11.2.26 dependency graph. The diagnostic binary is macOS ARM64.
- Shared input: the same IEEE float32 48 kHz WAV was consumed by both paths. The 16→48 kHz input was prepared once with `scipy.signal.resample_poly(x, 3, 1).astype(np.float32)` in the existing `pc_venv`; its hashes are recorded in `shared_inputs_metadata.json`.
- DFN3 configuration from the protected archive: 48 kHz, FFT 960, hop 480, 32 ERB bands, 96 DF bins, minimum 2 frequencies per ERB, normalization alpha `0.99`.
- All clips had exactly 300 frames and 144,000 samples.

## Results

The Python binding and Rust diagnostic arrays were **bit-identical** for every compared element on every clip:

| Stage | Shape per clip | Result |
|---|---:|---|
| Complex STFT | 300 × 481 complex | Exact equality; max absolute difference 0 |
| ERB normalized features | 300 × 32 float32 | Exact equality; max absolute difference 0 |
| Complex normalized features | 300 × 96 complex | Exact equality; max absolute difference 0 |
| Analysis-synthesis output | 144,000 float32 samples | Exact equality; max absolute difference 0 |

The exact arrays cover all 3 clips × all four stages. This validates the Python binding and Rust `DFState` framing, analysis, feature transforms, and synthesis mapping for the 0.5.6 source under the controlled same-input comparison. Stage 11.2.27 separately found the local 0.5.7-pre quiet-frame branch differs on 22 of 590 clips; this report does not erase that runtime behavior difference.

The remaining Stage 11.2.26 full-set SNR difference (−0.105 dB vs Python, paired 95% clip bootstrap CI [−0.168, −0.039]) is **not explained by this front-end**. Neural graph numerics, recurrent state progression, lookahead indexing, mask/DF coefficient output, and final enhanced-spectrum synthesis mapping remain to be compared directly.

## Environment failures and resolution

1. Existing `pc_venv` Python `3.14.7` has DeepFilterLib `0.5.6`, but a direct `libdf.DF(48000, 960, 480, 32)` construction segfaulted (exit code `139`) before analysis. `faulthandler` placed the crash in `PyNumber_Index` during the PyO3 constructor. No files or packages in that environment were changed.
2. The first offline Python-binding build failed at link time (exit code `101`) because the macOS dynamic library did not permit unresolved Python symbols. Rebuilding in the isolated Stage 11.2.28 target with explicit `-undefined dynamic_lookup` linker arguments succeeded. The binding was loaded directly from the run artifact folder; it was not installed.
3. The first Rust diagnostic compile failed with a format-string redundant-argument error (exit code `101`). The format string was corrected in the isolated Stage 11.2.28 source snapshot; the subsequent offline build exited `0`.
4. Initial Python attempts in Python 3.14 failed at `DF` construction and generated no feature arrays. They are preserved as execution history; final comparisons use only the successful Python 3.10 binding run.

## Commands

```text
../pc_venv/bin/python experiments/stage11_2_28_frontend_parity/prepare_shared_inputs.py

PYO3_PYTHON="/Users/shreyasdivekar/Documents/anc sih/antigravity/.venv_gtcrn/bin/python" CARGO_HOME=/private/tmp/stage26-cargo-home RUSTFLAGS='-C link-arg=-undefined -C link-arg=dynamic_lookup' cargo build --offline --release -p DeepFilterLib --manifest-path runs/stage11_2_28_frontend_parity_20261114/DeepFilterNet/Cargo.toml --target-dir runs/stage11_2_28_frontend_parity_20261114/target_py310

PYTHONPATH="/Users/shreyasdivekar/Documents/anc sih/antigravity/runs/stage11_2_28_frontend_parity_20261114/py310libdf" ../antigravity/.venv_gtcrn/bin/python experiments/stage11_2_28_frontend_parity/run_python_libdf.py

CARGO_HOME=/private/tmp/stage26-cargo-home cargo build --offline --release -p deep_filter --bin dump_frontend --no-default-features --features 'bin,tract,wav-utils,transforms' --manifest-path runs/stage11_2_28_frontend_parity_20261114/DeepFilterNet/Cargo.toml --target-dir runs/stage11_2_28_frontend_parity_20261114/target

<dump_frontend binary> <shared 48 kHz float input> <unique output directory> 0.99

../antigravity/.venv_gtcrn/bin/python experiments/stage11_2_28_frontend_parity/compare_frontend_dumps.py
```

## Verdict and next action

**Verified:** for the tested 0.5.6 source, Python and Rust front-end arrays match bit-for-bit on three canonical clips. This removes front-end wrapper/framing/features/synthesis as a cause for those tested inputs and points the next diagnostic at model inference and lookahead mapping. It is a small fixed subset, not full 590-clip parity and not evidence of independent quality or deployment readiness.

Next: in a new isolated trace, compare PyTorch and Tract outputs (`lsnr`, ERB gains, DF coefficients, enhanced spectra) at matched frame indices using the same features, then compare recurrent state and synthesis alignment. Keep all traces off the deployed source/binary and verify protected hashes before and after.

## Evidence

- Python feature arrays: `runs/stage11_2_28_frontend_parity_20261114/python_features_py310/`.
- Rust arrays: `runs/stage11_2_28_frontend_parity_20261114/rust_features_py310/`.
- Shared input hashes: `runs/stage11_2_28_frontend_parity_20261114/shared_inputs_metadata.json`.
- Bitwise comparison rows and summary: `frontend_comparison.csv` and `frontend_comparison_summary.json`.
- Python/Rust run metadata, exact source snapshot, binding and diagnostic binaries: `runs/stage11_2_28_frontend_parity_20261114/`.
