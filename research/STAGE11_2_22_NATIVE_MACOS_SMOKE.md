# Stage 11.2.22 — Native Step-500 Runtime Smoke on macOS ARM64

**Status:** Host artifact-load and single-file smoke passed; Raspberry Pi qualification remains unverified.

## Purpose and limits

Verify that the locally available native macOS ARM64 `deep-filter` executable loads the protected Step-500 Tract archive and processes one synthetic file. This is a smoke test only. It does not test the Raspberry Pi Linux ELF, live capture/playback, canonical speech quality, or system latency. No model was trained or changed, and no benchmark or gold audio was read.

## Artifact verification

| Artifact | SHA-256 | Result |
|---|---|---|
| Protected PyTorch Step-500 checkpoint, `runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt` | `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27` | Matches protected digest |
| Tract archive, `../models/dfn3_step500_tract.tar.gz` | `99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d` | Matches recorded digest |
| Native macOS runtime, `runs/sih26052_rpi_deployment_audit/runs/dfn3_pi_optimization/DeepFilterNet/target/release/deep-filter` | `0352b86f9e9f0ce7e82b4f8cb0c1c0dba7df75945782a666b46f5c3de2f57879` | Mach-O 64-bit arm64 |
| Runtime source, `.../libDF/src/bin/enhance_wav.rs` | `7074ac8d4e12e8cca289820ed3fb708271da2ae2d86c6d4f5fb2e33ef8eff11d` | Recorded |

The archive contains exactly `tmp/export/{enc.onnx,erb_dec.onnx,df_dec.onnx,config.ini}`. Each member's SHA-256 matched the corresponding file in `../models/onnx_tract_step500/`:

| Archive member | SHA-256 |
|---|---|
| `enc.onnx` | `b8ecbce6517e91cf8395aaf8da9b4187b601b874dbc51731d878039304d52be6` |
| `erb_dec.onnx` | `9465ae949e1abb69b2c4f711a3dfc9d0afdbb1172ac745e0fe86ccfebf13f1c0` |
| `df_dec.onnx` | `92850d7afa26b3f7de04021469bbb273c2be10cda2280ce0d894f759be13e8b3` |
| `config.ini` | `415eb925d44990d938fb739f514aa3662c1ec0ea836cff044fa1291b82cb4290` |

The embedded configuration reports 48 kHz, FFT 960, hop 480, `df_lookahead=2`, and `conv_lookahead=2`.

## Command and result

Host: macOS 26.6.2, arm64. The smoke input was a locally synthesized 2.0-second mono two-tone signal, 48 kHz PCM16, 96,000 frames.

```sh
"/Users/shreyasdivekar/Documents/anc sih/antigravity/runs/sih26052_rpi_deployment_audit/runs/dfn3_pi_optimization/DeepFilterNet/target/release/deep-filter" \
  --model "/Users/shreyasdivekar/Documents/anc sih/models/dfn3_step500_tract.tar.gz" \
  --compensate-delay -v \
  --output-dir "/Users/shreyasdivekar/Documents/anc sih/antigravity/runs/stage11_2_22_native_macos_smoke_20261114/output" \
  "/Users/shreyasdivekar/Documents/anc sih/antigravity/runs/stage11_2_22_native_macos_smoke_20261114/synthetic_48k_mono.wav"
```

The runtime exited `0`, loaded all three model subgraphs, logged model type `deepfilternet3` with lookahead `2`, and enhanced the file. Process wall time including startup and model loading was 0.568 s; the runtime's own enhancement log reported 0.14 s and RTF 0.0706 for the 2-second file. Neither number is a real-time streaming or Pi performance measurement.

Output: 48 kHz, mono, PCM16, 94,560 frames (1.97 s), finite by PCM representation. SHA-256: `ac6c90e0a378a7ccf80e23e1cf09484a0fc93954340c26d197f1a23982afb7de`. The 1,440-frame/30 ms reduction is expected for this file-mode command with `--compensate-delay`: `enhance_wav.rs` computes the STFT-plus-lookahead delay and slices that many samples from the beginning. It does not preserve file duration. Do not treat this CLI mode as the streaming continuity implementation.

## Failure and correction record

An initial smoke wrapper ran the native process successfully (process exit `0`) but the wrapper exited `1` because it incorrectly required the delay-compensated output to retain all 96,000 input frames. Source inspection confirmed the CLI intentionally removes 1,440 samples. The corrected wrapper expected 94,560 frames and exited `0`. This was a harness expectation error, not a model-load or inference failure. Both attempt outputs remain outside the protected benchmark; the authoritative corrected run is under `runs/stage11_2_22_native_macos_smoke_20261114/`.

## Evidence files

- `runs/stage11_2_22_native_macos_smoke_20261114/run_metadata.json`
- `runs/stage11_2_22_native_macos_smoke_20261114/stdout.log`
- `runs/stage11_2_22_native_macos_smoke_20261114/stderr.log`
- `runs/stage11_2_22_native_macos_smoke_20261114/SHA256SUMS.txt`
- Input/output synthetic WAVs in that run directory

All entries in the run's checksum list verified after the successful run. The 35 ms capture-to-headset gate, Linux ARM64 execution on physical Pi 5, ALSA behavior, thermal soak, XRUN count, and actual headset path remain unverified. No installation, network access, Kaggle access, Pi access, gold access, or upload occurred.
