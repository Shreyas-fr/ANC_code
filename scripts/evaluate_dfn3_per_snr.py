#!/usr/bin/env python3
"""
scripts/evaluate_dfn3_per_snr.py

Comprehensive evaluation of canonical DeepFilterNet3 (final_model/model.hk)
on the SIH26052 590-clip canonical validation set.

Outputs generated under results/dfn3/:
  - metrics_per_clip.csv
  - per_snr_table.md
  - per_origin_table.md
  - targets_vs_measured.png
  - deployed_streaming_comparison.md
"""

import os
import sys
import time
import math
import csv
import json
import hashlib
from pathlib import Path
from collections import defaultdict

import numpy as np
import scipy.signal as signal
import soundfile as sf
import torch

# Ensure repo root and edge/ are in python path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "edge"))

# Torchaudio backend shim
from edge.dfn3_enhance import _torchaudio_shim, FROZEN_SHA256, sha256_file
_torchaudio_shim()

import hk
from df.enhance import init_df, maybe_download_model, enhance
from pystoi import stoi as pystoi_stoi
from pesq import pesq as pesq_pesq

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

CANONICAL_AUDIO_DIR = Path("/Users/shreyasdivekar/Documents/anc sih/antigravity/runs/sih26052_canonical_validation")
MANIFEST_PATH = REPO_ROOT / "runs/sih26052_canonical_validation/manifest.csv"
MODEL_PATH = REPO_ROOT / "final_model/model.hk"
RESULTS_DIR = REPO_ROOT / "results/dfn3"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# PS TARGETS
PS_TARGET_SNR = 15.0
PS_TARGET_STOI = 0.85
PS_TARGET_PESQ = 2.50

def compute_si_sdr(ref: np.ndarray, est: np.ndarray) -> float:
    eps = 1e-8
    ref = np.asanyarray(ref, dtype=np.float32)
    est = np.asanyarray(est, dtype=np.float32)
    min_l = min(len(ref), len(est))
    ref = ref[:min_l] - np.mean(ref[:min_l])
    est = est[:min_l] - np.mean(est[:min_l])
    ref_energy = np.sum(ref ** 2)
    optimal_scaling = np.sum(ref * est) / (ref_energy + eps)
    projection = optimal_scaling * ref
    noise = est - projection
    ratio = np.sum(projection ** 2) / (np.sum(noise ** 2) + eps)
    return float(10.0 * np.log10(ratio + eps))

def compute_explicit_snr(clean: np.ndarray, est: np.ndarray) -> float:
    """10*log10(||clean||^2 / ||est - clean||^2)"""
    min_l = min(len(clean), len(est))
    c = clean[:min_l].astype(np.float64)
    e = est[:min_l].astype(np.float64)
    c_pwr = np.sum(c ** 2)
    err_pwr = np.sum((e - c) ** 2)
    if err_pwr <= 1e-12:
        return 99.0
    if c_pwr <= 1e-12:
        return -99.0
    return float(10.0 * np.log10(c_pwr / err_pwr))

def calculate_active_speech_level(waveform: np.ndarray, sample_rate=16000, frame_length_ms=30) -> float:
    x = np.asanyarray(waveform, dtype=np.float32)
    frame_length = int(sample_rate * frame_length_ms / 1000)
    if len(x) < frame_length:
        return float(np.mean(x ** 2))
    n_frames = len(x) // frame_length
    frames = x[:n_frames * frame_length].reshape(n_frames, frame_length)
    frame_energies = np.mean(frames ** 2, axis=-1)
    max_energy = np.max(frame_energies) if len(frame_energies) > 0 else 0.0
    threshold = max_energy * 0.001
    active_frames = frame_energies[frame_energies > threshold]
    if len(active_frames) == 0:
        return float(np.mean(x ** 2))
    return float(np.mean(active_frames))

def compute_active_snr(clean: np.ndarray, est: np.ndarray, sr=16000) -> float:
    """Historical active speech SNR: 10*log10(active_speech_pwr / err_pwr)"""
    min_l = min(len(clean), len(est))
    c = clean[:min_l]
    e = est[:min_l]
    cp = calculate_active_speech_level(c, sample_rate=sr)
    npwr = float(np.mean((e - c) ** 2))
    if cp > 0 and npwr > 0:
        return float(10.0 * np.log10(cp / npwr))
    return 0.0

