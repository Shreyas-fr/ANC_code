#!/usr/bin/env python3
"""Run paired comparisons for Ablation A1 vs Deployed Step-500 and R0 seed 26052."""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMPARE_SCRIPT = REPO / "antigravity/scripts/compare_dfn3_canonical_split.py"
OUT_DIR = REPO / "kaggle_output/dfn3_v10_a1_sisdr001"
DEPLOYED_CSV = REPO / "antigravity/runs/sih26052_dfn3_canonical_step500/per_clip.csv"
R0_500_CSV = REPO / "kaggle_output/dfn3_v10_r0_sih26052/canonical_eval_step500/per_clip.csv"
R0_550_CSV = REPO / "kaggle_output/dfn3_v10_r0_sih26052/canonical_eval_step550/per_clip.csv"

comparisons = [
    # (cand_step, ref_csv, ref_name, split)
    (500, DEPLOYED_CSV, "deployed_step500", "even"),
    (500, DEPLOYED_CSV, "deployed_step500", "odd"),
    (500, DEPLOYED_CSV, "deployed_step500", "all"),
    (500, R0_500_CSV, "r0_seed26052_step500", "even"),
    (500, R0_500_CSV, "r0_seed26052_step500", "odd"),
    (500, R0_500_CSV, "r0_seed26052_step500", "all"),
    (550, DEPLOYED_CSV, "deployed_step500", "even"),
    (550, DEPLOYED_CSV, "deployed_step500", "odd"),
    (550, DEPLOYED_CSV, "deployed_step500", "all"),
    (550, R0_550_CSV, "r0_seed26052_step550", "even"),
    (550, R0_550_CSV, "r0_seed26052_step550", "odd"),
    (550, R0_550_CSV, "r0_seed26052_step550", "all"),
]

def main():
    for step, ref_csv, ref_name, split in comparisons:
        cand_csv = OUT_DIR / f"canonical_eval_step{step}/per_clip.csv"
        out_json = OUT_DIR / f"paired_a1_step{step}_vs_{ref_name}_{split}.json"
        cmd = [
            "pc_venv/bin/python", str(COMPARE_SCRIPT),
            "--reference", str(ref_csv),
            "--candidate", str(cand_csv),
            "--output", str(out_json),
            "--split", split,
            "--bootstrap", "2000",
            "--seed", "26052"
        ]
        subprocess.run(cmd, check=True)
        print(f"Generated {out_json.name}")

if __name__ == "__main__":
    main()

