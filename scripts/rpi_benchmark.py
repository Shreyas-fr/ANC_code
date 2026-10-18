import torch
import torch.nn.functional as F
import time
import numpy as np
import os
import psutil
import subprocess
import threading
import sys
import math

class RPiBenchmark:
    def __init__(self, model_path="best.pt"):
        self.device = torch.device('cpu')
        
        from stateful_polar_lstm import StatefulPolarLSTM
        self.core = StatefulPolarLSTM().to(self.device)
        state_dict = torch.load(model_path, map_location=self.device)
        
        # remap keys if it was saved from wrapper
        new_state_dict = {}
        for k, v in state_dict.items():
            if k.startswith("core."):
                new_state_dict[k.replace("core.", "")] = v
            else:
                new_state_dict[k] = v
                
        self.core.load_state_dict(new_state_dict, strict=False)
        self.core.eval()
        
        self.n_fft = 512
        self.hop_length = 256
        self.window = torch.hann_window(self.n_fft).to(self.device)
        
    def measure_temp(self):
        try:
            res = subprocess.check_output(["vcgencmd", "measure_temp"]).decode('utf-8')
            return float(res.replace("temp=", "").replace("'C\n", ""))
        except:
            return 0.0
            
    def measure_freq(self):
        try:
            res = subprocess.check_output(["cat", "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"]).decode('utf-8')
            return float(res.strip()) / 1000.0
        except:
            return 0.0

    def get_ram(self):
        return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024

    def run_all(self):
        self.phase_5_load_test()
        self.phase_6_statefulness()
        self.phase_7_8_microbenchmark()
        self.phase_9_streaming()

    def phase_5_load_test(self):
        print("\n--- PHASE 5: MODEL LOAD TEST ---")
        params = sum(p.numel() for p in self.core.parameters())
        print(f"Model Parameters: {params}")
        
        dummy_in = torch.randn(1, 1, 514)
        h_in = torch.zeros(2, 1, 256)
        c_in = torch.zeros(2, 1, 256)
        
        mr, mi, h_out, c_out, mag, phase = self.core(dummy_in, h_in, c_in)
        
        print(f"Input shape: {dummy_in.shape}")
        print(f"Recurrent input shape: h={h_in.shape}, c={c_in.shape}")
        print(f"Output shape (mr/mi): {mr.shape}")
        print(f"Recurrent output shape: h={h_out.shape}, c={c_out.shape}")
        
        if torch.isnan(mr).any() or torch.isinf(mr).any():
            print("Output NaN/Inf: YES")
        else:
            print("Output NaN/Inf: NO")
            
        print("Model size (MB):", os.path.getsize("best.pt") / (1024*1024))

    def phase_6_statefulness(self):
        print("\n--- PHASE 6: STATEFULNESS TEST ---")
        torch.manual_seed(1234)
        f1 = torch.randn(1, 1, 514)
        f2 = torch.randn(1, 1, 514)
        f3 = torch.randn(1, 1, 514)
        
        h_0 = torch.zeros(2, 1, 256)
        c_0 = torch.zeros(2, 1, 256)
        
        # Sequential
        mr1, mi1, h1, c1, _, _ = self.core(f1, h_0, c_0)
        mr2, mi2, h2, c2, _, _ = self.core(f2, h1, c1)
        mr3, mi3, h3, c3, _, _ = self.core(f3, h2, c2)
        
        # Reset state at step 2
        mr2_reset, mi2_reset, h2_reset, c2_reset, _, _ = self.core(f2, h_0, c_0)
        
        diff = torch.max(torch.abs(mr2 - mr2_reset)).item()
        
        if diff > 1e-4:
            print("STATEFUL_DEPLOYMENT_STATUS=PASS")
        else:
            print("STATEFUL_DEPLOYMENT_STATUS=FAIL")
            print(f"Diff: {diff}")

    def phase_7_8_microbenchmark(self):
        print("\n--- PHASE 7 & 8: MICROBENCHMARK ---")
        N_FRAMES = 1000
        
        print(f"Initial Temp: {self.measure_temp():.1f}C")
        print(f"Initial Freq: {self.measure_freq():.0f} MHz")
        print(f"Initial RAM: {self.get_ram():.1f} MB")
        
        # Warmup
        h_in = torch.zeros(2, 1, 256)
        c_in = torch.zeros(2, 1, 256)
        for _ in range(50):
            audio = torch.randn(1, 512)
            stft = torch.stft(audio, n_fft=self.n_fft, hop_length=self.hop_length, window=self.window, return_complex=True, center=False)
            feats = torch.cat([stft.transpose(1, 2).real, stft.transpose(1, 2).imag], dim=-1)
            mr, mi, h_in, c_in, _, _ = self.core(feats, h_in, c_in)
            mask = torch.complex(mr, mi).transpose(1, 2)
            enh = stft * mask
            out = torch.fft.irfft(enh, n=self.n_fft, dim=1)
            
        times_stft = []
        times_model = []
        times_istft = []
        times_total = []
        
        temps = []
        freqs = []
        cpu_utils = []
        
        audio_stream = torch.randn(1, N_FRAMES * self.hop_length + self.n_fft)
        
        for i in range(N_FRAMES):
            start_sample = i * self.hop_length
            chunk = audio_stream[:, start_sample:start_sample + self.n_fft]
            
            t0 = time.perf_counter()
            stft = torch.stft(chunk, n_fft=self.n_fft, hop_length=self.hop_length, window=self.window, return_complex=True, center=False)
            feats = torch.cat([stft.transpose(1, 2).real, stft.transpose(1, 2).imag], dim=-1)
            t1 = time.perf_counter()
            
            mr, mi, h_in, c_in, _, _ = self.core(feats, h_in, c_in)
            t2 = time.perf_counter()
            
            mask = torch.complex(mr, mi).transpose(1, 2)
            enh = stft * mask
            # For causal real-time streaming istft on one frame (OLA is omitted for pure NN timing, just irfft + window)
            frames = torch.fft.irfft(enh, n=self.n_fft, dim=1)
            frames = frames * self.window.view(1, -1, 1)
            t3 = time.perf_counter()
            
            times_stft.append((t1 - t0)*1000)
            times_model.append((t2 - t1)*1000)
            times_istft.append((t3 - t2)*1000)
            times_total.append((t3 - t0)*1000)
            
            if i % 200 == 0:
                temps.append(self.measure_temp())
                freqs.append(self.measure_freq())
                cpu_utils.append(psutil.cpu_percent())
                
        def stats(arr):
            arr = np.array(arr)
            return {
                "mean": np.mean(arr), "median": np.median(arr), 
                "p50": np.percentile(arr, 50), "p90": np.percentile(arr, 90),
                "p95": np.percentile(arr, 95), "p99": np.percentile(arr, 99),
                "max": np.max(arr), "std": np.std(arr)
            }
            
        print("Total Processing Stats (ms):", stats(times_total))
        print("Model Processing Stats (ms):", stats(times_model))
        
        miss_rate = np.mean(np.array(times_total) > 16.0)
        p95 = np.percentile(times_total, 95)
        print(f"Deadline miss rate (>16ms): {miss_rate*100:.2f}%")
        print(f"Real-time factor: {16.0 / p95:.4f}")
        
        print(f"Final Temp: {self.measure_temp():.1f}C")
        print(f"Final Freq: {self.measure_freq():.0f} MHz")
        print(f"Final RAM: {self.get_ram():.1f} MB")
        
        with open("microbenchmark.csv", "w") as f:
            f.write("metric,mean,median,p50,p90,p95,p99,max,std\n")
            for k, v in {"stft": times_stft, "model": times_model, "istft": times_istft, "total": times_total}.items():
                s = stats(v)
                f.write(f"{k},{s['mean']},{s['median']},{s['p50']},{s['p90']},{s['p95']},{s['p99']},{s['max']},{s['std']}\n")
                
        with open("thermal_monitoring.csv", "w") as f:
            f.write("step,temp_C,freq_MHz,cpu_util\n")
            for i in range(len(temps)):
                f.write(f"{i*200},{temps[i]},{freqs[i]},{cpu_utils[i]}\n")
                
    def phase_9_streaming(self):
        print("\n--- PHASE 9: CONTINUOUS STREAMING TEST ---")
        N_FRAMES = 3750 # 60 seconds
        audio_stream = torch.randn(1, N_FRAMES * self.hop_length + self.n_fft)
        
        h_in = torch.zeros(2, 1, 256)
        c_in = torch.zeros(2, 1, 256)
        
        misses = 0
        nans = 0
        
        for i in range(N_FRAMES):
            start_sample = i * self.hop_length
            chunk = audio_stream[:, start_sample:start_sample + self.n_fft]
            
            t0 = time.perf_counter()
            stft = torch.stft(chunk, n_fft=self.n_fft, hop_length=self.hop_length, window=self.window, return_complex=True, center=False)
            feats = torch.cat([stft.transpose(1, 2).real, stft.transpose(1, 2).imag], dim=-1)
            mr, mi, h_in, c_in, _, _ = self.core(feats, h_in, c_in)
            mask = torch.complex(mr, mi).transpose(1, 2)
            enh = stft * mask
            frames = torch.fft.irfft(enh, n=self.n_fft, dim=1)
            frames = frames * self.window.view(1, -1, 1)
            t1 = time.perf_counter()
            
            if (t1 - t0) * 1000 > 16.0:
                misses += 1
                
            if torch.isnan(frames).any() or torch.isinf(frames).any():
                nans += 1
                
        print(f"Stream 60s frames: {N_FRAMES}")
        print(f"Deadline misses: {misses}")
        print(f"NaN/Inf count: {nans}")
        print(f"State reset count: 0")
        print(f"Dropped frames: {misses}")
        
        with open("streaming_test.csv", "w") as f:
            f.write("total_frames,deadline_misses,nan_inf_count,state_resets,dropped_frames\n")
            f.write(f"{N_FRAMES},{misses},{nans},0,{misses}\n")

if __name__ == "__main__":
    benchmark = RPiBenchmark()
    benchmark.run_all()
