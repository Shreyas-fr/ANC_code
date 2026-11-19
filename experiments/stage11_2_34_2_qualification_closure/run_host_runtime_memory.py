#!/usr/bin/env python3
"""
Stage 11.2.34.2: Task 1 — Host Complete Runtime Memory Measurement & Profiling.

Measures memory in a fresh isolated process:
- Cold start RSS
- Post-initialization RSS (C tables, normalizers, ONNX models loaded)
- Post-warmup RSS (after 10 frames)
- Steady-state RSS during 10,000 consecutive frames (sampled periodically)
- Memory growth / leak detection across the run
- Disaggregates static components
- Documents the standalone non-Python C executable blocker (lack of C headers)
"""

import os
import sys
import json
import time
import ctypes
import resource
import platform
from pathlib import Path
import numpy as np
import onnxruntime as ort

PROJECT_ROOT = Path("/Users/shreyasdivekar/Documents/anc sih")
ANTIGRAVITY_DIR = PROJECT_ROOT / "antigravity"
STAGE_DIR = ANTIGRAVITY_DIR / "experiments" / "stage11_2_34_2_qualification_closure"
MODELS_DIR = ANTIGRAVITY_DIR / "experiments" / "stage11_2_34_native_prototype" / "models"
NATIVE_LIB_PATH = ANTIGRAVITY_DIR / "experiments" / "stage11_2_34_native_prototype" / "c_src" / "libcandidate_b_native.dylib"

sys.path.insert(0, str(ANTIGRAVITY_DIR / "experiments" / "stage11_2_34_native_prototype"))
import native_pipeline

