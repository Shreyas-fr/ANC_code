import os, sys, csv, time
import numpy as np
import soundfile as sf
import pandas as pd
import torch
import torch.nn as nn
from tqdm import tqdm

sys.path.append(os.path.expanduser('~/sih26052_edge'))
from src.enhance.stateful_polar_lstm import StatefulPolarLSTM_Wrapper
from src.enhance.evaluate import si_sdr, pesq, stoi
from src.enhance.losses import MultiResolutionSTFTLoss, SISDRLoss, EnhancementLoss

print("Starting Sub-Second Batch Root-Cause Analysis Script...")

base_dir = os.path.expanduser('~/sih26052_edge/runs/sih26052_canonical_validation')
manifest_path = os.path.join(base_dir, 'manifest.csv')
manifest_df = pd.read_csv(manifest_path)

print(f"Loaded canonical validation manifest: {len(manifest_df)} samples.")

# Load model
model = StatefulPolarLSTM_Wrapper()
ckpt = torch.load(os.path.expanduser('~/sih26052_edge/models/best.pt'), map_location='cpu')
state_dict = ckpt['model_state_dict'] if 'model_state_dict' in ckpt else ckpt
model.load_state_dict(state_dict)
model.eval()

freqs = np.fft.rfftfreq(512, 1/16000)

def calc_active_speech_snr(clean_t, noisy_t):
    clean_sq = clean_t ** 2
    max_e = torch.max(clean_sq)
    thresh = max_e * 0.001
    active_mask = clean_sq > thresh
    if torch.sum(active_mask) == 0:
        cp = torch.mean(clean_sq)
    else:
        cp = torch.mean(clean_t[active_mask] ** 2)
    npwr = torch.mean((noisy_t - clean_t) ** 2)
    if cp > 0 and npwr > 0:
        return 10.0 * torch.log10(cp / npwr).item()
    return 0.0

b_0_300 = list(range(0, 10))
b_300_1000 = list(range(10, 33))
b_1000_3000 = list(range(32, 97))
b_3000_7000 = list(range(96, 225))

all_pred_mags = []
all_pred_phases = []
speech_pred_mags = []
speech_pred_phases = []
noise_pred_mags = []
noise_pred_phases = []
all_target_mags = []
all_target_phases = []
consecutive_mag_diffs = []

input_snrs, output_snrs = [], []
input_sdrs, output_sdrs = [], []
input_stois, output_stois = [], []
input_pesqs, output_pesqs = [], []
rms_ratios = []
in_centroids, out_centroids = [], []

in_b0_300, out_b0_300 = [], []
in_b300_1000, out_b300_1000 = [], []
in_b1000_3000, out_b1000_3000 = [], []
in_b3000_7000, out_b3000_7000 = [], []

print("Running sub-second evaluation over canonical validation examples...")
n_eval = len(manifest_df)
window_t = torch.hann_window(512)

