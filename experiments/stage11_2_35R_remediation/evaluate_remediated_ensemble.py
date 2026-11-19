#!/usr/bin/env python3
"""Stage 11.2.35R: Remediated Native Ensemble Parity & Quality Evaluator.

Audits:
1. Remediated native multi-threaded C ensemble outputs.
2. Parity against Python Causal Candidate B reference (0.15 D + 0.70 F + 0.15 G).
3. Parity against Stage 8 offline baseline (d2_fs70_raw).
4. Objective quality metrics (SNR, SI-SDR, STOI, PESQ-WB) against clean reference.
5. 16-bit PCM integer identity and tolerance distribution.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import sys

import numpy as np
import soundfile as sf
import torch

# Shim for numpy 1.26 / pystoi RankWarning compatibility
import numpy.exceptions
if not hasattr(numpy.exceptions, "RankWarning"):
    numpy.exceptions.RankWarning = np.RankWarning

ROOT = Path("/Users/shreyasdivekar/Documents/anc sih")
EXP_DIR = ROOT / "experiments/stage11_2_35R_remediation"
CANONICAL_DIR = ROOT / "antigravity/runs/sih26052_canonical_validation"
MANIFEST_PATH = CANONICAL_DIR / "manifest.csv"
CLEAN_DIR = CANONICAL_DIR / "clean_audio"
NOISY_DIR = CANONICAL_DIR / "noisy_audio"
BASELINE_DIR = ROOT / "antigravity/runs/stage8_ensemble_20261113/phase_c_ensembles/d2_fs70_raw/predictions"
STEP500_DIR = ROOT / "antigravity/runs/stage8_ensemble_20261113/step500_predictions"
FS_CAND_DIR = ROOT / "antigravity/experiments/stage11_2_34_4_qualification_reconciliation/wavs"
GTCRN_DIR = ROOT / "antigravity/runs/gtcrn_dns3_canonical_20261113/predictions"
WAV_DIR = EXP_DIR / "wavs"

sys.path.insert(0, str(ROOT / "antigravity"))
from scripts.evaluate_dfn3_canonical import metrics

CANONICAL_CLIP_IDS = [0, 1, 3, 4, 9, 23, 26, 28, 33, 61]


def compute_waveform_metrics(ref: np.ndarray, est: np.ndarray) -> dict[str, float]:
    n = min(len(ref), len(est))
    r_t = torch.from_numpy(ref[:n].copy()).double()
    e_t = torch.from_numpy(est[:n].copy()).double()

    diff_t = e_t - r_t
    rmse = float(torch.sqrt(torch.mean(diff_t**2)).item())
    max_err = float(torch.max(torch.abs(diff_t)).item())
    mean_bias = float(torch.mean(diff_t).item())
    r_pow = float(torch.sum(r_t**2).item())
    err_pow = float(torch.sum(diff_t**2).item())
    sdr = float(10.0 * np.log10((r_pow + 1e-12) / (err_pow + 1e-12)))

    rms_e = float(torch.sqrt(torch.mean(e_t**2)).item())
    rms_r = float(torch.sqrt(torch.mean(r_t**2)).item())
    gain_ratio = float(rms_e / (rms_r + 1e-12))

    # Cross-correlation sample lag check in window [-100..+100]
    search_lags = torch.arange(-100, 101)
    corrs = []
    for l in search_lags:
        li = int(l.item())
        if li < 0:
            c = float(torch.sum(e_t[:li] * r_t[-li:]).item() / (n + li))
        elif li > 0:
            c = float(torch.sum(e_t[li:] * r_t[:-li]).item() / (n - li))
        else:
            c = float(torch.sum(e_t * r_t).item() / n)
        corrs.append(c)

    best_idx = int(np.argmax(corrs))
    lag = int(search_lags[best_idx].item())

    return {
        "sdr_db": sdr,
        "rmse": rmse,
        "max_abs_err": max_err,
        "mean_bias": mean_bias,
        "lag_samples": lag,
        "gain_ratio": gain_ratio,
    }


def compute_pcm16_parity(ref: np.ndarray, est: np.ndarray) -> dict[str, object]:
    n = min(len(ref), len(est))
    ref_pcm = np.clip(np.round(ref[:n] * 32768.0), -32768, 32767).astype(np.int32)
    est_pcm = np.clip(np.round(est[:n] * 32768.0), -32768, 32767).astype(np.int32)

    diff = np.abs(est_pcm - ref_pcm)
    identical_count = int(np.sum(diff == 0))
    within_1_count = int(np.sum(diff <= 1))
    ge_2_count = int(np.sum(diff >= 2))
    max_diff = int(np.max(diff))

    return {
        "total_samples": n,
        "identical_samples": identical_count,
        "identical_pct": float(identical_count / n * 100.0),
        "within_1_count_samples": within_1_count,
        "within_1_count_pct": float(within_1_count / n * 100.0),
        "ge_2_count_samples": ge_2_count,
        "ge_2_count_pct": float(ge_2_count / n * 100.0),
        "max_count_diff": max_diff,
    }


def main():
    manifest_info = {}
    with open(MANIFEST_PATH, "r") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            idx = int(row["val_index"])
            if idx in CANONICAL_CLIP_IDS:
                manifest_info[idx] = {
                    "target_snr": float(row["target_snr"]),
                    "dataset_origin": row["dataset_origin"],
                    "clean_hash": row["clean_hash"],
                    "noisy_hash": row["noisy_hash"],
                }

    per_clip_results = []
    
    agg = {
        "sdr_vs_causal_ref": [],
        "sdr_vs_stage8": [],
        "rmse_vs_causal_ref": [],
        "max_abs_err_vs_causal_ref": [],
        "identical_samples": 0,
        "within_1_samples": 0,
        "ge_2_samples": 0,
        "total_samples": 0,
        "snr_db": [],
        "si_sdr_db": [],
        "stoi": [],
        "pesq_wb": [],
    }

    print("Evaluating remediated native ensemble on 10 canonical clips...")

    for cid in CANONICAL_CLIP_IDS:
        clean_path = CLEAN_DIR / f"{cid:04d}_clean.wav"
        noisy_path = NOISY_DIR / f"{cid:04d}_noisy.wav"
        base_path = BASELINE_DIR / f"{cid:04d}_enhanced.wav"
        native_path = WAV_DIR / f"{cid:04d}_ensemble_native.wav"
        dfn3_path = STEP500_DIR / f"{cid:04d}_enhanced.wav"
        fscand_path = FS_CAND_DIR / f"{cid:04d}_standalone_c.wav"
        gtcrn_py_path = GTCRN_DIR / f"{cid:04d}_enhanced.wav"

        clean, _ = sf.read(clean_path, dtype="float32")
        noisy, _ = sf.read(noisy_path, dtype="float32")
        base_wav, _ = sf.read(base_path, dtype="float32")
        native_wav, _ = sf.read(native_path, dtype="float32")
        dfn3_wav, _ = sf.read(dfn3_path, dtype="float32")
        fscand_wav, _ = sf.read(fscand_path, dtype="float32")
        gtcrn_py_wav, _ = sf.read(gtcrn_py_path, dtype="float32")

        # Python Causal Reference: 0.15 D + 0.70 F + 0.15 G
        py_causal_ref = 0.15 * dfn3_wav + 0.70 * fscand_wav + 0.15 * gtcrn_py_wav

        # Metrics vs Causal Ref
        par_vs_causal = compute_waveform_metrics(py_causal_ref, native_wav)
        pcm_vs_causal = compute_pcm16_parity(py_causal_ref, native_wav)

        # Metrics vs Stage 8 Offline
        par_vs_st8 = compute_waveform_metrics(base_wav, native_wav)
        pcm_vs_st8 = compute_pcm16_parity(base_wav, native_wav)

        # Objective Quality Metrics vs Clean
        q_native = metrics(clean, native_wav)
        q_base = metrics(clean, base_wav)

        peak_amp = float(np.max(np.abs(native_wav)))
        clip_count = int(np.sum(np.abs(native_wav) >= 1.0))

        # Accumulate
        agg["sdr_vs_causal_ref"].append(par_vs_causal["sdr_db"])
        agg["sdr_vs_stage8"].append(par_vs_st8["sdr_db"])
        agg["rmse_vs_causal_ref"].append(par_vs_causal["rmse"])
        agg["max_abs_err_vs_causal_ref"].append(par_vs_causal["max_abs_err"])
        agg["identical_samples"] += pcm_vs_causal["identical_samples"]
        agg["within_1_samples"] += pcm_vs_causal["within_1_count_samples"]
        agg["ge_2_samples"] += pcm_vs_causal["ge_2_count_samples"]
        agg["total_samples"] += pcm_vs_causal["total_samples"]
        agg["snr_db"].append(q_native["snr_db"])
        agg["si_sdr_db"].append(q_native["si_sdr_db"])
        agg["stoi"].append(q_native["stoi"])
        agg["pesq_wb"].append(q_native["pesq_wb"])

        per_clip_results.append({
            "val_index": cid,
            "manifest_info": manifest_info.get(cid, {}),
            "sample_count": len(clean),
            "duration_seconds": float(len(clean) / 16000.0),
            "peak_amplitude": peak_amp,
            "clipping_sample_count": clip_count,
            "waveform_parity_vs_causal_ref": par_vs_causal,
            "pcm16_parity_vs_causal_ref": pcm_vs_causal,
            "waveform_parity_vs_stage8_baseline": par_vs_st8,
            "pcm16_parity_vs_stage8_baseline": pcm_vs_st8,
            "quality_metrics_vs_clean": {
                "remediated_native": q_native,
                "stage8_baseline": q_base,
            }
        })

        print(f"Clip {cid:04d}: SDR vs Causal Ref: {par_vs_causal['sdr_db']:.2f} dB, "
              f"PCM Identical: {pcm_vs_causal['identical_pct']:.2f}%, "
              f"PESQ-WB: {q_native['pesq_wb']:.3f}")

    total_s = agg["total_samples"]
    summary = {
        "evaluation_metadata": {
            "stage": "Stage 11.2.35R Remediated Ensemble Evaluation",
            "host": "Apple M4 (macOS 15.1 ARM64)",
            "total_clips": len(CANONICAL_CLIP_IDS),
            "total_evaluated_samples": total_s,
            "ensemble_weights": "0.15 DFN3 + 0.70 FullSubNet Candidate B + 0.15 GTCRN",
        },
        "aggregate_parity_vs_causal_ref": {
            "mean_sdr_db": float(np.mean(agg["sdr_vs_causal_ref"])),
            "min_sdr_db": float(np.min(agg["sdr_vs_causal_ref"])),
            "max_sdr_db": float(np.max(agg["sdr_vs_causal_ref"])),
            "mean_rmse": float(np.mean(agg["rmse_vs_causal_ref"])),
            "max_abs_error": float(np.max(agg["max_abs_err_vs_causal_ref"])),
            "pcm16_total_samples": total_s,
            "pcm16_identical_samples": agg["identical_samples"],
            "pcm16_identical_pct": float(agg["identical_samples"] / total_s * 100.0),
            "pcm16_within_1_count_samples": agg["within_1_samples"],
            "pcm16_within_1_count_pct": float(agg["within_1_samples"] / total_s * 100.0),
            "pcm16_ge_2_count_samples": agg["ge_2_samples"],
            "pcm16_ge_2_count_pct": float(agg["ge_2_samples"] / total_s * 100.0),
        },
        "aggregate_quality_vs_clean": {
            "mean_snr_db": float(np.mean(agg["snr_db"])),
            "mean_si_sdr_db": float(np.mean(agg["si_sdr_db"])),
            "mean_stoi": float(np.mean(agg["stoi"])),
            "mean_pesq_wb": float(np.mean(agg["pesq_wb"])),
        },
        "per_clip_results": per_clip_results,
    }

    out_file = EXP_DIR / "ensemble_parity_results.json"
    with open(out_file, "w") as fp:
        json.dump(summary, fp, indent=2)

    print(f"\n=== AGGREGATE REMEDIATED PARITY SUMMARY ===")
    print(f"Mean SDR vs Causal Ref:      {summary['aggregate_parity_vs_causal_ref']['mean_sdr_db']:.2f} dB")
    print(f"Min  SDR vs Causal Ref:      {summary['aggregate_parity_vs_causal_ref']['min_sdr_db']:.2f} dB")
    print(f"PCM 16-bit Bit-Identical:    {summary['aggregate_parity_vs_causal_ref']['pcm16_identical_pct']:.4f}% ({agg['identical_samples']}/{total_s})")
    print(f"PCM 16-bit Within +-1 Count: {summary['aggregate_parity_vs_causal_ref']['pcm16_within_1_count_pct']:.4f}% ({agg['within_1_samples']}/{total_s})")
    print(f"PCM 16-bit Ge 2 Counts:      {summary['aggregate_parity_vs_causal_ref']['pcm16_ge_2_count_pct']:.4f}% ({agg['ge_2_samples']}/{total_s})")
    print(f"Mean PESQ-WB vs Clean:       {summary['aggregate_quality_vs_clean']['mean_pesq_wb']:.3f}")
    print(f"Mean STOI vs Clean:          {summary['aggregate_quality_vs_clean']['mean_stoi']:.4f}")
    print(f"Saved complete parity report to {out_file}")


if __name__ == "__main__":
    main()