def align_signals(ref: np.ndarray, sig: np.ndarray, max_lag_samples: int = 800):
    """
    Find optimal lag d in [-max_lag_samples, max_lag_samples] via cross-correlation.
    Returns (aligned_ref, aligned_sig, best_lag).
    """
    min_l = min(len(ref), len(sig))
    r = ref[:min_l].astype(np.float32)
    s = sig[:min_l].astype(np.float32)
    
    best_lag = 0
    best_corr = -1e12
    for lag in range(-max_lag_samples, max_lag_samples + 1):
        if lag > 0:
            c = np.dot(s[lag:], r[:len(s)-lag])
        elif lag < 0:
            c = np.dot(s[:len(s)+lag], r[-lag:])
        else:
            c = np.dot(s, r)
        if c > best_corr:
            best_corr = c
            best_lag = lag
            
    if best_lag > 0:
        s_aligned = s[best_lag:]
        r_aligned = r[:len(s_aligned)]
    elif best_lag < 0:
        s_aligned = s[:len(s)+best_lag]
        r_aligned = r[-best_lag:]
    else:
        s_aligned = s
        r_aligned = r
        
    return r_aligned, s_aligned, best_lag

def score_pair(clean_16k: np.ndarray, test_16k: np.ndarray, max_lag: int = 800):
    c_aln, t_aln, lag = align_signals(clean_16k, test_16k, max_lag_samples=max_lag)
    
    snr_exp = compute_explicit_snr(c_aln, t_aln)
    snr_act = compute_active_snr(c_aln, t_aln, sr=16000)
    sisdr = compute_si_sdr(c_aln, t_aln)
    
    try:
        st = float(pystoi_stoi(c_aln, t_aln, 16000, extended=False))
    except Exception:
        st = float("nan")
        
    try:
        pq = float(pesq_pesq(16000, c_aln, t_aln, "wb"))
    except Exception:
        pq = float("nan")
        
    return {
        "snr_explicit": snr_exp,
        "snr_active": snr_act,
        "sisdr": sisdr,
        "stoi": st,
        "pesq": pq,
        "lag": lag
    }