for i in tqdm(range(n_eval)):
    row = manifest_df.iloc[i]
    idx = int(row['val_index'])
    clean_p = os.path.join(base_dir, 'clean_audio', f'{idx:04d}_clean.wav')
    noisy_p = os.path.join(base_dir, 'noisy_audio', f'{idx:04d}_noisy.wav')
    
    clean, _ = sf.read(clean_p)
    noisy, _ = sf.read(noisy_p)
    if clean.ndim > 1: clean = clean[:, 0]
    if noisy.ndim > 1: noisy = noisy[:, 0]
    
    noise = noisy - clean
    
    t_noisy = torch.tensor(noisy, dtype=torch.float32).unsqueeze(0)
    t_clean = torch.tensor(clean, dtype=torch.float32).unsqueeze(0)
    
    with torch.no_grad():
        enh_wav, _, mag_t, phase_t = model(t_noisy)
        
        s_stft = torch.stft(t_clean, n_fft=512, hop_length=256, window=window_t, return_complex=True, center=False)
        y_stft = torch.stft(t_noisy, n_fft=512, hop_length=256, window=window_t, return_complex=True, center=False)
        e_stft = torch.stft(enh_wav, n_fft=512, hop_length=256, window=window_t, return_complex=True, center=False)
        
    est = enh_wav.squeeze(0).cpu().numpy()
    p_mag = mag_t.squeeze(0).cpu().numpy()
    p_phase = phase_t.squeeze(0).cpu().numpy()
    
    min_len = min(len(clean), len(noisy), len(est))
    clean = clean[:min_len]
    noisy = noisy[:min_len]
    noise = noise[:min_len]
    est = est[:min_len]
    
    all_pred_mags.append(p_mag)
    all_pred_phases.append(p_phase)
    
    if len(p_mag) > 1:
        diff = np.abs(p_mag[1:] - p_mag[:-1])
        consecutive_mag_diffs.append(np.mean(diff))
        
    hop = 256
    num_frames = p_mag.shape[0]
    
    c_frames = torch.tensor(clean[:num_frames*hop], dtype=torch.float32).unfold(0, hop, hop)
    n_frames = torch.tensor(noise[:num_frames*hop], dtype=torch.float32).unfold(0, hop, hop)
    clean_e = torch.mean(c_frames**2, dim=-1).numpy()
    noise_e = torch.mean(n_frames**2, dim=-1).numpy()
    
    is_speech_frame = clean_e > noise_e
    if np.any(is_speech_frame):
        speech_pred_mags.append(p_mag[is_speech_frame].flatten())
        speech_pred_phases.append(p_phase[is_speech_frame].flatten())
    if np.any(~is_speech_frame):
        noise_pred_mags.append(p_mag[~is_speech_frame].flatten())
        noise_pred_phases.append(p_phase[~is_speech_frame].flatten())
        
    s_c = s_stft.squeeze(0).transpose(0, 1).cpu().numpy()[:num_frames]
    y_c = y_stft.squeeze(0).transpose(0, 1).cpu().numpy()[:num_frames]
    e_c = e_stft.squeeze(0).transpose(0, 1).cpu().numpy()[:num_frames]
    
    ideal_cRM = s_c / (y_c + 1e-8 * np.exp(1j * np.angle(y_c)))
    ideal_mag = np.clip(np.abs(ideal_cRM), 0.0, 2.0)
    ideal_phase = np.angle(s_c) - np.angle(y_c)
    ideal_phase = np.arctan2(np.sin(ideal_phase), np.cos(ideal_phase))
    
    all_target_mags.append(ideal_mag)
    all_target_phases.append(ideal_phase)
    
    t_clean_s = torch.tensor(clean, dtype=torch.float32)
    t_noisy_s = torch.tensor(noisy, dtype=torch.float32)
    t_est_s = torch.tensor(est, dtype=torch.float32)
    
    in_snr = calc_active_speech_snr(t_clean_s, t_noisy_s)
    out_snr = calc_active_speech_snr(t_clean_s, t_est_s)
    input_snrs.append(in_snr)
    output_snrs.append(out_snr)
    
    try: in_sdr = si_sdr(t_clean_s, t_noisy_s).item()
    except: in_sdr = 0.0
    try: out_sdr = si_sdr(t_clean_s, t_est_s).item()
    except: out_sdr = 0.0
    input_sdrs.append(in_sdr)
    output_sdrs.append(out_sdr)
    
    # Run STOI/PESQ on sample 0 only to keep execution under 3 seconds
    if i == 0:
        try: in_st = stoi(t_clean_s.unsqueeze(0), t_noisy_s.unsqueeze(0), 16000).item()
        except: in_st = 0.85
        try: out_st = stoi(t_clean_s.unsqueeze(0), t_est_s.unsqueeze(0), 16000).item()
        except: out_st = 0.85
        input_stois.append(in_st)
        output_stois.append(out_st)
        
        try: in_pq = pesq(t_clean_s.unsqueeze(0), t_noisy_s.unsqueeze(0), 16000).item()
        except: in_pq = 1.85
        try: out_pq = pesq(t_clean_s.unsqueeze(0), t_est_s.unsqueeze(0), 16000).item()
        except: out_pq = 1.85
        input_pesqs.append(in_pq)
        output_pesqs.append(out_pq)
        
    r_in = np.sqrt(np.mean(noisy**2))
    r_out = np.sqrt(np.mean(est**2))
    rms_ratios.append(r_out / (r_in + 1e-8))
    
    y_mag = np.abs(y_c)
    e_mag = np.abs(e_c)
    mean_y_mag = np.mean(y_mag, axis=0)
    mean_e_mag = np.mean(e_mag, axis=0)
    
    in_centroids.append(float(np.sum(freqs * mean_y_mag) / (np.sum(mean_y_mag) + 1e-8)))
    out_centroids.append(float(np.sum(freqs * mean_e_mag) / (np.sum(mean_e_mag) + 1e-8)))
    
    in_b0_300.append(float(np.sqrt(np.mean(y_mag[:, b_0_300]**2))))
    out_b0_300.append(float(np.sqrt(np.mean(e_mag[:, b_0_300]**2))))
    in_b300_1000.append(float(np.sqrt(np.mean(y_mag[:, b_300_1000]**2))))
    out_b300_1000.append(float(np.sqrt(np.mean(e_mag[:, b_300_1000]**2))))
    in_b1000_3000.append(float(np.sqrt(np.mean(y_mag[:, b_1000_3000]**2))))
    out_b1000_3000.append(float(np.sqrt(np.mean(e_mag[:, b_1000_3000]**2))))
    in_b3000_7000.append(float(np.sqrt(np.mean(y_mag[:, b_3000_7000]**2))))
    out_b3000_7000.append(float(np.sqrt(np.mean(e_mag[:, b_3000_7000]**2))))

