import numpy as np
from scipy.io import wavfile
import os

def measure_corr():
    fs, ref = wavfile.read(os.path.expanduser('~/anc_tests/D_ref2_block.wav'))
    fs2, inp = wavfile.read(os.path.expanduser('~/anc_tests/D_in.wav'))
    
    assert fs == fs2
    # Ensure they are float32
    if ref.dtype == np.int16:
        ref = ref.astype(np.float32) / 32768.0
    if inp.dtype == np.int16:
        inp = inp.astype(np.float32) / 32768.0
        
    corr = np.correlate(inp, ref, mode='full')
    lag = np.argmax(corr) - (len(ref) - 1)
    peak = corr[np.argmax(corr)]
    
    print("Lag in samples:", lag)
    print("Peak correlation:", peak)
    
    # Align
    if lag > 0:
        aligned_ref = ref[:-lag]
        aligned_inp = inp[lag:len(ref)]
    elif lag < 0:
        aligned_ref = ref[-lag:len(inp)]
        aligned_inp = inp[:len(ref)+lag]
    else:
        aligned_ref = ref[:len(inp)]
        aligned_inp = inp[:len(ref)]
        
    residual = np.abs(aligned_inp - aligned_ref)
    print("Median of residual:", np.median(residual))
    print("P90 of residual:", np.percentile(residual, 90))

measure_corr()
