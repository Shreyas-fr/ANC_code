import sys
import os
import torch
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from tqdm import tqdm

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from scripts.dynamic_mixer import AntigravityDataset, MixerConfig
from src.enhance.complex_crn import ComplexCRN_Wrapper
from src.enhance.evaluate import pesq, stoi, si_sdr
import scipy.signal

def calculate_output_snr(clean, enhanced):
    noise = enhanced - clean
    p_signal = np.mean(clean ** 2)
    p_noise = np.mean(noise ** 2)
    if p_noise == 0: return 100.0
    return 10 * np.log10(p_signal / p_noise)

def run_evaluation(model, snr_levels=[-5, 0, 5, 10, 15, 20], samples_per_snr=200):
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model.eval()
    results = []

    noise_csv = "data/manifests/noise_test.csv"
    if not os.path.exists(noise_csv):
        print(f"Error: {noise_csv} not found.")
        return pd.DataFrame()

    noise_df = pd.read_csv(noise_csv)
    categories = noise_df['category'].unique()
    samples_per_cat = max(1, samples_per_snr // len(categories)) if len(categories) > 0 else samples_per_snr

    for snr in snr_levels:
        for cat in categories:
            cat_df = noise_df[noise_df['category'] == cat]
            if len(cat_df) == 0: continue
            
            cat_manifest = f"data/manifests/noise_test_{cat}.csv"
            cat_df.to_csv(cat_manifest, index=False)
            
            config = MixerConfig(
                clean_manifest="data/manifests/clean_test.csv",
                noise_manifest=cat_manifest,
                rir_manifest="data/manifests/rir_test.csv" if os.path.exists("data/manifests/rir_test.csv") else None,
                epoch_size=samples_per_cat,
                is_val=True,
                return_metadata=True,
                snr_levels=[snr],
                snr_probs=[1.0],
                use_augmentations=False
            )
            try:
                cat_ds = AntigravityDataset(config=config)
            except Exception as e:
                continue
            
            with torch.no_grad():
                for i in tqdm(range(samples_per_cat), desc=f"SNR {snr} {cat}"):
                    noisy, clean, meta = cat_ds[i]
                    if torch.max(torch.abs(noisy - clean)) < 1e-4: continue
                        
                    noisy_t = noisy.unsqueeze(0).to(device)
                    enhanced = model(noisy_t).squeeze(0).cpu()
                    
                    c = clean.numpy()
                    n = noisy.numpy()
                    e = enhanced.numpy()
                    
                    c_norm = c / (np.max(np.abs(c)) + 1e-8)
                    n_norm = n / (np.max(np.abs(n)) + 1e-8)
                    e_norm = e / (np.max(np.abs(e)) + 1e-8)
                    
                    sdr_n = si_sdr(c, n)
                    sdr_e = si_sdr(c, e)
                    sdr_imp = sdr_e - sdr_n
                    
                    out_snr_n = calculate_output_snr(c, n)
                    out_snr_e = calculate_output_snr(c, e)
                    
                    stoi_n = stoi(c_norm, n_norm, 16000, extended=False)
                    stoi_e = stoi(c_norm, e_norm, 16000, extended=False)
                    
                    try:
                        pesq_n = pesq(16000, c_norm, n_norm, 'wb')
                        pesq_e = pesq(16000, c_norm, e_norm, 'wb')
                    except:
                        pesq_n, pesq_e = np.nan, np.nan
                        
                    results.append({
                        'input_snr': snr,
                        'category': cat,
                        'out_snr_noisy': out_snr_n,
                        'out_snr_enhanced': out_snr_e,
                        'sisdr_noisy': sdr_n,
                        'sisdr_enhanced': sdr_e,
                        'sisdr_improvement': sdr_imp,
                        'stoi_noisy': stoi_n,
                        'stoi_enhanced': stoi_e,
                        'pesq_noisy': pesq_n,
                        'pesq_enhanced': pesq_e
                    })
            if os.path.exists(cat_manifest): os.remove(cat_manifest)

    return pd.DataFrame(results)

def generate_reports(df):
    os.makedirs("results", exist_ok=True)
    df.to_csv("results/metrics.csv", index=False)
    targets = {'out_snr': 15.0, 'stoi': 0.85, 'pesq': 2.5}
    
    with open("results/results_table.md", "w") as f:
        f.write("# Overall Results vs PS Targets\n\n")
        f.write("| Input SNR | Output SNR (N->E) | STOI (N->E) | PESQ (N->E) | SI-SDR Imp |\n")
        f.write("|-----------|-------------------|-------------|-------------|------------|\n")
        for snr in sorted(df['input_snr'].unique()):
            sub = df[df['input_snr'] == snr]
            snr_n = sub['out_snr_noisy'].mean()
            snr_e = sub['out_snr_enhanced'].mean()
            stoi_n = sub['stoi_noisy'].mean()
            stoi_e = sub['stoi_enhanced'].mean()
            pesq_n = sub['pesq_noisy'].mean()
            pesq_e = sub['pesq_enhanced'].mean()
            sdr_i = sub['sisdr_improvement'].mean()
            p_snr = "✅" if snr_e > targets['out_snr'] else "❌"
            p_stoi = "✅" if stoi_e > targets['stoi'] else "❌"
            p_pesq = "✅" if pesq_e > targets['pesq'] else "❌"
            f.write(f"| {snr} dB | {snr_n:.1f} -> {snr_e:.1f} {p_snr} | {stoi_n:.2f} -> {stoi_e:.2f} {p_stoi} | {pesq_n:.2f} -> {pesq_e:.2f} {p_pesq} | {sdr_i:.1f} dB |\n")
            
    with open("results/per_category.md", "w") as f:
        f.write("# Results by Category\n\n")
        for cat in sorted(df['category'].unique()):
            f.write(f"## {cat}\n")
            f.write("| Input SNR | Output SNR (N->E) | STOI (N->E) | PESQ (N->E) | SI-SDR Imp |\n")
            f.write("|-----------|-------------------|-------------|-------------|------------|\n")
            subcat = df[df['category'] == cat]
            for snr in sorted(subcat['input_snr'].unique()):
                sub = subcat[subcat['input_snr'] == snr]
                snr_n = sub['out_snr_noisy'].mean()
                snr_e = sub['out_snr_enhanced'].mean()
                stoi_n = sub['stoi_noisy'].mean()
                stoi_e = sub['stoi_enhanced'].mean()
                pesq_n = sub['pesq_noisy'].mean()
                pesq_e = sub['pesq_enhanced'].mean()
                sdr_i = sub['sisdr_improvement'].mean()
                f.write(f"| {snr} dB | {snr_n:.1f} -> {snr_e:.1f} | {stoi_n:.2f} -> {stoi_e:.2f} | {pesq_n:.2f} -> {pesq_e:.2f} | {sdr_i:.1f} dB |\n")
            f.write("\n")
            
    with open("results/slide_table.md", "w") as f:
        f.write("| Input SNR | STOI (T>0.85) | PESQ (T>2.5) | Out SNR (T>15dB) |\n")
        f.write("|-----------|---------------|--------------|------------------|\n")
        for snr in [5, 10, 15]:
            sub = df[df['input_snr'] == snr]
            if len(sub) == 0: continue
            stoi_e = sub['stoi_enhanced'].mean()
            pesq_e = sub['pesq_enhanced'].mean()
            snr_e = sub['out_snr_enhanced'].mean()
            p_stoi = "✅" if stoi_e > targets['stoi'] else "❌"
            p_pesq = "✅" if pesq_e > targets['pesq'] else "❌"
            p_snr = "✅" if snr_e > targets['out_snr'] else "❌"
            f.write(f"| {snr} dB | {stoi_e:.2f} {p_stoi} | {pesq_e:.2f} {p_pesq} | {snr_e:.1f} {p_snr} |\n")

    fig, ax1 = plt.subplots(figsize=(8,5))
    snrs = sorted(df['input_snr'].unique())
    stoi_means = [df[df['input_snr'] == s]['stoi_enhanced'].mean() for s in snrs]
    pesq_means = [df[df['input_snr'] == s]['pesq_enhanced'].mean() for s in snrs]
    ax1.set_xlabel('Input SNR (dB)')
    ax1.set_ylabel('STOI', color='tab:blue')
    ax1.plot(snrs, stoi_means, marker='o', color='tab:blue', label='STOI')
    ax1.tick_params(axis='y', labelcolor='tab:blue')
    ax1.axhline(y=targets['stoi'], color='tab:blue', linestyle='--', alpha=0.5, label='STOI Target')
    ax2 = ax1.twinx()
    ax2.set_ylabel('PESQ', color='tab:orange')
    ax2.plot(snrs, pesq_means, marker='s', color='tab:orange', label='PESQ')
    ax2.tick_params(axis='y', labelcolor='tab:orange')
    ax2.axhline(y=targets['pesq'], color='tab:orange', linestyle='--', alpha=0.5, label='PESQ Target')
    fig.tight_layout()
    plt.title('Performance vs PS Targets')
    fig.legend(loc="upper left", bbox_to_anchor=(0.1,0.9))
    plt.savefig("results/targets_vs_measured.png")
    plt.close()

if __name__ == "__main__":
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = ComplexCRN_Wrapper().to(device)
    checkpoint_path = "checkpoints/dtln/best.pt"
    if os.path.exists(checkpoint_path):
        state_dict = torch.load(checkpoint_path, map_location=device)
        new_state_dict = {}
        for k, v in state_dict.items():
            if not k.startswith("core."): new_state_dict["core." + k] = v
            else: new_state_dict[k] = v
        model.load_state_dict(new_state_dict)
    
    df = run_evaluation(model)
    if not df.empty:
        generate_reports(df)
