import socket
import struct
import time
import threading
import numpy as np
import logging
from typing import Optional, Callable

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger("AudioReceiver")

class AudioReceiver(QObject):
    """
    Dedicated UDP network receiver thread for PCM audio frames.
    Receives 1032-byte UDP packets:
      - 8-byte unsigned 64-bit int header: uint64 sequence number
      - 1024-byte float32 payload: 256 mono PCM samples at 16 kHz
    """
    # Signals emitted to Qt GUI thread
    frame_received = Signal(str, np.ndarray, int, float) # (stream_name, samples, sequence, timestamp)
    status_changed = Signal(str, bool)                   # (stream_name, is_connected)

    def __init__(self, port: int = 5005, stream_name: str = "enhanced", timeout_sec: float = 1.0):
        super().__init__()
        self.port = port
        self.stream_name = stream_name
        self.timeout_sec = timeout_sec
        
        self.sock: Optional[socket.socket] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        
        # Stream telemetry metrics
        self.lock = threading.Lock()
        self.packets_received = 0
        self.packets_lost = 0
        self.duplicate_packets = 0
        self.out_of_order_packets = 0
        self.sequence_resets = 0
        self.last_sequence: Optional[int] = None
        self.last_packet_time: Optional[float] = None
        self.is_connected = False
        self.start_time: Optional[float] = None
        
        self.malformed_packets = 0
        self.recent_stats = [] # list of (time, received_count, lost_count)
        self.recent_intervals = [] # list of (time, interval_ms)

    def start(self):
        """Start UDP receiver background thread."""
        if self.running:
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.thread.start()
        logger.info(f"AudioReceiver for {self.stream_name} started on port {self.port}")

    def stop(self):
        """Stop UDP receiver thread."""
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        logger.info(f"AudioReceiver for {self.stream_name} stopped.")

    def _receive_loop(self):
        """Background socket poll loop."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(('0.0.0.0', self.port))
            self.sock.settimeout(0.1) # 100ms non-blocking check
        except Exception as e:
            logger.error(f"Failed to bind UDP socket on port {self.port}: {e}")
            self.running = False
            return

        while self.running:
            now = time.time()
            
            # Check connection timeout
            with self.lock:
                was_connected = self.is_connected
                if self.last_packet_time is not None and (now - self.last_packet_time > self.timeout_sec):
                    self.is_connected = False
                    self.last_sequence = None
                if was_connected != self.is_connected:
                    self.status_changed.emit(self.stream_name, self.is_connected)

            try:
                data, _ = self.sock.recvfrom(2048)
                packet_time = time.time()
                
                # Malformed check: must have at least 8-byte header + some payload
                if len(data) < 8 or len(data) > 2048:
                    with self.lock:
                        self.malformed_packets += 1
                    logger.warning(f"Discarded short packet ({len(data)} bytes)")
                    continue
                    
                header = data[:8]
                payload = data[8:]
                
                seq = struct.unpack('<Q', header)[0]
                
                # Validate payload size (expected 256 float32 = 1024 bytes)
                if len(payload) != 1024:
                    # Handle partial/unexpected size without crashing
                    samples = np.frombuffer(payload, dtype=np.float32).copy()
                else:
                    samples = np.frombuffer(payload, dtype=np.float32).copy()

                with self.lock:
                    if self.start_time is None:
                        self.start_time = packet_time
                    self.last_packet_time = packet_time
                    
                    if not self.is_connected:
                        self.is_connected = True
                        self.status_changed.emit(self.stream_name, True)

                    # Sequence Tracking
                    added_received = 0
                    added_lost = 0
                    if self.last_sequence is None:
                        self.last_sequence = seq
                        self.packets_received += 1
                        added_received = 1
                    elif seq == self.last_sequence + 1:
                        self.packets_received += 1
                        added_received = 1
                        self.last_sequence = seq
                    elif seq == self.last_sequence:
                        self.duplicate_packets += 1
                    elif seq < self.last_sequence:
                        if self.last_sequence - seq > 1000:
                            self.sequence_resets += 1
                            self.last_sequence = seq
                            self.packets_received += 1
                            added_received = 1
                        else:
                            self.out_of_order_packets += 1
                    else: # seq > last_sequence + 1 (skipped packets)
                        lost = seq - (self.last_sequence + 1)
                        self.packets_lost += lost
                        self.packets_received += 1
                        added_received = 1
                        added_lost = lost
                        self.last_sequence = seq
                    
                    self.recent_stats.append((packet_time, added_received, added_lost))
                    
                    if hasattr(self, '_last_pkt_time_for_jitter') and self._last_pkt_time_for_jitter is not None:
                        interval = (packet_time - self._last_pkt_time_for_jitter) * 1000.0
                        self.recent_intervals.append((packet_time, interval))
                    self._last_pkt_time_for_jitter = packet_time
                    
                    # prune old stats (> 5 seconds)
                    cutoff = packet_time - 5.0
                    while self.recent_stats and self.recent_stats[0][0] < cutoff:
                        self.recent_stats.pop(0)
                    while self.recent_intervals and self.recent_intervals[0][0] < cutoff:
                        self.recent_intervals.pop(0)
                # Emit to GUI / buffer
                self.frame_received.emit(self.stream_name, samples, seq, packet_time)

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Error receiving UDP packet on port {self.port}: {e}")

    def get_stats(self) -> dict:
        """Return snapshot of network statistics."""
        with self.lock:
            total_expected = self.packets_received + self.packets_lost
            loss_pct = (self.packets_lost / total_expected * 100.0) if total_expected > 0 else 0.0
            duration = (time.time() - self.start_time) if self.start_time else 0.0
            
            # calculate 5s metrics
            recent_recv = sum(x[1] for x in self.recent_stats)
            recent_lost = sum(x[2] for x in self.recent_stats)
            recent_total = recent_recv + recent_lost
            recent_loss_pct = (recent_lost / recent_total * 100.0) if recent_total > 0 else 0.0
            
            if self.recent_intervals:
                intervals = [x[1] for x in self.recent_intervals]
                jitter_p95 = np.percentile(intervals, 95)
            else:
                jitter_p95 = 0.0
            
            return {
                'received': self.packets_received,
                'lost': self.packets_lost,
                'duplicates': self.duplicate_packets,
                'out_of_order': self.out_of_order_packets,
                'malformed': self.malformed_packets,
                'sequence_resets': self.sequence_resets,
                'loss_pct': loss_pct,
                'recent_loss_pct': recent_loss_pct,
                'jitter_p95_ms': jitter_p95,
                'last_seq': self.last_sequence,
                'connected': self.is_connected,
                'duration_sec': duration
            }
