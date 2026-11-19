# Stage 11.2.18 — GTCRN Adapter Ingress Bound Follow-up

**Status:** Host-side bounded-call behavior verified; no deployment qualification.

## Change

The isolated Stage 11.2.17 adapter now accepts at most 4,096 mono samples per call (256 ms at 16 kHz). It checks dimensionality, real numeric dtype, size and finiteness before converting to float32 or changing session state. Accepted input is still processed in internal pushes of 64 samples. The caller must split longer recordings into sequential calls; the adapter does not buffer a full long recording as one request.

This limits a single synchronous adapter call and its owned input path. It does not cap an upstream producer/ALSA queue, provide backpressure, or guarantee that a 256 ms call meets a real-time deadline. The caller-owned input object is outside the adapter's memory bound.

## Verification

Command, from the `antigravity` directory:

```sh
../pc_venv/bin/python experiments/stage11_2_17_gtcrn_streaming/run_stage11_2_17.py \
  --output-dir runs/stage11_2_17_gtcrn_streaming/run_20261114_r11_chunkcap \
  --long-seconds 20
```

The first attempt, R10 (`run_20261114_r10_chunkcap`), exited `1`: the prior session-isolation fixture submitted its 0.6-second Session A as one call, exceeding the new limit. No model or reference data were changed. The fixture was corrected to send 16 ms chunks. R11 then completed with exit `0`; R12 added a positive boundary test proving that exactly 4,096 samples are accepted and equivalent, and completed with exit `0`.

R12 used only synthetic signals and the pinned GTCRN DNS3 checkpoint. The strict checkpoint load passed; all 30 signal/chunk combinations had exact output lengths and passed the pre-frozen `atol=1e-5`, `rtol=1e-5` comparison. A 4,096-sample chunk was accepted, returned exactly 4,096 aligned samples and passed that tolerance (RMSE `2.52e-8`, max error `3.28e-7`). A 4,097-sample chunk raised `ValueError` and the session summary remained unchanged. Session B after reset and after rejected inputs matched the fresh-adapter output exactly. Ring bounds passed: 576 samples input, 512 samples ISTFT overlap. The 20-second soak processed 1,250 frames without duration-proportional state growth.

Host profile in R12: mean 3.469 ms, p95 6.294 ms, p99 22.595 ms, 6 deadline misses of 1,956 chunks; peak RSS 231,178,240 bytes; average Python allocation delta 1,453 bytes/chunk. These are single-run macOS ARM64/Python 3.14.7/PyTorch 2.14.1 CPU observations. Deadline checks compare processing time with the submitted chunk duration and exclude all device I/O, scheduler contention and external buffering.

## Protected hashes

Verified before and after the R11 run; all matched expected values:

| Artifact | SHA-256 |
|---|---|
| Deployed DFN3 Step-500 checkpoint | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` |
| FullSubNet epoch 58 checkpoint | `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0` |
| GTCRN DNS3 checkpoint | `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79` |
| Canonical manifest | `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4` |
| Frozen 15/70/15 summary | `8140618570c6ed8aaf1139b2845b941caed709bc55d1989e4a7b362c0c65d6b5` |
| Frozen 15/70/15 per-clip CSV | `b1f8ce8b21622672eb744b9ae0b1d7279579908265636ac0fe59e6825b372190` |

R11 machine-readable evidence hashes:

| File | SHA-256 |
|---|---|
| `run_metadata.json` | `a467d8f792a1cfa4b9b38e2087544bb3fdd82227003b5d8db99604fc17223303` |
| `chunk_equivalence_results.csv` | `929a1354f47995306b45b1486fda66fed3169ab0f8e7705f96958b6bdbfb1224` |
| `host_profile.csv` | `5572fd73f374ee480593e9c8331c171d3f9515ddbd3ec7c031ed013c5bff6b01` |
| `session_isolation.json` | `2820c527e8344690915dbb6fbcd21b1a5227ddb81a67df2fc2d570777c1d18df` |
| Adapter source | `ea74cb3286f088fa88859b3121a1a628ce6b459216cefd778627fe4d37f355ab` |
| Runner source | `fdbe14b6b634321546761fa81e84bf003b524db80379d5674e43567dd3a978b5` |

## Verdict and remaining work

The adapter now rejects oversized single calls safely and remains waveform-equivalent on the synthetic host matrix. This is **not** a bounded end-to-end stream: an external capture queue/backpressure policy is still absent, and the adapter remains Python/PyTorch rather than the deployment runtime. There was no canonical evaluation, speech-quality test, Pi access, ALSA test, live audio, training, model promotion, or gold access. Raspberry Pi 5, 35 ms end-to-end latency, headset operation, independent validation and the physical qualification gates remain unverified/locked.
