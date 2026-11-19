#!/usr/bin/env python3
"""Create the required Stage 8 ensemble tables and evidence report."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ENSEMBLE_ROOT = ROOT / "runs/stage8_ensemble_20261113/phase_c_ensembles"
RESEARCH = ROOT / "research"
MANIFEST_HASH = "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4"
SEED = 26052
N_BOOT = 2000
METRICS = ("snr_db", "si_sdr_db", "stoi", "pesq_wb")
MODEL_ORDER = ("step500", "fullsubnet", "gtcrn")
BASELINE_DIR = {
    "step500": ROOT / "runs/sih26052_candidate_step500_repro_20261113",
    "fullsubnet": ROOT / "runs/fullsubnet_baseline",
    "gtcrn": ROOT / "runs/gtcrn_dns3_canonical_20261113",
}
VARIANTS = (
    "d1_equal_333_raw",
    "d1_equal_333_rms_matched",
    "d2_fs60_raw",
    "d2_fs50_raw",
    "d2_fs70_raw",
    "d3_step500_fullsubnet_5050_raw",
    "d3_step500_gtcrn_5050_raw",
    "d3_fullsubnet_gtcrn_5050_raw",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as stream:
        rows = {int(row["val_index"]): row for row in csv.DictReader(stream)}
    if set(rows) != set(range(590)):
        raise ValueError(f"Invalid canonical clip IDs in {path}")
    return rows


def summarize(rows: list[dict[str, str]]):
    vals = {m: np.asarray([float(r[f"output_{m}"]) for r in rows], dtype=np.float64) for m in METRICS}
    p_snr = vals["snr_db"] > 15.0
    p_stoi = vals["stoi"] > 0.85
    p_pesq = vals["pesq_wb"] > 2.5
    joint = p_snr & p_stoi & p_pesq
    return {
        "n": len(rows),
        "mean": {m: float(np.mean(v)) for m, v in vals.items()},
        "median": {m: float(np.median(v)) for m, v in vals.items()},
        "pass": {
            "snr": int(p_snr.sum()), "stoi": int(p_stoi.sum()),
            "pesq": int(p_pesq.sum()), "joint": int(joint.sum()),
            "joint_pct": float(joint.mean() * 100.0),
        },
    }


def paired_ci(candidate, reference, ids, metric):
    delta = np.asarray([
        float(candidate[i][f"output_{metric}"]) - float(reference[i][f"output_{metric}"])
        for i in ids
    ], dtype=np.float64)
    rng = np.random.default_rng(SEED)
    draws = rng.integers(0, len(delta), size=(N_BOOT, len(delta)))
    means = np.mean(delta[draws], axis=1)
    return float(np.mean(delta)), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def csv_write(path: Path, rows: list[dict[str, object]]):
    if not rows:
        raise ValueError(f"No rows to write: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    run_record_path = ENSEMBLE_ROOT / "run_record.json"
    run_record = json.loads(run_record_path.read_text(encoding="utf-8"))
    if run_record["manifest_sha256"] != MANIFEST_HASH or run_record["paired_comparison_count"] != 24:
        raise SystemExit("Phase C run record failed required manifest/comparison checks")

    base_rows = {name: read_rows(BASELINE_DIR[name] / "per_clip.csv") for name in MODEL_ORDER}
    mix_rows = {name: read_rows(ENSEMBLE_ROOT / name / "per_clip.csv") for name in VARIANTS}
    mix_summaries = {name: json.loads((ENSEMBLE_ROOT / name / "summary.json").read_text(encoding="utf-8")) for name in VARIANTS}
    base_summaries = {name: summarize([base_rows[name][i] for i in range(590)]) for name in MODEL_ORDER}

    # Summary table: all baselines and fixed variants, including the combined <= 0 dB group.
    summary_rows = []
    for name in (*MODEL_ORDER, *VARIANTS):
        source = base_rows[name] if name in MODEL_ORDER else mix_rows[name]
        all_stats = summarize([source[i] for i in range(590)])
        low_ids = [i for i in range(590) if float(source[i]["target_snr_db"]) <= 0.0]
        low_stats = summarize([source[i] for i in low_ids])
        conf = mix_summaries[name] if name in VARIANTS else {}
        weights = conf.get("weights", {})
        scales = conf.get("global_model_scales", {})
        if name in VARIANTS:
            with (ENSEMBLE_ROOT / name / "prediction_files.csv").open(newline="", encoding="utf-8") as stream:
                peak_records = list(csv.DictReader(stream))
            peak_max = max(float(row["peak_abs"]) for row in peak_records)
            peaks_gt_one = sum(float(row["peak_abs"]) > 1.0 for row in peak_records)
        else:
            peak_max, peaks_gt_one = "", ""
        out = {
            "model_or_variant": name,
            "scope": "standalone" if name in MODEL_ORDER else "fixed_ensemble_diagnostic",
            "weights_step500": weights.get("step500", ""),
            "weights_fullsubnet": weights.get("fullsubnet", ""),
            "weights_gtcrn": weights.get("gtcrn", ""),
            "scale_step500": scales.get("step500", ""),
            "scale_fullsubnet": scales.get("fullsubnet", ""),
            "scale_gtcrn": scales.get("gtcrn", ""),
            "output_peak_abs_max": peak_max,
            "output_files_peak_abs_gt_1_count": peaks_gt_one,
            "n": all_stats["n"],
        }
        for metric in METRICS:
            out[f"mean_{metric}"] = all_stats["mean"][metric]
            out[f"median_{metric}"] = all_stats["median"][metric]
            out[f"le0_mean_{metric}"] = low_stats["mean"][metric]
            out[f"le0_median_{metric}"] = low_stats["median"][metric]
        out.update({
            "pass_snr_count": all_stats["pass"]["snr"],
            "pass_stoi_count": all_stats["pass"]["stoi"],
            "pass_pesq_count": all_stats["pass"]["pesq"],
            "joint_pass_count": all_stats["pass"]["joint"],
            "joint_pass_pct": all_stats["pass"]["joint_pct"],
            "le0_n": low_stats["n"],
            "le0_joint_pass_count": low_stats["pass"]["joint"],
            "le0_joint_pass_pct": low_stats["pass"]["joint_pct"],
        })
        summary_rows.append(out)
    summary_path = RESEARCH / "STAGE8_ENSEMBLE_SUMMARY.csv"
    csv_write(summary_path, summary_rows)

    # All paired CIs are from the unchanged comparator JSON. Add paired low-bin CIs
    # using its same percentile-of-paired-means method, seed, and resample count.
    comparison_rows = []
    for variant in VARIANTS:
        for reference in MODEL_ORDER:
            json_path = ENSEMBLE_ROOT / "paired_comparisons" / f"{variant}_vs_{reference}.json"
            paired = json.loads(json_path.read_text(encoding="utf-8"))
            full_ids = list(range(590))
            low_ids = [i for i in full_ids if float(mix_rows[variant][i]["target_snr_db"]) <= 0.0]
            for metric in METRICS:
                data = paired["paired_deltas"][metric]
                comparison_rows.append({
                    "variant": variant, "reference_model": reference, "subset": "all_590", "metric": metric,
                    "n": 590, "mean_candidate_minus_reference": data["mean_candidate_minus_reference"],
                    "ci95_low": data["ci95_low"], "ci95_high": data["ci95_high"],
                    "bootstrap_resamples": N_BOOT, "bootstrap_seed": SEED,
                    "method_script": "scripts/compare_dfn3_canonical.py",
                })
                mean, low, high = paired_ci(mix_rows[variant], base_rows[reference], low_ids, metric)
                comparison_rows.append({
                    "variant": variant, "reference_model": reference, "subset": "target_snr_le_0_db", "metric": metric,
                    "n": len(low_ids), "mean_candidate_minus_reference": mean,
                    "ci95_low": low, "ci95_high": high,
                    "bootstrap_resamples": N_BOOT, "bootstrap_seed": SEED,
                    "method_script": "scripts/summarize_stage8_ensembles.py using the comparator's paired percentile-mean method",
                })
    # Explicit amplitude-policy contrast: fixed RMS-matched D1 versus unscaled D1.
    # This is not a model search; it isolates the single declared gain policy.
    for metric in METRICS:
        all_ids = list(range(590))
        low_ids = [i for i in all_ids if float(mix_rows["d1_equal_333_raw"][i]["target_snr_db"]) <= 0.0]
        for scope, ids in (("all_590", all_ids), ("target_snr_le_0_db", low_ids)):
            mean, low, high = paired_ci(mix_rows["d1_equal_333_rms_matched"], mix_rows["d1_equal_333_raw"], ids, metric)
            comparison_rows.append({
                "variant": "d1_equal_333_rms_matched", "reference_model": "d1_equal_333_raw", "subset": scope,
                "metric": metric, "n": len(ids), "mean_candidate_minus_reference": mean,
                "ci95_low": low, "ci95_high": high, "bootstrap_resamples": N_BOOT,
                "bootstrap_seed": SEED, "method_script": "scripts/summarize_stage8_ensembles.py using the comparator's paired percentile-mean method",
            })
    comparison_path = RESEARCH / "STAGE8_ENSEMBLE_PAIRED_COMPARISONS.csv"
    csv_write(comparison_path, comparison_rows)

    # Per-target-SNR strata for standalone baselines and every fixed ensemble.
    snr_rows = []
    for name in (*MODEL_ORDER, *VARIANTS):
        source = base_rows[name] if name in MODEL_ORDER else mix_rows[name]
        bins = {}
        for i in range(590):
            key = f"{float(source[i]['target_snr_db']):g}"
            bins.setdefault(key, []).append(source[i])
        for target, rows in sorted(bins.items(), key=lambda item: float(item[0])):
            stats = summarize(rows)
            snr_rows.append({
                "model_or_variant": name, "target_snr_db": float(target), "n": stats["n"],
                **{f"mean_{m}": stats["mean"][m] for m in METRICS},
                **{f"median_{m}": stats["median"][m] for m in METRICS},
                "pass_snr_count": stats["pass"]["snr"], "pass_stoi_count": stats["pass"]["stoi"],
                "pass_pesq_count": stats["pass"]["pesq"], "joint_pass_count": stats["pass"]["joint"],
                "joint_pass_pct": stats["pass"]["joint_pct"],
            })
    snr_path = RESEARCH / "STAGE8_ENSEMBLE_SNR_BINS.csv"
    csv_write(snr_path, snr_rows)

    # Oracle diagnostics are strictly post hoc and use the stored standalone per-clip metrics.
    oracle_rows = []
    def add_oracle(diagnostic, metric, model, value, *, mean=None, median=None, fraction=None, leakage=False):
        oracle_rows.append({
            "diagnostic": diagnostic, "metric": metric, "model": model, "n": 590,
            "value": value, "mean": mean, "median": median, "fraction": fraction,
            "selection_uses_reference_metrics": leakage,
        })
    joint = {}
    metric_values = {m: {model: np.asarray([float(base_rows[model][i][f"output_{m}"]) for i in range(590)]) for model in MODEL_ORDER} for m in METRICS}
    joint = {model: np.asarray([
        float(base_rows[model][i]["output_snr_db"]) > 15.0
        and float(base_rows[model][i]["output_stoi"]) > 0.85
        and float(base_rows[model][i]["output_pesq_wb"]) > 2.5
        for i in range(590)
    ]) for model in MODEL_ORDER}
    union = np.logical_or.reduce([joint[m] for m in MODEL_ORDER])
    for model in MODEL_ORDER:
        add_oracle("individual_model_joint_pass", "joint", model, int(joint[model].sum()), fraction=float(joint[model].mean()))
    add_oracle("oracle_any_model_joint_pass_union", "joint", "oracle_union", int(union.sum()), fraction=float(union.mean()), leakage=True)
    add_oracle("best_joint_outcome_selector", "joint", "oracle_selector", int(union.sum()), fraction=float(union.mean()), leakage=True)
    winner_counts = {}
    for metric in METRICS:
        matrix = np.stack([metric_values[metric][model] for model in MODEL_ORDER], axis=0)
        best = np.max(matrix, axis=0)
        winner = np.argmax(matrix, axis=0)
        for j, model in enumerate(MODEL_ORDER):
            winner_counts[(metric, model)] = int(np.count_nonzero(winner == j))
        add_oracle("per_clip_best_metric_upper_bound", metric, "oracle_best_per_clip", "", mean=float(np.mean(best)), median=float(np.median(best)), leakage=True)
        for j, model in enumerate(MODEL_ORDER):
            count = winner_counts[(metric, model)]
            add_oracle("per_clip_best_metric_winner_count", metric, model, count, fraction=count / 590, leakage=True)
    oracle_path = RESEARCH / "STAGE8_ORACLE_DIAGNOSTICS.csv"
    csv_write(oracle_path, oracle_rows)

    # Descriptive clipwise behavior against each fixed baseline, including flagged IDs.
    exception_ids = {162, 436}
    diagnostic_rows = []
    for variant in VARIANTS:
        candidate = mix_rows[variant]
        worse_than_all = 0
        allfour_counts = {}
        snr_up_quality_down = {}
        worse_than_each = {}
        for reference in MODEL_ORDER:
            ref = base_rows[reference]
            all_four = []
            snr_up_q_down = []
            worse_all_metrics = []
            for i in range(590):
                diffs = {m: float(candidate[i][f"output_{m}"]) - float(ref[i][f"output_{m}"]) for m in METRICS}
                all_four.append(all(v > 0 for v in diffs.values()))
                snr_up_q_down.append(diffs["snr_db"] > 0 and (diffs["stoi"] < 0 or diffs["pesq_wb"] < 0))
                worse_all_metrics.append(all(v < 0 for v in diffs.values()))
            allfour_counts[reference] = int(sum(all_four))
            snr_up_quality_down[reference] = int(sum(snr_up_q_down))
            worse_than_each[reference] = int(sum(worse_all_metrics))
        for i in range(590):
            worse_all_models_all_metrics = all(
                all(float(candidate[i][f"output_{m}"]) < float(base_rows[ref][i][f"output_{m}"]) for m in METRICS)
                for ref in MODEL_ORDER
            )
            worse_than_all += int(worse_all_models_all_metrics)
        diagnostic_rows.append({
            "variant": variant,
            "improves_all_four_vs_step500_count": allfour_counts["step500"],
            "improves_all_four_vs_fullsubnet_count": allfour_counts["fullsubnet"],
            "improves_all_four_vs_gtcrn_count": allfour_counts["gtcrn"],
            "snr_up_but_stoi_or_pesq_down_vs_step500_count": snr_up_quality_down["step500"],
            "snr_up_but_stoi_or_pesq_down_vs_fullsubnet_count": snr_up_quality_down["fullsubnet"],
            "snr_up_but_stoi_or_pesq_down_vs_gtcrn_count": snr_up_quality_down["gtcrn"],
            "worse_all_four_than_step500_count": worse_than_each["step500"],
            "worse_all_four_than_fullsubnet_count": worse_than_each["fullsubnet"],
            "worse_all_four_than_gtcrn_count": worse_than_each["gtcrn"],
            "worse_all_four_than_all_three_models_count": worse_than_all,
            "alignment_exception_ids_162_436": "flagged; no clip-specific adjustment",
        })
    diagnostics_path = RESEARCH / "STAGE8_ENSEMBLE_CLIPWISE_DIAGNOSTICS.csv"
    csv_write(diagnostics_path, diagnostic_rows)
    alignment_flag_rows = []
    for variant in VARIANTS:
        for clip_id in (162, 436):
            alignment_flag_rows.append({
                "variant": variant,
                "val_index": clip_id,
                "alignment_correlation_exception": True,
                "finding": "Step-500 vs FullSubNet correlation ambiguous near +128 ms bounded search edge; no correction applied",
            })
    alignment_flags_path = RESEARCH / "STAGE8_ENSEMBLE_ALIGNMENT_FLAGS.csv"
    csv_write(alignment_flags_path, alignment_flag_rows)

    # Hash inventory for source inputs, generated waveforms, comparison outputs,
    # and required report tables. Individual source WAV hashes remain recorded
    # in their existing ledgers; every generated WAV is listed here as well.
    artifact_hash_rows = []

    def record_artifact(path: Path, kind: str):
        artifact_hash_rows.append({
            "artifact_type": kind,
            "relative_path": str(path.relative_to(ROOT)),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })

    for path in (
        ROOT / "runs/sih26052_canonical_validation/manifest.csv",
        ROOT / "runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt",
        ROOT / "checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar",
        ROOT / "checkpoints/gtcrn_stage5/model_trained_on_dns3.tar",
    ):
        record_artifact(path, "protected_manifest_or_checkpoint")
    for path in (
        ROOT / "runs/stage8_ensemble_20261113/step500_predictions/prediction_files.csv",
        ROOT / "runs/stage8_ensemble_20261113/fullsubnet_predictions/prediction_files.csv",
        ROOT / "runs/gtcrn_dns3_canonical_20261113/inference_per_clip.csv",
    ):
        record_artifact(path, "source_prediction_hash_ledger")
    for path in (
        ROOT / "scripts/evaluate_dfn3_canonical.py",
        ROOT / "scripts/compare_dfn3_canonical.py",
        ROOT / "scripts/run_stage8_ensemble_simulations.py",
        ROOT / "scripts/summarize_stage8_ensembles.py",
    ):
        record_artifact(path, "source_code")
    for path in (
        RESEARCH / "STAGE8_ENSEMBLE_SUMMARY.csv",
        RESEARCH / "STAGE8_ENSEMBLE_PAIRED_COMPARISONS.csv",
        RESEARCH / "STAGE8_ENSEMBLE_SNR_BINS.csv",
        RESEARCH / "STAGE8_ORACLE_DIAGNOSTICS.csv",
        RESEARCH / "STAGE8_ENSEMBLE_CLIPWISE_DIAGNOSTICS.csv",
        RESEARCH / "STAGE8_ENSEMBLE_ALIGNMENT_FLAGS.csv",
    ):
        record_artifact(path, "analysis_table")
    for path in sorted(ENSEMBLE_ROOT.rglob("*")):
        if path.is_file() and path.name != "PHASE_C_ARTIFACT_HASHES.csv":
            kind = "ensemble_waveform" if path.suffix == ".wav" else "ensemble_run_artifact"
            record_artifact(path, kind)
    artifact_hash_path = ENSEMBLE_ROOT / "PHASE_C_ARTIFACT_HASHES.csv"
    csv_write(artifact_hash_path, artifact_hash_rows)
    artifact_hash_sha = sha256(artifact_hash_path)

    # Parameter and storage estimates from existing metadata/artifacts.
    parameters = {"step500": 2_135_484, "fullsubnet": 5_637_635, "gtcrn": 48_245}
    ckpts = {
        "step500": ROOT / "runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt",
        "fullsubnet": ROOT / "checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar",
        "gtcrn": ROOT / "checkpoints/gtcrn_stage5/model_trained_on_dns3.tar",
    }
    checkpoint_bytes = {key: path.stat().st_size for key, path in ckpts.items()}
    best_variant = max(VARIANTS, key=lambda name: summarize([mix_rows[name][i] for i in range(590)])["pass"]["joint"])
    best_stats = summarize([mix_rows[best_variant][i] for i in range(590)])
    oracle_joint = int(union.sum())
    fs_joint = int(joint["fullsubnet"].sum())
    best_low_rows = [mix_rows[best_variant][i] for i in range(590) if float(mix_rows[best_variant][i]["target_snr_db"]) <= 0]
    best_low_stats = summarize(best_low_rows)
    fs_low_stats = summarize([base_rows["fullsubnet"][i] for i in range(590) if float(base_rows["fullsubnet"][i]["target_snr_db"]) <= 0])

    # Report selected paired comparisons vs FullSubNet using exact stored bootstrap JSON.
    key_variants = ("d1_equal_333_raw", "d2_fs60_raw", "d2_fs70_raw", "d3_step500_fullsubnet_5050_raw", "d3_step500_gtcrn_5050_raw", "d3_fullsubnet_gtcrn_5050_raw")
    paired_lines = []
    for name in key_variants:
        p = json.loads((ENSEMBLE_ROOT / "paired_comparisons" / f"{name}_vs_fullsubnet.json").read_text(encoding="utf-8"))
        cells = []
        for m, label in zip(METRICS, ("SNR", "SI-SDR", "STOI", "PESQ-WB")):
            v = p["paired_deltas"][m]
            cells.append(f"{label} {v['mean_candidate_minus_reference']:+.3f} [{v['ci95_low']:+.3f}, {v['ci95_high']:+.3f}]")
        paired_lines.append(f"| {name} | " + " | ".join(cells) + " |")

    amp_rows = [r for r in comparison_rows if r["reference_model"] == "d1_equal_333_raw" and r["subset"] == "all_590"]
    amp_line = " | ".join(
        f"{r['metric']} {r['mean_candidate_minus_reference']:+.4f} [{r['ci95_low']:+.4f}, {r['ci95_high']:+.4f}]"
        for r in amp_rows
    )
    low_d2 = [r for r in comparison_rows if r["variant"] == "d2_fs70_raw" and r["reference_model"] == "fullsubnet" and r["subset"] == "target_snr_le_0_db"]
    low_d2_line = " | ".join(
        f"{r['metric']} {r['mean_candidate_minus_reference']:+.3f} [{r['ci95_low']:+.3f}, {r['ci95_high']:+.3f}]"
        for r in low_d2
    )
    d2_clipwise = next(row for row in diagnostic_rows if row["variant"] == "d2_fs70_raw")
    oracle_metric_rows = [row for row in oracle_rows if row["diagnostic"] == "per_clip_best_metric_upper_bound"]
    oracle_metric_table = ["| Metric | Oracle mean of per-clip maxima | Oracle median of per-clip maxima |", "|---|---:|---:|"]
    for row in oracle_metric_rows:
        oracle_metric_table.append(f"| {row['metric']} | {row['mean']:.5f} | {row['median']:.5f} |")
    peak_rows = []
    for name in VARIANTS:
        with (ENSEMBLE_ROOT / name / "prediction_files.csv").open(newline="", encoding="utf-8") as stream:
            peaks = [float(row["peak_abs"]) for row in csv.DictReader(stream)]
        peak_rows.append(f"| {name} | {max(peaks):.6f} | {sum(value > 1.0 for value in peaks)} |")

    summary_table = ["| Model / variant | Mean SNR | Mean SI-SDR | Mean STOI | Mean PESQ-WB | Joint pass |", "|---|---:|---:|---:|---:|---:|"]
    for name in (*MODEL_ORDER, *VARIANTS):
        s = base_summaries[name] if name in MODEL_ORDER else summarize([mix_rows[name][i] for i in range(590)])
        summary_table.append(
            f"| {name} | {s['mean']['snr_db']:.3f} | {s['mean']['si_sdr_db']:.3f} | {s['mean']['stoi']:.5f} | {s['mean']['pesq_wb']:.5f} | {s['pass']['joint']}/590 ({s['pass']['joint_pct']:.1f}%) |"
        )

    low_table = ["| Model / variant | n | SNR | SI-SDR | STOI | PESQ-WB | Joint pass |", "|---|---:|---:|---:|---:|---:|---:|"]
    for name in (*MODEL_ORDER, *VARIANTS):
        source = base_rows[name] if name in MODEL_ORDER else mix_rows[name]
        selected = [source[i] for i in range(590) if float(source[i]["target_snr_db"]) <= 0.0]
        s = summarize(selected)
        low_table.append(f"| {name} | {s['n']} | {s['mean']['snr_db']:.3f} | {s['mean']['si_sdr_db']:.3f} | {s['mean']['stoi']:.5f} | {s['mean']['pesq_wb']:.5f} | {s['pass']['joint']}/{s['n']} |")

    rtf_step = 27.99813282757532 / 1770.0
    rtf_full = 195.45172123902012 / 1770.0
    rtf_gtcrn = 17.241890417644754 / 1770.0
    report = f"""# SIH 26052 — Stage 8 Three-Model Ensemble Feasibility

