import sys
import os
import time
import subprocess
import numpy as np
import wave
import signal
import re
import socket
import struct

sys.path.append(os.path.expanduser("~/sih26052_edge"))
from app.anc_stream import ANCStream
import json

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
    
    # audio_dir = os.path.expanduser("~/sih26052_edge/audio")
    # os.makedirs(audio_dir, exist_ok=True)
    # timestamp = time.strftime("%Y%m%d_%H%M%S")
    # in_wav_path = os.path.join(audio_dir, "shreyaswork_input.wav")
    # out_wav_path = os.path.join(audio_dir, "shreyaswork_output.wav")
    
    # in_wav = wave.open(in_wav_path, 'wb')
    # in_wav.setnchannels(1)
    # in_wav.setsampwidth(2)
    # in_wav.setframerate(16000)
    
    # out_wav = wave.open(out_wav_path, 'wb')
    # out_wav.setnchannels(1)
    # out_wav.setsampwidth(2)
    # out_wav.setframerate(16000)
    
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
    
    target_ip = "10.190.58.182"  # Using correct Mac PC IP
    target_port = 5005
    target_port_input = 5007
    target_port_telemetry = 5006
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_input = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_telemetry = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    frames_processed = 0
    misses = 0
    times = []
    
    print(f"Starting recording and live streaming to {target_ip}:{target_port}...")
    
    seq = 0
    try:
        while not stop_processing:
            raw_bytes = proc.stdout.read(1024)
            if not raw_bytes:
                break
            if len(raw_bytes) < 1024:
                continue
                
            chunk = np.frombuffer(raw_bytes, dtype=np.float32).copy()
            
            # in_pcm = (np.clip(chunk, -1.0, 1.0) * 32767.0).astype(np.int16)
            # in_wav.writeframes(in_pcm.tobytes())
            
            start_t = time.perf_counter()
            out_chunk = stream_processor.process_frame(chunk)
            elapsed_ms = (time.perf_counter() - start_t) * 1000
            
            times.append(elapsed_ms)
            if elapsed_ms > 16.0:
                misses += 1
                
            # out_pcm = (np.clip(out_chunk, -1.0, 1.0) * 32767.0).astype(np.int16)
            # out_wav.writeframes(out_pcm.tobytes())
                
            header = struct.pack('<Q', seq)
            
            # Send Enhanced stream (5005)
            payload_enhanced = out_chunk.astype(np.float32).tobytes()
            packet_enhanced = header + payload_enhanced
            sock.sendto(packet_enhanced, (target_ip, target_port))
            
            # Send Raw Input stream (5007) using identical sequence number
            payload_input = chunk.astype(np.float32).tobytes()
            packet_input = header + payload_input
            sock_input.sendto(packet_input, (target_ip, target_port_input))
            
            # Send Telemetry (5006) every 50 frames
            if frames_processed % 50 == 0:
                try:
                    temp_str = subprocess.check_output(["cat", "/sys/class/thermal/thermal_zone0/temp"], text=True)
                    temp_c = int(temp_str.strip()) / 1000.0
                except:
                    temp_c = 0.0
                    
                recent_times = times[-100:] if len(times) > 0 else [0]
                
                resets = 0
                nans = 0
                if hasattr(stream_processor, 'monitor'):
                    resets = stream_processor.monitor.state_resets
                    nans = stream_processor.monitor.nan_inf_count
                    
                telemetry_data = {
                    "model": "StatefulPolarLSTM",
                    "parameters": 1448962,
                    "frame": frames_processed,
                    "processing_ms": round(elapsed_ms, 2),
                    "median_ms": round(np.median(recent_times), 2),
                    "p95_ms": round(np.percentile(recent_times, 95), 2),
                    "max_ms": round(np.max(recent_times), 2),
                    "temperature_c": temp_c,
                    "state_resets": resets,
                    "nan_inf_events": nans,
                    "deadline_misses": misses
                }
                sock_telemetry.sendto(json.dumps(telemetry_data).encode('utf-8'), (target_ip, target_port_telemetry))
            
            frames_processed += 1
            seq += 1
            if frames_processed >= 18750: # 60 seconds (18750 * 16ms = 60s)
                break
                
    except Exception as e:
        print(f"Exception during processing: {e}")
    finally:
        proc.terminate()
        sock.close()
        sock_input.close()
        sock_telemetry.close()
        # in_wav.close()
        # out_wav.close()
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
    print(f"Packets sent: {seq}")
    
    try:
        temp_str = subprocess.check_output(["cat", "/sys/class/thermal/thermal_zone0/temp"], text=True)
        temp_c = int(temp_str.strip()) / 1000.0
        print(f"Temperature: {temp_c:.1f} °C")
    except:
        pass
        
    print(f"\nFiles saved:\nInput: NONE (Recording disabled)\nOutput: NONE (Recording disabled)")
    with open("/tmp/last_recordings.txt", "w") as f:
        f.write(f"DISABLED\nDISABLED\n")

if __name__ == "__main__":
    main()
