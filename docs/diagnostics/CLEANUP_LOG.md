# Cleanup Log: SIH26052 ANC Repository

## Phase 1 - Secrets & Credentials Sanitization
- **scripts/copy_ssh_key.py**:
  - Removed literal Pi password (`[REDACTED]`).
  - Rewritten to interactively prompt using `getpass.getpass` or read non-interactive credentials via `SIH_PI_PASSWORD`.
  - Added support for target host specification via `SIH_PI_TARGET` environment variable or CLI argument.
- **Hardcoded LAN IP Sanitization**:
  - Grepped the entire tree (Python scripts, shell scripts, markdown docs, csv data).
  - Replaced hardcoded IP addresses (e.g. `<LAN-IP>`, `<LAN-IP>`, `<LAN-IP>`) with `SIH_PC_IP` / `SIH_PI_IP` environment variables or required CLI arguments with no default IPs.
  - Updated files:
    - `edge_deployment_tests/controlled_test_sender.py`
    - `edge_deployment_tests/pi_ai_network_sender.py`
    - `Documents/anc sih/controlled_test_sender.py`
    - `Documents/anc sih/dfn3_paced2.py`
    - `Documents/anc sih/run_s2.sh`
    - `Documents/anc sih/runs/final_model/dfn3_live_sender.py`
    - `Documents/anc sih/run_p1.sh`
    - `Documents/anc sih/run_s1.sh`
    - `Documents/anc sih/run_phase_A.sh`
    - `Documents/anc sih/run_phase_B.sh`
    - `Documents/anc sih/run_phase_C.sh`
    - `Documents/anc sih/run_phase_D.sh`
    - `Documents/anc sih/pi_task_a.txt`
- **.gitignore Hardening**:
  - Added rules to both root `.gitignore` and `Documents/anc sih/.gitignore`:
    - `*.key`, `*.pem`, `rpi_key*`, `id_rsa*`, `id_ed25519*`, `*.p12`, `*.pfx`
    - `.env`, `.env.*`
    - `*.hk` (heavy model weights)