**Status:** fixed, offline diagnostic simulations complete. No training, inference, unrestricted weight search, gold-set access, Kaggle/Pi access, promotion, or deployment occurred. The protected Step-500 model remains unchanged.

## Method and predeclared configurations

Phase A/B verified 590 waveform predictions per model and common 16 kHz / mono / 48,000-sample grids. Phase B had two ambiguous pairwise Step-500 / FullSubNet correlation clips (IDs 162, 436); they remain included and flagged with no shifting, phase correction, or exclusion. Predictions were joined by canonical `val_index`, read from the saved float WAVs, and combined sample-for-sample. All 4,720 ensemble outputs remain float WAV; no clipping or peak normalization was applied.

Predeclared tests: D1 raw equal thirds; D2 weights (0.20/0.60/0.20), (0.25/0.50/0.25), (0.15/0.70/0.15); D3 all three equal-weight pairs; plus one D1 amplitude-policy diagnostic. D4 was not run. The amplitude-policy diagnostic applies only fixed global scalar factors from Phase B's output-only median RMS values, making each model's median clip RMS equal to `0.05011982079309145`, then averages in equal thirds: Step-500 `1.045618`, FullSubNet `0.968214`, GTCRN `1.000000`. No clip-specific normalization or clean-reference/metric-based scaling was used. It is an in-sample amplitude diagnostic, not a deployable calibration.

