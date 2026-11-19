#!/usr/bin/env python3
"""Simulate only the predeclared Stage 8 fixed-weight ensembles.

Reads saved waveform predictions; performs no model inference. Writes results
only into a new, isolated Phase C directory and never clips or normalizes the
mixed output. A single amplitude-matched equal-weight variant uses only the
fixed per-model median RMS values recorded in the Phase B report.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate_dfn3_canonical import metrics, sha256  # noqa: E402

MANIFEST_SHA256 = "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4"
METRIC_SHA256 = "66e448cc47b0ae60846399d803d8f6321068c5e4a9faa18f6ebb09305219b16a"
MODELS = ("step500", "fullsubnet", "gtcrn")
METRICS = ("snr_db", "si_sdr_db", "stoi", "pesq_wb")
EXPECTED_IDS = list(range(590))
BASELINE_DIRS = {
    "step500": ROOT / "runs/sih26052_candidate_step500_repro_20261113",
    "fullsubnet": ROOT / "runs/fullsubnet_baseline",
    "gtcrn": ROOT / "runs/gtcrn_dns3_canonical_20261113",
}
PREDICTION_DIRS = {
    "step500": ROOT / "runs/stage8_ensemble_20261113/step500_predictions",
    "fullsubnet": ROOT / "runs/stage8_ensemble_20261113/fullsubnet_predictions",
    "gtcrn": ROOT / "runs/gtcrn_dns3_canonical_20261113/predictions",
}
WEIGHTS = {
    "d1_equal_333_raw": (1 / 3, 1 / 3, 1 / 3),
    "d2_fs60_raw": (0.20, 0.60, 0.20),
    "d2_fs50_raw": (0.25, 0.50, 0.25),
    "d2_fs70_raw": (0.15, 0.70, 0.15),
    "d3_step500_fullsubnet_5050_raw": (0.50, 0.50, 0.00),
    "d3_step500_gtcrn_5050_raw": (0.50, 0.00, 0.50),
    "d3_fullsubnet_gtcrn_5050_raw": (0.00, 0.50, 0.50),
    "d1_equal_333_rms_matched": (1 / 3, 1 / 3, 1 / 3),
}
PHASE_B_MEDIAN_RMS = {
    "step500": 0.047933210502252965,
    "fullsubnet": 0.051765255788227035,
    "gtcrn": 0.05011982079309145,
}
TARGET_RMS = float(np.median(list(PHASE_B_MEDIAN_RMS.values())))
RMS_SCALES = {name: TARGET_RMS / value for name, value in PHASE_B_MEDIAN_RMS.items()}


def load_csv_map(path: Path) -> dict[int, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        result = {int(row["val_index"]): row for row in csv.DictReader(stream)}
    if set(result) != set(EXPECTED_IDS) or len(result) != 590:
        raise ValueError(f"Expected exact canonical ID coverage in {path}")
    return result


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    values = {
        metric: np.asarray([float(row[f"output_{metric}"]) for row in rows], dtype=np.float64)
        for metric in METRICS
    }
    pass_snr = values["snr_db"] > 15.0
    pass_stoi = values["stoi"] > 0.85
    pass_pesq = values["pesq_wb"] > 2.5
    joint = pass_snr & pass_stoi & pass_pesq
    return {
        "count": len(rows),
        "means": {metric: float(np.mean(array)) for metric, array in values.items()},
        "medians": {metric: float(np.median(array)) for metric, array in values.items()},
        "pass_counts": {
            "snr_gt_15_db": int(pass_snr.sum()),
            "stoi_gt_0_85": int(pass_stoi.sum()),
            "pesq_gt_2_5": int(pass_pesq.sum()),
            "all_three": int(joint.sum()),
            "all_three_rate": float(joint.mean()),
        },
    }


def score_group(rows: list[dict[str, object]]) -> dict[str, object]:
    if not rows:
        raise ValueError("Cannot summarize empty group")
    return summarize(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "runs/stage8_ensemble_20261113/phase_c_ensembles",
    )
    args = parser.parse_args()

    manifest = ROOT / "runs/sih26052_canonical_validation/manifest.csv"
    if sha256(manifest) != MANIFEST_SHA256:
        raise SystemExit("Frozen canonical manifest hash mismatch")
    if sha256(ROOT / "scripts/evaluate_dfn3_canonical.py") != METRIC_SHA256:
        raise SystemExit("Canonical metric evaluator changed; refusing to simulate")
    manifest_rows = list(csv.DictReader(manifest.open(newline="", encoding="utf-8")))
    if [int(row["val_index"]) for row in manifest_rows] != EXPECTED_IDS:
        raise SystemExit("Canonical manifest clip IDs are not the expected sequence")

    output_root = args.output_root.expanduser().resolve()
    if output_root.exists():
        raise SystemExit(f"Refusing to overwrite Phase C output root: {output_root}")
    output_root.mkdir(parents=True)

    baseline_rows = {}
    baseline_summaries = {}
    baseline_hashes = {}
    for model, directory in BASELINE_DIRS.items():
        summary_path = directory / "summary.json"
        per_clip_path = directory / "per_clip.csv"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("canonical_manifest_sha256") != MANIFEST_SHA256:
            raise SystemExit(f"{model} baseline manifest mismatch")
        baseline_rows[model] = load_csv_map(per_clip_path)
        baseline_summaries[model] = summary
        baseline_hashes[model] = {"per_clip_csv": sha256(per_clip_path), "summary_json": sha256(summary_path)}

    # Read and hash-verify every saved source prediction before constructing any mixture.
    ledgers = {
        "step500": load_csv_map(PREDICTION_DIRS["step500"] / "prediction_files.csv"),
        "fullsubnet": load_csv_map(PREDICTION_DIRS["fullsubnet"] / "prediction_files.csv"),
        "gtcrn": load_csv_map(ROOT / "runs/gtcrn_dns3_canonical_20261113/inference_per_clip.csv"),
    }
    ledger_hash_field = {"step500": "sha256", "fullsubnet": "sha256", "gtcrn": "output_sha256"}
    verified_source_files = {model: 0 for model in MODELS}
    for model in MODELS:
        for clip_id in EXPECTED_IDS:
            path = PREDICTION_DIRS[model] / f"{clip_id:04d}_enhanced.wav"
            if sha256(path) != ledgers[model][clip_id][ledger_hash_field[model]]:
                raise SystemExit(f"Source waveform hash mismatch: {model}, clip {clip_id}")
            verified_source_files[model] += 1

    # Each variant uses predeclared fixed weights. RMS matching applies fixed global
    # scalar factors derived from Phase B output-only median RMS values, no clean audio
    # or metric outcomes; it does not normalize individual clips.
    specifications = {}
    for name, weights in WEIGHTS.items():
        scales = RMS_SCALES if name.endswith("rms_matched") else {model: 1.0 for model in MODELS}
        specifications[name] = {"weights": dict(zip(MODELS, weights)), "scales": scales}

    start_all = time.perf_counter()
    result_rows = {name: [] for name in specifications}
    file_records = {name: [] for name in specifications}
    source_ledgers_before = {
        model: {i: ledgers[model][i][ledger_hash_field[model]] for i in EXPECTED_IDS}
        for model in MODELS
    }

    for position, manifest_row in enumerate(manifest_rows, start=1):
        clip_id = int(manifest_row["val_index"])
        source_arrays = {}
        for model in MODELS:
            path = PREDICTION_DIRS[model] / f"{clip_id:04d}_enhanced.wav"
            wave, sr = sf.read(path, dtype="float32")
            if sr != 16000 or wave.ndim != 1 or len(wave) != 48000 or not np.isfinite(wave).all():
                raise ValueError(f"Invalid source waveform {model} clip {clip_id}")
            source_arrays[model] = wave

        clean, clean_sr = sf.read(ROOT / "runs/sih26052_canonical_validation/clean_audio" / f"{clip_id:04d}_clean.wav", dtype="float32")
        noisy, noisy_sr = sf.read(ROOT / "runs/sih26052_canonical_validation/noisy_audio" / f"{clip_id:04d}_noisy.wav", dtype="float32")
        if clean_sr != 16000 or noisy_sr != 16000 or clean.shape != (48000,) or noisy.shape != (48000,):
            raise ValueError(f"Invalid canonical scoring pair for clip {clip_id}")
        input_metrics = metrics(clean, noisy)

        for name, spec in specifications.items():
            mix = np.zeros(48000, dtype=np.float32)
            for model in MODELS:
                weight = np.float32(spec["weights"][model])
                scale = np.float32(spec["scales"][model])
                mix += weight * (scale * source_arrays[model])
            if not np.isfinite(mix).all():
                raise ValueError(f"Non-finite mixture: {name}, clip {clip_id}")

            run_dir = output_root / name
            prediction_dir = run_dir / "predictions"
            if position == 1:
                run_dir.mkdir()
                prediction_dir.mkdir()
            out_path = prediction_dir / f"{clip_id:04d}_enhanced.wav"
            sf.write(out_path, mix, 16000, subtype="FLOAT")
            saved, saved_sr = sf.read(out_path, dtype="float32")
            if saved_sr != 16000 or saved.shape != clean.shape or not np.isfinite(saved).all():
                raise ValueError(f"Saved mixture is invalid/misaligned: {name}, clip {clip_id}")

            output_metrics = metrics(clean, saved)
            row = {
                "val_index": clip_id,
                "origin": manifest_row.get("dataset_origin", "UNKNOWN"),
                "target_snr_db": float(manifest_row["target_snr"]),
                "input_snr_db": input_metrics["snr_db"],
                **{f"input_{key}": value for key, value in input_metrics.items() if key != "snr_db"},
                **{f"output_{key}": value for key, value in output_metrics.items()},
            }
            result_rows[name].append(row)
            file_records[name].append({
                "val_index": clip_id,
                "relative_path": str(out_path.relative_to(output_root)),
                "sha256": sha256(out_path),
                "sample_rate_hz": 16000,
                "channels": 1,
                "sample_count": len(saved),
                "duration_seconds": len(saved) / 16000,
                "peak_abs": float(np.max(np.abs(saved))),
                "finite": True,
            })
        if position % 25 == 0 or position == 590:
            print(f"Simulated and scored {position}/590 clips for {len(specifications)} fixed variants", flush=True)

    # Ensure source prediction hashes remain exactly as recorded.
    for model in MODELS:
        for clip_id in EXPECTED_IDS:
            path = PREDICTION_DIRS[model] / f"{clip_id:04d}_enhanced.wav"
            if sha256(path) != source_ledgers_before[model][clip_id]:
                raise RuntimeError(f"Source prediction changed during simulation: {model}, clip {clip_id}")

    summary_index = {}
    for name, rows in result_rows.items():
        run_dir = output_root / name
        per_clip = run_dir / "per_clip.csv"
        with per_clip.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        files_csv = run_dir / "prediction_files.csv"
        with files_csv.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(file_records[name][0]))
            writer.writeheader()
            writer.writerows(file_records[name])
        strata = {}
        for row in rows:
            strata.setdefault(f"{float(row['target_snr_db']):g}", []).append(row)
        low = [row for row in rows if float(row["target_snr_db"]) <= 0]
        spec = specifications[name]
        summary = {
            "variant": name,
            "canonical_manifest_sha256": MANIFEST_SHA256,
            "metric_implementation": "scripts/evaluate_dfn3_canonical.py::metrics",
            "metric_implementation_sha256": METRIC_SHA256,
            "input_waveforms": {model: str(PREDICTION_DIRS[model]) for model in MODELS},
            "input_hashes_verified": verified_source_files,
            "weights": spec["weights"],
            "global_model_scales": spec["scales"],
            "amplitude_policy": "raw float32 weighted sum; no clipping or output normalization" if not name.endswith("rms_matched") else "apply fixed global scalar per model to make Phase B dataset median RMS equal to 0.05011982079309145, then fixed equal-thirds sum; no per-clip normalization, clipping, or output normalization",
            "scale_reference_median_rms": PHASE_B_MEDIAN_RMS if name.endswith("rms_matched") else None,
            "summary_all": summarize(rows),
            "summary_target_snr_le_0_db": summarize(low),
            "by_target_snr": {key: summarize(value) for key, value in sorted(strata.items(), key=lambda pair: float(pair[0]))},
            "prediction_count": len(file_records[name]),
            "per_clip_csv_sha256": sha256(per_clip),
            "prediction_files_csv_sha256": sha256(files_csv),
        }
        summary_path = run_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        summary_index[name] = {"summary": summary, "summary_path": str(summary_path), "per_clip_path": str(per_clip)}

    # Run the established paired comparator for each ensemble against all three baselines.
    paired_dir = output_root / "paired_comparisons"
    paired_dir.mkdir()
    commands = []
    for name in specifications:
        candidate_csv = output_root / name / "per_clip.csv"
        for reference in MODELS:
            output_json = paired_dir / f"{name}_vs_{reference}.json"
            command = [
                sys.executable,
                str(ROOT / "scripts/compare_dfn3_canonical.py"),
                "--reference", str(BASELINE_DIRS[reference] / "per_clip.csv"),
                "--candidate", str(candidate_csv),
                "--output", str(output_json),
                "--bootstrap", "2000", "--seed", "26052",
            ]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            commands.append({"command": command, "exit_code": result.returncode, "stdout_tail": result.stdout[-1000:], "stderr_tail": result.stderr[-1000:]})
            if result.returncode != 0:
                raise RuntimeError(f"Paired comparison failed for {name} vs {reference}: {result.stderr}")

    run_record = {
        "created_by": "scripts/run_stage8_ensemble_simulations.py",
        "simulation_script_sha256": sha256(Path(__file__)),
        "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(),
        "python": sys.version,
        "numpy": np.__version__,
        "soundfile": sf.__version__,
        "manifest_sha256": sha256(manifest),
        "metric_evaluator_sha256": sha256(ROOT / "scripts/evaluate_dfn3_canonical.py"),
        "paired_comparator_sha256": sha256(ROOT / "scripts/compare_dfn3_canonical.py"),
        "source_prediction_hashes_verified_before_and_after": verified_source_files,
        "baseline_artifacts": baseline_hashes,
        "baseline_checkpoint_sha256": {model: baseline_summaries[model].get("checkpoint_sha256") for model in MODELS},
        "weights_and_scales": specifications,
        "rms_match_target": TARGET_RMS,
        "rms_match_scales": RMS_SCALES,
        "clip_count_per_variant": 590,
        "variant_count": len(specifications),
        "ensemble_waveform_count": sum(len(items) for items in file_records.values()),
        "paired_comparison_count": len(commands),
        "paired_comparison_commands": commands,
        "simulation_and_scoring_elapsed_wall_seconds": time.perf_counter() - start_all,
        "no_inference_no_training_no_tuning_no_clipping": True,
    }
    (output_root / "run_record.json").write_text(json.dumps(run_record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output_root": str(output_root),
        "variant_count": len(specifications),
        "ensemble_waveform_count": run_record["ensemble_waveform_count"],
        "paired_comparison_count": run_record["paired_comparison_count"],
        "rms_match_target": TARGET_RMS,
        "rms_match_scales": RMS_SCALES,
        "elapsed_seconds": run_record["simulation_and_scoring_elapsed_wall_seconds"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
