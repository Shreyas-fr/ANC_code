import time
import argparse
import numpy as np
import onnxruntime as ort
import sounddevice as sd
import json
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class LiveInfer:
    def __init__(self, model_path, input_device, output_device, use_nlms=False, use_dsp_limiter=False):
        self.use_dsp_limiter = use_dsp_limiter
        self.sess = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
        self.input_name = self.sess.get_inputs()[0].name
        
        import scipy.signal
        self.n_fft = 512
        self.hop = 256
        self.window = scipy.signal.windows.hann(self.n_fft, sym=False).astype(np.float32)
        self.ola_window = self.window[:self.hop]**2 + self.window[self.hop:]**2
        
        self.use_nlms = use_nlms
        if self.use_nlms:
            from deploy.nlms_postfilter import NLMSPostFilter
            self.nlms = NLMSPostFilter(filter_len=128, mu=0.05)
            
        self.in_buf = np.zeros(self.n_fft, dtype=np.float32)
        self.out_buf = np.zeros(self.n_fft, dtype=np.float32)
        
        self.input_device = input_device
        self.output_device = output_device
        
        self.frames_processed = 0
        self.xruns = 0
        self.start_time = time.time()
        self.total_infer_time = 0.0

    def process_block(self, indata, outdata, frames, time_info, status):
        if status:
            self.xruns += 1
            
        chunk = indata[:, 0]
        
        if self.use_dsp_limiter:
            # Hybrid DSP Pre-Limiter: instantly hard-clip explosive peaks before the STFT and CRN
            chunk = np.clip(chunk, -0.4, 0.4)
            
        self.in_buf[:-self.hop] = self.in_buf[self.hop:]
        self.in_buf[-self.hop:] = chunk
        
        framed = self.in_buf * self.window
        stft = np.fft.rfft(framed)
        mag = np.abs(stft).astype(np.float32)
        
        t0 = time.perf_counter()
        mag_input = np.expand_dims(np.expand_dims(mag, axis=0), axis=2)
        mask_real, mask_imag = self.sess.run(None, {self.input_name: mag_input})
        t1 = time.perf_counter()
        self.total_infer_time += (t1 - t0)
        
        mask_complex = mask_real[0, :, 0] + 1j * mask_imag[0, :, 0]
        enhanced_stft = stft * mask_complex
        enhanced_frame = np.fft.irfft(enhanced_stft) * self.window
        
        if self.use_nlms:
            est_noise = framed - enhanced_frame
            enhanced_frame = self.nlms.process(enhanced_frame, est_noise)
            
        self.out_buf += enhanced_frame
        outdata[:, 0] = self.out_buf[:self.hop] / (self.ola_window + 1e-8)
        
        self.out_buf[:-self.hop] = self.out_buf[self.hop:]
        self.out_buf[-self.hop:] = 0.0
        
        self.frames_processed += 1
        
        if self.frames_processed % 312 == 0: 
            rtf = self.total_infer_time / 5.0
            print(f"[Stats] Runtime: {time.time()-self.start_time:.1f}s | RTF: {rtf:.4f} | Xruns/Drops: {self.xruns}")
            self.total_infer_time = 0.0

    def loopback_latency_test(self):
        print("Loopback test requires physical loopback cable from Output to Input.")
        print("Emitting impulse...")
        
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--input-device", type=int, default=None)
    parser.add_argument("--output-device", type=int, default=None)
    parser.add_argument("--nlms", action="store_true")
    parser.add_argument("--dsp-limiter", action="store_true", help="Enable pre-NN DSP transient hard clipper")
    parser.add_argument("--loopback-latency-test", action="store_true")
    args = parser.parse_args()
    
    if args.list_devices:
        print(sd.query_devices())
        return
        
    if args.loopback_latency_test:
        infer = LiveInfer("checkpoints/dtln/model.onnx", None, None, False)
        infer.loopback_latency_test()
        return
        
    infer = LiveInfer("checkpoints/dtln/model.onnx", args.input_device, args.output_device, args.nlms, args.dsp_limiter)
    
    print("Starting audio stream... (Press Ctrl+C to stop)")
    try:
        with sd.Stream(device=(args.input_device, args.output_device),
                       samplerate=16000, blocksize=256,
                       dtype='float32', channels=1, callback=infer.process_block):
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print("Stream stopped.")

if __name__ == "__main__":
    main()
