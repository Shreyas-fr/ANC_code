# Stage 11.2.16 — Recovery Roadmap

This audit is software/source inspection only. No checkpoint/config was modified, no new inference or training was run, and no Raspberry Pi, live audio, gold data, or external upload was used.

## Recommended order

1. **Keep the frozen 15/70/15 mix as offline quality reference.** Preserve its three inputs, checkpoints, hashes, stored waveforms and current 590-clip report. No further weight tuning on this reused benchmark.
2. **Prototype only the low-risk software question next:** a synthetic, non-gold GTCRN chunk-state adapter that carries inter-GRU and temporal-convolution state, plus STFT/ISTFT overlap. First compare chunked and full-call output with fixed source weights across chunk boundaries and session resets. Keep it isolated and do not alter the protected GTCRN source/checkpoint.
3. **Evaluate a DFN3 + GTCRN two-model path only after a separate approval.** Its fixed blend/weight must be predeclared, and quality compared against both component baselines and the frozen 15/70/15 offline reference. It is not the same ensemble.
4. **Do not attempt exact FullSubNet streaming by merely cutting audio into chunks.** The frozen offline Laplace normalization uses all frames. A causal normalization and explicit recurrent-state version is a model/inference change; it requires separate approval and an independently reviewed quality plan.
5. **Measure host execution and queue bounds** for the isolated streaming adapters on a non-gold synthetic signal. Host timings are feasibility data only and do not establish Raspberry Pi 5 RTF or latency.
6. **Independent quality validation remains blocked** until a provenance-cleared, non-gold speaker/session-disjoint data source with clean references is available (see Stage 9/10 reports). The repeated 590-clip benchmark stays development-only.
7. **Physical qualification remains locked.** A later separately authorized stage must test the actual Pi 5, selected wired UAC2/I2S capture/playback devices, measured ALSA periods, electrical loopback, underruns, resource ceilings, and blinded headset quality. Keep all five physical gates locked until approved evidence is collected.

## Stage decision

**NO-GO for claiming the frozen ensemble is bounded-latency or real-time.** The exact FullSubNet configuration makes the wait for normalization depend on the full utterance. **GO only for planning a separately reviewed synthetic GTCRN state-preservation experiment**; this audit does not run or authorize that next experiment. DFN3 Step-500 remains a frame-streaming software fallback/reference, but its 30 ms algorithmic floor and unmeasured physical path do not establish compliance with the provisional 35 ms target.

## Partial V10 artifact

`runs/stage11_2_16_v10_causal_candidate/` is preserved and now carries `INCOMPLETE_NOT_QUALIFIED.md`. It contains only the copied V10 R0 Step-500 checkpoint and a zero-lookahead configuration. It is not an ensemble export, was not used as a source, and was not loaded or evaluated in this audit.

## Follow-up status

The isolated synthetic GTCRN host adapter proposed in item 2 was implemented and checked in Stages 11.2.17–11.2.18. It matched the full-call reference for the documented synthetic matrix and passed session-reset, input-rejection and bounded-state checks. The next unresolved software step is an explicitly bounded, timestamped 48 kHz/16 kHz resampling and queue integration design; this is not yet an authorized ensemble experiment or a deployment result. The host adapter does not change the NO-GO for the frozen three-model ensemble, because FullSubNet's exact utterance normalization remains unbounded for live sessions.

The exact deployed Step-500 Tract archive is also absent from the current project tree (expected SHA-256 `99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d`). Recover it from an already authorized local backup before attempting a frozen Step-500 native stream; do not substitute the incomplete V10 export or the separate causal candidate archive.
