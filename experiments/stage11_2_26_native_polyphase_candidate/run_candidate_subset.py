#!/usr/bin/env python3
"""Validate the integrated native polyphase resampler against Stage 25 outputs."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import subprocess
import time
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "runs/stage11_2_26_native_polyphase_candidate_20261114"
OUT = RUN / "subset_native_outputs_v2"
CANONICAL = ROOT / "runs/sih26052_canonical_validation"
ARCHIVE = ROOT.parent / "models/dfn3_step500_tract.tar.gz"
CHECKPOINT = ROOT / "runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt"
MANIFEST = CANONICAL / "manifest.csv"
STAGE25_REF = ROOT / "runs/stage11_2_25_resampler_isolation_20261114/full_scipy_comparison/native_scipy_16k_float_outputs"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
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

    require_non_gold_canonical_dir(CANONICAL)
    expected = {
        MANIFEST: "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4",
        CHECKPOINT: "bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27",
        ARCHIVE: "99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d",
    }
    before = {str(p): sha256(p) for p in expected}
    if any(before[str(p)] != h for p, h in expected.items()):
        raise SystemExit(f"Protected hashes fail: {before}")
    prior = json.loads((ROOT / "runs/stage11_2_25_resampler_isolation_20261114/run_metadata.json").read_text())
    ids = list(prior["selected_ids"])
    binary = RUN / "target/release/deep-filter"
    command = [str(binary), "--model", str(ARCHIVE), "--compensate-delay", "--output-dir", str(OUT)]
    command.extend(str(CANONICAL / "noisy_audio" / f"{i:04d}_noisy.wav") for i in ids)
    t0 = time.monotonic()
    with (RUN / "subset_v2_stdout.log").open("wb") as stdout, (RUN / "subset_v2_stderr.log").open("wb") as stderr:
        proc = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, check=False)
    elapsed = time.monotonic() - t0
    if proc.returncode or len(list(OUT.glob("*.wav"))) != len(ids):
        raise SystemExit(f"Candidate subset inference failed: rc={proc.returncode}")

    with MANIFEST.open(newline="", encoding="utf-8") as f:
        manifest = list(csv.DictReader(f))
    rows = []
    for i in ids:
        c, sr = sf.read(CANONICAL / "clean_audio" / f"{i:04d}_clean.wav", dtype="float32")
        native, nsr = sf.read(OUT / f"{i:04d}_noisy.wav", dtype="float32")
        scipy, ssr = sf.read(STAGE25_REF / f"{i:04d}_enhanced.wav", dtype="float32")
        if sr != 16000 or nsr != 16000 or ssr != 16000 or len(native) != 47520 or len(scipy) != 47520:
            raise SystemExit(f"Unexpected length/rate in candidate subset at {i}")
        m_native = metrics(c[:47520], native)
        m_scipy = metrics(c[:47520], scipy)
        diff = native.astype(np.float64) - scipy.astype(np.float64)
        rows.append({
            "val_index": i,
            "target_snr_db": float(manifest[i]["target_snr"]),
            "candidate_polyphase_snr_db": m_native["snr_db"],
            "scipy_control_snr_db": m_scipy["snr_db"],
            "delta_snr_db": m_native["snr_db"] - m_scipy["snr_db"],
            "candidate_polyphase_si_sdr_db": m_native["si_sdr_db"],
            "scipy_control_si_sdr_db": m_scipy["si_sdr_db"],
            "delta_si_sdr_db": m_native["si_sdr_db"] - m_scipy["si_sdr_db"],
            "candidate_polyphase_stoi": m_native["stoi"],
            "scipy_control_stoi": m_scipy["stoi"],
            "delta_stoi": m_native["stoi"] - m_scipy["stoi"],
            "candidate_polyphase_pesq_wb": m_native["pesq_wb"],
            "scipy_control_pesq_wb": m_scipy["pesq_wb"],
            "delta_pesq_wb": m_native["pesq_wb"] - m_scipy["pesq_wb"],
            "waveform_rmse_vs_scipy_control": float(np.sqrt(np.mean(diff * diff))),
            "waveform_corr_vs_scipy_control": float(np.corrcoef(native, scipy)[0, 1]),
        })
    with (RUN / "subset_v2_comparison.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    after = {str(p): sha256(p) for p in expected}
    if before != after:
        raise SystemExit(f"Protected hash changed: before={before}, after={after}")
    meta = {
        "command": command,
        "selected_ids": ids,
        "returncode": proc.returncode,
        "wall_seconds": elapsed,
        "protected_hashes_before": before,
        "protected_hashes_after": after,
        "model_or_evaluator_changed": False,
        "gold_accessed": False,
    }
    (RUN / "subset_v2_run_metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({"returncode": proc.returncode, "seconds": elapsed, "n": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
