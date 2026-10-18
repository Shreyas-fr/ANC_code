import numpy as np
import scipy.io.wavfile as wavfile
import scipy.signal

inp_path = "/home/shreyas/sih26052_edge/audio/final_test2_input_20260930_164525.wav"
out_path = "/home/shreyas/sih26052_edge/audio/final_test2_ai_output_20260930_164525.wav"

rate_i, inp = wavfile.read(inp_path)
rate_o, out = wavfile.read(out_path)
inp = inp.astype(np.float32) / 32768.0
out = out.astype(np.float32) / 32768.0

duration = len(inp) / rate_i
print(f"Duration      : {duration:.2f} s")
print(f"Sample rate   : {rate_i} Hz")
print(f"Input RMS     : {np.sqrt(np.mean(inp**2)):.6f}")
print(f"Output RMS    : {np.sqrt(np.mean(out**2)):.6f}")
print(f"Input peak    : {np.max(np.abs(inp)):.4f}")
print(f"Output peak   : {np.max(np.abs(out)):.4f}")
print(f"NaN/Inf out   : {np.isnan(out).any() or np.isinf(out).any()}")
print(f"Clip in       : {np.any(np.abs(inp) >= 0.99)}")
print(f"Clip out      : {np.any(np.abs(out) >= 0.99)}")

min_l = min(len(inp), len(out))
i2, o2 = inp[:min_l], out[:min_l]
corr = scipy.signal.correlate(o2, i2, mode='full')
lags = scipy.signal.correlation_lags(len(o2), len(i2), mode='full')
peaks_idx, _ = scipy.signal.find_peaks(np.abs(corr), distance=160)
top5 = sorted(peaks_idx, key=lambda x: -abs(corr[x]))[:5]
print("\nTop 5 correlation peaks:")
for idx in top5:
    lag_ms = lags[idx] / rate_i * 1000.0
    print(f"  lag={lags[idx]:+d} ({lag_ms:+.2f} ms)  corr={corr[idx]:.2f}")

hop = int(rate_o * 0.01)
env = np.array([np.sqrt(np.mean(out[i:i+hop]**2)) for i in range(0, len(out)-hop, hop)])
thr = np.max(env) * 0.1
active = env > thr
offsets = [i for i in range(1, len(active)) if active[i-1] and not active[i]]
decay_e = [np.sum(env[o:o+50]) for o in offsets if o+50 < len(env)]
tail = float(np.mean(decay_e)) if decay_e else 0.0
print(f"\nPost-speech tail energy : {tail:.6f}")
print(f"Pre-fix reference tail  : 0.289287")
print(f"Clipped test tail       : 0.993908")
