import os
import sys
import numpy as np

try:
    import numpy.exceptions
    if not hasattr(numpy.exceptions, 'RankWarning'):
        numpy.exceptions.RankWarning = type("RankWarning", (Warning,), {})
except:
    pass
np.long = int
np.ulong = int

sys.path.insert(0, "/Users/shreyasdivekar/Downloads/anc_fix")
from streaming_core import AudioChain, BlockBackend

def make_identity_enhance_fn():
    def enhance(chunk):
        return chunk
    return enhance

def test_delay(signal_type="click"):
    fn = make_identity_enhance_fn()
    backend = BlockBackend(fn, block_ms=500, context_ms=300)
    chain = AudioChain(backend)
    
    lat = chain.latency_ms()
    print("latency_ms():", lat)
    
    FRAME = 256
    SR = 16000
    
    # 1s silence, 1 click or burst, 2s silence
    n_pre = 1 * SR
    n_burst = 256
    n_post = 2 * SR
    
    in_audio = np.zeros(n_pre + n_burst + n_post, dtype=np.float32)
    if signal_type == "click":
        in_audio[n_pre] = 0.5
    else:
        # 440 Hz burst
        t = np.arange(n_burst) / SR
        in_audio[n_pre:n_pre+n_burst] = 0.5 * np.sin(2 * np.pi * 440 * t)
        
    out_audio = []
    
    returns_256 = True
    for i in range(0, len(in_audio), FRAME):
        chunk = in_audio[i:i+FRAME]
        out_chunk = chain.process(chunk)
        if len(out_chunk) != FRAME:
            returns_256 = False
        out_audio.append(out_chunk)
        
    out_audio = np.concatenate(out_audio)
    
    if signal_type == "click":
        click_in = n_pre
        peak_out = np.argmax(np.abs(out_audio))
        delay = peak_out - click_in
    else:
        # Cross correlate for burst
        c = np.correlate(out_audio, in_audio, mode="full")
        lags = np.arange(-len(in_audio) + 1, len(out_audio))
        delay = lags[np.argmax(np.abs(c))]
        click_in = n_pre
        peak_out = click_in + delay
        
    print(f"[{signal_type}] Returns 256 samples per call? {returns_256}")
    print(f"[{signal_type}] Input index: {click_in}, Peak output index: {peak_out}")
    print(f"[{signal_type}] Delay: {delay} samples ({delay / SR * 1000:.2f} ms)")
    if delay > 0:
        print(f"[{signal_type}] Is output of call k already delayed? YES")
    else:
        print(f"[{signal_type}] Is output of call k already delayed? NO")

if __name__ == "__main__":
    import numpy as np
    try:
        import numpy.exceptions
        if not hasattr(numpy.exceptions, 'RankWarning'):
            numpy.exceptions.RankWarning = type("RankWarning", (Warning,), {})
    except:
        pass
    np.long = int
    np.ulong = int

    print("--- 11a: Structural Delay ---")
    test_delay("click")
    print()
    test_delay("burst")
