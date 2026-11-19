#!/usr/bin/env python3
"""Paired comparison of two evaluator outputs on the same frozen canonical clips."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


def load_rows(path: Path) -> tuple[dict[int, dict[str, str]], str]:
    summary_path = path.parent / "summary.json"
    if not summary_path.is_file():
        raise ValueError(f"Missing evaluator summary beside {path}")
    summary = json.loads(summary_path.read_text())
    manifest_hash = summary.get("canonical_manifest_sha256")
    if not manifest_hash:
        raise ValueError(f"Missing canonical manifest hash in {summary_path}")
    with path.open(newline="") as stream:
        rows = {int(row["val_index"]): row for row in csv.DictReader(stream)}
    if len(rows) != 590:
        raise ValueError(f"Expected 590 unique canonical clips in {path}, got {len(rows)}")
    return rows, manifest_hash


def stats(rows: list[dict[str, str]], metric: str) -> dict[str, float | int]:
    values = np.asarray([float(row[f"output_{metric}"]) for row in rows], dtype=np.float64)
    return {"n": int(values.size), "mean": float(np.nanmean(values))}


def paired_delta_ci(
    deltas: np.ndarray, rng: np.random.Generator, n_bootstrap: int
) -> dict[str, float]:
    draws = rng.integers(0, len(deltas), size=(n_bootstrap, len(deltas)))
    means = np.nanmean(deltas[draws], axis=1)
    return {
        "mean_candidate_minus_reference": float(np.nanmean(deltas)),
        "ci95_low": float(np.nanpercentile(means, 2.5)),
        "ci95_high": float(np.nanpercentile(means, 97.5)),
    }


def summarize_subset(rows: list[dict[str, str]]) -> dict[str, object]:
    metric_stats = {
        metric: stats(rows, metric) for metric in ("snr_db", "si_sdr_db", "stoi", "pesq_wb")
    }
    passed = [
        float(row["output_snr_db"]) > 15.0
        and float(row["output_stoi"]) > 0.85
        and float(row["output_pesq_wb"]) > 2.5
        for row in rows
    ]
    return {
        "count": len(rows),
        "means": metric_stats,
        "pass_counts": {
            "snr_gt_15_db": sum(float(r["output_snr_db"]) > 15.0 for r in rows),
            "stoi_gt_0_85": sum(float(r["output_stoi"]) > 0.85 for r in rows),
            "pesq_gt_2_5": sum(float(r["output_pesq_wb"]) > 2.5 for r in rows),
            "all_three": sum(passed),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True, help="Reference evaluator per_clip.csv")
    parser.add_argument("--candidate", type=Path, required=True, help="Candidate evaluator per_clip.csv")
    parser.add_argument("--output", type=Path, required=True, help="Write paired comparison JSON here")
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=26052)
    args = parser.parse_args()

    ref, ref_hash = load_rows(args.reference)
    cand, cand_hash = load_rows(args.candidate)
    if ref_hash != cand_hash:
        raise ValueError("Reference and candidate were not evaluated with the same canonical manifest")
    if ref.keys() != cand.keys():
        raise ValueError("Reference and candidate clip indices differ")

    ordered = sorted(ref)
    rng = np.random.default_rng(args.seed)
    metrics = ("snr_db", "si_sdr_db", "stoi", "pesq_wb")
    result: dict[str, object] = {
        "canonical_manifest_sha256": ref_hash,
        "clip_count": len(ordered),
        "reference": str(args.reference),
        "candidate": str(args.candidate),
        "bootstrap_resamples": args.bootstrap,
        "bootstrap_seed": args.seed,
        "criteria": {"output_snr_db_gt": 15.0, "stoi_gt": 0.85, "pesq_wb_gt": 2.5},
        "candidate_overall": summarize_subset([cand[i] for i in ordered]),
        "paired_deltas": {},
        "input_snr_ge_9_6_db": {},
        "by_target_snr": {},
    }
    for metric in metrics:
        differences = np.asarray(
            [float(cand[i][f"output_{metric}"]) - float(ref[i][f"output_{metric}"]) for i in ordered]
        )
        result["paired_deltas"][metric] = paired_delta_ci(differences, rng, args.bootstrap)

    above = [i for i in ordered if float(cand[i]["input_snr_db"]) >= 9.6]
    result["input_snr_ge_9_6_db"] = summarize_subset([cand[i] for i in above])
    target_groups: dict[str, list[int]] = {}
    for i in ordered:
        target_groups.setdefault(f"{float(cand[i]['target_snr_db']):g}", []).append(i)
    result["by_target_snr"] = {
        snr: summarize_subset([cand[i] for i in inds])
        for snr, inds in sorted(target_groups.items(), key=lambda pair: float(pair[0]))
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
