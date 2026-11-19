#!/usr/bin/env python3
"""Stage 11.2.35: Canonical Multi-Threaded Ensemble Evaluator.

Compares the native multi-threaded C ensemble output against:
1. The frozen Stage 8 Python ensemble baseline (d2_fs70_raw).
2. Clean speech reference to measure output SNR, SI-SDR, STOI, and PESQ-WB.
3. 16-bit PCM integer agreement within +-1 count.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

# Shim for numpy 1.26 / pystoi RankWarning compatibility
import numpy.exceptions
if not hasattr(numpy.exceptions, "RankWarning"):
    numpy.exceptions.RankWarning = np.RankWarning

ROOT = Path(__file__).resolve().parents[3]
STAGE_DIR = Path(__file__).resolve().parent
CANONICAL_DIR = ROOT / "antigravity/runs/sih26052_canonical_validation"
BASELINE_DIR = ROOT / "antigravity/runs/stage8_ensemble_20261113/phase_c_ensembles/d2_fs70_raw/predictions"
STEP500_DIR = ROOT / "antigravity/runs/stage8_ensemble_20261113/step500_predictions"
NOISY_DIR = CANONICAL_DIR / "noisy_audio"
CLEAN_DIR = CANONICAL_DIR / "clean_audio"
WAV_OUT_DIR = STAGE_DIR / "wavs"

sys.path.insert(0, str(ROOT / "antigravity"))
from scripts.evaluate_dfn3_canonical import metrics

CANONICAL_CLIP_IDS = [0, 1, 3, 4, 9, 23, 26, 28, 33, 61]


def compute_waveform_parity(ref: np.ndarray, est: np.ndarray) -> dict[str, float]:
    n = min(len(ref), len(est))
    r = ref[:n].astype(np.float64)
    e = est[:n].astype(np.float64)
    diff = e - r

    rmse = float(np.sqrt(np.mean(diff**2)))
    max_err = float(np.max(np.abs(diff)))
    r_pow = float(np.sum(r**2))
    err_pow = float(np.sum(diff**2))
    sdr = float(10.0 * np.log10((r_pow + 1e-12) / (err_pow + 1e-12)))

    # Cross-correlation lag
    fft_len = 1 << (2 * n - 1).bit_length()
    r_fft = np.fft.rfft(r - np.mean(r), fft_len)
    e_fft = np.fft.rfft(e - np.mean(e), fft_len)
    xcorr = np.fft.irfft(e_fft * np.conj(r_fft), fft_len)
    xcorr = np.concatenate((xcorr[-(n - 1):], xcorr[:n]))
    lag = int(np.argmax(xcorr) - (n - 1))

    # Gain ratio
    gain_ratio = float(np.sqrt(np.mean(e**2)) / (np.sqrt(np.mean(r**2)) + 1e-12))

    return {
        "sdr_db": sdr,
        "rmse": rmse,
        "max_abs_err": max_err,
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
        "max_count_diff": max_diff,
    }


def main():
    WAV_OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Run native executable across canonical clips
    cmd = [
        str(STAGE_DIR / "sih_ensemble_host"),
        "--evaluate-canonical",
        str(STAGE_DIR / "models/fullband_step.onnx"),
        str(STAGE_DIR / "models/subband_step.onnx"),
        str(STAGE_DIR / "models/gtcrn_model.onnx"),
        str(NOISY_DIR),
        str(STEP500_DIR),
        str(WAV_OUT_DIR),
        str(STAGE_DIR / "canonical_eval.json"),
    ]
    print("Executing native ensemble pipeline on canonical clips...")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print("ERROR running native ensemble:", proc.stderr)
        sys.exit(1)
    print(proc.stdout)

    # 2. Evaluate each clip against Stage 8 baseline and clean reference
    clip_results = []
    base_metrics_list = []
    cand_metrics_list = []

    print("\nEvaluating Objective Speech Metrics (SNR, SI-SDR, STOI, PESQ-WB)...")
    for cid in CANONICAL_CLIP_IDS:
        clean_path = CLEAN_DIR / f"{cid:04d}_clean.wav"
        noisy_path = NOISY_DIR / f"{cid:04d}_noisy.wav"
        base_path = BASELINE_DIR / f"{cid:04d}_enhanced.wav"
        cand_path = WAV_OUT_DIR / f"{cid:04d}_ensemble_native.wav"

        clean, _ = sf.read(clean_path, dtype="float32")
        noisy, _ = sf.read(noisy_path, dtype="float32")
        base_wav, _ = sf.read(base_path, dtype="float32")
        cand_wav, _ = sf.read(cand_path, dtype="float32")

        # Parity vs Stage 8 Baseline
        parity_base = compute_waveform_parity(base_wav, cand_wav)
        pcm_base = compute_pcm16_parity(base_wav, cand_wav)

        # Objective Quality Metrics
        m_base = metrics(clean, base_wav)
        m_cand = metrics(clean, cand_wav)
        base_metrics_list.append(m_base)
        cand_metrics_list.append(m_cand)

        clip_results.append({
            "val_index": cid,
            "waveform_parity_vs_stage8": parity_base,
            "pcm16_parity_vs_stage8": pcm_base,
            "quality_metrics": {
                "stage8_baseline": m_base,
                "native_candidate": m_cand,
                "delta": {
                    "snr_db": m_cand["snr_db"] - m_base["snr_db"],
                    "si_sdr_db": m_cand["si_sdr_db"] - m_base["si_sdr_db"],
                    "stoi": m_cand["stoi"] - m_base["stoi"],
                    "pesq_wb": m_cand["pesq_wb"] - m_base["pesq_wb"],
                }
            }
        })

    # Summary Statistics
    summary = {
        "num_clips": len(CANONICAL_CLIP_IDS),
        "mean_quality_metrics": {
            "stage8_baseline": {
                "snr_db": float(np.mean([m["snr_db"] for m in base_metrics_list])),
                "si_sdr_db": float(np.mean([m["si_sdr_db"] for m in base_metrics_list])),
                "stoi": float(np.mean([m["stoi"] for m in base_metrics_list])),
                "pesq_wb": float(np.mean([m["pesq_wb"] for m in base_metrics_list])),
            },
            "native_candidate": {
                "snr_db": float(np.mean([m["snr_db"] for m in cand_metrics_list])),
                "si_sdr_db": float(np.mean([m["si_sdr_db"] for m in cand_metrics_list])),
                "stoi": float(np.mean([m["stoi"] for m in cand_metrics_list])),
                "pesq_wb": float(np.mean([m["pesq_wb"] for m in cand_metrics_list])),
            },
            "mean_delta": {
                "snr_db": float(np.mean([c["quality_metrics"]["delta"]["snr_db"] for c in clip_results])),
                "si_sdr_db": float(np.mean([c["quality_metrics"]["delta"]["si_sdr_db"] for c in clip_results])),
                "stoi": float(np.mean([c["quality_metrics"]["delta"]["stoi"] for c in clip_results])),
                "pesq_wb": float(np.mean([c["quality_metrics"]["delta"]["pesq_wb"] for c in clip_results])),
            }
        },
        "per_clip": clip_results,
    }

    out_file = STAGE_DIR / "stage11_2_35_canonical_evaluation.json"
    with open(out_file, "w") as fp:
        json.dump(summary, fp, indent=2)

    print("\n======================================================================")
    print("STAGE 11.2.35 CANONICAL ENSEMBLE EVALUATION SUMMARY (10 CLIPS)")
    print("======================================================================")
    print("Metric     | Stage 8 Baseline | Native Candidate | Delta")
    print("-----------|------------------|------------------|-------")
    b = summary["mean_quality_metrics"]["stage8_baseline"]
    c = summary["mean_quality_metrics"]["native_candidate"]
    d = summary["mean_quality_metrics"]["mean_delta"]
    print(f"SNR (dB)   | {b['snr_db']:16.2f} | {c['snr_db']:16.2f} | {d['snr_db']:+6.2f}")
    print(f"SI-SDR(dB) | {b['si_sdr_db']:16.2f} | {c['si_sdr_db']:16.2f} | {d['si_sdr_db']:+6.2f}")
    print(f"STOI       | {b['stoi']:16.4f} | {c['stoi']:16.4f} | {d['stoi']:+6.4f}")
    print(f"PESQ-WB    | {b['pesq_wb']:16.3f} | {c['pesq_wb']:16.3f} | {d['pesq_wb']:+6.3f}")
    print("======================================================================")
    print(f"Detailed evaluation report written to {out_file}")


if __name__ == "__main__":
    main()
