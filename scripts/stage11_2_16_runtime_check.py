#!/usr/bin/env python3
"""Compare corrected PyTorch and host-native Tract file outputs for frozen weights."""
from __future__ import annotations

import argparse
import configparser
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import types
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

EXPECTED_STEP500_SHA256 = "bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27"
EXPECTED_STEP500_ARCHIVE_SHA256 = "99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def install_torchaudio_shim() -> None:
    import torchaudio
    if getattr(getattr(torchaudio, "backend", None), "common", None) is not None:
        return
    common = types.ModuleType("torchaudio.backend.common")

    class AudioMetaData:
        def __init__(self, sample_rate, num_frames, num_channels, bits_per_sample, encoding):
            self.sample_rate = sample_rate
            self.num_frames = num_frames
            self.num_channels = num_channels
            self.bits_per_sample = bits_per_sample
            self.encoding = encoding

    common.AudioMetaData = AudioMetaData
    backend = types.ModuleType("torchaudio.backend")
    backend.common = common
    sys.modules["torchaudio.backend"] = backend
    sys.modules["torchaudio.backend.common"] = common
    torchaudio.backend = backend


def config_from_archive(archive: Path, output: Path, zero_lookahead: bool) -> Path:
    with tarfile.open(archive, "r:gz") as tf:
        members = [m for m in tf.getmembers() if m.name.endswith("config.ini")]
        if len(members) != 1:
            raise RuntimeError(f"Expected exactly one config.ini in {archive}")
        raw = tf.extractfile(members[0]).read()
    cfg = configparser.ConfigParser()
    cfg.read_string(raw.decode("utf-8"))
    if zero_lookahead:
        cfg.set("deepfilternet", "conv_lookahead", "0")
        cfg.set("df", "df_lookahead", "0")
    output.mkdir(parents=True)
    path = output / "config.ini"
    with path.open("w", encoding="utf-8") as f:
        cfg.write(f)
    return path


def load_state(path: Path):
    state = torch.load(path, map_location="cpu", weights_only=True)
    if isinstance(state, dict) and "model_state_dict" in state:
        state = state["model_state_dict"]
    if isinstance(state, dict) and state and all(k.startswith("model.") for k in list(state)[:3]):
        state = {k[len("model."):]: v for k, v in state.items()}
    return state


def init_model(config_path: Path, checkpoint: Path):
    install_torchaudio_shim()
    from df.enhance import init_df

    model, state, _ = init_df(str(config_path.parent), log_file=None, epoch="none", config_allow_defaults=True)
    model = model.cpu().eval()
    result = model.load_state_dict(load_state(checkpoint), strict=True)
    if result.missing_keys or result.unexpected_keys:
        raise RuntimeError(f"Non-strict checkpoint load: {result}")
    return model, state


def synthetic_input(seconds: float = 2.0, sr: int = 48000) -> np.ndarray:
    n = int(seconds * sr)
    t = np.arange(n, dtype=np.float64) / sr
    envelope = 0.5 * (1.0 + np.sin(2.0 * np.pi * 4.0 * t))
    clean = envelope * (
        0.5 * np.sin(2.0 * np.pi * 150.0 * t)
        + 0.3 * np.sin(2.0 * np.pi * 300.0 * t)
        + 0.2 * np.sin(2.0 * np.pi * 600.0 * t)
        + 0.15 * np.sin(2.0 * np.pi * 1200.0 * t)
        + 0.1 * np.sin(2.0 * np.pi * 2400.0 * t)
    )
    rng = np.random.default_rng(26052)
    noise = rng.standard_normal(n)
    noise *= np.sqrt(np.mean(clean**2) / (10.0 ** (5.0 / 10.0) * np.mean(noise**2)))
    mixture = clean + noise
    mixture *= 0.891 / np.max(np.abs(mixture))
    return mixture.astype(np.float32)


