import os
import random
import pandas as pd
import torch
import torchaudio
import scipy.signal
import numpy as np

class AntigravityDataset(torch.utils.data.Dataset):
    def __init__(self, clean_manifest, noise_manifest, rir_manifest=None, epoch_size=10000, is_val=False):
        self.clean_df = pd.read_csv(clean_manifest)
        self.noise_df = pd.read_csv(noise_manifest)
        self.rir_df = pd.read_csv(rir_manifest) if rir_manifest and os.path.exists(rir_manifest) else None
        self.epoch_size = epoch_size
        self.target_sr = 16000
        self.clip_duration = 3.0 # Fixed 3s clips for training
        self.is_val = is_val

    def __len__(self):
        return self.epoch_size

    def load_random_clip(self, row):
        path = row['path']
        duration = row['duration']
        
        # We want to load a random 3s window
        max_start = max(0, duration - self.clip_duration)
        start_time = random.uniform(0, max_start)
        frame_offset = int(start_time * self.target_sr)
        num_frames = int(self.clip_duration * self.target_sr)
        
        import soundfile as sf
        wav, sr = sf.read(path, start=frame_offset, frames=num_frames, dtype='float32', always_2d=True)
        wav = torch.from_numpy(wav.T)[0] # Extract the first channel to make it 1D [Time]
        # Pad if too short
        if wav.shape[0] < num_frames:
            pad = num_frames - wav.shape[0]
            wav = torch.nn.functional.pad(wav, (0, pad))
        return wav

    def apply_rir(self, clean, rir):
        clean_np = clean.numpy()
        rir_np = rir.numpy()
        
        # Normalize RIR
        rir_np = rir_np / np.max(np.abs(rir_np))
        
        # Convolve (1D arrays)
        reverb = scipy.signal.convolve(clean_np, rir_np, mode='full')[:clean_np.shape[0]]
        return torch.from_numpy(reverb)

    def mix_at_snr(self, clean, noise, snr_db):
        clean_rms = torch.sqrt(torch.mean(clean ** 2))
        noise_rms = torch.sqrt(torch.mean(noise ** 2))
        
        if clean_rms == 0 or noise_rms == 0:
            return clean + noise, clean

        # Calculate desired noise RMS
        snr_linear = 10 ** (snr_db / 20)
        target_noise_rms = clean_rms / snr_linear
        
        noise_scaled = noise * (target_noise_rms / noise_rms)
        mixed = clean + noise_scaled
        
        # Normalize to avoid clipping
        max_val = torch.max(torch.abs(mixed))
        if max_val > 1.0:
            mixed = mixed / max_val
            clean = clean / max_val
            
        return mixed, clean

    def get_snr(self):
        # Distribution: SNR -10 dB -> 5%, -5 dB -> 10%, 0 dB -> 20%, +5 dB -> 25%, +10 dB -> 20%, +15 dB -> 15%, +20 dB -> 5%
        snrs = [-10, -5, 0, 5, 10, 15, 20]
        probs = [0.05, 0.10, 0.20, 0.25, 0.20, 0.15, 0.05]
        return np.random.choice(snrs, p=probs)

    def __getitem__(self, idx):
        if self.is_val:
            random.seed(idx)
            np.random.seed(idx)
            
        # 1. Sample clean
        clean_row = self.clean_df.sample(1).iloc[0]
        clean_audio = self.load_random_clip(clean_row)
        
        # 2. Sample noise
        # Just pick a random noise for now
        noise_row = self.noise_df.sample(1).iloc[0]
        noise_audio = self.load_random_clip(noise_row)
        
        # 3. Apply RIR (50% chance if available)
        reverberant_clean = clean_audio
        if self.rir_df is not None and random.random() < 0.5:
            rir_row = self.rir_df.sample(1).iloc[0]
            rir_audio = self.load_random_clip(rir_row)
            reverberant_clean = self.apply_rir(clean_audio, rir_audio)
            
        # 4. Mix
        snr = self.get_snr()
        noisy, target = self.mix_at_snr(reverberant_clean, noise_audio, snr)
        
        return noisy, target

def test():
    print("Testing dynamic mixer...")
    try:
        ds = AntigravityDataset("data/manifests/clean.csv", "data/manifests/noise.csv")
        noisy, clean = ds[0]
        print(f"Sample generated! Noisy shape: {noisy.shape}, Clean shape: {clean.shape}")
    except Exception as e:
        print(f"Test skipped or failed (likely because manifests aren't populated yet): {e}")

if __name__ == "__main__":
    test()
