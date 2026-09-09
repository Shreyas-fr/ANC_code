import os
import shutil
from pathlib import Path

def categorize():
    NOISE_DIR = Path("data/noise")
    if not NOISE_DIR.exists():
        print("data/noise does not exist yet.")
        return

    targets = ["stationary", "nonstationary", "impulsive"]
    for t in targets:
        (NOISE_DIR / t).mkdir(parents=True, exist_ok=True)

    # Map DEMAND
    demand_map = {
        "DKITCHEN": "stationary", "DLIVING": "stationary", "DWASHING": "stationary",
        "NFIELD": "stationary", "NPARK": "stationary", "NRIVER": "stationary",
        "OHALLWAY": "nonstationary", "OMEETING": "nonstationary", "OOFFICE": "nonstationary",
        "PCAFETER": "nonstationary", "PRESTO": "nonstationary", "PSTATION": "nonstationary",
        "SPSQUARE": "nonstationary", "STRAFFIC": "nonstationary", "TBUS": "stationary",
        "TCAR": "stationary", "TMETRO": "stationary"
    }

    demand_dir = NOISE_DIR / "demand"
    if demand_dir.exists():
        for demand_cat, target_cat in demand_map.items():
            src = demand_dir / demand_cat
            dst = NOISE_DIR / target_cat / demand_cat
            if src.exists() and not dst.exists():
                print(f"Moving {src} to {dst}")
                shutil.move(str(src), str(dst))

    # Map MUSAN
    musan_dir = NOISE_DIR / "musan"
    if musan_dir.exists():
        musan_map = {
            "noise": "stationary",
            "music": "nonstationary",
            "speech": "nonstationary"
        }
        for musan_cat, target_cat in musan_map.items():
            src = musan_dir / musan_cat
            dst = NOISE_DIR / target_cat / f"musan_{musan_cat}"
            if src.exists() and not dst.exists():
                print(f"Moving {src} to {dst}")
                shutil.move(str(src), str(dst))

if __name__ == "__main__":
    categorize()
