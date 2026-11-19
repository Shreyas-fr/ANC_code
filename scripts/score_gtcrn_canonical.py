#!/usr/bin/env python3
"""Score GTCRN WAV predictions with the unchanged canonical metric function."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate_dfn3_canonical import metrics, require_non_gold_canonical_dir, sha256

EXPECTED_MANIFEST_SHA256 = "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4"


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    names = ("snr_db", "si_sdr_db", "stoi", "pesq_wb")
    data = {name: np.asarray([r[f"output_{name}"] for r in rows], dtype=np.float64) for name in names}
    finite = {name: np.isfinite(vals) for name, vals in data.items()}
    joint_valid = finite["snr_db"] & finite["stoi"] & finite["pesq_wb"]
    passed = (
        (data["snr_db"][joint_valid] > 15.0)
        & (data["stoi"][joint_valid] > 0.85)
        & (data["pesq_wb"][joint_valid] > 2.5)
    )
    return {
        **{name: float(np.nanmean(vals)) for name, vals in data.items()},
        "count": len(rows),
        "pass_counts": {
            "snr_gt_15_db": int(np.sum(data["snr_db"][finite["snr_db"]] > 15.0)),
            "stoi_gt_0_85": int(np.sum(data["stoi"][finite["stoi"]] > 0.85)),
            "pesq_gt_2_5": int(np.sum(data["pesq_wb"][finite["pesq_wb"]] > 2.5)),
            "all_three": int(passed.sum()),
            "valid": {name: int(mask.sum()) for name, mask in finite.items()},
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-dir", type=Path, default=ROOT / "runs/sih26052_canonical_validation")
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    canonical = require_non_gold_canonical_dir(args.canonical_dir)
    manifest = canonical / "manifest.csv"
    if sha256(manifest) != EXPECTED_MANIFEST_SHA256:
        raise SystemExit("Frozen canonical manifest hash mismatch")
    rows_in = list(csv.DictReader(manifest.open(newline="", encoding="utf-8")))
    if len(rows_in) != 590:
        raise SystemExit(f"Expected 590 manifest rows, got {len(rows_in)}")
    run_dir = args.run_dir.expanduser().resolve()
    pred_dir = run_dir / "predictions"
    if not (run_dir / "inference_runtime.json").is_file():
        raise SystemExit("Missing GTCRN inference runtime record")
    started = time.perf_counter()
    rows_out: list[dict[str, object]] = []
    for position, row in enumerate(rows_in, start=1):
        index = int(row["val_index"])
        clean, clean_sr = sf.read(canonical / "clean_audio" / f"{index:04d}_clean.wav", dtype="float32")
        noisy, noisy_sr = sf.read(canonical / "noisy_audio" / f"{index:04d}_noisy.wav", dtype="float32")
        enhanced, enhanced_sr = sf.read(pred_dir / f"{index:04d}_enhanced.wav", dtype="float32")
        if (clean_sr, noisy_sr, enhanced_sr) != (16000, 16000, 16000):
            raise ValueError(f"Clip {index} has a noncanonical sample rate")
        if clean.ndim != 1 or noisy.ndim != 1 or enhanced.ndim != 1:
            raise ValueError(f"Clip {index} is not mono")
        if len(clean) != len(noisy) or len(clean) != len(enhanced):
            raise ValueError(f"Clip {index} is not sample-aligned")
        if not (np.isfinite(clean).all() and np.isfinite(noisy).all() and np.isfinite(enhanced).all()):
            raise ValueError(f"Clip {index} contains non-finite waveform values")
        input_metrics = metrics(clean, noisy)
        output_metrics = metrics(clean, enhanced)
        rows_out.append({
            "val_index": index,
            "origin": row.get("dataset_origin", "UNKNOWN"),
            "target_snr_db": float(row["target_snr"]),
            "input_snr_db": input_metrics["snr_db"],
            **{f"input_{key}": value for key, value in input_metrics.items() if key != "snr_db"},
            **{f"output_{key}": value for key, value in output_metrics.items()},
        })
        if position % 25 == 0 or position == len(rows_in):
            print(f"Scored {position}/590", flush=True)
    scoring_wall = time.perf_counter() - started

    per_clip = run_dir / "per_clip.csv"
    with per_clip.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows_out[0]))
        writer.writeheader()
        writer.writerows(rows_out)
    strata: dict[str, list[dict[str, object]]] = {}
    for row in rows_out:
        strata.setdefault(f"{float(row['target_snr_db']):g}", []).append(row)
    runtime = json.loads((run_dir / "inference_runtime.json").read_text(encoding="utf-8"))
    summary = {
        "model": "Xiaobin-Rong GTCRN official DNS3 checkpoint",
        "checkpoint_sha256": runtime["checkpoint_sha256"],
        "source_commit": runtime["source_commit"],
        "source_snapshot_sha256": runtime["source_snapshot_sha256"],
        "parameter_count_learned": runtime["parameter_count_learned"],
        "checkpoint_bytes": runtime["checkpoint_bytes"],
        "canonical_manifest_sha256": sha256(manifest),
        "sample_rate_hz": 16000,
        "channels": 1,
        "stft": runtime["stft"],
        "device": "cpu",
        "count": len(rows_out),
        "criteria": {"output_snr_db_gt": 15.0, "stoi_gt": 0.85, "pesq_wb_gt": 2.5},
        "overall": {"mean": summarize(rows_out)},
        "strata": {key: summarize(value) for key, value in sorted(strata.items(), key=lambda item: float(item[0]))},
        "runtime": {**runtime, "metric_scoring_wall_seconds": scoring_wall},
        "metric_implementation": {
            "path": "scripts/evaluate_dfn3_canonical.py::metrics",
            "sha256": sha256(ROOT / "scripts/evaluate_dfn3_canonical.py"),
        },
    }
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {per_clip} and {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
