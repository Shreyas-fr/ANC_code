import sys
import os
import time
import subprocess
import numpy as np
import wave
import signal
import re

sys.path.append(os.path.expanduser("~/sih26052_edge"))
from app.anc_stream import ANCStream

stop_processing = False
def signal_handler(sig, frame):
    global stop_processing
    stop_processing = True
    print("\nCtrl+C detected, stopping stream...")
    
signal.signal(signal.SIGINT, signal_handler)

def get_vs102_source():
    try:
        out = subprocess.check_output(["wpctl", "status"], text=True)
        m = re.search(r'(\d+)\.\s+bluez_input', out)
        if m:
            return m.group(1)
    except Exception as e:
        print(f"Failed to find VS102 source: {e}")
    return None

def main():
    target_id = get_vs102_source()
    if not target_id:
        print("A. VS102 source disappeared")
        sys.exit(1)
        
    print(f"Found VS102 source ID: {target_id}")
    
    config_path = os.path.expanduser("~/sih26052_edge/config/config.json")
    stream_processor = ANCStream(config_path)
    
    audio_dir = os.path.expanduser("~/sih26052_edge/audio")
    os.makedirs(audio_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    in_wav_path = os.path.join(audio_dir, f"vs102_live_input_{timestamp}.wav")
    out_wav_path = os.path.join(audio_dir, f"vs102_ai_output_{timestamp}.wav")
    
    in_wav = wave.open(in_wav_path, 'wb')
    in_wav.setnchannels(1)
    in_wav.setsampwidth(2)
    in_wav.setframerate(16000)
    
    out_wav = wave.open(out_wav_path, 'wb')
    out_wav.setnchannels(1)
    out_wav.setsampwidth(2)
    out_wav.setframerate(16000)
    
    cmd = [
        "pw-record",
        "-a",
        "--target", target_id,
        "--rate", "16000",
        "--channels", "1",
        "--format", "f32",
        "-"
    ]
    
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    frames_processed = 0
    misses = 0
    times = []
    
    print(f"Starting recording on target {target_id}...")
    
    try:
        while not stop_processing:
            raw_bytes = proc.stdout.read(1024)
            if not raw_bytes:
                break
            if len(raw_bytes) < 1024:
                continue
                
            chunk = np.frombuffer(raw_bytes, dtype=np.float32).copy()
            
            in_pcm = (np.clip(chunk, -1.0, 1.0) * 32767.0).astype(np.int16)
            in_wav.writeframes(in_pcm.tobytes())
            
            start_t = time.perf_counter()
            out_chunk = stream_processor.process_frame(chunk)
            elapsed_ms = (time.perf_counter() - start_t) * 1000
            
            times.append(elapsed_ms)
            if elapsed_ms > 16.0:
                misses += 1
                
            out_pcm = (np.clip(out_chunk, -1.0, 1.0) * 32767.0).astype(np.int16)
            out_wav.writeframes(out_pcm.tobytes())
            
            frames_processed += 1
            if frames_processed >= 1250: # 20 seconds
                break
                
    except Exception as e:
        print(f"Exception during processing: {e}")
    finally:
        proc.terminate()
        in_wav.close()
        out_wav.close()
        stream_processor.monitor.flush_log(force=True)
        
    if not times:
        print("No frames processed!")
        sys.exit(1)
        
    times = np.array(times)
    median = np.median(times)
    p95 = np.percentile(times, 95)
    p99 = np.percentile(times, 99)
    max_t = np.max(times)
    
    print("\n=== REAL-TIME MEASUREMENT ===")
    print(f"Frames processed: {frames_processed}")
    print(f"Median: {median:.2f} ms")
    print(f"p95: {p95:.2f} ms")
    print(f"p99: {p99:.2f} ms")
    print(f"Max: {max_t:.2f} ms")
    print(f">16ms frames (Deadline misses): {misses}")
    
    try:
        temp_str = subprocess.check_output(["cat", "/sys/class/thermal/thermal_zone0/temp"], text=True)
        temp_c = int(temp_str.strip()) / 1000.0
        print(f"Temperature: {temp_c:.1f} °C")
    except:
        pass
        
    print(f"\nFiles saved:\nInput: {in_wav_path}\nOutput: {out_wav_path}")
    with open("/tmp/last_recordings.txt", "w") as f:
        f.write(f"{in_wav_path}\n{out_wav_path}\n")

if __name__ == "__main__":
    main()
