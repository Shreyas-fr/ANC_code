import time
import json
import numpy as np
import torch
import soundfile as sf
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

from df.enhance import init_df, maybe_download_model, enhance
from app.monitor import PerformanceMonitor
import torchaudio.functional as F_audio

class DFN3Stream:
    def __init__(self, config_dict):
        self.config = config_dict
            
        self.device = torch.device("cpu")
        
        print("Initializing DeepFilterNet3...")
        # init_df automatically loads the state for native 48kHz processing
        base = maybe_download_model('DeepFilterNet3')
        self.model, self.df_state, _ = init_df(base, log_file=None)
        
        # Load the custom finetuned pt checkpoint
        print(f"Loading custom fine-tuned weights from {self.config.get('model_path')}")
        import hk
        ckpt = hk.load_file(self.config['model_path'])
        
        # Depending on if it's a full state dict or wrapped
        state_dict = ckpt['model_state_dict'] if 'model_state_dict' in ckpt else ckpt
        self.model.load_state_dict(state_dict, strict=True)
        self.model.to(self.device)
        self.model.eval()
        
        self.sr_native = 48000
        self.hop_native = 480 # 10ms at 48kHz
        
        self.sr_io = self.config.get('sample_rate', 16000)
        self.hop_io = int(self.hop_native * (self.sr_io / self.sr_native)) # e.g. 160 at 16kHz
        
        # Resampling state (if needed for continuous stream)
        # DeepFilterNet operates at 48kHz, but if input is 16kHz, we should resample.
        # But wait, doing streaming resample in python is slow.
        # For this test, we assume the hardware or the audio pipeline gives us 48kHz.
        # If the input is 16kHz, we do a block-by-block resample for now.
        
        self.monitor = PerformanceMonitor(
            log_path=os.path.join(self.config['log_directory'], "runtime_metrics.csv"),
            deadline_ms=self.config['frame_ms']
        )
        
        self.reset_state()
        print("DFN3 Stream Ready.")

    def reset_state(self):
        # DFN state resets are handled internally by passing a fresh df_state?
        # Actually df_state is mutated in place, but we don't have a reset API exposed cleanly
        # Re-init is safest:
        base = maybe_download_model('DeepFilterNet3')
        _, self.df_state, _ = init_df(base, log_file=None)
        self.monitor.record_anomaly(state_reset=True)

    def process_frame(self, audio_chunk):
        """
        Process a single chunk.
        If audio_chunk is 16kHz, it upsamples to 48kHz, processes, and downsamples.
        """
        start_time = time.time()
        
        try:
            if np.isnan(audio_chunk).any() or np.isinf(audio_chunk).any():
                self.monitor.record_anomaly(nan_inf=True)
                self.reset_state()
                return audio_chunk # Fallback
                
            # If input is not 48kHz, resample it
            if self.sr_io != self.sr_native:
                chunk_48k_t = torch.from_numpy(audio_chunk).float().unsqueeze(0)
                chunk_48k_t = F_audio.resample(chunk_48k_t, self.sr_io, self.sr_native)
                chunk_48k = chunk_48k_t.squeeze(0).numpy()
            else:
                chunk_48k = audio_chunk.astype(np.float32)
                
            # DFN requires [1, N] tensor
            input_t = torch.from_numpy(chunk_48k).unsqueeze(0).to(self.device)
            
            with torch.no_grad():
                enhanced_48k_t = enhance(self.model, self.df_state, input_t)
                
            enhanced_48k = enhanced_48k_t.squeeze(0).numpy()
            
            if np.isnan(enhanced_48k).any() or np.isinf(enhanced_48k).any():
                self.monitor.record_anomaly(nan_inf=True)
                self.reset_state()
                return audio_chunk # Fallback
                
            if self.sr_io != self.sr_native:
                enhanced_48k_t = torch.from_numpy(enhanced_48k).float().unsqueeze(0)
                out_chunk_t = F_audio.resample(enhanced_48k_t, self.sr_native, self.sr_io)
                out_chunk = out_chunk_t.squeeze(0).numpy()
                # Trim/pad to match exact IO hop size due to resample edge effects
                if len(out_chunk) > len(audio_chunk):
                    out_chunk = out_chunk[:len(audio_chunk)]
                elif len(out_chunk) < len(audio_chunk):
                    out_chunk = np.pad(out_chunk, (0, len(audio_chunk) - len(out_chunk)))
            else:
                out_chunk = enhanced_48k
            
        except Exception as e:
            print(f"Exception in process_frame: {e}")
            self.monitor.record_anomaly(dropped=True)
            return audio_chunk # Fallback
            
        proc_time_ms = (time.time() - start_time) * 1000
        self.monitor.record_frame(proc_time_ms)
        
        return out_chunk

    def run_file(self, in_file, out_file):
        audio, sr = sf.read(in_file)
        if sr != self.sr_io:
            raise ValueError(f"Expected {self.sr_io} Hz, got {sr}")
            
        hop = self.hop_io
        out_audio = []
        
        print(f"Processing {len(audio)/sr:.2f} seconds of audio in chunks of {hop} samples...")
        
        for i in range(0, len(audio), hop):
            chunk = audio[i:i+hop]
            if len(chunk) < hop:
                chunk = np.pad(chunk, (0, hop - len(chunk)))
            out = self.process_frame(chunk)
            out_audio.extend(out)
            
            if i % (hop * 100) == 0:
                self.monitor.flush_log()
                
        self.monitor.flush_log(force=True)
        sf.write(out_file, out_audio[:len(audio)], sr)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        config_path = os.path.expanduser("~/sih26052_edge/config/config.json")
        # Ensure we patch config to point to DFN3 pt model
        with open(config_path, "r") as f:
            cfg = json.load(f)
        cfg['model_path'] = os.path.expanduser("~/sih26052_edge/models/dfn3_final.pt")
        cfg['sample_rate'] = 48000
        # DFN runs natively at 48k 10ms frame (480). If we give it 48kHz, it avoids resampling overhead.
        
        stream = DFN3Stream(cfg)
        
        dummy_audio = np.random.randn(48000 * 10).astype(np.float32) * 0.1
        sf.write("/tmp/test_in_48k.wav", dummy_audio, 48000)
        
        t0 = time.time()
        stream.run_file("/tmp/test_in_48k.wav", "/tmp/test_out_48k.wav")
        t1 = time.time()
        print(f"30-second test completed in {t1-t0:.2f} seconds.")
        
        import csv
        frames = 0
        misses = 0
        p50 = []
        p95 = []
        p99 = []
        max_t = 0
        
        with open(os.path.expanduser("~/sih26052_edge/logs/runtime_metrics.csv"), "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                frames = max(frames, int(row['frames_processed']))
                misses = max(misses, int(row['deadline_misses']))
                p50.append(float(row['p50_ms']))
                p95.append(float(row['p95_ms']))
                p99.append(float(row['p99_ms']))
                max_t = max(max_t, float(row['max_ms']))
                
        print(f"Metrics - Frames: {frames}, Misses: {misses}, P95: {np.median(p95):.2f}ms, Max: {max_t:.2f}ms")
    else:
        print("Use 'python3 dfn3_stream.py test' to benchmark")
