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
OUT_DIR = "/home/shreyas/sih26052_edge/audio"
CONFIG_PATH = "/home/shreyas/sih26052_edge/config/config.json"

os.makedirs(OUT_DIR, exist_ok=True)

rate, in_data_int = wavfile.read(IN_WAV)
# For metric comparisons, normalize using int16 range
in_data_norm = in_data_int.astype(np.float32) / 32768.0

# ---------------------------------------------------------
# MATHEMATICAL CHECK
# ---------------------------------------------------------
window = np.hanning(512).astype(np.float32)

hann_1 = window.copy()
hann_2 = np.roll(window, 256)
sum_hann = hann_1 + hann_2

hann_sq_1 = window**2
hann_sq_2 = np.roll(window**2, 256)
sum_hann_sq = hann_sq_1 + hann_sq_2

print("==================================================")
print("CRITICAL CHECK - OVERLAP-ADD NORMALIZATION CURVE")
print("==================================================")
print(f"Hann[n] + Hann[n-256]:")
print(f"  Min:  {np.min(sum_hann):.6f}")
print(f"  Max:  {np.max(sum_hann):.6f}")
print(f"  Mean: {np.mean(sum_hann):.6f}")
print(f"Hann[n]^2 + Hann[n-256]^2:")
print(f"  Min:  {np.min(sum_hann_sq):.6f}")
print(f"  Max:  {np.max(sum_hann_sq):.6f}")
print(f"  Mean: {np.mean(sum_hann_sq):.6f}")
print("==================================================\n")

# ---------------------------------------------------------
# METRIC FUNCTIONS
# ---------------------------------------------------------
def calc_decay(data, rate):
    hop = int(rate * 0.01)
    env = []
    for i in range(0, len(data) - hop, hop):
        env.append(np.sqrt(np.mean(data[i:i+hop]**2)))
    env = np.array(env)
    
    if len(env) == 0:
        return 0.0
        
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
            
    diff = deg - ref
    max_err = np.max(np.abs(diff))
    mean_err = np.mean(np.abs(diff))
    
    snr = 10 * np.log10(np.sum(ref**2) / (np.sum(diff**2) + 1e-10))
    
    return peak_16, snr, max_err, mean_err

# ---------------------------------------------------------
# RECONSTRUCTION FRAMEWORKS
# ---------------------------------------------------------

stream = ANCStream(CONFIG_PATH)
original_core = stream.model.core
device = original_core.fc_mag.weight.device

class IdentityWrapper(torch.nn.Module):
    def __init__(self, core):
        super().__init__()
        self.core = core
    def forward(self, features, h_in, c_in):
        _, _, h_out, c_out, _, _ = self.core(features, h_in, c_in)
        mag = torch.ones_like(features[..., :257])
        phase = torch.zeros_like(mag)
        return mag, phase, h_out, c_out, mag, phase

def run_custom_processor(name, out_filename, use_identity=False, normalize_ola=False):
    print(f"Running {name}...")
    stream.reset_state()
    
    if use_identity:
        stream.model.core = IdentityWrapper(original_core)
    else:
        stream.model.core = original_core

    out_audio = []
    hop = 256
    
    # Custom OLA buffers
    window = np.hanning(512).astype(np.float32)
    in_buffer = np.zeros(512, dtype=np.float32)
    ola_sum = np.zeros(512, dtype=np.float32)
    window_sum = np.zeros(512, dtype=np.float32)
    
    # We will process in chunks manually to enforce normalize OLA if required
    audio_full = in_data_norm.copy()
    
    for i in range(0, len(audio_full), hop):
        chunk = audio_full[i:i+hop]
        if len(chunk) < hop:
            chunk = np.pad(chunk, (0, hop - len(chunk)))
            
        in_buffer[:256] = in_buffer[256:]
        in_buffer[256:] = chunk
        
        frame = in_buffer * window
        stft = np.fft.rfft(frame)
        
        # Neural Processing
        features = np.concatenate([stft.real, stft.imag])
        input_t = torch.tensor(features, dtype=torch.float32).unsqueeze(0).unsqueeze(0).to(device)
        
        with torch.no_grad():
            if stream.h is None:
                stream.h = torch.zeros(2, 1, 256, device=device)
                stream.c = torch.zeros(2, 1, 256, device=device)
            mr, mi, stream.h, stream.c, _, _ = stream.model.core(input_t, stream.h, stream.c)
            
        mr = mr.squeeze().cpu().numpy()
        mi = mi.squeeze().cpu().numpy()
        
        # Apply mask
        mask = mr + 1j * mi
        enh_stft = stft * mask
        
        # iSTFT
        enh_frame = np.fft.irfft(enh_stft, n=512) * window
        
        # OLA
        if normalize_ola:
            ola_sum += enh_frame
            window_sum += window**2 # Because window was applied twice (once at STFT, once at iSTFT)
            
            # Extract 256 samples
            out_chunk = ola_sum[:256] / np.maximum(window_sum[:256], 1e-7)
            
            # Shift buffers
            ola_sum[:256] = ola_sum[256:]
            ola_sum[256:] = 0.0
            window_sum[:256] = window_sum[256:]
            window_sum[256:] = 0.0
            
            out_audio.extend(out_chunk)
        else:
            # Use EXACTLY production logic (un-normalized)
            ola_sum[:256] += enh_frame[:256]
            out_chunk = ola_sum[:256].copy()
            ola_sum[:256] = ola_sum[256:] + enh_frame[256:]
            ola_sum[256:] = 0.0
            
            out_audio.extend(out_chunk)
            
    out_audio = np.array(out_audio, dtype=np.float32)[:len(audio_full)]
    
    out_path = os.path.join(OUT_DIR, out_filename)
    sf.write(out_path, out_audio, rate)
    
    rms = np.sqrt(np.mean(out_audio**2))
    peak = np.max(np.abs(out_audio))
    tail = calc_decay(out_audio, rate)
    p16, snr, max_err, mean_err = calc_metrics(in_data_norm, out_audio)
    
    has_nan = bool(np.isnan(out_audio).any())
    has_inf = bool(np.isinf(out_audio).any())
    
    return {
        "Test": name,
        "rms": float(rms),
        "peak": float(peak),
        "nan_inf": has_nan or has_inf,
        "peak_16": float(p16),
        "tail": float(tail),
        "snr": float(snr),
        "max_err": float(max_err),
        "mean_err": float(mean_err)
    }

results = []

results.append(run_custom_processor("CURRENT IDENTITY", "ola_test_current.wav", use_identity=True, normalize_ola=False))
results.append(run_custom_processor("NORMALIZED OLA", "ola_test_normalized.wav", use_identity=False, normalize_ola=True))
results.append(run_custom_processor("PURE DSP IDENTITY", "ola_test_identity_normalized.wav", use_identity=True, normalize_ola=True))

print("\n--- RESULTS TABLE ---")
print("Test | 16ms peak | tail energy | RMS | peak | max_err | mean_err | recon SNR")
for r in results:
    print(f"{r['Test']} | {r['peak_16']:.2f} | {r['tail']:.6f} | {r['rms']:.6f} | {r['peak']:.4f} | {r['max_err']:.6f} | {r['mean_err']:.6f} | {r['snr']:.2f}")

