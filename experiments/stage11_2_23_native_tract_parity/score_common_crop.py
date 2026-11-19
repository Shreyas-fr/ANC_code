#!/usr/bin/env python3
"""Score existing native and Python Step-500 WAVs on their common duration.

No inference is performed. The evaluator's unchanged metrics() function is
used after a process-local NumPy/pystoi import-compatibility alias.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument(
        "--canonical-dir", type=Path, default=Path("runs/sih26052_canonical_validation")
    )
    parser.add_argument(
        "--native-dir",
        type=Path,
        default=Path("runs/stage11_2_23_native_tract_canonical_parity_20261114/native_predictions"),
    )
    parser.add_argument(
        "--python-dir",
        type=Path,
        default=Path("runs/stage8_ensemble_20261113/step500_predictions"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs/stage11_2_23_native_tract_canonical_parity_20261114/common_crop_scoring"),
    )
    args = parser.parse_args()
    repo = args.repo.expanduser().resolve()
    canonical = (repo / args.canonical_dir).resolve()
    native_dir = (repo / args.native_dir).resolve()
    python_dir = (repo / args.python_dir).resolve()
    output = (repo / args.output_dir).resolve()
    if any(part.casefold() == "sih_gold_test" for part in canonical.parts):
        raise SystemExit(f"Refusing protected gold path: {canonical}")
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty directory: {output}")
    sys.path.insert(0, str(repo))

    # pystoi 0.4.1 imports RankWarning from numpy.exceptions. The available
    # NumPy 1.26.4 exposes the same warning class as numpy.RankWarning. Add the
    # missing module attribute in this process only; do not edit packages.
    import numpy.exceptions

    if not hasattr(numpy.exceptions, "RankWarning"):
        if not hasattr(np, "RankWarning"):
            raise SystemExit("Neither NumPy exception spelling is available")
        numpy.exceptions.RankWarning = np.RankWarning

    import soundfile as sf
    from scripts.evaluate_dfn3_canonical import (
        active_speech_power,
        metrics,
        require_non_gold_canonical_dir,
    )

    canonical = require_non_gold_canonical_dir(canonical)
    manifest = canonical / "manifest.csv"
    expected_manifest = "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4"
    manifest_hash = sha256(manifest)
    if manifest_hash != expected_manifest:
        raise SystemExit(f"Canonical manifest hash mismatch: {manifest_hash}")
    with manifest.open(newline="", encoding="utf-8") as f:
        manifest_rows = list(csv.DictReader(f))
    if len(manifest_rows) != 590:
        raise SystemExit(f"Expected 590 manifest rows; found {len(manifest_rows)}")

    ledger_path = python_dir / "prediction_files.csv"
    with ledger_path.open(newline="", encoding="utf-8") as f:
        ledger_rows = {int(r["val_index"]): r for r in csv.DictReader(f)}
    if len(ledger_rows) != 590:
        raise SystemExit("Reference prediction ledger must contain 590 IDs")

    output.mkdir(parents=True, exist_ok=False)
    result_sets: dict[str, list[dict[str, object]]] = {"native": [], "python": []}
    for i, row in enumerate(manifest_rows):
        if int(row["val_index"]) != i or i not in ledger_rows:
            raise SystemExit(f"Manifest/reference ID mismatch at row {i}")
        clean_path = canonical / "clean_audio" / f"{i:04d}_clean.wav"
        noisy_path = canonical / "noisy_audio" / f"{i:04d}_noisy.wav"
        native_path = native_dir / f"{i:04d}_noisy.wav"
        python_path = python_dir / ledger_rows[i]["relative_path"]
        if sha256(python_path) != ledger_rows[i]["sha256"]:
            raise SystemExit(f"Reference WAV ledger mismatch for ID {i}")
        clean, clean_sr = sf.read(clean_path, dtype="float32")
        noisy, noisy_sr = sf.read(noisy_path, dtype="float32")
        native, native_sr = sf.read(native_path, dtype="float32")
        python_output, python_sr = sf.read(python_path, dtype="float32")
        if (clean_sr, noisy_sr, native_sr, python_sr) != (16000, 16000, 16000, 16000):
            raise SystemExit(f"Sample-rate mismatch for ID {i}")
        if any(a.ndim != 1 for a in (clean, noisy, native, python_output)):
            raise SystemExit(f"Non-mono waveform for ID {i}")
        if len(clean) != 48000 or len(noisy) != 48000 or len(native) != 47520 or len(python_output) != 48000:
            raise SystemExit(f"Unexpected lengths for ID {i}")
        if not all(np.isfinite(a).all() for a in (clean, noisy, native, python_output)):
            raise SystemExit(f"Non-finite waveform for ID {i}")

        input_error = noisy.astype(np.float64) - clean.astype(np.float64)
        speech_power = active_speech_power(clean)
        input_snr = float(
            10.0 * np.log10((speech_power + 1e-12) / (float(np.mean(input_error**2)) + 1e-12))
        )
        common_n = len(native)
        common_clean = clean[:common_n]
        target_snr = float(row["target_snr"])
        for label, estimate in (("native", native), ("python", python_output[:common_n])):
            score = metrics(common_clean, estimate)
            if not all(np.isfinite(float(v)) for v in score.values()):
                raise SystemExit(f"Non-finite metric for {label}, ID {i}: {score}")
            result_sets[label].append(
                {
                    "val_index": i,
                    "origin": row.get("dataset_origin", "UNKNOWN"),
                    "target_snr_db": target_snr,
                    "input_snr_db": input_snr,
                    **{f"output_{k}": float(v) for k, v in score.items()},
                }
            )
        if (i + 1) % 50 == 0 or i == 589:
            print(f"Scored {i + 1}/590 canonical clips", flush=True)

    for label, rows in result_sets.items():
        outdir = output / label
        outdir.mkdir()
        per_clip = outdir / "per_clip.csv"
        with per_clip.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        summary = {
            "canonical_manifest_sha256": manifest_hash,
            "count": len(rows),
            "model_label": "native_tract_step500_common_crop" if label == "native" else "python_step500_common_crop",
            "compared_samples_per_clip": 47520,
            "delay_compensated_native_output_samples": 47520,
            "metric_function": "scripts/evaluate_dfn3_canonical.py::metrics (unchanged)",
            "numpy_stoi_import_compatibility": "process-local numpy.exceptions.RankWarning alias to numpy.RankWarning",
        }
        (outdir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Wrote common-crop metrics under {output}")


if __name__ == "__main__":
    main()