def waveform_metrics(ref: np.ndarray, estimate: np.ndarray) -> dict[str, float | int]:
    n = min(len(ref), len(estimate))
    ref = np.asarray(ref[:n], dtype=np.float64)
    estimate = np.asarray(estimate[:n], dtype=np.float64)
    size = 1 << (len(ref) + len(estimate) - 2).bit_length()
    corr = np.fft.irfft(
        np.fft.rfft(ref, size) * np.fft.rfft(estimate[::-1], size), size
    )[: len(ref) + len(estimate) - 1]
    lag = int(np.argmax(corr) - (len(estimate) - 1))
    if lag > 0:
        a, b = ref[lag:], estimate[:len(ref) - lag]
    elif lag < 0:
        a, b = ref[:len(ref) + lag], estimate[-lag:]
    else:
        a, b = ref, estimate
    def calc(x: np.ndarray, y: np.ndarray) -> dict[str, float]:
        x64 = np.array(x, dtype=np.float64, copy=True)
        y64 = np.array(y, dtype=np.float64, copy=True)
        err = np.subtract(y64, x64)
        err_sq = np.square(err)
        p_ref = float(np.sum(np.square(x64), dtype=np.float64))
        p_err = float(np.sum(err_sq, dtype=np.float64))
        rmse = float(np.sqrt(np.mean(err_sq, dtype=np.float64)))
        max_abs = float(np.max(np.abs(err)))
        max_abs_after_power = float(np.max(np.abs(err)))
        corrcoef = float(np.corrcoef(x64.copy(), y64.copy())[0, 1])
        return {
            "sdr_db": float(10.0 * np.log10((p_ref + 1e-30) / (p_err + 1e-30))),
            "rmse": rmse,
            "max_abs_error": max_abs,
            "max_abs_after_power_calculation": max_abs_after_power,
            "pearson_r": corrcoef,
            "error_sq_max": float(np.max(err_sq)),
        }
    return {
        "sample_count": int(n),
        "correlation_lag_samples": lag,
        "correlation_lag_ms_at_48k": 1000.0 * lag / 48000.0,
        "unaligned": calc(ref, estimate),
        "lag_aligned": calc(a, b),
    }


def pytorch_enhance(model, state, audio: np.ndarray) -> tuple[np.ndarray, float]:
    from df.enhance import enhance

    state.reset()
    start = time.perf_counter()
    with torch.inference_mode():
        y = enhance(model, state, torch.from_numpy(audio).unsqueeze(0), pad=True)
    return y.squeeze(0).cpu().numpy().astype(np.float32), time.perf_counter() - start


