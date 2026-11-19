#!/usr/bin/env python3
"""Synthetic GTCRN adapter profiling and continuous pipeline latency study."""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "experiments/stage11_2_19_bounded_audio_pipeline"))
sys.path.insert(0, str(ROOT / "experiments/stage11_2_17_gtcrn_streaming/compat"))
sys.path.insert(0, str(ROOT / "experiments/stage11_2_17_gtcrn_streaming"))
sys.path.insert(0, str(ROOT / "third_party/gtcrn_stage5"))

from bounded_pipeline import AudioChunk, BoundedGTCRNPipeline, OfferResult  # noqa: E402
from gtcrn_stream_adapter import GTCRNStreamAdapter  # noqa: E402
from concurrent_pipeline import run_concurrent_pipeline  # noqa: E402
from run_stage11_2_19 import (  # noqa: E402
    git_state,
    load_gtcrn_model,
    protected_hashes,
    rss_high_water_bytes,
    sha256,
)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def percentile(values: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=np.float64), q)) if values else 0.0


def profile_chunk_sizes(model: torch.nn.Module, seconds: int) -> list[dict[str, object]]:
    sample_rate = 16000
    total = seconds * sample_rate
    rng = np.random.default_rng(26052)
    # Low-level speech-like modulation plus deterministic broadband noise; no
    # project recordings or benchmark inputs are used.
    t = np.arange(total, dtype=np.float32) / sample_rate
    source = (0.04 * np.sin(2 * np.pi * 180 * t) * (0.65 + 0.35 * np.sin(2 * np.pi * 3 * t))
              + 0.008 * rng.standard_normal(total)).astype(np.float32)
    rows: list[dict[str, object]] = []
    for chunk_size in (64, 128, 256, 512, 1024, 2048, 4096):
        adapter = GTCRNStreamAdapter(model)
        warm = source[:sample_rate]
        for warm_start in range(0, warm.size, 4096):
            warm_stop = min(warm.size, warm_start + 4096)
            adapter.process_chunk(
                warm[warm_start:warm_stop], final=warm_stop == warm.size
            )
        adapter.reset_session()
        timings_ms: list[float] = []
        rtf_values: list[float] = []
        deadline_misses = 0
        out_samples = 0
        call_count = 0
        for start in range(0, total, chunk_size):
            stop = min(total, start + chunk_size)
            final = stop == total
            before = time.perf_counter()
            output = adapter.process_chunk(source[start:stop], final=final)
            elapsed = time.perf_counter() - before
            call_count += 1
            out_samples += int(output.size)
            n = stop - start
            duration = n / sample_rate
            timings_ms.append(elapsed * 1000)
            rtf_values.append(elapsed / duration)
            deadline_misses += int(elapsed > duration)
        if out_samples != total:
            raise RuntimeError(f"chunk profile {chunk_size}: output length {out_samples}!={total}")
        rows.append({
            "chunk_samples": chunk_size,
            "chunk_duration_ms": chunk_size / sample_rate * 1000,
            "calls": call_count,
            "audio_seconds": seconds,
            "mean_process_ms": statistics.fmean(timings_ms),
            "p95_process_ms": percentile(timings_ms, 95),
            "p99_process_ms": percentile(timings_ms, 99),
            "max_process_ms": max(timings_ms),
            "mean_rtf": statistics.fmean(rtf_values),
            "p95_rtf": percentile(rtf_values, 95),
            "p99_rtf": percentile(rtf_values, 99),
            "per_chunk_deadline_misses": deadline_misses,
            "deadline_miss_rate": deadline_misses / call_count,
            "output_samples": out_samples,
        })
    return rows


def verify_aligned_chunk_output_bound(
    model: torch.nn.Module, *, duration_s: int = 4, chunk_samples: int = 256,
) -> dict[str, object]:
    """Measure a bounded output reserve for this exact hop-aligned workload."""
    total = duration_s * 16000
    if total % chunk_samples:
        raise ValueError("preflight duration must align to chunk size")
    rng = np.random.default_rng(26053)
    t = np.arange(total, dtype=np.float32) / 16000
    source = (0.035 * np.sin(2 * np.pi * 220 * t)
              + 0.006 * rng.standard_normal(total)).astype(np.float32)
    adapter = GTCRNStreamAdapter(model)
    sizes: list[int] = []
    nonfinal_sizes: list[int] = []
    final_size = 0
    total_output = 0
    for start in range(0, total, chunk_samples):
        stop = start + chunk_samples
        output = adapter.process_chunk(source[start:stop], final=stop == total)
        sizes.append(int(output.size))
        if stop == total:
            final_size = int(output.size)
        else:
            nonfinal_sizes.append(int(output.size))
        total_output += int(output.size)
    maximum = max(sizes, default=0)
    nonfinal_max = max(nonfinal_sizes, default=0)
    if total_output != total or nonfinal_max > chunk_samples or final_size > 2 * chunk_samples:
        raise RuntimeError(
            f"aligned output reserve preflight failed: {total_output}/{total}, "
            f"nonfinal max={nonfinal_max}, final={final_size}, input chunk={chunk_samples}"
        )
    return {
        "input_samples": total,
        "input_chunk_samples": chunk_samples,
        "calls": len(sizes),
        "output_samples": total_output,
        "maximum_output_block_samples": maximum,
        "maximum_nonfinal_output_block_samples": nonfinal_max,
        "final_output_block_samples": final_size,
        "output_block_size_counts": {str(size): sizes.count(size) for size in sorted(set(sizes))},
        "nonfinal_reservation_samples": chunk_samples,
        "final_reservation_samples": 2 * chunk_samples,
        "scope": "fixed 256-sample hop-aligned chunks only; no general adapter bound asserted",
    }