Scoring used the unchanged `scripts/evaluate_dfn3_canonical.py::metrics` implementation (SHA-256 `{sha256(ROOT / 'scripts/evaluate_dfn3_canonical.py')}`) and the same clean/noisy references as the frozen canonical evaluation. Paired confidence intervals used `scripts/compare_dfn3_canonical.py`, 2,000 paired bootstrap resamples, seed 26052. All three baselines' stored per-clip metrics were previously reproduced exactly in Stage 8A.

These are objective metrics only; no human listening panel or speech-distortion annotation was conducted. Eight fixed configurations and multiple paired comparisons were examined on a repeatedly used benchmark without a multiplicity correction, so the apparent best variant is selection-exposed and exploratory.

## Overall results

""" + "\n".join(summary_table) + f"""

The highest observed joint pass among the fixed actual variants is **{best_variant}** at {best_stats['pass']['joint']}/590 ({best_stats['pass']['joint_pct']:.1f}%). It passes more clips than FullSubNet alone ({fs_joint}/590), but this is a diagnostic result on a repeatedly used benchmark, not independent validation. No model or weight set is selected for deployment. Only D2 0.15/0.70/0.15 has mean SNR above 15 dB (`{summarize([mix_rows['d2_fs70_raw'][i] for i in range(590)])["mean"]["snr_db"]:.3f} dB`); this does not mean the joint target is universally met.

