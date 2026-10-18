import socket, struct, numpy as np, time
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
for seq in range(10):
    payload = np.ones(256, dtype=np.float32) * 0.5
    data = struct.pack('<Q', seq) + payload.tobytes()
    sock.sendto(data, ('127.0.0.1', 5010))
    time.sleep(0.01)
