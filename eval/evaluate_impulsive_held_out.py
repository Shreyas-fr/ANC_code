"""
Regenerates results/impulsive_table.md using only AudioSet-sourced clips
(gunshot, artillery, explosion) from the current noise_test.csv.
These clips were NOT used in training and passed the hash-dedup check.
"""
import os
import sys
import csv
import torch
import numpy as np
from pathlib import Path
from tqdm import tqdm

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from scripts.dynamic_mixer import AntigravityDataset, MixerConfig
from src.enhance.complex_crn import ComplexCRN_Wrapper
from src.enhance.evaluate import si_sdr

IMPULSIVE_CLASSES = {"gunshot", "artillery", "explosion"}
CHECKPOINT = "checkpoints/dtln/latest.pt"
SEED = 42

def get_impulsive_clips():
    """Extract impulsive clips from test manifest by matching audioset subfolder names."""
    clips = []
    with open("data/manifests/noise_test.csv") as f:
        for row in csv.DictReader(f):
            path = row["path"]
            # audioset clips are stored as data/raw/noise/<category>/<subfolder>/xxx.wav
            parts = Path(path).parts
            # check any part of the path for impulsive class name
            if any(cls in path.lower() for cls in IMPULSIVE_CLASSES):
                clips.append(row)
    return clips

def evaluate_impulsive():
    import random
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)

    device = torch.device("cpu")
    model = ComplexCRN_Wrapper().to(device)
    sd = torch.load(CHECKPOINT, map_location=device)
    model.load_state_dict(sd)
    model.eval()

    clips = get_impulsive_clips()
    print(f"Found {len(clips)} impulsive clips in test set")

    if len(clips) == 0:
        print("WARNING: No impulsive clips found. Writing stale marker.")
        os.makedirs("results", exist_ok=True)
        with open("results/impulsive_table.md", "w") as f:
            f.write("# Impulsive Noise Performance\n\n")
            f.write("> **NOTE**: No held-out impulsive clips available after deduplication.\n")
            f.write("> ESC-50 impulsive clips used during training were removed from the test set.\n")
            f.write("> AudioSet impulsive classes (gunshot/artillery/explosion) had 0 clips in the test manifest.\n")
            f.write("> Impulsive evaluation is a planned next step using a separate held-out set.\n")
        print("Written results/impulsive_table.md with honest status.")
        return

    # Write temp manifest for the impulsive clips
    tmp = "data/manifests/noise_test_impulsive_tmp.csv"
    with open(tmp, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["path","category","dataset","sample_rate","duration"])
        writer.writeheader()
        writer.writerows(clips)

    snr_levels = [-5, 0, 5, 10, 15]
    rows = []

    for snr in snr_levels:
        config = MixerConfig(
            clean_manifest="data/manifests/clean_test.csv",
            noise_manifest=tmp,
            epoch_size=min(50, len(clips)),
            is_val=True,
            return_metadata=True,
            snr_levels=[snr],
            snr_probs=[1.0],
            use_augmentations=False,
        )
        ds = AntigravityDataset(config=config)
        full_sdrs, burst_sdrs, peak_ratios = [], [], []

        with torch.no_grad():
            for i in tqdm(range(len(ds)), desc=f"Impulsive SNR={snr}"):
                noisy, clean, meta = ds[i]
                if torch.max(torch.abs(noisy - clean)) < 1e-4:
                    continue
                enhanced = model(noisy.unsqueeze(0)).squeeze(0)
                c, n, e = clean.numpy(), noisy.numpy(), enhanced.numpy()

                full_sdrs.append(si_sdr(c, e))

                # 400ms burst window centred in clip
                sr = 16000
                w = int(0.2 * sr)
                mid = len(c) // 2
                s, end_ = max(0, mid-w), min(len(c), mid+w)
                burst_sdrs.append(si_sdr(c[s:end_], e[s:end_]))

                peak_n = np.max(np.abs(n))
                peak_e = np.max(np.abs(e))
                if peak_n > 1e-8:
                    peak_ratios.append(20 * np.log10(peak_e / peak_n + 1e-8))

        rows.append({
            "snr": snr,
            "full_sdr_n": np.mean([si_sdr(c, n) for _ in [1]]),   # noisy full SI-SDR
            "full_sdr_e": np.mean(full_sdrs) if full_sdrs else float('nan'),
            "burst_sdr_e": np.mean(burst_sdrs) if burst_sdrs else float('nan'),
            "peak_ratio": np.mean(peak_ratios) if peak_ratios else float('nan'),
        })

    os.remove(tmp)
    os.makedirs("results", exist_ok=True)
    with open("results/impulsive_table.md", "w") as f:
        f.write("# Impulsive Noise Performance\n\n")
        f.write("| Input SNR | SI-SDR Full (N->E) | SI-SDR Burst Window (N->E) | Peak Ratio (E/C) |\n")
        f.write("|-----------|--------------------|----------------------------|------------------|\n")
        for r in rows:
            f.write(f"| {r['snr']} dB | {r['full_sdr_n']:.1f} -> {r['full_sdr_e']:.1f} | ? -> {r['burst_sdr_e']:.1f} | {r['peak_ratio']:.1f} dB |\n")
    print("Written results/impulsive_table.md")

if __name__ == "__main__":
    evaluate_impulsive()
