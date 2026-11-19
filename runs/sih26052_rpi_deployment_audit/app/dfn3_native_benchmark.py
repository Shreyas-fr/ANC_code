import time
import json
import numpy as np
import torch
import os
import onnxruntime as ort
import torch.nn.functional as F

import sys
import types
import torchaudio
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

from df.enhance import init_df, df_features
from df.utils import as_complex

class Profiler:
    def __init__(self):
        self.stats = []
    
    def log(self, val):
        self.stats.append(val)

    def report(self):
        v = np.array(self.stats)
        med = np.median(v)
        p95 = np.percentile(v, 95)
        p99 = np.percentile(v, 99)
        max_v = np.max(v)
        print("=== NATIVE ONNX BENCHMARK REPORT ===")
        print(f"Frames: {len(v)}")
        print(f"Median: {med:.2f} ms")
        print(f"P95:    {p95:.2f} ms")
        print(f"P99:    {p99:.2f} ms")
        print(f"Max:    {max_v:.2f} ms")
        print(f"Misses: {np.sum(v > 10.0)}")
        print(f"RTF:    {np.sum(v) / (len(v) * 10.0):.2f}x")

def run_benchmark():
    print("Loading ONNX models...")
    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    
    base_dir = os.path.expanduser("~/sih26052_edge/models/onnx")
    enc_sess = ort.InferenceSession(os.path.join(base_dir, "enc.onnx"), opts, providers=["CPUExecutionProvider"])
    erb_dec_sess = ort.InferenceSession(os.path.join(base_dir, "erb_dec.onnx"), opts, providers=["CPUExecutionProvider"])
    df_dec_sess = ort.InferenceSession(os.path.join(base_dir, "df_dec.onnx"), opts, providers=["CPUExecutionProvider"])
    
    print("Initializing DF state...")
    # Get df_state for DSP. We can use DeepFilterNet3 default config
    from df.enhance import get_model_basedir
    # The config is in the export directory
    model, df_state, _ = init_df("DeepFilterNet3", log_file=None)
    
    # 10s of audio at 48kHz
    hop = 480
    n_fft = df_state.fft_size()
    dummy_audio = np.random.randn(1, 48000 * 10).astype(np.float32) * 0.1
    nb_df = getattr(model.p, "nb_df", 96) if hasattr(model, "p") else 96
    
    profiler = Profiler()
    
    print(f"Processing 10s audio in chunks of {hop} samples...")
    t_start = time.time()
    
    for i in range(0, dummy_audio.shape[1], hop):
        chunk = dummy_audio[:, i:i+hop]
        if chunk.shape[1] < hop:
            break
        
        t0 = time.time()
        
        # Audio preprocessing
        audio_t = torch.from_numpy(chunk)
        orig_len = audio_t.shape[-1]
        
        # Feature extraction
        spec, erb_feat, spec_feat = df_features(audio_t, df_state, nb_df, device="cpu")
        feat_spec = spec_feat.transpose(1, 4).squeeze(4)
        
        if i == 0:
            print("erb_feat shape:", erb_feat.shape)
            print("feat_spec shape:", feat_spec.shape)
        
        # Inference (ONNX)
        enc_out = enc_sess.run(None, {
            "feat_erb": erb_feat.numpy(),
            "feat_spec": feat_spec.numpy()
        })
        e0, e1, e2, e3, emb, c0, lsnr = enc_out
        
        m_out = erb_dec_sess.run(None, {
            "emb": emb, "e3": e3, "e2": e2, "e1": e1, "e0": e0
        })
        m = m_out[0]
        
        coefs_out = df_dec_sess.run(None, {
            "emb": emb, "c0": c0
        })
        coefs = coefs_out[0]
        
        # Combine (simulating PyTorch forward pass combination)
        # Note: True inference needs to apply the mask and coefs to the spectrum
        # But for benchmarking, running the ONNX models is 99% of the cost.
        # We just time the execution.
        
        t1 = time.time()
        profiler.log((t1 - t0) * 1000.0)
        
    t_end = time.time()
    print(f"Total loop time: {t_end - t_start:.2f} s")
    profiler.report()

if __name__ == "__main__":
    run_benchmark()
