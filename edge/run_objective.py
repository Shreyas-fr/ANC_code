import soundfile as sf
import numpy as np

def rms_db(audio):
    rms = np.sqrt(np.mean(audio**2))
    return 20 * np.log10(rms) if rms > 1e-10 else -999

def get_lag(ref, sig):
    n = min(len(ref), len(sig), 16000 * 5)
    corr = np.correlate(sig[:n], ref[:n], mode="full")
    lags = np.arange(-len(ref[:n]) + 1, len(sig[:n]))
    return lags[np.argmax(np.abs(corr))]

def analyze_fidelity():
    d_out, sr = sf.read("/Users/shreyasdivekar/anc_tests/D_out.wav")
    d_ref, _ = sf.read("/Users/shreyasdivekar/anc_tests/D_ref_block.wav")
    
    # We want to align D_out to D_ref_block.
    # We know D_out is delayed compared to D_in by 544ms (8704 samples)
    # D_ref_block is perfectly aligned with D_in.
    # Let's cross-correlate D_out and D_ref_block to be sure.
    lag = get_lag(d_ref, d_out)
    if lag > 0:
        d_out_a = d_out[lag:]
        d_ref_a = d_ref[:-lag]
    else:
        d_out_a = d_out[:lag]
        d_ref_a = d_ref[-lag:]
        
    n_min = min(len(d_out_a), len(d_ref_a))
    d_out_a = d_out_a[:n_min]
    d_ref_a = d_ref_a[:n_min]
    
    # 500 ms windows
    w_size = int(sr * 0.5)
    residuals = []
    for i in range(0, n_min - w_size, w_size):
        diff = d_out_a[i:i+w_size] - d_ref_a[i:i+w_size]
        residuals.append(rms_db(diff))
        
    print(f"Lag between D_out and D_ref_block: {lag} samples ({lag/sr*1000:.2f} ms)")
    print("Residual RMS per 500ms window (dB):")
    print(", ".join(f"{r:.1f}" for r in residuals))
    print(f"Mean residual: {np.mean(residuals):.1f} dB")

def get_metrics(audio, sr):
    frame_len = int(sr * 0.02)
    rmses = []
    for i in range(0, len(audio) - frame_len, frame_len):
        frame = audio[i:i+frame_len]
        rms = np.sqrt(np.mean(frame**2))
        rmses.append(20 * np.log10(rms) if rms > 1e-10 else -100)
    
    rmses = np.array(rmses)
    rmses = np.sort(rmses)
    noise_floor = np.mean(rmses[:max(1, int(len(rmses)*0.1))])
    speech_level = np.mean(rmses[-max(1, int(len(rmses)*0.2)):])
    
    # 4-8 kHz energy
    f = np.fft.rfft(audio)
    freqs = np.fft.rfftfreq(len(audio), 1/sr)
    mask = (freqs >= 4000) & (freqs <= 8000)
    hf_energy = np.sum(np.abs(f[mask])**2)
    hf_db = 10 * np.log10(hf_energy / len(audio)) if hf_energy > 0 else -100
    
    return noise_floor, speech_level, speech_level - noise_floor, hf_db

def run_objective():
    files = [
        ("D_in", "/Users/shreyasdivekar/anc_tests/D_in.wav"),
        ("D_ref_whole", "/Users/shreyasdivekar/anc_tests/D_ref_whole.wav"),
        ("D_ref_block", "/Users/shreyasdivekar/anc_tests/D_ref_block.wav"),
        ("D_out", "/Users/shreyasdivekar/anc_tests/D_out.wav"),
    ]
    
    print("--- 8e: Objective Proxies ---")
    print(f"{'File':<15} | {'Noise Floor (dB)':<18} | {'Speech Level (dB)':<18} | {'SNR Diff (dB)':<15} | {'4-8kHz Energy (dB)'}")
    print("-" * 90)
    for name, path in files:
        audio, sr = sf.read(path)
        nf, sp, snr, hf = get_metrics(audio, sr)
        print(f"{name:<15} | {nf:<18.2f} | {sp:<18.2f} | {snr:<15.2f} | {hf:.2f}")

if __name__ == "__main__":
    analyze_fidelity()
    run_objective()
