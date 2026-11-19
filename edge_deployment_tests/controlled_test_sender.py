import socket
import struct
import numpy as np
import time

def main():
    target_ip = "10.85.100.182"
    target_port = 5005
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    sample_rate = 16000
    freq = 1000.0
    duration = 5.0
    frames = int((sample_rate * duration) / 256)
    
    print(f"Sending 1kHz sine wave for {duration}s to {target_ip}:{target_port}")
    
    t = np.arange(256)
    phase = 0.0
    
    sent_packets = 0
    
    for seq in range(frames):
        chunk = np.sin(2 * np.pi * freq * (t + phase) / sample_rate).astype(np.float32)
        phase += 256
        
        header = struct.pack('<Q', seq)
        payload = chunk.tobytes()
        packet = header + payload
        
        sock.sendto(packet, (target_ip, target_port))
        sent_packets += 1
        time.sleep(256 / sample_rate) # Sleep 16ms
        
    print(f"Done sending controlled test signal. Sent {sent_packets} packets.")
    sock.close()

if __name__ == "__main__":
    main()
