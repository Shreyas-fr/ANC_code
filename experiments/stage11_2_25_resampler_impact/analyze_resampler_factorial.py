#!/usr/bin/env python3
"""Factorial isolation of native input and output resampler implementations."""
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
RUN = ROOT / "runs/stage11_2_25_resampler_isolation_20261114"
CANONICAL = ROOT / "runs/sih26052_canonical_validation"
ARCHIVE = ROOT.parent / "models/dfn3_step500_tract.tar.gz"
CHECKPOINT = ROOT / "runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt"
STEP23 = ROOT / "runs/stage11_2_23_native_tract_canonical_parity_20261114/native_predictions"
STAGE25 = ROOT / "runs/stage11_2_25_resampler_isolation_20261114/native_48k_outputs"
RUST = ROOT / "runs/stage11_2_25_resampler_isolation_20261114/rust_target/release/stage25-rubato-resample"
MATRIX = RUN / "factorial"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def rust_resample(input_f32: np.ndarray, in_rate: int, out_rate: int, label: str, i: int) -> np.ndarray:
    source = MATRIX / "raw" / f"{label}_{i:04d}_{in_rate}.f32"
    target = MATRIX / "raw" / f"{label}_{i:04d}_{out_rate}.f32"
    source.write_bytes(np.asarray(input_f32, dtype="<f4").tobytes())
    subprocess.run([str(RUST), str(source), str(target), str(in_rate), str(out_rate)], check=True)
    return np.fromfile(target, dtype="<f4").copy()


def main() -> None:
    if MATRIX.exists():
        raise SystemExit(f"Refusing to overwrite {MATRIX}")
    sys.path.insert(0, str(ROOT))
    import numpy.exceptions
    if not hasattr(numpy.exceptions, "RankWarning"):
        numpy.exceptions.RankWarning = np.RankWarning
    import soundfile as sf
    from scipy.signal import resample_poly
    from scripts.evaluate_dfn3_canonical import metrics, require_non_gold_canonical_dir

    canonical = require_non_gold_canonical_dir(CANONICAL)
    manifest_path = canonical / "manifest.csv"
    expected_hashes = {
        manifest_path: "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4",
        CHECKPOINT: "bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27",
        ARCHIVE: "99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d",
    }
    before = {str(p): sha256(p) for p in expected_hashes}
    if any(before[str(p)] != h for p, h in expected_hashes.items()):
        raise SystemExit(f"Protected hashes fail before factorial: {before}")
    meta = json.loads((RUN / "run_metadata.json").read_text())
    ids = list(meta["selected_ids"])
    with manifest_path.open(newline="", encoding="utf-8") as f:
        manifest = list(csv.DictReader(f))
    MATRIX.mkdir(parents=True, exist_ok=False)
    (MATRIX / "raw").mkdir()
    input_dir = MATRIX / "rubato_48k_float_inputs"
    input_dir.mkdir()
    rustup_inputs = []
    for i in ids:
        x, sr = sf.read(canonical / "noisy_audio" / f"{i:04d}_noisy.wav", dtype="float32")
        if sr != 16000 or len(x) != 48000:
            raise SystemExit(f"Bad source {i}: sr={sr}, n={len(x)}")
        x48 = rust_resample(x, 16000, 48000, "input", i)
        if len(x48) != 144000:
            raise SystemExit(f"Rubato upsample length wrong at {i}: {len(x48)}")
        p = input_dir / f"{i:04d}_noisy_48k.wav"
        sf.write(p, x48, 48000, subtype="FLOAT")
        rustup_inputs.append(p)

    native_raw_dir = MATRIX / "native_48k_rubato_input"
    binary = meta["native_command"][0]
    command = [binary, "--model", str(ARCHIVE), "--compensate-delay", "--output-dir", str(native_raw_dir), *map(str, rustup_inputs)]
    started = time.monotonic()
    with (MATRIX / "native_stdout.log").open("wb") as stdout, (MATRIX / "native_stderr.log").open("wb") as stderr:
        proc = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, check=False)
    native_seconds = time.monotonic() - started
    if proc.returncode or len(list(native_raw_dir.glob("*.wav"))) != len(ids):
        raise SystemExit(f"Native Rubato-upsample run failed: code={proc.returncode}")

    raw_native_dirs = {
        "scipy": STAGE25,
        "rubato": native_raw_dir,
    }
    rows = []
    for input_resampler, raw_dir in raw_native_dirs.items():
        for i in ids:
            raw_name = f"{i:04d}_noisy_48k.wav"
            raw, sr = sf.read(raw_dir / raw_name, dtype="float32")
            if sr != 48000 or len(raw) != 142560:
                raise SystemExit(f"Bad 48k native output {input_resampler}/{i}: {sr}, {len(raw)}")
            for output_resampler in ("scipy", "rubato"):
                if output_resampler == "scipy":
                    y = resample_poly(raw, 1, 3).astype(np.float32)
                else:
                    y = rust_resample(raw, 48000, 16000, f"output_{input_resampler}", i)
                if len(y) != 47520 or not np.isfinite(y).all():
                    raise SystemExit(f"Bad {input_resampler}/{output_resampler} 16k result for {i}: {len(y)}")
                clean, sr = sf.read(canonical / "clean_audio" / f"{i:04d}_clean.wav", dtype="float32")
                score = metrics(clean[:47520], y)
                rows.append({
                    "val_index": i,
                    "target_snr_db": float(manifest[i]["target_snr"]),
                    "input_resampler": input_resampler,
                    "output_resampler": output_resampler,
                    **{f"output_{k}": float(v) for k, v in score.items()},
                })
                out = MATRIX / f"{input_resampler}up_{output_resampler}down"
                out.mkdir(exist_ok=True)
                sf.write(out / f"{i:04d}_enhanced.wav", y, 16000, subtype="FLOAT")

    with (MATRIX / "per_clip_factorial.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    grouped = {}
    for up in ("scipy", "rubato"):
        for down in ("scipy", "rubato"):
            grp = [r for r in rows if r["input_resampler"] == up and r["output_resampler"] == down]
            grouped[f"{up}_up_{down}_down"] = {
                "n": len(grp),
                "means": {m: float(np.mean([r[f"output_{m}"] for r in grp])) for m in ("snr_db", "si_sdr_db", "stoi", "pesq_wb")},
            }
    after = {str(p): sha256(p) for p in expected_hashes}
    if before != after:
        raise SystemExit(f"Protected hashes changed: before={before}, after={after}")
    result = {
        "manifest_sha256": before[str(manifest_path)],
        "selected_ids": ids,
        "factorial": grouped,
        "native_returncode": proc.returncode,
        "native_seconds": native_seconds,
        "interpretation_limit": "targeted n=9 diagnostic; native output PCM quantization remains; same 47,520 sample common crop; not a confirmatory quality result",
        "native_command": command,
        "protected_hashes_before": before,
        "protected_hashes_after": after,
        "gold_accessed": False,
        "training_or_tuning": False,
    }
    (MATRIX / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["factorial"], indent=2))


if __name__ == "__main__":
    main()
