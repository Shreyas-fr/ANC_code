import sys
import os
import numpy as np
import scipy.io.wavfile as wavfile
import scipy.signal

IN_WAV = "/home/shreyas/sih26052_edge/audio/final_test2_input_20260930_154218.wav"
OUT_WAV = "/home/shreyas/sih26052_edge/audio/final_test2_ai_output_20260930_154218.wav"

rate, d1 = wavfile.read(IN_WAV)
_, d2 = wavfile.read(OUT_WAV)
d1 = d1.astype(np.float32) / 32768.0
d2 = d2.astype(np.float32) / 32768.0

# 1. Decay
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

print(f"Input avg tail energy: {decay1:.6f}")
print(f"Output avg tail energy: {decay2:.6f}")

# 2. Correlation
d1_sub = d1[:16000*10]
d2_sub = d2[:16000*10]
corr = scipy.signal.correlate(d2_sub, d1_sub, mode='full')
lags = scipy.signal.correlation_lags(len(d2_sub), len(d1_sub), mode='full')
peaks, _ = scipy.signal.find_peaks(corr, height=np.max(corr)*0.3, distance=16000*0.01)

peak_lags = lags[peaks]
peak_vals = corr[peaks]
sorted_idx = np.argsort(peak_vals)[::-1]
for i in range(min(5, len(sorted_idx))):
    idx = sorted_idx[i]
    print(f"Delay: {(peak_lags[idx] / 16000.0) * 1000.0:.2f} ms (corr {peak_vals[idx]:.2f})")
