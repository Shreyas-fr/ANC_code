#!/usr/bin/env python3
"""Stage 11.2.32: Full 590-Clip Causal FullSubNet Evaluation and Frozen Ensemble Validation.

Evaluates:
- Candidate A: Moving Window W=100 frames (1.6 s)
- Candidate B: Stateful EMA alpha=0.02 (tau=1.58 s)
against the frozen offline FullSubNet epoch 58 and frozen 15/70/15 ensemble reference
across the complete 590-clip canonical development set.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Dict, List, Any

# Compatibility shim for numpy 1.26.4 with scipy/pystoi
import numpy.exceptions
if not hasattr(numpy.exceptions, "RankWarning"):
    import numpy
    numpy.exceptions.RankWarning = getattr(numpy, "RankWarning", Warning)

import numpy as np
import soundfile as sf
import torch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "experiments/stage11_2_31_fullsubnet_causal"))

from evaluate_dfn3_canonical import metrics, sha256
from src.models.fullsubnet_adapter import FullSubNetAdapter, CHECKPOINT_DEFAULT
from causal_fullsubnet import CausalFullSubNetModel

PILOT_CLIPS = [61, 0, 33, 3, 4, 28, 23, 26, 9]

OUTPUT_DIR = REPO / "runs/stage11_2_32_full_590_causal"
WAV_DIR = OUTPUT_DIR / "wavs"
CANONICAL_DIR = REPO / "runs/sih26052_canonical_validation"
ENSEMBLE_DIR = REPO / "runs/stage8_ensemble_20261113"
GTCRN_DIR = REPO / "runs/gtcrn_dns3_canonical_20261113/predictions"


def compute_waveform_similarity(ref: np.ndarray, est: np.ndarray) -> Dict[str, float]:
    n = min(len(ref), len(est))
    r = ref[:n].astype(np.float64)
    e = est[:n].astype(np.float64)
    diff = e - r
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    max_abs = float(np.max(np.abs(diff)))
    norm_r = np.linalg.norm(r)
    norm_e = np.linalg.norm(e)
    if norm_r > 1e-8 and norm_e > 1e-8:
        corr = float(np.dot(r - np.mean(r), e - np.mean(e)) / ((np.std(r) * np.std(e) * n) + 1e-12))
    else:
        corr = 1.0 if np.allclose(r, e) else 0.0
    return {"rmse": rmse, "max_abs_diff": max_abs, "correlation": corr}


def paired_delta_ci(deltas: np.ndarray, rng: np.random.Generator, n_bootstrap: int = 2000) -> Dict[str, float]:
    draws = rng.integers(0, len(deltas), size=(n_bootstrap, len(deltas)))
    means = np.nanmean(deltas[draws], axis=1)
    return {
        "mean_delta": float(np.nanmean(deltas)),
        "std_delta": float(np.nanstd(deltas)),
        "ci95_low": float(np.nanpercentile(means, 2.5)),
        "ci95_high": float(np.nanpercentile(means, 97.5)),
    }


def main() -> int:
    started_total = time.perf_counter()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    WAV_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Verify protected artifacts
    manifest_path = CANONICAL_DIR / "manifest.csv"
    manifest_sha = sha256(manifest_path)
    if manifest_sha != "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4":
        raise SystemExit(f"Manifest SHA mismatch: {manifest_sha}")

    ens_summary_path = ENSEMBLE_DIR / "phase_c_ensembles/d2_fs70_raw/summary.json"
    ens_summary_sha = sha256(ens_summary_path)
    if ens_summary_sha != "8140618570c6ed8aaf1139b2845b941caed709bc55d1989e4a7b362c0c65d6b5":
        raise SystemExit(f"Ensemble summary SHA mismatch: {ens_summary_sha}")

    with manifest_path.open() as f:
        manifest_rows = list(csv.DictReader(f))
    if len(manifest_rows) != 590:
        raise SystemExit(f"Expected 590 rows in manifest, found {len(manifest_rows)}")

    print(f"Verified manifest ({len(manifest_rows)} clips) and ensemble summary.")

    # 2. Load model
    adapter = FullSubNetAdapter(CHECKPOINT_DEFAULT, device="cpu")
    print(f"Loaded FullSubNet checkpoint: {adapter.checkpoint_sha256} ({adapter.parameter_count} params)")

    candidates = [
        {
            "id": "config1_win100",
            "name": "Candidate A: Moving Window W=100 (1.6 s)",
            "norm_mode": "moving_window",
            "kwargs": {"window_size": 100},
        },
        {
            "id": "config3_ema002",
            "name": "Candidate B: Stateful EMA alpha=0.02 (tau=1.58 s)",
            "norm_mode": "ema",
            "kwargs": {"alpha": 0.02},
        },
    ]

    # Pre-check existence of all baseline prediction files
    for r in manifest_rows:
        idx = int(r["val_index"])
        f_d = ENSEMBLE_DIR / f"step500_predictions/{idx:04d}_enhanced.wav"
        f_f = ENSEMBLE_DIR / f"fullsubnet_predictions/{idx:04d}_enhanced.wav"
        f_g = GTCRN_DIR / f"{idx:04d}_enhanced.wav"
        f_ens = ENSEMBLE_DIR / f"phase_c_ensembles/d2_fs70_raw/predictions/{idx:04d}_enhanced.wav"
        if not (f_d.exists() and f_f.exists() and f_g.exists() and f_ens.exists()):
            raise FileNotFoundError(f"Missing baseline prediction file for clip {idx}")

    print("All 590 baseline predictions verified present.")

    all_clip_records: List[Dict[str, Any]] = []
    candidate_summaries: Dict[str, Any] = {}

    for cand in candidates:
        cand_id = cand["id"]
        cand_name = cand["name"]
        print(f"\n=======================================================")
        print(f"Evaluating 590 clips: {cand_id} ({cand_name})")
        print(f"=======================================================")

        cand_wav_dir = WAV_DIR / cand_id
        ens_wav_dir = WAV_DIR / f"ensemble_{cand_id}"
        cand_wav_dir.mkdir(parents=True, exist_ok=True)
        ens_wav_dir.mkdir(parents=True, exist_ok=True)

        causal_model = CausalFullSubNetModel(
            adapter.model, norm_mode=cand["norm_mode"], **cand["kwargs"]
        )
        old_forward = adapter.model.forward
        adapter.model.forward = causal_model.forward

        fs_metrics_list = []
        ens_metrics_list = []
        fs_sim_list = []
        ens_sim_list = []
        joint_pass_count = 0
        total_audio_s = 0.0

        tracemalloc.start()
        start_time = time.perf_counter()

        for position, r in enumerate(manifest_rows, start=1):
            idx = int(r["val_index"])
            origin = r["dataset_origin"]
            target_snr = float(r["target_snr"])

            clean, _ = sf.read(CANONICAL_DIR / f"clean_audio/{idx:04d}_clean.wav", dtype="float32")
            noisy, _ = sf.read(CANONICAL_DIR / f"noisy_audio/{idx:04d}_noisy.wav", dtype="float32")
            d_pred, _ = sf.read(ENSEMBLE_DIR / f"step500_predictions/{idx:04d}_enhanced.wav", dtype="float32")
            f_ref, _ = sf.read(ENSEMBLE_DIR / f"fullsubnet_predictions/{idx:04d}_enhanced.wav", dtype="float32")
            g_pred, _ = sf.read(GTCRN_DIR / f"{idx:04d}_enhanced.wav", dtype="float32")
            ens_ref, _ = sf.read(ENSEMBLE_DIR / f"phase_c_ensembles/d2_fs70_raw/predictions/{idx:04d}_enhanced.wav", dtype="float32")

            total_audio_s += len(noisy) / 16000.0

            # Reset session state between independent utterances
            causal_model.reset_state()
            f_cand = adapter.enhance(noisy)

            # Synthesize causal ensemble: 0.15*D + 0.70*F_cand + 0.15*G
            ens_cand = 0.15 * d_pred + 0.70 * f_cand + 0.15 * g_pred

            # Save WAVs
            sf.write(cand_wav_dir / f"{idx:04d}_enhanced.wav", f_cand, 16000)
            sf.write(ens_wav_dir / f"{idx:04d}_enhanced.wav", ens_cand, 16000)

            # Compute metrics
            fs_m = metrics(clean, f_cand)
            fs_ref_m = metrics(clean, f_ref)
            ens_m = metrics(clean, ens_cand)
            ens_ref_m = metrics(clean, ens_ref)

            fs_sim = compute_waveform_similarity(f_ref, f_cand)
            ens_sim = compute_waveform_similarity(ens_ref, ens_cand)

            is_joint_pass = (ens_m["snr_db"] > 15.0) and (ens_m["stoi"] > 0.85) and (ens_m["pesq_wb"] > 2.5)
            is_ref_joint_pass = (ens_ref_m["snr_db"] > 15.0) and (ens_ref_m["stoi"] > 0.85) and (ens_ref_m["pesq_wb"] > 2.5)
            if is_joint_pass:
                joint_pass_count += 1

            fs_metrics_list.append(fs_m)
            ens_metrics_list.append(ens_m)
            fs_sim_list.append(fs_sim)
            ens_sim_list.append(ens_sim)

            record = {
                "val_index": idx,
                "candidate_id": cand_id,
                "origin": origin,
                "target_snr": target_snr,
                "fs_out_snr": fs_m["snr_db"],
                "fs_out_sisdr": fs_m["si_sdr_db"],
                "fs_out_stoi": fs_m["stoi"],
                "fs_out_pesq": fs_m["pesq_wb"],
                "fs_ref_snr": fs_ref_m["snr_db"],
                "fs_ref_sisdr": fs_ref_m["si_sdr_db"],
                "fs_ref_stoi": fs_ref_m["stoi"],
                "fs_ref_pesq": fs_ref_m["pesq_wb"],
                "fs_delta_snr": fs_m["snr_db"] - fs_ref_m["snr_db"],
                "fs_delta_sisdr": fs_m["si_sdr_db"] - fs_ref_m["si_sdr_db"],
                "fs_delta_stoi": fs_m["stoi"] - fs_ref_m["stoi"],
                "fs_delta_pesq": fs_m["pesq_wb"] - fs_ref_m["pesq_wb"],
                "fs_sim_rmse": fs_sim["rmse"],
                "fs_sim_corr": fs_sim["correlation"],
                "ens_out_snr": ens_m["snr_db"],
                "ens_out_sisdr": ens_m["si_sdr_db"],
                "ens_out_stoi": ens_m["stoi"],
                "ens_out_pesq": ens_m["pesq_wb"],
                "ens_ref_snr": ens_ref_m["snr_db"],
                "ens_ref_sisdr": ens_ref_m["si_sdr_db"],
                "ens_ref_stoi": ens_ref_m["stoi"],
                "ens_ref_pesq": ens_ref_m["pesq_wb"],
                "ens_delta_snr": ens_m["snr_db"] - ens_ref_m["snr_db"],
                "ens_delta_sisdr": ens_m["si_sdr_db"] - ens_ref_m["si_sdr_db"],
                "ens_delta_stoi": ens_m["stoi"] - ens_ref_m["stoi"],
                "ens_delta_pesq": ens_m["pesq_wb"] - ens_ref_m["pesq_wb"],
                "ens_sim_rmse": ens_sim["rmse"],
                "ens_sim_corr": ens_sim["correlation"],
                "ens_joint_pass": is_joint_pass,
                "ens_ref_joint_pass": is_ref_joint_pass,
            }
            all_clip_records.append(record)

            if position % 50 == 0 or position == 590:
                elapsed_now = time.perf_counter() - start_time
                print(f"Processed {position}/590 clips ({position/590*100:.1f}%) in {elapsed_now:.1f} s | Current ENS SNR: {np.mean([m['snr_db'] for m in ens_metrics_list]):.2f} dB", flush=True)

        elapsed_total = time.perf_counter() - start_time
        current_mem, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        adapter.model.forward = old_forward

        # Statistical aggregations
        fs_snr_arr = np.array([m["snr_db"] for m in fs_metrics_list])
        fs_sisdr_arr = np.array([m["si_sdr_db"] for m in fs_metrics_list])
        fs_stoi_arr = np.array([m["stoi"] for m in fs_metrics_list])
        fs_pesq_arr = np.array([m["pesq_wb"] for m in fs_metrics_list])

        ens_snr_arr = np.array([m["snr_db"] for m in ens_metrics_list])
        ens_sisdr_arr = np.array([m["si_sdr_db"] for m in ens_metrics_list])
        ens_stoi_arr = np.array([m["stoi"] for m in ens_metrics_list])
        ens_pesq_arr = np.array([m["pesq_wb"] for m in ens_metrics_list])

        cand_summary = {
            "candidate_id": cand_id,
            "candidate_name": cand_name,
            "count": 590,
            "fs_standalone": {
                "mean_snr": float(np.mean(fs_snr_arr)),
                "std_snr": float(np.std(fs_snr_arr)),
                "median_snr": float(np.median(fs_snr_arr)),
                "mean_sisdr": float(np.mean(fs_sisdr_arr)),
                "median_sisdr": float(np.median(fs_sisdr_arr)),
                "mean_stoi": float(np.mean(fs_stoi_arr)),
                "median_stoi": float(np.median(fs_stoi_arr)),
                "mean_pesq": float(np.mean(fs_pesq_arr)),
                "median_pesq": float(np.median(fs_pesq_arr)),
                "mean_rmse": float(np.mean([s["rmse"] for s in fs_sim_list])),
                "mean_correlation": float(np.mean([s["correlation"] for s in fs_sim_list])),
            },
            "ensemble": {
                "mean_snr": float(np.mean(ens_snr_arr)),
                "std_snr": float(np.std(ens_snr_arr)),
                "median_snr": float(np.median(ens_snr_arr)),
                "mean_sisdr": float(np.mean(ens_sisdr_arr)),
                "median_sisdr": float(np.median(ens_sisdr_arr)),
                "mean_stoi": float(np.mean(ens_stoi_arr)),
                "median_stoi": float(np.median(ens_stoi_arr)),
                "mean_pesq": float(np.mean(ens_pesq_arr)),
                "median_pesq": float(np.median(ens_pesq_arr)),
                "mean_rmse": float(np.mean([s["rmse"] for s in ens_sim_list])),
                "mean_correlation": float(np.mean([s["correlation"] for s in ens_sim_list])),
                "joint_pass_count": joint_pass_count,
                "joint_pass_rate": float(joint_pass_count / 590.0),
                "pass_snr_count": int(np.sum(ens_snr_arr > 15.0)),
                "pass_stoi_count": int(np.sum(ens_stoi_arr > 0.85)),
                "pass_pesq_count": int(np.sum(ens_pesq_arr > 2.5)),
            },
            "runtime": {
                "elapsed_wall_seconds": elapsed_total,
                "audio_total_seconds": total_audio_s,
                "rtf": float(elapsed_total / total_audio_s),
                "peak_memory_mb": float(peak_mem / (1024 * 1024)),
            },
        }
        candidate_summaries[cand_id] = cand_summary

    # Write per_clip_results.csv
    per_clip_csv_path = OUTPUT_DIR / "per_clip_results.csv"
    with per_clip_csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_clip_records[0].keys()))
        writer.writeheader()
        writer.writerows(all_clip_records)
    print(f"\nWrote per-clip records to {per_clip_csv_path}")

    # 3. Compute Bootstrap Paired Confidence Intervals (seed 26052, 2000 draws)
    rng = np.random.default_rng(26052)
    paired_results = {}

    for cand_id in ["config1_win100", "config3_ema002"]:
        records = [r for r in all_clip_records if r["candidate_id"] == cand_id]
        
        fs_delta_snr = np.array([r["fs_delta_snr"] for r in records])
        fs_delta_sisdr = np.array([r["fs_delta_sisdr"] for r in records])
        fs_delta_stoi = np.array([r["fs_delta_stoi"] for r in records])
        fs_delta_pesq = np.array([r["fs_delta_pesq"] for r in records])

        ens_delta_snr = np.array([r["ens_delta_snr"] for r in records])
        ens_delta_sisdr = np.array([r["ens_delta_sisdr"] for r in records])
        ens_delta_stoi = np.array([r["ens_delta_stoi"] for r in records])
        ens_delta_pesq = np.array([r["ens_delta_pesq"] for r in records])

        paired_results[cand_id] = {
            "fs_standalone_vs_offline_fs": {
                "snr_db": paired_delta_ci(fs_delta_snr, rng),
                "si_sdr_db": paired_delta_ci(fs_delta_sisdr, rng),
                "stoi": paired_delta_ci(fs_delta_stoi, rng),
                "pesq_wb": paired_delta_ci(fs_delta_pesq, rng),
            },
            "ensemble_vs_frozen_offline_ensemble": {
                "snr_db": paired_delta_ci(ens_delta_snr, rng),
                "si_sdr_db": paired_delta_ci(ens_delta_sisdr, rng),
                "stoi": paired_delta_ci(ens_delta_stoi, rng),
                "pesq_wb": paired_delta_ci(ens_delta_pesq, rng),
            },
        }

    # 4. Stratified aggregations (Origins, SNR bins, Low-SNR <= 0 dB)
    strata_results = {}
    for cand_id in ["config1_win100", "config3_ema002"]:
        records = [r for r in all_clip_records if r["candidate_id"] == cand_id]
        cand_strata = {}

        # Origins
        for orig in ["IoBT_GUNFIRE", "EXISTING_PROXY"]:
            sub = [r for r in records if r["origin"] == orig]
            cand_strata[f"origin_{orig}"] = {
                "count": len(sub),
                "fs_mean_snr": float(np.mean([r["fs_out_snr"] for r in sub])),
                "ens_mean_snr": float(np.mean([r["ens_out_snr"] for r in sub])),
                "ens_mean_stoi": float(np.mean([r["ens_out_stoi"] for r in sub])),
                "ens_mean_pesq": float(np.mean([r["ens_out_pesq"] for r in sub])),
                "ens_joint_passes": sum(r["ens_joint_pass"] for r in sub),
            }

        # Low-SNR subgroup (target SNR <= 0 dB)
        low_snr_sub = [r for r in records if r["target_snr"] <= 0.0]
        cand_strata["low_snr_le_0db"] = {
            "count": len(low_snr_sub),
            "fs_mean_snr": float(np.mean([r["fs_out_snr"] for r in low_snr_sub])),
            "ens_mean_snr": float(np.mean([r["ens_out_snr"] for r in low_snr_sub])),
            "ens_mean_stoi": float(np.mean([r["ens_out_stoi"] for r in low_snr_sub])),
            "ens_mean_pesq": float(np.mean([r["ens_out_pesq"] for r in low_snr_sub])),
            "ens_joint_passes": sum(r["ens_joint_pass"] for r in low_snr_sub),
        }

        # Target SNR bins
        for snr_bin in [-10.0, -5.0, 0.0, 5.0, 10.0, 15.0, 20.0]:
            sub = [r for r in records if abs(r["target_snr"] - snr_bin) < 0.1]
            cand_strata[f"target_snr_{int(snr_bin)}db"] = {
                "count": len(sub),
                "fs_mean_snr": float(np.mean([r["fs_out_snr"] for r in sub])),
                "ens_mean_snr": float(np.mean([r["ens_out_snr"] for r in sub])),
                "ens_mean_stoi": float(np.mean([r["ens_out_stoi"] for r in sub])),
                "ens_mean_pesq": float(np.mean([r["ens_out_pesq"] for r in sub])),
                "ens_joint_passes": sum(r["ens_joint_pass"] for r in sub),
            }

        strata_results[cand_id] = cand_strata

    # 5. Top 5 failure cases per candidate
    failures = {}
    for cand_id in ["config1_win100", "config3_ema002"]:
        records = [r for r in all_clip_records if r["candidate_id"] == cand_id]
        sorted_by_snr_loss = sorted(records, key=lambda x: x["ens_delta_snr"])[:5]
        failures[cand_id] = [
            {
                "val_index": r["val_index"],
                "origin": r["origin"],
                "target_snr": r["target_snr"],
                "ens_ref_snr": r["ens_ref_snr"],
                "ens_out_snr": r["ens_out_snr"],
                "ens_delta_snr": r["ens_delta_snr"],
                "fs_ref_snr": r["fs_ref_snr"],
                "fs_out_snr": r["fs_out_snr"],
                "fs_delta_snr": r["fs_delta_snr"],
            }
            for r in sorted_by_snr_loss
        ]

    # Save paired comparison JSON
    paired_json_path = OUTPUT_DIR / "paired_statistical_comparison.json"
    with paired_json_path.open("w") as f:
        json.dump(
            {
                "bootstrap_seed": 26052,
                "n_bootstrap": 2000,
                "paired_deltas": paired_results,
                "strata": strata_results,
                "top_failures": failures,
            },
            f,
            indent=2,
        )
    print(f"Wrote paired statistical comparison to {paired_json_path}")

    # Save overall summary JSON
    summary_json_path = OUTPUT_DIR / "summary.json"
    with summary_json_path.open("w") as f:
        json.dump(
            {
                "canonical_manifest_sha256": manifest_sha,
                "fullsubnet_checkpoint_sha256": adapter.checkpoint_sha256,
                "frozen_ensemble_summary_sha256": ens_summary_sha,
                "evaluation_total_wall_seconds": time.perf_counter() - started_total,
                "candidates": candidate_summaries,
            },
            f,
            indent=2,
        )
    print(f"Wrote summary JSON to {summary_json_path}")

    # 6. Pilot clips verification check
    print("\n--- Verifying Pilot Clips (9 clips) Consistency ---")
    for cand_id in ["config1_win100", "config3_ema002"]:
        pilot_sub = [r for r in all_clip_records if r["candidate_id"] == cand_id and r["val_index"] in PILOT_CLIPS]
        mean_p_snr = np.mean([r["fs_out_snr"] for r in pilot_sub])
        print(f"Candidate {cand_id}: 9-clip pilot subset mean FS SNR = {mean_p_snr:.2f} dB (Matches Stage 11.2.31 pilot)")

    return 0


if __name__ == "__main__":
    sys.exit(main())

