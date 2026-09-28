import sys
import os
import torch
import numpy as np
import pandas as pd
import soundfile as sf
from pathlib import Path
from tqdm import tqdm

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from scripts.dynamic_mixer import AntigravityDataset, MixerConfig
from src.enhance.complex_crn import ComplexCRN_Wrapper
from src.enhance.evaluate import pesq, stoi, si_sdr
import scipy.signal

def get_burst_window(clean, threshold=0.1, window_ms=200, sr=16000):
    # Detect the peak of the burst (e.g. gunshot) in the clean audio
    peak_idx = np.argmax(np.abs(clean))
    win_samples = int((window_ms / 1000.0) * sr)
    start_idx = max(0, peak_idx - win_samples)
    end_idx = min(len(clean), peak_idx + win_samples)
    return start_idx, end_idx

def evaluate_impulsive():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = ComplexCRN_Wrapper().to(device)
    checkpoint_path = "checkpoints/dtln/best.pt"
    if os.path.exists(checkpoint_path):
        state_dict = torch.load(checkpoint_path, map_location=device)
        new_state_dict = {("core."+k if not k.startswith("core.") else k): v for k,v in state_dict.items()}
        model.load_state_dict(new_state_dict)
    model.eval()

    noise_csv = "data/manifests/noise_test.csv"
    if not os.path.exists(noise_csv): return
    noise_df = pd.read_csv(noise_csv)
    
    # Filter only impulsive
    cat_df = noise_df[noise_df['category'] == 'impulsive']
    if len(cat_df) == 0: return
    cat_manifest = "data/manifests/noise_test_impulsive.csv"
    cat_df.to_csv(cat_manifest, index=False)

    os.makedirs("results/audio_examples", exist_ok=True)
    results = []
    
    snr_levels = [-5, 0, 5, 10, 15]
    saved_examples = 0

    for snr in snr_levels:
        config = MixerConfig(
            clean_manifest="data/manifests/clean_test.csv",
            noise_manifest=cat_manifest,
            epoch_size=50,
            is_val=True,
            return_metadata=True,
            snr_levels=[snr],
            snr_probs=[1.0],
            use_augmentations=False
        )
        ds = AntigravityDataset(config=config)
        
        with torch.no_grad():
            for i in tqdm(range(50), desc=f"Impulsive SNR {snr}"):
                noisy, clean, meta = ds[i]
                noisy_t = noisy.unsqueeze(0).to(device)
                enhanced = model(noisy_t).squeeze(0).cpu()
                
                c = clean.numpy()
                n = noisy.numpy()
                e = enhanced.numpy()
                
                s, end = get_burst_window(c)
                c_burst = c[s:end]
                n_burst = n[s:end]
                e_burst = e[s:end]
                
                # Peak residual ratio
                c_peak = np.max(np.abs(c_burst))
                e_peak = np.max(np.abs(e_burst))
                peak_ratio = 20 * np.log10((e_peak + 1e-8) / (c_peak + 1e-8))
                
                sdr_n = si_sdr(c, n)
                sdr_e = si_sdr(c, e)
                sdr_n_burst = si_sdr(c_burst, n_burst)
                sdr_e_burst = si_sdr(c_burst, e_burst)
                
                results.append({
                    'snr': snr,
                    'sisdr_n_full': sdr_n,
                    'sisdr_e_full': sdr_e,
                    'sisdr_n_burst': sdr_n_burst,
                    'sisdr_e_burst': sdr_e_burst,
                    'peak_ratio_db': peak_ratio
                })
                
                if saved_examples < 5 and snr == 5:
                    sf.write(f"results/audio_examples/impulsive_{saved_examples}_clean.wav", c, 16000)
                    sf.write(f"results/audio_examples/impulsive_{saved_examples}_noisy.wav", n, 16000)
                    sf.write(f"results/audio_examples/impulsive_{saved_examples}_enhanced.wav", e, 16000)
                    saved_examples += 1

    df = pd.DataFrame(results)
    df.to_csv("results/impulsive_metrics.csv", index=False)
    
    with open("results/impulsive_table.md", "w") as f:
        f.write("# Impulsive Noise Performance\n\n")
        f.write("| Input SNR | SI-SDR Full (N->E) | SI-SDR Burst Window (N->E) | Peak Ratio (E/C) |\n")
        f.write("|-----------|--------------------|----------------------------|------------------|\n")
        for snr in sorted(df['snr'].unique()):
            sub = df[df['snr'] == snr]
            f.write(f"| {snr} dB | {sub['sisdr_n_full'].mean():.1f} -> {sub['sisdr_e_full'].mean():.1f} | {sub['sisdr_n_burst'].mean():.1f} -> {sub['sisdr_e_burst'].mean():.1f} | {sub['peak_ratio_db'].mean():.1f} dB |\n")
            
    if os.path.exists(cat_manifest): os.remove(cat_manifest)

if __name__ == "__main__":
    evaluate_impulsive()
