import sys
import wave
import math

filepath = sys.argv[1]
try:
    with wave.open(filepath, 'rb') as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        duration = frames / float(rate)
        
        raw_data = wf.readframes(frames)
        
        # calculate RMS
        sum_sq = 0.0
        peak = 0
        if sampwidth == 2:
            import struct
            samples = struct.unpack(f"<{frames*channels}h", raw_data)
            for s in samples:
                sum_sq += s*s
                if abs(s) > peak:
                    peak = abs(s)
            rms = math.sqrt(sum_sq / len(samples)) if len(samples) > 0 else 0
        else:
            rms = -1
            peak = -1
            
        print(f"duration: {duration:.2f}s")
        print(f"sample_rate: {rate} Hz")
        print(f"channels: {channels}")
        print(f"sampwidth: {sampwidth} bytes")
        print(f"rms: {rms:.2f}")
        print(f"peak: {peak}")
        
        if peak == 0:
            print("speech_detected: NO (completely silent)")
        else:
            print("speech_detected: YES (non-zero audio)")
except Exception as e:
    print(f"Error analyzing audio: {e}")
