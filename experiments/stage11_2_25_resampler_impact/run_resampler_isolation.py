#!/usr/bin/env python3
"""Small predeclared comparison replacing Rust resampling with SciPy polyphase."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "runs/sih26052_canonical_validation"
ARCHIVE = ROOT.parent / "models/dfn3_step500_tract.tar.gz"
CHECKPOINT = ROOT / "runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt"
REFERENCE = ROOT / "runs/stage8_ensemble_20261113/step500_predictions"
STEP23_NATIVE = ROOT / "runs/stage11_2_23_native_tract_canonical_parity_20261114/native_predictions"
RUN = ROOT / "runs/stage11_2_25_resampler_isolation_20261114"


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
    import numpy as np
    import numpy.exceptions
    if not hasattr(numpy.exceptions, "RankWarning"):
        numpy.exceptions.RankWarning = np.RankWarning
    import soundfile as sf
    from scipy.signal import resample_poly
    from scripts.evaluate_dfn3_canonical import metrics, require_non_gold_canonical_dir

    canonical = require_non_gold_canonical_dir(CANONICAL)
    manifest_path = canonical / "manifest.csv"
    manifest_hash = sha256(manifest_path)
    expected = {
        manifest_path: "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4",
        CHECKPOINT: "bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27",
        ARCHIVE: "99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d",
    }
    before = {str(p): sha256(p) for p in expected}
    if any(before[str(p)] != digest for p, digest in expected.items()):
        raise SystemExit(f"Protected hash failure before run: {before}")
    with manifest_path.open(newline="", encoding="utf-8") as f:
        manifest = list(csv.DictReader(f))
    by_snr: dict[float, int] = {}
    for i, row in enumerate(manifest):
        by_snr.setdefault(float(row["target_snr"]), i)
    ids = sorted(set(by_snr.values()) | {162, 436})
    RUN.mkdir(parents=True, exist_ok=False)
    input_dir = RUN / "scipy_48k_float_inputs"
    raw_out = RUN / "native_48k_outputs"
    converted_out = RUN / "native_scipy_16k_float_outputs"
    input_dir.mkdir()
    converted_out.mkdir()
    inputs = []
    for i in ids:
        x, sr = sf.read(canonical / "noisy_audio" / f"{i:04d}_noisy.wav", dtype="float32")
        if sr != 16000 or x.shape != (48000,):
            raise SystemExit(f"Unexpected canonical input at {i}: {sr}, {x.shape}")
        x48 = resample_poly(x, 3, 1).astype(np.float32)
        path = input_dir / f"{i:04d}_noisy_48k.wav"
        sf.write(path, x48, 48000, subtype="FLOAT")
        inputs.append(path)

    source_meta = json.loads((ROOT / "runs/stage11_2_23_native_tract_canonical_parity_20261114/run_metadata.json").read_text())
    binary = source_meta["command"][0]
    command = [binary, "--model", str(ARCHIVE), "--compensate-delay", "--output-dir", str(raw_out), *map(str, inputs)]
    t0 = time.monotonic()
    with (RUN / "native_stdout.log").open("wb") as stdout, (RUN / "native_stderr.log").open("wb") as stderr:
        proc = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, check=False)
    native_seconds = time.monotonic() - t0
    if proc.returncode != 0:
        raise SystemExit(f"Native CLI failed ({proc.returncode}); see {RUN}/native_stderr.log")

    ref_ledger = {int(r["val_index"]): r for r in csv.DictReader((REFERENCE / "prediction_files.csv").open(newline="", encoding="utf-8"))}
    records = []
    for i in ids:
        native48_path = raw_out / f"{i:04d}_noisy_48k.wav"
        native48, sr = sf.read(native48_path, dtype="float32")
        if sr != 48000 or native48.shape != (142560,):
            raise SystemExit(f"Unexpected compensated 48k output at {i}: {sr}, {native48.shape}")
        native16 = resample_poly(native48, 1, 3).astype(np.float32)
        if native16.shape != (47520,) or not np.isfinite(native16).all():
            raise SystemExit(f"Bad SciPy-converted native output at {i}: {native16.shape}")
        converted = converted_out / f"{i:04d}_enhanced.wav"
        sf.write(converted, native16, 16000, subtype="FLOAT")
        clean, sr = sf.read(canonical / "clean_audio" / f"{i:04d}_clean.wav", dtype="float32")
        python_path = REFERENCE / ref_ledger[i]["relative_path"]
        if sha256(python_path) != ref_ledger[i]["sha256"]:
            raise SystemExit(f"Python reference hash mismatch at {i}")
        python, _ = sf.read(python_path, dtype="float32")
        old_native, old_sr = sf.read(STEP23_NATIVE / f"{i:04d}_noisy.wav", dtype="float32")
        if len(clean) != 48000 or len(python) != 48000 or old_sr != 16000 or len(old_native) != 47520:
            raise SystemExit(f"Unexpected comparison length at {i}")
        n = len(native16)
        new_metrics = metrics(clean[:n], native16)
        old_metrics = metrics(clean[:n], old_native)
        py_metrics = metrics(clean[:n], python[:n])
        records.append({
            "val_index": i,
            "target_snr_db": float(manifest[i]["target_snr"]),
            "native_rust_resample_snr_db": old_metrics["snr_db"],
            "native_scipy_resample_snr_db": new_metrics["snr_db"],
            "python_snr_db": py_metrics["snr_db"],
            "delta_snr_vs_old_native_db": new_metrics["snr_db"] - old_metrics["snr_db"],
            "delta_snr_vs_python_db": new_metrics["snr_db"] - py_metrics["snr_db"],
            "native_rust_resample_si_sdr_db": old_metrics["si_sdr_db"],
            "native_scipy_resample_si_sdr_db": new_metrics["si_sdr_db"],
            "python_si_sdr_db": py_metrics["si_sdr_db"],
            "native_rust_resample_stoi": old_metrics["stoi"],
            "native_scipy_resample_stoi": new_metrics["stoi"],
            "python_stoi": py_metrics["stoi"],
            "native_rust_resample_pesq_wb": old_metrics["pesq_wb"],
            "native_scipy_resample_pesq_wb": new_metrics["pesq_wb"],
            "python_pesq_wb": py_metrics["pesq_wb"],
        })
    with (RUN / "per_clip_diagnostic.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(records[0]))
        w.writeheader()
        w.writerows(records)
    after = {str(p): sha256(p) for p in expected}
    if before != after:
        raise SystemExit(f"Protected artifact hashes changed: before={before}, after={after}")
    metadata = {
        "purpose": "diagnostic isolate of Rust/Rubato sample-rate conversion; feed SciPy-resampled 48kHz input, so native runtime performs no resampling, then SciPy-downsample native output",
        "selected_ids": ids,
        "one_per_target_snr_bin_ids": {str(k): v for k, v in by_snr.items()},
        "additional_phase_b_correlation_exception_ids": [162, 436],
        "native_command": command,
        "native_returncode": proc.returncode,
        "native_wall_seconds": native_seconds,
        "metric_method": "unchanged scripts/evaluate_dfn3_canonical.py::metrics; first 47,520 samples",
        "manifest_sha256": manifest_hash,
        "protected_hashes_before": before,
        "protected_hashes_after": after,
        "gold_accessed": False,
        "training_or_tuning": False,
    }
    (RUN / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({"selected_ids": ids, "returncode": proc.returncode, "wall_seconds": native_seconds, "protected_hashes_unchanged": before == after}, indent=2))


if __name__ == "__main__":
    main()
