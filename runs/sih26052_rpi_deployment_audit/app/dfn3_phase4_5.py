#!/usr/bin/env python3
"""
Phase 4 — Functional Equivalence Test
Compares:
  A) Native PyTorch DeepFilterNet3 (via df.enhance)
  B) Native Rust/Tract DeepFilterNet3 (via the compiled deep-filter binary)

Phase 5 — State Persistence Test
Runs three variants:
  A) PyTorch persistent state (same as Phase 4 A)
  B) Rust/Tract persistent state (same as Phase 4 B)
  C) PyTorch with state reset every frame (diagnostic)

Run as:
  python3 dfn3_phase4_5.py --binary ~/sih26052_edge/runs/dfn3_pi_optimization/DeepFilterNet/libDF/target/release/deep-filter \\
                            --model ~/.cache/DeepFilterNet/DeepFilterNet3 \\
                            --input ~/sih26052_edge/audio/test_deterministic_48k_10s.wav
"""
import argparse
import os
import subprocess
import time
import warnings
from pathlib import Path

import numpy as np
import soundfile as sf

# ── stdlib shim for torchaudio.backend (not needed on Pi env, but harmless) ──
import sys, types
try:
    import torchaudio
    if not hasattr(getattr(torchaudio, "backend", None), "common"):
        _cm = types.ModuleType("torchaudio.backend.common")
        _cm.AudioMetaData = type("AudioMetaData", (), {})
        sys.modules["torchaudio.backend.common"] = _cm
        if not hasattr(torchaudio, "backend"):
            _bm = types.ModuleType("torchaudio.backend")
            _bm.common = _cm
            sys.modules["torchaudio.backend"] = _bm
            torchaudio.backend = _bm
        else:
            torchaudio.backend.common = _cm
except ImportError:
    pass

import torch
from df.enhance import enhance, init_df
from libdf import DF as DFState


def rms(x):     return float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
def peak(x):    return float(np.abs(x).max())
def si_sdr(ref, est):
    ref = ref - ref.mean();  est = est - est.mean()
    alpha = np.dot(ref, est) / (np.dot(ref, ref) + 1e-9)
    proj  = alpha * ref
    noise = est - proj
    return float(10 * np.log10((np.dot(proj, proj) + 1e-9) / (np.dot(noise, noise) + 1e-9)))


# ────────────────────────────────────────────────────────────────────
# PyTorch streaming inference (persistent state via df_state)
# ────────────────────────────────────────────────────────────────────
def run_pytorch_streaming(audio_np: np.ndarray, model, df_state, reset_every_frame=False) -> np.ndarray:
    """Frame-by-frame PyTorch DFN3 inference using the enhance() single-frame path."""
    from df.enhance import df_features
    import torch

    hop = df_state.hop_size()
    sr  = df_state.sr()
    n_frames = len(audio_np) // hop
    out_chunks = []

    # Warm-up: 2 lookahead frames (lookahead=1 for DFN3, we skip 2 output frames)
    WARMUP_FRAMES = 2

    with torch.no_grad():
        for i in range(n_frames):
            chunk = audio_np[i * hop: (i + 1) * hop].astype(np.float32)
            chunk_2d = chunk[np.newaxis, :]  # [1, hop]

            if reset_every_frame:
                df_state.reset()

            spec = df_state.analysis(chunk_2d)               # [1, 1, F] complex
            spec_t = torch.from_numpy(spec[:, np.newaxis, :, :])  # [1, 1, 1, F]

            from df.enhance import df_features
            feat_erb_np, feat_spec_np = _extract_features(chunk_2d, df_state)
            feat_erb  = torch.from_numpy(feat_erb_np)
            feat_spec = torch.from_numpy(feat_spec_np)

            enh_spec, _, _, _ = model(spec_t, feat_erb, feat_spec)

            from df.utils import as_complex
            enh_c = as_complex(enh_spec.squeeze(1))    # [1, 1, F]
            out = df_state.synthesis(enh_c.detach().numpy())  # [1, hop]
            out_chunks.append(out[0])

    audio_out = np.concatenate(out_chunks)
    return audio_out


