import numpy as np
from dfn3_enhance import make_dfn3_enhance_fn
from streaming_core import AudioChain, BlockBackend
import os

def measure():
    model_path = os.path.expanduser("~/sih26052_edge/models/dfn3_final.hk")
    enhance_fn = make_dfn3_enhance_fn(model_path, threads=1)
    chain = AudioChain(BlockBackend(enhance_fn, block_ms=500, context_ms=300, guard_ms=40, xfade_ms=10))
    
    rng = np.random.default_rng(1)
    x = rng.standard_normal(16000 * 5).astype(np.float32)
    y = np.concatenate([chain.process(x[i:i+256]) for i in range(0, len(x), 256)])
    
    corr = np.correlate(y, x, mode='full')
    lag = np.argmax(corr) - (len(x) - 1)
    print("Real DFN3 Lag in samples:", lag)
    print("Real DFN3 Lag in ms:", lag / 16.0)

measure()