All mixtures are unclipped FLOAT WAVs. Some exceed the usual PCM peak of 1.0:

| Variant | Maximum absolute peak | Files with peak >1.0 |
|---|---:|---:|
""" + "\n".join(peak_rows) + f"""

## Paired comparisons against FullSubNet epoch 58

Differences are candidate minus FullSubNet; brackets are 95% paired bootstrap CIs.

| Variant | SNR dB (95% CI) | SI-SDR dB (95% CI) | STOI (95% CI) | PESQ-WB (95% CI) |
|---|---|---|---|---|
""" + "\n".join(paired_lines) + f"""

The two 60–70% FullSubNet-favored mixes have positive paired intervals for all four metrics versus FullSubNet, with only modest joint-pass gains (8–9 additional clips). Raw equal thirds improves STOI and PESQ-WB versus FullSubNet but loses mean SNR; its SI-SDR interval includes zero. Equal median-RMS matching changes raw equal-thirds SNR by only about +0.031 dB and does not change the 223 joint passes. Paired amplitude-matched minus raw equal-thirds CIs (all 590): {amp_line}. The intervals are tight but effect sizes are tiny; this amplitude policy is not a material ensemble gain.

## Combined target-SNR ≤0 dB region

This subgroup has 210 clips. Means and joint pass counts:

