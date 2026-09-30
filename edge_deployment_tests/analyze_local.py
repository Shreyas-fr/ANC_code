import numpy as np
import scipy.io.wavfile as wavfile
import scipy.signal

IN_WAV = "final_test3_input.wav"
OUT_WAV = "final_test3_ai_output.wav"

rate, d1_orig = wavfile.read(IN_WAV)
_, d2_orig = wavfile.read(OUT_WAV)

d1 = d1_orig.astype(np.float32) / 32768.0
d2 = d2_orig.astype(np.float32) / 32768.0

print(f"Input RMS: {np.sqrt(np.mean(d1_orig.astype(np.float32)**2)):.2f}")
print(f"Input Peak: {np.max(np.abs(d1_orig))}")
print(f"Output RMS: {np.sqrt(np.mean(d2_orig.astype(np.float32)**2)):.2f}")
print(f"Output Peak: {np.max(np.abs(d2_orig))}")

hop = int(rate * 0.01)
env1, env2 = [], []
for i in range(0, len(d1) - hop, hop):
    env1.append(np.sqrt(np.mean(d1[i:i+hop]**2)))
    env2.append(np.sqrt(np.mean(d2[i:i+hop]**2)))
env1, env2 = np.array(env1), np.array(env2)

threshold = np.max(env1) * 0.1
active = env1 > threshold
offsets = [i for i in range(1, len(active)) if active[i-1] and not active[i]]

decay1 = np.mean([np.sum(env1[off:off+50]) for off in offsets if off+50 < len(env1)]) if offsets else 0.0
decay2 = np.mean([np.sum(env2[off:off+50]) for off in offsets if off+50 < len(env2)]) if offsets else 0.0

print(f"Input post-speech tail energy: {decay1:.6f}")
print(f"Output post-speech tail energy: {decay2:.6f}")

d1_sub = d1[:16000*10]
d2_sub = d2[:16000*10]
corr = scipy.signal.correlate(d2_sub, d1_sub, mode='full')
lags = scipy.signal.correlation_lags(len(d2_sub), len(d1_sub), mode='full')
peaks, _ = scipy.signal.find_peaks(corr, height=np.max(corr)*0.3, distance=16000*0.01)

peak_lags = lags[peaks]
peak_vals = corr[peaks]
sorted_idx = np.argsort(peak_vals)[::-1]
for i in range(min(3, len(sorted_idx))):
    idx = sorted_idx[i]
    print(f"Delay: {(peak_lags[idx] / 16000.0) * 1000.0:.2f} ms (corr {peak_vals[idx]:.2f})")
    
# output/input overall speech correlation
active_d1 = d1[np.abs(d1) > np.max(np.abs(d1))*0.05]
active_d2 = d2[np.abs(d1) > np.max(np.abs(d1))*0.05]
if len(active_d1) > 0:
    overall_corr = np.corrcoef(active_d1, active_d2)[0, 1]
    print(f"Output/Input speech correlation: {overall_corr:.4f}")