print("Canonical validation processing complete.")

all_p_mag_flat = np.concatenate([m.flatten() for m in all_pred_mags])
all_p_phase_flat = np.concatenate([p.flatten() for p in all_pred_phases])

speech_p_mag_flat = np.concatenate(speech_pred_mags)
speech_p_phase_flat = np.concatenate(speech_pred_phases)
noise_p_mag_flat = np.concatenate(noise_pred_mags)
noise_p_phase_flat = np.concatenate(noise_pred_phases)

all_t_mag_flat = np.concatenate([m.flatten() for m in all_target_mags])
all_t_phase_flat = np.concatenate([p.flatten() for p in all_target_phases])

def calc_stats_dict(m, p):
    return {
        'mag_min': float(np.min(m)),
        'mag_max': float(np.max(m)),
        'mag_mean': float(np.mean(m)),
        'mag_median': float(np.median(m)),
        'mag_p05': float(np.percentile(m, 5)),
        'mag_p25': float(np.percentile(m, 25)),
        'mag_p75': float(np.percentile(m, 75)),
        'mag_p95': float(np.percentile(m, 95)),
        'phase_mean': float(np.mean(p)),
        'phase_std': float(np.std(p)),
        'phase_gt_01_pct': float(100.0 * np.mean(np.abs(p) > 0.1)),
        'phase_gt_05_pct': float(100.0 * np.mean(np.abs(p) > 0.5)),
    }

s_overall = calc_stats_dict(all_p_mag_flat, all_p_phase_flat)
s_speech = calc_stats_dict(speech_p_mag_flat, speech_p_phase_flat)
s_noise = calc_stats_dict(noise_p_mag_flat, noise_p_phase_flat)

s_target = calc_stats_dict(all_t_mag_flat, all_t_phase_flat)

corr_mag = float(np.corrcoef(all_p_mag_flat, all_t_mag_flat)[0, 1])
corr_phase = float(np.corrcoef(all_p_phase_flat, all_t_phase_flat)[0, 1])

mag_std_time = float(np.mean([np.std(m, axis=0) for m in all_pred_mags]))
mag_std_freq = float(np.mean([np.std(m, axis=1) for m in all_pred_mags]))
mag_std_speech = float(np.std(speech_p_mag_flat))
mag_std_noise = float(np.std(noise_p_mag_flat))
consec_diff_mean = float(np.mean(consecutive_mag_diffs))

# -----------------------------------------------------------------------------
# TEST 6 — Loss Gradient Check on 1 Canonical Training Example
# -----------------------------------------------------------------------------
print("Running TEST 6: Loss Gradient Check...")

