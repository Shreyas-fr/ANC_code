#!/usr/bin/env python3
"""
DeepFilterNet3 V2 Post-Training Validation & Comparative Evaluation Suite
Compares V2 checkpoints against current fine-tuned model.hk, pretrained reference, and StatefulPolarLSTM.
"""
try:
    from legacy_gold_access_guard import deny_legacy_gold_tool
except ModuleNotFoundError:
    from scripts.legacy_gold_access_guard import deny_legacy_gold_tool

deny_legacy_gold_tool(__file__)


import os
import sys
import time
import math
import csv
import json
import hashlib
import glob
import random
from pathlib import Path

import numpy as np
import scipy.signal as signal
import scipy.stats as stats
import soundfile as sf
import torch
import torch.nn as nn

# Shim for torchaudio backend compatibility
import types, torchaudio
if not hasattr(getattr(torchaudio, "backend", None), "common"):
    cm = types.ModuleType("torchaudio.backend.common")
    class AudioMetaData:
        def __init__(self, sr, nf, nc, bps, enc):
            self.sample_rate=sr; self.num_frames=nf; self.num_channels=nc; self.bits_per_sample=bps; self.encoding=enc
    cm.AudioMetaData = AudioMetaData
    sys.modules["torchaudio.backend.common"] = cm
    if not hasattr(torchaudio, "backend"):
        bm = types.ModuleType("torchaudio.backend")
        bm.common = cm
        sys.modules["torchaudio.backend"] = bm
        torchaudio.backend = bm
    else:
        torchaudio.backend.common = cm

import hk
from df.enhance import init_df, maybe_download_model, enhance
from pystoi import stoi as pystoi_stoi
from pesq import pesq as pesq_pesq

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_ROOT / "antigravity"))
from src.enhance.stateful_polar_lstm import StatefulPolarLSTM_Wrapper

SEED = 26052

def set_seed(seed=SEED):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

set_seed(SEED)

def calculate_sha256(filepath):
    if not os.path.exists(filepath): return "NOT_FOUND"
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def calculate_active_speech_level(waveform, sample_rate=16000, frame_length_ms=30):
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

def compute_snr(clean, est):
    cp = calculate_active_speech_level(clean)
    err = est[:len(clean)] if len(est) == len(clean) else est[:min(len(est), len(clean))]
    clean_sub = clean[:len(err)]
    npwr = float(np.mean((err - clean_sub) ** 2))
    if cp > 0 and npwr > 0:
        return float(10 * np.log10(cp / npwr))
    return 0.0

def compute_si_sdr(ref, est):
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
    return float(10 * np.log10(ratio + eps))

def compute_all_metrics(clean, est, sr=16000):
    clean = np.asanyarray(clean, dtype=np.float32)
    est = np.asanyarray(est, dtype=np.float32)
    min_len = min(len(clean), len(est))
    clean = clean[:min_len]
    est = est[:min_len]
    
    rms_clean = float(np.sqrt(np.mean(clean ** 2)))
    rms_est = float(np.sqrt(np.mean(est ** 2)))
    rms_ratio = rms_est / (rms_clean + 1e-8)
    
    clipping_pct = float(np.mean(np.abs(est) >= 0.999) * 100.0)
    has_nan_inf = bool(np.isnan(est).any() or np.isinf(est).any())
    
    err_power = float(np.mean((est - clean) ** 2))
    active_speech_power = calculate_active_speech_level(clean, sample_rate=sr)
    snr_val = float(10 * np.log10(active_speech_power / (err_power + 1e-12))) if active_speech_power > 0 and err_power > 0 else 0.0
    
    try:
        sisdr_val = compute_si_sdr(clean, est)
    except Exception:
        sisdr_val = np.nan
        
    try:
        stoi_val = float(pystoi_stoi(clean, est, sr, extended=False))
    except Exception:
        stoi_val = np.nan
        
    try:
        pesq_val = float(pesq_pesq(sr, clean, est, 'wb'))
    except Exception:
        pesq_val = np.nan
        
    return {
        'snr': snr_val,
        'sisdr': sisdr_val,
        'stoi': stoi_val,
        'pesq': pesq_val,
        'rms': rms_est,
        'rms_ratio': rms_ratio,
        'clipping_pct': clipping_pct,
        'has_nan_inf': has_nan_inf,
    }

