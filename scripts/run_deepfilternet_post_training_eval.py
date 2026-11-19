#!/usr/bin/env python3
"""
DeepFilterNet3 Post-Training Evaluation Suite
Executes complete 14-point evaluation workflow comparing newly fine-tuned DeepFilterNet3
against current production baseline StatefulPolarLSTM, pretrained DeepFilterNet3, and epoch checkpoints.
"""

import os
import sys
import time
import math
import csv
import json
import hashlib
import glob
from pathlib import Path
import numpy as np
import scipy.signal as signal
import scipy.stats as stats
import soundfile as sf
import torch
import torch.nn as nn

# Shim for torchaudio backend compatibility in Python 3.14 / modern torchaudio
import types, torchaudio
if not hasattr(getattr(torchaudio, "backend", None), "common"):
    cm = types.ModuleType("torchaudio.backend.common")
    class AudioMetaData:
        def __init__(self, sr, nf, nc, bps, enc):
            self.sample_rate=sr; self.num_frames=nf
            self.num_channels=nc; self.bits_per_sample=bps; self.encoding=enc
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

# Add workspace path for StatefulPolarLSTM
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.enhance.stateful_polar_lstm import StatefulPolarLSTM_Wrapper

# Set reproducible random seeds
SEED = 26052
np.random.seed(SEED)
torch.manual_seed(SEED)

def calculate_active_speech_level(waveform, sample_rate=16000, frame_length_ms=30):
    """Calculate active speech power using energy thresholding."""
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

def compute_snr(clean, est_or_noise):
    """Compute active speech SNR in dB."""
    cp = calculate_active_speech_level(clean)
    err = est_or_noise if len(est_or_noise) == len(clean) else est_or_noise[:len(clean)]
    npwr = float(np.mean((err - clean) ** 2)) if np.array_equal(clean, err) is False else float(np.mean(err ** 2))
    if cp > 0 and npwr > 0:
        return float(10 * np.log10(cp / npwr))
    return 0.0

def compute_si_sdr(ref, est):
    """Compute Scale-Invariant Signal-to-Distortion Ratio (SI-SDR) in dB."""
    eps = 1e-8
    ref = np.asanyarray(ref, dtype=np.float32)
    est = np.asanyarray(est, dtype=np.float32)
    ref = ref - np.mean(ref)
    est = est - np.mean(est)
    ref_energy = np.sum(ref ** 2)
    optimal_scaling = np.sum(ref * est) / (ref_energy + eps)
    projection = optimal_scaling * ref
    noise = est - projection
    ratio = np.sum(projection ** 2) / (np.sum(noise ** 2) + eps)
    return float(10 * np.log10(ratio + eps))

def compute_all_metrics(clean, est, sr=16000):
    """Compute full metric suite for a single audio pair."""
    clean = np.asanyarray(clean, dtype=np.float32)
    est = np.asanyarray(est, dtype=np.float32)
    
    # Match length
    min_len = min(len(clean), len(est))
    clean = clean[:min_len]
    est = est[:min_len]
    
    rms_clean = float(np.sqrt(np.mean(clean ** 2)))
    rms_est = float(np.sqrt(np.mean(est ** 2)))
    rms_ratio = rms_est / (rms_clean + 1e-8)
    
    clipping_pct = float(np.mean(np.abs(est) >= 0.999) * 100.0)
    has_nan_inf = bool(np.isnan(est).any() or np.isinf(est).any())
    
    # SNR calculation (error power vs active speech power)
    err_power = float(np.mean((est - clean) ** 2))
    active_speech_power = calculate_active_speech_level(clean, sample_rate=sr)
    snr_val = float(10 * np.log10(active_speech_power / (err_power + 1e-12))) if active_speech_power > 0 and err_power > 0 else 0.0
    
    # SI-SDR
    try:
        sisdr_val = compute_si_sdr(clean, est)
    except Exception:
        sisdr_val = np.nan
        
    # STOI
    try:
        stoi_val = float(pystoi_stoi(clean, est, sr, extended=False))
    except Exception:
        stoi_val = np.nan
        
    # PESQ
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
    """Run StatefulPolarLSTM model at native 16 kHz."""
    with torch.no_grad():
        noisy_t = torch.from_numpy(noisy_16k).float().unsqueeze(0)
        out = model(noisy_t)[0]
        return out.squeeze(0).cpu().numpy()[:len(noisy_16k)]

def run_df3_inference(model, df_state, noisy_16k):
    """
    Run DeepFilterNet3 model at native 48 kHz inference rate.
    Resampling procedure:
    1. Resample 16 kHz noisy audio to 48 kHz using scipy.signal.resample_poly (factor 3).
    2. Pass 48 kHz audio through DF3 enhance function.
    3. Resample 48 kHz output back to 16 kHz using scipy.signal.resample_poly (factor 1/3).
    4. Truncate/pad to match exact input length.
    """
    noisy_48k = signal.resample_poly(noisy_16k, 48000, 16000).astype(np.float32)
    t_48k = torch.from_numpy(noisy_48k).unsqueeze(0) # [1, N]
    with torch.no_grad():
        enhanced_48k = enhance(model, df_state, t_48k)
    enhanced_48k_np = enhanced_48k.squeeze().cpu().numpy()
    enhanced_16k = signal.resample_poly(enhanced_48k_np, 16000, 48000).astype(np.float32)
    return enhanced_16k[:len(noisy_16k)]

print("Post-training evaluation framework module initialized.")
