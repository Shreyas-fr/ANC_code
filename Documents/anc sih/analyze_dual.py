import sys
import wave
import math
import struct
import numpy as np

in_path = sys.argv[1]
out_path = sys.argv[2]

def analyze(filepath):
    with wave.open(filepath, 'rb') as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        duration = frames / float(rate)
        
        raw_data = wf.readframes(frames)
        samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32)
        
        rms = np.sqrt(np.mean(samples**2)) if len(samples) > 0 else 0
        peak = np.max(np.abs(samples)) if len(samples) > 0 else 0
        
        # Check nan/inf
        has_nan = np.isnan(samples).any()
        has_inf = np.isinf(samples).any()
        
        return {
            "duration": duration,
            "rate": rate,
            "channels": channels,
            "rms": rms,
            "peak": peak,
            "has_nan": has_nan,
            "has_inf": has_inf,
            "frames": frames,
            "samples": samples
        }

in_data = analyze(in_path)
out_data = analyze(out_path)

print(f"INPUT:")
print(f"Duration: {in_data['duration']:.2f}s")
print(f"Sample Rate: {in_data['rate']} Hz")
print(f"Channels: {in_data['channels']}")
print(f"RMS: {in_data['rms']:.2f}")
print(f"Peak: {in_data['peak']}")
print(f"NaN/Inf: {in_data['has_nan']}/{in_data['has_inf']}")

print(f"\nOUTPUT:")
print(f"Duration: {out_data['duration']:.2f}s")
print(f"Sample Rate: {out_data['rate']} Hz")
print(f"Channels: {out_data['channels']}")
print(f"RMS: {out_data['rms']:.2f}")
print(f"Peak: {out_data['peak']}")
print(f"NaN/Inf: {out_data['has_nan']}/{out_data['has_inf']}")

# Correlation
if in_data['frames'] == out_data['frames'] and in_data['frames'] > 0:
    corr = np.corrcoef(in_data['samples'], out_data['samples'])[0, 1]
    print(f"\nCross-correlation: {corr:.4f}")
    if out_data['rms'] > 0:
        print("Output contains speech: YES")
    else:
        print("Output contains speech: NO")
else:
    print("\nFrame count mismatch or empty files.")
