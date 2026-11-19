# SIH 26052 — Stage 11.2.16: Frozen Ensemble Streaming Feasibility Audit

**Audit result: NO-GO for bounded-latency equivalence of the frozen 15/70/15 ensemble.** The frozen offline quality reference is useful, but current FullSubNet inference depends on utterance-wide normalization. Therefore its output cannot be produced for an unbounded live session with a finite wait. Making that component causal would change the inference method and requires separate review and quality evaluation.

**What remains feasible:** DFN3 Step-500 has an existing frame-based Rust/Tract processing path; GTCRN's pinned architecture has causal temporal operations in source, but the current wrapper is whole-clip and does not preserve recurrent state across calls. A two-model DFN3/GTCRN stream is a research candidate, not a proven substitute for the offline ensemble. The single-model DFN3 path has a statically derived 30 ms algorithmic floor before inference and physical input/output delays.

## Frozen offline reference (unchanged)

`y[n] = 0.15 D[n] + 0.70 F[n] + 0.15 G[n]`, where D is deployed DFN3 Step-500, F is FullSubNet epoch 58 and G is GTCRN DNS3. Existing summary: SNR 15.04124 dB, SI-SDR 13.96529 dB, STOI 0.906858, PESQ-WB 2.585263, and 227/590 (38.5%) joint passes. The mean metrics cross the threshold values, but only 227 clips passed all three together. These are reused 590-clip development results, not independent validation, live streaming results or Pi 5 measurements.

Reference summary and per-clip output: `runs/stage8_ensemble_20261113/phase_c_ensembles/d2_fs70_raw/`. The 590-clip manifest SHA-256 remains `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`. Phase B found all output files mono 16 kHz and 48,000 samples; no systematic offset. IDs 162 and 436 have ambiguous direct Step-500/FullSubNet correlations and are not shifted or corrected. FullSubNet and GTCRN contain float samples above 1.0, so playback headroom policy remains open. See `runs/stage8_ensemble_20261113/phase_b_alignment/PHASE_B_ALIGNMENT_REPORT.md:18-48`.

## Component audit

### DFN3 Step-500 — STREAMING-READY at software component level; hardware unqualified

The protected archive config is 48 kHz, FFT 960, hop 480, with `conv_lookahead=2` and `df_lookahead=2`. In `libDF/src/tract.rs`, `DfTract` owns recurrent `TractModel` states and rolling spectrogram queues (lines 196-232); it derives total model lookahead as the maximum of the two settings (312-323), initializes buffers (405-434), resets state between utterances (437-444), and accepts a single-hop sample block while updating analysis, rolling spectra and synthesis state (523-655). `libDF/src/bin/enhance_wav.rs:137-138` calculates delay as `fft_size-hop_size + lookahead*hop_size`; lines 150-170 reset between files and process frames. The component is stream-capable in software; this does not prove integrated real-time behavior on Pi.

Delay is derived as `(960-480)/48000 = 10 ms` framing plus `2*480/48000 = 20 ms` lookahead, total **30 ms**. This leaves 5 ms under the provisional 35 ms end-to-end ceiling for compute, capture, playback, resampling/codec and scheduling combined. Those contributions are not physically measured here.

### FullSubNet epoch 58 — OFFLINE ONLY as frozen

`src/models/fullsubnet_adapter.py:59-71` configures a 16 kHz, 512/256 STFT, two-frame lookahead and `offline_laplace_norm`; lines 111-140 run centered whole-waveform STFT, one full model call and ISTFT. `third_party/fullsubnet_vendor/audio_zen/model/base_model.py:203-218` computes `mu = mean(input, dims=all non-batch dims)`, which includes the complete frame axis. The upstream model pads two future frames and drops the first two outputs (`third_party/FullSubNet/recipes/dns_interspeech_2020/fullsubnet/model.py:72-136`). Thus fixed 3-second canonical clips imply at least 3 seconds of wait under exact frozen inference; a continuous, variable-length session has no finite wait bound. Centered analysis adds up to 16 ms future availability and the model's two hops add 32 ms, even before normalization.

A causal running normalization, chunk state, context and boundary handling would change the inference method. No such adaptation was implemented or evaluated.

### GTCRN DNS3 — STREAMING WITH MODIFICATIONS

GTCRN's stored model is evaluated at 16 kHz with a 512-point square-root Hann STFT and hop 256 (`scripts/infer_gtcrn_canonical.py:92-120`). `gtcrn.py:107-153` left-pads temporal convolutions; `:186-225` uses bidirectional GRUs along frequency and unidirectional GRUs along time; `:292-318` exposes a whole-spectrogram forward call. Lines 330-345 contain a source-level causality probe that excludes 32 ms around the changed boundary, but there is no recorded result from that probe in this audit. The current canonical wrapper runs one whole clip per call and preserves no stream state.