""" + "\n".join(low_table) + f"""

For the highest-joint fixed mix ({best_variant}), the ≤0 dB subset has {best_low_stats['pass']['joint']}/210 joint passes versus FullSubNet's {fs_low_stats['pass']['joint']}/210. Its means are SNR {best_low_stats['mean']['snr_db']:.3f} dB, SI-SDR {best_low_stats['mean']['si_sdr_db']:.3f} dB, STOI {best_low_stats['mean']['stoi']:.5f}, PESQ-WB {best_low_stats['mean']['pesq_wb']:.5f}. For D2 0.15/0.70/0.15 versus FullSubNet, paired ≤0 dB metric differences are: {low_d2_line}. The fixed benchmark shows positive mean metric differences, but joint-pass improvement is only one clip and low-bin means remain well below the joint criteria; this is not a validated operational gain.

## SNR-bin and clipwise behavior

All seven target-SNR bins for three baselines and eight variants are in `research/STAGE8_ENSEMBLE_SNR_BINS.csv`. Paired deltas and intervals for every variant versus every standalone baseline, for both all 590 clips and the combined ≤0 dB subset, are in `research/STAGE8_ENSEMBLE_PAIRED_COMPARISONS.csv` (2,000 resamples, seed 26052). The clipwise diagnostic table counts all-four-metric improvements, SNR improvements paired with STOI/PESQ degradation, and cases worse than all standalone models: `research/STAGE8_ENSEMBLE_CLIPWISE_DIAGNOSTICS.csv`. For D2 0.15/0.70/0.15, all four metrics improve over FullSubNet on {d2_clipwise['improves_all_four_vs_fullsubnet_count']} clips; SNR improves while STOI or PESQ-WB declines on {d2_clipwise['snr_up_but_stoi_or_pesq_down_vs_fullsubnet_count']} clips. No variant is strictly worse on all four metrics than all three standalone models on any clip. IDs 162 and 436 are explicitly flagged for every variant in `research/STAGE8_ENSEMBLE_ALIGNMENT_FLAGS.csv`; no correction was applied.

