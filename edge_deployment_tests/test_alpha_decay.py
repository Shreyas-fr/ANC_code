import sys
import os
import wave
import json
import torch
import numpy as np
import scipy.io.wavfile as wavfile
import scipy.signal
import soundfile as sf

sys.path.append(os.path.expanduser("~/sih26052_edge"))
from app.anc_stream import ANCStream

IN_WAV = "/home/shreyas/sih26052_edge/audio/final_test2_input_20260930_154218.wav"
OUT_DIR = "/home/shreyas/sih26052_edge/audio/reverb_fix_test"
os.makedirs(OUT_DIR, exist_ok=True)
CONFIG_PATH = "/home/shreyas/sih26052_edge/config/config.json"

alphas = [1.00, 0.95, 0.90, 0.85, 0.80, 0.70, 0.50, 0.00]

def calc_decay(data, rate):
    hop = int(rate * 0.01)
    env = []
    for i in range(0, len(data) - hop, hop):
        env.append(np.sqrt(np.mean(data[i:i+hop]**2)))
    env = np.array(env)
    
    threshold = np.max(env) * 0.1
    active = env > threshold
    
    offsets = []
    for i in range(1, len(active)):
        if active[i-1] and not active[i]:
            offsets.append(i)
            
    decay_energy = []
    for off in offsets:
        if off + 50 < len(env):
            tail = env[off:off+50]
            decay_energy.append(np.sum(tail))
            
    return np.mean(decay_energy) if decay_energy else 0.0

def calc_metrics(ref, deg):
    # Cross correlation peak at 16 ms (16ms * 16kHz = 256 samples lag)
    # We'll just search around 16ms
    ref_sub = ref[:16000*10]
    deg_sub = deg[:16000*10]
    corr = scipy.signal.correlate(deg_sub, ref_sub, mode='full')
    lags = scipy.signal.correlation_lags(len(deg_sub), len(ref_sub), mode='full')
    peaks, _ = scipy.signal.find_peaks(corr, height=np.max(corr)*0.1, distance=16000*0.01)
    peak_lags = lags[peaks]
    peak_vals = corr[peaks]
    
    peak_16 = 0.0
    for l, v in zip(peak_lags, peak_vals):
        if abs(l - 256) <= 5: # Around 16ms
            peak_16 = max(peak_16, v)
            
    # Speech correlation (Pearson)
    active_ref = ref[np.abs(ref) > np.max(np.abs(ref))*0.05]
    active_deg = deg[np.abs(ref) > np.max(np.abs(ref))*0.05]
    speech_corr = np.corrcoef(active_ref, active_deg)[0, 1] if len(active_ref) > 0 else 0.0
    
    # SNR
    noise = ref - deg
    snr = 10 * np.log10(np.sum(ref**2) / (np.sum(noise**2) + 1e-8))
    
    # SI-SDR
    alpha_sdr = np.sum(deg * ref) / (np.sum(ref**2) + 1e-8)
    e_target = alpha_sdr * ref
    e_res = deg - e_target
    sisdr = 10 * np.log10(np.sum(e_target**2) / (np.sum(e_res**2) + 1e-8))
    
    return peak_16, speech_corr, snr, sisdr

print("Starting State Decay Experiment...")
rate, in_data_full = wavfile.read(IN_WAV)
in_data = in_data_full[:16000*10] # Process only 10 seconds
in_data_norm = in_data.astype(np.float32) / 32768.0

IN_WAV_10s = "/home/shreyas/sih26052_edge/audio/temp_10s.wav"
wavfile.write(IN_WAV_10s, rate, in_data)

results = []

stream = ANCStream(CONFIG_PATH)
class DecayingCore(torch.nn.Module):
    def __init__(self, core, alpha):
        super().__init__()
        self.core = core
        self.alpha = alpha
        self.count = 0
    def forward(self, features, h_in, c_in):
        if self.count < 3:
            print(f"DecayingCore [alpha={self.alpha}] input h_in sum: {h_in.sum().item():.4f}")
        h_dec = h_in * self.alpha
        c_dec = c_in * self.alpha
        res = self.core(features, h_dec, c_dec)
        if self.count < 3:
            print(f"DecayingCore output h_out sum: {res[2].sum().item():.4f}")
            self.count += 1
        return res

original_core = stream.model.core

for a in alphas:
    print(f"Processing alpha = {a:.2f}")
    
    stream.model.core = DecayingCore(original_core, a)
    stream.reset_state()
    
    out_path = os.path.join(OUT_DIR, f"diagnostic_alpha_{a:.2f}.wav")
    stream.run_file(IN_WAV_10s, out_path)
    
    rate, out_data = wavfile.read(out_path)
    out_data = out_data.astype(np.float32) / 32768.0
    
    rms = np.sqrt(np.mean(out_data**2))
    peak = np.max(np.abs(out_data))
    tail = calc_decay(out_data, rate)
    p16, scorr, snr, sisdr = calc_metrics(in_data_norm, out_data)
    
    results.append({
        "alpha": a,
        "peak16": p16,
        "tail": tail,
        "rms": rms,
        "peak": peak,
        "scorr": scorr,
        "sisdr": sisdr,
        "snr": snr
    })

print("\n--- RESULTS TABLE ---")
print("alpha | 16ms peak | tail energy | RMS | speech corr | SI-SDR | SNR | STOI")
for r in results:
    print(f"{r['alpha']:.2f} | {r['peak16']:.2f} | {r['tail']:.6f} | {r['rms']:.6f} | {r['scorr']:.4f} | {r['sisdr']:.2f} | {r['snr']:.2f} | N/A")
