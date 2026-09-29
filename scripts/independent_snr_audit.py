import os
import csv
import torch
import torchaudio
import numpy as np
import random
from pathlib import Path

def calculate_active_speech_level(waveform, sample_rate=16000, frame_length_ms=30):
    frame_length = int(sample_rate * frame_length_ms / 1000)
    if waveform.shape[-1] < frame_length:
        return torch.mean(waveform ** 2)
        
    frames = waveform.unfold(-1, frame_length, frame_length)
    frame_energies = torch.mean(frames ** 2, dim=-1)
    
    max_energy = torch.max(frame_energies)
    threshold = max_energy * 0.001
    
    active_frames = frame_energies[frame_energies > threshold]
    if len(active_frames) == 0:
        return torch.mean(waveform ** 2)
        
    return torch.mean(active_frames)

def audit_snr():
    print("=== SIH26052 INDEPENDENT SNR AUDIT ===")
    
    # 1. We must recover the exact paths by mirroring the generation RNG state
    random.seed(12345)
    
    with open("data/clean_manifests/clean_test.csv", "r") as f:
        clean_records = list(csv.DictReader(f))
    with open("data/clean_manifests/noise_test.csv", "r") as f:
        noise_records = list(csv.DictReader(f))
    with open("data/clean_manifests/SIH_GOLD_TEST_manifest.csv", "r") as f:
        gold_records = list(csv.DictReader(f))
        
    target_snrs = []
    achieved_snrs = []
    residuals_max = []
    residuals_rms = []
    
    clipped_files = 0
    
    print(f"{'ID':<5} | {'Target':<8} | {'Measured':<8} | {'Error':<8} | {'MaxResid':<8}")
    print("-" * 50)
    
    for i in range(100):
        # Mirror RNG
        c_rec = random.choice(clean_records)
        n_rec = random.choice(noise_records)
        
        c_wav, sr_c = torchaudio.load(c_rec["file_path"])
        n_wav, sr_n = torchaudio.load(n_rec["file_path"])
        
        if sr_c != 16000: c_wav = torchaudio.transforms.Resample(sr_c, 16000)(c_wav)
        if sr_n != 16000: n_wav = torchaudio.transforms.Resample(sr_n, 16000)(n_wav)
        if c_wav.shape[0] > 1: c_wav = c_wav.mean(dim=0, keepdim=True)
        if n_wav.shape[0] > 1: n_wav = n_wav.mean(dim=0, keepdim=True)
        
        min_len = min(c_wav.shape[-1], n_wav.shape[-1], 16000 * 5)
        c_wav = c_wav[:, :min_len]
        
        if n_wav.shape[-1] > min_len:
            start = random.randint(0, n_wav.shape[-1] - min_len)
            n_wav = n_wav[:, start:start+min_len]
            
        target_snr = random.uniform(-5.0, 15.0)
        
        # Load the saved file
        saved_mix, sr_mix = torchaudio.load(f"data/SIH_GOLD_TEST/gold_test_{i:04d}.wav")
        
        # Independent Measurement
        clean_power = calculate_active_speech_level(c_wav)
        noise_power = torch.mean(n_wav ** 2)
        
        # In the file, the mixture is saved. 
        # But wait, how much was the noise scaled? We must figure out the scaling applied.
        # It was scaled to achieve target SNR:
        snr_linear = 10 ** (target_snr / 10)
        target_noise_power = clean_power / snr_linear
        scale = torch.sqrt(target_noise_power / noise_power)
        scaled_noise = n_wav * scale
        
        raw_mixed = c_wav + scaled_noise
        
        # Check normalization alpha
        max_val = torch.max(torch.abs(raw_mixed))
        alpha = 1.0
        if max_val > 0.99:
            alpha = (0.99 / max_val).item()
            
        # The true clean in the file is c_wav * alpha
        # The true noise in the file is scaled_noise * alpha
        true_clean = c_wav * alpha
        true_noise = scaled_noise * alpha
        
        # Residual
        residual = saved_mix - (true_clean + true_noise)
        res_max = torch.max(torch.abs(residual)).item()
        res_rms = torch.sqrt(torch.mean(residual ** 2)).item()
        
        # Check clipping in saved file
        if torch.max(torch.abs(saved_mix)) >= 0.9999:
            clipped_files += 1
            
        # Independent SNR calculation on the TRUE components present in the saved file
        # We must use VAD on the true_clean to see if scaling affects VAD
        indep_clean_power = calculate_active_speech_level(true_clean)
        indep_noise_power = torch.mean(true_noise ** 2)
        
        if indep_clean_power > 0 and indep_noise_power > 0:
            measured_snr = 10 * torch.log10(indep_clean_power / indep_noise_power).item()
        else:
            measured_snr = 0.0
            
        error = abs(measured_snr - target_snr)
        
        target_snrs.append(target_snr)
        achieved_snrs.append(measured_snr)
        residuals_max.append(res_max)
        residuals_rms.append(res_rms)
        
        if i < 15:
            print(f"{i:<5} | {target_snr:>8.2f} | {measured_snr:>8.2f} | {error:>8.4f} | {res_max:>8.4e}")
            
    # Statistics
    achieved_snrs = np.array(achieved_snrs)
    errors = np.abs(np.array(target_snrs) - achieved_snrs)
    
    print("-" * 50)
    print(f"ACTUAL_MEASURED_SNR_MEAN={achieved_snrs.mean():.4f}")
    print(f"ACTUAL_MEASURED_SNR_MEDIAN={np.median(achieved_snrs):.4f}")
    print(f"ACTUAL_MEASURED_SNR_STD={achieved_snrs.std():.4f}")
    print(f"ACTUAL_MEASURED_SNR_MIN={achieved_snrs.min():.4f}")
    print(f"ACTUAL_MEASURED_SNR_MAX={achieved_snrs.max():.4f}")
    print(f"ABSOLUTE_ERROR_MEAN={errors.mean():.4f}")
    print(f"ABSOLUTE_ERROR_MEDIAN={np.median(errors):.4f}")
    print(f"ABSOLUTE_ERROR_MAX={errors.max():.4f}")
    print(f"COUNT_WITH_ERROR_LE_0_1DB={np.sum(errors <= 0.1)}")
    print(f"COUNT_WITH_ERROR_LE_0_5DB={np.sum(errors <= 0.5)}")
    print(f"COUNT_WITH_ERROR_LE_1_0DB={np.sum(errors <= 1.0)}")
    print(f"CLIPPED_FILE_COUNT={clipped_files}")
    print(f"MIXTURE_RECONSTRUCTION_RESIDUAL_RMS={np.mean(residuals_rms):.4e}")

if __name__ == "__main__":
    audit_snr()
