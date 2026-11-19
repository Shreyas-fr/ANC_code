import numpy as np

t = np.arange(10000) / 16000.0
sine = np.sin(2 * np.pi * 440 * t).astype(np.float32)
crossfade_samples = 160
fade_in = np.linspace(0, 1, crossfade_samples, dtype=np.float32)
fade_out = np.linspace(1, 0, crossfade_samples, dtype=np.float32)

chunks = [sine[i:i+256] for i in range(0, 10000-256, 256)]
currently_enhanced = True
last_sample = 0.0

for i, delayed_chunk in enumerate(chunks):
    target_audio = delayed_chunk.copy()
    target_state = (i % 4) < 2
    
    if target_state != currently_enhanced:
        if target_state:
            target_audio[:crossfade_samples] = target_audio[:crossfade_samples] * fade_in + delayed_chunk[:crossfade_samples] * fade_out
        else:
            dummy_out = np.linspace(last_sample, delayed_chunk[crossfade_samples-1], crossfade_samples, dtype=np.float32) * fade_out
            target_audio[:crossfade_samples] = target_audio[:crossfade_samples] * fade_in + dummy_out
        currently_enhanced = target_state
        
    if i > 0:
        jump = abs(target_audio[0] - last_sample)
        if jump > 0.01:
            print(f"Jump at {i}: {jump:.5f}")
            print("target_audio[0]:", target_audio[0], "last_sample:", last_sample)
    last_sample = target_audio[-1]