Required changes: expose and carry temporal GRU states, cache temporal convolution context and STFT/ISTFT overlap, reset all state on new session, and compare chunked to full-call output at boundaries. The current centered STFT needs up to 16 ms future samples. The architecture suggests a causal temporal model after state refactoring, but exact chunk-equivalence and quality are unverified.

## Synchronization and architecture alternatives

All saved predictions are sample-aligned at 16 kHz with no systematic inter-model delay. For a 48 kHz wired input, DFN3 can remain native and the other two models require stateful 3:1 resampling in and 1:3 resampling out. Timestamped sample FIFOs can align outputs without a global frame barrier. A strict barrier at each common frame boundary would repeat every `LCM(10 ms,16 ms)=80 ms`, already beyond the 35 ms target. Asynchronous FIFOs avoid that specific 80 ms barrier, but the slowest model, frame completion, resampler delay, inference, and output queue still need measured bounds.

1. **A — three-model bounded buffer:** not feasible with exact current FullSubNet due utterance-wide normalization. A later causal-normalization FullSubNet may use timestamped asynchronous queues, but changes the inference method, has a 48 ms framing-plus-lookahead floor, and would require reevaluating quality. No winner or weights are selected.
2. **B — DFN3 + GTCRN:** technically plausible after exposing GTCRN state; at least 30 ms model-side DFN3 delay plus physical I/O and compute. Quality is not equal to frozen ensemble by assumption; a fixed reduced mix must be separately predeclared/evaluated. No selection.
3. **C — single DFN3 Step-500 fallback:** existing software frame API and 30 ms algorithmic floor. It is the strongest current streaming implementation, but the 35 ms provisional end-to-end target leaves 5 ms for all remaining contributions. Existing 49-56.5 ms values are historical design estimates, not measurements; no Pi qualification.

Detailed alternatives: `research/STAGE11_2_16_ARCHITECTURE_COMPARISON.md`.

## Latency assessment

| Stage/component | Value | Evidence type |
|---|---:|---|
| DFN3 framing | 10 ms | Mathematically derived from 960/480 at 48 kHz |
| DFN3 lookahead | 20 ms | Mathematically derived from 2 x 480 at 48 kHz |
| DFN3 total algorithmic floor | 30 ms | Derived; source delay formula agrees |
| FullSubNet centered STFT future context | up to 16 ms | Derived from half of 512 samples at 16 kHz |
| FullSubNet explicit lookahead | 32 ms | Derived from 2 x 256 at 16 kHz |
| FullSubNet global normalization wait | current 3 s clips: 3,000 ms; live arbitrary sessions: unbounded | Derived from current implementation; prevents bounded stream |
| GTCRN centered STFT future context | up to 16 ms | Derived from half of 512 samples at 16 kHz |
| Model inference on Raspberry Pi 5 | Unknown | No hardware access/measurement in this stage |
| Resampler, ALSA, codec, electrical round trip | Unknown | No selected hardware configuration or live measurement |
| Provisional system target | <=35 ms p95 | Engineering target only |

The separate latency CSV records each value and classification. The prior Stage 11.2.15 report's non-algorithmic Pi figures are explicitly estimates and are not reused as measurements.

## Quality and safety plan

If a streaming candidate is separately approved, compare it against the saved frozen ensemble using the existing unchanged metric implementation and identical inputs. Report per-clip SNR, SI-SDR, STOI, PESQ-WB, joint passes, seven input-SNR bins, target-SNR strata, and paired confidence intervals. Include the `target_snr <= 0 dB` subgroup (n=210), speech onset/offset, chunk boundaries, session resets, clipping/headroom, transient-source limitations and blinded listening where authorized. Do not tune ensemble weights, clip or normalize outputs, or access the sealed gold set. The canonical set remains development regression only.

## Partial V10 export

Inspected `runs/stage11_2_16_v10_causal_candidate/`: it contains only `model_config/config.ini` (SHA-256 `6fd82652cef2b90375512df15cf028040ac09f9ce353792a4b8ff24e43222b9b`) and copied `causal_v10_r0_step500_weights.hk` (SHA-256 `57fedd5b608bb7a82e85c7573b0f921f427546a0321cc948182cb1c5695ba40c`). There is no ONNX export, Tract package, export metadata or evaluation. It was not used or loaded. `INCOMPLETE_NOT_QUALIFIED.md` in that folder records the status. No deletion or rename was made.

## Protected-artifact integrity

### Follow-up correction — Stage 11.2.17 (2026-11-14)

The Stage 11.2.17 workspace audit could not locate any project-tree file matching the previously recorded deployed Step-500 Tract archive hash `99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d`. The checkpoint itself was present and matched its expected hash, but the archive's current byte integrity is **not verified** until the archive is recovered and hashed. The Stage 11.2.16 table below preserves what that report recorded at the time; do not interpret that entry as a currently reproducible verification.