def _extract_features(chunk_2d, df_state):
    """Extract ERB + spec features for a single frame."""
    from libdf import erb as erb_fn, erb_norm, unit_norm, unit_norm_init
    import numpy as np

    # We call df_state.analysis() which updates internal state
    spec = df_state.analysis(chunk_2d)           # [1, 1, F] complex
    erb_widths = df_state.erb_widths()

    # ERB features
    feat_erb = erb_fn(spec, erb_widths, True)    # [1, 1, 1, nb_erb]

    # Unit-norm spec features for df decoder (first nb_df freqs)
    nb_df = 96
    spec_df = spec[:, :, :nb_df]                # [1, 1, nb_df] complex
    feat_spec_r = spec_df.real[:, :, :, np.newaxis]  # add last dim
    feat_spec_i = spec_df.imag[:, :, :, np.newaxis]
    feat_spec = np.concatenate([feat_spec_r, feat_spec_i], axis=-1)  # [1,1,1,nb_df,2]

    return feat_erb, feat_spec


# ────────────────────────────────────────────────────────────────────
# Rust/Tract inference via compiled binary
# ────────────────────────────────────────────────────────────────────
def run_rust_tract(binary: str, input_wav: str, output_wav: str, model_tar: str = None) -> None:
    cmd = [binary, "--output-dir", str(Path(output_wav).parent)]
    if model_tar:
        cmd += ["--model", model_tar]
    cmd.append(input_wav)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("STDERR:", result.stderr)
        raise RuntimeError(f"Rust binary failed (code {result.returncode})")


# ────────────────────────────────────────────────────────────────────
# Full enhance path (for Phase 4 reference — full audio)
# ────────────────────────────────────────────────────────────────────
def run_pytorch_full_enhance(audio_np: np.ndarray, model, df_state, sr: int) -> np.ndarray:
    import torch
    audio_t = torch.from_numpy(audio_np[np.newaxis, :].astype(np.float32))
    with torch.no_grad():
        enh = enhance(model, df_state, audio_t)
    return enh.squeeze().numpy()


# ────────────────────────────────────────────────────────────────────
# Report helpers
# ────────────────────────────────────────────────────────────────────
def report_metrics(label_a, a, label_b, b, skip_samples=0):
    a = a[skip_samples:]; b = b[skip_samples:]
    min_len = min(len(a), len(b))
    a = a[:min_len]; b = b[:min_len]

    corr = float(np.corrcoef(a, b)[0, 1]) if min_len > 1 else float("nan")
    rms_err = float(np.sqrt(np.mean((a - b) ** 2)))
    max_err  = float(np.abs(a - b).max())
    sdr      = si_sdr(a, b)

    print(f"\n── {label_a} vs {label_b} ──")
    print(f"  Samples compared : {min_len}  (warmup skipped: {skip_samples})")
    print(f"  {label_a} RMS   : {rms(a):.6f}   Peak: {peak(a):.6f}")
    print(f"  {label_b} RMS   : {rms(b):.6f}   Peak: {peak(b):.6f}")
    print(f"  Waveform corr    : {corr:.6f}")
    print(f"  RMS error        : {rms_err:.8f}")
    print(f"  Max abs error    : {max_err:.8f}")
    print(f"  SI-SDR           : {sdr:.2f} dB")

    # Gates
    eq_pass = (corr >= 0.999 and sdr >= 50.0 and np.isfinite(a).all() and np.isfinite(b).all())
    print(f"  Equivalence gate : {'PASS ✓' if eq_pass else 'FAIL ✗'}")
    return {
        "corr": corr, "rms_err": rms_err, "max_err": max_err,
        "si_sdr": sdr, "pass": eq_pass, "n": min_len
    }


