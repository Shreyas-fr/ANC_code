#!/usr/bin/env python3
"""Score Stage 11.2.24 native WAVs with the unchanged canonical metric function."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "runs/stage11_2_24_native_delay_compensation_diagnostic_20261114"
CANONICAL = ROOT / "runs/sih26052_canonical_validation"
OUT = RUN / "metrics/native"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"Refusing to overwrite {OUT}")
    sys.path.insert(0, str(ROOT))
    import numpy.exceptions

    if not hasattr(numpy.exceptions, "RankWarning"):
        numpy.exceptions.RankWarning = np.RankWarning
    import soundfile as sf
    from scripts.evaluate_dfn3_canonical import metrics, require_non_gold_canonical_dir

    canonical = require_non_gold_canonical_dir(CANONICAL)
    manifest = canonical / "manifest.csv"
    manifest_hash = sha256(manifest)
    expected = "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4"
    if manifest_hash != expected:
        raise SystemExit(f"Manifest mismatch: {manifest_hash}")
    with manifest.open(newline="", encoding="utf-8") as f:
        source_rows = list(csv.DictReader(f))
    if len(source_rows) != 590:
        raise SystemExit(f"Expected 590 manifest rows, got {len(source_rows)}")
    OUT.mkdir(parents=True, exist_ok=False)
    reference_path = ROOT / "runs/stage8_ensemble_20261113/step500_predictions/per_clip.csv"
    with reference_path.open(newline="", encoding="utf-8") as f:
        reference_rows = {int(r["val_index"]): r for r in csv.DictReader(f)}
    if len(reference_rows) != 590:
        raise SystemExit("Python Step-500 reference per_clip.csv must contain 590 rows")
    rows = []
    for i, source in enumerate(source_rows):
        clean_path = canonical / "clean_audio" / f"{i:04d}_clean.wav"
        native_path = RUN / "native_predictions" / f"{i:04d}_noisy.wav"
        clean, sr_clean = sf.read(clean_path, dtype="float32")
        enhanced, sr_enh = sf.read(native_path, dtype="float32")
        if sr_clean != 16000 or sr_enh != 16000 or clean.shape != (48000,) or enhanced.shape != (48000,):
            raise SystemExit(f"Unexpected sample rate/shape at ID {i}: {sr_clean}/{sr_enh}, {clean.shape}/{enhanced.shape}")
        if not np.isfinite(clean).all() or not np.isfinite(enhanced).all():
            raise SystemExit(f"Non-finite waveform at ID {i}")
        score = metrics(clean, enhanced)
        rows.append({
            "val_index": i,
            "origin": source.get("dataset_origin", "UNKNOWN"),
            "target_snr_db": float(source["target_snr"]),
            "input_snr_db": float(reference_rows[i]["input_snr_db"]),
            **{f"output_{k}": float(v) for k, v in score.items()},
        })
        if (i + 1) % 100 == 0 or i == 589:
            print(f"Scored {i + 1}/590", flush=True)
    with (OUT / "per_clip.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "canonical_manifest_sha256": manifest_hash,
        "count": len(rows),
        "model_label": "native_tract_step500_without_delay_trim",
        "samples_per_clip": 48000,
        "sample_rate_hz": 16000,
        "metric_function": "scripts/evaluate_dfn3_canonical.py::metrics (unchanged)",
        "python_reference": "runs/stage8_ensemble_20261113/step500_predictions/per_clip.csv",
        "numpy_stoi_import_compatibility": "process-local numpy.exceptions.RankWarning alias to numpy.RankWarning",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
