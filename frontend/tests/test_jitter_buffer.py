import numpy as np
import pytest
import sys, os

repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from frontend.audio.jitter_buffer import JitterBuffer

def test_jitter_buffer_write_read():
    buf = JitterBuffer(sample_rate=16000, target_buffer_ms=48, max_buffer_ms=500)
    samples_in = np.ones(256, dtype=np.float32) * 0.5
    buf.write(samples_in)
    
    assert buf.get_level_ms() == pytest.approx(16.0, rel=1e-2)
    
    samples_out = buf.read(256)
    assert len(samples_out) == 256
    np.testing.assert_allclose(samples_out, samples_in)
    assert buf.get_level_ms() == 0.0

def test_jitter_buffer_underrun_concealment():
    buf = JitterBuffer(sample_rate=16000, target_buffer_ms=48)
    # Read from empty buffer
    samples_out = buf.read(128)
    assert len(samples_out) == 128
    np.testing.assert_allclose(samples_out, np.zeros(128, dtype=np.float32))
    assert buf.underrun_count == 128
