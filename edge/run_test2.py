import sys, os
sys.path.insert(0, os.path.expanduser("~/Downloads/anc_fix 2"))
import time
import numpy as np
import soundfile as sf
import torch
import soxr

# Shim for torchaudio backend compatibility
import types, torchaudio
if not hasattr(getattr(torchaudio, "backend", None), "common"):
    cm = types.ModuleType("torchaudio.backend.common")
    class AudioMetaData:
        def __init__(self, sr, nf, nc, bps, enc):
            self.sample_rate=sr; self.num_frames=nf
            self.num_channels=nc; self.bits_per_sample=bps; self.encoding=enc
    cm.AudioMetaData = AudioMetaData
    sys.modules["torchaudio.backend.common"] = cm
    if not hasattr(torchaudio, "backend"):
        bm = types.ModuleType("torchaudio.backend")
        bm.common = cm
        sys.modules["torchaudio.backend"] = bm
        torchaudio.backend = bm
    else:
        torchaudio.backend.common = cm

from streaming_core import AudioChain, BlockBackend
from dfn3_enhance import make_dfn3_enhance_fn
import scipy.signal

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

def main():
    wav_path = "/tmp/sih26052_edge/audio/shreyaswork_input.wav"
    audio, sr = sf.read(wav_path)
    if sr != 16000:
        raise ValueError("Requires 16kHz")
        
    model_path = "/tmp/sih26052_edge/models/dfn3_final.hk"
    
    print("Generating ref_fir...")
    import torchaudio.functional as F_audio
    audio_t = torch.from_numpy(audio).float()
    audio_48k = F_audio.resample(audio_t, 16000, 48000, rolloff=0.99, lowpass_filter_width=64).numpy()
    
    from df.enhance import init_df, maybe_download_model, enhance
    import hk
    base = maybe_download_model('DeepFilterNet3')
    model, df_state, _ = init_df(base, log_file=None)
    ckpt = hk.load_file(model_path)
    state_dict = ckpt['model_state_dict'] if 'model_state_dict' in ckpt else ckpt
    model.load_state_dict(state_dict, strict=True)
    model.to(torch.device("cpu"))
    model.eval()
    
    input_t = torch.from_numpy(audio_48k).unsqueeze(0).to(torch.device("cpu"))
    with torch.no_grad():
        enhanced_48k_t = enhance(model, df_state, input_t)
    
    enhanced_48k = enhanced_48k_t.squeeze(0).numpy()
    ref_fir = F_audio.resample(torch.from_numpy(enhanced_48k), 48000, 16000, rolloff=0.99, lowpass_filter_width=64).numpy()
    
    os.makedirs("tools/equiv_output", exist_ok=True)
    sf.write("tools/equiv_output/ref_fir.wav", ref_fir, 16000)
    
    # We already have test1 out, so I won't re-run it unless I want it in the same run.
    # The user says "Put test1 and test2 in one table", I'll just print them.
    # The previous test1 results: vs ref = -1.62, vs noisy = -1.58.
    
    contexts = [300, 1000, 2000]
    block_ms = 500
    
    for ctx in contexts:
        print(f"\n--- test2 (block={block_ms}ms, context={ctx}ms) ---")
        fn = make_dfn3_enhance_fn(model_path, threads=1)
        backend = BlockBackend(fn, block_ms=block_ms, context_ms=ctx)
        chain = AudioChain(backend)
        
        parts = []
        t0 = time.perf_counter()
        for i in range(0, len(audio), 256):
            chunk = audio[i:i+256]
            if len(chunk) < 256:
                chunk = np.pad(chunk, (0, 256-len(chunk)))
            parts.append(chain.process(chunk.astype(np.float32)))
            
        elapsed = time.perf_counter() - t0
        test2_out = np.concatenate(parts)
        bs = backend.stats()
        
        sf.write(f"tools/equiv_output/test2_ctx{ctx}.wav", test2_out, 16000)
        
        sisdr_vs_ref, lag_ref = compute_sisdr(ref_fir, test2_out)
        sisdr_vs_noisy, lag_noisy = compute_sisdr(audio, test2_out)
        
        print(f"test2_ctx{ctx} vs ref_fir: {sisdr_vs_ref:.2f} dB (lag: {lag_ref} samples)")
        print(f"test2_ctx{ctx} vs noisy: {sisdr_vs_noisy:.2f} dB (lag: {lag_noisy} samples)")
        print(f"Stats: compute_rtf={bs.get('compute_rtf',0):.3f} windows={bs.get('windows',0)} errors={bs.get('enhance_errors',0)}")

if __name__ == '__main__':
    main()
