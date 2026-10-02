import threading
import collections
import numpy as np

class JitterBuffer:
    """
    Thread-safe low-latency ring/jitter buffer for real-time audio playback.
    Stores mono float32 PCM samples.
    Conceals underruns with silence (zeros).
    """
    def __init__(self, sample_rate: int = 16000, target_buffer_ms: int = 48, max_buffer_ms: int = 500):
        self.sample_rate = sample_rate
        self.target_samples = int((target_buffer_ms / 1000.0) * sample_rate)
        self.max_samples = int((max_buffer_ms / 1000.0) * sample_rate)
        
        self.lock = threading.Lock()
        self.buffer = collections.deque()
        self.underrun_count = 0
        self.overflow_count = 0
        
    def write(self, samples: np.ndarray):
        """Append float32 samples to the jitter buffer."""
        if samples is None or len(samples) == 0:
            return
            
        with self.lock:
            for s in samples:
                self.buffer.append(float(s))
            
            # Bound buffer size to max_samples (drop oldest if overflow occurs)
            while len(self.buffer) > self.max_samples:
                self.buffer.popleft()
                self.overflow_count += 1

    def read(self, num_samples: int) -> np.ndarray:
        """
        Read exact `num_samples` from the buffer.
        If underflow occurs, pad remaining samples with zeros (silence).
        """
        out = np.zeros(num_samples, dtype=np.float32)
        with self.lock:
            available = len(self.buffer)
            to_read = min(num_samples, available)
            for i in range(to_read):
                out[i] = self.buffer.popleft()
                
            if to_read < num_samples:
                self.underrun_count += (num_samples - to_read)
                
        return out

    def get_level_ms(self) -> float:
        """Return current buffer size in milliseconds."""
        with self.lock:
            return (len(self.buffer) / self.sample_rate) * 1000.0

    def clear(self):
        """Flush the buffer."""
        with self.lock:
            self.buffer.clear()
            self.underrun_count = 0
            self.overflow_count = 0
