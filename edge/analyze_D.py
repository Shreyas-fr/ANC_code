import numpy as np
import soundfile as sf
import sys
from scipy import signal
import matplotlib.pyplot as plt

def get_lag(x, y):
    correlation = signal.correlate(y, x, mode="full")
    lags = signal.correlation_lags(len(y), len(x), mode="full")
    lag_idx = np.argmax(np.abs(correlation))
    return lags[lag_idx]

def band_power(f, Pxx, fmin, fmax):
    idx = np.logical_and(f >= fmin, f <= fmax)
    return np.trapezoid(Pxx[idx], f[idx])

def analyze_d():
    din, sr = sf.read("/Users/shreyasdivekar/anc_tests/D_in.wav")
    dout, sr_out = sf.read("/Users/shreyasdivekar/anc_tests/D_out.wav")
    
    n_samples = min(10 * sr, len(din), len(dout))
    lag_samples = get_lag(din[:n_samples], dout[:n_samples])
    lag_ms = lag_samples * 1000.0 / sr
    print(f"Lag: {lag_ms:.2f} ms ({lag_samples} samples)")
    
    if lag_samples > 0:
        dout_aligned = dout[lag_samples:]
        din_aligned = din[:-lag_samples]
    elif lag_samples < 0:
        dout_aligned = dout[:lag_samples]
        din_aligned = din[-lag_samples:]
    else:
        dout_aligned = dout
        din_aligned = din
        
    n_min = min(len(din_aligned), len(dout_aligned))
    din_aligned = din_aligned[:n_min]
    dout_aligned = dout_aligned[:n_min]
    
    window_samples = int(sr * 0.5)
    n_windows = n_min // window_samples
    
    timeline = []
    e_rms_in = []
    e_rms_out = []
    e_spec_in = []
    e_spec_out = []
    
    for i in range(n_windows):
        start = i * window_samples
        end = start + window_samples
        w_in = din_aligned[start:end]
        w_out = dout_aligned[start:end]
        
        if np.std(w_in) == 0 or np.std(w_out) == 0:
            corr = 0
        else:
            corr = np.corrcoef(w_in, w_out)[0, 1]
            
        if corr > 0.99:
            timeline.append("F")
        else:
            timeline.append("E")
            e_rms_in.append(np.sqrt(np.mean(w_in**2)))
            e_rms_out.append(np.sqrt(np.mean(w_out**2)))
            
            f, Pxx_in = signal.welch(w_in, sr, nperseg=1024)
            f, Pxx_out = signal.welch(w_out, sr, nperseg=1024)
            e_spec_in.append(Pxx_in)
            e_spec_out.append(Pxx_out)
            
    print("Timeline: " + "".join(timeline))
    f_count = timeline.count("F")
    e_count = timeline.count("E")
    print(f"Fraction F: {f_count/n_windows:.2f}, E: {e_count/n_windows:.2f}")
    
    if e_count > 0:
        mean_rms_in = np.mean(e_rms_in)
        mean_rms_out = np.mean(e_rms_out)
        rms_ratio_db = 20 * np.log10(mean_rms_out / mean_rms_in)
        print(f"E windows RMS ratio (out/in): {rms_ratio_db:.2f} dB")
        
        mean_Pxx_in = np.mean(e_spec_in, axis=0)
        mean_Pxx_out = np.mean(e_spec_out, axis=0)
        
        bands = [(0, 300), (300, 4000), (4000, 8000)]
        for bmin, bmax in bands:
            p_in = band_power(f, mean_Pxx_in, bmin, bmax)
            p_out = band_power(f, mean_Pxx_out, bmin, bmax)
            diff_db = 10 * np.log10(p_out / p_in) if p_in > 0 else 0
            print(f"Band {bmin}-{bmax} Hz spectral diff: {diff_db:.2f} dB")
            
    plt.figure(figsize=(12, 10))
    plt.subplot(3, 1, 1)
    plt.specgram(din_aligned, Fs=sr, NFFT=512, noverlap=256, cmap='viridis')
    plt.title("D_in (Aligned)")
    plt.subplot(3, 1, 2)
    plt.specgram(dout_aligned, Fs=sr, NFFT=512, noverlap=256, cmap='viridis')
    plt.title("D_out")
    plt.subplot(3, 1, 3)
    plt.specgram(dout_aligned - din_aligned, Fs=sr, NFFT=512, noverlap=256, cmap='inferno')
    plt.title("Difference")
    plt.tight_layout()
    plt.savefig("/Users/shreyasdivekar/anc_tests/D_spec.png")
    plt.close()
    print("Saved D_spec.png")

def check_ab():
    try:
        a, sr = sf.read("/Users/shreyasdivekar/anc_tests/A_raw.wav")
        b, sr = sf.read("/Users/shreyasdivekar/anc_tests/B_resampled.wav")
        chunk_len = sr * 2 
        lag_start = get_lag(a[:chunk_len], b[:chunk_len])
        lag_end = get_lag(a[-chunk_len:], b[-chunk_len:])
        drift_samples = lag_end - lag_start
        duration_samples = min(len(a), len(b))
        drift_ppm = (drift_samples / duration_samples) * 1e6
        print(f"A/B Sample rate drift: {drift_ppm:.2f} ppm")
    except Exception as e:
        print(f"Could not check A/B drift: {e}")

if __name__ == "__main__":
    analyze_d()
    check_ab()
