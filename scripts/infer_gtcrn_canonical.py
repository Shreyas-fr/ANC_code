#!/usr/bin/env python3
"""Run pinned official GTCRN inference only on the frozen canonical set.

Scoring is performed separately with the existing canonical metrics function.
This runner writes enhanced float WAVs and inference/runtime metadata; it does
not modify the evaluator or the benchmark manifest.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import resource
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "third_party/gtcrn_stage5"
CHECKPOINT = ROOT / "checkpoints/gtcrn_stage5/model_trained_on_dns3.tar"
MANIFEST_SHA256 = "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4"
CHECKPOINT_SHA256 = "a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79"
SOURCE_SHA256 = "d1ad0784ec14ad9abe10b1a0e08e4a68ed9fb104c5e79c6729a305db55cebeac"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def source_snapshot_sha256() -> str:
    h = hashlib.sha256()
    paths = [SOURCE_DIR / "gtcrn.py", SOURCE_DIR / "LICENSE", SOURCE_DIR / "requirements.txt"]
    for path in paths:
        data = path.read_bytes()
        rel = path.relative_to(ROOT).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(str(len(data)).encode("ascii"))
        h.update(b"\0")
        h.update(data)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-dir", type=Path, default=ROOT / "runs/sih26052_canonical_validation")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    canonical = args.canonical_dir.expanduser().resolve()
    if any(part.casefold() == "sih_gold_test" for part in canonical.parts):
        raise SystemExit(f"Refusing gold path: {canonical}")
    manifest = canonical / "manifest.csv"
    if file_sha256(manifest) != MANIFEST_SHA256:
        raise SystemExit("Frozen canonical manifest hash mismatch")
    if file_sha256(CHECKPOINT) != CHECKPOINT_SHA256:
        raise SystemExit("Pinned GTCRN checkpoint hash mismatch")
    if source_snapshot_sha256() != SOURCE_SHA256:
        raise SystemExit("Pinned GTCRN source snapshot hash mismatch")
    rows = list(csv.DictReader(manifest.open(newline="", encoding="utf-8")))
    if len(rows) != 590 or [int(row["val_index"]) for row in rows] != list(range(590)):
        raise SystemExit("Canonical manifest is not the expected ordered 590 rows")

    output_dir = args.output_dir.expanduser().resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    predictions = output_dir / "predictions"
    predictions.mkdir()

    sys.path.insert(0, str(SOURCE_DIR))
    from gtcrn import GTCRN

    load_start = time.perf_counter()
    model = GTCRN().cpu().eval()
    checkpoint = torch.load(CHECKPOINT, map_location="cpu")
    load_result = model.load_state_dict(checkpoint["model"], strict=True)
    model_load_seconds = time.perf_counter() - load_start
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    window = torch.hann_window(512).pow(0.5)

    inference_rows: list[dict[str, object]] = []
    infer_seconds_sum = 0.0
    audio_duration = 0.0
    loop_start = time.perf_counter()
    for position, row in enumerate(rows, start=1):
        index = int(row["val_index"])
        noisy_path = canonical / "noisy_audio" / f"{index:04d}_noisy.wav"
        noisy, sample_rate = sf.read(noisy_path, dtype="float32")
        if sample_rate != 16000 or noisy.ndim != 1 or not np.isfinite(noisy).all():
            raise ValueError(f"Clip {index} violates the finite mono 16 kHz input contract")
        started = time.perf_counter()
        noisy_tensor = torch.from_numpy(np.ascontiguousarray(noisy))
        noisy_spec = torch.stft(
            noisy_tensor, 512, 256, 512, window, return_complex=False
        )
        with torch.no_grad():
            enhanced_spec = model(noisy_spec.unsqueeze(0))[0]
        # Explicit length preserves original sample alignment for lengths not
        # divisible by the 256-sample hop; the model/STFT definition is intact.
        enhanced_tensor = torch.istft(
            enhanced_spec, 512, 256, 512, window,
            length=len(noisy), return_complex=False,
        )
        elapsed = time.perf_counter() - started
        enhanced = enhanced_tensor.detach().cpu().numpy().astype(np.float32, copy=False)
        if enhanced.shape != noisy.shape or not np.isfinite(enhanced).all():
            raise RuntimeError(f"Clip {index} produced invalid/misaligned output {enhanced.shape}")
        out_path = predictions / f"{index:04d}_enhanced.wav"
        sf.write(out_path, enhanced, sample_rate, subtype="FLOAT")
        infer_seconds_sum += elapsed
        duration = len(noisy) / sample_rate
        audio_duration += duration
        inference_rows.append({
            "val_index": index,
            "audio_seconds": duration,
            "inference_seconds_stft_model_istft": elapsed,
            "output_samples": int(len(enhanced)),
            "output_sha256": file_sha256(out_path),
        })
        if position % 25 == 0 or position == len(rows):
            print(f"GTCRN inference {position}/590", flush=True)

    loop_wall_seconds = time.perf_counter() - loop_start
    with (output_dir / "inference_per_clip.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(inference_rows[0]))
        writer.writeheader()
        writer.writerows(inference_rows)

    rss_raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_rss_bytes = int(rss_raw if platform.system() == "Darwin" else rss_raw * 1024)
    runtime = {
        "model": "official GTCRN DNS3",
        "source_commit": "502ebfab64da7c4a9af78dcb9c6ceef1ebb01c73",
        "source_snapshot_sha256": SOURCE_SHA256,
        "checkpoint": str(CHECKPOINT),
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "checkpoint_bytes": CHECKPOINT.stat().st_size,
        "parameter_count_learned": parameter_count,
        "strict_load_status": str(load_result),
        "manifest_sha256": MANIFEST_SHA256,
        "clip_count": len(inference_rows),
        "sample_rate_hz": 16000,
        "channels": 1,
        "stft": {"n_fft": 512, "win_length": 512, "hop_length": 256, "window": "sqrt Hann"},
        "runtime_versions": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "numpy": np.__version__,
            "soundfile": sf.__version__,
        },
        "hardware": {"platform": platform.platform(), "machine": platform.machine(), "device": "cpu"},
        "model_load_wall_seconds": model_load_seconds,
        "inference_wall_seconds_sum": infer_seconds_sum,
        "inference_loop_wall_seconds_including_io": loop_wall_seconds,
        "audio_duration_seconds": audio_duration,
        "inference_only_rtf": infer_seconds_sum / audio_duration,
        "loop_wall_rtf_including_io": loop_wall_seconds / audio_duration,
        "peak_process_rss_bytes": peak_rss_bytes,
        "output_audio_files": len(inference_rows),
    }
    (output_dir / "inference_runtime.json").write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(runtime, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