def get_current_rss_bytes() -> int:
    """Returns current process max resident set size in bytes on macOS."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

def format_mem(bytes_val: int) -> dict:
    return {
        "bytes": int(bytes_val),
        "mb_decimal": round(bytes_val / 1e6, 3),
        "mib_binary": round(bytes_val / (1024 * 1024), 3)
    }

def main():
    print("=" * 70)
    print("STAGE 11.2.34.2 — TASK 1: COMPLETE HOST RUNTIME MEMORY MEASUREMENT")
    print("=" * 70)

    # 1. Cold start RSS (before loading models or initializing pipeline)
    cold_rss = get_current_rss_bytes()
    print(f"1. Cold-start Process RSS:           {cold_rss / 1e6:8.2f} MB ({cold_rss / (1024*1024):8.2f} MiB)")

    # 2. Session & Pipeline Initialization
    t0 = time.perf_counter()
    pipe = native_pipeline.NativeCandidateBPipeline(MODELS_DIR)
    t_init = time.perf_counter() - t0
    post_init_rss = get_current_rss_bytes()
    print(f"2. Post-Initialization RSS:          {post_init_rss / 1e6:8.2f} MB ({post_init_rss / (1024*1024):8.2f} MiB) [Init: {t_init*1000:.1f} ms]")

    # 3. Warm-up Phase (10 frames)
    dummy_mag = np.random.randn(257).astype(np.float32) * 0.5 + 1.0
    for _ in range(10):
        _ = pipe.process_frame(dummy_mag)
    post_warmup_rss = get_current_rss_bytes()
    print(f"3. Post-Warmup RSS (10 frames):       {post_warmup_rss / 1e6:8.2f} MB ({post_warmup_rss / (1024*1024):8.2f} MiB)")

    # 4. Steady-State Streaming Execution over 10,000 Consecutive Frames
    sample_intervals = [100, 500, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000]
    frame_rss_samples = []

    print(f"Executing 10,000 frames through native C + ONNX Runtime streaming pipeline...")
    t_start_loop = time.perf_counter()
    for frame_idx in range(1, 10001):
        _ = pipe.process_frame(dummy_mag)
        if frame_idx in sample_intervals:
            rss_now = get_current_rss_bytes()
            frame_rss_samples.append({
                "frame": frame_idx,
                "rss": format_mem(rss_now)
            })
            print(f"   Frame {frame_idx:5d} RSS: {rss_now / 1e6:8.2f} MB ({rss_now / (1024*1024):8.2f} MiB)")

    t_total_loop = time.perf_counter() - t_start_loop
    final_rss = get_current_rss_bytes()
    print(f"4. Final Steady-State RSS (10k frames): {final_rss / 1e6:8.2f} MB ({final_rss / (1024*1024):8.2f} MiB) [Time: {t_total_loop:.2f} s, {t_total_loop*1000/10000:.3f} ms/frame]")

    # 5. Memory Growth Analysis
    rss_f100 = frame_rss_samples[0]["rss"]["bytes"]
    rss_f10k = frame_rss_samples[-1]["rss"]["bytes"]
    growth_bytes = rss_f10k - rss_f100
    print(f"5. Memory Growth (Frame 100 -> 10,000): {growth_bytes / 1e6:8.2f} MB ({growth_bytes / (1024*1024):8.2f} MiB) [Status: {'ZERO GROWTH' if growth_bytes == 0 else f'Delta {growth_bytes} bytes'}]")

    # 6. Static Component Disaggregation
    fb_onnx_size = (MODELS_DIR / "fullband_step.onnx").stat().st_size
    sb_onnx_size = (MODELS_DIR / "subband_step.onnx").stat().st_size
    fb_recurrent = 2 * 1 * 512 * 4 * 2
    sb_recurrent = 2 * 257 * 384 * 4 * 2
    dsp_buffers = 4096 + 2048 + 2048 + 2048

    results = {
        "task": "Task 1: Complete Host Runtime Memory Measurement",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": sys.version,
            "onnxruntime_version": ort.__version__,
            "intra_op_threads": 1,
            "inter_op_threads": 1,
        },
        "measured_memory": {
            "cold_start_rss": format_mem(cold_rss),
            "post_initialization_rss": format_mem(post_init_rss),
            "post_warmup_rss": format_mem(post_warmup_rss),
            "final_steady_state_rss_10k": format_mem(final_rss),
            "peak_rss": format_mem(final_rss),
            "memory_growth_f100_to_f10000": format_mem(growth_bytes),
            "samples": frame_rss_samples,
        },
        "performance": {
            "init_time_seconds": t_init,
            "total_loop_seconds": t_total_loop,
            "mean_frame_time_ms": (t_total_loop * 1000.0) / 10000.0,
            "real_time_factor": ((t_total_loop * 1000.0) / 10000.0) / 16.0,
        },
        "static_components": {
            "fullband_onnx_weights": format_mem(fb_onnx_size),
            "subband_onnx_weights": format_mem(sb_onnx_size),
            "total_model_weights": format_mem(fb_onnx_size + sb_onnx_size),
            "fullband_recurrent_state": format_mem(fb_recurrent),
            "subband_recurrent_state": format_mem(sb_recurrent),
            "total_recurrent_state": format_mem(fb_recurrent + sb_recurrent),
            "dsp_buffers": format_mem(dsp_buffers),
            "total_static_theoretical": format_mem(fb_onnx_size + sb_onnx_size + fb_recurrent + sb_recurrent + dsp_buffers),
        },
        "governance_disposition": {
            "gate_01_standalone_non_python_binary": "INCONCLUSIVE",
            "blocker_description": (
                "ONNX Runtime C/C++ development headers (onnxruntime_c_api.h) are not bundled in the "
                "standard pip wheel distribution (onnxruntime 1.32.0). Under stage execution constraints "
                "(strict offline execution with no network access and no package installations), external "
                "C SDK headers cannot be downloaded. Compiling a standalone non-Python C executable would require "
                "unverified manual reverse-engineering of the 150+ function pointer layout in the OrtApi struct, "
                "which violates forensic rigor. Per instruction guidelines, Gate 01 is marked INCONCLUSIVE."
            ),
            "host_runtime_measured_fact": (
                f"The complete host runtime driver executing native C DSP + ONNX Runtime models over 10,000 frames "
                f"settles at {final_rss / 1e6:.2f} MB ({final_rss / (1024*1024):.2f} MiB) RSS with exactly "
                f"{growth_bytes} bytes of memory growth between frame 100 and frame 10,000."
            )
        }
    }

    out_json = STAGE_DIR / "task1_host_runtime_memory.json"
    with open(out_json, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nTask 1 results written to: {out_json}")

if __name__ == "__main__":
    main()

