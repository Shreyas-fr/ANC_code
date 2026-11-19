import time
import json
import numpy as np
import soundfile as sf
import os
import argparse
import scipy.signal

# My test imports
from scratch_pi_dfn3 import DFN3Stream
from df.enhance import init_df, maybe_download_model, enhance
import torch
import soxr

def compute_sisdr(ref, est):
    if len(ref) != len(est):
        mlen = min(len(ref), len(est))
        ref = ref[:mlen]
        est = est[:mlen]
    
    correlation = scipy.signal.correlate(est, ref, mode='full')
    lags = scipy.signal.correlation_lags(len(est), len(ref), mode='full')
    lag = lags[np.argmax(correlation)]
    
    if lag >= 0:
        r, e = ref[:len(ref)-lag], est[lag:]
    else:
        r, e = ref[-lag:], est[:len(est)+lag]
        
    def sisdr_core(ref_sig, est_sig):
        ref_energy = np.sum(ref_sig ** 2) + 1e-8
        alpha = np.sum(ref_sig * est_sig) / ref_energy
        target = alpha * ref_sig
        res = est_sig - target
        return 10 * np.log10(np.sum(target ** 2) / (np.sum(res ** 2) + 1e-8))
        
    return sisdr_core(r, e), lag

def whole_file_enhance(audio_16k, model_path):
    print("Generating reference (whole-file enhance)...")
    resampler_up = soxr.ResampleStream(16000, 48000, 1, dtype=np.float32, quality='QQ')
    resampler_down = soxr.ResampleStream(48000, 16000, 1, dtype=np.float32, quality='QQ')
    
    audio_48k = resampler_up.resample_chunk(audio_16k.astype(np.float32))
    
    base = maybe_download_model('DeepFilterNet3')
    model, df_state, _ = init_df(base, log_file=None)
    
    import hk
    ckpt = hk.load_file(model_path)
    state_dict = ckpt['model_state_dict'] if 'model_state_dict' in ckpt else ckpt
    model.load_state_dict(state_dict, strict=True)
    model.to(torch.device("cpu"))
    model.eval()
    
    input_t = torch.from_numpy(audio_48k).unsqueeze(0).to(torch.device("cpu"))
    with torch.no_grad():
        enhanced_48k_t = enhance(model, df_state, input_t)
        
    enhanced_48k = enhanced_48k_t.squeeze(0).numpy()
    out_16k = resampler_down.resample_chunk(enhanced_48k)
    return out_16k

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    args = ap.add_argument("--model", default="/Users/shreyasdivekar/Documents/anc sih/runs/final_model/dfn3_final.hk")
    args = ap.parse_args()
    
    audio, sr = sf.read(args.input)
    if sr != 16000:
        raise ValueError("Requires 16kHz")
    
    # Truncate to exactly 60s if longer, or pad if shorter? The prompt says "60 s wav". I will just use the file as is.
    
    cfg = {
        'model_path': args.model, 
        'log_directory': "/tmp",
        'frame_ms': 16,
        'sample_rate': 16000
    }
    
    print("Initializing stream processor...")
    stream = DFN3Stream(cfg)
    
    print("Processing with process_frame in 256-sample chunks...")
    times = []
    out_chunks = []
    for i in range(0, len(audio), 256):
        chunk = audio[i:i+256]
        if len(chunk) < 256:
            chunk = np.pad(chunk, (0, 256-len(chunk)))
        t0 = time.perf_counter()
        out = stream.process_frame(chunk)
        times.append((time.perf_counter() - t0) * 1000.0)
        out_chunks.append(out)
        
    test1_out = np.concatenate(out_chunks)
    
    # 3. Reference whole-file enhance
    ref_out = whole_file_enhance(audio, args.model)
    
    # Score
    self_test, _ = compute_sisdr(audio, np.pad(audio, (123, 0))[:len(audio)])
    assert self_test > 60.0, f"Self-test failed: {self_test} dB"
    
    sisdr_test1_ref, lag_test1_ref = compute_sisdr(ref_out, test1_out)
    sisdr_test1_noisy, lag_test1_noisy = compute_sisdr(audio, test1_out)
    sisdr_ref_noisy, lag_ref_noisy = compute_sisdr(audio, ref_out)
    
    print("=== RESULTS ===")
    print(f"test1 vs ref: {sisdr_test1_ref:.2f} dB (lag: {lag_test1_ref} samples)")
    print(f"test1 vs noisy: {sisdr_test1_noisy:.2f} dB (lag: {lag_test1_noisy} samples)")
    print(f"ref vs noisy: {sisdr_ref_noisy:.2f} dB (lag: {lag_ref_noisy} samples)")
    
    os.makedirs("tools/equiv_output", exist_ok=True)
    sf.write("tools/equiv_output/test1_pi_stream.wav", test1_out, 16000)
    sf.write("tools/equiv_output/ref_whole_file.wav", ref_out, 16000)
    sf.write("tools/equiv_output/noisy_in.wav", audio, 16000)
    
    times = np.array(times)
    print(f"=== PERFORMANCE ===")
    print(f"Processing time per 256-sample chunk:")
    print(f"  p50: {np.median(times):.2f} ms")
    print(f"  p95: {np.percentile(times, 95):.2f} ms")
    print(f"  max: {np.max(times):.2f} ms")

if __name__ == '__main__':
    main()
