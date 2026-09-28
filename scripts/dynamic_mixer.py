import os
import random
import logging
from dataclasses import dataclass, field
import pandas as pd
import torch
import torchaudio
import scipy.signal
import numpy as np
import soundfile as sf
from functools import lru_cache

try:
    from audiomentations import Compose, AddGaussianNoise, PitchShift, TimeStretch
except ImportError:
    Compose = None

logger = logging.getLogger(__name__)

@dataclass
class MixerConfig:
    clean_manifest: str
    noise_manifest: str
    rir_manifest: str = None
    epoch_size: int = 10000
    target_sr: int = 16000
    clip_duration: float = 3.0
    is_val: bool = False
    return_metadata: bool = False
    snr_levels: list = field(default_factory=lambda: [-10, -5, 0, 5, 10, 15, 20])
    snr_probs: list = field(default_factory=lambda: [0.05, 0.10, 0.20, 0.25, 0.20, 0.15, 0.05])
    use_augmentations: bool = True

class AntigravityDataset(torch.utils.data.Dataset):
    def __init__(self, clean_manifest=None, noise_manifest=None, rir_manifest=None, epoch_size=10000, is_val=False, return_metadata=False, use_augmentations=True, config=None):
        if config is not None:
            self.config = config
        else:
            self.config = MixerConfig(
                clean_manifest=clean_manifest,
                noise_manifest=noise_manifest,
                rir_manifest=rir_manifest,
                epoch_size=epoch_size,
                is_val=is_val,
                return_metadata=return_metadata,
                use_augmentations=use_augmentations and not is_val
            )
        self.clean_df = pd.read_csv(self.config.clean_manifest)
        self.noise_df = pd.read_csv(self.config.noise_manifest)
        self.rir_df = pd.read_csv(self.config.rir_manifest) if self.config.rir_manifest and os.path.exists(self.config.rir_manifest) else None
        
        self.augment = self._init_augmentations() if self.config.use_augmentations and Compose else None

    def _init_augmentations(self):
        return Compose([
            AddGaussianNoise(min_amplitude=0.001, max_amplitude=0.015, p=0.2),
            PitchShift(min_semitones=-2, max_semitones=2, p=0.2),
            TimeStretch(min_rate=0.8, max_rate=1.2, leave_length_unchanged=True, p=0.2)
        ])

    def __len__(self):
        return self.config.epoch_size

    def load_random_clip(self, row, is_rir=False):
        path = row['path']
        
        if is_rir:
            # RIRs are usually fully loaded and small, perfect for caching
            return self._load_full_clip_cached(path)
            
        duration = row['duration']
        max_start = max(0, duration - self.config.clip_duration)
        start_time = random.uniform(0, max_start)
        frame_offset = int(start_time * self.config.target_sr)
        num_frames = int(self.config.clip_duration * self.config.target_sr)
        
        try:
            wav, sr = sf.read(path, start=frame_offset, frames=num_frames, dtype='float32', always_2d=True)
            wav = torch.from_numpy(wav.T)[0] # Extract the first channel
            
            if wav.shape[0] < num_frames:
                pad = num_frames - wav.shape[0]
                wav = torch.nn.functional.pad(wav, (0, pad))
            return wav
        except Exception as e:
            logger.error(f"Error loading clip {path}: {e}")
            return torch.zeros(num_frames)

    @lru_cache(maxsize=1024)
    def _load_full_clip_cached(self, path):
        try:
            wav, sr = sf.read(path, dtype='float32', always_2d=True)
            return torch.from_numpy(wav.T)[0]
        except Exception as e:
            logger.error(f"Error loading RIR {path}: {e}")
            return torch.tensor([1.0]) # fallback impulse

    def apply_rir(self, clean, rir):
        clean_np = clean.numpy()
        rir_np = rir.numpy()
        
        rir_np = rir_np / (np.max(np.abs(rir_np)) + 1e-8)
        reverb = scipy.signal.convolve(clean_np, rir_np, mode='full')[:clean_np.shape[0]]
        return torch.from_numpy(reverb)

    def mix_at_snr(self, clean, noise, snr_db):
        clean_rms = torch.sqrt(torch.mean(clean ** 2))
        noise_rms = torch.sqrt(torch.mean(noise ** 2))
        
        if clean_rms == 0 or noise_rms == 0:
            return clean + noise, clean

        snr_linear = 10 ** (snr_db / 20)
        target_noise_rms = clean_rms / snr_linear
        
        noise_scaled = noise * (target_noise_rms / noise_rms)
        mixed = clean + noise_scaled
        
        max_val = torch.max(torch.abs(mixed))
        if max_val > 1.0:
            mixed = mixed / max_val
            clean = clean / max_val
            
        return mixed, clean

    def __getitem__(self, idx):
        if self.config.is_val:
            random.seed(idx)
            np.random.seed(idx)
            
        clean_row = self.clean_df.sample(1).iloc[0]
        clean_audio = self.load_random_clip(clean_row)
        
        if self.augment:
            try:
                clean_np = self.augment(samples=clean_audio.numpy(), sample_rate=self.config.target_sr)
                clean_audio = torch.from_numpy(clean_np)
            except Exception as e:
                logger.warning(f"Augmentation failed, skipping: {e}")

        noise_row = self.noise_df.sample(1).iloc[0]
        noise_audio = self.load_random_clip(noise_row)
        
        reverberant_clean = clean_audio
        if self.rir_df is not None and random.random() < 0.5:
            rir_row = self.rir_df.sample(1).iloc[0]
            rir_audio = self.load_random_clip(rir_row, is_rir=True)
            reverberant_clean = self.apply_rir(clean_audio, rir_audio)
            
        snr = np.random.choice(self.config.snr_levels, p=self.config.snr_probs)
        noisy, target = self.mix_at_snr(reverberant_clean, noise_audio, snr)
        
        if self.config.return_metadata:
            meta = {
                'snr': snr,
                'category': noise_row.get('category', 'unknown')
            }
            return noisy, target, meta
            
        return noisy, target

def test():
    logging.basicConfig(level=logging.INFO)
    logger.info("Testing dynamic mixer with Config, LRU Cache & Augmentations...")
    try:
        ds = AntigravityDataset(clean_manifest="data/manifests/clean.csv", noise_manifest="data/manifests/noise.csv")
        noisy, clean = ds[0]
        logger.info(f"Sample generated! Noisy shape: {noisy.shape}, Clean shape: {clean.shape}")
    except Exception as e:
        logger.warning(f"Test skipped or failed: {e}")

if __name__ == "__main__":
    test()
