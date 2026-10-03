import socket
import json
import time
import threading
import logging
from typing import Optional

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger("TelemetryReceiver")

class TelemetryReceiver(QObject):
    """
    Dedicated UDP network receiver for JSON telemetry packets (Port 5006).
    """
    telemetry_received = Signal(dict)
    telemetry_status = Signal(bool)

    def __init__(self, port: int = 5006, timeout_sec: float = 2.0):
        super().__init__()
        self.port = port
        self.timeout_sec = timeout_sec
        self.sock: Optional[socket.socket] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_telemetry_time: Optional[float] = None
        self.is_connected = False
        self.latest_data: Optional[dict] = None
        self.lock = threading.Lock()

    def start(self):
        """Start UDP receiver background thread."""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.thread.start()
        logger.info(f"TelemetryReceiver started on port {self.port}")

    def stop(self):
        """Stop receiver thread."""
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        logger.info("TelemetryReceiver stopped.")

    def _receive_loop(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(('0.0.0.0', self.port))
            self.sock.settimeout(0.2)
        except Exception as e:
            logger.error(f"Failed to bind Telemetry UDP socket on port {self.port}: {e}")
            self.running = False
            return

        while self.running:
            now = time.time()
            with self.lock:
                was_conn = self.is_connected
                if self.last_telemetry_time is not None and (now - self.last_telemetry_time > self.timeout_sec):
                    self.is_connected = False
                if was_conn != self.is_connected:
                    self.telemetry_status.emit(self.is_connected)

            try:
                data, _ = self.sock.recvfrom(4096)
                packet_time = time.time()
                
                try:
                    text = data.decode('utf-8').strip()
                    payload = json.loads(text)
                    
                    with self.lock:
                        self.latest_data = payload
                        self.last_telemetry_time = packet_time
                        if not self.is_connected:
                            self.is_connected = True
                            self.telemetry_status.emit(True)
                            
                    self.telemetry_received.emit(payload)
                except Exception as parse_err:
                    logger.warning(f"Malformed JSON telemetry packet: {parse_err}")

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Telemetry receive error: {e}")
