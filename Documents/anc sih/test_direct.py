import torch
import numpy as np
import scipy.io.wavfile as wavfile
import sys
import os
sys.path.append(os.path.expanduser("~/sih26052_edge"))
from app.anc_stream import ANCStream

stream = ANCStream("/home/shreyas/sih26052_edge/config/config.json")

# generate dummy random audio frame
audio_chunk = np.random.randn(256).astype(np.float32)
frame = np.concatenate([np.zeros(256), audio_chunk]) * np.hanning(512).astype(np.float32)
stft = np.fft.rfft(frame)
features = np.concatenate([stft.real, stft.imag])
input_t = torch.tensor(features, dtype=torch.float32).unsqueeze(0).unsqueeze(0)

# Run multiple frames to build state
h, c = None, None
for i in range(10):
    if h is None:
        h = torch.zeros(2, 1, 256)
        c = torch.zeros(2, 1, 256)
    mr, mi, h, c, _, _ = stream.model.core(input_t, h, c)

# Now, test frame 11 with normal state vs zero state
mr1, mi1, h1, c1, _, _ = stream.model.core(input_t, h, c)
mr0, mi0, h0, c0, _, _ = stream.model.core(input_t, h*0, c*0)

print(f"mr1 sum: {mr1.sum().item()}, mr0 sum: {mr0.sum().item()}")
print(f"Diff mr sum: {torch.abs(mr1 - mr0).sum().item()}")