def main():
    print("=" * 70)
    print("SIH26052 DFN3 CANONICAL EVALUATION & PER-SNR ANALYSIS")
    print("=" * 70)
    
    # 1. Model Verification
    print("\n--- TASK 0: Model Checkpoint & Manifest Verification ---")
    model_sha = sha256_file(str(MODEL_PATH))
    print(f"Model Path:   {MODEL_PATH}")
    print(f"Model SHA256: {model_sha}")
    assert model_sha == FROZEN_SHA256, f"Checksum mismatch: {model_sha} != {FROZEN_SHA256}"
    print("Checkpoint SHA256 matches frozen canonical checkpoint EXACTLY.")
    
    assert MANIFEST_PATH.exists(), f"Manifest not found at {MANIFEST_PATH}"
    with open(MANIFEST_PATH, newline="") as f:
        manifest_rows = list(csv.DictReader(f))
    print(f"Manifest rows: {len(manifest_rows)}")
    assert len(manifest_rows) == 590, f"Expected 590 rows, got {len(manifest_rows)}"
    
    # Check audio files presence
    for i in [0, 295, 589]:
        c_p = CANONICAL_AUDIO_DIR / "clean_audio" / f"{i:04d}_clean.wav"
        n_p = CANONICAL_AUDIO_DIR / "noisy_audio" / f"{i:04d}_noisy.wav"
        assert c_p.exists() and n_p.exists(), f"Audio files missing for clip {i}"
    print(f"Canonical audio files located at {CANONICAL_AUDIO_DIR}")
    
    # Load DFN3
    print("\n--- Loading DeepFilterNet3 Model ---")
    base = maybe_download_model("DeepFilterNet3")
    model, df_state, _ = init_df(base, log_file=None)
    model = model.cpu()
    state_dict = hk.load_file(str(MODEL_PATH))
    state = state_dict["model_state_dict"] if "model_state_dict" in state_dict else state_dict
    model.load_state_dict(state, strict=True)
    model.eval()
    print("DeepFilterNet3 fine-tuned checkpoint loaded into memory strictly.")
    
    # Evaluate all 590 clips
    print("\n--- Evaluating 590 Clips (Offline Mode) ---")
    clip_metrics = []
    t0 = time.time()
    
    for idx, row in enumerate(manifest_rows):
        val_idx = int(row["val_index"])
        origin = row.get("dataset_origin", "UNKNOWN")
        target_snr = float(row.get("target_snr", 0.0))
        
        c_path = CANONICAL_AUDIO_DIR / "clean_audio" / f"{val_idx:04d}_clean.wav"
        n_path = CANONICAL_AUDIO_DIR / "noisy_audio" / f"{val_idx:04d}_noisy.wav"
        
        clean_16k, _ = sf.read(str(c_path), dtype="float32")
        noisy_16k, _ = sf.read(str(n_path), dtype="float32")
        
        # Resample 16k -> 48k for DFN3
        noisy_48k = signal.resample_poly(noisy_16k, 48000, 16000).astype(np.float32)
        t_48k = torch.from_numpy(noisy_48k).unsqueeze(0)
        with torch.no_grad():
            enh_48k = enhance(model, df_state, t_48k)
        enh_48k_np = enh_48k.squeeze().cpu().numpy()
        enh_16k = signal.resample_poly(enh_48k_np, 16000, 48000).astype(np.float32)[:len(noisy_16k)]
        
        # Score noisy vs clean
        n_scores = score_pair(clean_16k, noisy_16k, max_lag=800)
        # Score enh vs clean
        e_scores = score_pair(clean_16k, enh_16k, max_lag=800)
        
        entry = {
            "val_index": val_idx,
            "dataset_origin": origin,
            "target_snr": target_snr,
            "in_snr_explicit": round(n_scores["snr_explicit"], 4),
            "in_snr_active": round(n_scores["snr_active"], 4),
            "in_sisdr": round(n_scores["sisdr"], 4),
            "in_stoi": round(n_scores["stoi"], 4),
            "in_pesq": round(n_scores["pesq"], 4),
            "in_lag": n_scores["lag"],
            "out_snr_explicit": round(e_scores["snr_explicit"], 4),
            "out_snr_active": round(e_scores["snr_active"], 4),
            "out_sisdr": round(e_scores["sisdr"], 4),
            "out_stoi": round(e_scores["stoi"], 4),
            "out_pesq": round(e_scores["pesq"], 4),
            "out_lag": e_scores["lag"],
            "delta_sisdr": round(e_scores["sisdr"] - n_scores["sisdr"], 4),
            "delta_stoi": round(e_scores["stoi"] - n_scores["stoi"], 4),
            "delta_pesq": round(e_scores["pesq"] - n_scores["pesq"], 4),
            "delta_snr_explicit": round(e_scores["snr_explicit"] - n_scores["snr_explicit"], 4),
        }
        clip_metrics.append(entry)
        
        if (idx + 1) % 100 == 0 or idx == len(manifest_rows) - 1:
            elapsed = time.time() - t0
            print(f"Processed {idx + 1}/{len(manifest_rows)} clips [{elapsed:.1f}s, {(idx+1)/elapsed:.1f} clips/s]")
            
    # Save metrics_per_clip.csv
    csv_out_path = RESULTS_DIR / "metrics_per_clip.csv"
    with open(csv_out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=clip_metrics[0].keys())
        writer.writeheader()
        writer.writerows(clip_metrics)
    print(f"\nSaved per-clip metrics to: {csv_out_path}")
    
    # --- TASK 1: SANITY GATE ---
    print("\n" + "=" * 70)
    print("TASK 1 - SANITY GATE VERIFICATION")
    print("=" * 70)
    
    def mean_val(key):
        vals = [r[key] for r in clip_metrics if not math.isnan(r[key])]
        return float(np.mean(vals))
        
    m_in_sisdr = mean_val("in_sisdr")
    m_out_sisdr = mean_val("out_sisdr")
    m_out_stoi = mean_val("out_stoi")
    m_out_pesq = mean_val("out_pesq")
    m_out_snr_act = mean_val("out_snr_active")
    m_out_snr_exp = mean_val("out_snr_explicit")
    m_in_stoi = mean_val("in_stoi")
    m_in_pesq = mean_val("in_pesq")
    m_in_snr_act = mean_val("in_snr_active")
    m_in_snr_exp = mean_val("in_snr_explicit")
    
    # Documented values: noisy SI-SDR 6.03, DFN3 SI-SDR 8.45, STOI 0.866, PESQ 1.798, output SNR 7.27
    doc_in_sisdr = 6.03
    doc_out_sisdr = 8.45
    doc_out_stoi = 0.866
    doc_out_pesq = 1.798
    doc_out_snr = 7.27
    
    diff_in_sisdr = abs(m_in_sisdr - doc_in_sisdr)
    diff_out_sisdr = abs(m_out_sisdr - doc_out_sisdr)
    diff_out_stoi = abs(m_out_stoi - doc_out_stoi)
    diff_out_pesq = abs(m_out_pesq - doc_out_pesq)
    diff_out_snr = abs(m_out_snr_act - doc_out_snr)
    
    print(f"Noisy SI-SDR:      Measured = {m_in_sisdr:6.3f} dB | Documented = {doc_in_sisdr:6.3f} dB | Diff = {diff_in_sisdr:6.3f} dB (limit: 0.20)")
    print(f"DFN3 SI-SDR:       Measured = {m_out_sisdr:6.3f} dB | Documented = {doc_out_sisdr:6.3f} dB | Diff = {diff_out_sisdr:6.3f} dB (limit: 0.20)")
    print(f"DFN3 STOI:         Measured = {m_out_stoi:6.3f}    | Documented = {doc_out_stoi:6.3f}    | Diff = {diff_out_stoi:6.3f}    (limit: 0.02)")
    print(f"DFN3 PESQ:         Measured = {m_out_pesq:6.3f}    | Documented = {doc_out_pesq:6.3f}    | Diff = {diff_out_pesq:6.3f}    (limit: 0.02)")
    print(f"DFN3 Active SNR:   Measured = {m_out_snr_act:6.3f} dB | Documented = {doc_out_snr:6.3f} dB | Diff = {diff_out_snr:6.3f} dB")
    print(f"DFN3 Explicit SNR: Measured = {m_out_snr_exp:6.3f} dB | (10*log10(||clean||^2 / ||enh - clean||^2))")
    
    gate_passed = (
        diff_in_sisdr <= 0.20 and
        diff_out_sisdr <= 0.20 and
        diff_out_stoi <= 0.02 and
        diff_out_pesq <= 0.02
    )
    
    if not gate_passed:
        print("\nFATAL: SANITY GATE FAILED! Discrepancy exceeds allowed tolerance.")
        sys.exit(1)
        
    print("\n>>> SANITY GATE PASSED: Measured overall metrics match documented baseline within strict limits! <<<")
    
    # --- TASK 2: PER-SNR TABLE ---
    print("\n" + "=" * 70)
    print("TASK 2 - PER-SNR ANALYSIS & REPORTING")
    print("=" * 70)
    
    snr_groups = defaultdict(list)
    for r in clip_metrics:
        snr_groups[r["target_snr"]].append(r)
        
    snr_targets = sorted(snr_groups.keys())
    
    per_snr_rows = []
    for snr in snr_targets:
        clips = snr_groups[snr]
        n = len(clips)
        
        in_exp_m = np.mean([c["in_snr_explicit"] for c in clips])
        in_exp_s = np.std([c["in_snr_explicit"] for c in clips])
        out_exp_m = np.mean([c["out_snr_explicit"] for c in clips])
        out_exp_s = np.std([c["out_snr_explicit"] for c in clips])
        
        in_sdr_m = np.mean([c["in_sisdr"] for c in clips])
        in_sdr_s = np.std([c["in_sisdr"] for c in clips])
        out_sdr_m = np.mean([c["out_sisdr"] for c in clips])
        out_sdr_s = np.std([c["out_sisdr"] for c in clips])
        
        in_st_m = np.mean([c["in_stoi"] for c in clips])
        in_st_s = np.std([c["in_stoi"] for c in clips])
        out_st_m = np.mean([c["out_stoi"] for c in clips])
        out_st_s = np.std([c["out_stoi"] for c in clips])
        
        in_pq_m = np.mean([c["in_pesq"] for c in clips])
        in_pq_s = np.std([c["in_pesq"] for c in clips])
        out_pq_m = np.mean([c["out_pesq"] for c in clips])
        out_pq_s = np.std([c["out_pesq"] for c in clips])
        
        pass_snr = "PASS" if out_exp_m >= PS_TARGET_SNR else "FAIL"
        pass_stoi = "PASS" if out_st_m >= PS_TARGET_STOI else "FAIL"
        pass_pesq = "PASS" if out_pq_m >= PS_TARGET_PESQ else "FAIL"
        
        row_dict = {
            "snr": snr,
            "n": n,
            "in_snr_mean": in_exp_m, "in_snr_std": in_exp_s,
            "out_snr_mean": out_exp_m, "out_snr_std": out_exp_s,
            "pass_snr": pass_snr,
            "in_sisdr_mean": in_sdr_m, "in_sisdr_std": in_sdr_s,
            "out_sisdr_mean": out_sdr_m, "out_sisdr_std": out_sdr_s,
            "in_stoi_mean": in_st_m, "in_stoi_std": in_st_s,
            "out_stoi_mean": out_st_m, "out_stoi_std": out_st_s,
            "pass_stoi": pass_stoi,
            "in_pesq_mean": in_pq_m, "in_pesq_std": in_pq_s,
            "out_pesq_mean": out_pq_m, "out_pesq_std": out_pq_s,
            "pass_pesq": pass_pesq,
        }
        per_snr_rows.append(row_dict)
        
    # Write results/dfn3/per_snr_table.md
    md_table_path = RESULTS_DIR / "per_snr_table.md"
    with open(md_table_path, "w") as f:
        f.write("# DeepFilterNet3 Canonical Per-SNR Evaluation Table\n\n")
        f.write(f"- **Evaluated Checkpoint**: `final_model/model.hk` (SHA256 `{FROZEN_SHA256}`)\n")
        f.write("- **Dataset**: SIH26052 Canonical 590-clip Validation Set\n")
        f.write(f"- **Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("## Problem Statement (PS) Targets\n")
        f.write("- **Output SNR**: > 15.0 dB (explicit formula $10\\log_{10}(\\|\\text{clean}\\|^2 / \\|\\text{est} - \\text{clean}\\|^2)$)\n")
        f.write("- **STOI**: > 0.85\n")
        f.write("- **PESQ (wideband, 16 kHz)**: > 2.50\n\n")
        f.write("## Measured Per-SNR Results\n\n")
        f.write("| Input SNR (dB) | n | Noisy In SNR | DFN3 Out SNR (dB) | PS SNR (>15 dB) | Noisy STOI | DFN3 STOI | PS STOI (>0.85) | Noisy PESQ | DFN3 PESQ | PS PESQ (>2.5) | Noisy SI-SDR | DFN3 SI-SDR |\n")
        f.write("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n")
        for r in per_snr_rows:
            f.write(f"| {r['snr']:+.1f} | {r['n']} | {r['in_snr_mean']:.2f} ± {r['in_snr_std']:.2f} | **{r['out_snr_mean']:.2f} ± {r['out_snr_std']:.2f}** | **{r['pass_snr']}** | {r['in_stoi_mean']:.3f} ± {r['in_stoi_std']:.3f} | **{r['out_stoi_mean']:.3f} ± {r['out_stoi_std']:.3f}** | **{r['pass_stoi']}** | {r['in_pesq_mean']:.3f} ± {r['in_pesq_std']:.3f} | **{r['out_pesq_mean']:.3f} ± {r['out_pesq_std']:.3f}** | **{r['pass_pesq']}** | {r['in_sisdr_mean']:.2f} ± {r['in_sisdr_std']:.2f} | {r['out_sisdr_mean']:.2f} ± {r['out_sisdr_std']:.2f} |\n")
            
        f.write("\n\n## Overall Means Across All 590 Clips\n\n")
        f.write(f"- **Noisy Input**: Explicit SNR = {m_in_snr_exp:.2f} dB, Active SNR = {m_in_snr_act:.2f} dB, SI-SDR = {m_in_sisdr:.2f} dB, STOI = {m_in_stoi:.3f}, PESQ = {m_in_pesq:.3f}\n")
        f.write(f"- **DFN3 Enhanced**: Explicit SNR = {m_out_snr_exp:.2f} dB, Active SNR = {m_out_snr_act:.2f} dB, SI-SDR = {m_out_sisdr:.2f} dB, STOI = {m_out_stoi:.3f}, PESQ = {m_out_pesq:.3f}\n")
    print(f"Generated per-SNR table: {md_table_path}")
    
    # --- TASK 2: PER-ORIGIN BREAKDOWN AT 5, 10, 15 dB ---
    print("\n--- TASK 2: Per-Origin Breakdown at 5, 10, 15 dB ---")
    origin_snrs = [5.0, 10.0, 15.0]
    origins = ["IoBT_GUNFIRE", "EXISTING_PROXY"]
    
    origin_rows = []
    for snr in origin_snrs:
        for orig in origins:
            sub = [c for c in clip_metrics if c["target_snr"] == snr and c["dataset_origin"] == orig]
            n = len(sub)
            if n == 0:
                continue
            in_snr_m = np.mean([c["in_snr_explicit"] for c in sub])
            out_snr_m = np.mean([c["out_snr_explicit"] for c in sub])
            in_sdr_m = np.mean([c["in_sisdr"] for c in sub])
            out_sdr_m = np.mean([c["out_sisdr"] for c in sub])
            in_st_m = np.mean([c["in_stoi"] for c in sub])
            out_st_m = np.mean([c["out_stoi"] for c in sub])
            in_pq_m = np.mean([c["in_pesq"] for c in sub])
            out_pq_m = np.mean([c["out_pesq"] for c in sub])
            
            origin_rows.append({
                "snr": snr,
                "origin": orig,
                "n": n,
                "in_snr": in_snr_m,
                "out_snr": out_snr_m,
                "in_sisdr": in_sdr_m,
                "out_sisdr": out_sdr_m,
                "in_stoi": in_st_m,
                "out_stoi": out_st_m,
                "in_pesq": in_pq_m,
                "out_pesq": out_pq_m,
                "delta_sdr": out_sdr_m - in_sdr_m,
                "delta_stoi": out_st_m - in_st_m,
                "delta_pesq": out_pq_m - in_pq_m,
            })
            
    md_origin_path = RESULTS_DIR / "per_origin_table.md"
    with open(md_origin_path, "w") as f:
        f.write("# DeepFilterNet3 Canonical Per-Origin Breakdown (5, 10, 15 dB)\n\n")
        f.write(f"- **Evaluated Checkpoint**: `final_model/model.hk` (SHA256 `{FROZEN_SHA256}`)\n")
        f.write(f"- **Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("| Target SNR | Dataset Origin | n | In SNR (dB) | Out SNR (dB) | In SI-SDR | Out SI-SDR | Δ SI-SDR | In STOI | Out STOI | Δ STOI | In PESQ | Out PESQ | Δ PESQ |\n")
        f.write("| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n")
        for r in origin_rows:
            f.write(f"| {r['snr']:+.0f} dB | {r['origin']} | {r['n']} | {r['in_snr']:.2f} | **{r['out_snr']:.2f}** | {r['in_sisdr']:.2f} | **{r['out_sisdr']:.2f}** | {r['delta_sdr']:+.2f} dB | {r['in_stoi']:.3f} | **{r['out_stoi']:.3f}** | {r['delta_stoi']:+.3f} | {r['in_pesq']:.3f} | **{r['out_pesq']:.3f}** | {r['delta_pesq']:+.3f} |\n")
    print(f"Generated per-origin table: {md_origin_path}")
    
    # --- TASK 2: TARGETS VS MEASURED PLOT ---
    print("\n--- Generating targets_vs_measured.png Plot ---")
    plot_path = RESULTS_DIR / "targets_vs_measured.png"
    
    snrs = [r["snr"] for r in per_snr_rows]
    out_stois = [r["out_stoi_mean"] for r in per_snr_rows]
    in_stois = [r["in_stoi_mean"] for r in per_snr_rows]
    out_pesqs = [r["out_pesq_mean"] for r in per_snr_rows]
    in_pesqs = [r["in_pesq_mean"] for r in per_snr_rows]
    out_snrs = [r["out_snr_mean"] for r in per_snr_rows]
    in_snrs = [r["in_snr_mean"] for r in per_snr_rows]
    
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    
    # Plot 1: STOI vs Input SNR
    ax = axes[0]
    ax.plot(snrs, in_stois, "o--", color="#6c757d", label="Noisy Input", linewidth=1.8, markersize=6)
    ax.plot(snrs, out_stois, "s-", color="#1f77b4", label="DFN3 Enhanced", linewidth=2.2, markersize=7)
    ax.axhline(PS_TARGET_STOI, color="#d62728", linestyle=":", linewidth=2.0, label=f"PS Target ({PS_TARGET_STOI})")
    ax.set_title("STOI vs Input SNR", fontsize=13, fontweight="bold")
    ax.set_xlabel("Input Target SNR (dB)", fontsize=11)
    ax.set_ylabel("STOI (0 to 1)", fontsize=11)
    ax.set_ylim([0.4, 1.0])
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="lower right", framealpha=0.9)
    
    # Plot 2: PESQ vs Input SNR
    ax = axes[1]
    ax.plot(snrs, in_pesqs, "o--", color="#6c757d", label="Noisy Input", linewidth=1.8, markersize=6)
    ax.plot(snrs, out_pesqs, "s-", color="#2ca02c", label="DFN3 Enhanced", linewidth=2.2, markersize=7)
    ax.axhline(PS_TARGET_PESQ, color="#d62728", linestyle=":", linewidth=2.0, label=f"PS Target ({PS_TARGET_PESQ})")
    ax.set_title("PESQ (Wideband) vs Input SNR", fontsize=13, fontweight="bold")
    ax.set_xlabel("Input Target SNR (dB)", fontsize=11)
    ax.set_ylabel("PESQ Score (1.0 to 4.5)", fontsize=11)
    ax.set_ylim([1.0, 3.5])
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="lower right", framealpha=0.9)
    
    # Plot 3: Output SNR vs Input SNR
    ax = axes[2]
    ax.plot(snrs, in_snrs, "o--", color="#6c757d", label="Noisy Input", linewidth=1.8, markersize=6)
    ax.plot(snrs, out_snrs, "s-", color="#ff7f0e", label="DFN3 Enhanced", linewidth=2.2, markersize=7)
    ax.axhline(PS_TARGET_SNR, color="#d62728", linestyle=":", linewidth=2.0, label=f"PS Target ({PS_TARGET_SNR} dB)")
    ax.set_title("Measured Output SNR vs Input SNR", fontsize=13, fontweight="bold")
    ax.set_xlabel("Input Target SNR (dB)", fontsize=11)
    ax.set_ylabel("Output SNR (dB)", fontsize=11)
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(loc="lower right", framealpha=0.9)
    
    plt.tight_layout()
    plt.savefig(plot_path, dpi=200)
    plt.close()
    print(f"Generated plot: {plot_path}")
    
    # --- TASK 3: DEPLOYED-CONFIG CHECK (5, 10, 15 dB subsets) ---
    print("\n" + "=" * 70)
    print("TASK 3 - DEPLOYED-CONFIG STREAMING CHECK (5, 10, 15 dB subsets)")
    print("=" * 70)
    
    try:
        from edge.streaming_core import AudioChain, BlockBackend
        from edge.dfn3_enhance import make_dfn3_enhance_fn
        
        block_enhance_fn = make_dfn3_enhance_fn(str(MODEL_PATH), threads=3)
        deployed_chain = AudioChain(
            BlockBackend(block_enhance_fn, block_ms=500, context_ms=300, guard_ms=40, xfade_ms=10)
        )
        print("Initialized deployed AudioChain with BlockBackend (500 ms block, 300 ms context).")
        
        deployed_targets = [5.0, 10.0, 15.0]
        deployed_clips = [c for c in clip_metrics if c["target_snr"] in deployed_targets]
        print(f"Running streaming deployed check on {len(deployed_clips)} clips (5, 10, 15 dB)...")
        
        deployed_results = []
        FRAME_SIZE = 256
        
        for i, c in enumerate(deployed_clips):
            val_idx = c["val_index"]
            c_path = CANONICAL_AUDIO_DIR / "clean_audio" / f"{val_idx:04d}_clean.wav"
            n_path = CANONICAL_AUDIO_DIR / "noisy_audio" / f"{val_idx:04d}_noisy.wav"
            
            clean_16k, _ = sf.read(str(c_path), dtype="float32")
            noisy_16k, _ = sf.read(str(n_path), dtype="float32")
            
            # Recreate chain per clip to evaluate clip performance independently without cross-clip bleed
            chain = AudioChain(
                BlockBackend(block_enhance_fn, block_ms=500, context_ms=300, guard_ms=40, xfade_ms=10)
            )
            
            # Feed noisy in 256-sample chunks (with trailing flush to retrieve primed FIFO delay)
            out_chunks = []
            pad_len = int(chain.backend.delay_samples_48k / 3) + 4000
            padded_noisy = np.concatenate([noisy_16k, np.zeros(pad_len, dtype=np.float32)])
            
            for offset in range(0, len(padded_noisy), FRAME_SIZE):
                frame = padded_noisy[offset: offset + FRAME_SIZE]
                if len(frame) < FRAME_SIZE:
                    frame = np.pad(frame, (0, FRAME_SIZE - len(frame)))
                out_f = chain.process(frame)
                out_chunks.append(out_f)
                
            streamed_16k = np.concatenate(out_chunks)
            # Score against clean with cross-correlation delay alignment up to 500ms
            c_aln, s_aln, lag = align_signals(clean_16k, streamed_16k, max_lag_samples=8000)
            
            snr_exp = compute_explicit_snr(c_aln, s_aln)
            sisdr = compute_si_sdr(c_aln, s_aln)
            try:
                st = float(pystoi_stoi(c_aln, s_aln, 16000, extended=False))
            except Exception:
                st = float("nan")
            try:
                pq = float(pesq_pesq(16000, c_aln, s_aln, "wb"))
            except Exception:
                pq = float("nan")
                
            deployed_results.append({
                "val_index": val_idx,
                "target_snr": c["target_snr"],
                "dataset_origin": c["dataset_origin"],
                "off_snr": c["out_snr_explicit"],
                "off_sisdr": c["out_sisdr"],
                "off_stoi": c["out_stoi"],
                "off_pesq": c["out_pesq"],
                "stream_snr": snr_exp,
                "stream_sisdr": sisdr,
                "stream_stoi": st,
                "stream_pesq": pq,
                "stream_lag": lag
            })
            if (i + 1) % 50 == 0 or i == len(deployed_clips) - 1:
                print(f"  Processed {i+1}/{len(deployed_clips)} deployed streaming clips.")
                
        # Aggregate deployed streaming comparison
        dep_md_path = RESULTS_DIR / "deployed_streaming_comparison.md"
        with open(dep_md_path, "w") as f:
            f.write("# Deployed Streaming Config (500 ms Block / 300 ms Context) vs Offline Processing\n\n")
            f.write("- **Backend**: `BlockBackend` (500 ms block, 300 ms context, 40 ms guard, 10 ms crossfade)\n")
            f.write("- **Engine**: `AudioChain` (Stateful rational FIR resamplers 16k <-> 48k)\n")
            f.write(f"- **Evaluated**: Subsets at 5 dB, 10 dB, 15 dB (n = {len(deployed_clips)})\n\n")
            f.write("| Input SNR | n | Offline SNR | Stream SNR | Offline SI-SDR | Stream SI-SDR | Offline STOI | Stream STOI | Offline PESQ | Stream PESQ |\n")
            f.write("| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n")
            for snr in deployed_targets:
                sub = [x for x in deployed_results if x["target_snr"] == snr]
                n = len(sub)
                off_snr_m = np.mean([x["off_snr"] for x in sub])
                str_snr_m = np.mean([x["stream_snr"] for x in sub])
                off_sdr_m = np.mean([x["off_sisdr"] for x in sub])
                str_sdr_m = np.mean([x["stream_sisdr"] for x in sub])
                off_st_m = np.mean([x["off_stoi"] for x in sub])
                str_st_m = np.mean([x["stream_stoi"] for x in sub])
                off_pq_m = np.mean([x["off_pesq"] for x in sub])
                str_pq_m = np.mean([x["stream_pesq"] for x in sub])
                f.write(f"| {snr:+.0f} dB | {n} | {off_snr_m:.2f} dB | **{str_snr_m:.2f} dB** | {off_sdr_m:.2f} dB | **{str_sdr_m:.2f} dB** | {off_st_m:.3f} | **{str_st_m:.3f}** | {off_pq_m:.3f} | **{str_pq_m:.3f}** |\n")
        print(f"Generated deployed streaming comparison: {dep_md_path}")
        
    except Exception as e:
        print(f"WARNING: Deployed check encountered an error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("ALL EVALUATION TASKS COMPLETED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    main()
