import json, glob
from pathlib import Path

files = sorted(glob.glob("kaggle_output/dfn3_v10_a1_sisdr001/paired_*.json"))
for f in files:
    data = json.loads(Path(f).read_text())
    print("=" * 70)
    print(Path(f).name)
    split = data.get("split")
    count = data.get("clip_count")
    print(f"Split: {split} | Count: {count}")
    
    means = data.get("candidate_overall", {}).get("means", {})
    deltas = data.get("paired_deltas", {})
    for m in ["snr_db", "si_sdr_db", "stoi", "pesq_wb"]:
        cand_m = means.get(m, {}).get("mean", 0.0)
        d = deltas.get(m, {})
        diff = d.get("mean_candidate_minus_reference", 0.0)
        ci_lo = d.get("ci95_low", 0.0)
        ci_hi = d.get("ci95_high", 0.0)
        print(f"  {m:10s}: cand={cand_m:8.4f}, delta={diff:+8.4f}, 95%CI=[{ci_lo:+7.4f}, {ci_hi:+7.4f}]")
    
    co = data.get("candidate_overall", {})
    cand_pass = co.get("pass_counts", {}).get("all_three", "N/A")
    print(f"  Candidate joint pass count: {cand_pass}/{count}")
