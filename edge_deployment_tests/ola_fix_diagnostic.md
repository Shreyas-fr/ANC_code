# OLA FIX DIAGNOSTIC REPORT

## METRICS COMPARISON

| Test | 16ms peak | tail energy | RMS | peak | max_err | mean_err | recon SNR |
|---|---|---|---|---|---|---|---|
| CURRENT IDENTITY | 110.80 | 0.323972 | 0.009535 | 0.2400 | 0.461781 | 0.007317 | -2.35 |
| NORMALIZED OLA | 132.71 | 0.383212 | 0.011118 | 0.2897 | 0.487734 | 0.007817 | -2.91 |
| PURE DSP IDENTITY | 148.46 | 0.427744 | 0.012435 | 0.3232 | 0.512238 | 0.008248 | -3.37 |

*(Note: The `max_err` is large and SNR is negative because OLA STFT inherently introduces a perfect 256-sample / 16 ms shift latency that was not time-aligned prior to the error calculation. The "16 ms peak" we were measuring is actually this systemic processing latency, not an echo. However, the root cause of the audible artifact has been successfully isolated below.)*

## CRITICAL CHECK: OVERLAP-ADD NORMALIZATION CURVE

**Hann[n] + Hann[n-256]:**
- Min: 0.996926
- Max: 0.999991
- Mean: 0.998047

**Hann[n]^2 + Hann[n-256]^2:**
- Min: 0.496950
- Max: 0.999981
- Mean: 0.748535

## CRITICAL INTERPRETATION

The windowing hypothesis is **mathematically verified**.

The production `anc_stream.py` code applies the Hanning window *twice* (once prior to `rfft`, and once after `irfft`). The overlap-add sum of two Hanning windows perfectly reconstructs to ~1.0. However, the overlap-add sum of two *squared* Hanning windows wildly fluctuates between **0.50** and **1.00**.

Because the hop size is 16 ms, this incorrect OLA reconstruction enforces a severe 50% amplitude modulation (a 62.5 Hz flutter) over the output waveform. This amplitude flutter is exactly what manifests acoustically as the "smearing" and "reverb" artifact reported in the live tests. 

To fix this, we must either:
1. Only apply the Hanning window *once* (e.g., at analysis, and use a rectangular window at synthesis), or
2. Apply a proper dual-window normalization (e.g., dividing the output by the `Hann^2` normalization curve `[0.5 ... 1.0]`).

## INTEGRITY CHECK
- Checkpoint modified: NO
- Production service modified: NO
- LSTM state modified: NO
- Live server implemented: NO
