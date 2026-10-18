import argparse
import socket
import struct
import time
import numpy as np
import soundfile as sf
import threading

def main():
    parser = argparse.ArgumentParser(description="Record audio from UDP stream.")
    parser.add_argument("--port", type=int, default=5007, help="UDP port to listen on")
    parser.add_argument("--out", type=str, required=True, help="Output WAV file path")
    parser.add_argument("--duration", type=float, default=65.0, help="Duration to record in seconds")
    parser.add_argument("--sample-rate", type=int, default=16000, help="Sample rate")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.port))
    sock.settimeout(1.0)
    
    print(f"Listening on port {args.port} for {args.duration} seconds...")
    
    start_time = None
    frames = []
    
    expected_seq = None
    total_received = 0
    total_gaps = 0
    longest_gap = 0
    
    deadline = time.time() + args.duration
    first_packet = True
    
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(65536)
            
            if len(data) < 8:
                continue
                
            seq = struct.unpack('<Q', data[:8])[0]
            payload = np.frombuffer(data[8:], dtype=np.float32)
            
            if first_packet:
                expected_seq = seq
                start_time = time.time()
                deadline = start_time + args.duration
                first_packet = False
                print(f"Started receiving from {addr}. Recording for {args.duration}s...")
                
            if seq != expected_seq:
                gap = seq - expected_seq
                if gap > 0:
                    total_gaps += gap
                    if gap > longest_gap:
                        longest_gap = gap
            
            frames.append(payload)
            total_received += 1
            expected_seq = seq + 1
            
        except socket.timeout:
            pass
        except Exception as e:
            print(f"Error: {e}")
            break
            
    sock.close()
    
    if not frames:
        print("No packets received.")
        return
        
    audio_data = np.concatenate(frames)
    sf.write(args.out, audio_data, args.sample_rate)
    
    packets_sent_inferred = total_received + total_gaps
    
    print(f"\n=== RECORDER STATS ===")
    print(f"WAV Path: {args.out}")
    print(f"Sample Rate: {args.sample_rate}")
    print(f"Channels: 1")
    print(f"Duration: {len(audio_data) / args.sample_rate:.2f}s")
    print(f"Packets received: {total_received}")
    print(f"Packets sent (inferred): {packets_sent_inferred}")
    print(f"Gaps (lost packets): {total_gaps}")
    print(f"Longest gap: {longest_gap}")
    
    if total_received > 0:
        rms = np.sqrt(np.mean(audio_data**2))
        peak = np.max(np.abs(audio_data))
        print(f"RMS: {rms:.5f}")
        print(f"Peak: {peak:.5f}")

if __name__ == "__main__":
    main()
