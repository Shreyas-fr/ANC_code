# Stage 11.2.16 — Streaming Architecture Comparison

## Decision

The frozen 15/70/15 ensemble cannot currently be represented as a bounded-latency stream while retaining the exact frozen inference methods. FullSubNet's offline Laplace normalization computes one scalar from the complete utterance. For an unconstrained live session, that waits until the session ends. On the existing fixed 3-second canonical clips, it would wait for the 3-second clip. Therefore the exact ensemble has **no finite current streaming latency bound** and cannot meet the provisional 35 ms target as implemented.

No architecture is selected. DFN3 and GTCRN have plausible streaming paths, but an implementation and quality-preservation result for this ensemble do not yet exist.

## A. Full three-model mix with bounded buffering

Proposed wiring: capture 48 kHz mono PCM; feed DFN3 at native 48 kHz; use stateful 3:1 decimation/resampling for FullSubNet and GTCRN at 16 kHz; timestamp every component output by source-sample index; use bounded per-model FIFOs; resample 16 kHz outputs back to 48 kHz; align only by measured fixed algorithmic delays; combine float outputs with the frozen formula `0.15 D + 0.70 F + 0.15 G`.

As it stands, FullSubNet blocks this design because its utterance-wide normalization has no finite bound. Its 2-frame lookahead contributes 32 ms and centered analysis needs up to 16 ms future input, but replacing the global normalization is the larger change and would no longer reproduce the offline reference. Even with causal normalization, a direct component-context floor is at least 48 ms before inference, resampling, queues, ALSA or codec delay. That exceeds the provisional 35 ms target.

For an implementation using strict 10 ms / 16 ms frame barriers, the common barrier repeats every 80 ms (LCM), which alone misses the target. Timestamped asynchronous FIFOs can avoid waiting for an 80 ms super-frame, but require sample-accurate mapping and a measured bound on the slowest component. Any queue overflow, missed deadline or underrun must be counted and trigger a defined fallback; silent queue growth is not acceptable.

**Status: NO-GO for exact frozen FullSubNet in a bounded-latency path.** A modified FullSubNet may be investigated only after separate approval, and would require a new quality assessment.

## B. Reduced two-model streaming ensemble: DFN3 + GTCRN

This alternative excludes FullSubNet's unbounded normalization. It is technically plausible after GTCRN exposes persistent temporal GRU, convolution, and STFT/ISTFT state. DFN3 already has frame-wise Tract state and 480-sample frame processing at 48 kHz. GTCRN runs at 16 kHz with 16 ms hops and at least 16 ms future availability from centered 512-point analysis.

**Follow-up evidence:** Stage 11.2.17/11.2.18 now provides an isolated Python/PyTorch GTCRN stateful host adapter. Thirty synthetic signal/chunk combinations match the whole-call reference within `1e-5` tolerances, with reset and bounded adapter-owned state checks. This resolves the initial state-exposure prototype question, but does not provide a native runtime or tested synchronization with DFN3. The R12 host run had 6 deadline misses in 1,956 chunks; therefore even host per-call timing was not uniformly below chunk duration in that run. The two-model system remains a research candidate and still needs a separately approved fixed mixture, timestamp/resampler design, external queue policy, and quality evaluation.

Use stateful rational resampling and timestamps, then asynchronous queues; do not impose the 80 ms strict common barrier. The component model-side floor is at least the greater of DFN3's 30 ms and GTCRN's 16 ms, plus resampler, execution, queue and physical I/O delay. DFN3 alone leaves only 5 ms under the provisional 35 ms ceiling, so this two-model option is not demonstrated feasible at that target. The equal-weight DFN3/GTCRN offline pair was tested as a diagnostic, but it is not the frozen 15/70/15 ensemble and is not independently validated. Removing the 70% FullSubNet contribution is a material quality change.

**Status: RESEARCH CANDIDATE, not selected.** First expose GTCRN streaming state and test boundary equivalence on synthetic signals; then evaluate fixed two-model weights against the frozen offline reference on the development benchmark. Do not assume quality carries over.

