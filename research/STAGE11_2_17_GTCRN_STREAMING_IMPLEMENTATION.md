# Stage 11.2.17 — GTCRN Stateful Streaming Prototype

## Verdict

**STREAMING PROTOTYPE VERIFIED ON HOST.** The isolated adapter produced exactly the reference sample count and matched the pinned GTCRN full-call inference within the tolerance fixed before testing (`atol=1e-5`, `rtol=1e-5`) in all 30 synthetic signal/chunk combinations. Session reset and invalid-input recovery passed. This verifies a host-side streaming implementation path only; it does not establish real-time readiness, Raspberry Pi 5 performance, enhancement quality on speech recordings, or equivalence to the frozen 15/70/15 ensemble.

## Scope and protections

The tests used only locally synthesized silence, impulses, sinusoids, white noise, synthetic speech-like harmonics, and high-energy-to-silence signals. No canonical or gold clips were opened, and no inference was run on project recordings. No training, tuning, upload, Kaggle, or Pi access occurred. GTCRN source was not edited. The adapter and runner are isolated in `experiments/stage11_2_17_gtcrn_streaming/`.

GTCRN checkpoint SHA-256 before run (runner guard) and after run: `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79`. The Stage 5 upstream source checkout reports commit `242e24c6fd803729314a5636d63ae0be235ce2e4`. Local source file: `third_party/gtcrn_stage5/gtcrn.py`. The Python/PyTorch compatibility shim under `compat/einops.py` implements only the source's single rearrange pattern and avoids installing or modifying upstream dependencies/source.

## Adapter behavior

`GTCRNStreamAdapter` accepts sequential mono float32 chunks at 16 kHz. It holds centered sqrt-Hann STFT analysis context, dispatches one frame at a time, carries each temporal GRU state and causal temporal-convolution history, and maintains an ISTFT overlap-add numerator/denominator ring. Frequency-axis bidirectional GRUs are recomputed within each frame; they do not look into future audio frames. `final=True` reflects the right boundary, processes the remaining centered STFT frames, emits the final overlap-add tail, and closes the session. `reset_session()` creates a clean independent state. Shape and finite-value checks occur before session state is mutated. State names and tensor dimensions are in `STAGE11_2_17_STATE_INVENTORY.csv`.

The full-call reference uses unchanged GTCRN weights and call semantics. For PyTorch 2.14, the model's legacy real/imag output is converted with `view_as_complex` before `torch.istft`, preserving the intended complex interpretation. The reference uses the same periodic sqrt-Hann window, FFT=512, hop=256, centered framing and original input length. The adapter uses equivalent reflected boundary samples and overlap-add accumulation. Input is ingested internally in 64-sample slices, which bounds adapter-owned input buffering independently of the caller chunk length; the final measured ring maximum was 576 samples (512-sample frame context plus one 64-sample internal push).

## Results

Run directory: `runs/stage11_2_17_gtcrn_streaming/run_20261114_r9/`. There are 30 cases (six signals × five chunk modes), all with exact output length and all passing `numpy.allclose` at the frozen tolerance. Across cases, worst RMSE was `2.373e-8`, worst absolute sample error `3.279e-7`, minimum zero-lag correlation `0.9999999999995896`, worst boundary-window RMSE `8.573e-8`, and worst boundary absolute error `3.279e-7`. Detailed per-case results and sample-boundary errors are in `STAGE11_2_17_CHUNK_EQUIVALENCE_RESULTS.csv`.

## Failures encountered

Earlier failed attempts are preserved and must not be interpreted as passing runs. `run_20261114/` exited nonzero because the first adapter version emitted the ISTFT tail before all final reflected frames had been processed. `run_20261114_r2/` exited nonzero because the startup/final reflect path required one sample that had already been trimmed from the input ring. Both implementation issues were corrected. A later `run_20261114_r7/` exited 3 because its initial ring assertion (<512 samples) was stricter than the measured 576-sample bound; the bound was corrected to FFT size plus the 64-sample internal push. R8 passed waveform and bound checks; R9 was rerun after fixing pooled-profile aggregation and exited 0. The final R9 run verified rejection of both a malformed 2-D chunk and a NaN chunk, with session state unchanged in each case. The quick smoke run at `/tmp/stage11_2_17_quick` also passed.

## Run command and reproduction

From the `antigravity` project directory:

```sh
../pc_venv/bin/python experiments/stage11_2_17_gtcrn_streaming/run_stage11_2_17.py \
  --output-dir runs/stage11_2_17_gtcrn_streaming/run_20261114_r9 \
  --long-seconds 20
```

The output path must be unused; the runner refuses to overwrite an existing run directory. Environment: macOS 26.6.2, arm64 Apple CPU, Python 3.14.7, PyTorch 2.14.1, NumPy 1.26.4, SoundFile 0.14.0, one PyTorch CPU thread. Full metrics are in the host-performance report and machine-readable run metadata.

## Protected artifact verification

After the run, hashes matched the recorded values for: deployed DFN3 Step-500 checkpoint (`bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27`), FullSubNet epoch 58 (`482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0`), GTCRN checkpoint (above), canonical validation manifest (`d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`), and frozen 15/70/15 ensemble summary/per-clip files (`8140618570c6ed8aaf1139b2845b941caed709bc55d1989e4a7b362c0c65d6b5`, `b1f8ce8b21622672eb744b9ae0b1d7279579908265636ac0fe59e6825b372190`). The locally available V10 partial candidate config/checkpoint hashes also match Stage 11.2.16 records; it remains incomplete and was not loaded. The separate Stage 11.2.16 causal-candidate Tract archive is unchanged (hash `3b1881f2cbf4a40c5451e23883f1473d68f8e66bedcc3dce77144ebd7c2f8b01`). The previously recorded expected hash for the deployed Step-500 Tract archive (`99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d`) did not match any file found in the project tree during this stage; the protected Step-500 checkpoint itself was present and hash-verified. Thus archive byte-integrity could not be reverified here, although this work did not touch the deployment archive.

## Limitations

This prototype is CPU/PyTorch host code, not native Rust/Tract, and its timing includes Python-side per-frame work. No quality metrics against clean references are meaningful for the synthetic probes. Small nonzero differences arise from FFT and overlap-add floating-point accumulation; all remained well under the frozen tolerance. Irregular chunk sizes produce larger temporary input buffering and occasional deadlines misses; see the profiling report. No measurements here can be extrapolated to Raspberry Pi 5 or 48 kHz deployment.

## Follow-up ingress-bound verification (2026-11-14)

The adapter now rejects caller chunks larger than 4,096 samples (256 ms at 16 kHz) before conversion to float32 or mutation of session state. Accepted chunks continue to be ingested internally in 64-sample slices. Fresh run R12 passed all 30 synthetic waveform comparisons, exact lengths/alignment, reset and invalid-input recovery, the 576-sample ring bound, rejection of 4,097 samples without state mutation, and acceptance/equivalence at exactly 4,096 samples. See `STAGE11_2_18_INGRESS_BOUND_REPORT.md` and `runs/stage11_2_17_gtcrn_streaming/run_20261114_r12_chunkcap_boundary/`. This limits one synchronous adapter call; it does not bound an external capture queue or provide an upstream backpressure contract.
