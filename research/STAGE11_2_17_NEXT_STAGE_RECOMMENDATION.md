# Stage 11.2.17 — Next-Stage Recommendation

## Decision

Accept this work as **STREAMING PROTOTYPE VERIFIED ON HOST** for sample-aligned, state-carrying GTCRN inference on synthetic test signals. Do not qualify it as a real-time or deployment implementation. The result does not demonstrate speech-enhancement quality, ensemble equivalence, Pi 5 runtime, or wired-path end-to-end latency.

## Recommended next step

Before adding the adapter to any live pipeline, make a separate reviewable engineering stage for: (1) native-runtime feasibility and exact operator/state mapping; (2) an upstream capture-queue and backpressure contract; (3) CPU performance under realistic concurrent load on the intended target hardware, only after separate hardware authorization; and (4) permitted non-gold speech-quality regression against a declared reference, without tuning on the held-out evaluation set. The frozen 15/70/15 offline ensemble and all protected standalone artifacts remain untouched.

The adapter now rejects chunks above 4,096 samples (256 ms at 16 kHz) before mutating state; R11 verified oversized-input rejection and recovery. This caps one synchronous call and adapter-owned ingress path. It does not limit a separate producer/capture queue or define backpressure behavior, and a permitted 256 ms chunk can still exceed its own processing deadline. The prototype also relies on per-frame PyTorch module calls and a local compatibility shim, so it is not a native deployment package.

## Do not infer

- No causal speech-quality result was measured here.
- No GTCRN checkpoint or model source was changed.
- No Stage 8 ensemble candidate was recreated or compared.
- No gold or canonical inputs were accessed.
- No Raspberry Pi 5, ALSA, wired headset, or 48 kHz path was measured.
- The 35 ms target remains unqualified.

All physical qualification gates remain locked. A subsequent task involving real audio, Pi hardware, live I/O, or deployment requires its own explicit scope and authorization.
