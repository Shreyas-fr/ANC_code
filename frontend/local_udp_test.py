import socket
import struct
import time
import json
import numpy as np

IP = "127.0.0.1"

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def send_audio(port, seq):
    header = struct.pack('<Q', seq)
    # Generate 256 float32 samples (1024 bytes)
    samples = np.sin(np.linspace(0, 2*np.pi, 256)).astype(np.float32).tobytes()
    sock.sendto(header + samples, (IP, port))

def send_telemetry(port, data):
    payload = json.dumps(data).encode('utf-8')
    sock.sendto(payload, (IP, port))

print("Starting Local UDP Test...")
# Send telemetry
telemetry_data = {
    "model": "DeepFilterNet3",
    "backend": "Rust/Tract",
    "model_sha": "522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe",
    "model_active": True,
    "bluetooth_connected": True,
    "latency_ms": 7.5,
    "temperature_c": 51.5
}

for i in range(100):
    send_audio(5005, i)      # Enhanced
    send_audio(5007, i*2)    # Input (different sequence numbers to prove independence)
    if i % 10 == 0:
        send_telemetry(5006, telemetry_data)
    time.sleep(0.016) # 16ms

print("Test streams sent successfully.")
