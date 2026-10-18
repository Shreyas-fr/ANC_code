import os
import csv
import torch
import torchaudio
import numpy as np
import random
import time
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.enhance.stateful_lstm import StatefulComplexLSTM_Wrapper
from src.enhance.losses import EnhancementLoss

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

def main():
    device = torch.device('cpu')
    model = StatefulComplexLSTM_Wrapper().to(device)
    model.load_state_dict(torch.load("runs/sih26052_full/best.pt", map_location=device))
    model.eval()
    
    random.seed(12345)
    with open("data/clean_manifests/clean_test.csv", "r") as f:
        clean_records = list(csv.DictReader(f))
    with open("data/clean_manifests/noise_test.csv", "r") as f:
        noise_records = list(csv.DictReader(f))
    with open("data/clean_manifests/SIH_GOLD_TEST_manifest.csv", "r") as f:
        gold_records = list(csv.DictReader(f))
        
    rms_in, rms_out, rms_clean = [], [], []
    corr_in_c, corr_out_c = [], []
    res_in, res_out = [], []
    
    mask_reals, mask_imags, mask_mags, mask_phases = [], [], [], []
    t_mask_mags = []
    
    for i in range(100):
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
        
        with torch.no_grad():
            stft = torch.stft(mix_wav, n_fft=512, hop_length=256, window=model.window, return_complex=True, center=False)
            features = torch.cat([stft.transpose(1, 2).real, stft.transpose(1, 2).imag], dim=-1)
            h_in = torch.zeros(2, 1, 256)
            c_in = torch.zeros(2, 1, 256)
            mr, mi, _, _ = model.core(features, h_in, c_in)
            enh_wav, L_out = model(mix_wav)
        
        mc = torch.complex(mr, mi)
        mask_mags.append(torch.abs(mc).flatten().numpy())
        mask_phases.append(torch.angle(mc).flatten().numpy())
        mask_reals.append(mr.flatten().numpy())
        mask_imags.append(mi.flatten().numpy())
        
        c_al = true_clean[:, :L_out]
        m_al = mix_wav[:, :L_out]
        e_al = enh_wav
        
        r_i = torch.sqrt(torch.mean(m_al**2)).item()
        r_c = torch.sqrt(torch.mean(c_al**2)).item()
        r_o = torch.sqrt(torch.mean(e_al**2)).item()
        
        rms_in.append(r_i)
        rms_clean.append(r_c)
        rms_out.append(r_o)
        
        c_np = c_al.squeeze().numpy()
        m_np = m_al.squeeze().numpy()
        e_np = e_al.squeeze().numpy()
        
        corr_in_c.append(np.corrcoef(m_np, c_np)[0, 1])
        corr_out_c.append(np.corrcoef(e_np, c_np)[0, 1])
        
        res_in.append(torch.sqrt(torch.mean((m_al - c_al)**2)).item())
        res_out.append(torch.sqrt(torch.mean((e_al - c_al)**2)).item())
        
        # Target Mask Audit
        stft_c = torch.stft(c_al, n_fft=512, hop_length=256, window=model.window, return_complex=True, center=False)
        stft_m = torch.stft(m_al, n_fft=512, hop_length=256, window=model.window, return_complex=True, center=False)
        # S / X
        tm = stft_c / (stft_m + 1e-8)
        t_mask_mags.append(torch.abs(tm).flatten().numpy())

    # Aggregate
    print("=== 1. OUTPUT GAIN / ENERGY AUDIT ===")
    r_i_arr = np.array(rms_in)
    r_c_arr = np.array(rms_clean)
    r_o_arr = np.array(rms_out)
    
    r_oi = r_o_arr / r_i_arr
    r_oc = r_o_arr / r_c_arr
    
    print(f"RMS(input): mean={r_i_arr.mean():.4f}")
    print(f"RMS(clean): mean={r_c_arr.mean():.4f}")
    print(f"RMS(output): mean={r_o_arr.mean():.4f}")
    print(f"RMS(output)/RMS(input): mean={r_oi.mean():.4f}, std={r_oi.std():.4f}")
    print(f"RMS(output)/RMS(clean): mean={r_oc.mean():.4f}, std={r_oc.std():.4f}")

    print("\n=== 2. SPEECH PRESERVATION AUDIT ===")
    print(f"Corr(input, clean): mean={np.mean(corr_in_c):.4f}")
    print(f"Corr(output, clean): mean={np.mean(corr_out_c):.4f}")
    print(f"Res(input - clean): mean={np.mean(res_in):.4f}")
    print(f"Res(output - clean): mean={np.mean(res_out):.4f}")

    print("\n=== 3. COMPLEX MASK AUDIT ===")
    mm = np.concatenate(mask_mags)
    mp = np.concatenate(mask_phases)
    mr = np.concatenate(mask_reals)
    mi = np.concatenate(mask_imags)
    print(f"Mask Real: mean={mr.mean():.4f}, std={mr.std():.4f}, min={mr.min():.4f}, max={mr.max():.4f}")
    print(f"Mask Imag: mean={mi.mean():.4f}, std={mi.std():.4f}, min={mi.min():.4f}, max={mi.max():.4f}")
    print(f"Mask Mag: mean={mm.mean():.4f}, std={mm.std():.4f}, min={mm.min():.4f}, max={mm.max():.4f}")
    print(f"Mask Phase: mean={mp.mean():.4f}, std={mp.std():.4f}")
    print(f"Mag Percentiles: 10%={np.percentile(mm, 10):.4f}, 50%={np.percentile(mm, 50):.4f}, 90%={np.percentile(mm, 90):.4f}, 99%={np.percentile(mm, 99):.4f}")

    print("\n=== 6. TARGET MASK AUDIT ===")
    tm = np.concatenate(t_mask_mags)
    print(f"Target Mag: mean={tm.mean():.4f}, median={np.median(tm):.4f}, std={tm.std():.4f}")
    print(f"Target Mag Percentiles: 90%={np.percentile(tm, 90):.4f}, 99%={np.percentile(tm, 99):.4f}")
    print(f"Target Mag > 1: {np.mean(tm > 1.0)*100:.2f}%")
    print(f"Target Mag < 0.25: {np.mean(tm < 0.25)*100:.2f}%")
    print(f"Target Mag > 10: {np.mean(tm > 10.0)*100:.2f}%")
    
    # Load past results for SNR/Noise stats
    print("\n=== 7 & 8. SNR AND NOISE BREAKDOWN ===")
    res = torch.load("runs/sih26052_full/gold_results.pt", weights_only=False)
    
    def print_bin(name, fn):
        b = [r for r in res if fn(r)]
        if len(b) == 0: return
        snr_i = np.mean([r['in_snr'] for r in b])
        snr_o = np.mean([r['out_snr'] for r in b])
        sdr_i = np.mean([r['in_sisdr'] for r in b])
        sdr_o = np.mean([r['out_sisdr'] for r in b])
        print(f"[{name}] N={len(b)} | In SNR={snr_i:.2f}, Out SNR={snr_o:.2f}, Delta={snr_o-snr_i:.2f} | In SDR={sdr_i:.2f}, Out SDR={sdr_o:.2f}, Delta={sdr_o-sdr_i:.2f}")
        
    print_bin("< 0 dB", lambda r: r['in_snr'] < 0)
    print_bin("0 - 5 dB", lambda r: 0 <= r['in_snr'] < 5)
    print_bin("5 - 10 dB", lambda r: 5 <= r['in_snr'] < 10)
    print_bin("10 - 15 dB", lambda r: 10 <= r['in_snr'] < 15)
    print_bin(">= 15 dB", lambda r: r['in_snr'] >= 15)
    
    print()
    print_bin("Nonstationary", lambda r: r['noise_class'] == 'nonstationary')
    print_bin("Impulsive", lambda r: r['noise_class'] == 'impulsive')
    print_bin("Stationary", lambda r: r['noise_class'] == 'stationary')

if __name__ == "__main__":
    main()
