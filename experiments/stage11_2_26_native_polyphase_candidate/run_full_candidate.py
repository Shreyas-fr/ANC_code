#!/usr/bin/env python3
"""Full frozen-development parity run for the isolated Rust polyphase candidate."""
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
RUN = ROOT / "runs/stage11_2_26_native_polyphase_candidate_20261114"
CANONICAL = ROOT / "runs/sih26052_canonical_validation"
REFERENCE_DIR = ROOT / "runs/stage8_ensemble_20261113/step500_predictions"
ARCHIVE = ROOT.parent / "models/dfn3_step500_tract.tar.gz"
CHECKPOINT = ROOT / "runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt"
MANIFEST = CANONICAL / "manifest.csv"
OUT = RUN / "full_native_outputs"
METRICS = RUN / "full_metrics"
MANIFEST_HASH = "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4"
CHECKPOINT_HASH = "bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27"
ARCHIVE_HASH = "99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    if OUT.exists() or METRICS.exists():
        raise SystemExit("Refusing to overwrite prior full candidate outputs")
    sys.path.insert(0, str(ROOT))
    import numpy.exceptions
    if not hasattr(numpy.exceptions, "RankWarning"):
        numpy.exceptions.RankWarning = np.RankWarning
    import soundfile as sf
    from scripts.evaluate_dfn3_canonical import metrics, require_non_gold_canonical_dir

    canonical = require_non_gold_canonical_dir(CANONICAL)
    protected = {MANIFEST: MANIFEST_HASH, CHECKPOINT: CHECKPOINT_HASH, ARCHIVE: ARCHIVE_HASH}
    before = {str(p): sha256(p) for p in protected}
    if any(before[str(p)] != expected for p, expected in protected.items()):
        raise SystemExit(f"Protected hashes failed before inference: {before}")
    with MANIFEST.open(newline="", encoding="utf-8") as f:
        manifest = list(csv.DictReader(f))
    if len(manifest) != 590 or sha256(MANIFEST) != MANIFEST_HASH:
        raise SystemExit("Canonical manifest count or hash mismatch")
    ledger = {int(r["val_index"]): r for r in csv.DictReader((REFERENCE_DIR / "prediction_files.csv").open(newline="", encoding="utf-8"))}
    ref_metrics = {int(r["val_index"]): r for r in csv.DictReader((REFERENCE_DIR / "per_clip.csv").open(newline="", encoding="utf-8"))}
    if len(ledger) != 590 or len(ref_metrics) != 590:
        raise SystemExit("Stage 8 Python reference rows/ledger must contain 590 records")

    binary = RUN / "target/release/deep-filter"
    command = [str(binary), "--model", str(ARCHIVE), "--compensate-delay", "--output-dir", str(OUT)]
    command.extend(str(CANONICAL / "noisy_audio" / f"{i:04d}_noisy.wav") for i in range(590))
    started = time.monotonic()
    with (RUN / "full_native_stdout.log").open("wb") as stdout, (RUN / "full_native_stderr.log").open("wb") as stderr:
        proc = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, check=False)
    elapsed = time.monotonic() - started
    if proc.returncode != 0 or len(list(OUT.glob("*.wav"))) != 590:
        raise SystemExit(f"Candidate inference failed: return={proc.returncode}, files={len(list(OUT.glob('*.wav')))}")

    METRICS.mkdir(parents=True, exist_ok=False)
    native_rows, python_rows = [], []
    for i, item in enumerate(manifest):
        native_path = OUT / f"{i:04d}_noisy.wav"
        enhanced, sr = sf.read(native_path, dtype="float32")
        clean, clean_sr = sf.read(CANONICAL / "clean_audio" / f"{i:04d}_clean.wav", dtype="float32")
        ref_path = REFERENCE_DIR / ledger[i]["relative_path"]
        if sha256(ref_path) != ledger[i]["sha256"]:
            raise SystemExit(f"Reference prediction hash mismatch at {i}")
        reference, ref_sr = sf.read(ref_path, dtype="float32")
        if (sr, clean_sr, ref_sr) != (16000, 16000, 16000) or enhanced.shape != (47520,) or clean.shape != (48000,) or reference.shape != (48000,):
            raise SystemExit(f"Unexpected rate/length at ID {i}")
        if not np.isfinite(enhanced).all() or not np.isfinite(clean).all() or not np.isfinite(reference).all():
            raise SystemExit(f"Non-finite waveform at ID {i}")
        native_score = metrics(clean[:47520], enhanced)
        python_score = metrics(clean[:47520], reference[:47520])
        shared = {
            "val_index": i,
            "origin": item.get("dataset_origin", "UNKNOWN"),
            "target_snr_db": float(item["target_snr"]),
            "input_snr_db": float(ref_metrics[i]["input_snr_db"]),
        }
        native_rows.append({**shared, **{f"output_{k}": float(v) for k, v in native_score.items()}})
        python_rows.append({**shared, **{f"output_{k}": float(v) for k, v in python_score.items()}})
        if (i + 1) % 100 == 0 or i == 589:
            print(f"Scored {i + 1}/590", flush=True)

    for label, rows in (("native", native_rows), ("python", python_rows)):
        d = METRICS / label
        d.mkdir()
        with (d / "per_clip.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader(); w.writerows(rows)
        (d / "summary.json").write_text(json.dumps({
            "canonical_manifest_sha256": MANIFEST_HASH,
            "count": len(rows),
            "model_label": f"{label}_common_47_520_samples",
            "samples_per_clip": 47520,
            "metric_function": "scripts/evaluate_dfn3_canonical.py::metrics (unchanged)",
        }, indent=2) + "\n")

    compare = [
        str(ROOT.parent / "pc_venv/bin/python"), str(ROOT / "scripts/compare_dfn3_canonical.py"),
        "--reference", str(METRICS / "python/per_clip.csv"),
        "--candidate", str(METRICS / "native/per_clip.csv"),
        "--output", str(METRICS / "paired_native_vs_python.json"),
        "--bootstrap", "2000", "--seed", "26052",
    ]
    cmp = subprocess.run(compare, cwd=ROOT, text=True, capture_output=True, check=False)
    if cmp.returncode:
        raise SystemExit(f"Paired comparison failed: {cmp.stderr}")
    (METRICS / "paired_comparison_stdout.txt").write_text(cmp.stdout)
    after = {str(p): sha256(p) for p in protected}
    if before != after:
        raise SystemExit(f"Protected hashes changed: before={before}, after={after}")
    meta = {
        "command": command,
        "comparison_command": compare,
        "native_returncode": proc.returncode,
        "comparison_returncode": cmp.returncode,
        "native_wall_seconds": elapsed,
        "count": 590,
        "common_samples": 47520,
        "candidate_binary_sha256": sha256(binary),
        "candidate_source_transforms_sha256": sha256(RUN / "DeepFilterNet/libDF/src/transforms.rs"),
        "candidate_source_enhance_wav_sha256": sha256(RUN / "DeepFilterNet/libDF/src/bin/enhance_wav.rs"),
        "protected_hashes_before": before,
        "protected_hashes_after": after,
        "gold_accessed": False,
        "training_or_tuning": False,
    }
    (RUN / "full_run_metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({"returncode": proc.returncode, "seconds": elapsed, "count": 590, "paired_json": str(METRICS / "paired_native_vs_python.json")}, indent=2))


if __name__ == "__main__":
    main()