def simulate_continuous_pipeline(
    model: torch.nn.Module,
    *,
    duration_s: int,
    chunk_samples: int,
    capture_capacity: int,
    playback_capacity: int,
) -> dict[str, object]:
    adapter = GTCRNStreamAdapter(model)
    return run_concurrent_pipeline(
        adapter,
        duration_s=duration_s,
        chunk_samples=chunk_samples,
        capture_capacity_samples=capture_capacity,
        playback_capacity_samples=playback_capacity,
        playback_reservation_samples=256,
        final_output_reservation_samples=512,
        seed=26053,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "runs/stage11_2_20_low_latency/run_20261114_r1")
    parser.add_argument("--profile-seconds", type=int, default=8)
    parser.add_argument("--continuous-seconds", type=int, default=4)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error(f"refusing to overwrite existing directory: {args.output_dir}")
    if args.profile_seconds < 4 or args.continuous_seconds < 2:
        parser.error("profile-seconds >=4 and continuous-seconds >=2 required")
    if args.continuous_seconds * 16000 % 256:
        parser.error("continuous-seconds must yield an integer number of 256-sample chunks")

    before = protected_hashes()
    out = args.output_dir.resolve()
    out.mkdir(parents=True)
    torch.manual_seed(26052)
    torch.set_num_threads(1)
    model = load_gtcrn_model()
    profile = profile_chunk_sizes(model, args.profile_seconds)
    output_bound_preflight = verify_aligned_chunk_output_bound(model)
    continuous = []
    # Isolate queue budgets at a fixed 256-sample (16 ms) input cadence.
    # A separate actual-adapter preflight verifies output blocks are no larger
    # than this aligned chunk size before using the tighter playback reserve.
    for label, capture_cap, playback_cap in (
        ("tight", 512, 512),
        ("medium", 1024, 1024),
        ("large", 8192, 8192),
    ):
        result = simulate_continuous_pipeline(
            model, duration_s=args.continuous_seconds, chunk_samples=256,
            capture_capacity=capture_cap, playback_capacity=playback_cap,
        )
        result["queue_profile"] = label
        continuous.append(result)
    after = protected_hashes()
    if before != after:
        raise RuntimeError("protected artifacts changed during Stage 11.2.20")

    write_csv(out / "chunk_size_profile.csv", profile)
    write_csv(out / "continuous_pipeline_results.csv", continuous)
    metadata = {
        "stage": "11.2.20",
        "scope": "synthetic software-only profiling plus actual threaded host inference and timed sink; no hardware or benchmark audio",
        "seed": 26052,
        "environment": {
            "python": sys.version,
            "numpy": np.__version__,
            "torch": torch.__version__,
            "device": "cpu",
            "threads": torch.get_num_threads(),
        },
        "command": [sys.executable, *sys.argv],
        "profile_seconds_per_chunk_size": args.profile_seconds,
        "continuous_seconds_per_queue_profile": args.continuous_seconds,
        "aligned_chunk_output_bound_preflight": output_bound_preflight,
        "protected_hashes_before": before,
        "protected_hashes_after": after,
        "git_head": git_state()["head"],
        "limitations": [
            "Producer, GTCRN inference consumer, and sink scheduler execute concurrently on this host; the paced producer can block and is not a microphone model.",
            "Playback uses a software sample-clock timer, not a physical audio device or ALSA callback.",
            "Observed delivery latency includes host scheduling; sample-clock latency is the configured playback deadline; both are host-only measurements.",
            "Synthetic input and CPU-only host timings do not establish Raspberry Pi 5 performance or end-to-end acoustic latency.",
            "No 35 ms compliance claim is made; Stage 11.2.15 gives Step-500 an estimated 49.5–54.5 ms physical latency and the GTCRN result does not qualify that DFN3 deployment path.",
        ],
    }
    (out / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    hash_files = [HERE / "run_stage11_2_20.py", HERE / "concurrent_pipeline.py"] + list(out.glob("*.csv")) + [out / "run_metadata.json"]
    (out / "SHA256SUMS.txt").write_text("".join(
        f"{sha256(path)}  {path.relative_to(ROOT)}\n" for path in hash_files
    ), encoding="utf-8")
    print(json.dumps({"output_dir": str(out), "profile": profile,
                      "continuous": continuous,
                      "protected_hashes_unchanged": before == after}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
