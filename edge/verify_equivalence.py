#!/usr/bin/env python3
"""tools/verify_equivalence.py
Compare audio processing paths on a 16 kHz speech wav.
"""
from __future__ import annotations
import argparse, os, sys, time, types
import numpy as np
import soundfile as sf

def sisdr(ref, est, max_lag=32000):
    import scipy.signal
    ref = ref.astype(np.float64); est = est.astype(np.float64)
    n = min(len(ref), len(est)); ref, est = ref[:n], est[:n]
    
    # Fast FFT cross-correlation to find the best lag
    search = min(max_lag, n//4)
    r_cen = ref[search:n-search]
    r_cen = r_cen - r_cen.mean()
    e_norm = est - est.mean()
    
    # correlate(est, r_cen) -> length n + (n - 2*search) - 1
    # max value tells us where r_cen aligns best within est
    corr = scipy.signal.correlate(e_norm, r_cen, mode='valid', method='fft')
    best_idx = np.argmax(np.abs(corr))
    # best_idx is the start index of r_cen inside e_norm.
    # We want 'lag' such that est shifts to align with ref.
    # If best_idx == search, they are aligned (lag=0).
    # If best_idx > search, est is delayed -> lag = best_idx - search.
    lag = best_idx - search
    
    # User's corrected pairing:
    r, e = (ref[:n-lag], est[lag:]) if lag >= 0 else (ref[-lag:], est[:n+lag])
    
    if len(r) < 100: return -999.0, lag
    r -= r.mean(); e -= e.mean()
    a = np.dot(r,e)/(np.dot(r,r)+1e-20)
    noise = e - a*r
    v = 10*np.log10((a**2*np.dot(r,r))/(np.dot(noise,noise)+1e-20)+1e-20)
    return float(v), int(lag)

def resample_linear(x, in_sr, out_sr):
    if in_sr == out_sr: return x.astype(np.float32)
    ratio = out_sr/in_sr; n_out = int(len(x)*ratio)
    idx = np.arange(n_out)/ratio; i = np.clip(np.floor(idx).astype(np.int64), 0, len(x)-2)
    return (x[i]*(1.0-idx+i) + x[i+1]*(idx-i)).astype(np.float32)

def _shim():
    try:
        import torchaudio
        if not hasattr(getattr(torchaudio,"backend",None),"common"):
            cm = types.ModuleType("torchaudio.backend.common")
            class AudioMetaData:
                def __init__(self,sr,nf,nc,bps,enc):
                    self.sample_rate,self.num_frames,self.num_channels=sr,nf,nc
                    self.bits_per_sample,self.encoding=bps,enc
            cm.AudioMetaData = AudioMetaData
            sys.modules["torchaudio.backend.common"] = cm
            if not hasattr(torchaudio,"backend"):
                bm=types.ModuleType("torchaudio.backend"); bm.common=cm
                sys.modules["torchaudio.backend"]=bm; torchaudio.backend=bm
            else:
                torchaudio.backend.common=cm
    except Exception: pass

def _init_df_compat(base):
    from df.enhance import init_df
    r = init_df(base, log_file=None)
    if len(r) == 4:
        return r[0], r[1]
    return r[0], r[1]

def make_reference(noisy_16k, model_path):
    import torch, hk
    _shim()
    from df.enhance import enhance, maybe_download_model
    torch.set_num_threads(2)
    base = maybe_download_model("DeepFilterNet3")
    model, df_state = _init_df_compat(base)
    ckpt = hk.load_file(model_path)
    state = ckpt.get("model_state_dict", ckpt)
    model.load_state_dict(state, strict=True); model.eval()

    sr_n = int(df_state.sr())
    a48 = resample_linear(noisy_16k, 16000, sr_n)
    print("  [ref] df.enhance() on %.1fs @ %d Hz ..." % (len(a48)/sr_n, sr_n))
    t0 = time.perf_counter()
    with torch.no_grad():
        out48 = enhance(model, df_state, torch.from_numpy(a48).unsqueeze(0))
    elapsed = time.perf_counter()-t0
    print("  [ref] Done %.2fs RTF=%.3f" % (elapsed, elapsed/(len(a48)/sr_n)))
    return resample_linear(out48.squeeze(0).cpu().numpy().astype(np.float32), sr_n, 16000)

def run_control_b(noisy_16k, model_path, anc_fix_dir):
    sys.path.insert(0, anc_fix_dir)
    from dfn3_enhance import make_dfn3_enhance_fn
    print("  [Control B] Loading make_dfn3_enhance_fn ...")
    fn = make_dfn3_enhance_fn(model_path, threads=2)
    a48 = resample_linear(noisy_16k, 16000, 48000)
    print("  [Control B] Enhancing whole 48k file ...")
    out48 = fn(a48)
    return resample_linear(out48, 48000, 16000)

def run_test1(noisy_16k, model_path, chunk=256):
    _shim()
    import sys
    if "df.enhance" not in sys.modules: import df.enhance
    _orig_init = sys.modules["df.enhance"].init_df
    def _patched_init(*a, **kw):
        r = _orig_init(*a, **kw)
        return (r[0], r[1], None, None) if len(r)==3 else r
    sys.modules["df.enhance"].init_df = _patched_init

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runs", "final_model"))
    if "dfn3_stream" in sys.modules: del sys.modules["dfn3_stream"]
    from dfn3_stream import DFN3Stream

    cfg = {"model_path": model_path, "sample_rate": 16000}
    print("  [test1] Init DFN3Stream ...")
    t0 = time.perf_counter()
    stream = DFN3Stream(cfg)
    print("  [test1] Init %.1fs. Processing %d samples ..." % (time.perf_counter()-t0, len(noisy_16k)))
    parts = []; t0 = time.perf_counter()
    try:
        for i in range(0, len(noisy_16k), chunk):
            y = stream.process_pcm16k(noisy_16k[i:i+chunk].astype(np.float32))
            if len(y): parts.append(y)
        elapsed = time.perf_counter()-t0
        print("  [test1] Done %.2fs RTF=%.3f state_resets=%d nan_inf=%d misses=%d" % (
            elapsed, elapsed/(len(noisy_16k)/16000), stream.state_resets-1, stream.nan_inf_count, stream.deadline_misses))
    except Exception as e:
        print(f"  [test1] CRASHED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc(file=sys.stdout)
        parts = None
    sys.modules["df.enhance"].init_df = _orig_init
    return np.concatenate(parts) if parts is not None else None

def run_test2(noisy_16k, model_path, anc_fix_dir, block_ms=500, context_ms=300, chunk=256, is_control_a=False):
    _shim()
    sys.path.insert(0, anc_fix_dir)
    if "streaming_core" in sys.modules: del sys.modules["streaming_core"]
    if "dfn3_enhance" in sys.modules: del sys.modules["dfn3_enhance"]
    from streaming_core import AudioChain, BlockBackend
    from dfn3_enhance import make_dfn3_enhance_fn

    if is_control_a:
        print("  [Control A] Using IDENTITY enhance_fn ...")
        fn = lambda w: w.copy()
    else:
        print("  [test2] Loading model (block=%dms ctx=%dms) ..." % (block_ms, context_ms))
        fn = make_dfn3_enhance_fn(model_path, threads=2)
    
    t0 = time.perf_counter()
    backend = BlockBackend(fn, block_ms=block_ms, context_ms=context_ms)
    chain = AudioChain(backend)
    lat = chain.latency_ms()
    print("  [Chain] Init %.1fs  algorithmic_latency=%.1fms  %s" % (time.perf_counter()-t0, lat["algorithmic_total_ms"], lat))
    parts = []; t0 = time.perf_counter()
    for i in range(0, len(noisy_16k), chunk):
        parts.append(chain.process(noisy_16k[i:i+chunk].astype(np.float32)))
    elapsed = time.perf_counter()-t0
    bs = backend.stats()
    print("  [Chain] Done %.2fs RTF=%.3f windows=%d errors=%d compute_rtf=%.3f underruns=%d" % (
        elapsed, elapsed/(len(noisy_16k)/16000), bs["windows"], bs["enhance_errors"], bs.get("compute_rtf",0), chain.underruns))
    return np.concatenate(parts), lat["algorithmic_total_ms"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--model", default=os.path.expanduser("~/sih26052_edge/models/dfn3_final.hk"))
    ap.add_argument("--anc-fix", default=os.path.expanduser("~/Downloads/anc_fix 2"))
    ap.add_argument("--out-dir", default="tools/equiv_output")
    ap.add_argument("--block-ms", type=int, default=500)
    ap.add_argument("--context-ms", type=int, default=300)
    ap.add_argument("--chunk", type=int, default=256)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    print("\n=== verify_equivalence.py ===")

    noisy, sr = sf.read(args.input)
    if noisy.ndim > 1: noisy = noisy[:,0]
    noisy = noisy.astype(np.float32)
    print("Loaded %.1fs @ %d Hz\n" % (len(noisy)/sr, sr))
    
    # Self-test sisdr with 9024 lag
    test_shift = 9024
    test_est = np.concatenate([np.zeros(test_shift, dtype=np.float32), noisy])
    st_val, st_lag = sisdr(noisy, test_est)
    assert st_val > 60.0 and st_lag == test_shift, f"sisdr self-test failed: val={st_val} lag={st_lag}"

    print("=== ref ===")
    ref = make_reference(noisy, args.model)
    
    print("\n=== Control A: AudioChain Identity ===")
    ctrl_a, lat_a = run_test2(noisy, args.model, args.anc_fix, args.block_ms, args.context_ms, args.chunk, is_control_a=True)
    
    print("\n=== Control B: dfn3_enhance on whole file ===")
    ctrl_b = run_control_b(noisy, args.model, args.anc_fix)

    print("\n=== test1: DFN3Stream 256-chunk ===")
    test1 = run_test1(noisy, args.model, chunk=args.chunk)

    print("\n=== test2: AudioChain+BlockBackend block=%dms ===" % args.block_ms)
    test2, lat_2 = run_test2(noisy, args.model, args.anc_fix, args.block_ms, args.context_ms, args.chunk)

    print("\n" + "="*80)
    print("SI-SDR RESULTS (best-lag ±32000 samples [±2 sec], higher=better)")
    print("="*80)
    def row(a_name, a, b_name, b, expected_lat_ms=0):
        v, lag = sisdr(a, b, max_lag=32000)
        lag_ms = (lag / 16000.0) * 1000.0
        print("  %-35s vs %-15s : %+.2f dB  | Lag: %5d spls (%7.1f ms) [Alg Lat: %5.1f ms]" % (
            a_name, b_name, v, lag, lag_ms, expected_lat_ms))
        return v, lag

    row("Control A (Identity Chain)", ctrl_a, "noisy input", noisy, expected_lat_ms=lat_a)
    row("Control B (dfn3 adapter)", ctrl_b, "ref", ref)
    row("ref (whole-file)", ref, "noisy input", noisy)
    
    if test1 is not None:
        row("test1 (DFN3Stream)", test1, "ref", ref)
        row("test1 (DFN3Stream)", test1, "noisy input", noisy)
        
    if test2 is not None:
        row("test2 (AudioChain)", test2, "ref", ref, expected_lat_ms=lat_2)
        row("test2 (AudioChain)", test2, "noisy input", noisy, expected_lat_ms=lat_2)

    print("="*80)
    print("\nWavs: %s/" % os.path.abspath(args.out_dir))

if __name__ == "__main__":
    main()