## Oracle diagnostics (not achievable model outputs)

The standalone joint-pass counts are Step-500 161, FullSubNet {fs_joint}, and GTCRN {int(joint['gtcrn'].sum())}. An oracle that chooses any standalone model that passes all three criteria reaches **{oracle_joint}/590 ({oracle_joint / 590 * 100:.1f}%)**. Per-clip best metric upper bounds:

""" + "\n".join(oracle_metric_table) + f"""

Which model supplied each per-clip metric maximum and the oracle joint result are in `research/STAGE8_ORACLE_DIAGNOSTICS.csv`. These values depend on clean-reference scores and are post hoc diagnostics, not implementable selection rules.

## Compute and deployment feasibility

Parameter counts from the verified model records are Step-500 2,135,484, FullSubNet 5,637,635, GTCRN 48,245; total **7,821,364 parameters**. Protected checkpoint storage is {sum(checkpoint_bytes.values()):,} bytes ({sum(checkpoint_bytes.values()) / (1024**2):.2f} MiB): Step-500 {checkpoint_bytes['step500']:,}, FullSubNet {checkpoint_bytes['fullsubnet']:,}, GTCRN {checkpoint_bytes['gtcrn']:,}. A weighted ensemble must run every model whose weight is nonzero for each clip/block, then sum the outputs. All are already at 16 kHz, so this experiment needed no sample-rate conversion.

