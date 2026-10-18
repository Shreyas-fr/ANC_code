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
from src.enhance.stateful_polar_lstm import StatefulPolarLSTM_Wrapper
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
        
    ckpt_path = "runs/sih26052_polar_gpu/checkpoint_25000.pt"
    if not os.path.exists(ckpt_path):
        print(f"CRITICAL: BEST CHECKPOINT NOT FOUND AT {ckpt_path}")
        sys.exit(1)
        
    device = torch.device('cpu') 
    model = StatefulPolarLSTM_Wrapper().to(device)
    model.load_state_dict(torch.load(ckpt_path, map_location=device, weights_only=False))
    model.eval()
    
    params = sum(p.numel() for p in model.parameters())
    print(f"Parameters: {params}")
    assert params == 1448962, "Parameter count mismatch"
    
    _ = model(torch.randn(1, 16000))
    
    random.seed(12345)
    with open("data/clean_manifests/clean_test.csv", "r") as f:
        clean_records = list(csv.DictReader(f))
    with open("data/clean_manifests/noise_test.csv", "r") as f:
        noise_records = list(csv.DictReader(f))
    with open("data/clean_manifests/SIH_GOLD_TEST_manifest.csv", "r") as f:
        gold_records = list(csv.DictReader(f))
        
    results = []
    
    timing_stft = 0.0
    timing_model = 0.0
    timing_istft = 0.0
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
        
        # Latency tracking inside custom forward
        hop_length = model.hop_length
        n_fft = model.n_fft
        
        with torch.no_grad():
            t0 = time.perf_counter()
            stft = torch.stft(mix_wav, n_fft=model.n_fft, hop_length=model.hop_length, window=model.window, return_complex=True, center=False)
            t1 = time.perf_counter()
            features = torch.cat([stft.transpose(1, 2).real, stft.transpose(1, 2).imag], dim=-1)
            h_in = torch.zeros(2, 1, 256)
            c_in = torch.zeros(2, 1, 256)
            mr, mi, _, _, mag, phase = model.core(features, h_in, c_in)
            mask_complex = torch.complex(mr, mi).transpose(1, 2)
            enh_stft = stft * mask_complex
            t2 = time.perf_counter()
            from src.enhance.stateful_lstm import causal_istft
            enh_wav = causal_istft(enh_stft, model.n_fft, model.hop_length, model.window)
            t3 = time.perf_counter()
            L_out = (stft.shape[-1] - 1) * model.hop_length + model.n_fft
            
        timing_stft += (t1 - t0)
        timing_model += (t2 - t1)
        timing_istft += (t3 - t2)
        timing_frames += stft.shape[-1]
        
        enh_wav = enh_wav.squeeze(0)
        mix_aligned = mix_wav[0, :L_out]
        clean_aligned = true_clean[0, :L_out]
        noise_aligned = true_noise[0, :L_out]
        
        c_np = clean_aligned.numpy()
        m_np = mix_aligned.numpy()
        e_np = enh_wav.numpy()
        n_np = mix_aligned.numpy() - clean_aligned.numpy()
        
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
        mask_real = []
        mask_imag = []
        with torch.no_grad():
            for t in range(stft.shape[-1]):
                feat_t = features[:, t:t+1, :]
                h_in = torch.zeros(2, 1, 256)
                c_in = torch.zeros(2, 1, 256)
                mr, mi, _, _, _, _ = model.core(feat_t, h_in, c_in)
                mask_real.append(mr)
                mask_imag.append(mi)
        
        mask_real = torch.cat(mask_real, dim=1)
        mask_imag = torch.cat(mask_imag, dim=1)
        mask_complex_res = torch.complex(mask_real, mask_imag).transpose(1, 2)
        enh_stft_reset = stft * mask_complex_res
        enh_wav_reset = causal_istft(enh_stft_reset, n_fft, hop_length, model.window).squeeze(0)
        e_res_np = enh_wav_reset.numpy()
        out_sisdr_reset = si_sdr(c_np, e_res_np)
        out_snr_reset = compute_snr(clean_aligned.unsqueeze(0), enh_wav_reset.unsqueeze(0) - clean_aligned.unsqueeze(0))
        try:
            out_pesq_reset = pesq(16000, c_np, e_res_np, 'wb')
        except: out_pesq_reset = 0.0
        out_stoi_reset = stoi(c_np, e_res_np, 16000, extended=False)
        
        results.append({
            "id": i,
            "noise_class": gold_records[i]["parent_noise_class"],
            "in_snr": in_snr,
            "out_snr": out_snr,
            "in_sisdr": in_sisdr,
            "out_sisdr": out_sisdr,
            "out_sisdr_reset": out_sisdr_reset,
            "out_snr_reset": out_snr_reset,
            "out_pesq_reset": out_pesq_reset,
            "out_stoi_reset": out_stoi_reset,
            "in_pesq": in_pesq,
            "out_pesq": out_pesq,
            "in_stoi": in_stoi,
            "out_stoi": out_stoi,
            "mag": mag.numpy(),
            "phase": phase.numpy(),
            "corr": np.corrcoef(e_np, c_np)[0,1],
            "rms_out": np.sqrt(np.mean(e_np**2)),
            "rms_in": np.sqrt(np.mean(m_np**2))
        })
        
    torch.save(results, "runs/sih26052_polar_gpu/gold_results.pt")
    
    # Aggregation
    df = {k: np.array([r[k] for r in results]) for k in ["in_snr", "out_snr", "in_sisdr", "out_sisdr", "in_pesq", "out_pesq", "in_stoi", "out_stoi", "corr", "rms_in", "rms_out"]}
    
    imp = {
        "snr": df["out_snr"] - df["in_snr"],
        "sisdr": df["out_sisdr"] - df["in_sisdr"],
        "pesq": df["out_pesq"] - df["in_pesq"],
        "stoi": df["out_stoi"] - df["in_stoi"]
    }
    
    def print_stats(name, arr):
        print(f"{name}: Mean={np.mean(arr):.4f}, Median={np.median(arr):.4f}, Std={np.std(arr):.4f}, Min={np.min(arr):.4f}, Max={np.max(arr):.4f}")

    print("\n=== AGGREGATE METRICS ===")
    print_stats("INPUT SNR", df["in_snr"])
    print_stats("OUTPUT SNR", df["out_snr"])
    print_stats("SNR DELTA", imp["snr"])
    
    print_stats("INPUT SI-SDR", df["in_sisdr"])
    print_stats("OUTPUT SI-SDR", df["out_sisdr"])
    print_stats("SI-SDR DELTA", imp["sisdr"])
    
    print_stats("INPUT STOI", df["in_stoi"])
    print_stats("OUTPUT STOI", df["out_stoi"])
    print_stats("STOI DELTA", imp["stoi"])
    
    print_stats("INPUT PESQ", df["in_pesq"])
    print_stats("OUTPUT PESQ", df["out_pesq"])
    print_stats("PESQ DELTA", imp["pesq"])
    
    print(f"COUNT_IMPROVED_SNR={np.sum(imp['snr'] > 0)}")
    print(f"COUNT_DEGRADED_SNR={np.sum(imp['snr'] < 0)}")
    print(f"COUNT_UNCHANGED_SNR={np.sum(imp['snr'] == 0)}")
    
    print(f"\n=== SIH TARGET CHECK ===")
    targets_met = 0
    targets_met += np.sum(df["out_snr"] > 15.0)
    targets_met += np.sum(df["out_stoi"] > 0.85)
    targets_met += np.sum(df["out_pesq"] > 2.5)
    print(f"Output SNR > 15 dB: {np.sum(df['out_snr'] > 15.0)}")
    print(f"Output STOI > 0.85: {np.sum(df['out_stoi'] > 0.85)}")
    print(f"Output PESQ > 2.5: {np.sum(df['out_pesq'] > 2.5)}")
    
    print(f"\n=== NOISE SUBSETS ===")
    classes = set([r["noise_class"] for r in results])
    for cls in classes:
        subs = [r for r in results if r["noise_class"] == cls]
        print(f"[{cls.upper()}] N={len(subs)}")
        print(f"  Input SNR: {np.mean([s['in_snr'] for s in subs]):.4f} | Output SNR: {np.mean([s['out_snr'] for s in subs]):.4f} | Delta: {np.mean([s['out_snr']-s['in_snr'] for s in subs]):.4f}")
        print(f"  SI-SDR Delta: {np.mean([s['out_sisdr']-s['in_sisdr'] for s in subs]):.4f}")
        print(f"  STOI Delta: {np.mean([s['out_stoi']-s['in_stoi'] for s in subs]):.4f}")
        print(f"  PESQ Delta: {np.mean([s['out_pesq']-s['in_pesq'] for s in subs]):.4f}")

    print(f"\n=== SNR BINS ===")
    bins = [(float('-inf'), 0), (0, 5), (5, 10), (10, 15), (15, float('inf'))]
    for b_min, b_max in bins:
        subs = [r for r in results if b_min <= r["in_snr"] < b_max]
        if not subs: continue
        print(f"[SNR {b_min} to {b_max}] N={len(subs)}")
        print(f"  SNR Delta: {np.mean([s['out_snr']-s['in_snr'] for s in subs]):.4f}")
        print(f"  SI-SDR Delta: {np.mean([s['out_sisdr']-s['in_sisdr'] for s in subs]):.4f}")
        
    print(f"\n=== STATEFUL VS FRAME RESET ===")
    res_sdr = np.mean([r["out_sisdr_reset"] for r in results])
    res_snr = np.mean([r["out_snr_reset"] for r in results])
    res_stoi = np.mean([r["out_stoi_reset"] for r in results])
    res_pesq = np.mean([r["out_pesq_reset"] for r in results])
    
    print(f"Stateful SI-SDR: {df['out_sisdr'].mean():.4f} | Reset SI-SDR: {res_sdr:.4f} | Delta: {df['out_sisdr'].mean() - res_sdr:.4f}")
    print(f"Stateful SNR: {df['out_snr'].mean():.4f} | Reset SNR: {res_snr:.4f} | Delta: {df['out_snr'].mean() - res_snr:.4f}")
    print(f"Stateful STOI: {df['out_stoi'].mean():.4f} | Reset STOI: {res_stoi:.4f} | Delta: {df['out_stoi'].mean() - res_stoi:.4f}")
    print(f"Stateful PESQ: {df['out_pesq'].mean():.4f} | Reset PESQ: {res_pesq:.4f} | Delta: {df['out_pesq'].mean() - res_pesq:.4f}")
    
    print(f"\n=== MASK HEALTH ===")
    all_mags = np.concatenate([r["mag"].flatten() for r in results])
    all_phases = np.concatenate([r["phase"].flatten() for r in results])
    print(f"Mag Mean: {all_mags.mean():.4f}, Std: {all_mags.std():.4f}, Min: {all_mags.min():.4f}, Max: {all_mags.max():.4f}")
    print(f"Phase Mean: {all_phases.mean():.4f}, Std: {all_phases.std():.4f}, Min: {all_phases.min():.4f}, Max: {all_phases.max():.4f}")
    print(f"Mag > 1.0: {(all_mags > 1.0).mean():.4f}")
    print(f"Mag > 1.5: {(all_mags > 1.5).mean():.4f}")
    print(f"Mag at Cap: {(all_mags >= 1.99).mean():.4f}")
    print(f"RMS Ratio: {df['rms_out'].mean() / df['rms_in'].mean():.4f}")
    print(f"Speech Correlation: {df['corr'].mean():.4f}")
    
    print(f"\n=== LATENCY (CPU MEASURED) ===")
    print("EMBEDDED_HARDWARE_MEASURED=NO")
    print(f"STFT: {timing_stft*1000/timing_frames:.4f} ms/frame")
    print(f"MODEL: {timing_model*1000/timing_frames:.4f} ms/frame")
    print(f"ISTFT: {timing_istft*1000/timing_frames:.4f} ms/frame")
    print(f"TOTAL: {(timing_stft+timing_model+timing_istft)*1000/timing_frames:.4f} ms/frame")
    
    print(f"\n=== BEST/WORST CASES ===")
    snr_sorted = sorted(results, key=lambda x: x["out_snr"] - x["in_snr"])
    print("WORST 5 SNR DELTAS:")
    for r in snr_sorted[:5]: print(f"  ID {r['id']} ({r['noise_class']}): {r['out_snr'] - r['in_snr']:.4f} dB")
    print("BEST 5 SNR DELTAS:")
    for r in snr_sorted[-5:]: print(f"  ID {r['id']} ({r['noise_class']}): {r['out_snr'] - r['in_snr']:.4f} dB")
    
    stoi_sorted = sorted(results, key=lambda x: x["out_stoi"] - x["in_stoi"])
    print("WORST 5 STOI DELTAS:")
    for r in stoi_sorted[:5]: print(f"  ID {r['id']} ({r['noise_class']}): {r['out_stoi'] - r['in_stoi']:.4f}")
    print("BEST 5 STOI DELTAS:")
    for r in stoi_sorted[-5:]: print(f"  ID {r['id']} ({r['noise_class']}): {r['out_stoi'] - r['in_stoi']:.4f}")

if __name__ == "__main__":
    evaluate()
