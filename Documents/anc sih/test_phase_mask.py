import sys
import os
import torch
import numpy as np
import scipy.io.wavfile as wavfile
import scipy.signal
import soundfile as sf

sys.path.append(os.path.expanduser("~/sih26052_edge"))
from app.anc_stream import ANCStream

IN_WAV = "/home/shreyas/sih26052_edge/audio/final_test2_input_20260930_154218.wav"
OUT_DIR = "/home/shreyas/sih26052_edge/audio/phase_test"
CONFIG_PATH = "/home/shreyas/sih26052_edge/config/config.json"

os.makedirs(OUT_DIR, exist_ok=True)

rate, in_data = wavfile.read(IN_WAV)
# For metric comparisons, normalize using int16 range
in_data_norm = in_data.astype(np.float32) / 32768.0

# ---------------------------------------------------------
# METRIC FUNCTIONS
# ---------------------------------------------------------
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
    # Truncate to match lengths
    min_len = min(len(ref), len(deg))
    ref = ref[:min_len]
    deg = deg[:min_len]
    
    corr = scipy.signal.correlate(deg, ref, mode='full')
    lags = scipy.signal.correlation_lags(len(deg), len(ref), mode='full')
    peaks, _ = scipy.signal.find_peaks(corr, height=np.max(corr)*0.3, distance=160)
    
    peak_16 = 0.0
    for l, v in zip(lags[peaks], corr[peaks]):
        if abs(l - 256) <= 5:
            peak_16 = max(peak_16, v)
            
    # Speech corr at lag 0 (approximate)
    speech_corr = np.corrcoef(ref, deg)[0, 1] if np.std(deg) > 1e-6 else 0.0
    
    noise = deg - ref
    snr = 10 * np.log10(np.sum(ref**2) / (np.sum(noise**2) + 1e-10))
    sisdr = snr # Approximate SI-SDR
    
    return peak_16, speech_corr, snr, sisdr

# ---------------------------------------------------------
# TESTS
# ---------------------------------------------------------
stream = ANCStream(CONFIG_PATH)
original_core = stream.model.core

# We will collect phase statistics during Test A
phase_stats = []

class CurrentModelWrapper(torch.nn.Module):
    def __init__(self, core):
        super().__init__()
        self.core = core
    def forward(self, features, h_in, c_in):
        mr, mi, h_out, c_out, mag, phase = self.core(features, h_in, c_in)
        phase_stats.append(phase.detach().cpu().numpy())
        return mr, mi, h_out, c_out, mag, phase

class PhaseZeroWrapper(torch.nn.Module):
    def __init__(self, core):
        super().__init__()
        self.core = core
    def forward(self, features, h_in, c_in):
        _, _, h_out, c_out, mag, phase = self.core(features, h_in, c_in)
        mr_0 = mag
        mi_0 = torch.zeros_like(mag)
        return mr_0, mi_0, h_out, c_out, mag, phase

class IdentityWrapper(torch.nn.Module):
    def __init__(self, core):
        super().__init__()
        self.core = core
    def forward(self, features, h_in, c_in):
        _, _, h_out, c_out, _, _ = self.core(features, h_in, c_in)
        mag = torch.ones_like(features[..., :257])
        phase = torch.zeros_like(mag)
        return mag, phase, h_out, c_out, mag, phase

results = []

def run_test(name, wrapper_cls, out_filename):
    print(f"Running {name}...")
    stream.model.core = wrapper_cls(original_core)
    stream.reset_state()
    
    out_path = os.path.join(OUT_DIR, out_filename)
    stream.run_file(IN_WAV, out_path)
    
    out_audio, sr = sf.read(out_path)
    # sf.read returns float64 in [-1.0, 1.0]
    out_data = out_audio.astype(np.float32)
    
    rms = np.sqrt(np.mean(out_data**2))
    peak = np.max(np.abs(out_data))
    tail = calc_decay(out_data, sr)
    p16, scorr, snr, sisdr = calc_metrics(in_data_norm, out_data)
    
    has_nan = bool(np.isnan(out_data).any())
    has_inf = bool(np.isinf(out_data).any())
    
    results.append({
        "Test": name,
        "peak_16": p16,
        "tail": tail,
        "rms": rms,
        "peak": peak,
        "nan_inf": has_nan or has_inf,
        "scorr": scorr,
        "snr": snr,
        "sisdr": sisdr
    })

run_test("CURRENT", CurrentModelWrapper, "phase_test_current.wav")
run_test("PHASE_ZERO", PhaseZeroWrapper, "phase_test_zero.wav")
run_test("IDENTITY", IdentityWrapper, "phase_test_identity.wav")

# Calculate Phase Statistics
all_phases = np.concatenate(phase_stats)
p_mean = np.mean(all_phases)
p_std = np.std(all_phases)
p_min = np.min(all_phases)
p_max = np.max(all_phases)
p_med_abs = np.median(np.abs(all_phases))

p_gt_01 = np.mean(np.abs(all_phases) > 0.1) * 100
p_gt_05 = np.mean(np.abs(all_phases) > 0.5) * 100
p_gt_10 = np.mean(np.abs(all_phases) > 1.0) * 100

print("\n--- RESULTS TABLE ---")
print("Test | 16ms peak | tail energy | RMS | speech corr | SI-SDR | SNR")
for r in results:
    print(f"{r['Test']} | {r['peak_16']:.2f} | {r['tail']:.6f} | {r['rms']:.6f} | {r['scorr']:.4f} | {r['sisdr']:.2f} | {r['snr']:.2f}")

print("\n--- PHASE STATISTICS ---")
print(f"Mean: {p_mean:.6f} rad")
print(f"Std: {p_std:.6f} rad")
print(f"Min: {p_min:.6f} rad")
print(f"Max: {p_max:.6f} rad")
print(f"Median Absolute: {p_med_abs:.6f} rad")
print(f"Bins > 0.1 rad: {p_gt_01:.2f}%")
print(f"Bins > 0.5 rad: {p_gt_05:.2f}%")
print(f"Bins > 1.0 rad: {p_gt_10:.2f}%")
