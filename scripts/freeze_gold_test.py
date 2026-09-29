import os
import csv
import hashlib
import torch
import torchaudio
import numpy as np
from pathlib import Path
import random
import soundfile as sf
from tqdm import tqdm

def compute_sha256(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def calculate_active_speech_level(waveform, sample_rate=16000, frame_length_ms=30):
    # Simple energy-based VAD for active speech level (simplified ITU-T P.56)
    frame_length = int(sample_rate * frame_length_ms / 1000)
    if waveform.shape[-1] < frame_length:
        return torch.mean(waveform ** 2)
        
    frames = waveform.unfold(-1, frame_length, frame_length)
    frame_energies = torch.mean(frames ** 2, dim=-1)
    
    # Threshold: 30 dB below max energy
    max_energy = torch.max(frame_energies)
    threshold = max_energy * 0.001
    
    active_frames = frame_energies[frame_energies > threshold]
    if len(active_frames) == 0:
        return torch.mean(waveform ** 2)
        
    return torch.mean(active_frames)

def mix_snr(clean, noise, snr_db):
    clean_power = calculate_active_speech_level(clean)
    # Noise is usually continuous, we can use simple RMS
    noise_power = torch.mean(noise ** 2)
    
    if clean_power <= 1e-10 or noise_power <= 1e-10:
        return clean, 0.0 # Cannot mix silently
        
    snr_linear = 10 ** (snr_db / 10)
    target_noise_power = clean_power / snr_linear
    
    scale = torch.sqrt(target_noise_power / noise_power)
    scaled_noise = noise * scale
    
    mixed = clean + scaled_noise
    
    # Verify achieved SNR
    achieved_noise_power = torch.mean(scaled_noise ** 2)
    achieved_snr = 10 * torch.log10(clean_power / achieved_noise_power)
    
    # Normalize to prevent clipping
    max_val = torch.max(torch.abs(mixed))
    if max_val > 0.99:
        mixed = mixed / max_val * 0.99
        
    return mixed, achieved_snr.item()

def freeze_gold_test():
    random.seed(12345)
    
    clean_manifest = "data/clean_manifests/clean_test.csv"
    noise_manifest = "data/clean_manifests/noise_test.csv"
    
    if not os.path.exists(clean_manifest) or not os.path.exists(noise_manifest):
        print("Test manifests not found. Run build_clean_manifests.py first.")
        return
        
    with open(clean_manifest, "r") as f:
        clean_records = list(csv.DictReader(f))
    with open(noise_manifest, "r") as f:
        noise_records = list(csv.DictReader(f))
        
    out_dir = Path("data/SIH_GOLD_TEST")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    gold_manifest_path = "data/clean_manifests/SIH_GOLD_TEST_manifest.csv"
    
    # Let's generate 100 test clips to freeze
    num_clips = 100
    rows = []
    
    print(f"Generating {num_clips} frozen test clips...")
    for i in tqdm(range(num_clips)):
        c_rec = random.choice(clean_records)
        n_rec = random.choice(noise_records)
        
        c_wav, sr_c = torchaudio.load(c_rec["file_path"])
        n_wav, sr_n = torchaudio.load(n_rec["file_path"])
        
        # Ensure 16k
        if sr_c != 16000: c_wav = torchaudio.transforms.Resample(sr_c, 16000)(c_wav)
        if sr_n != 16000: n_wav = torchaudio.transforms.Resample(sr_n, 16000)(n_wav)
        
        # Convert to mono
        if c_wav.shape[0] > 1: c_wav = c_wav.mean(dim=0, keepdim=True)
        if n_wav.shape[0] > 1: n_wav = n_wav.mean(dim=0, keepdim=True)
        
        # Match lengths (crop to min)
        min_len = min(c_wav.shape[-1], n_wav.shape[-1], 16000 * 5) # max 5 seconds
        c_wav = c_wav[:, :min_len]
        
        # Random start for noise
        if n_wav.shape[-1] > min_len:
            start = random.randint(0, n_wav.shape[-1] - min_len)
            n_wav = n_wav[:, start:start+min_len]
            
        target_snr = random.uniform(-5.0, 15.0)
        
        mixed, achieved_snr = mix_snr(c_wav, n_wav, target_snr)
        
        out_path = out_dir / f"gold_test_{i:04d}.wav"
        torchaudio.save(str(out_path), mixed, 16000)
        
        h = compute_sha256(str(out_path))
        
        rows.append({
            "file_path": str(out_path),
            "file_hash": h,
            "parent_clean_id": c_rec["source_recording_id"],
            "parent_noise_id": n_rec["source_recording_id"],
            "parent_noise_class": n_rec["source_class"],
            "target_snr": f"{target_snr:.2f}",
            "achieved_snr": f"{achieved_snr:.2f}",
            "sample_rate": 16000,
            "duration": f"{min_len / 16000:.2f}"
        })
        
    with open(gold_manifest_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        
    manifest_hash = compute_sha256(gold_manifest_path)
    print(f"SIH_GOLD_TEST Frozen!")
    print(f"Manifest Hash: {manifest_hash}")
    
    with open("data/clean_manifests/SIH_GOLD_TEST_hash.txt", "w") as f:
        f.write(manifest_hash)

if __name__ == "__main__":
    freeze_gold_test()
