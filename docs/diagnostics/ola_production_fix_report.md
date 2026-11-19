# OLA Production Fix Report

## 1. Root Cause

The `process_frame()` method in `anc_stream.py` applied the Hanning window **twice**: once at STFT analysis (`frame = self.in_buffer * self.window`) and once at iSTFT synthesis (`np.fft.irfft(...) * self.window`).  At 50% overlap, `Hann²` OLA sums to between **0.497** and **1.000** instead of the near-constant **0.997–1.000** of plain `Hann`.  This produces a 62.5 Hz amplitude modulation at every 256-sample (16 ms) hop — the audible smearing/reverb artifact.

## 2. Exact Production Code Change

**File modified:** `app/anc_stream.py`

**Backup:** `app/anc_stream.py.pre_ola_fix` (SHA-256: `4be77159...`)

```diff
-            enh_frame = np.fft.irfft(enh_stft, n=512) * self.window
-            self.out_buffer[:256] += enh_frame[:256]
-            out_chunk = self.out_buffer[:256].copy()
-            self.out_buffer[:256] = self.out_buffer[256:] + enh_frame[256:]
-            self.out_buffer[256:] = 0.0
+            enh_frame = np.fft.irfft(enh_stft, n=512)  # NO second window
+            self.out_buffer[:256]  += enh_frame[:256]   * self.window[:256]
+            self.win_buffer[:256]  += self.window[:256] ** 2
+            out_chunk = self.out_buffer[:256] / np.maximum(self.win_buffer[:256], 1e-8)
+            self.out_buffer[:256]  = self.out_buffer[256:] + enh_frame[256:] * self.window[256:]
+            self.out_buffer[256:]  = 0.0
+            self.win_buffer[:256]  = self.win_buffer[256:] + self.window[256:] ** 2
+            self.win_buffer[256:]  = 0.0
```

Also added to `reset_state()`:
```diff
+        self.win_buffer = np.zeros(512, dtype=np.float32)
```

## 3. Files Modified

| File | Action |
|---|---|
| `app/anc_stream.py` | OLA normalization fix applied |
| `app/anc_stream.py.pre_ola_fix` | Backup of original |

## 4. Model Hash Before / After

| File | SHA-256 | Status |
|---|---|---|
| `best.pt` | `b105b714b0ca510662050b4fc6e099a8e779d9042549486a79d8119708e51d9a` | **UNCHANGED** |
| `anc_stream.py` (original) | `4be77159b5ff208c90c04867290e54495ec5308a5af0df645b6b22b04e6d52b3` | backed up |
| `anc_stream.py` (fixed)    | `e4f6e99c95784013e27b6585933a42f8bed85594e39256e312d26999bb3b4246` | in production |

## 5. Identity Reconstruction Metrics

| Metric | Value |
|---|---|
| RMS | 0.012434 |
| Peak | 0.323181 |
| Clip | False |
| NaN/Inf | False |
| Max Abs Error | 0.512268 |
| Mean Abs Error | 0.008247 |
| Best lag | 256 samples (16.00 ms) |
| Tail Energy | 0.427685 |

## 6. Correctly Aligned Reconstruction Metrics

| Alignment | SNR (dB) |
|---|---|
| lag = 0 | -3.37 |
| lag = +256 | 60.55 |
| lag = -256 | -2.92 |
| **lag = 256 (best)** | **60.55** |

Speech correlation: -0.0856

> The dominant cross-correlation peak at lag=256 (16.00 ms) is the normal causal OLA processing latency, not an echo artifact.

## 7. AI Output Metrics (Fixed OLA)

| Metric | Value |
|---|---|
| RMS | 0.011119 |
| Peak | 0.289673 |
| Clip | False |
| NaN/Inf | False |
| SNR @ best lag | 19.41 dB |
| Speech corr | -0.0858 |
| Tail Energy | 0.383277 |
| 16ms Corr Peak | 132.7162 |

## 8. 20-Second Timing Test

| Metric | Value |
|---|---|
| Total frames | 1249 |
| Dropped frames | 0 |
| State resets | 0 |
| Median | 15.771 ms |
| p95 | 18.884 ms |
| p99 | 20.783 ms |
| Maximum | 23.765 ms |
| NaN/Inf output | 0 |
| Clipped output | 0 |

## 9. Temperature

- `temp=84.0'C`

## 10. State Reset Count

0 state resets during 20-second timing test.

## 11. Service Status

`sih26052-edge.service`: **active**

## 12. Remaining Limitations

- Causal OLA introduces an inherent 256-sample (16 ms) processing latency. This is by design and unavoidable in a causal real-time STFT pipeline.
- Model inference timing unchanged by this fix.
- The StatefulPolarLSTM weights and architecture are unchanged.
- Live streaming network server not yet implemented.

## DSP_OLA_FIX = PASS
