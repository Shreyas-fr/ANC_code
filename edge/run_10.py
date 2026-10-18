import sys
import numpy as np
import soundfile as sf

def rms_db(audio):
    rms = np.sqrt(np.mean(audio**2))
    return 20 * np.log10(rms) if rms > 1e-10 else -999

def get_best_lag(ref, sig, search_radius_s=1.0):
    sr = 16000
    n = min(len(ref), len(sig))
    # start from 8s
    start = 8 * sr
    dur = 10 * sr
    
    if start + dur > n:
        dur = n - start
    if dur <= 0: return 0, 0
    
    ref_seg = ref[start:start+dur]
    sig_seg = sig[start:start+dur]
    
    # We want lag of sig relative to ref
    # sig[lag:] matches ref[:-lag] if lag > 0
    corr = np.correlate(sig_seg, ref_seg, mode="full")
    lags = np.arange(-len(ref_seg) + 1, len(sig_seg))
    
    # limit search radius
    radius = int(search_radius_s * sr)
    valid = (lags >= -radius) & (lags <= radius)
    
    best_idx = np.argmax(np.abs(corr[valid]))
    best_lag = lags[valid][best_idx]
    best_corr = corr[valid][best_idx] / (np.linalg.norm(sig_seg) * np.linalg.norm(ref_seg) + 1e-10)
    
    return best_lag, best_corr

def run_10d():
    print("--- 10d: Pairwise Comparison ---")
    d_out, sr = sf.read("/Users/shreyasdivekar/anc_tests/D_out.wav")
    d_ref, _ = sf.read("/Users/shreyasdivekar/anc_tests/D_ref2_block.wav")
    r_out, _ = sf.read("/Users/shreyasdivekar/anc_tests/replay_out.wav")
    d_in, _ = sf.read("/Users/shreyasdivekar/anc_tests/D_in.wav")
    
    pairs = [
        ("replay_out", r_out, "D_ref2_block", d_ref),
        ("replay_out", r_out, "D_out", d_out),
        ("D_ref2_block", d_ref, "D_out", d_out)
    ]
    
    for name1, sig1, name2, sig2 in pairs:
        lag, corr = get_best_lag(sig2, sig1) # sig1 relative to sig2
        print(f"{name1} vs {name2}: best lag = {lag} samples ({lag/sr*1000:.2f} ms), corr = {corr:.4f}")
        
        # align sig1 to sig2
        if lag > 0:
            s1_a = sig1[lag:]
            s2_a = sig2[:-lag]
        elif lag < 0:
            s1_a = sig1[:lag]
            s2_a = sig2[-lag:]
        else:
            s1_a = sig1
            s2_a = sig2
            
        n_min = min(len(s1_a), len(s2_a))
        s1_a = s1_a[:n_min]
        s2_a = s2_a[:n_min]
        
        res = []
        w_size = int(sr * 0.5)
        for i in range(int(1.5*sr), n_min - int(1.0*sr) - w_size, w_size):
            w1 = s1_a[i:i+w_size]
            w2 = s2_a[i:i+w_size]
            
            diff = w1 - w2
            r2 = rms_db(w2)
            if r2 > -100:
                res.append(rms_db(diff) - r2)
        
        if res:
            print("Residuals:", ", ".join(f"{r:.1f}" for r in res))
            print(f"Median: {np.median(res):.1f} dB, p90: {np.percentile(res, 90):.1f} dB")
        print()

def run_10e():
    print("--- 10e: Fallback detection ---")
    d_out, sr = sf.read("/Users/shreyasdivekar/anc_tests/D_out.wav")
    d_in, _ = sf.read("/Users/shreyasdivekar/anc_tests/D_in.wav")
    
    lag564 = 9024
    lag544 = 8704
    
    din564 = d_in[:-lag564] if lag564 > 0 else d_in
    dout564 = d_out[lag564:] if lag564 > 0 else d_out
    
    din544 = d_in[:-lag544] if lag544 > 0 else d_in
    dout544 = d_out[lag544:] if lag544 > 0 else d_out
    
    w_size = int(sr * 0.5)
    timeline = []
    
    for i in range(0, min(len(din564), len(dout564)) - w_size, w_size):
        w_out = dout564[i:i+w_size]
        w_in564 = din564[i:i+w_size]
        c564 = np.corrcoef(w_out, w_in564)[0,1] if np.std(w_out)>1e-6 and np.std(w_in564)>1e-6 else 0
        if np.std(w_out)<=1e-6 and np.std(w_in564)<=1e-6: c564 = 1.0
        
        w_out2 = dout544[i:i+w_size]
        w_in544 = din544[i:i+w_size]
        c544 = np.corrcoef(w_out2, w_in544)[0,1] if np.std(w_out2)>1e-6 and np.std(w_in544)>1e-6 else 0
        if np.std(w_out2)<=1e-6 and np.std(w_in544)<=1e-6: c544 = 1.0
        
        if c564 > 0.999:
            timeline.append("F564")
        elif c544 > 0.999:
            timeline.append("F544")
        else:
            timeline.append("E")
            
    print("Timeline:", "".join(timeline))
    print(f"Counts: E={timeline.count('E')}, F564={timeline.count('F564')}, F544={timeline.count('F544')}")