## C. Single-model DFN3 Step-500 real-time fallback

The Rust/Tract source exposes a one-hop stateful processing API, and the prior audit recorded the deployed Step-500 configuration as 48 kHz, FFT 960/hop 480, with 2-frame lookahead. Its derived model-side delay is 30 ms: 10 ms framing/overlap-add plus 20 ms lookahead. However, the exact protected Step-500 Tract archive with expected SHA-256 `99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d` is absent from the current project tree. Therefore this is a source-level fallback architecture, not an executable verified package until the exact archive is recovered and verified. If available, the 30 ms model-side floor leaves 5 ms for inference and every capture/playback/codec/queue contribution under the provisional 35 ms end-to-end target. Previous end-to-end values of roughly 49-56 ms are estimates in project documentation, not measurements on a Pi 5.

**Status: strongest existing software-streaming path; latency and hardware qualification still NO-GO.** Preserve the checkpoint and archive. Evaluate actual target hardware only in a separately authorized physical stage.

## Synchronization, lifecycle and failure policy

- Time-stamp at the common 48 kHz sample index; convert 16 kHz model indices by exact integer ratio and preserve the stateful resampler's phase.
- Wait for the latest required sample from all active branches before mixing. Delay faster branches by explicit sample FIFO, not per-clip correlation correction.
- Phase B found same sample counts/rates and no systematic offset; IDs 162 and 436 remain ambiguous for Step-500 vs FullSubNet and must not receive per-clip shifts or polarity flips.
- Initialize a fresh state for each session. At startup, prime required STFT, model, resampler and output queues with declared zeros; record startup delay. At shutdown, flush documented overlap tails and discard padding by timestamp.
- Bound each FIFO in samples and milliseconds. On deadline miss, underrun or overflow, log it and switch to a separately evaluated deterministic fallback (or a safe pass-through path); do not silently increase latency.
- Model outputs can exceed `|1|` in float: playback needs a declared limiter/headroom policy. Metric evaluation must retain un-clipped float outputs so the Phase C metric comparison remains interpretable.

## Relative weights and storage

Frozen weights remain 0.15 / 0.70 / 0.15; this audit does not tune them. Recorded learned parameter counts are 2,135,484 DFN3, 5,637,635 FullSubNet and 48,245 GTCRN. At float32, weights alone are approximately 8.14 MiB, 21.51 MiB and 0.18 MiB respectively, about 29.8 MiB combined; this excludes runtime libraries, activations, state buffers, resamplers and audio queues. These are arithmetic estimates, not resident-memory measurements for a streaming process.

## Evidence references

- Frozen output/result: `runs/stage8_ensemble_20261113/phase_c_ensembles/d2_fs70_raw/summary.json`.
- Model output alignment: `runs/stage8_ensemble_20261113/phase_b_alignment/PHASE_B_ALIGNMENT_REPORT.md:18-48`.
- DFN3 config and frame processing: protected archive config (`sr=48000`, `fft_size=960`, `hop_size=480`, `conv_lookahead=2`, `df_lookahead=2`); `libDF/src/tract.rs:312-330,405-444,523-655`; `libDF/src/bin/enhance_wav.rs:137-170`.
- FullSubNet setup and normalization: `src/models/fullsubnet_adapter.py:41-141`; `third_party/fullsubnet_vendor/audio_zen/model/base_model.py:203-218`; upstream vendored model `third_party/FullSubNet/recipes/dns_interspeech_2020/fullsubnet/model.py:72-136`.
- GTCRN temporal operations and file inference: `third_party/gtcrn_stage5/gtcrn.py:77-93,107-153,186-225,292-345`; `scripts/infer_gtcrn_canonical.py:92-120`.
- Prior latency ledger is explicitly estimated for non-algorithmic stages: `research/STAGE11_2_15_LATENCY_RECONCILIATION.md:98-120`.
