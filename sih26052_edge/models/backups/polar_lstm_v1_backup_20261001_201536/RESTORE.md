# Backup: StatefulPolarLSTM best.pt

This is the backup of the original production best.pt before the DeepFilterNet3/HKNT upgrade.

## To restore:
```bash
cp ~/sih26052_edge/models/backups/polar_lstm_v1_backup_*/best.pt ~/sih26052_edge/models/best.pt
# Then restart the Pi service
sudo systemctl restart anc-stream
```

## Model:
- Architecture: StatefulPolarLSTM (2-layer LSTM, hidden=256, input=514)
- Format: PyTorch .pt checkpoint
- SNR: 7.57 dB (canonical validation, 590 examples)
- SI-SDR: 3.88 dB
