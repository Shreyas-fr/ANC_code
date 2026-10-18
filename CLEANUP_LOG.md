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

## Phase 2 - Repository Restructuring & Consolidation
- **Deduplication of `Documents/anc sih/`**:
  - Identified all duplicate files between `Documents/anc sih/` and top-level directories.
  - Kept single canonical copies; moved unique files to target directories:
    - Frontend moved to top-level `frontend/` (all UI, audio, network modules and tests).
    - Raspberry Pi deployment, streaming, and hardware scripts moved to top-level `edge/`.
    - Experimental models and ablation runs moved to top-level `experiments/`.
    - Architectural diagrams (`system_diagrams.md`, `interactive_diagram.html`) and diagnostic markdown reports moved to `docs/` and `docs/diagnostics/`.
    - Demonstration media and audio assets moved to `assets/` and `assets/audio/`.
    - Authoritative frozen model descriptor moved to `final_model/`.
  - Untracked `Documents/anc sih` duplicate folder from git index and added `Documents/` to `.gitignore`.
- **Absolute Symlinks & Gitlinks Removed**:
  - `edge-collected-gunshot-audio`: Symlink removed; replaced with `edge-collected-gunshot-audio/README.md` documenting dataset acquisition and IoBT audio storage.
  - `sih26052_edge`: Replaced with `sih26052_edge/README.md` pointing to canonical `edge/` code.
  - `runs/sih26052_canonical_validation`: Updated `README.md` documenting validation dataset generation and manifest hash.
  - Nested untracked submodules (`ANC_code_repo`, `antigravity`): Untracked from git index and replaced with explanatory README notes.
- **Canonical Model Documentation**:
  - Created top-level `MODEL.md` documenting fine-tuned DeepFilterNet3 (48 kHz, 2,167,969 parameters).
  - Listed frozen SHA256 checksum `522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe`, storage paths, and `shasum -a 256` verification procedure.
  - Excluded large binary checkpoints (`*.hk`, `*.ckpt`, `*.pt`) from git tracking.
- **Verification**:
  - `python3 -m compileall`: 0 syntax or compilation errors across all Python code in `src/`, `eval/`, `scripts/`, `deploy/`, `edge/`, `frontend/`, `docs/`.
  - `pytest frontend/tests`: 16 passed in 37.96s (100% pass rate).

## Phase 3 - Documentation: One Consistent Story
- **REPORT.md Rewritten Around DeepFilterNet3**:
  - Established DFN3 (48 kHz, frozen SHA256: `522c87ac9e7ff15a09e5d2043139d1b77ec3a6187cea9f91fff10addcabedfbe`) as the sole canonical model.
  - Moved legacy Polar-D, Complex CRN, DFN3 v2 rejected candidate, and NLMS negative results to `docs/experiments.md`.
  - Stated honest latency breakdown:
    - Deployed 500 ms block + 300 ms context configuration: **~713 ms median end-to-end latency** (500 ms accumulation + 213 ms median compute + ~1 ms UDP). No low-latency claims made for block configuration.
    - Model algorithmic latency: **~16 ms** (STFT hop length in streaming mode).
  - Integrated single authoritative PS Target comparison table (Input SNR 5/10/15 dB x Output SNR, STOI, PESQ), marking per-SNR breakdown as UNVERIFIED for DFN3 where traced to Polar-D baseline, reporting PESQ and low-SNR output SNR misses honestly.
  - Claims section revised: clarified single-channel neural filter (not physical ANC), documented NLMS negative result, retracted any claims of quantization/pruning/TensorRT, noted dual-mic reference path as untested.
- **PROJECT_INDEX.md Updated**:
  - Corrected stale "Pi NOT CONNECTED YET" status to confirmed hardware deployment and 6-minute stress testing results on Raspberry Pi 5.
- **Top-Level README.md Merged**:
  - Unified project-level and frontend READMEs into single top-level `README.md` with complete architecture diagram, quick start, deployment commands, stress test benchmarks, and directory tree.

## Phase 4 - History Scrub Audit
- **Backup Verification Check**:
  - Checked for sibling backup folders ending in `_backup` (e.g. `/Users/shreyasdivekar/*_backup`, `/Users/shreyasdivekar/Documents/*_backup`).
  - **Result:** Missing safety backup directory. Per user instruction ("just check for a sibling folder ending in _backup and stop with a clear message if missing"), historical rewriting with `git filter-repo` has been paused to protect git history against irreversible loss.
- **Scrubbing Script & Instructions Prepared**:
  - Script prepared to replace `[REDACTED]` with `REDACTED` via `git filter-repo --replace-text`.
  - Force-push instructions provided for execution after password rotation and backup creation.
