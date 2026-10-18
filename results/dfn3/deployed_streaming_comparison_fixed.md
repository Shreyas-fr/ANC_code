# Deployed Streaming Config (500 ms Block / 300 ms Context) vs Offline Processing (Fixed Alignment)

- **Alignment Method**: Exactly compensated for `chain.delay_samples_io` (9,216 samples = 576.0 ms) by padding input with $D$ zero samples and dropping the first $D$ output samples.
- **Delay Verification**: Cross-correlation peak was asserted to be within $\le 2$ samples of nominal delay for 100% of evaluated clips.
- **Backend**: `BlockBackend` (500 ms block, 300 ms context, 40 ms guard, 10 ms crossfade, 256-sample IO frames)
- **Evaluated Subsets**: 5 dB, 10 dB, 15 dB ($n=344$)

| Input SNR | n | Offline SNR | Stream SNR | $\Delta$ SNR (Stream) | Offline SI-SDR | Stream SI-SDR | $\Delta$ SI-SDR (Stream) | Offline STOI | Stream STOI | Offline PESQ | Stream PESQ |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **+5 dB** | 137 | 6.95 dB | **7.31 dB** | +2.31 dB | 9.24 dB | **9.33 dB** | +4.68 dB | 0.875 | **0.873** | 1.687 | **1.675** |
| **+10 dB** | 121 | 8.51 dB | **9.01 dB** | -1.72 dB | 11.38 dB | **11.55 dB** | +0.88 dB | 0.913 | **0.912** | 2.021 | **2.011** |
| **+15 dB** | 86 | 10.31 dB | **10.87 dB** | -5.10 dB | 13.50 dB | **13.62 dB** | -2.15 dB | 0.942 | **0.943** | 2.309 | **2.316** |


### Gunfire-Only Streaming Performance (5, 10, 15 dB)

| Input SNR | n | Offline SNR | Stream SNR | Offline SI-SDR | Stream SI-SDR | Offline STOI | Stream STOI | Offline PESQ | Stream PESQ |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **+5 dB** | 104 | 7.14 dB | **7.55 dB** | 9.33 dB | **9.42 dB** | 0.870 | **0.868** | 1.679 | **1.659** |
| **+10 dB** | 93 | 8.61 dB | **9.21 dB** | 11.45 dB | **11.67 dB** | 0.909 | **0.910** | 1.990 | **1.982** |
| **+15 dB** | 63 | 10.30 dB | **10.86 dB** | 13.36 dB | **13.43 dB** | 0.940 | **0.939** | 2.236 | **2.227** |
