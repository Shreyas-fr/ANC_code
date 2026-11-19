import time
import soundfile as sf
import numpy as np
import os
import torch
import sys
import types

try:
    import torchaudio
    if not hasattr(getattr(torchaudio, "backend", None), "common"):
        cm = types.ModuleType("torchaudio.backend.common")

        class AudioMetaData:
            def __init__(self, sr, nf, nc, bps, enc):
                self.sample_rate = sr
                self.num_frames = nf
                self.num_channels = nc
                self.bits_per_sample = bps
                self.encoding = enc

        cm.AudioMetaData = AudioMetaData
        sys.modules["torchaudio.backend.common"] = cm
        if not hasattr(torchaudio, "backend"):
            bm = types.ModuleType("torchaudio.backend")
            bm.common = cm
            sys.modules["torchaudio.backend"] = bm
            torchaudio.backend = bm
        else:
            torchaudio.backend.common = cm
except Exception:
    pass

from df.enhance import init_df, enhance, maybe_download_model
from df.io import resample
import torch

class FakeDFN3:
    def __init__(self, model_path):
        base = maybe_download_model("DeepFilterNet3")
        _res = init_df(base, log_file=None)
        self.model, self.df_state = _res[0], _res[1]
        
        # Load custom weights
        import hk
        ckpt = hk.load_file(model_path)
        if isinstance(ckpt, dict) and "model_state_dict" in ckpt:
            self.model.load_state_dict(ckpt["model_state_dict"], strict=True)
        elif isinstance(ckpt, dict) and "state_dict" in ckpt:
            self.model.load_state_dict(ckpt["state_dict"], strict=True)
        else:
            self.model.load_state_dict(ckpt, strict=True)
        self.model.eval()
        
    def __call__(self, audio_np):
        audio = torch.from_numpy(audio_np).unsqueeze(0).float()
        audio = resample(audio, 16000, self.df_state.sr())
        enhanced = enhance(self.model, self.df_state, audio)
        enhanced = resample(enhanced, self.df_state.sr(), 16000)
        return enhanced.squeeze(0).numpy()

class BlockBackend:
    def __init__(self, fn, block_ms, context_ms, sr=16000):
        self.fn = fn
        self.block_samples = int(block_ms * sr / 1000)
        self.context_samples = int(context_ms * sr / 1000)
        self.sr = sr
        self.buffer = np.zeros(0, dtype=np.float32)
        self.context = np.zeros(self.context_samples, dtype=np.float32)
        
    def process(self, chunk):
        self.buffer = np.concatenate([self.buffer, chunk])
        out_chunks = []
        while len(self.buffer) >= self.block_samples:
            block = self.buffer[:self.block_samples]
            self.buffer = self.buffer[self.block_samples:]
            
            # Combine context and block
            x = np.concatenate([self.context, block])
            # Update context
            if self.context_samples > 0:
                self.context = block[-self.context_samples:]
                
            y = self.fn(x)
            
            # Keep only the block part
            # Wait, does the model preserve length perfectly?
            # Yes, DFN3Stream does resampling and hop processing.
            # But DFN3Stream has algorithmic latency!
            # If we pass a 800ms chunk, the output might be shorter due to latency?
            # No, DFN3Stream.process_pcm16k returns exactly what it can.
            # Actually, `fn` should be a stateless evaluation.
            
            # The sender expects `fn` to return the same length as input.
            if len(y) > self.context_samples:
                out_block = y[self.context_samples:]
            else:
                out_block = np.zeros(self.block_samples, dtype=np.float32)
                
            # Pad if needed
            if len(out_block) < self.block_samples:
                out_block = np.pad(out_block, (0, self.block_samples - len(out_block)))
            elif len(out_block) > self.block_samples:
                out_block = out_block[:self.block_samples]
                
            out_chunks.append(out_block)
            
        if out_chunks:
            return np.concatenate(out_chunks)
        else:
            return np.zeros(0, dtype=np.float32)

def rms_db(audio):
    rms = np.sqrt(np.mean(audio**2))
    return 20 * np.log10(rms) if rms > 0 else -999

def run_refs():
    model_path = "/Users/shreyasdivekar/Documents/anc sih/runs/final_model/model.hk"
    din, sr = sf.read("/Users/shreyasdivekar/anc_tests/D_in.wav")
    
    fn = FakeDFN3(model_path)
    
    # 1. Whole file
    t0 = time.time()
    out_whole = fn(din)
    t_whole = time.time() - t0
    rtf_whole = t_whole / (len(din) / sr)
    sf.write("/Users/shreyasdivekar/anc_tests/D_ref_whole.wav", out_whole, sr)
    
    # 2. Block mode
    backend = BlockBackend(fn, block_ms=500, context_ms=300)
    
    t0 = time.time()
    out_block_chunks = []
    chunk_size = 256
    for i in range(0, len(din), chunk_size):
        chunk = din[i:i+chunk_size]
        if len(chunk) < chunk_size:
            chunk = np.pad(chunk, (0, chunk_size - len(chunk)))
        out_chunk = backend.process(chunk)
        if len(out_chunk) > 0:
            out_block_chunks.append(out_chunk)
            
    out_block = np.concatenate(out_block_chunks)[:len(din)]
    t_block = time.time() - t0
    rtf_block = t_block / (len(din) / sr)
    sf.write("/Users/shreyasdivekar/anc_tests/D_ref_block.wav", out_block, sr)
    
    print(f"Whole file RTF: {rtf_whole:.3f} (Time: {t_whole:.2f}s)")
    print(f"Block mode RTF: {rtf_block:.3f} (Time: {t_block:.2f}s)")
    
    n_min = min(len(out_block), len(out_whole))
    diff = out_block[:n_min] - out_whole[:n_min]
    
    print(f"Null test (Block - Whole) RMS: {rms_db(diff):.2f} dB")

if __name__ == "__main__":
    run_refs()
