#!/usr/bin/env python3
"""Run the canonical evaluator and attach reproducibility metadata.

This is a thin orchestration layer: metric calculation remains exclusively in
evaluate_dfn3_canonical.py. Existing evaluator output directories are never
overwritten. An optional reference per-clip CSV produces paired comparisons
with the existing comparison script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXPECTED_MANIFEST_SHA256 = "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_commit() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--canonical-dir", type=Path, default=REPO / "runs/sih26052_canonical_validation")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, help="Optional inference configuration to hash")
    parser.add_argument("--expected-manifest-sha256", default=EXPECTED_MANIFEST_SHA256)
    parser.add_argument("--reference-per-clip", type=Path, help="Optional baseline per_clip.csv")
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=26052)
    parser.add_argument("--atten-lim-db", type=float)
    parser.add_argument("--post-gain-db", type=float, default=0.0)
    args = parser.parse_args()

    checkpoint = args.checkpoint.expanduser().resolve()
    canonical_dir = args.canonical_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    config = args.config.expanduser().resolve() if args.config else None
    reference = args.reference_per_clip.expanduser().resolve() if args.reference_per_clip else None

    if not checkpoint.is_file():
        parser.error(f"Checkpoint does not exist: {checkpoint}")
    if any(part.casefold() == "sih_gold_test" for part in canonical_dir.parts):
        parser.error("Refusing any SIH_GOLD_TEST path")
    manifest = canonical_dir / "manifest.csv"
    if not manifest.is_file():
        parser.error(f"Canonical manifest not found: {manifest}")
    manifest_hash = sha256(manifest)
    if manifest_hash != args.expected_manifest_sha256:
        parser.error(
            f"Canonical manifest hash mismatch: expected {args.expected_manifest_sha256}, got {manifest_hash}"
        )
    if config is not None and not config.is_file():
        parser.error(f"Configuration does not exist: {config}")
    if reference is not None and not reference.is_file():
        parser.error(f"Reference per-clip CSV does not exist: {reference}")
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"Refusing to overwrite non-empty output directory: {output_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    evaluator = REPO / "scripts/evaluate_dfn3_canonical.py"
    command = [
        sys.executable,
        str(evaluator),
        "--checkpoint", str(checkpoint),
        "--canonical-dir", str(canonical_dir),
        "--output-dir", str(output_dir),
        "--post-gain-db", str(args.post_gain_db),
    ]
    if args.atten_lim_db is not None:
        command.extend(["--atten-lim-db", str(args.atten_lim_db)])

    started = time.perf_counter()
    result = subprocess.run(command, cwd=REPO, check=False)
    elapsed_s = time.perf_counter() - started
    if result.returncode != 0:
        print(f"Canonical evaluator failed with exit code {result.returncode}", file=sys.stderr)
        return result.returncode

    summary_path = output_dir / "summary.json"
    per_clip_path = output_dir / "per_clip.csv"
    if not summary_path.is_file() or not per_clip_path.is_file():
        print("Evaluator returned success without both expected output files", file=sys.stderr)
        return 2

    import csv

    with manifest.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    total_audio_s = sum(int(row["length_samples"]) / int(row["sample_rate"]) for row in rows)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["reproducibility"] = {
        "git_commit": git_commit(),
        "evaluator_sha256": sha256(evaluator),
        "config_path": str(config) if config else None,
        "config_sha256": sha256(config) if config else None,
        "input_sample_rate_hz": 16000,
        "input_channels": 1,
        "elapsed_wall_seconds": elapsed_s,
        "canonical_audio_duration_seconds": total_audio_s,
        "wall_clock_real_time_factor": elapsed_s / total_audio_s if total_audio_s else None,
        "manifest_expected_sha256": args.expected_manifest_sha256,
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    if reference is not None:
        compare_script = REPO / "scripts/compare_dfn3_canonical_split.py"
        for split in ("all", "even", "odd"):
            comparison = output_dir / f"paired_vs_reference_{split}.json"
            compare_command = [
                sys.executable, str(compare_script),
                "--reference", str(reference),
                "--candidate", str(per_clip_path),
                "--output", str(comparison),
                "--split", split,
                "--bootstrap", str(args.bootstrap),
                "--seed", str(args.seed),
            ]
            compared = subprocess.run(compare_command, cwd=REPO, check=False)
            if compared.returncode != 0:
                print(f"Paired comparison ({split}) failed with exit code {compared.returncode}", file=sys.stderr)
                return compared.returncode

    print(f"Evaluation artifacts: {output_dir}")
    print(f"Elapsed wall time: {elapsed_s:.2f}s; audio duration: {total_audio_s:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
