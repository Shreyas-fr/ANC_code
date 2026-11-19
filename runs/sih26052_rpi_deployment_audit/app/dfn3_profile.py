import time
import json
import numpy as np
import torch
import os
import sys

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

from df.enhance import init_df, maybe_download_model, df_features
from df.utils import as_complex
import torch.nn.functional as F

class Profiler:
    def __init__(self):
        self.stats = {
            "pad": [],
            "features": [],
            "inference": [],
            "complex_conv": [],
            "istft": [],
            "crop": [],
            "total": [],
        }
    
    def log(self, phase, t0, t1):
        self.stats[phase].append((t1 - t0) * 1000.0)

    def report(self):
        print("=== PROFILING REPORT (ms) ===")
        for k, v in self.stats.items():
            if len(v) == 0: continue
            med = np.median(v)
            p95 = np.percentile(v, 95)
            print(f"{k.ljust(15)} Median: {med:6.2f} ms | P95: {p95:6.2f} ms")


def run_profile(config_path):
    with open(config_path, "r") as f:
        cfg = json.load(f)
    cfg['model_path'] = os.path.expanduser("~/sih26052_edge/models/dfn3_final.pt")
    
    print("Initializing DeepFilterNet3...")
    base = maybe_download_model('DeepFilterNet3')
    model, df_state, _ = init_df(base, log_file=None)
    
    ckpt = torch.load(cfg['model_path'], map_location='cpu')
    state_dict = ckpt['model_state_dict'] if 'model_state_dict' in ckpt else ckpt
    model.load_state_dict(state_dict, strict=True)
    model.to(torch.device("cpu"))
    model.eval()

    profiler = Profiler()
    
    # 10s of audio at 48kHz
    hop = 480
    n_fft = df_state.fft_size()
    dummy_audio = np.random.randn(1, 48000 * 10).astype(np.float32) * 0.1
    nb_df = getattr(model, "nb_df", 0)
    if nb_df == 0: nb_df = getattr(model, "df_bins", 32)
    device = torch.device("cpu")
    
    # Pre-warm
    if hasattr(model, "reset_h0"):
        model.reset_h0(batch_size=1, device=device)
        
    print(f"Processing in chunks of {hop} samples...")
    for i in range(0, dummy_audio.shape[1], hop):
        chunk = dummy_audio[:, i:i+hop]
        if chunk.shape[1] < hop:
            break
        
        t_start = time.time()
        audio_t = torch.from_numpy(chunk).to(device)
        orig_len = audio_t.shape[-1]
        
        t0 = time.time()
        audio_t = F.pad(audio_t, (0, n_fft))
        t1 = time.time()
        profiler.log("pad", t0, t1)
        
        # features
        spec, erb_feat, spec_feat = df_features(audio_t, df_state, nb_df, device=device)
        t2 = time.time()
        profiler.log("features", t1, t2)
        
        # inference
        with torch.no_grad():
            enhanced = model(spec.clone(), erb_feat, spec_feat)[0].cpu()
        t3 = time.time()
        profiler.log("inference", t2, t3)
        
        # complex conv
        enhanced = as_complex(enhanced.squeeze(1))
        t4 = time.time()
        profiler.log("complex_conv", t3, t4)
        
        # istft
        out_audio = torch.as_tensor(df_state.synthesis(enhanced.numpy()))
        t5 = time.time()
        profiler.log("istft", t4, t5)
        
        # crop
        d = n_fft - hop
        out_audio = out_audio[:, d : orig_len + d]
        t6 = time.time()
        profiler.log("crop", t5, t6)
        
        profiler.log("total", t_start, t6)
        
    profiler.report()

if __name__ == "__main__":
    config_path = os.path.expanduser("~/sih26052_edge/config/config.json")
    run_profile(config_path)
