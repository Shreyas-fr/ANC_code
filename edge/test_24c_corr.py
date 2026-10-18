import numpy as np
from scipy import signal
from streaming_core import AudioChain, BlockBackend

def measure():
    chain = AudioChain(BlockBackend(lambda x: x, block_ms=500, context_ms=300, guard_ms=40, xfade_ms=10))
    rng = np.random.default_rng(1)
    x = rng.standard_normal(16000 * 5).astype(np.float32)
    y = np.concatenate([chain.process(x[i:i+256]) for i in range(0, len(x), 256)])
    
    corr = np.correlate(y, x, mode='full')
    lag = np.argmax(corr) - (len(x) - 1)
    print("Lag in samples:", lag)
    print("Lag in ms:", lag / 16.0)

measure()
