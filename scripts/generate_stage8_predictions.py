#!/usr/bin/env python3
"""Generate and score Stage 8 waveform predictions using the frozen baseline paths.

This is an append-only runner: it refuses an existing output directory. It
imports the canonical metric and DFN3 inference functions without changing the
canonical evaluator. FullSubNet uses its previously evaluated adapter/config.
"""

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
from pathlib import Path

import numpy as np
import scipy
import soundfile as sf
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
from evaluate_dfn3_canonical import (  # noqa: E402
    enhance_one,
    load_checkpoint,
    metrics,
    require_non_gold_canonical_dir,
    sha256,
)
from src.models.fullsubnet_adapter import (  # noqa: E402
    CHECKPOINT_DEFAULT,
    FullSubNetAdapter,
)

MANIFEST_SHA256 = "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4"
DFN3_SHA256 = "bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27"
FULLSUBNET_SHA256 = "482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0"
METRICS = ("snr_db", "si_sdr_db", "stoi", "pesq_wb")


def memory_bytes() -> int:
    # macOS reports ru_maxrss in bytes (unlike Linux, which reports KiB).
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if platform.system() == "Darwin" else value * 1024


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("dfn3", "fullsubnet"), required=True)
    parser.add_argument("--canonical-dir", type=Path, default=ROOT / "runs/sih26052_canonical_validation")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dfn3-checkpoint", type=Path, default=ROOT / "runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt")
    parser.add_argument("--fullsubnet-checkpoint", type=Path, default=CHECKPOINT_DEFAULT)
    args = parser.parse_args()

    canonical_dir = require_non_gold_canonical_dir(args.canonical_dir)
    manifest = canonical_dir / "manifest.csv"
    if sha256(manifest) != MANIFEST_SHA256:
        raise SystemExit("Frozen canonical manifest SHA-256 mismatch; refusing inference")
    rows = list(csv.DictReader(manifest.open(newline="", encoding="utf-8")))
    if len(rows) != 590:
        raise SystemExit(f"Expected 590 canonical rows, found {len(rows)}")
    ids = [int(row["val_index"]) for row in rows]
    if len(set(ids)) != 590:
        raise SystemExit("Canonical val_index values are not unique")

    checkpoint = args.dfn3_checkpoint if args.model == "dfn3" else args.fullsubnet_checkpoint
    expected_checkpoint_hash = DFN3_SHA256 if args.model == "dfn3" else FULLSUBNET_SHA256
    if sha256(checkpoint) != expected_checkpoint_hash:
        raise SystemExit(f"Protected {args.model} checkpoint SHA-256 mismatch; refusing inference")

    output_dir = args.output_dir.expanduser().resolve()
    if output_dir.exists():
        raise SystemExit(f"Refusing to overwrite existing prediction directory: {output_dir}")
    output_dir.mkdir(parents=True)
    prediction_dir = output_dir

    if args.model == "dfn3":
        model, df_state = load_checkpoint(checkpoint)
        inference_call = lambda noisy, sr: enhance_one(model, df_state, noisy)
    else:
        model = FullSubNetAdapter(checkpoint, device="cpu")
        inference_call = model.enhance

    results: list[dict[str, object]] = []
    file_records: list[dict[str, object]] = []
    audio_seconds = 0.0
    inference_seconds = 0.0
    whole_started = time.perf_counter()
    for position, row in enumerate(rows, start=1):
        clip_id = int(row["val_index"])
        clean, clean_sr = sf.read(canonical_dir / "clean_audio" / f"{clip_id:04d}_clean.wav", dtype="float32")
        noisy, noisy_sr = sf.read(canonical_dir / "noisy_audio" / f"{clip_id:04d}_noisy.wav", dtype="float32")
        if clean_sr != 16000 or noisy_sr != 16000 or clean.ndim != 1 or noisy.ndim != 1:
            raise ValueError(f"Clip {clip_id} violates canonical mono 16 kHz contract")
        if clean.shape != noisy.shape or not np.isfinite(clean).all() or not np.isfinite(noisy).all():
            raise ValueError(f"Clip {clip_id} has invalid or misaligned canonical audio")

        clip_started = time.perf_counter()
        if args.model == "dfn3":
            enhanced = inference_call(noisy, noisy_sr)
        else:
            enhanced = inference_call(noisy, sample_rate=noisy_sr)
        inference_seconds += time.perf_counter() - clip_started
        enhanced = np.asarray(enhanced, dtype=np.float32)
        if enhanced.ndim != 1 or enhanced.shape != noisy.shape or not np.isfinite(enhanced).all():
            raise ValueError(f"Model output for clip {clip_id} is nonfinite or misaligned")

        output_path = prediction_dir / f"{clip_id:04d}_enhanced.wav"
        sf.write(output_path, enhanced, 16000, subtype="FLOAT")
        # Verify and score the serialized prediction using the canonical metric
        # implementation. FLOAT WAV preserves the generated float32 samples.
        stored, stored_sr = sf.read(output_path, dtype="float32")
        if stored_sr != 16000 or stored.shape != clean.shape or not np.isfinite(stored).all():
            raise ValueError(f"Serialized prediction for clip {clip_id} failed integrity checks")

        input_metric = metrics(clean, noisy)
        output_metric = metrics(clean, stored)
        results.append({
            "val_index": clip_id,
            "origin": row.get("dataset_origin", "UNKNOWN"),
            "target_snr_db": float(row["target_snr"]),
            "input_snr_db": input_metric["snr_db"],
            **{f"input_{k}": v for k, v in input_metric.items() if k != "snr_db"},
            **{f"output_{k}": v for k, v in output_metric.items()},
        })
        file_records.append({
            "val_index": clip_id,
            "canonical_clip_id": f"{clip_id:04d}",
            "relative_path": str(output_path.relative_to(output_dir)),
            "sha256": sha256(output_path),
            "sample_rate_hz": stored_sr,
            "channels": 1,
            "sample_count": len(stored),
            "duration_seconds": len(stored) / stored_sr,
            "finite": True,
        })
        audio_seconds += len(stored) / stored_sr
        if position % 25 == 0 or position == len(rows):
            print(f"Generated and scored {position}/{len(rows)}", flush=True)

    elapsed = time.perf_counter() - whole_started
    per_clip_path = output_dir / "per_clip.csv"
    with per_clip_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    files_path = output_dir / "prediction_files.csv"
    with files_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(file_records[0]))
        writer.writeheader()
        writer.writerows(file_records)

    # Save canonical aggregate metrics and target-SNR strata for direct
    # comparison to the original baseline summaries.
    strata: dict[str, list[dict[str, object]]] = {}
    for result in results:
        strata.setdefault(f"{float(result['target_snr_db']):g}", []).append(result)

    def summarize(selected: list[dict[str, object]]) -> dict[str, object]:
        values = {name: np.asarray([r[f"output_{name}"] for r in selected], dtype=np.float64) for name in METRICS}
        valid = np.logical_and.reduce([np.isfinite(values[name]) for name in ("snr_db", "stoi", "pesq_wb")])
        joint = ((values["snr_db"] > 15.0) & (values["stoi"] > 0.85) & (values["pesq_wb"] > 2.5))
        return {
            **{name: float(np.nanmean(array)) for name, array in values.items()},
            "count": len(selected),
            "joint_pass_count": int(np.count_nonzero(joint & valid)),
            "joint_pass_rate": float(np.mean(joint[valid])) if valid.any() else float("nan"),
        }

    if args.model == "dfn3":
        import df
        import torchaudio
        libdf_version = getattr(df, "__version__", "unknown")
        torchaudio_version = torchaudio.__version__
        model_config = {"method": "scripts/evaluate_dfn3_canonical.py::enhance_one", "atten_lim_db": None, "post_gain_db": 0.0, "state_reset_per_clip": True}
    else:
        libdf_version = None
        torchaudio_version = None
        model_config = {"method": "src.models.fullsubnet_adapter.FullSubNetAdapter.enhance", "sample_rate_hz": 16000, "n_fft": 512, "win_length": 512, "hop_length": 256, "look_ahead": 2, "norm_type": "offline_laplace_norm", "sequence_model": "LSTM", "device": "cpu", "fresh_clip_call": True}

    metadata = {
        "model": args.model,
        "checkpoint_path": str(checkpoint.resolve()),
        "checkpoint_sha256": sha256(checkpoint),
        "canonical_manifest_sha256": sha256(manifest),
        "clip_count": len(results),
        "canonical_clip_ids": ids,
        "sample_rate_hz": 16000,
        "channels": 1,
        "sample_count_min": min(item["sample_count"] for item in file_records),
        "sample_count_max": max(item["sample_count"] for item in file_records),
        "duration_seconds_total": audio_seconds,
        "all_finite": all(item["finite"] for item in file_records),
        "all_sample_aligned": all(item["sample_count"] == int(rows[i]["length_samples"]) for i, item in enumerate(file_records)),
        "model_config": model_config,
        "metrics": "imported unchanged: scripts/evaluate_dfn3_canonical.py::metrics",
        "metric_evaluator_sha256": sha256(ROOT / "scripts/evaluate_dfn3_canonical.py"),
        "fullsubnet_evaluator_sha256": sha256(ROOT / "scripts/evaluate_fullsubnet_canonical.py"),
        "fullsubnet_adapter_sha256": sha256(ROOT / "src/models/fullsubnet_adapter.py"),
        "generator_sha256": sha256(Path(__file__)),
        "git_commit": os.popen(f"git -C '{ROOT}' rev-parse HEAD").read().strip(),
        "runtime_versions": {
            "python": sys.version,
            "torch": torch.__version__,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "soundfile": sf.__version__,
            "libdf": libdf_version,
            "torchaudio": torchaudio_version,
        },
        "hardware": {"platform": platform.platform(), "machine": platform.machine(), "device": "cpu"},
        "runtime": {
            "inference_wall_seconds_sum": inference_seconds,
            "generation_and_scoring_wall_seconds": elapsed,
            "audio_duration_seconds": audio_seconds,
            "inference_only_rtf": inference_seconds / audio_seconds,
            "wall_clock_rtf_including_io_scoring": elapsed / audio_seconds,
            "peak_process_rss_bytes": memory_bytes(),
        },
        "prediction_count": len(file_records),
        "prediction_files_csv": str(files_path.resolve()),
        "per_clip_metrics_csv": str(per_clip_path.resolve()),
        "overall": summarize(results),
        "target_snr_strata": {key: summarize(value) for key, value in sorted(strata.items(), key=lambda item: float(item[0]))},
    }
    (output_dir / "generation_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: metadata[k] for k in ("model", "clip_count", "checkpoint_sha256", "runtime", "overall")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