def run_native(binary: Path, archive: Path, input_wav: Path, output_dir: Path) -> tuple[np.ndarray, float]:
    output_dir.mkdir()
    start = time.perf_counter()
    result = subprocess.run(
        [str(binary), "-m", str(archive), "-o", str(output_dir), "-D", str(input_wav)],
        check=False, text=True, capture_output=True,
    )
    elapsed = time.perf_counter() - start
    if result.returncode != 0:
        raise RuntimeError(f"Host Tract command failed exit={result.returncode}: {result.stderr[-2000:]}")
    output = output_dir / input_wav.name
    if not output.is_file():
        raise FileNotFoundError(f"Native binary did not create {output}; stderr={result.stderr[-1000:]}")
    y, sr = sf.read(output, dtype="float32")
    if sr != 48000 or y.ndim != 1 or not np.isfinite(y).all():
        raise RuntimeError(f"Invalid native output: sr={sr}, shape={y.shape}, finite={np.isfinite(y).all()}")
    return y, elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--baseline-archive", type=Path, default=Path("../models/dfn3_step500_tract.tar.gz")
    )
    parser.add_argument(
        "--native-binary",
        type=Path,
        default=Path("runs/sih26052_rpi_deployment_audit/runs/dfn3_pi_optimization/DeepFilterNet/target/release/deep-filter"),
    )
    args = parser.parse_args()
    run_dir = args.run_dir.expanduser().resolve()
    output = args.output_dir.expanduser().resolve() if args.output_dir else run_dir / "runtime_waveform_check"
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing runtime check: {output}")
    baseline_archive = args.baseline_archive.expanduser().resolve()
    binary = args.native_binary.expanduser().resolve()
    checkpoint = run_dir / "causal_step500_weights.pt"
    candidate_archive = run_dir / "causal_step500_tract.tar.gz"
    for p in (baseline_archive, binary, checkpoint, candidate_archive):
        if not p.is_file():
            raise FileNotFoundError(p)
    if sha256(baseline_archive) != EXPECTED_STEP500_ARCHIVE_SHA256:
        raise RuntimeError("Protected baseline archive hash mismatch")
    if sha256(checkpoint) != EXPECTED_STEP500_SHA256:
        raise RuntimeError("Candidate weights differ from protected Step-500 bytes")

    output.mkdir(parents=True)
    base_cfg_dir = output / "baseline_config"
    base_cfg = config_from_archive(baseline_archive, base_cfg_dir, zero_lookahead=False)
    causal_cfg = run_dir / "model_config" / "config.ini"
    base_model, base_state = init_model(base_cfg, checkpoint)
    causal_model, causal_state = init_model(causal_cfg, checkpoint)

    input_wave = synthetic_input()
    input_path = output / "synthetic_input_float.wav"
    sf.write(input_path, input_wave, 48000, subtype="FLOAT")
    shared_input, sr = sf.read(input_path, dtype="float32")
    if sr != 48000 or not np.array_equal(shared_input, input_wave):
        raise RuntimeError("Shared float input roundtrip changed samples")

    results = {
        "purpose": "Host-native waveform regression only; not Raspberry Pi measurement",
        "input": {
            "path": str(input_path),
            "sha256": sha256(input_path),
            "sample_rate_hz": sr,
            "samples": int(len(shared_input)),
            "subtype": "FLOAT",
            "same_float_waveform_for_pytorch_and_native": True,
        },
        "baseline_step500": {},
        "causal_candidate": {},
    }
    for label, model, state, package in [
        ("baseline_step500", base_model, base_state, baseline_archive),
        ("causal_candidate", causal_model, causal_state, candidate_archive),
    ]:
        py, py_sec = pytorch_enhance(model, state, shared_input)
        state.reset()
        py_repeat, repeat_sec = pytorch_enhance(model, state, shared_input)
        if py.shape != shared_input.shape or py_repeat.shape != py.shape:
            raise RuntimeError(f"{label} PyTorch output length mismatch: {py.shape}")
        repeat_max = float(np.max(np.abs(py.astype(np.float64) - py_repeat.astype(np.float64))))
        if not np.isfinite(py).all() or repeat_max > 1e-6:
            raise RuntimeError(f"{label} PyTorch determinism/finite check failed; repeat max={repeat_max}")
        py_path = output / f"{label}_pytorch.wav"
        sf.write(py_path, py, 48000, subtype="FLOAT")
        native, native_sec = run_native(
            binary, package, input_path, output / f"{label}_native_out"
        )
        native_path = output / f"{label}_native.wav"
        shutil.copyfile(output / f"{label}_native_out" / input_path.name, native_path)
        results[label] = {
            "package_sha256": sha256(package),
            "pytorch_output_sha256": sha256(py_path),
            "native_output_sha256": sha256(native_path),
            "pytorch_wall_seconds_host": py_sec,
            "pytorch_repeat_wall_seconds_host": repeat_sec,
            "native_wall_seconds_host": native_sec,
            "pytorch_output_samples": int(len(py)),
            "native_output_samples": int(len(native)),
            "native_output_shortfall_samples": int(len(py) - len(native)),
            "native_output_shortfall_ms_at_48k": 1000.0 * (len(py) - len(native)) / 48000.0,
            "waveform_metric_span": "shared initial samples; no shift or padding applied",
            "pytorch_reset_repeat_max_abs_delta": repeat_max,
            "pytorch_vs_native": waveform_metrics(py, native),
        }

    result_path = output / "summary.json"
    result_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))
    print(f"WROTE={result_path}")


if __name__ == "__main__":
    main()