# ────────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True, help="Path to compiled deep-filter Rust binary")
    ap.add_argument("--model-tar", default=None, help="Path to model .tar.gz (optional, uses bundled default if omitted)")
    ap.add_argument("--model-dir", default="DeepFilterNet3", help="Model name for init_df (default: DeepFilterNet3)")
    ap.add_argument("--input", required=True, help="Input WAV (48 kHz mono)")
    ap.add_argument("--out-dir", default=os.path.expanduser("~/sih26052_edge/runs/dfn3_pi_optimization/native_tract/"),
                    help="Output directory for results")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    # Load audio
    audio_np, sr = sf.read(args.input, dtype="float32", always_2d=False)
    assert sr == 48000, f"Expected 48 kHz input, got {sr} Hz"
    assert audio_np.ndim == 1, "Expected mono audio"
    print(f"Input: {args.input}  ({len(audio_np)/sr:.2f}s @ {sr} Hz)")

    # ── A: PyTorch full enhance ──────────────────────────────────────
    print("\n[A] Running PyTorch DeepFilterNet3 full enhance...")
    model_pt, df_state_pt, _ = init_df(args.model_dir, log_level="WARNING")
    t0 = time.perf_counter()
    pt_audio = run_pytorch_full_enhance(audio_np, model_pt, df_state_pt, sr)
    pt_wall = time.perf_counter() - t0
    print(f"    Done in {pt_wall:.2f}s  RTF={pt_wall/(len(audio_np)/sr):.3f}")
    pt_out_path = os.path.join(args.out_dir, "phase4_pytorch_out.wav")
    sf.write(pt_out_path, pt_audio, sr, subtype="PCM_16")
    print(f"    Saved: {pt_out_path}")

    assert np.isfinite(pt_audio).all(), "PyTorch output contains NaN/Inf!"
    print(f"    PyTorch RMS={rms(pt_audio):.6f}  Peak={peak(pt_audio):.6f}")

    # ── B: Rust/Tract via binary ─────────────────────────────────────
    print("\n[B] Running Rust/Tract DeepFilterNet3...")
    rust_out_path = os.path.join(args.out_dir, os.path.basename(args.input))
    t0 = time.perf_counter()
    run_rust_tract(args.binary, args.input, rust_out_path, model_tar=args.model_tar)
    rust_wall = time.perf_counter() - t0
    print(f"    Done in {rust_wall:.2f}s")

    rust_audio, rust_sr = sf.read(rust_out_path, dtype="float32", always_2d=False)
    assert rust_sr == sr, f"Rust output SR mismatch: {rust_sr} vs {sr}"
    assert np.isfinite(rust_audio).all(), "Rust/Tract output contains NaN/Inf!"
    print(f"    Rust RMS={rms(rust_audio):.6f}  Peak={peak(rust_audio):.6f}")
    print(f"    Rust out len={len(rust_audio)}  PT out len={len(pt_audio)}")

    # ── Delay alignment ──────────────────────────────────────────────
    # Tract's pulse model introduces delay = (fft_size - hop_size) + df_lookahead * hop_size
    # = (960 - 480) + 2 * 480 = 1440 samples = 30 ms
    # Rust output is shifted RIGHT by delay (first delay samples are fill-in).
    # PyTorch enhance() processes all at once — no streaming delay.
    # We detect lag via cross-correlation to be robust.
    xcorr = np.correlate(rust_audio[:48000], pt_audio[:48000], mode="full")
    auto_lag = int(np.argmax(np.abs(xcorr))) - (48000 - 1)
    print(f"  Auto-detected delay: {auto_lag} samples ({auto_lag/sr*1000:.1f} ms)")
    DELAY_SAMPLES = max(0, auto_lag)  # always positive: rust output is delayed

    # Align: skip first DELAY_SAMPLES from Rust, compare against PyTorch from the start
    rust_aligned = rust_audio[DELAY_SAMPLES:]
    pt_trimmed   = pt_audio[:len(rust_aligned)]

    # ── Phase 4 equivalence ──────────────────────────────────────────
    print("\n═══ PHASE 4 — EQUIVALENCE TEST ═══")
    print(f"  (Delay-compensated: skip first {DELAY_SAMPLES} samples from Rust / {DELAY_SAMPLES/sr*1000:.1f} ms)")
    phase4 = report_metrics("PyTorch", pt_trimmed, "Rust/Tract", rust_aligned, skip_samples=0)

    # ── C: PyTorch with state reset every frame (diagnostic) ─────────
    print("\n[C] Running PyTorch with state reset every frame (diagnostic)...")
    warnings.filterwarnings("ignore")
    model_c, df_state_c, _ = init_df(args.model_dir, log_level="WARNING")

    hop = df_state_c.hop_size()
    n_frames = len(audio_np) // hop
    reset_chunks = []
    with torch.no_grad():
        for i in range(n_frames):
            chunk = audio_np[i * hop:(i + 1) * hop][np.newaxis, :].astype(np.float32)
            df_state_c.reset()
            audio_chunk_t = torch.from_numpy(chunk)
            enh_chunk = enhance(model_c, df_state_c, audio_chunk_t)
            reset_chunks.append(enh_chunk.squeeze().numpy())
    reset_audio = np.concatenate(reset_chunks)

    reset_out_path = os.path.join(args.out_dir, "phase5_pytorch_reset_state.wav")
    sf.write(reset_out_path, reset_audio, sr, subtype="PCM_16")

    # ── Phase 5 state persistence ─────────────────────────────────────
    print("\n═══ PHASE 5 — STATE PERSISTENCE TEST ═══")
    print("A vs B: PyTorch (persistent) vs Rust/Tract (persistent)")
    phase5_ab = report_metrics("PyTorch[persist]", pt_trimmed, "Rust[persist]", rust_aligned)

    print("\nA vs C: PyTorch (persistent) vs PyTorch (reset-each-frame)")
    rc_trimmed = reset_audio[:len(pt_trimmed)]
    phase5_ac = report_metrics("PyTorch[persist]", pt_trimmed, "PyTorch[reset]", rc_trimmed)

    # Expected: A vs B should be close (state preserved), A vs C should diverge
    state_ok = (phase5_ab["corr"] >= 0.999) and (phase5_ac["corr"] < 0.99)
    print(f"\n  State persistence gate: {'PASS ✓' if state_ok else 'PARTIAL/FAIL ✗'}")
    print(f"  (A-B corr={phase5_ab['corr']:.4f} should be ≥0.999, "
          f"A-C corr={phase5_ac['corr']:.4f} should be <0.99)")

    # ── Final summary ─────────────────────────────────────────────────
    print("\n" + "=" * 50)
    print("PHASE 4 EQUIVALENCE RESULT")
    print(f"  corr   : {phase4['corr']:.6f}")
    print(f"  SI-SDR : {phase4['si_sdr']:.2f} dB")
    print(f"  Gate   : {'PASS ✓' if phase4['pass'] else 'FAIL ✗'}")
    print("\nPHASE 5 STATE PERSISTENCE RESULT")
    print(f"  A-B corr : {phase5_ab['corr']:.6f}  SI-SDR={phase5_ab['si_sdr']:.2f} dB")
    print(f"  A-C corr : {phase5_ac['corr']:.6f}  SI-SDR={phase5_ac['si_sdr']:.2f} dB")
    print(f"  Gate     : {'PASS ✓' if state_ok else 'FAIL ✗'}")
    print("=" * 50)

    # Write markdown report
    report = f"""# Phase 4 & 5 Report

## Phase 4 — Equivalence

| Metric | Value |
|--------|-------|
| Waveform correlation | {phase4['corr']:.6f} |
| RMS error | {phase4['rms_err']:.8f} |
| Max absolute error | {phase4['max_err']:.8f} |
| SI-SDR | {phase4['si_sdr']:.2f} dB |
| Gate | {'PASS' if phase4['pass'] else 'FAIL'} |

Warmup skipped: {DELAY_SAMPLES} samples ({DELAY_SAMPLES/sr*1000:.1f} ms)

## Phase 5 — State Persistence

| Comparison | Corr | SI-SDR | Interpretation |
|------------|------|--------|----------------|
| A(PT persist) vs B(Rust persist) | {phase5_ab['corr']:.6f} | {phase5_ab['si_sdr']:.2f} dB | Should be ≥0.999 |
| A(PT persist) vs C(PT reset/frame) | {phase5_ac['corr']:.6f} | {phase5_ac['si_sdr']:.2f} dB | Should be <0.99 |

State persistence gate: {'PASS' if state_ok else 'FAIL'}
"""
    report_path = os.path.join(args.out_dir, "native_vs_pytorch_equivalence.md")
    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport written: {report_path}")


if __name__ == "__main__":
    main()