The Stage 11.2.16 run recorded these protected SHA-256 values. The deployed Tract archive entry is a recorded expected hash only; its current file presence/integrity is unverified per the follow-up correction above:

| Protected item | SHA-256 |
|---|---|
| Canonical manifest | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` |
| Deployed DFN3 Step-500 checkpoint | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` |
| Step-500 Tract archive | `99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d` |
| FullSubNet epoch-58 checkpoint | `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0` |
| GTCRN DNS3 checkpoint | `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79` |
| Frozen `d2_fs70_raw/summary.json` | `8140618570c6ed8aaf1139b2845b941caed709bc55d1989e4a7b362c0c65d6b5` |
| Frozen `d2_fs70_raw/per_clip.csv` | `b1f8ce8b21622672eb744b9ae0b1d7279579908265636ac0fe59e6825b372190` |

All three model prediction ledgers were rechecked against the 590 stored WAV files per model; each had 590 rows, 590 WAVs and zero hash mismatches. Two initial read-only hash-check invocations failed because one ran outside the repository-relative working directory and another constructed an incorrect GTCRN ledger path; the corrected checks passed. Both failures occurred before modifying anything, and no files were changed by them. The audit performed no model loading, inference, training, upload, Pi access or gold access.

## Deliverables and decision

- Component source audit: `research/STAGE11_2_16_COMPONENT_STREAMING_AUDIT.csv`.
- Latency classifications: `research/STAGE11_2_16_LATENCY_BUDGET.csv`.
- Alternative architectures: `research/STAGE11_2_16_ARCHITECTURE_COMPARISON.md`.
- Future evaluation protocol: `research/STAGE11_2_16_QUALITY_PRESERVATION_PROTOCOL.md`.
- Recovery sequence: `research/STAGE11_2_16_RECOVERY_ROADMAP.md`.

**Stage 11.2.16 feasibility decision: NO-GO for claiming the frozen ensemble is a bounded-latency real-time system.** Software preparation can continue with an isolated synthetic GTCRN state-preservation experiment after separate approval. Real-time readiness, independent validation, Pi 5 qualification and physical headset demonstration remain unproven; all physical qualification gates remain locked.

## Current-state addendum (Stage 11.2.17–11.2.18)

The Stage 11.2.16 component findings above are the audit snapshot. Subsequent authorized host-only work implemented an isolated GTCRN stateful adapter in `experiments/stage11_2_17_gtcrn_streaming/gtcrn_stream_adapter.py`. On synthetic signals, 30 signal/chunk combinations matched the pinned full-call reference within the predeclared `atol=1e-5, rtol=1e-5`; session reset and invalid-input recovery passed. The R12 follow-up accepts a maximum 4,096-sample caller chunk, rejects 4,097 samples without changing state, and completed a 20-second synthetic soak without duration-proportional state growth. See `research/STAGE11_2_17_GTCRN_STREAMING_IMPLEMENTATION.md` and `research/STAGE11_2_18_INGRESS_BOUND_REPORT.md`.

This upgrades GTCRN's current classification to **STREAMING WITH MODIFICATIONS (host prototype verified)**. It remains a Python/PyTorch host prototype with no speech-quality evaluation, native Rust/Tract implementation, cross-model synchronization, external queue/backpressure contract, or Pi/48 kHz performance evidence. The R12 host profile recorded mean 3.469 ms, p95 6.294 ms, p99 22.595 ms, and 6 deadline misses in 1,956 chunks on the test Mac; these are observations from that host experiment only, not Raspberry Pi latency or RTF. The exact three-model frozen ensemble remains NO-GO for bounded latency because frozen FullSubNet requires utterance-wide normalization.

### Audit-scope correction

During a later broad local inventory command, the filesystem returned filenames beneath `data/SIH_GOLD_TEST`. No gold audio was opened, hashed, decoded, scored, or used, and no files were changed. This filename enumeration was outside the requested gold-isolation boundary and is recorded as a process deviation; do not describe the later inventory as zero filesystem contact with the gold directory. All gold files remain untouched. No further gold-path inspection is part of this audit.

### Current protected-artifact checks

Read-only checks in the current workspace matched the deployed Step-500 checkpoint copy (`runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt`, SHA-256 `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27`), FullSubNet epoch 58 (`checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar`, `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0`), GTCRN DNS3 (`checkpoints/gtcrn_stage5/model_trained_on_dns3.tar`, `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79`), canonical manifest (`runs/sih26052_canonical_validation/manifest.csv`, `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`) and frozen ensemble summary/per-clip files (hashes above). The deployed Step-500 Tract archive with expected hash `99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d` is still absent from the project tree, so its current byte integrity is not verified. The incomplete V10 folder remains present and is not a source for any candidate.
