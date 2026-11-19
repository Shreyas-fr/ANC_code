import os
import sys
import soundfile as sf
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
from dfn3_enhance import make_dfn3_enhance_fn
from streaming_core import AudioChain, BlockBackend

def run_9a():
    print("--- 9a ---")
    model_path = "/Users/shreyasdivekar/Documents/anc sih/runs/final_model/model.hk"
    print(f"Loading weights from {model_path}")
    din, sr = sf.read("/Users/shreyasdivekar/anc_tests/D_in.wav")
    
    fn = make_dfn3_enhance_fn(model_path, threads=1)
    # Re-run whole
    import torch
    from df.enhance import init_df, enhance, maybe_download_model
    from libdf import DF
    
    # Just use fn() directly for whole file? No, fn() takes 48kHz audio.
    # D_in is 16kHz. 
    # To use the EXACT Pi path, we should use AudioChain (which has resamplers).
    backend = BlockBackend(fn, block_ms=500, context_ms=300)
    chain = AudioChain(backend)
    
    print("Generating D_ref2_block.wav using Pi's AudioChain and BlockBackend")
    chunk_size = 256
    out_chunks = []
    for i in range(0, len(din), chunk_size):
        chunk = din[i:i+chunk_size]
        if len(chunk) < chunk_size:
            chunk = np.pad(chunk, (0, chunk_size - len(chunk)))
        y = chain.process(chunk)
        if len(y) > 0:
            out_chunks.append(y)
    
    out_block = np.concatenate(out_chunks)[:len(din)]
    sf.write("/Users/shreyasdivekar/anc_tests/D_ref2_block.wav", out_block, sr)
    
    # D_ref2_whole: we use FakeDFN3 or what?
    # The Pi chain doesn't run "whole file". But if we want to run "whole file" using exactly the Pi's processing path,
    # we upsample to 48kHz, run fn, and downsample.
    from streaming_core import StatefulResampler
    up = StatefulResampler(3, 1, 16000)
    down = StatefulResampler(1, 3, 48000)
    
    d_up = up.process(din)
    # fn is just enhance_fn(window48).
    # Since it's offline enhance, we can pass the whole 48kHz signal to fn.
    d_up_enhanced = fn(d_up)
    d_down_enhanced = down.process(d_up_enhanced)
    
    sf.write("/Users/shreyasdivekar/anc_tests/D_ref2_whole.wav", d_down_enhanced, sr)

if __name__ == "__main__":
    run_9a()
