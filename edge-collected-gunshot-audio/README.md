# Edge-Collected Gunshot Audio Dataset

## Dataset Description
Field-collected and IoBT acoustic recordings containing gunshot impulses, muzzle blasts, and supersonic shockwaves for training and evaluating neural noise suppression under high-energy impulsive conditions.

## Data Storage & Acquisition
- **Raw Storage Location**: `data/raw_defence/iobt_gunfire/extracted/edge-collected-gunshot-audio/`
- **Acquisition Script**: Run `python scripts/acquire_and_audit_gunfire.py` to download and audit raw audio.
- **Verification Script**: Run `python scripts/final_gunfire_validation.py` to verify sample rates (48 kHz / 16 kHz) and waveform integrity.

*Note: Raw audio WAV files are ignored from git version control due to binary file size limits.*