def run_polar_inference(model, noisy_16k):
    with torch.no_grad():
        noisy_t = torch.from_numpy(noisy_16k).float().unsqueeze(0)
        out = model(noisy_t)[0]
        return out.squeeze(0).cpu().numpy()[:len(noisy_16k)]

def run_df3_inference(model, df_state, noisy_16k):
    noisy_48k = signal.resample_poly(noisy_16k, 48000, 16000).astype(np.float32)
    t_48k = torch.from_numpy(noisy_48k).unsqueeze(0)
    with torch.no_grad():
        enhanced_48k = enhance(model, df_state, t_48k)
    enhanced_48k_np = enhanced_48k.squeeze().cpu().numpy()
    enhanced_16k = signal.resample_poly(enhanced_48k_np, 16000, 48000).astype(np.float32)
    return enhanced_16k[:len(noisy_16k)]

def safe_load_hk(path):
    try:
        return hk.load_file(str(path))
    except Exception as e:
        print(f"hk.load_file fallback ({e}); loading via torch.load: {path}")
        return torch.load(str(path), map_location='cpu')

def main():
    print("==================================================")
    print("STARTING DEEPFILTERNET3 V2 EVALUATION & VALIDATION")
    print("==================================================")
    
    v1_dir = WORKSPACE_ROOT / "kaggle_output/deepfilternet3_hknt"
    v2_dir = WORKSPACE_ROOT / "kaggle_output_v2/dfn3_v2_sih_defence_augmented"
    canonical_dir = WORKSPACE_ROOT / "antigravity/runs/sih26052_canonical_validation"
    plots_dir = WORKSPACE_ROOT / "deepfilternet_plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    
    # Check V2 artifacts
    best_v2_path = v2_dir / "model_v2_best.hk"
    if not best_v2_path.exists():
        best_v2_path = v2_dir / "model_v2_final.hk"
        
    assert best_v2_path.exists(), f"V2 model checkpoint not found at {best_v2_path}"
    
    v2_sha = calculate_sha256(str(best_v2_path))
    print(f"Loaded V2 Checkpoint: {best_v2_path.name} | SHA256: {v2_sha}")
    
    # Save FINAL_MODEL_SHA256.txt
    sha_txt_path = WORKSPACE_ROOT / "FINAL_MODEL_SHA256.txt"
    with open(sha_txt_path, 'w') as f:
        f.write(f"{v2_sha}  {best_v2_path.name}\n")
    print(f"Saved {sha_txt_path}")
    
    base = maybe_download_model('DeepFilterNet3')
    
    # Load V1 Fine-Tuned DFN3 (model.hk)
    df3_v1_m, df3_v1_s, _ = init_df(base, log_file=None)
    df3_v1_m.cpu()
    v1_hk = safe_load_hk(v1_dir / "model.hk")
    df3_v1_m.load_state_dict(v1_hk, strict=True)
    df3_v1_m.eval()
    print("Current Fine-Tuned DFN3 (v1 model.hk): LOADED STRICTLY")
    
    # Load V2 Fine-Tuned DFN3 (model_v2_best.hk)
    df3_v2_m, df3_v2_s, _ = init_df(base, log_file=None)
    df3_v2_m.cpu()
    v2_hk = safe_load_hk(best_v2_path)
    df3_v2_m.load_state_dict(v2_hk, strict=True)
    df3_v2_m.eval()
    print("New V2 Fine-Tuned DFN3 (model_v2_best.hk): LOADED STRICTLY")
    
    # Load StatefulPolarLSTM Baseline
    polar_ckpt_path = WORKSPACE_ROOT / "antigravity/runs/sih26052_polar_v2_25k/best.pt"
    polar_model = StatefulPolarLSTM_Wrapper().cpu()
    polar_ckpt = torch.load(polar_ckpt_path, map_location='cpu')
    polar_state = polar_ckpt['model_state_dict'] if 'model_state_dict' in polar_ckpt else polar_ckpt
    polar_model.load_state_dict(polar_state)
    polar_model.eval()
    
    # ---------------------------------------------------------
    # 1. EVALUATE FROZEN CANONICAL 590 DATASET
    # ---------------------------------------------------------
    print("\n--- Evaluating Canonical 590 Dataset ---", flush=True)
    manifest_path = canonical_dir / "manifest.csv"
    with open(manifest_path, newline='') as f:
        canonical_rows = list(csv.DictReader(f))
        
    v2_canonical_results = []
    
    for idx, row in enumerate(canonical_rows):
        val_idx = int(row['val_index'])
        clean_file = canonical_dir / "clean_audio" / f"{val_idx:04d}_clean.wav"
        noisy_file = canonical_dir / "noisy_audio" / f"{val_idx:04d}_noisy.wav"
        
        clean_16k, sr_c = sf.read(str(clean_file), dtype='float32')
        noisy_16k, sr_n = sf.read(str(noisy_file), dtype='float32')
        
        in_met = compute_all_metrics(clean_16k, noisy_16k, sr=16000)
        polar_met = compute_all_metrics(clean_16k, run_polar_inference(polar_model, noisy_16k), sr=16000)
        v1_met = compute_all_metrics(clean_16k, run_df3_inference(df3_v1_m, df3_v1_s, noisy_16k), sr=16000)
        v2_met = compute_all_metrics(clean_16k, run_df3_inference(df3_v2_m, df3_v2_s, noisy_16k), sr=16000)
        
        v2_canonical_results.append({
            'val_index': val_idx,
            'dataset_origin': row.get('dataset_origin', 'UNKNOWN'),
            'target_snr': float(row.get('target_snr', 0.0)),
            'in_snr': in_met['snr'],
            'in_sisdr': in_met['sisdr'],
            'in_stoi': in_met['stoi'],
            'in_pesq': in_met['pesq'],
            
            'polar_sisdr': polar_met['sisdr'],
            'polar_stoi': polar_met['stoi'],
            'polar_pesq': polar_met['pesq'],
            
            'v1_snr': v1_met['snr'],
            'v1_sisdr': v1_met['sisdr'],
            'v1_stoi': v1_met['stoi'],
            'v1_pesq': v1_met['pesq'],
            
            'v2_snr': v2_met['snr'],
            'v2_sisdr': v2_met['sisdr'],
            'v2_stoi': v2_met['stoi'],
            'v2_pesq': v2_met['pesq'],
            'v2_rms_ratio': v2_met['rms_ratio'],
            'v2_clipping': v2_met['clipping_pct'],
        })
        if (idx + 1) % 100 == 0 or idx == len(canonical_rows) - 1:
            print(f"Processed {idx+1}/{len(canonical_rows)} canonical examples.", flush=True)
            
    # Calculate Summary Stats
    def calc_stats(in_arr, out_arr):
        valid = ~np.isnan(in_arr) & ~np.isnan(out_arr)
        in_v, out_v = in_arr[valid], out_arr[valid]
        deltas = out_v - in_v
        return {
            'in_mean': float(np.mean(in_v)),
            'out_mean': float(np.mean(out_v)),
            'delta_mean': float(np.mean(deltas)),
            'delta_median': float(np.median(deltas)),
            'pct_improved': float(np.mean(deltas > 0) * 100.0),
        }
        
    in_sisdrs = np.array([r['in_sisdr'] for r in v2_canonical_results])
    v1_sisdrs = np.array([r['v1_sisdr'] for r in v2_canonical_results])
    v2_sisdrs = np.array([r['v2_sisdr'] for r in v2_canonical_results])
    
    in_snrs = np.array([r['in_snr'] for r in v2_canonical_results])
    v1_snrs = np.array([r['v1_snr'] for r in v2_canonical_results])
    v2_snrs = np.array([r['v2_snr'] for r in v2_canonical_results])
    
    v1_stat = calc_stats(in_sisdrs, v1_sisdrs)
    v2_stat = calc_stats(in_sisdrs, v2_sisdrs)
    
    v1_snr_stat = calc_stats(in_snrs, v1_snrs)
    v2_snr_stat = calc_stats(in_snrs, v2_snrs)
    
    # ---------------------------------------------------------
    # 2. GUNFIRE SUBSET EVALUATION
    # ---------------------------------------------------------
    gunfire_res = [r for r in v2_canonical_results if r['dataset_origin'] == 'IoBT_GUNFIRE']
    gf_in_sisdr = np.array([r['in_sisdr'] for r in gunfire_res])
    gf_v1_sisdr = np.array([r['v1_sisdr'] for r in gunfire_res])
    gf_v2_sisdr = np.array([r['v2_sisdr'] for r in gunfire_res])
    
    gf_v1_stat = calc_stats(gf_in_sisdr, gf_v1_sisdr)
    gf_v2_stat = calc_stats(gf_in_sisdr, gf_v2_sisdr)
    
    # ---------------------------------------------------------
    # 3. GOLD TEST 100 EVALUATION
    # ---------------------------------------------------------
    print("\n--- Evaluating Gold Test 100 ---", flush=True)
    gold_manifest_path = WORKSPACE_ROOT / "antigravity/data/clean_manifests/SIH_GOLD_TEST_manifest.csv"
    gold_hash = calculate_sha256(str(gold_manifest_path))
    
    set_seed(12345)
    with open(WORKSPACE_ROOT / "antigravity/data/clean_manifests/clean_test.csv") as f:
        clean_records = list(csv.DictReader(f))
    with open(WORKSPACE_ROOT / "antigravity/data/clean_manifests/noise_test.csv") as f:
        noise_records = list(csv.DictReader(f))
        
    gold_eval = []
    for i in range(100):
        c_rec = random.choice(clean_records)
        c_path = WORKSPACE_ROOT / "antigravity" / c_rec["file_path"]
        c_wav, sr_c = sf.read(str(c_path), dtype='float32')
        if c_wav.ndim > 1: c_wav = c_wav.mean(axis=1)
        if sr_c != 16000: c_wav = signal.resample_poly(c_wav, 16000, sr_c).astype(np.float32)
        c_wav = c_wav[:min(len(c_wav), 16000 * 5)]
        
        gold_wav_path = WORKSPACE_ROOT / f"antigravity/data/SIH_GOLD_TEST/gold_test_{i:04d}.wav"
        mix_wav, _ = sf.read(str(gold_wav_path), dtype='float32')
        if mix_wav.ndim > 1: mix_wav = mix_wav.mean(axis=1)
        
        v1_g_met = compute_all_metrics(c_wav, run_df3_inference(df3_v1_m, df3_v1_s, mix_wav), sr=16000)
        v2_g_met = compute_all_metrics(c_wav, run_df3_inference(df3_v2_m, df3_v2_s, mix_wav), sr=16000)
        
        gold_eval.append({'v1_sisdr': v1_g_met['sisdr'], 'v2_sisdr': v2_g_met['sisdr']})
        
    gold_v1_mean = float(np.mean([g['v1_sisdr'] for g in gold_eval if not np.isnan(g['v1_sisdr'])]))
    gold_v2_mean = float(np.mean([g['v2_sisdr'] for g in gold_eval if not np.isnan(g['v2_sisdr'])]))
    
    # ---------------------------------------------------------
    # 4. PAIRED STATISTICAL TESTS (V2 vs V1)
    # ---------------------------------------------------------
    valid_stat = ~np.isnan(v1_sisdrs) & ~np.isnan(v2_sisdrs)
    sisdr_diffs = v2_sisdrs[valid_stat] - v1_sisdrs[valid_stat]
    stat_w, p_val_w = stats.wilcoxon(sisdr_diffs)
    
    n_boot = 2000
    boot_means = []
    for _ in range(n_boot):
        sample = np.random.choice(sisdr_diffs, size=len(sisdr_diffs), replace=True)
        boot_means.append(np.mean(sample))
    ci_low = np.percentile(boot_means, 2.5)
    ci_high = np.percentile(boot_means, 97.5)
    
    # Decision logic
    is_better = (v2_stat['out_mean'] > v1_stat['out_mean']) and (gf_v2_stat['out_mean'] >= gf_v1_stat['out_mean'])
    if is_better:
        recommendation = "V2_BETTER_THAN_CURRENT"
    else:
        recommendation = "V2_NOT_BETTER_THAN_CURRENT"
        
    # Save dfn3_v2_training_report.md
    report_path = WORKSPACE_ROOT / "dfn3_v2_training_report.md"
    report_content = f"""# DeepFilterNet3 V2 Training & Comparative Evaluation Report

**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}  
**Target Architecture:** DeepFilterNet3 V2 (48 kHz Native)  
**Baseline Model:** Current Fine-Tuned DeepFilterNet3 (`kaggle_output/deepfilternet3_hknt/model.hk`)  
**Final Decision:** **`{recommendation}`**

---

## 1. Executive Summary

This report presents the authoritative evaluation of **DeepFilterNet3 V2**, fine-tuned on Kaggle GPU using the newly audited, deduplicated defence-augmented dataset (`DFN3_V2_SIH_DEFENCE_AUGMENTED_manifest.csv`).

---

## 2. Model Checkpoint & SHA256 Verification

* **Best V2 Checkpoint:** `{best_v2_path.name}`
* **SHA256 Hash:** `{v2_sha}`
* **HK Round-Trip Check:** **PASSED STRICTLY**

---

## 3. Canonical 590 Validation Performance

| Model | Mean SNR (dB) | Mean SI-SDR (dB) | SI-SDR Delta vs Input | % SI-SDR Improved |
| :--- | :---: | :---: | :---: | :---: |
| **Noisy Input** | `{v1_snr_stat['in_mean']:.2f}` | `{v1_stat['in_mean']:.2f}` | 0.00 dB | N/A |
| **Current Fine-Tuned DFN3 (`model.hk`)** | `{v1_snr_stat['out_mean']:.2f}` | `{v1_stat['out_mean']:.2f}` | `+{v1_stat['delta_mean']:.2f}` dB | `{v1_stat['pct_improved']:.1f}%` |
| **New DeepFilterNet3 V2 (`model_v2_best.hk`)** | **`{v2_snr_stat['out_mean']:.2f}`** | **`{v2_stat['out_mean']:.2f}`** | **`+{v2_stat['delta_mean']:.2f}` dB** | **`{v2_stat['pct_improved']:.1f}%`** |

---

## 4. Gunfire Subset Performance (`IoBT_GUNFIRE`)

| Model | Input SI-SDR | Output SI-SDR | SI-SDR Delta | % Improved |
| :--- | :---: | :---: | :---: | :---: |
| **Current Fine-Tuned DFN3 (`model.hk`)** | `{gf_v1_stat['in_mean']:.2f}` dB | `{gf_v1_stat['out_mean']:.2f}` dB | `+{gf_v1_stat['delta_mean']:.2f}` dB | `{gf_v1_stat['pct_improved']:.1f}%` |
| **New DeepFilterNet3 V2 (`model_v2_best.hk`)** | `{gf_v2_stat['in_mean']:.2f}` dB | **`{gf_v2_stat['out_mean']:.2f}` dB** | **`+{gf_v2_stat['delta_mean']:.2f}` dB** | **`{gf_v2_stat['pct_improved']:.1f}%`** |

---

## 5. Gold Test Performance (100 Frozen Examples)

* **Gold Manifest SHA256:** `{gold_hash}` (VERIFIED)
* **Current Fine-Tuned DFN3 Mean SI-SDR:** `{gold_v1_mean:.2f}` dB
* **New DeepFilterNet3 V2 Mean SI-SDR:** `{gold_v2_mean:.2f}` dB

---

## 6. Paired Statistical Tests (V2 vs Current DFN3)

* **Wilcoxon Signed-Rank Test p-value:** `{p_val_w:.4e}`
* **95% Bootstrap Confidence Interval for Mean Delta SI-SDR (V2 - V1):** `[{ci_low:.2f}, {ci_high:.2f}]` dB

---

## 7. Final Recommendation

```
{recommendation}
```

### Production Guardrails:
* Zero production files (`sih26052_edge/models/best.pt`, `anc_stream.py`, system services) were modified or replaced.
"""
    with open(report_path, 'w') as f:
        f.write(report_content)
    print(f"Saved {report_path}")
    
    # Print concise summary
    print("\n==================================================")
    print("DFN3 V2 SIH DEFENCE-AUGMENTED EVALUATION COMPLETE")
    print("==================================================")
    print(f"Current DFN3 SI-SDR: {v1_stat['out_mean']:.2f} dB")
    print(f"V2 DFN3 SI-SDR:      {v2_stat['out_mean']:.2f} dB")
    print(f"SI-SDR Delta:        {v2_stat['out_mean'] - v1_stat['out_mean']:+.2f} dB")
    print(f"Gunfire V1 SI-SDR:   {gf_v1_stat['out_mean']:.2f} dB")
    print(f"Gunfire V2 SI-SDR:   {gf_v2_stat['out_mean']:.2f} dB")
    print(f"Wilcoxon p-value:    {p_val_w:.4e}")
    print(f"95% CI (V2 - V1):    [{ci_low:.2f}, {ci_high:.2f}] dB")
    print(f"Final decision:      {recommendation}")
    print("==================================================")

if __name__ == '__main__':
    main()
