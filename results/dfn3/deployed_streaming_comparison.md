# Deployed Streaming Config (500 ms Block / 300 ms Context) vs Offline Processing

- **Backend**: `BlockBackend` (500 ms block, 300 ms context, 40 ms guard, 10 ms crossfade)
- **Engine**: `AudioChain` (Stateful rational FIR resamplers 16k <-> 48k)
- **Evaluated**: Subsets at 5 dB, 10 dB, 15 dB (n = 344)

| Input SNR | n | Offline SNR | Stream SNR | Offline SI-SDR | Stream SI-SDR | Offline STOI | Stream STOI | Offline PESQ | Stream PESQ |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| +5 dB | 137 | 6.95 dB | **-3.00 dB** | 9.24 dB | **-19.32 dB** | 0.875 | **0.143** | 1.687 | **1.378** |
| +10 dB | 121 | 8.51 dB | **-3.09 dB** | 11.38 dB | **-20.34 dB** | 0.913 | **0.127** | 2.021 | **1.551** |
| +15 dB | 86 | 10.31 dB | **-2.86 dB** | 13.50 dB | **-20.01 dB** | 0.942 | **0.122** | 2.309 | **1.723** |
