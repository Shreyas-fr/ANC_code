import numpy as np
from streaming_core import AudioChain, BlockBackend
import time

chain = AudioChain(BlockBackend(lambda x: x, block_ms=500, context_ms=300))
print("Latency ms:", chain.latency_ms())