Measured prior standalone CPU inference-only RTFs on the Mac are Step-500 {rtf_step:.4f}, FullSubNet {rtf_full:.4f}, GTCRN {rtf_gtcrn:.4f}; their arithmetic sum is about {rtf_step + rtf_full + rtf_gtcrn:.4f}. This is only a rough sequential estimate from separate runs/environments, not a combined runtime measurement. Prior peak process RSS observations were about 362 MiB, 847 MiB, and 131 MiB respectively; they cannot be summed into a reliable shared-process memory estimate. FullSubNet uses offline normalization and two-frame look-ahead, so direct streaming integration is not established. No Raspberry Pi, latency, live microphone, or real-time test was performed. **Real-time suitability is not claimed.**

## Eight decision questions

1. **Does raw equal averaging outperform each individual?** No. It clearly improves over Step-500 and GTCRN, but its SNR is below FullSubNet (paired Δ −0.187 dB, CI [−0.327, −0.050]); SI-SDR is inconclusive versus FullSubNet. STOI and PESQ-WB improve.
2. **Does FullSubNet-favored averaging perform better?** The 0.20/0.60/0.20 and 0.15/0.70/0.15 variants improve all four means over FullSubNet with paired intervals above zero. The gains are modest and exploratory; the 0.25/0.50/0.25 SNR CI includes zero.
3. **Does any pairwise variant outperform the three-model mix?** No pairwise mix beats the best predeclared three-model weighted mix on joint passes or all aggregate metrics. FullSubNet + GTCRN is near FullSubNet but has fewer joint passes; DFN3 + GTCRN is weaker.
4. **Are errors complementary enough to justify an ensemble?** There is evidence of complementary errors: fixed weighted mixes improve several metrics over FullSubNet and modestly increase joint passes. The benefit is small, and two Step-500/FullSubNet correlation exceptions remain flagged.
5. **How close is the best actual ensemble to the oracle?** Best actual is {best_stats['pass']['joint']}/590; oracle union is {oracle_joint}/590, a gap of {oracle_joint - best_stats['pass']['joint']} clips ({(oracle_joint - best_stats['pass']['joint']) / 590 * 100:.1f} percentage points).
6. **Is the gain meaningful at ≤0 dB?** Not clearly. Best actual has {best_low_stats['pass']['joint']}/210 vs FullSubNet {fs_low_stats['pass']['joint']}/210, and mean low-bin SNR remains {best_low_stats['mean']['snr_db']:.2f} dB. The paired subgroup intervals are provided before making any low-SNR claim.
7. **Is three-model compute justified?** Not yet. Fixed mixes show diagnostic gains, but require all nonzero-weight models, roughly 7.82M parameters / 73.4 MiB of checkpoints, and retain FullSubNet's offline limitations. No Pi/real-time evidence exists.
8. **Single best next experiment:** evaluate the predeclared `d2_fs70_raw` candidate on a new independent, non-gold validation set with a frozen amplitude policy and no weight retuning; include clips analogous to the flagged IDs and listen for speech distortion before considering hardware work.

