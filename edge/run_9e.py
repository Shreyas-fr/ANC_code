import os
import random
import numpy as np
import soundfile as sf

def rms_db(audio):
    rms = np.sqrt(np.mean(audio**2))
    return 20 * np.log10(rms) if rms > 1e-10 else -999

def match_loudness(target_db, audio):
    db = rms_db(audio)
    if db > -100:
        gain = 10 ** ((target_db - db) / 20)
        return audio * gain
    return audio

def run_9e():
    out_dir = "/Users/shreyasdivekar/anc_tests/listen"
    os.makedirs(out_dir, exist_ok=True)
    
    d_in, sr = sf.read("/Users/shreyasdivekar/anc_tests/D_in.wav")
    d_out, _ = sf.read("/Users/shreyasdivekar/anc_tests/D_out.wav")
    d_ref2_w, _ = sf.read("/Users/shreyasdivekar/anc_tests/D_ref2_whole.wav")
    d_ref2_b, _ = sf.read("/Users/shreyasdivekar/anc_tests/D_ref2_block.wav")
    
    lag_out = 8704  # 544 ms
    lag_ref = 9024  # 564 ms
    
    d_out_a = d_out[lag_out:]
    d_ref2_w_a = d_ref2_w[lag_ref:]
    d_ref2_b_a = d_ref2_b[lag_ref:]
    d_in_a = d_in[:-lag_out] # We align to D_in time. So D_out is delayed by lag_out. Wait, if D_out is delayed, D_out[lag_out:] is time-aligned with D_in[0:].
    
    n_min = min(len(d_in_a), len(d_out_a), len(d_ref2_w_a), len(d_ref2_b_a))
    files = {
        "D_in": d_in_a[:n_min],
        "D_ref2_whole": d_ref2_w_a[:n_min],
        "D_ref2_block": d_ref2_b_a[:n_min],
        "D_out": d_out_a[:n_min]
    }
    
    # Excerpts (8 seconds each)
    # Loud speech: let's pick 15s to 23s
    # Noisiest speech: let's pick 25s to 33s
    # Noise-only: let's pick 2s to 10s
    excerpts = {
        "loud_speech": (15 * sr, 23 * sr),
        "noisiest_speech": (25 * sr, 33 * sr),
        "noise_only": (2 * sr, 10 * sr)
    }
    
    target_rms = -25.0
    key_lines = []
    
    for exc_name, (start, end) in excerpts.items():
        if end > n_min:
            print(f"Skipping {exc_name}, not enough audio.")
            continue
            
        versions = list(files.keys())
        random.shuffle(versions)
        
        for i, v_name in enumerate(versions):
            audio = files[v_name][start:end]
            audio = match_loudness(target_rms, audio)
            
            # Hard limiter
            audio = np.clip(audio, -0.99, 0.99)
            
            out_name = f"{exc_name}_V{i+1}.wav"
            sf.write(os.path.join(out_dir, out_name), audio, sr)
            
            key_lines.append(f"{out_name}: {v_name}")
            
    with open(os.path.join(out_dir, "KEY.txt"), "w") as f:
        f.write("\n".join(key_lines))
        
    print("Generated 9e listen excerpts successfully.")

if __name__ == "__main__":
    run_9e()
