#!/usr/bin/env python3
"""Stage 11.2.31: FullSubNet Causal Streaming Pilot Evaluation Script.

Evaluates 5 causal normalization configurations and stateful chunk inference
across the 9 preselected canonical development clips.
Scores each candidate against:
1. Frozen offline FullSubNet epoch 58 outputs.
2. Frozen offline 15/70/15 ensemble reference (d2_fs70_raw).
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluate_dfn3_canonical import metrics, sha256
from src.models.fullsubnet_adapter import FullSubNetAdapter, CHECKPOINT_DEFAULT
from causal_fullsubnet import CausalFullSubNetModel, StatefulChunkAdapter

PILOT_CLIPS = [61, 0, 33, 3, 4, 28, 23, 26, 9]

OUTPUT_DIR = REPO / "runs/stage11_2_31_fullsubnet_causal"
WAV_DIR = OUTPUT_DIR / "wavs"
CANONICAL_DIR = REPO / "runs/sih26052_canonical_validation"
ENSEMBLE_DIR = REPO / "runs/stage8_ensemble_20261113"


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


def main() -> int:
    started_total = time.perf_counter()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    WAV_DIR.mkdir(parents=True, exist_ok=True)

    # Verify manifest
    manifest_path = CANONICAL_DIR / "manifest.csv"
    manifest_sha = sha256(manifest_path)
    if manifest_sha != "d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4":
        raise SystemExit(f"Manifest SHA mismatch: {manifest_sha}")

    with manifest_path.open() as f:
        manifest_rows = {int(r["val_index"]): r for r in csv.DictReader(f)}

    print(f"Loaded canonical manifest. Target clips: {PILOT_CLIPS}")

    # Load base adapter
    adapter = FullSubNetAdapter(CHECKPOINT_DEFAULT, device="cpu")
    print(f"Loaded FullSubNet checkpoint. Param count: {adapter.parameter_count}")

    # Define candidate configurations
    configs = [
        {
            "id": "offline_baseline",
            "name": "Frozen Offline Baseline (epoch 58)",
            "type": "whole_call",
            "norm_mode": "offline",
            "kwargs": {},
            "status": "RUN",
        },
        {
            "id": "config1_win25",
            "name": "Config 1A: Moving Window W=25 frames (400 ms)",
            "type": "whole_call",
            "norm_mode": "moving_window",
            "kwargs": {"window_size": 25},
            "status": "RUN",
        },
        {
            "id": "config1_win50",
            "name": "Config 1B: Moving Window W=50 frames (800 ms)",
            "type": "whole_call",
            "norm_mode": "moving_window",
            "kwargs": {"window_size": 50},
            "status": "RUN",
        },
        {
            "id": "config1_win100",
            "name": "Config 1C: Moving Window W=100 frames (1600 ms)",
            "type": "whole_call",
            "norm_mode": "moving_window",
            "kwargs": {"window_size": 100},
            "status": "RUN",
        },
        {
            "id": "config2_cumulative",
            "name": "Config 2: Causal Cumulative Normalization (0..t)",
            "type": "whole_call",
            "norm_mode": "cumulative",
            "kwargs": {},
            "status": "RUN",
        },
        {
            "id": "config3_ema005",
            "name": "Config 3A: Stateful EMA alpha=0.05 (tau=624 ms)",
            "type": "whole_call",
            "norm_mode": "ema",
            "kwargs": {"alpha": 0.05},
            "status": "RUN",
        },
        {
            "id": "config3_ema002",
            "name": "Config 3B: Stateful EMA alpha=0.02 (tau=1.58 s)",
            "type": "whole_call",
            "norm_mode": "ema",
            "kwargs": {"alpha": 0.02},
            "status": "RUN",
        },
        {
            "id": "config3_ema001",
            "name": "Config 3C: Stateful EMA alpha=0.01 (tau=3.18 s)",
            "type": "whole_call",
            "norm_mode": "ema",
            "kwargs": {"alpha": 0.01},
            "status": "RUN",
        },
        {
            "id": "config4_fixed",
            "name": "Config 4: Fixed Pre-Calibrated Statistics",
            "type": "blocked",
            "norm_mode": "fixed",
            "kwargs": {},
            "status": "BLOCKED",
            "reason": "Eligible external provenance-cleared training dataset not available on local filesystem",
        },
        {
            "id": "config5_chunk32ms_stateful",
            "name": "Config 5A: Stateful Chunk Inference 32 ms (EMA alpha=0.02, persistent h,c)",
            "type": "chunked",
            "norm_mode": "ema",
            "kwargs": {"chunk_size_samples": 512, "alpha": 0.02, "reset_recurrent_each_chunk": False},
            "status": "RUN",
        },
        {
            "id": "config5_chunk16ms_stateful",
            "name": "Config 5B: Stateful Chunk Inference 16 ms (EMA alpha=0.02, persistent h,c)",
            "type": "chunked",
            "norm_mode": "ema",
            "kwargs": {"chunk_size_samples": 256, "alpha": 0.02, "reset_recurrent_each_chunk": False},
            "status": "RUN",
        },
        {
            "id": "config5_chunk32ms_stateless_ablation",
            "name": "Config 5C: Chunk Inference 32 ms Ablation (recurrent state reset each chunk)",
            "type": "chunked",
            "norm_mode": "ema",
            "kwargs": {"chunk_size_samples": 512, "alpha": 0.02, "reset_recurrent_each_chunk": True},
            "status": "RUN",
        },
    ]

    # Preload clean and noisy audio, plus frozen component predictions
    clip_data = {}
    for idx in PILOT_CLIPS:
        clean, _ = sf.read(CANONICAL_DIR / f"clean_audio/{idx:04d}_clean.wav", dtype="float32")
        noisy, _ = sf.read(CANONICAL_DIR / f"noisy_audio/{idx:04d}_noisy.wav", dtype="float32")
        d_pred, _ = sf.read(ENSEMBLE_DIR / f"step500_predictions/{idx:04d}_enhanced.wav", dtype="float32")
        f_pred, _ = sf.read(ENSEMBLE_DIR / f"fullsubnet_predictions/{idx:04d}_enhanced.wav", dtype="float32")
        g_pred, _ = sf.read(REPO / f"runs/gtcrn_dns3_canonical_20261113/predictions/{idx:04d}_enhanced.wav", dtype="float32")
        ens_ref, _ = sf.read(ENSEMBLE_DIR / f"phase_c_ensembles/d2_fs70_raw/predictions/{idx:04d}_enhanced.wav", dtype="float32")

        meta = manifest_rows[idx]
        clip_data[idx] = {
            "clean": clean,
            "noisy": noisy,
            "d_pred": d_pred,
            "f_pred": f_pred,
            "g_pred": g_pred,
            "ens_ref": ens_ref,
            "origin": meta["dataset_origin"],
            "target_snr": float(meta["target_snr"]),
        }

    per_clip_records: List[Dict[str, Any]] = []
    config_summaries: List[Dict[str, Any]] = []

    for cfg in configs:
        cfg_id = cfg["id"]
        cfg_name = cfg["name"]
        print(f"\n--- Running Configuration: {cfg_id} ({cfg_name}) ---")

        if cfg["status"] == "BLOCKED":
            print(f"Skipping BLOCKED configuration {cfg_id}: {cfg.get('reason')}")
            config_summaries.append({
                "config_id": cfg_id,
                "config_name": cfg_name,
                "status": "BLOCKED",
                "block_reason": cfg.get("reason"),
            })
            continue

        cfg_wav_dir = WAV_DIR / cfg_id
        cfg_wav_dir.mkdir(parents=True, exist_ok=True)

        # Setup model for this configuration
        if cfg["type"] == "whole_call":
            causal_wrapper = CausalFullSubNetModel(
                adapter.model, norm_mode=cfg["norm_mode"], **cfg["kwargs"]
            )
            old_forward = adapter.model.forward
            adapter.model.forward = causal_wrapper.forward

            def enhance_fn(noisy_wav):
                causal_wrapper.reset_state()
                return adapter.enhance(noisy_wav)

        elif cfg["type"] == "chunked":
            chunk_runner = StatefulChunkAdapter(
                adapter.model, norm_mode=cfg["norm_mode"], **cfg["kwargs"]
            )
            def enhance_fn(noisy_wav):
                return chunk_runner.enhance_stream(noisy_wav)

        cfg_snrs = []
        cfg_sisdrs = []
        cfg_stois = []
        cfg_pesqs = []
        cfg_rmses = []
        cfg_corrs = []
        ens_snrs = []
        ens_sisdrs = []
        ens_stois = []
        ens_pesqs = []
        ens_rmses = []
        ens_corrs = []
        joint_passes = 0
        total_audio_s = 0.0

        tracemalloc.start()
        start_time = time.perf_counter()

        for idx in PILOT_CLIPS:
            data = clip_data[idx]
            clean = data["clean"]
            noisy = data["noisy"]
            total_audio_s += len(noisy) / 16000.0

            # Enhance
            f_cand = enhance_fn(noisy)
            # Save enhanced WAV
            sf.write(cfg_wav_dir / f"{idx:04d}_enhanced.wav", f_cand, 16000)

            # Standalone FullSubNet metrics
            fs_m = metrics(clean, f_cand)
            fs_sim = compute_waveform_similarity(data["f_pred"], f_cand)

            # 15/70/15 Ensemble candidate synthesis:
            # 0.15 * D + 0.70 * F_cand + 0.15 * G
            ens_cand = 0.15 * data["d_pred"] + 0.70 * f_cand + 0.15 * data["g_pred"]
            ens_m = metrics(clean, ens_cand)
            ens_sim = compute_waveform_similarity(data["ens_ref"], ens_cand)

            is_joint_pass = (ens_m["snr_db"] > 15.0) and (ens_m["stoi"] > 0.85) and (ens_m["pesq_wb"] > 2.5)
            if is_joint_pass:
                joint_passes += 1

            cfg_snrs.append(fs_m["snr_db"])
            cfg_sisdrs.append(fs_m["si_sdr_db"])
            cfg_stois.append(fs_m["stoi"])
            cfg_pesqs.append(fs_m["pesq_wb"])
            cfg_rmses.append(fs_sim["rmse"])
            cfg_corrs.append(fs_sim["correlation"])

            ens_snrs.append(ens_m["snr_db"])
            ens_sisdrs.append(ens_m["si_sdr_db"])
            ens_stois.append(ens_m["stoi"])
            ens_pesqs.append(ens_m["pesq_wb"])
            ens_rmses.append(ens_sim["rmse"])
            ens_corrs.append(ens_sim["correlation"])

            record = {
                "config_id": cfg_id,
                "config_name": cfg_name,
                "val_index": idx,
                "origin": data["origin"],
                "target_snr": data["target_snr"],
                "fs_out_snr": fs_m["snr_db"],
                "fs_out_sisdr": fs_m["si_sdr_db"],
                "fs_out_stoi": fs_m["stoi"],
                "fs_out_pesq": fs_m["pesq_wb"],
                "fs_sim_rmse": fs_sim["rmse"],
                "fs_sim_corr": fs_sim["correlation"],
                "ens_out_snr": ens_m["snr_db"],
                "ens_out_sisdr": ens_m["si_sdr_db"],
                "ens_out_stoi": ens_m["stoi"],
                "ens_out_pesq": ens_m["pesq_wb"],
                "ens_sim_rmse": ens_sim["rmse"],
                "ens_sim_corr": ens_sim["correlation"],
                "ens_joint_pass": is_joint_pass,
            }
            per_clip_records.append(record)

        elapsed_wall = time.perf_counter() - start_time
        current_mem, peak_mem = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        if cfg["type"] == "whole_call":
            adapter.model.forward = old_forward

        summary = {
            "config_id": cfg_id,
            "config_name": cfg_name,
            "status": "COMPLETED",
            "clip_count": len(PILOT_CLIPS),
            "fs_mean_snr": float(np.mean(cfg_snrs)),
            "fs_mean_sisdr": float(np.mean(cfg_sisdrs)),
            "fs_mean_stoi": float(np.mean(cfg_stois)),
            "fs_mean_pesq": float(np.mean(cfg_pesqs)),
            "fs_mean_rmse": float(np.mean(cfg_rmses)),
            "fs_mean_corr": float(np.mean(cfg_corrs)),
            "ens_mean_snr": float(np.mean(ens_snrs)),
            "ens_mean_sisdr": float(np.mean(ens_sisdrs)),
            "ens_mean_stoi": float(np.mean(ens_stois)),
            "ens_mean_pesq": float(np.mean(ens_pesqs)),
            "ens_mean_rmse": float(np.mean(ens_rmses)),
            "ens_mean_corr": float(np.mean(ens_corrs)),
            "ens_joint_pass_count": joint_passes,
            "ens_joint_pass_rate": float(joint_passes / len(PILOT_CLIPS)),
            "runtime_wall_s": elapsed_wall,
            "audio_total_s": total_audio_s,
            "rtf": float(elapsed_wall / total_audio_s),
            "peak_memory_mb": float(peak_mem / (1024 * 1024)),
        }
        config_summaries.append(summary)
        print(f"Summary for {cfg_id}:")
        print(f"  FS Out SNR:  {summary['fs_mean_snr']:.2f} dB (RMSE vs offline: {summary['fs_mean_rmse']:.4f}, r: {summary['fs_mean_corr']:.4f})")
        print(f"  ENS Out SNR: {summary['ens_mean_snr']:.2f} dB, STOI: {summary['ens_mean_stoi']:.4f}, PESQ: {summary['ens_mean_pesq']:.4f}")
        print(f"  ENS Joint Passes: {joint_passes}/{len(PILOT_CLIPS)} ({summary['ens_joint_pass_rate']*100:.1f}%)")
        print(f"  RTF: {summary['rtf']:.4f}, Peak Mem: {summary['peak_memory_mb']:.2f} MB")

    # Write per_clip results CSV
    per_clip_csv_path = OUTPUT_DIR / "pilot_per_clip_results.csv"
    with per_clip_csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(per_clip_records[0].keys()))
        writer.writeheader()
        writer.writerows(per_clip_records)
    print(f"\nWrote per-clip records to {per_clip_csv_path}")

    # Write summary JSON
    summary_json_path = OUTPUT_DIR / "pilot_summary.json"
    with summary_json_path.open("w") as f:
        json.dump(
            {
                "pilot_clips": PILOT_CLIPS,
                "canonical_manifest_sha256": manifest_sha,
                "fullsubnet_checkpoint_sha256": adapter.checkpoint_sha256,
                "total_wall_seconds": time.perf_counter() - started_total,
                "configurations": config_summaries,
            },
            f,
            indent=2,
        )
    print(f"Wrote pilot summary to {summary_json_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