## Commands, software, inputs and outputs

- Simulation command (from project root): `../pc_venv/bin/python scripts/run_stage8_ensemble_simulations.py --output-root runs/stage8_ensemble_20261113/phase_c_ensembles` (exit 0; 8 variants, 4,720 float WAVs, 24 paired comparison runs).
- Summary command: `../pc_venv/bin/python scripts/summarize_stage8_ensembles.py`.
- Paired comparison command pattern (run for each variant and each baseline): `../pc_venv/bin/python scripts/compare_dfn3_canonical.py --reference runs/<baseline>/per_clip.csv --candidate runs/stage8_ensemble_20261113/phase_c_ensembles/<variant>/per_clip.csv --output runs/stage8_ensemble_20261113/phase_c_ensembles/paired_comparisons/<variant>_vs_<baseline>.json --bootstrap 2000 --seed 26052` (all 24 exited 0; exact argument arrays are recorded in `run_record.json`).
- Software: Python `3.14.7`, PyTorch `2.14.1` (metric environment), NumPy `1.26.4`, SciPy `1.18.1`, SoundFile `0.14.0`, pystoi `0.4.1`, PESQ package. The prior GTCRN predictions were made in the recorded Python `3.10.22` / PyTorch `1.11.0` environment.
- Manifest SHA-256: `{MANIFEST_HASH}`. The 1,770 source predictions were individually hash-verified against their existing ledgers before and after simulation; the protected checkpoints and manifest were not written.
- Protected checkpoint SHA-256 values: Step-500 `bc1fc9b769589da1754c4ee529c8578edf3262f7d2d4515fe69455c8a467bb27`; FullSubNet `482615e9709d2d6c10ee0d24f9844ad2da2dae3c0cf897f014839c365917a2e0`; GTCRN `a630d992cf792daf4ce2bb5bcf9c4d389f740a8f09c6e0971184697fe6371b79`.
- Per-variant float WAVs, `per_clip.csv`, `prediction_files.csv` and `summary.json` are under `runs/stage8_ensemble_20261113/phase_c_ensembles/<variant>/`. Each output WAV SHA-256 is in its `prediction_files.csv`.
- Full artifact inventory with per-file output hashes: `runs/stage8_ensemble_20261113/phase_c_ensembles/PHASE_C_ARTIFACT_HASHES.csv` (SHA-256 `{artifact_hash_sha}`). The inventory includes all 4,720 ensemble WAVs, source prediction hash ledgers, protected input hashes, source code, summaries, comparisons, and required CSV tables.
- Phase C run record (commands, source hashes, weights/scales, environment and exit codes): `runs/stage8_ensemble_20261113/phase_c_ensembles/run_record.json`.
- Existing NumPy/SciPy compatibility warning appeared during metric import; all scoring and paired comparisons completed. No simulation/scoring failures occurred.
- This canonical set was already used for model comparison and exploratory research. These variants are not independent validation; no weights are selected for deployment and no gold set was accessed.

## Required tables

- `research/STAGE8_ENSEMBLE_SUMMARY.csv`
- `research/STAGE8_ENSEMBLE_PAIRED_COMPARISONS.csv`
- `research/STAGE8_ENSEMBLE_SNR_BINS.csv`
- `research/STAGE8_ORACLE_DIAGNOSTICS.csv`
- Additional clipwise diagnostic: `research/STAGE8_ENSEMBLE_CLIPWISE_DIAGNOSTICS.csv`
- Alignment exception flags: `research/STAGE8_ENSEMBLE_ALIGNMENT_FLAGS.csv`

**Decision:** retain deployed Step-500. Phase C is diagnostic only. Stop here for review; no further training, tuning, inference, model changes, or deployment was performed.
"""
    report_path = RESEARCH / "STAGE8_ENSEMBLE_FEASIBILITY.md"
    report_path.write_text(report, encoding="utf-8")
    print(json.dumps({
        "summary_csv": str(summary_path),
        "paired_csv": str(comparison_path),
        "snr_bins_csv": str(snr_path),
        "oracle_csv": str(oracle_path),
        "clipwise_csv": str(diagnostics_path),
        "report": str(report_path),
        "best_joint_variant": best_variant,
        "best_joint_count": best_stats["pass"]["joint"],
        "oracle_joint_count": oracle_joint,
    }, indent=2))


if __name__ == "__main__":
    main()
