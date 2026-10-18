import soundfile as sf
import numpy as np
import sys
def get_lag(ref, sig):
    # Find lag of sig relative to ref using numpy cross correlation
    n = min(len(ref), len(sig))
    if n > 16000 * 5:
        n = 16000 * 5
    corr = np.correlate(sig[:n], ref[:n], mode="full")
    lags = np.arange(-len(ref[:n]) + 1, len(sig[:n]))
    lag = lags[np.argmax(np.abs(corr))]
    return lag

def analyze(in_path, out_path, expected_lag=544):
    d_in, sr = sf.read(in_path)
    d_out, _ = sf.read(out_path)
    
    lag = get_lag(d_in, d_out)
    # Use expected lag for alignment to see if F/E works
    if expected_lag > 0:
        d_out_aligned = d_out[expected_lag:]
        d_in_aligned = d_in[:-expected_lag]
    else:
        d_out_aligned = d_out
        d_in_aligned = d_in
        
    n_min = min(len(d_in_aligned), len(d_out_aligned))
    d_in_aligned = d_in_aligned[:n_min]
    d_out_aligned = d_out_aligned[:n_min]
    
    # F/E timeline
    window_ms = 500
    w_size = int(sr * window_ms / 1000)
    timeline = []
    
    # Let's fix the F/E detector if it fails!
    # Expected: raw fallback is exactly identical to D_in except maybe crossfade.
    # D_ref_block is DFN3 output.
    corrs = []
    for i in range(0, n_min - w_size, w_size):
        w_in = d_in_aligned[i:i+w_size]
        w_out = d_out_aligned[i:i+w_size]
        
        if np.std(w_in) > 1e-6 and np.std(w_out) > 1e-6:
            c = np.corrcoef(w_in, w_out)[0, 1]
        else:
            # If both are basically zero, it's identical (F).
            if np.std(w_in) <= 1e-6 and np.std(w_out) <= 1e-6:
                c = 1.0
            else:
                c = 0.0
        corrs.append(c)
        if c > 0.999:
            timeline.append("F")
        else:
            timeline.append("E")
            
    print(f"{in_path} vs {out_path}:")
    print(f"  Lag: {lag} samples ({lag/sr*1000:.2f} ms)")
    print(f"  F: {timeline.count('F')}, E: {timeline.count('E')}")
    print(f"  Timeline: {''.join(timeline)}")
    print(f"  Mean corr F: {np.mean([c for c, t in zip(corrs, timeline) if t == 'F']) if timeline.count('F') > 0 else 0:.4f}")
    print(f"  Mean corr E: {np.mean([c for c, t in zip(corrs, timeline) if t == 'E']) if timeline.count('E') > 0 else 0:.4f}")
    return corrs, timeline

if __name__ == "__main__":
    d_in, sr = sf.read("/Users/shreyasdivekar/anc_tests/D_in.wav")
    d_in_delayed = np.zeros(len(d_in) + int(564 * sr / 1000))
    d_in_delayed[int(564 * sr / 1000):] = d_in
    sf.write("/Users/shreyasdivekar/anc_tests/D_in_delayed.wav", d_in_delayed[:len(d_in)], sr)
    
    print("--- Case (i) D_in vs D_in delayed 564ms ---")
    analyze("/Users/shreyasdivekar/anc_tests/D_in.wav", "/Users/shreyasdivekar/anc_tests/D_in_delayed.wav", expected_lag=int(564*16))
    
    print("--- Case (ii) D_in vs D_ref_block ---")
    # For D_ref_block, there's no lag because it's processed offline without transmission delay
    # Wait, does FakeDFN3 have algorithmic lag?
    # Yes, FakeDFN3 uses `enhance` which has NO lag (it's time-aligned)!
    # Wait, if `enhance` is time-aligned, the lag should be 0.
    analyze("/Users/shreyasdivekar/anc_tests/D_in.wav", "/Users/shreyasdivekar/anc_tests/D_ref_block.wav", expected_lag=0)
    
    print("--- Case (iii) D_in vs D_out ---")
    # D_out has 544ms measured lag
    analyze("/Users/shreyasdivekar/anc_tests/D_in.wav", "/Users/shreyasdivekar/anc_tests/D_out.wav", expected_lag=8704)
