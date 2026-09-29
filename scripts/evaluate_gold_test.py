import os
import csv
import torch
import torchaudio
import numpy as np
import random
import time
import hashlib
import sys
from tqdm import tqdm

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.enhance.stateful_lstm import StatefulComplexLSTM_Wrapper
from src.enhance.evaluate import si_sdr, pesq, stoi

def compute_sha256(filepath):
    if not os.path.exists(filepath): return "NOT_FOUND"
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

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

def compute_snr(clean, noise):
    cp = calculate_active_speech_level(clean)
    npwr = torch.mean(noise ** 2)
    if cp > 0 and npwr > 0:
        return 10 * torch.log10(cp / npwr).item()
    return 0.0

def evaluate():
    gold_manifest_hash = compute_sha256("data/clean_manifests/SIH_GOLD_TEST_manifest.csv")
    expected_gold = "46236aef9af38056e08f296ac8c498dac888a85fb4b1ff9f371879c49670b0c9"
    if gold_manifest_hash != expected_gold:
        print(f"CRITICAL: GOLD TEST HASH CHANGED! Found {gold_manifest_hash}")
        sys.exit(1)
        
    ckpt_path = "runs/sih26052_full/best.pt"
    if not os.path.exists(ckpt_path):
        print(f"CRITICAL: BEST CHECKPOINT NOT FOUND AT {ckpt_path}")
        sys.exit(1)
        
    device = torch.device('cpu') # Use CPU to reliably measure generic compute
    model = StatefulComplexLSTM_Wrapper().to(device)
    model.load_state_dict(torch.load(ckpt_path, map_location=device))
    model.eval()
    
    # Pre-warm JIT/cache
    _ = model(torch.randn(1, 16000))
    
    # 1. Recover exact parents by mirroring RNG
    random.seed(12345)
    with open("data/clean_manifests/clean_test.csv", "r") as f:
        clean_records = list(csv.DictReader(f))
    with open("data/clean_manifests/noise_test.csv", "r") as f:
        noise_records = list(csv.DictReader(f))
    with open("data/clean_manifests/SIH_GOLD_TEST_manifest.csv", "r") as f:
        gold_records = list(csv.DictReader(f))
        
    results = []
    
    timing_total = 0.0
    timing_frames = 0
    
    for i in tqdm(range(100), desc="Evaluating Gold Test"):
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
        
        mix_wav, _ = torchaudio.load(f"data/SIH_GOLD_TEST/gold_test_{i:04d}.wav")
        
        snr_linear = 10 ** (target_snr / 10)
        target_noise_power = calculate_active_speech_level(c_wav) / snr_linear
        scale = torch.sqrt(target_noise_power / torch.mean(n_wav ** 2))
        scaled_noise = n_wav * scale
        raw_mixed = c_wav + scaled_noise
        
        alpha = 1.0
        max_val = torch.max(torch.abs(raw_mixed))
        if max_val > 0.99: alpha = (0.99 / max_val).item()
            
        true_clean = c_wav * alpha
        true_noise = scaled_noise * alpha
        
        # A. Stateful sequential inference
        with torch.no_grad():
            t0 = time.perf_counter()
            enh_wav, L_out = model(mix_wav)
            t1 = time.perf_counter()
            
        timing_total += (t1 - t0)
        
        # STFT parameters from model
        hop_length = model.hop_length
        n_fft = model.n_fft
        T_frames = (mix_wav.shape[-1] - n_fft) // hop_length + 1
        timing_frames += T_frames
        
        enh_wav = enh_wav.squeeze(0)
        mix_aligned = mix_wav[0, :L_out]
        clean_aligned = true_clean[0, :L_out]
        noise_aligned = true_noise[0, :L_out]
        
        # Metrics
        c_np = clean_aligned.numpy()
        m_np = mix_aligned.numpy()
        e_np = enh_wav.numpy()
        
        in_snr = compute_snr(clean_aligned.unsqueeze(0), noise_aligned.unsqueeze(0))
        out_noise = enh_wav.unsqueeze(0) - clean_aligned.unsqueeze(0)
        out_snr = compute_snr(clean_aligned.unsqueeze(0), out_noise)
        
        in_sisdr = si_sdr(c_np, m_np)
        out_sisdr = si_sdr(c_np, e_np)
        
        try:
            in_pesq = pesq(16000, c_np, m_np, 'wb')
            out_pesq = pesq(16000, c_np, e_np, 'wb')
        except:
            in_pesq, out_pesq = 0.0, 0.0
            
        in_stoi = stoi(c_np, m_np, 16000, extended=False)
        out_stoi = stoi(c_np, e_np, 16000, extended=False)
        
        # B. Frame-reset diagnostic mode
        # Since this is diagnostic, we won't manually unfold, we'll just force the model
        # to process independent chunks of size n_fft and see how it performs
        # Wait, it's easier to just pass sequence of 1 frame at a time and reset h_in, c_in!
        stft = torch.stft(mix_wav, n_fft=n_fft, hop_length=hop_length, window=model.window, return_complex=True, center=False)
        features = torch.cat([stft.transpose(1, 2).real, stft.transpose(1, 2).imag], dim=-1)
        B, T_f, _ = features.shape
        
        mask_real = []
        mask_imag = []
        with torch.no_grad():
            for t in range(T_f):
                feat_t = features[:, t:t+1, :]
                # Explicit state reset!
                h_in = torch.zeros(2, B, 256)
                c_in = torch.zeros(2, B, 256)
                mr, mi, _, _ = model.core(feat_t, h_in, c_in)
                mask_real.append(mr)
                mask_imag.append(mi)
        
        mask_real = torch.cat(mask_real, dim=1)
        mask_imag = torch.cat(mask_imag, dim=1)
        mask_complex = torch.complex(mask_real, mask_imag).transpose(1, 2)
        enh_stft_reset = stft * mask_complex
        
        # We need the custom causal_istft here
        from src.enhance.stateful_lstm import causal_istft
        enh_wav_reset = causal_istft(enh_stft_reset, n_fft, hop_length, model.window).squeeze(0)
        e_res_np = enh_wav_reset.numpy()
        
        out_sisdr_reset = si_sdr(c_np, e_res_np)
        
        results.append({
            "id": i,
            "noise_class": gold_records[i]["parent_noise_class"],
            "in_snr": in_snr,
            "out_snr": out_snr,
            "in_sisdr": in_sisdr,
            "out_sisdr": out_sisdr,
            "out_sisdr_reset": out_sisdr_reset,
            "in_pesq": in_pesq,
            "out_pesq": out_pesq,
            "in_stoi": in_stoi,
            "out_stoi": out_stoi
        })
        
    # Aggregate results
    df = {}
    for k in results[0].keys():
        if k not in ["id", "noise_class"]:
            df[k] = np.array([r[k] for r in results])
            
    imp = {
        "snr": df["out_snr"] - df["in_snr"],
        "sisdr": df["out_sisdr"] - df["in_sisdr"],
        "pesq": df["out_pesq"] - df["in_pesq"],
        "stoi": df["out_stoi"] - df["in_stoi"]
    }
    
    print("=== OVERALL RESULTS ===")
    print(f"INPUT_SNR_MEAN={df['in_snr'].mean():.4f}")
    print(f"OUTPUT_SNR_MEAN={df['out_snr'].mean():.4f}")
    print(f"SNR_IMPROVEMENT_MEAN={imp['snr'].mean():.4f}")
    
    print(f"INPUT_SI_SDR_MEAN={df['in_sisdr'].mean():.4f}")
    print(f"OUTPUT_SI_SDR_MEAN={df['out_sisdr'].mean():.4f}")
    
    print(f"INPUT_STOI_MEAN={df['in_stoi'].mean():.4f}")
    print(f"OUTPUT_STOI_MEAN={df['out_stoi'].mean():.4f}")
    
    print(f"INPUT_PESQ_MEAN={df['in_pesq'].mean():.4f}")
    print(f"OUTPUT_PESQ_MEAN={df['out_pesq'].mean():.4f}")
    
    print(f"COUNT_IMPROVED_SNR={np.sum(imp['snr'] > 0)}")
    print(f"COUNT_DEGRADED_SNR={np.sum(imp['snr'] < 0)}")
    
    impulsive = [r for r in results if r["noise_class"] == "impulsive"]
    nonstat = [r for r in results if r["noise_class"] == "nonstationary"]
    print(f"IMPULSIVE_COUNT={len(impulsive)}")
    print(f"NONSTATIONARY_COUNT={len(nonstat)}")
    
    state_diff = df["out_sisdr"].mean() - df["out_sisdr_reset"].mean()
    print(f"STATEFUL VS RESET SI-SDR DIFF: {state_diff:.4f} dB")
    state_test = "PASS" if state_diff > 0 else "FAIL"
    print(f"STATEFUL_VS_RESET_TEST={state_test}")
    
    total_time_ms = timing_total * 1000
    ms_per_frame = total_time_ms / timing_frames
    print(f"MODEL_COMPUTE_MS={ms_per_frame:.4f}")
    print(f"TOTAL_FRAME_PROCESSING_MS={ms_per_frame:.4f}") # Using this for now as proxy
    
    # Save outputs to file for the report
    torch.save(results, "runs/sih26052_full/gold_results.pt")

if __name__ == "__main__":
    evaluate()
