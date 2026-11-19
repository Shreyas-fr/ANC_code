#!/usr/bin/env python3
"""
Generate a deterministic 10-second test WAV at 48 kHz.
Contains: speech-like burst, stationary noise, and impulsive content.
Deterministic: seeded RNG.
"""
import numpy as np
import soundfile as sf
import os

SEED = 42
SR = 48000
DURATION = 10  # seconds
N = SR * DURATION
OUT = os.path.expanduser("~/sih26052_edge/audio/test_deterministic_48k_10s.wav")

rng = np.random.default_rng(SEED)
t = np.linspace(0, DURATION, N, endpoint=False)

# 1. Stationary noise floor (pink-ish noise via cumsum)
white = rng.standard_normal(N).astype(np.float32) * 0.05
noise = np.cumsum(white)
noise -= noise.mean()
noise /= (np.abs(noise).max() + 1e-9)
noise *= 0.07  # -23 dBFS approx

# 2. Speech-like bursts (AM sine sweeps)
speech = np.zeros(N, dtype=np.float32)
for start_s, dur_s, f0 in [
    (0.5, 0.4, 220), (1.2, 0.6, 280), (2.5, 0.8, 200),
    (4.0, 0.5, 240), (5.5, 0.7, 170), (7.0, 0.6, 260),
    (8.5, 0.4, 220), (9.0, 0.3, 200),
]:
    s = int(start_s * SR)
    e = min(s + int(dur_s * SR), N)
    seg_t = t[s:e]
    # AM modulation: fundamental + harmonics
    carrier = (
        0.5 * np.sin(2 * np.pi * f0 * seg_t)
        + 0.3 * np.sin(2 * np.pi * f0 * 2 * seg_t)
        + 0.15 * np.sin(2 * np.pi * f0 * 3 * seg_t)
    )
    envelope = np.sin(np.pi * np.arange(e - s) / (e - s))
    speech[s:e] += carrier * envelope * 0.35

# 3. Impulsive content (gunfire-like clicks)
for click_t in [1.0, 3.5, 6.0, 8.2]:
    ci = int(click_t * SR)
    click_len = int(0.004 * SR)  # 4 ms
    decay = np.exp(-np.arange(click_len) / (0.001 * SR))
    end_i = min(ci + click_len, N)
    speech[ci:end_i] += (rng.standard_normal(end_i - ci) * decay[: end_i - ci] * 0.6)

# Mix
audio = (noise + speech).astype(np.float32)
# Normalize to -3 dBFS
peak = np.abs(audio).max()
audio /= peak
audio *= 10 ** (-3 / 20)
audio = np.clip(audio, -1.0, 1.0)

sf.write(OUT, audio, SR, subtype="PCM_16")
print(f"Written: {OUT}")
print(f"Duration: {DURATION:.1f}s  SR: {SR} Hz  Frames: {N}  Peak: {np.abs(audio).max():.4f}")
print(f"RMS: {np.sqrt(np.mean(audio**2)):.6f}")