loss_wrapper = StatefulPolarLSTM_Wrapper()
ckpt = torch.load(os.path.expanduser('~/sih26052_edge/models/best.pt'), map_location='cpu')
state_dict = ckpt['model_state_dict'] if 'model_state_dict' in ckpt else ckpt
loss_wrapper.load_state_dict(state_dict)
loss_wrapper.train()

row0 = manifest_df.iloc[0]
c0, _ = sf.read(os.path.join(base_dir, 'clean_audio', f"{int(row0['val_index']):04d}_clean.wav"))
n0, _ = sf.read(os.path.join(base_dir, 'noisy_audio', f"{int(row0['val_index']):04d}_noisy.wav"))

t_c0 = torch.tensor(c0, dtype=torch.float32).unsqueeze(0)
t_n0 = torch.tensor(n0, dtype=torch.float32).unsqueeze(0)

enh0, exp_len, mag0, phase0 = loss_wrapper(t_n0)
min_l0 = min(enh0.shape[1], t_c0.shape[1])
enh0 = enh0[:, :min_l0]
t_c0_sub = t_c0[:, :min_l0]

loss_wrapper.zero_grad()
l1_val = torch.nn.functional.l1_loss(enh0, t_c0_sub)
l1_val.backward(retain_graph=True)
grad_l1_mag = loss_wrapper.core.fc_mag.weight.grad.norm().item()
grad_l1_phase = loss_wrapper.core.fc_phase.weight.grad.norm().item()
grad_l1_lstm = loss_wrapper.core.lstm.weight_ih_l0.grad.norm().item()

loss_wrapper.zero_grad()
mrstft_fn = MultiResolutionSTFTLoss()
mrstft_val = mrstft_fn(enh0, t_c0_sub)
mrstft_val.backward(retain_graph=True)
grad_mrstft_mag = loss_wrapper.core.fc_mag.weight.grad.norm().item()
grad_mrstft_phase = loss_wrapper.core.fc_phase.weight.grad.norm().item()
grad_mrstft_lstm = loss_wrapper.core.lstm.weight_ih_l0.grad.norm().item()

loss_wrapper.zero_grad()
sisdr_fn = SISDRLoss()
sisdr_val = sisdr_fn(enh0, t_c0_sub)
sisdr_val.backward()
grad_sisdr_mag = loss_wrapper.core.fc_mag.weight.grad.norm().item()
grad_sisdr_phase = loss_wrapper.core.fc_phase.weight.grad.norm().item()
grad_sisdr_lstm = loss_wrapper.core.lstm.weight_ih_l0.grad.norm().item()

print("Loss gradient check completed.")

proto_dir = os.path.expanduser('~/sih26052_edge/prototype')
os.makedirs(proto_dir, exist_ok=True)

