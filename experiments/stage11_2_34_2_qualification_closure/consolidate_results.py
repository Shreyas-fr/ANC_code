#!/usr/bin/env python3
"""
Consolidates all Stage 11.2.34.2 task outputs into master stage11_2_34_2_results.json.
"""

import json
from pathlib import Path

STAGE_DIR = Path("/Users/shreyasdivekar/Documents/anc sih/antigravity/experiments/stage11_2_34_2_qualification_closure")

def main():
    t1 = json.loads((STAGE_DIR / "task1_host_runtime_memory.json").read_text())
    t2 = json.loads((STAGE_DIR / "task2_ort_allocations.json").read_text())
    t3 = json.loads((STAGE_DIR / "task3_recurrent_numerical_parity.json").read_text())
    t4 = json.loads((STAGE_DIR / "task4_waveform_parity.json").read_text())
    t5 = json.loads((STAGE_DIR / "task5_provenance_and_hashes.json").read_text())

    master = {
        "stage": "11.2.34.2",
        "title": "Native Runtime Memory, ONNX Allocation & Recurrent Parity Closure",
        "date": "2026-11-14",
        "gate_dispositions": {
            "gate_01_complete_native_runtime": {
                "status": "INCONCLUSIVE",
                "finding": "Host driver (C DSP + ONNX Runtime) measured at 298.01 MB (284.20 MiB) over 10,000 frames with zero memory growth in final 3,000 frames. Standalone non-Python C executable gate marked INCONCLUSIVE due to lack of C SDK headers in offline environment."
            },
            "gate_02_onnx_allocation_instrumentation": {
                "status": "PASS",
                "finding": "Inference sessions use CPUExecutionProvider BFCArena allocator. Steady-state arena expansion delta was 0 bytes across all frames. Lock-free claims explicitly rejected."
            },
            "gate_03_recurrent_numerical_parity": {
                "status": "PASS_WITH_REQUESTED_TOLERANCE_ADJUSTMENT",
                "finding": "Non-divergent error progression proven empirically and analytically. Observed peaks: Fullband out 9.92e-5 (vs original 7.0e-5), Fullband c 1.72e-4 (vs original 5.0e-5), Subband c 2.75e-4 (vs original 5.0e-5). Formally submitted for reviewer sign-off without silent relaxation."
            },
            "gate_04_waveform_parity_reproduction": {
                "status": "PASS",
                "finding": "10-clip canonical validation reproduced with min SDR 105.70 dB, max ΔSNR 0.0000 dB, 0-sample lag, and exact N-to-N sample reconstruction (final 30 ms tail SDR 102.71 dB)."
            },
            "gate_05_provenance_and_protected_hashes": {
                "status": "PASS",
                "finding": "All 5 protected hashes bit-exact. Holdout test set sealed."
            }
        },
        "overall_stage_verdict": "PARTIALLY_SATISFIED_PENDING_REVIEWER_SIGNOFF",
        "recommendation": "Do not declare unconditional completion; wait for reviewer evaluation of Gate 01 blocker and Gate 03 tolerance adjustment request.",
        "task1_runtime_memory": t1,
        "task2_ort_allocations": t2,
        "task3_recurrent_parity": t3,
        "task4_waveform_parity": t4,
        "task5_provenance_and_hashes": t5,
    }

    out_file = STAGE_DIR / "stage11_2_34_2_results.json"
    out_file.write_text(json.dumps(master, indent=2) + "\n")
    print(f"Master results consolidated to: {out_file}")

if __name__ == "__main__":
    main()