def run_10f():
    print("--- 10f: Level table v2 ---")
    d_in, sr = sf.read("/Users/shreyasdivekar/anc_tests/D_in.wav")
    d_out, _ = sf.read("/Users/shreyasdivekar/anc_tests/D_out.wav")
    r_out, _ = sf.read("/Users/shreyasdivekar/anc_tests/replay_out.wav")
    d_ref, _ = sf.read("/Users/shreyasdivekar/anc_tests/D_ref2_block.wav")
    
    # align to D_in
    def get_lag_to_in(sig):
        return get_best_lag(d_in, sig, 2.0)[0]
        
    lag_out = get_lag_to_in(d_out)
    lag_rout = get_lag_to_in(r_out)
    lag_ref = get_lag_to_in(d_ref)
    
    files = {
        "D_in": d_in,
        "D_ref2_block": d_ref[lag_ref:] if lag_ref > 0 else d_ref,
        "replay_out": r_out[lag_rout:] if lag_rout > 0 else r_out,
        "D_out": d_out[lag_out:] if lag_out > 0 else d_out
    }
    
    frame_ms = 20
    frame_samples = int(sr * frame_ms / 1000)
    vad = []
    
    rmses = []
    n_min = min(len(f) for f in files.values())
    for i in range(0, n_min - frame_samples, frame_samples):
        rmses.append(rms_db(d_in[i:i+frame_samples]))
    rmses = np.array(rmses)
    
    threshold = -50.1
    for r in rmses: vad.append(r > threshold)
    
    print(f"{'File':<15} | {'Non-Speech (dB)':<16} | {'Speech (dB)':<12} | {'Level Gap':<10} | {'0-300 S/NS':<12} | {'300-4k S/NS':<12} | {'4-8k S/NS':<12}")
    print("-" * 110)
    
    for name, audio in files.items():
        speech_audio = []
        nspeech_audio = []
        for i, is_speech in enumerate(vad):
            if i * frame_samples < 1.5 * sr: continue
            frame = audio[i*frame_samples:(i+1)*frame_samples]
            if is_speech: speech_audio.extend(frame)
            else: nspeech_audio.extend(frame)
                
        sp = rms_db(np.array(speech_audio)) if speech_audio else -999
        ns = rms_db(np.array(nspeech_audio)) if nspeech_audio else -999
        
        def band_energy(audio_arr, f_low, f_high):
            if len(audio_arr) == 0: return -999
            f = np.fft.rfft(audio_arr)
            freqs = np.fft.rfftfreq(len(audio_arr), 1/sr)
            mask = (freqs >= f_low) & (freqs <= f_high)
            hf_energy = np.sum(np.abs(f[mask])**2)
            return 10 * np.log10(hf_energy / len(audio_arr)) if hf_energy > 0 else -100
            
        sp_0 = band_energy(speech_audio, 0, 300)
        ns_0 = band_energy(nspeech_audio, 0, 300)
        sp_3 = band_energy(speech_audio, 300, 4000)
        ns_3 = band_energy(nspeech_audio, 300, 4000)
        sp_4 = band_energy(speech_audio, 4000, 8000)
        ns_4 = band_energy(nspeech_audio, 4000, 8000)
        
        print(f"{name:<15} | {ns:<16.1f} | {sp:<12.1f} | {sp-ns:<10.1f} | {sp_0:.1f}/{ns_0:.1f} | {sp_3:.1f}/{ns_3:.1f} | {sp_4:.1f}/{ns_4:.1f}")

if __name__ == "__main__":
    run_10d()
    run_10e()
    run_10f()