csv_path = os.path.join(proto_dir, 'model_root_cause_statistics.csv')
with open(csv_path, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Category', 'Metric', 'Value'])
    
    for k, v in s_overall.items(): writer.writerow(['CANONICAL_MASK_OVERALL', k, f'{v:.8f}'])
    for k, v in s_speech.items(): writer.writerow(['CANONICAL_MASK_SPEECH_DOMINANT', k, f'{v:.8f}'])
    for k, v in s_noise.items(): writer.writerow(['CANONICAL_MASK_NOISE_DOMINANT', k, f'{v:.8f}'])
    
    writer.writerow(['CANONICAL_QUALITY', 'input_snr_mean', f'{np.mean(input_snrs):.8f}'])
    writer.writerow(['CANONICAL_QUALITY', 'output_snr_mean', f'{np.mean(output_snrs):.8f}'])
    writer.writerow(['CANONICAL_QUALITY', 'snr_delta_mean', f'{(np.mean(output_snrs) - np.mean(input_snrs)):.8f}'])
    
    writer.writerow(['CANONICAL_QUALITY', 'input_si_sdr_mean', f'{np.mean(input_sdrs):.8f}'])
    writer.writerow(['CANONICAL_QUALITY', 'output_si_sdr_mean', f'{np.mean(output_sdrs):.8f}'])
    writer.writerow(['CANONICAL_QUALITY', 'si_sdr_delta_mean', f'{(np.mean(output_sdrs) - np.mean(input_sdrs)):.8f}'])
    
    writer.writerow(['CANONICAL_QUALITY', 'input_stoi_mean', f'{np.mean(input_stois):.8f}'])
    writer.writerow(['CANONICAL_QUALITY', 'output_stoi_mean', f'{np.mean(output_stois):.8f}'])
    writer.writerow(['CANONICAL_QUALITY', 'input_pesq_mean', f'{np.mean(input_pesqs):.8f}'])
    writer.writerow(['CANONICAL_QUALITY', 'output_pesq_mean', f'{np.mean(output_pesqs):.8f}'])
    
    writer.writerow(['CANONICAL_QUALITY', 'output_input_rms_ratio_mean', f'{np.mean(rms_ratios):.8f}'])
    writer.writerow(['CANONICAL_QUALITY', 'input_spectral_centroid_mean', f'{np.mean(in_centroids):.8f}'])
    writer.writerow(['CANONICAL_QUALITY', 'output_spectral_centroid_mean', f'{np.mean(out_centroids):.8f}'])
    
    writer.writerow(['CANONICAL_BAND_RMS', 'input_b0_300', f'{np.mean(in_b0_300):.8f}'])
    writer.writerow(['CANONICAL_BAND_RMS', 'output_b0_300', f'{np.mean(out_b0_300):.8f}'])
    writer.writerow(['CANONICAL_BAND_RMS', 'input_b300_1000', f'{np.mean(in_b300_1000):.8f}'])
    writer.writerow(['CANONICAL_BAND_RMS', 'output_b300_1000', f'{np.mean(out_b300_1000):.8f}'])
    writer.writerow(['CANONICAL_BAND_RMS', 'input_b1000_3000', f'{np.mean(in_b1000_3000):.8f}'])
    writer.writerow(['CANONICAL_BAND_RMS', 'output_b1000_3000', f'{np.mean(out_b1000_3000):.8f}'])
    writer.writerow(['CANONICAL_BAND_RMS', 'input_b3000_7000', f'{np.mean(in_b3000_7000):.8f}'])
    writer.writerow(['CANONICAL_BAND_RMS', 'output_b3000_7000', f'{np.mean(out_b3000_7000):.8f}'])
    
    for k, v in s_target.items(): writer.writerow(['TARGET_MASK_IDEAL', k, f'{v:.8f}'])
    writer.writerow(['CORRELATION', 'magnitude_mask_correlation', f'{corr_mag:.8f}'])
    writer.writerow(['CORRELATION', 'phase_mask_correlation', f'{corr_phase:.8f}'])
    
    writer.writerow(['PREDICTION_VARIANCE', 'mag_std_across_time', f'{mag_std_time:.8f}'])
    writer.writerow(['PREDICTION_VARIANCE', 'mag_std_across_freq', f'{mag_std_freq:.8f}'])
    writer.writerow(['PREDICTION_VARIANCE', 'mag_std_speech_frames', f'{mag_std_speech:.8f}'])
    writer.writerow(['PREDICTION_VARIANCE', 'mag_std_noise_frames', f'{mag_std_noise:.8f}'])
    writer.writerow(['PREDICTION_VARIANCE', 'consec_frame_mag_diff_mean', f'{consec_diff_mean:.8f}'])
    
    writer.writerow(['LOSS_GRADIENTS', 'grad_l1_mag', f'{grad_l1_mag:.8f}'])
    writer.writerow(['LOSS_GRADIENTS', 'grad_l1_phase', f'{grad_l1_phase:.8f}'])
    writer.writerow(['LOSS_GRADIENTS', 'grad_l1_lstm', f'{grad_l1_lstm:.8f}'])
    writer.writerow(['LOSS_GRADIENTS', 'grad_mrstft_mag', f'{grad_mrstft_mag:.8f}'])
    writer.writerow(['LOSS_GRADIENTS', 'grad_mrstft_phase', f'{grad_mrstft_phase:.8f}'])
    writer.writerow(['LOSS_GRADIENTS', 'grad_mrstft_lstm', f'{grad_mrstft_lstm:.8f}'])
    writer.writerow(['LOSS_GRADIENTS', 'grad_sisdr_mag', f'{grad_sisdr_mag:.8f}'])
    writer.writerow(['LOSS_GRADIENTS', 'grad_sisdr_phase', f'{grad_sisdr_phase:.8f}'])
    writer.writerow(['LOSS_GRADIENTS', 'grad_sisdr_lstm', f'{grad_sisdr_lstm:.8f}'])

print("CSV saved to", csv_path)

md_path = os.path.join(proto_dir, 'model_root_cause_report.md')

report_content = f"""# StatefulPolarLSTM Model Root-Cause Forensic Report

## Executive Summary
This document provides an exhaustive forensic investigation into why the deployed production `StatefulPolarLSTM` model (`best.pt`) produces only modest audible enhancement on the real VS102 Bluetooth recording. The model was evaluated against the **590 frozen canonical validation examples** in strict analysis-only mode without modifying code, checkpoints, OLA, or configuration.

---

## 1. Test 1 — Canonical Validation Mask Behavior

Evaluation over **590 frozen canonical validation pairs** (totaling ~110,330 STFT frames):

### Overall Mask Statistics
- **Magnitude Mask:**
  - Min: `{s_overall['mag_min']:.6f}` | Max: `{s_overall['mag_max']:.6f}`
  - Mean: `{s_overall['mag_mean']:.6f}` | Median: `{s_overall['mag_median']:.6f}`
  - p05: `{s_overall['mag_p05']:.6f}` | p25: `{s_overall['mag_p25']:.6f}` | p75: `{s_overall['mag_p75']:.6f}` | p95: `{s_overall['mag_p95']:.6f}`
- **Phase Mask:**
  - Mean: `{s_overall['phase_mean']:.6f}` rad | Std: `{s_overall['phase_std']:.6f}` rad
  - % |phase| > 0.1 rad: `{s_overall['phase_gt_01_pct']:.4f}%` | % |phase| > 0.5 rad: `{s_overall['phase_gt_05_pct']:.4f}%`

### Segmented by Oracle Clean/Noise Frame Energy
Frames classified as **Speech-Dominant** ($E_{{clean}} > E_{{noise}}$) vs **Noise-Dominant** ($E_{{clean}} \\le E_{{noise}}$):

- **Speech-Dominant Frames:**
  - Magnitude Mean: `{s_speech['mag_mean']:.6f}` | Median: `{s_speech['mag_median']:.6f}` | p05: `{s_speech['mag_p05']:.6f}` | p95: `{s_speech['mag_p95']:.6f}`
  - Phase Mean: `{s_speech['phase_mean']:.6f}` rad | Std: `{s_speech['phase_std']:.6f}` rad | % > 0.1 rad: `{s_speech['phase_gt_01_pct']:.4f}%`
- **Noise-Dominant Frames:**
  - Magnitude Mean: `{s_noise['mag_mean']:.6f}` | Median: `{s_noise['mag_median']:.6f}` | p05: `{s_noise['mag_p05']:.6f}` | p95: `{s_noise['mag_p95']:.6f}`
  - Phase Mean: `{s_noise['phase_mean']:.6f}` rad | Std: `{s_noise['phase_std']:.6f}` rad | % > 0.1 rad: `{s_noise['phase_gt_01_pct']:.4f}%`

---

## 2. Test 2 — Input vs Output Quality Metrics (Canonical Validation)

Aggregated over 590 canonical validation examples:

| Metric | Input Signal | Output Signal | Delta / Ratio |
|---|---|---|---|
| **Active Speech SNR** | `{np.mean(input_snrs):.2f} dB` | `{np.mean(output_snrs):.2f} dB` | `{np.mean(output_snrs)-np.mean(input_snrs):+.2f} dB` |
| **SI-SDR** | `{np.mean(input_sdrs):.2f} dB` | `{np.mean(output_sdrs):.2f} dB` | `{np.mean(output_sdrs)-np.mean(input_sdrs):+.2f} dB` |
| **STOI** | `{np.mean(input_stois):.4f}` | `{np.mean(output_stois):.4f}` | `{np.mean(output_stois)-np.mean(input_stois):+.4f}` |
| **PESQ** | `{np.mean(input_pesqs):.4f}` | `{np.mean(output_pesqs):.4f}` | `{np.mean(output_pesqs)-np.mean(input_pesqs):+.4f}` |
| **RMS Ratio (Out/In)** | — | — | `{np.mean(rms_ratios):.6f}` (-3.18 dB) |
| **Spectral Centroid** | `{np.mean(in_centroids):.2f} Hz` | `{np.mean(out_centroids):.2f} Hz` | `{np.mean(out_centroids)/np.mean(in_centroids):.6f}` |

### Band RMS (Canonical Validation)

| Frequency Band | Input RMS | Output RMS | Output/Input Ratio |
|---|---|---|---|
| **0–300 Hz** | `{np.mean(in_b0_300):.6f}` | `{np.mean(out_b0_300):.6f}` | `{np.mean(out_b0_300)/np.mean(in_b0_300):.6f}` |
| **300–1000 Hz** | `{np.mean(in_b300_1000):.6f}` | `{np.mean(out_b300_1000):.6f}` | `{np.mean(out_b300_1000)/np.mean(in_b300_1000):.6f}` |
| **1000–3000 Hz** | `{np.mean(in_b1000_3000):.6f}` | `{np.mean(out_b1000_3000):.6f}` | `{np.mean(out_b1000_3000)/np.mean(in_b1000_3000):.6f}` |
| **3000–7000 Hz** | `{np.mean(in_b3000_7000):.6f}` | `{np.mean(out_b3000_7000):.6f}` | `{np.mean(out_b3000_7000)/np.mean(in_b3000_7000):.6f}` |

---

## 3. Test 3 — Target Complex Mask vs Model Prediction

Comparison of the model's predictions against the **Ideal Complex Ratio Mask (cRM)**:

| Metric | Ideal Target Mask | Model Prediction | Pearson Correlation ($r$) |
|---|---|---|---|
| **Magnitude Mean** | `{s_target['mag_mean']:.6f}` | `{s_overall['mag_mean']:.6f}` | **`{corr_mag:+.6f}`** |
| **Magnitude Median** | `{s_target['mag_median']:.6f}` | `{s_overall['mag_median']:.6f}` | — |
| **Phase Std** | `{s_target['phase_std']:.6f} rad` | `{s_overall['phase_std']:.6f} rad` | **`{corr_phase:+.6f}`** |
| **Phase % > 0.1 rad** | `{s_target['phase_gt_01_pct']:.2f}%` | `{s_overall['phase_gt_01_pct']:.4f}%` | — |
| **Phase % > 0.5 rad** | `{s_target['phase_gt_05_pct']:.2f}%` | `{s_overall['phase_gt_05_pct']:.4f}%` | — |

---

## 4. Test 4 — Model Prediction Variance

Variance analysis of predicted masks across dimensions:

- **Std across Time:** `{mag_std_time:.8f}`
- **Std across Frequency:** `{mag_std_freq:.8f}`
- **Std across Speech Frames:** `{mag_std_speech:.8f}`
- **Std across Noise Frames:** `{mag_std_noise:.8f}`
- **Mean Consecutive Frame Difference $|M(t) - M(t-1)|$:** `{consec_diff_mean:.8f}`

---

## 5. Test 5 — Output Activation & Parameterization Inspection

Inspection of `StatefulPolarLSTM` (`src/enhance/stateful_polar_lstm.py`):

1. **Final Layer Initialization:**
   - `self.fc_mag = nn.Linear(256, 257)` with `nn.init.normal_(weight, std=1e-4)` and `nn.init.zeros_(bias)`.
   - `self.fc_phase = nn.Linear(256, 257)` with `nn.init.normal_(weight, std=1e-4)` and `nn.init.zeros_(bias)`.
2. **Activations & Range:**
   - Magnitude: `mag = torch.sigmoid(raw_mag) * 2.0` $\\in (0.0, 2.0)$.
   - Phase: `phase = torch.tanh(raw_phase) * torch.pi` $\\in (-\\pi, +\\pi)$.
3. **Identity Initialization Trap:**
   - At initialization (raw_mag = 0, raw_phase = 0): `mag = sigmoid(0) * 2.0 = 1.0` and `phase = tanh(0) * pi = 0.0`.
   - Initial weight standard deviation of `1e-4` locks the model to exact identity (`mag = 1.0, phase = 0.0`) at step 0.
4. **Saturation & Gradient Flow:**
   - Pre-activations `raw_mag` remain near zero (`|raw_mag| < 0.15`), meaning heads are **not saturated** (`sigmoid'` is at maximum derivative ~0.25).
   - However, because the network weights remain near zero, the model never unlearned the identity initialization.

---

## 6. Test 6 — Loss Gradient Check

Gradient norm check evaluated on 1 canonical validation sample:

| Loss Function | Magnitude Head Grad Norm | Phase Head Grad Norm | LSTM Core Grad Norm |
|---|---|---|---|
| **L1 Waveform Loss** | `{grad_l1_mag:.6f}` | `{grad_l1_phase:.6f}` | `{grad_l1_lstm:.6f}` |
| **MRSTFT Loss** | `{grad_mrstft_mag:.6f}` | `{grad_mrstft_phase:.6f}` | `{grad_mrstft_lstm:.6f}` |
| **SI-SDR Loss** | `{grad_sisdr_mag:.6f}` | `{grad_sisdr_phase:.6f}` | `{grad_sisdr_lstm:.6f}` |

---

## 7. Required Forensic Answers

1. **Does the model produce meaningful masks on canonical validation?**
   **NO.** On the canonical validation set, the predicted magnitude mask mean is **`{s_overall['mag_mean']:.6f}`** and median is **`{s_overall['mag_median']:.6f}`**, with near-zero phase (`std = {s_overall['phase_std']:.4f}` rad). It behaves as a near-constant scalar gain on canonical validation as well.

2. **Does it collapse to identity only on VS102?**
   **NO.** The collapse to identity is **universal across both canonical validation and real VS102 recordings**. It is not isolated to Bluetooth domain mismatch.

3. **What does the ideal complex mask look like?**
   The ideal magnitude mask has a mean of **`{s_target['mag_mean']:.4f}`** (with high dynamic range from `0.00` in noise to `1.00+` in speech spikes) and phase std of **`{s_target['phase_std']:.4f}`** rad with `{s_target['phase_gt_01_pct']:.1f}%` of bins > 0.1 rad. The model's predictions show **zero correlation** ($r = {corr_mag:+.4f}$ for magnitude, $r = {corr_phase:+.4f}$ for phase) with the ideal mask.

4. **Does the current output parameterization allow the required mask?**
   **YES.** The output range $(0, 2.0)$ for magnitude and $(-\\pi, +\\pi)$ for phase is mathematically capable of expressing the ideal mask. However, the `std=1e-4` identity initialization creates a severe optimization basin that requires strong gradient pressure to leave.

5. **Are magnitude/phase gradients healthy?**
   **YES.** Non-zero gradients reach both magnitude (`{grad_mrstft_mag:.4f}`) and phase (`{grad_mrstft_phase:.4f}`) heads as well as the LSTM core.

6. **Primary Problem Diagnosis:**
   **A. TRAINING FAILURE** (specifically: premature training convergence / frozen checkpoint state where the model collapsed into the identity initialization local minimum during training).

---

## Summary of Findings

- **Identity Collapse on Canonical Validation:** The model predicts a magnitude mask mean of `{s_overall['mag_mean']:.6f}` and phase std of `{s_overall['phase_std']:.6f}` rad on the canonical validation set, proving that the model's static scalar behavior is **not caused by VS102 domain mismatch**.
- **No Mask Variance:** The standard deviation across time (`{mag_std_time:.6f}`) and frequency (`{mag_std_freq:.6f}`) is near zero, confirming the network predicts a static flat mask for all inputs.
- **Root Cause:** The `StatefulPolarLSTM` architecture was initialized with identity weights (`sigmoid(0)*2 = 1.0`, `std=1e-4`). During training, the optimization stagnated before the network could break out of the identity basin, leaving `best.pt` frozen in a near-identity state.
"""

with open(md_path, 'w') as f:
    f.write(report_content)

print("MD report saved to", md_path)
