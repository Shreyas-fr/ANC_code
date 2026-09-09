import torch
import torchaudio
import argparse
from pesq import pesq
from pystoi import stoi
import numpy as np

def si_sdr(reference, estimation):
    eps = 1e-8
    reference = reference - np.mean(reference)
    estimation = estimation - np.mean(estimation)
    reference_energy = np.sum(reference ** 2)
    
    optimal_scaling = np.sum(reference * estimation) / (reference_energy + eps)
    projection = optimal_scaling * reference
    noise = estimation - projection
    
    ratio = np.sum(projection ** 2) / (np.sum(noise ** 2) + eps)
    return 10 * np.log10(ratio + eps)

def evaluate_metrics(clean_path, noisy_path, enhanced_path, sr=16000):
    clean, sr_c = torchaudio.load(clean_path)
    noisy, sr_n = torchaudio.load(noisy_path)
    enhanced, sr_e = torchaudio.load(enhanced_path)
    
    # Resample if necessary (assuming 16k based on pipeline)
    clean_np = clean.squeeze().numpy()
    noisy_np = noisy.squeeze().numpy()
    enhanced_np = enhanced.squeeze().numpy()
    
    # Match lengths
    min_len = min(len(clean_np), len(noisy_np), len(enhanced_np))
    clean_np = clean_np[:min_len]
    noisy_np = noisy_np[:min_len]
    enhanced_np = enhanced_np[:min_len]
    
    # STOI
    noisy_stoi = stoi(clean_np, noisy_np, sr, extended=False)
    enhanced_stoi = stoi(clean_np, enhanced_np, sr, extended=False)
    
    # PESQ
    try:
        noisy_pesq = pesq(sr, clean_np, noisy_np, 'wb')
        enhanced_pesq = pesq(sr, clean_np, enhanced_np, 'wb')
    except Exception as e:
        noisy_pesq = 0.0
        enhanced_pesq = 0.0
        print(f"PESQ error (likely audio too short or fully silent): {e}")
        
    # SI-SDR
    noisy_sisdr = si_sdr(clean_np, noisy_np)
    enhanced_sisdr = si_sdr(clean_np, enhanced_np)
    
    print("\n--- Evaluation Metrics ---")
    print(f"STOI   | Noisy: {noisy_stoi:.4f} -> Enhanced: {enhanced_stoi:.4f}")
    print(f"PESQ   | Noisy: {noisy_pesq:.4f} -> Enhanced: {enhanced_pesq:.4f}")
    print(f"SI-SDR | Noisy: {noisy_sisdr:.2f} dB -> Enhanced: {enhanced_sisdr:.2f} dB")
    print("--------------------------\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", required=True)
    parser.add_argument("--noisy", required=True)
    parser.add_argument("--enhanced", required=True)
    args = parser.parse_args()
    
    evaluate_metrics(args.clean, args.noisy, args.enhanced)
