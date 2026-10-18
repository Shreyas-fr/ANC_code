# Perceptual Metric Fix Report

## Diagnosis of PESQ/STOI Failure
During the canonical evaluation, `PESQ`, `STOI`, and `SI-SDR` all failed and silently returned `0.0`. Upon investigation, the failures were entirely due to incorrect argument typing and ordering when interfacing with the underlying metric libraries. 

The evaluation loop was incorrectly passing `torch.Tensor` objects instead of 1D `numpy.ndarray` objects, and in the case of `pesq`, passed the arguments in the wrong order.

### Metric Details:

1. **SI-SDR**
   - **Waveform Shape Expected:** 1D `numpy.ndarray` `(N,)`
   - **Waveform Shape Supplied:** 1D `torch.Tensor` `[N]`
   - **Exact Exception:** `TypeError: mean() got an unexpected keyword argument 'axis'`
   - **Cause:** `src/enhance/evaluate.py` implements `si_sdr` using `np.mean()`. In newer versions of numpy, calling `np.mean()` on a PyTorch tensor raises an axis error instead of implicitly converting it.

2. **STOI**
   - **Waveform Shape Expected:** 1D `numpy.ndarray` `(N,)`
   - **Waveform Shape Supplied:** 2D `torch.Tensor` `[1, N]` (via `.unsqueeze(0)`)
   - **Exact Exception:** `numpy.exceptions.AxisError: axis 1 is out of bounds for array of dimension 1`
   - **Cause:** `pystoi` strictly expects 1D arrays and calculates norms along `axis=1` internally under the assumption of a 2D framed structure generated inside the library. Passing a 2D array breaks its internal dimensionality.

3. **PESQ**
   - **Waveform Shape Expected:** 1D `numpy.ndarray` `(N,)`
   - **Waveform Shape Supplied:** 2D `torch.Tensor` `[1, N]` passed as the Sample Rate argument.
   - **Exact Exception:** `RuntimeError: Boolean value of Tensor with more than one value is ambiguous`
   - **Cause:** The `pesq` library expects the signature `pesq(fs, ref, deg, mode)`. The evaluation script called `pesq(t_target, t_est, sr)`, meaning a tensor was passed to the `fs` argument. The C-wrapper checks `if fs != 8000 and fs != 16000:`, which triggers the boolean ambiguity error on tensors.

### Correction Required
The `compute_metrics` wrapper has been corrected to:
1. Keep the audio signals as 1D `numpy.ndarray` (shape: `(N,)`, dtype: `float32`).
2. Call `si_sdr(target_np, est_np)`.
3. Call `stoi(target_np, est_np, sr, extended=False)`.
4. Call `pesq(sr, target_np, est_np, 'wb')`.

These corrections strictly affect the wrapper API and do NOT alter the audio signals, preserving the integrity of the frozen 16 kHz representation without any resampling, truncation, or normalization.
