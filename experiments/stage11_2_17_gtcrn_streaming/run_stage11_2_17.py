#!/usr/bin/env python3
"""Synthetic chunk-equivalence, reset and host profiling experiment."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import resource
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent / "compat"))
sys.path.insert(0, str(ROOT / "third_party/gtcrn_stage5"))
from gtcrn import GTCRN  # noqa: E402
from gtcrn_stream_adapter import GTCRNStreamAdapter  # noqa: E402

CHECKPOINT = ROOT / "checkpoints/gtcrn_stage5/model_trained_on_dns3.tar"
EXPECTED_CHECKPOINT_SHA256 = "a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79"
SR = 16000
FFT = 512
HOP = 256
WINDOW = torch.hann_window(FFT).sqrt()
ATOL = 1.0e-5
RTOL = 1.0e-5
BOUNDARY_RADIUS = 128


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def load_model() -> GTCRN:
    if sha256(CHECKPOINT) != EXPECTED_CHECKPOINT_SHA256:
        raise RuntimeError("GTCRN checkpoint SHA-256 mismatch")
    model = GTCRN().cpu().eval()
    obj = torch.load(CHECKPOINT, map_location="cpu", weights_only=True)
    state = obj.get("model") if isinstance(obj, dict) else None
    result = model.load_state_dict(state, strict=True)
    if result.missing_keys or result.unexpected_keys:
        raise RuntimeError(f"strict GTCRN load failed: {result}")
    return model


@torch.inference_mode()
def full_call(model: GTCRN, audio: np.ndarray) -> np.ndarray:
    x = torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32))
    spec = torch.stft(x, FFT, HOP, FFT, WINDOW, return_complex=False)
    enhanced_spec_ri = model(spec.unsqueeze(0))[0]
    # PyTorch 2.14 requires complex input to istft. This is the exact complex
    # interpretation of the pinned model's legacy final real/imag dimension.
    enhanced_spec = torch.view_as_complex(enhanced_spec_ri.contiguous())
    y = torch.istft(enhanced_spec, FFT, HOP, FFT, WINDOW, length=len(audio), return_complex=False)
    return y.cpu().numpy().astype(np.float32, copy=False)


def make_signal(name: str, seconds: float = 1.0, seed: int = 26052) -> np.ndarray:
    n = int(seconds * SR)
    t = np.arange(n, dtype=np.float64) / SR
    rng = np.random.default_rng(seed)
    if name == "silence":
        return np.zeros(n, np.float32)
    if name == "impulses":
        x = np.zeros(n, np.float32)
        for i in [0, 159, 160, 255, 256, 4097, n // 2, n - 17]:
            if 0 <= i < n:
                x[i] = 0.9 if i % 2 else -0.9
        return x
    if name == "sinusoid":
        return (0.3 * np.sin(2 * np.pi * 440 * t) + 0.1 * np.sin(2 * np.pi * 1700 * t)).astype(np.float32)
    if name == "white_noise":
        return (rng.standard_normal(n) * 0.15).astype(np.float32)
    if name == "speech_like":
        f0 = 115.0 + 18.0 * np.sin(2 * np.pi * 2.1 * t)
        phase = 2 * np.pi * np.cumsum(f0) / SR
        env = (0.25 + 0.75 * np.maximum(0, np.sin(2 * np.pi * 3.4 * t)))
        x = env * (0.35 * np.sin(phase) + 0.22 * np.sin(2 * phase) + 0.12 * np.sin(3 * phase))
        x += 0.025 * rng.standard_normal(n)
        return x.astype(np.float32)
    if name == "high_to_silence":
        half = n // 2
        x = np.zeros(n, np.float32)
        x[:half] = (rng.standard_normal(half) * 0.6).astype(np.float32)
        return x
    raise ValueError(name)


def chunk_boundaries(n: int, mode: str) -> list[int]:
    sizes = {"10ms": 160, "16ms": 256, "20ms": 320, "32ms": 512}
    if mode in sizes:
        step = sizes[mode]
        return list(range(step, n, step))
    pattern = [137, 509, 93, 17, 777, 320, 61, 2053, 251, 48, 991]
    result, pos, j = [], 0, 0
    while pos < n:
        pos += pattern[j % len(pattern)]
        if pos < n:
            result.append(pos)
        j += 1
    return result


def stream_call(model: GTCRN, audio: np.ndarray, mode: str, profile: bool = False):
    adapter = GTCRNStreamAdapter(model)
    boundaries = chunk_boundaries(len(audio), mode)
    edges = [0] + boundaries + [len(audio)]
    outputs = []
    chunk_times, chunk_deadlines, chunk_input_sizes, chunk_output_sizes = [], [], [], []
    py_alloc_bytes = []
    input_ring_sizes, ola_ring_sizes = [], []
    tracemalloc.start()
    for j, (a, b) in enumerate(zip(edges[:-1], edges[1:])):
        chunk = audio[a:b]
        started = time.perf_counter()
        before, _ = tracemalloc.get_traced_memory()
        y = adapter.process_chunk(chunk, final=(j == len(edges) - 2))
        after, peak = tracemalloc.get_traced_memory()
        elapsed = time.perf_counter() - started
        if profile:
            py_alloc_bytes.append(max(0, after - before))
            chunk_times.append(elapsed)
            chunk_deadlines.append(elapsed > len(chunk) / SR)
            chunk_input_sizes.append(len(chunk))
            chunk_output_sizes.append(len(y))
            state = adapter.state_summary()
            input_ring_sizes.append(state["input_ring_samples"])
            ola_ring_sizes.append(state["ola_ring_samples"])
        outputs.append(y)
    _, peak_traced = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    y = np.concatenate(outputs) if outputs else np.zeros(0, np.float32)
    return y, boundaries, adapter, {
        "chunk_seconds": chunk_times,
        "deadline_misses": chunk_deadlines,
        "chunk_input_sizes": chunk_input_sizes,
        "chunk_output_sizes": chunk_output_sizes,
        "python_alloc_delta_bytes_per_chunk": py_alloc_bytes,
        "python_tracemalloc_peak_bytes": peak_traced,
        "input_ring_sizes": input_ring_sizes,
        "ola_ring_sizes": ola_ring_sizes,
    }


def signal_stats(reference: np.ndarray, actual: np.ndarray, boundaries: list[int]) -> dict:
    n = min(len(reference), len(actual))
    r = np.asarray(reference[:n], np.float64)
    a = np.asarray(actual[:n], np.float64)
    err = a - r
    p_ref = float(np.sum(r * r, dtype=np.float64))
    p_err = float(np.sum(err * err, dtype=np.float64))
    denom = float(np.linalg.norm(r) * np.linalg.norm(a))
    corr = float(np.dot(r, a) / denom) if denom > 0 else (1.0 if p_err == 0 else 0.0)
    lag_scores = []
    for lag in range(-32, 33):
        if lag < 0:
            u, v = r[-lag:], a[:n + lag]
        elif lag > 0:
            u, v = r[:n - lag], a[lag:]
        else:
            u, v = r, a
        d = float(np.linalg.norm(u) * np.linalg.norm(v))
        lag_scores.append((float(np.dot(u, v) / d) if d > 0 else 0.0, lag))
    best_corr, best_lag = max(lag_scores)
    boundary_errors = []
    for boundary in boundaries:
        lo, hi = max(0, boundary - BOUNDARY_RADIUS), min(n, boundary + BOUNDARY_RADIUS)
        if hi > lo:
            e = a[lo:hi] - r[lo:hi]
            boundary_errors.append({
                "sample": boundary,
                "rmse": float(np.sqrt(np.mean(e * e))),
                "max_abs": float(np.max(np.abs(e))),
            })
    return {
        "reference_samples": int(len(reference)),
        "stream_samples": int(len(actual)),
        "length_match": bool(len(reference) == len(actual)),
        "zero_lag_correlation": corr,
        "best_correlation_lag_search_pm32": int(best_lag),
        "best_correlation_pm32": best_corr,
        "rmse": float(np.sqrt(np.mean(err * err))) if n else 0.0,
        "max_abs_error": float(np.max(np.abs(err))) if n else 0.0,
        "waveform_sdr_db": float(10 * np.log10((p_ref + 1e-30) / (p_err + 1e-30))),
        "allclose_atol_1e-5_rtol_1e-5": bool(np.allclose(r, a, atol=ATOL, rtol=RTOL)),
        "boundary_windows": len(boundary_errors),
        "boundary_rmse_max": max((v["rmse"] for v in boundary_errors), default=0.0),
        "boundary_max_abs_max": max((v["max_abs"] for v in boundary_errors), default=0.0),
        "boundary_errors": boundary_errors,
        "startup_rmse_first_256": float(np.sqrt(np.mean(err[:min(256, n)] ** 2))) if n else 0.0,
        "final_rmse_last_256": float(np.sqrt(np.mean(err[max(0, n - 256):] ** 2))) if n else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--quick", action="store_true", help="single smoke case only")
    parser.add_argument("--long-seconds", type=float, default=20.0)
    args = parser.parse_args()
    out = args.output_dir.expanduser().resolve()
    if out.exists():
        raise SystemExit(f"Refusing to overwrite existing output directory: {out}")
    if sha256(CHECKPOINT) != EXPECTED_CHECKPOINT_SHA256:
        raise SystemExit("protected GTCRN checkpoint hash mismatch")

    torch.set_num_threads(1)
    model_load_start = time.perf_counter()
    model = load_model()
    model_load_seconds = time.perf_counter() - model_load_start
    start = time.perf_counter()
    probe = make_signal("sinusoid", 1.0)
    probe_ref = full_call(model, probe)
    probe_out, _, _, _ = stream_call(model, probe, "16ms")
    smoke = signal_stats(probe_ref, probe_out, [])
    print("SMOKE", json.dumps(smoke), flush=True)
    if args.quick:
        return 0 if smoke["length_match"] else 2

    out.mkdir(parents=True)
    chunk_modes = ["10ms", "16ms", "20ms", "32ms", "irregular"]
    signal_names = ["silence", "impulses", "sinusoid", "white_noise", "speech_like", "high_to_silence"]
    if args.quick:
        signal_names, chunk_modes = ["sinusoid"], ["16ms"]

    equivalence_rows = []
    profile_rows = []
    per_chunk_rows = []
    for signal_name in signal_names:
        duration = 2.0 if signal_name == "high_to_silence" else 1.0
        audio = make_signal(signal_name, duration)
        ref = full_call(model, audio)
        for mode in chunk_modes:
            started = time.perf_counter()
            streamed, boundaries, adapter, profile = stream_call(model, audio, mode, profile=True)
            wall = time.perf_counter() - started
            stats = signal_stats(ref, streamed, boundaries)
            equivalence_rows.append({
                "signal": signal_name,
                "chunk_mode": mode,
                "input_samples": len(audio),
                "chunk_count": len(profile["chunk_seconds"]),
                "chunk_boundaries": len(boundaries),
                **{k: v for k, v in stats.items() if k != "boundary_errors"},
                "wall_seconds_total": wall,
                "adapter_state": json.dumps(adapter.state_summary(), sort_keys=True),
            })
            times = np.asarray(profile["chunk_seconds"], np.float64)
            sizes = np.asarray(profile["chunk_input_sizes"], np.float64)
            deadlines = np.asarray(profile["deadline_misses"], bool)
            profile_rows.append({
                "signal": signal_name,
                "chunk_mode": mode,
                "chunks": len(times),
                "mean_chunk_ms": float(np.mean(times) * 1000) if len(times) else 0.0,
                "p95_chunk_ms": float(np.percentile(times, 95) * 1000) if len(times) else 0.0,
                "p99_chunk_ms": float(np.percentile(times, 99) * 1000) if len(times) else 0.0,
                "deadline_misses": int(deadlines.sum()),
                "nominal_chunk_duration_ms_mean": float(np.mean(sizes) / SR * 1000) if len(sizes) else 0.0,
                "max_input_ring_samples": adapter.max_input_ring_samples,
                "max_ola_ring_samples": adapter.max_ola_ring_samples,
                "python_tracemalloc_peak_bytes": profile["python_tracemalloc_peak_bytes"],
                "wall_seconds_total": wall,
            })
            for chunk_i, chunk_seconds in enumerate(profile["chunk_seconds"]):
                per_chunk_rows.append({
                    "signal": signal_name,
                    "chunk_mode": mode,
                    "chunk_index": chunk_i,
                    "input_samples": profile["chunk_input_sizes"][chunk_i],
                    "input_duration_ms": profile["chunk_input_sizes"][chunk_i] / SR * 1000,
                    "output_samples_finalized": profile["chunk_output_sizes"][chunk_i],
                    "execution_ms": chunk_seconds * 1000,
                    "deadline_miss": bool(profile["deadline_misses"][chunk_i]),
                    "python_alloc_delta_bytes": profile["python_alloc_delta_bytes_per_chunk"][chunk_i],
                    "input_ring_samples_after_chunk": profile["input_ring_sizes"][chunk_i],
                    "istft_overlap_ring_samples_after_chunk": profile["ola_ring_sizes"][chunk_i],
                    "output_queue_samples_after_return": 0,
                })
            print(f"DONE {signal_name} {mode} samples={len(streamed)} rmse={stats['rmse']:.3g} max={stats['max_abs_error']:.3g}", flush=True)

    # Session isolation and invalid-input recovery.
    session_a = make_signal("white_noise", 0.6, seed=3001)
    session_b = make_signal("speech_like", 0.8, seed=3002)
    limit_probe = make_signal(
        "sinusoid", GTCRNStreamAdapter.max_chunk_samples / SR, seed=3003
    )
    limit_ref = full_call(model, limit_probe)
    limit_adapter = GTCRNStreamAdapter(model)
    limit_probe_accepted = True
    try:
        limit_out = limit_adapter.process_chunk(limit_probe, final=True)
    except ValueError:
        limit_probe_accepted = False
        limit_out = np.zeros(0, np.float32)
    limit_stats = signal_stats(limit_ref, limit_out, [])
    reused = GTCRNStreamAdapter(model)
    for i in range(0, len(session_a), HOP):
        reused.process_chunk(
            session_a[i : i + HOP], final=(i + HOP >= len(session_a))
        )
    reset_start = time.perf_counter()
    reused.reset_session()
    reset_seconds = time.perf_counter() - reset_start
    b_after_reset_parts = []
    for i in range(0, len(session_b), 256):
        b_after_reset_parts.append(reused.process_chunk(session_b[i:i+256], final=(i+256 >= len(session_b))))
    b_after_reset = np.concatenate(b_after_reset_parts)
    fresh = GTCRNStreamAdapter(model)
    b_fresh_parts = []
    for i in range(0, len(session_b), 256):
        b_fresh_parts.append(fresh.process_chunk(session_b[i:i+256], final=(i+256 >= len(session_b))))
    b_fresh = np.concatenate(b_fresh_parts)
    isolation = signal_stats(b_fresh, b_after_reset, [])
    invalid = GTCRNStreamAdapter(model)
    before_invalid = invalid.state_summary()
    invalid_shape_rejected = False
    try:
        invalid.process_chunk(np.zeros((2, 8), np.float32))
    except ValueError:
        invalid_shape_rejected = True
    after_invalid_shape = invalid.state_summary()
    invalid_rejected = False
    try:
        invalid.process_chunk(np.asarray([0.0, np.nan], np.float32))
    except ValueError:
        invalid_rejected = True
    after_invalid = invalid.state_summary()
    oversized_chunk_rejected = False
    try:
        invalid.process_chunk(np.zeros(GTCRNStreamAdapter.max_chunk_samples + 1, np.float32))
    except ValueError:
        oversized_chunk_rejected = True
    after_oversized = invalid.state_summary()
    invalid_recovery_parts = []
    for i in range(0, len(session_b), 256):
        invalid_recovery_parts.append(invalid.process_chunk(session_b[i:i+256], final=(i+256 >= len(session_b))))
    invalid_recovery = np.concatenate(invalid_recovery_parts)
    invalid_recovery_stats = signal_stats(b_fresh, invalid_recovery, [])
    init_start = time.perf_counter()
    _ = GTCRNStreamAdapter(model)
    adapter_init_seconds = time.perf_counter() - init_start
    (out / "session_isolation.json").write_text(json.dumps({
        "session_a_samples": len(session_a),
        "session_b_samples": len(session_b),
        "maximum_size_chunk_samples": GTCRNStreamAdapter.max_chunk_samples,
        "maximum_size_chunk_accepted": limit_probe_accepted,
        "maximum_size_chunk_matches_reference": limit_stats,
        "reset_wall_seconds_host": reset_seconds,
        "adapter_initialization_wall_seconds_host": adapter_init_seconds,
        "session_b_after_reset_vs_fresh": isolation,
        "invalid_shape_rejected": invalid_shape_rejected,
        "state_summary_unchanged_after_shape_rejection": before_invalid == after_invalid_shape,
        "invalid_nan_rejected": invalid_rejected,
        "state_summary_unchanged_after_nan_rejection": before_invalid == after_invalid,
        "oversized_chunk_limit_samples": GTCRNStreamAdapter.max_chunk_samples,
        "oversized_chunk_rejected": oversized_chunk_rejected,
        "state_summary_unchanged_after_oversized_rejection": before_invalid == after_oversized,
        "valid_session_after_invalid_input_vs_fresh": invalid_recovery_stats,
    }, indent=2) + "\n")

    # Bounded-state soak. The input audio is generated in-place and fed in 16 ms
    # blocks; only fixed context/state and bounded overlap rings should remain.
    soak = GTCRNStreamAdapter(model)
    block = np.zeros(HOP, np.float32)
    soak_started = time.perf_counter()
    for k in range(int(args.long_seconds * SR / HOP)):
        soak.process_chunk(block, final=False)
        if k % max(1, int(SR / HOP)) == 0:
            print(f"SOAK {k * HOP / SR:.0f}s", flush=True)
    soak_summary = soak.state_summary()
    soak_wall = time.perf_counter() - soak_started

    rss_raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_rss = int(rss_raw if platform.system() == "Darwin" else rss_raw * 1024)
    metadata = {
        "verdict_components": {
            "checkpoint_sha256": sha256(CHECKPOINT),
            "strict_state_load": "PASS",
            "synthetic_trial_count": len(equivalence_rows),
            "all_lengths_match": all(r["length_match"] for r in equivalence_rows),
            "all_allclose": all(r["allclose_atol_1e-5_rtol_1e-5"] for r in equivalence_rows),
            "input_ring_within_fft_plus_internal_push": all(
                r["max_input_ring_samples"] <= FFT + GTCRNStreamAdapter.max_internal_push_samples
                for r in profile_rows
            ),
            "input_ring_bound_samples": FFT + GTCRNStreamAdapter.max_internal_push_samples,
            "session_isolation_allclose": isolation["allclose_atol_1e-5_rtol_1e-5"],
            "invalid_input_rejected_without_state_change": (
                invalid_shape_rejected and invalid_rejected
                and before_invalid == after_invalid_shape and before_invalid == after_invalid
            ),
            "oversized_chunk_rejected_without_state_change": (
                oversized_chunk_rejected and before_invalid == after_oversized
            ),
            "maximum_size_chunk_accepted_and_equivalent": (
                limit_probe_accepted and limit_stats["length_match"]
                and limit_stats["allclose_atol_1e-5_rtol_1e-5"]
            ),
        },
        "host": {
            "os": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "numpy": np.__version__,
            "soundfile": sf.__version__,
            "device": "CPU",
            "torch_num_threads": torch.get_num_threads(),
            "peak_process_rss_bytes": peak_rss,
            "model_load_seconds_host": model_load_seconds,
        },
        "audio": {"sample_rate_hz": SR, "channels": 1, "stft_n_fft": FFT, "hop_samples": HOP,
                  "window": "periodic sqrt Hann", "reference_center": True},
        "numerical_tolerance_frozen_before_run": {"atol": ATOL, "rtol": RTOL},
        "boundary_radius_samples": BOUNDARY_RADIUS,
        "long_session_soak": {
            "seconds_requested": args.long_seconds,
            "frames_processed": soak.frames_seen,
            "wall_seconds_host": soak_wall,
            "state_summary": soak_summary,
        },
        "experiment_wall_seconds": time.perf_counter() - start,
        "pooled_chunk_profile": {
            "chunks": len(per_chunk_rows),
            "mean_execution_ms": float(np.mean([r["execution_ms"] for r in per_chunk_rows])),
            "p95_execution_ms": float(np.percentile([r["execution_ms"] for r in per_chunk_rows], 95)),
            "p99_execution_ms": float(np.percentile([r["execution_ms"] for r in per_chunk_rows], 99)),
            "deadline_misses": int(sum(bool(r["deadline_miss"]) for r in per_chunk_rows)),
            "python_alloc_delta_mean_bytes": float(np.mean([r["python_alloc_delta_bytes"] for r in per_chunk_rows])),
            "max_input_ring_samples": int(max(r["max_input_ring_samples"] for r in profile_rows)),
            "max_istft_overlap_ring_samples": int(max(r["max_ola_ring_samples"] for r in profile_rows)),
            "max_output_queue_samples": 0,
        },
        "gold_accessed": False,
        "canonical_benchmark_run": False,
        "training_performed": False,
        "pi_accessed": False,
    }
    with (out / "chunk_equivalence_results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(equivalence_rows[0]))
        writer.writeheader(); writer.writerows(equivalence_rows)
    with (out / "host_profile.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(profile_rows[0]))
        writer.writeheader(); writer.writerows(profile_rows)
    with (out / "per_chunk_profile.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(per_chunk_rows[0]))
        writer.writeheader(); writer.writerows(per_chunk_rows)
    (out / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))
    required = metadata["verdict_components"]
    passed = all(required[k] for k in (
        "all_lengths_match", "all_allclose", "session_isolation_allclose",
        "invalid_input_rejected_without_state_change",
        "oversized_chunk_rejected_without_state_change",
        "maximum_size_chunk_accepted_and_equivalent",
        "input_ring_within_fft_plus_internal_push"
    ))
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
