#!/usr/bin/env python3
"""Evaluate official pretrained FullSubNet on the frozen canonical set.

Metric calculation is imported from the established canonical evaluator; this
script only supplies FullSubNet inference and writes the same per-clip schema.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
from evaluate_dfn3_canonical import metrics, require_non_gold_canonical_dir, sha256
from src.models.fullsubnet_adapter import CHECKPOINT_DEFAULT, FullSubNetAdapter


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=CHECKPOINT_DEFAULT)
    parser.add_argument("--canonical-dir", type=Path, default=REPO / "runs/sih26052_canonical_validation")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    canonical_dir = require_non_gold_canonical_dir(args.canonical_dir)
    manifest = canonical_dir / "manifest.csv"
    if sha256(manifest) != "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4":
        raise SystemExit("Frozen canonical manifest SHA-256 mismatch")
    rows = list(csv.DictReader(manifest.open(newline="", encoding="utf-8")))
    if len(rows) != 590:
        raise SystemExit(f"Expected 590 canonical rows; found {len(rows)}")

    output_dir = args.output_dir.expanduser().resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    model = FullSubNetAdapter(args.checkpoint, device=args.device)
    output_rows: list[dict[str, object]] = []
    lengths_s: list[float] = []
    started = time.perf_counter()
    for position, row in enumerate(rows, start=1):
        index = int(row["val_index"])
        clean, clean_sr = sf.read(canonical_dir / "clean_audio" / f"{index:04d}_clean.wav", dtype="float32")
        noisy, noisy_sr = sf.read(canonical_dir / "noisy_audio" / f"{index:04d}_noisy.wav", dtype="float32")
        if clean_sr != 16000 or noisy_sr != 16000 or clean.ndim != 1 or noisy.ndim != 1:
            raise ValueError(f"Clip {index} violates the mono 16 kHz input contract")
        if len(clean) != len(noisy) or not np.isfinite(clean).all() or not np.isfinite(noisy).all():
            raise ValueError(f"Clip {index} is invalid or misaligned")
        enhanced = model.enhance(noisy, sample_rate=noisy_sr)
        input_metrics = metrics(clean, noisy)
        output_metrics = metrics(clean, enhanced)
        lengths_s.append(len(clean) / clean_sr)
        output_rows.append({
            "val_index": index,
            "origin": row.get("dataset_origin", "UNKNOWN"),
            "target_snr_db": float(row["target_snr"]),
            "input_snr_db": input_metrics["snr_db"],
            **{f"input_{k}": v for k, v in input_metrics.items() if k != "snr_db"},
            **{f"output_{k}": v for k, v in output_metrics.items()},
        })
        if position % 25 == 0 or position == len(rows):
            print(f"Evaluated {position}/{len(rows)}", flush=True)

    elapsed = time.perf_counter() - started
    per_clip_path = output_dir / "per_clip.csv"
    with per_clip_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)

    metric_names = ("snr_db", "si_sdr_db", "stoi", "pesq_wb")
    target_bins: dict[str, list[dict[str, object]]] = {}
    for result in output_rows:
        target_bins.setdefault(f"{float(result['target_snr_db']):g}", []).append(result)

    def summarize(selected: list[dict[str, object]]) -> dict[str, object]:
        values = {
            name: np.asarray([r[f"output_{name}"] for r in selected], dtype=np.float64)
            for name in metric_names
        }
        valid = np.logical_and.reduce([np.isfinite(values[name]) for name in ("snr_db", "stoi", "pesq_wb")])
        return {
            **{name: float(np.nanmean(array)) if np.isfinite(array).any() else float("nan") for name, array in values.items()},
            "count": len(selected),
            "pass_rate": {
                "snr_gt_15_db": float(np.nanmean(values["snr_db"] > 15.0)),
                "stoi_gt_0_85": float(np.nanmean(values["stoi"] > 0.85)),
                "pesq_gt_2_5": float(np.nanmean(values["pesq_wb"] > 2.5)),
                "all_three": float(np.mean((values["snr_db"][valid] > 15.0) & (values["stoi"][valid] > 0.85) & (values["pesq_wb"][valid] > 2.5))) if valid.any() else float("nan"),
                "valid_counts": {"snr": int(np.isfinite(values["snr_db"]).sum()), "stoi": int(np.isfinite(values["stoi"]).sum()), "pesq": int(np.isfinite(values["pesq_wb"]).sum()), "all_three": int(valid.sum())},
            },
        }

    summary = {
        "model": "Audio-WestlakeU FullSubNet (official pretrained, epoch 58)",
        "checkpoint": str(model.checkpoint),
        "checkpoint_sha256": model.checkpoint_sha256,
        "parameter_count": model.parameter_count,
        "canonical_manifest_sha256": sha256(manifest),
        "sample_rate_hz": 16000,
        "channels": 1,
        "stft": {"n_fft": 512, "win_length": 512, "hop_length": 256},
        "model_config": {"look_ahead": 2, "norm_type": "offline_laplace_norm", "sequence_model": "LSTM"},
        "device": str(model.device),
        "count": len(output_rows),
        "criteria": {"output_snr_db_gt": 15.0, "stoi_gt": 0.85, "pesq_wb_gt": 2.5},
        "overall": {"mean": summarize(output_rows)},
        "strata": {key: summarize(value) for key, value in sorted(target_bins.items(), key=lambda item: float(item[0]))},
        "runtime": {"elapsed_wall_seconds": elapsed, "audio_duration_seconds": sum(lengths_s), "wall_clock_rtf": elapsed / sum(lengths_s)},
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {per_clip_path} and {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
