import time
import socket
import struct
import argparse
import random
import wave
import numpy as np
import threading

class SimSender:
    def __init__(self, wav_path, loss=0.0, reorder=0.0, jitter_ms=0.0, dup=0.0, 
                 stop_after=None, restart_at=None, silent_enhanced_after=None, 
                 host='127.0.0.1', port_enh=5005, port_raw=5007, port_telem=5006, malformed=0.0):
        self.wav_path = wav_path
        self.loss = loss
        self.reorder = reorder
        self.jitter_ms = jitter_ms
        self.dup = dup
        self.stop_after = stop_after
        self.restart_at = restart_at
        self.silent_enhanced_after = silent_enhanced_after
        self.malformed = malformed
        
        self.host = host
        self.port_enh = port_enh
        self.port_raw = port_raw
        self.port_telem = port_telem
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # internal counters to verify against frontend
        self.sent_count = 0
        self.loss_count = 0
        self.reorder_count = 0
        self.dup_count = 0
        self.malformed_count = 0
        
        self.running = False
        self.thread = None

    def _read_wav(self):
        # mock reading or actually read
        if not self.wav_path:
            # generate sine
            t = np.arange(16000 * 10) / 16000.0
            return (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
            
        with wave.open(self.wav_path, 'rb') as wf:
            frames = wf.readframes(wf.getnframes())
            if wf.getsampwidth() == 2:
                samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            else:
                samples = np.frombuffer(frames, dtype=np.float32)
        return samples

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def _run(self):
        samples = self._read_wav()
        seq = 5000
        start_time = time.time()
        
        chunk_size = 256
        num_chunks = len(samples) // chunk_size
        
        reorder_queue = []
        
        for i in range(num_chunks):
            if not self.running:
                break
                
            now = time.time()
            elapsed = now - start_time
            
            if self.stop_after and elapsed > self.stop_after:
                break
                
            if self.restart_at and elapsed > self.restart_at:
                seq = 0 # trigger restart
                self.restart_at = None # do it once
                
            chunk = samples[i*chunk_size : (i+1)*chunk_size]
            payload = chunk.tobytes()
            
            # create packet
            packet = struct.pack('<Q', seq) + payload
            
            # send raw always
            self.sock.sendto(packet, (self.host, self.port_raw))
            
            # send enhanced logic
            send_enhanced = True
            if self.silent_enhanced_after and elapsed > self.silent_enhanced_after:
                send_enhanced = False
                
            if send_enhanced:
                # apply network conditions
                if random.random() < self.loss:
                    self.loss_count += 1
                else:
                    pkt_to_send = packet
                    if random.random() < self.malformed:
                        pkt_to_send = b'SHORT'
                        self.malformed_count += 1
                        
                    if random.random() < self.reorder:
                        # delay packet
                        reorder_queue.append((pkt_to_send, now + 0.040)) # 40ms delay
                        self.reorder_count += 1
                    else:
                        if self.jitter_ms > 0:
                            j = random.uniform(0, self.jitter_ms) / 1000.0
                            time.sleep(j)
                        
                        self.sock.sendto(pkt_to_send, (self.host, self.port_enh))
                        self.sent_count += 1
                        
                        if random.random() < self.dup:
                            self.sock.sendto(pkt_to_send, (self.host, self.port_enh))
                            self.dup_count += 1
                            
            # flush reordered
            for rp, t in list(reorder_queue):
                if time.time() >= t:
                    self.sock.sendto(rp, (self.host, self.port_enh))
                    reorder_queue.remove((rp, t))
            
            seq += 1
            
            # cadence
            expected = start_time + (i + 1) * (chunk_size / 16000.0)
            sleep_time = expected - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav", default="")
    parser.add_argument("--loss", type=float, default=0.0)
    parser.add_argument("--reorder", type=float, default=0.0)
    parser.add_argument("--jitter-ms", type=float, default=0.0)
    parser.add_argument("--dup", type=float, default=0.0)
    parser.add_argument("--malformed", type=float, default=0.0)
    parser.add_argument("--stop-after", type=float, default=0.0)
    parser.add_argument("--restart-at", type=float, default=0.0)
    parser.add_argument("--silent-enhanced-after", type=float, default=0.0)
    args = parser.parse_args()
    
    sender = SimSender(args.wav, args.loss, args.reorder, args.jitter_ms, args.dup, 
                       args.stop_after, args.restart_at, args.silent_enhanced_after, malformed=args.malformed)
    sender.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sender.stop()
