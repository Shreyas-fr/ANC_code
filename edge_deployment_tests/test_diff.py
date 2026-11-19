import numpy as np
import scipy.io.wavfile as wavfile

r1, d1 = wavfile.read("/home/shreyas/sih26052_edge/audio/reverb_fix_test/diagnostic_alpha_1.00.wav")
r0, d0 = wavfile.read("/home/shreyas/sih26052_edge/audio/reverb_fix_test/diagnostic_alpha_0.00.wav")

diff = np.abs(d1.astype(float) - d0.astype(float))
print(f"Max diff: {np.max(diff)}")
print(f"Mean diff: {np.mean(diff)}")
print(f"Non-zero diff count: {np.sum(diff > 0)} / {len(diff)}")

rms1 = np.sqrt(np.mean(d1.astype(float)**2))
rms0 = np.sqrt(np.mean(d0.astype(float)**2))
print(f"RMS 1.00: {rms1}")
print(f"RMS 0.00: {rms0}")
