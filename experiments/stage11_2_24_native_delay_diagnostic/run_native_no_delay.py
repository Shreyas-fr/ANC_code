#!/usr/bin/env python3
"""Run a non-overwriting native Step-500 diagnostic without output delay trim."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
SOURCE_RUN = ROOT / "runs/stage11_2_23_native_tract_canonical_parity_20261114"
OUT = ROOT / "runs/stage11_2_24_native_delay_compensation_diagnostic_20261114"
MANIFEST = ROOT / "runs/sih26052_canonical_validation/manifest.csv"
CHECKPOINT = ROOT / "runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt"
ARCHIVE = ROOT.parent / "models/dfn3_step500_tract.tar.gz"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"Refusing to overwrite existing output directory: {OUT}")
    if any("sih_gold_test" == part.casefold() for part in MANIFEST.parts):
        raise SystemExit("Refusing protected gold path")
    expected = {
        MANIFEST: "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4",
        CHECKPOINT: "bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27",
        ARCHIVE: "99e99379e81ecf5a678833912d28418c3cc7fb40345fd4a8fb8f5b82669a559d",
    }
    for path, digest in expected.items():
        actual = sha256(path)
        if actual != digest:
            raise SystemExit(f"Protected hash mismatch for {path}: {actual}")

    prior = json.loads((SOURCE_RUN / "run_metadata.json").read_text())
    command = list(prior["command"])
    command.remove("--compensate-delay")
    out_arg = command.index("--output-dir") + 1
    command[out_arg] = str(OUT / "native_predictions")
    OUT.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    with (OUT / "stdout.log").open("wb") as stdout, (OUT / "stderr.log").open("wb") as stderr:
        proc = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, check=False)
    elapsed = time.monotonic() - started

    output_files = sorted((OUT / "native_predictions").glob("*.wav"))
    if proc.returncode != 0 or len(output_files) != 590:
        raise SystemExit(
            f"Native run failed: returncode={proc.returncode}, outputs={len(output_files)}; "
            f"see {OUT}/stderr.log"
        )
    after = {str(path): sha256(path) for path in expected}
    if any(after[str(path)] != digest for path, digest in expected.items()):
        raise SystemExit(f"Protected artifact hash changed: {after}")
    metadata = {
        "diagnostic": "toggle only CLI --compensate-delay off; all other argv copied from Stage 11.2.23",
        "source_run_metadata": str(SOURCE_RUN / "run_metadata.json"),
        "command": command,
        "returncode": proc.returncode,
        "wall_seconds": elapsed,
        "output_count": len(output_files),
        "protected_hashes_before": {str(p): h for p, h in expected.items()},
        "protected_hashes_after": after,
        "gold_data_accessed": False,
        "kaggle_accessed": False,
        "raspberry_pi_accessed": False,
        "training_or_tuning": False,
    }
    (OUT / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    with (OUT / "output_hashes.csv").open("w") as f:
        f.write("filename,sha256\n")
        for path in output_files:
            f.write(f"{path.name},{sha256(path)}\n")
    print(json.dumps({k: metadata[k] for k in ("returncode", "wall_seconds", "output_count", "protected_hashes_after")}, indent=2))


if __name__ == "__main__":
    main()
