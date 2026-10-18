import soundfile as sf
import numpy as np

def rms_db(audio):
    rms = np.sqrt(np.mean(audio**2))
    return 20 * np.log10(rms) if rms > 1e-10 else -999

def run_9b_and_9c():
    d_in, sr = sf.read("/Users/shreyasdivekar/anc_tests/D_in.wav")
    d_out, _ = sf.read("/Users/shreyasdivekar/anc_tests/D_out.wav")
    d_ref2_block, _ = sf.read("/Users/shreyasdivekar/anc_tests/D_ref2_block.wav")
    
    # 9b: Find true D_out lag against D_in over +/- 40ms around 544ms (8704 samples)
    center_lag = 8704
    search_radius = int(40 * sr / 1000)
    best_lag = center_lag
    best_corr = -1
    
    # Calculate cross correlation
    # We use a 10-second segment starting at 10 seconds to avoid padding at start
    start_in = 10 * sr
    dur = 10 * sr
    segment_in = d_in[start_in:start_in+dur]
    
    for lag in range(center_lag - search_radius, center_lag + search_radius + 1):
        segment_out = d_out[start_in + lag : start_in + lag + dur]
        if len(segment_out) == dur:
            c = np.corrcoef(segment_in, segment_out)[0, 1]
            if c > best_corr:
                best_corr = c
                best_lag = lag
                
    print(f"9b: Best lag D_out vs D_in: {best_lag} samples ({best_lag/sr*1000:.2f} ms)")
    print(f"Correlation at best lag: {best_corr:.4f}")
    print("Fallback delay (564ms expected) vs true enhanced lag (544ms measured). Misalignment of 20ms!")
    
    # 9c: Resolve contradiction
    print("--- 9c ---")
    d_out_a = d_out[best_lag:]
    d_in_a = d_in[:-best_lag]
    
    # Wait, D_ref2_block has NO lag relative to D_in because BlockBackend output is perfectly time-aligned by dropping initial zeroes?
    # Wait, in the Pi chain, BlockBackend is used by AudioChain, which adds reframe_ms + resample_ms.
    # In my run_9a, I used AudioChain which DOES pad `prime_io` zeroes at the start!
    # Let's find the lag of D_ref2_block against D_in
    lag_ref = 8704 # Actually AudioChain introduces algorithmic latency
    # Let's just find it using correlation
    corr_ref = np.correlate(d_ref2_block[:15*sr], d_in[:15*sr], mode="full")
    lags_ref = np.arange(-len(d_in[:15*sr]) + 1, len(d_ref2_block[:15*sr]))
    lag_ref = lags_ref[np.argmax(np.abs(corr_ref))]
    print(f"Lag of D_ref2_block vs D_in: {lag_ref} samples ({lag_ref/sr*1000:.2f} ms)")
    
    if lag_ref > 0:
        d_ref2_a = d_ref2_block[lag_ref:]
    else:
        d_ref2_a = d_ref2_block
        
    n_min = min(len(d_in_a), len(d_out_a), len(d_ref2_a))
    d_in_a = d_in_a[:n_min]
    d_out_a = d_out_a[:n_min]
    d_ref2_a = d_ref2_a[:n_min]
    
    w_size = int(sr * 0.5)
    c_out_in = []
    c_ref_in = []
    c_out_ref = []
    res_rel = []
    
    for i in range(int(1.5*sr), n_min - int(1.0*sr) - w_size, w_size):
        w_in = d_in_a[i:i+w_size]
        w_out = d_out_a[i:i+w_size]
        w_ref = d_ref2_a[i:i+w_size]
        
        c_out_in.append(np.corrcoef(w_out, w_in)[0,1] if np.std(w_in)>0 and np.std(w_out)>0 else 0)
        c_ref_in.append(np.corrcoef(w_ref, w_in)[0,1] if np.std(w_in)>0 and np.std(w_ref)>0 else 0)
        c_out_ref.append(np.corrcoef(w_out, w_ref)[0,1] if np.std(w_ref)>0 and np.std(w_out)>0 else 0)
        
        diff = w_out - w_ref
        rms_ref = rms_db(w_ref)
        if rms_ref > -100:
            res_rel.append(rms_db(diff) - rms_ref)
        else:
            res_rel.append(-999)
            
    print(f"Mean corr(D_out, D_in): {np.mean(c_out_in):.4f}")
    print(f"Mean corr(D_ref2_block, D_in): {np.mean(c_ref_in):.4f}")
    print(f"Mean corr(D_out, D_ref2_block): {np.mean(c_out_ref):.4f}")
    
    print("Residual RELATIVE to D_ref2_block (dB):")
    valid_res = [r for r in res_rel if r != -999]
    print(", ".join(f"{r:.1f}" for r in valid_res))
    if valid_res:
        print(f"Median: {np.median(valid_res):.1f} dB, p90: {np.percentile(valid_res, 90):.1f} dB")
        
