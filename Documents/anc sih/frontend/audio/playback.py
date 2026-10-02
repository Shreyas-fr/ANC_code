import sounddevice as sd
import numpy as np
import logging
from typing import Optional, List, Tuple

from frontend.audio.jitter_buffer import JitterBuffer

logger = logging.getLogger("AudioPlayback")

class AudioPlayback:
    """
    Real-time low-latency audio output player using sounddevice OutputStream.
    Reads directly from JitterBuffer in a high-priority sound card callback.
    Memory-only: NEVER records or writes audio files to disk.
    """
    def __init__(self, jitter_buffer: JitterBuffer, sample_rate: int = 16000, device: Optional[int] = None):
        self.jitter_buffer = jitter_buffer
        self.sample_rate = sample_rate
        self.device = device
        self.stream: Optional[sd.OutputStream] = None
        self.is_playing = False
        self.is_muted = False

    @staticmethod
    def get_output_devices() -> List[Tuple[int, str]]:
        """List available soundcard output devices."""
        devices = []
        try:
            devs = sd.query_devices()
            for idx, d in enumerate(devs):
                if d.get('max_output_channels', 0) > 0:
                    devices.append((idx, f"{idx}: {d['name']}"))
        except Exception as e:
            logger.error(f"Error querying audio devices: {e}")
        return devices

    def _audio_callback(self, outdata: np.ndarray, frames: int, time_info, status):
        """High-priority audio callback executed by sound card driver."""
        if status:
            logger.warning(f"Soundcard status warning: {status}")
            
        if self.is_muted or not self.is_playing:
            outdata.fill(0.0)
            return

        samples = self.jitter_buffer.read(frames)
        outdata[:, 0] = samples

    def start(self, device: Optional[int] = None):
        """Start live audio output stream."""
        if self.is_playing:
            return
            
        target_device = device if device is not None else self.device
        try:
            self.stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype='float32',
                blocksize=256, # 16ms blocks matching Pi frame size
                device=target_device,
                callback=self._audio_callback
            )
            self.stream.start()
            self.is_playing = True
            logger.info(f"Audio playback started on device {target_device}")
        except Exception as e:
            logger.error(f"Failed to start sounddevice OutputStream: {e}")
            self.is_playing = False

    def stop(self):
        """Stop audio output stream."""
        if not self.is_playing:
            return
            
        self.is_playing = False
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as e:
                logger.error(f"Error closing audio stream: {e}")
            finally:
                self.stream = None
        logger.info("Audio playback stopped.")

    def set_muted(self, muted: bool):
        """Mute or unmute audio output."""
        self.is_muted = muted
