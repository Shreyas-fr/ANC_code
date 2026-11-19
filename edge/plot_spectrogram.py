import numpy as np
from scipy.io import wavfile
import matplotlib.pyplot as plt
from scipy import signal
import os

def generate_spectrogram():
    fs, ref = wavfile.read(os.path.expanduser('~/anc_tests/D_ref2_block.wav'))
    fs2, inp = wavfile.read(os.path.expanduser('~/anc_tests/D_in.wav'))
    
    assert fs == fs2
    if ref.dtype == np.int16:
        ref = ref.astype(np.float32) / 32768.0
    if inp.dtype == np.int16:
        inp = inp.astype(np.float32) / 32768.0
        
    corr = np.correlate(inp, ref, mode='full')
    lag = np.argmax(corr) - (len(ref) - 1)
    
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
        
    # Plot spectrograms
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True, sharey=True)
    
    ax1.specgram(aligned_inp, Fs=fs, NFFT=256, noverlap=128, cmap='magma')
    ax1.set_title('Input Spectrogram (D_in.wav)')
    ax1.set_ylabel('Frequency [Hz]')
    
    ax2.specgram(aligned_ref, Fs=fs, NFFT=256, noverlap=128, cmap='magma')
    ax2.set_title('Output Spectrogram (D_ref2_block.wav)')
    ax2.set_ylabel('Frequency [Hz]')
    ax2.set_xlabel('Time [sec]')
    
    plt.tight_layout()
    
    # Save the plot
    output_path = os.path.expanduser('/Users/shreyasdivekar/.gemini/antigravity-ide/brain/e724a19f-207d-4b09-92ad-17a4ac0eace9/spectrogram.png')
    plt.savefig(output_path, dpi=150)
    print(f"Spectrogram saved to {output_path}")

generate_spectrogram()
