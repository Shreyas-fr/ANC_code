import socket
import struct
import subprocess
import sys
import time
import os

def main():
    host = '0.0.0.0'
    port = 5005
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    
    cmd = [
        "/opt/homebrew/bin/ffplay",
        "-f", "f32le",
        "-ar", "16000",
        "-ch_layout", "mono",
        "-nodisp",
        "-autoexit",
        "-probesize", "32",
        "-sync", "ext",
        "-i", "pipe:0"
    ]
    
    print("Starting ffplay...")
    ffplay_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    
    print(f"Listening on UDP {host}:{port}...")
    
    expected_seq = None
    packets_received = 0
    packets_lost = 0
    duplicates = 0
    out_of_order = 0
    
    start_time = None
    
    f_out = open("received_test.raw", "wb")
    
    try:
        sock.settimeout(10.0)
        while True:
            try:
                data, addr = sock.recvfrom(2048)
                
                if start_time is None:
                    start_time = time.time()
                
                if len(data) < 8:
                    continue
                    
                header = data[:8]
                payload = data[8:]
                
                seq = struct.unpack('<Q', header)[0]
                
                if expected_seq is None:
                    expected_seq = seq
                    
                if seq == expected_seq:
                    expected_seq += 1
                elif seq < expected_seq:
                    out_of_order += 1
                else:
                    packets_lost += (seq - expected_seq)
                    expected_seq = seq + 1
                    
                packets_received += 1
                
                f_out.write(payload)
                ffplay_proc.stdin.write(payload)
                ffplay_proc.stdin.flush()
                
            except socket.timeout:
                if start_time is not None:
                    print("Timeout waiting for packets. Assuming stream ended.")
                    break
            except BrokenPipeError:
                print("Broken pipe. ffplay exited.")
                break
    except KeyboardInterrupt:
        print("Interrupted by user.")
    finally:
        sock.close()
        f_out.close()
        try:
            ffplay_proc.stdin.close()
            ffplay_proc.wait(timeout=2)
        except:
            ffplay_proc.kill()
            
    print("\n=== RECEIVER STATISTICS ===")
    print(f"Packets received: {packets_received}")
    print(f"Packets lost: {packets_lost}")
    print(f"Out of order / Duplicates: {out_of_order}")
    print("===========================")
    
    with open("receiver_stats.txt", "w") as f:
        f.write(f"received:{packets_received}\n")
        f.write(f"lost:{packets_lost}\n")
        f.write(f"ooo:{out_of_order}\n")

if __name__ == "__main__":
    main()