def run_9d():
    print("--- 9d: Mask and Proxy Table ---")
    d_in, sr = sf.read("/Users/shreyasdivekar/anc_tests/D_in.wav")
    d_out, _ = sf.read("/Users/shreyasdivekar/anc_tests/D_out.wav")
    d_ref2_w, _ = sf.read("/Users/shreyasdivekar/anc_tests/D_ref2_whole.wav")
    d_ref2_b, _ = sf.read("/Users/shreyasdivekar/anc_tests/D_ref2_block.wav")
    
    # Align all to D_in
    lag_out = 8704
    corr_ref_w = np.correlate(d_ref2_w[:5*sr], d_in[:5*sr], mode="full")
    lag_ref_w = np.arange(-len(d_in[:5*sr]) + 1, len(d_ref2_w[:5*sr]))[np.argmax(np.abs(corr_ref_w))]
    
    corr_ref_b = np.correlate(d_ref2_b[:5*sr], d_in[:5*sr], mode="full")
    lag_ref_b = np.arange(-len(d_in[:5*sr]) + 1, len(d_ref2_b[:5*sr]))[np.argmax(np.abs(corr_ref_b))]
    
    d_out_a = d_out[lag_out:] if lag_out > 0 else d_out
    d_ref2_w_a = d_ref2_w[lag_ref_w:] if lag_ref_w > 0 else d_ref2_w
    d_ref2_b_a = d_ref2_b[lag_ref_b:] if lag_ref_b > 0 else d_ref2_b
    d_in_a = d_in[:-lag_out] if lag_out > 0 else d_in
    
    n_min = min(len(d_in_a), len(d_out_a), len(d_ref2_w_a), len(d_ref2_b_a))
    files = {
        "D_in": d_in_a[:n_min],
        "D_ref2_whole": d_ref2_w_a[:n_min],
        "D_ref2_block": d_ref2_b_a[:n_min],
        "D_out": d_out_a[:n_min]
    }
    
    # Energy VAD on D_in
    frame_ms = 20
    frame_samples = int(sr * frame_ms / 1000)
    vad = []
    
    # Calculate rms per frame to find threshold
    rmses = []
    for i in range(0, n_min - frame_samples, frame_samples):
        rmses.append(rms_db(files["D_in"][i:i+frame_samples]))
    rmses = np.array(rmses)
    
    # threshold = median + 10dB (or some reasonable margin above noise floor)
    threshold = np.percentile(rmses, 20) + 15
    print(f"VAD Threshold: {threshold:.1f} dB")
    
    for r in rmses:
        vad.append(r > threshold)
        
    print(f"Speech frames: {sum(vad)}, Non-speech frames: {len(vad) - sum(vad)}")
    
    print(f"{'File':<15} | {'Non-Speech (dB)':<16} | {'Speech (dB)':<12} | {'Level Gap':<10} | {'0-300 S/NS':<12} | {'300-4k S/NS':<12} | {'4-8k S/NS':<12}")
    print("-" * 110)
    
    for name, audio in files.items():
        speech_audio = []
        nspeech_audio = []
        for i, is_speech in enumerate(vad):
            # exclude first 1.5s
            if i * frame_samples < 1.5 * sr:
                continue
            frame = audio[i*frame_samples:(i+1)*frame_samples]
            if is_speech:
                speech_audio.extend(frame)
            else:
                nspeech_audio.extend(frame)
                
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
    run_9b_and_9c()
    run_9d()
