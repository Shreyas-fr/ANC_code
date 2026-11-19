# Stage 11.2.29 — PyTorch / exported Tract graph parity

**Date:** 2026-11-14  
**Purpose:** Identify whether the protected Step-500 PyTorch model and its exported native Tract ONNX encoder/decoder graphs disagree when fed the same verified front-end features. This is a fixed-subset diagnostic, not model selection or deployment qualification.

## Result

The first neural components tested agree to normal float32 execution tolerance. The first comparison without temporal alignment showed large errors; that was caused by comparing different frame conventions. The PyTorch model's configured two-frame convolution lookahead shifts feature input by two frames (`pad_feat=(0,0,-2,+2)`). After applying that documented shift to the ONNX inputs, all encoder outputs, ERB mask decoder output and DF coefficient decoder output match closely on the fixed clips 6, 93 and 287.

Across 27 component/clip comparisons (7 encoder outputs × 3 clips, plus two decoder outputs × 3 clips):

- Encoder `e0`–`e3`, embedding and `c0`: maximum absolute difference across all clips **6.71e-6**; largest per-component RMSE **2.37e-7**.
- Encoder local-SNR output: maximum absolute difference **4.01e-5**; largest RMSE **1.41e-5**.
- ERB mask decoder: maximum absolute difference **2.86e-6**; largest RMSE **4.86e-7**.
- DF coefficient decoder: maximum absolute difference **2.77e-6**; largest RMSE **8.48e-8**.
- 0/27 comparisons were bit-identical, as expected for separate CPU graph implementations, but no material graph-output discrepancy was found.

This localizes the previously observed Python/native output gap away from the tested neural encoder/decoder weights and operators. It does **not** establish complete end-to-end waveform parity: the stage did not compare Tract's live recurrent state frame by frame, DeepFilter application, attenuation/quiet-frame handling, overlap-add waveform synthesis, or the full 16↔48 kHz runtime path. The earlier 590-clip result also showed an approximately 0.10 dB SNR residual after resampling parity work; that residual remains unexplained. Keep the existing deployed binary and Step-500 model unchanged.

## Method

- Used only fixed canonical development IDs 6, 93 and 287; no gold data, Kaggle, Pi or live audio.
- Reused Stage 11.2.28's shared 48 kHz inputs and its bit-verified Python libDF v0.5.6 STFT/ERB/complex feature arrays; feature input hashes are listed in `runs/stage11_2_28_frontend_parity_20261114/shared_inputs_metadata.json`.
- Loaded `step500_from_pi.pt` in existing Python 3.14.7 / PyTorch 2.14.1, with a strict state-dict load. The Python 3.14 libDF constructor is known to segfault, so the trace did not call it; graph initialization used the same ERB widths recorded from the locally built 0.5.6 binding.
- Extracted the existing protected `dfn3_step500_tract.tar.gz` into the new Stage 11.2.29 evidence directory and ran `enc.onnx`, `erb_dec.onnx`, `df_dec.onnx` through existing ONNX Runtime 1.32.0 CPU. The archive and original model were not altered.
- Matched the explicit two-frame lookahead before comparing outputs. No weights, model parameters or evaluation clips were changed.

## Commands

```sh
../pc_venv/bin/python experiments/stage11_2_29_network_parity/trace_pytorch.py
mkdir -p runs/stage11_2_29_network_parity_20261114/tract_export
tar -xzf ../models/dfn3_step500_tract.tar.gz -C runs/stage11_2_29_network_parity_20261114/tract_export
../pc_venv/bin/python experiments/stage11_2_29_network_parity/compare_onnx.py
```

The first PyTorch import attempt exited 1 because package initialization imported an unavailable `torchaudio.backend` module. The isolated diagnostic then bypassed `df.__init__` (which eagerly imports audio helpers) and stubbed only the unavailable libDF initialization API; the successful run used real PyTorch model code and the unchanged protected state dict. An initial unaligned ONNX comparison had large errors; correcting the frame mapping for the two-frame lookahead reduced all reported errors to the values above. No dependency was installed.

## Integrity and limits

- Protected Step-500 SHA-256 before and after: `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27`.
- Protected Tract archive SHA-256 before and after: `99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d`.
- Canonical manifest SHA-256 (unchanged): `d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4`.
- Per-component metrics: `runs/stage11_2_29_network_parity_20261114/onnx_component_comparison.csv`.
- PyTorch trace arrays and metadata: `runs/stage11_2_29_network_parity_20261114/pytorch/`.
- Extracted protected graph snapshot: `runs/stage11_2_29_network_parity_20261114/tract_export/`.

**Conclusion:** no actionable mismatch was found in the neural encoder or decoder graphs on this subset once frame lookahead was aligned. The remaining parity investigation should continue at streaming recurrent-state behavior, DeepFilter/synthesis alignment, quiet-frame policy and full pipeline resampling. This is not a deployment approval and does not clear Pi 5, latency, ANC, independent validation or physical qualification gates.
