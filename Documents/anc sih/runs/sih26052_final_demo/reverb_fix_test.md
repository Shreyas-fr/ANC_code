# TEMPORARY STATE-DECAY EXPERIMENT REPORT

## CURRENT STATUS:
**alpha=1.00**

## BEST CANDIDATE:
**NONE (Inconclusive/No Effect)**

## REASON:
The experiment definitively proved that the LSTM's persistent hidden state (`h`) and cell state (`c`) are **NOT** the cause of the reverb artifact. 

During the diagnostic test, applying state decay (`alpha`) from `1.00` down to `0.00` resulted in identical output waveforms up to floating-point quantization limits (only 278 samples out of 160,000 differed by a 1-bit quantization error between `alpha=1.00` and `alpha=0.00`). 

**Correction on Previous Forensic Findings:**
The previous forensic script (`run_forensic.py`) that originally identified LSTM memory bleed as the cause was flawed. The `stream_processor.reset_state()` function not only reset `h` and `c`, but also zeroed out the PipeWire `in_buffer` and `out_buffer`. Zeroing the `out_buffer` every frame structurally broke the 512/256 Overlap-Add (OLA) STFT reconstruction, effectively truncating the audio tail mathematically rather than algorithmically.

When properly isolated in this experiment (modifying *only* `h_in` and `c_in` passed to the LSTM), the state decay had **zero impact** on the metrics. The model acts almost entirely as a memoryless feed-forward network with respect to this artifact. The reverb/smearing must be stemming directly from the complex polar mask itself (likely the phase predictions), not the recurrent state.

### METRICS TABLE:

| alpha | 16ms peak | tail energy | RMS | speech corr | SI-SDR | SNR | STOI |
|---|---|---|---|---|---|---|---|
| 1.00 | 26.54 | 0.327400 | 0.010827 | 0.1492 | -17.70 | -1.12 | N/A |
| 0.95 | 26.54 | 0.327401 | 0.010827 | 0.1492 | -17.70 | -1.12 | N/A |
| 0.90 | 26.54 | 0.327401 | 0.010827 | 0.1492 | -17.70 | -1.12 | N/A |
| 0.85 | 26.54 | 0.327401 | 0.010827 | 0.1492 | -17.70 | -1.12 | N/A |
| 0.80 | 26.54 | 0.327401 | 0.010827 | 0.1492 | -17.70 | -1.12 | N/A |
| 0.70 | 26.54 | 0.327401 | 0.010827 | 0.1492 | -17.70 | -1.12 | N/A |
| 0.50 | 26.54 | 0.327401 | 0.010827 | 0.1492 | -17.70 | -1.12 | N/A |
| 0.00 | 26.54 | 0.327400 | 0.010827 | 0.1492 | -17.70 | -1.12 | N/A |

*(Note: STOI was skipped because this is real unaligned data).*

## INTEGRITY CHECK
- **CHECKPOINT MODIFIED:** NO
- **PRODUCTION SERVICE MODIFIED:** NO
