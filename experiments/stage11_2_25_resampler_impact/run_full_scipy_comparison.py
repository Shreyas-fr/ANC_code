#!/usr/bin/env python3
"""Full canonical diagnostic with SciPy-equivalent resampling around native Tract."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "runs/stage11_2_25_resampler_isolation_20261114/full_scipy_comparison"
CANONICAL = ROOT / "runs/sih26052_canonical_validation"
REFERENCE = ROOT / "runs/stage8_ensemble_20261113/step500_predictions"
CHECKPOINT = ROOT / "runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt"
ARCHIVE = ROOT.parent / "models/dfn3_step500_tract.tar.gz"
MANIFEST_HASH = "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4"
CHECKPOINT_HASH = "bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27"
ARCHIVE_HASH = "99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    if RUN.exists():
        raise SystemExit(f"Refusing to overwrite {RUN}")
    sys.path.insert(0, str(ROOT))
    import numpy.exceptions
    if not hasattr(numpy.exceptions, "RankWarning"):
        numpy.exceptions.RankWarning = np.RankWarning
    import soundfile as sf
    from scipy.signal import resample_poly
    from scripts.evaluate_dfn3_canonical import metrics, require_non_gold_canonical_dir

    canonical = require_non_gold_canonical_dir(CANONICAL)
    manifest_path = canonical / "manifest.csv"
    protected = {manifest_path: MANIFEST_HASH, CHECKPOINT: CHECKPOINT_HASH, ARCHIVE: ARCHIVE_HASH}
    before = {str(p): sha256(p) for p in protected}
    if any(before[str(p)] != expected for p, expected in protected.items()):
        raise SystemExit(f"Protected hashes failed before run: {before}")
    with manifest_path.open(newline="", encoding="utf-8") as f:
        manifest = list(csv.DictReader(f))
    if len(manifest) != 590:
        raise SystemExit(f"Expected 590 manifest records, found {len(manifest)}")
    ref_ledger = {int(r["val_index"]): r for r in csv.DictReader((REFERENCE / "prediction_files.csv").open(newline="", encoding="utf-8"))}
    if len(ref_ledger) != 590:
        raise SystemExit("Python reference ledger does not contain 590 predictions")

    RUN.mkdir(parents=True, exist_ok=False)
    input_dir = RUN / "scipy_48k_float_inputs"
    native48_dir = RUN / "native_48k_pcm_outputs"
    enhanced_dir = RUN / "native_scipy_16k_float_outputs"
    scores_dir = RUN / "scores"
    input_dir.mkdir()
    enhanced_dir.mkdir()
    for i in range(590):
        x, sr = sf.read(canonical / "noisy_audio" / f"{i:04d}_noisy.wav", dtype="float32")
        if sr != 16000 or x.shape != (48000,) or not np.isfinite(x).all():
            raise SystemExit(f"Bad canonical input {i}: sr={sr}, shape={x.shape}")
        x48 = resample_poly(x, 3, 1).astype(np.float32)
        if x48.shape != (144000,):
            raise SystemExit(f"Bad resampled input length at {i}: {x48.shape}")
        sf.write(input_dir / f"{i:04d}_noisy_48k.wav", x48, 48000, subtype="FLOAT")

    source_meta = json.loads((ROOT / "runs/stage11_2_23_native_tract_canonical_parity_20261114/run_metadata.json").read_text())
    command = [source_meta["command"][0], "--model", str(ARCHIVE), "--compensate-delay", "--output-dir", str(native48_dir)]
    command.extend(str(input_dir / f"{i:04d}_noisy_48k.wav") for i in range(590))
    started = time.monotonic()
    with (RUN / "native_stdout.log").open("wb") as stdout, (RUN / "native_stderr.log").open("wb") as stderr:
        proc = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, check=False)
    native_seconds = time.monotonic() - started
    if proc.returncode != 0 or len(list(native48_dir.glob("*.wav"))) != 590:
        raise SystemExit(f"Native inference failed: return={proc.returncode}, outputs={len(list(native48_dir.glob('*.wav')))}")

    reference_rows = {int(r["val_index"]): r for r in csv.DictReader((REFERENCE / "per_clip.csv").open(newline="", encoding="utf-8"))}
    if len(reference_rows) != 590:
        raise SystemExit("Python reference score file does not contain 590 rows")
    native_rows = []
    python_crop_rows = []
    for i, source in enumerate(manifest):
        raw, sr = sf.read(native48_dir / f"{i:04d}_noisy_48k.wav", dtype="float32")
        if sr != 48000 or raw.shape != (142560,):
            raise SystemExit(f"Bad native compensated 48k output at {i}: sr={sr}, shape={raw.shape}")
        y = resample_poly(raw, 1, 3).astype(np.float32)
        if y.shape != (47520,) or not np.isfinite(y).all():
            raise SystemExit(f"Bad SciPy-downsampled output at {i}")
        sf.write(enhanced_dir / f"{i:04d}_enhanced.wav", y, 16000, subtype="FLOAT")
        clean, sr = sf.read(canonical / "clean_audio" / f"{i:04d}_clean.wav", dtype="float32")
        if sr != 16000 or clean.shape != (48000,):
            raise SystemExit(f"Bad clean reference at {i}")
        metric = metrics(clean[:47520], y)
        native_rows.append({
            "val_index": i,
            "origin": source.get("dataset_origin", "UNKNOWN"),
            "target_snr_db": float(source["target_snr"]),
            "input_snr_db": float(reference_rows[i]["input_snr_db"]),
            **{f"output_{k}": float(v) for k, v in metric.items()},
        })
        python_crop_rows.append({
            key: value for key, value in reference_rows[i].items()
            if key in {"val_index", "origin", "target_snr_db", "input_snr_db", "output_snr_db", "output_si_sdr_db", "output_stoi", "output_pesq_wb"}
        })
        python_crop_rows[-1]["val_index"] = i
        # Use the same window as native and unchanged canonical metric formulas.
        py_path = REFERENCE / ref_ledger[i]["relative_path"]
        if sha256(py_path) != ref_ledger[i]["sha256"]:
            raise SystemExit(f"Python reference file hash mismatch at {i}")
        py, sr = sf.read(py_path, dtype="float32")
        if sr != 16000 or py.shape != (48000,):
            raise SystemExit(f"Bad saved Python reference at {i}")
        py_metric = metrics(clean[:47520], py[:47520])
        python_crop_rows[-1].update({f"output_{k}": float(v) for k, v in py_metric.items()})

    for label, rows in (("native", native_rows), ("python", python_crop_rows)):
        out = scores_dir / label
        out.mkdir(parents=True)
        with (out / "per_clip.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        (out / "summary.json").write_text(json.dumps({
            "canonical_manifest_sha256": MANIFEST_HASH,
            "count": len(rows),
            "model_label": f"{label}_common_47_520_sample_crop",
            "samples_per_clip": 47520,
            "metric_function": "scripts/evaluate_dfn3_canonical.py::metrics (unchanged)",
        }, indent=2) + "\n")

    compare_cmd = [
        str(ROOT.parent / "pc_venv/bin/python"), str(ROOT / "scripts/compare_dfn3_canonical.py"),
        "--reference", str(scores_dir / "python/per_clip.csv"),
        "--candidate", str(scores_dir / "native/per_clip.csv"),
        "--output", str(scores_dir / "paired_native_vs_python.json"),
        "--bootstrap", "2000", "--seed", "26052",
    ]
    comparison = subprocess.run(compare_cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    if comparison.returncode != 0:
        raise SystemExit(f"Paired comparison failed: {comparison.stderr}")
    (scores_dir / "paired_comparison_stdout.json").write_text(comparison.stdout)
    after = {str(p): sha256(p) for p in protected}
    if before != after:
        raise SystemExit(f"Protected hashes changed: before={before}, after={after}")
    result = {
        "purpose": "full-set diagnostic replacing Rust/Rubato input and output resampling with scipy.signal.resample_poly while preserving Tract model/archive and CLI state reset",
        "manifest_sha256": MANIFEST_HASH,
        "count": 590,
        "common_samples_per_clip": 47520,
        "native_command": command,
        "native_returncode": proc.returncode,
        "native_wall_seconds": native_seconds,
        "comparison_command": compare_cmd,
        "comparison_returncode": comparison.returncode,
        "protected_hashes_before": before,
        "protected_hashes_after": after,
        "gold_accessed": False,
        "kaggle_accessed": False,
        "raspberry_pi_accessed": False,
        "training_or_tuning": False,
    }
    (RUN / "run_metadata.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"returncode": proc.returncode, "seconds": native_seconds, "count": 590, "paired_comparison": str(scores_dir / "paired_native_vs_python.json")}, indent=2))


if __name__ == "__main__":
    main()
