import pandas as pd
import soundfile as sf
from pathlib import Path
from tqdm import tqdm

def validate_manifest(manifest_path):
    print(f"\n======================================")
    print(f"Validating {manifest_path}...")
    print(f"======================================")
    
    if not Path(manifest_path).exists():
        print(f"Manifest not found: {manifest_path}")
        return
        
    df = pd.read_csv(manifest_path)
    issues = 0
    
    for _, row in tqdm(df.iterrows(), total=len(df)):
        path = row['path']
        if not Path(path).exists():
            print(f"Missing file: {path}")
            issues += 1
            continue
            
        try:
            info = sf.info(path)
            if info.samplerate != 16000:
                print(f"Wrong sample rate ({info.samplerate}) in {path}")
                issues += 1
            if info.subtype != 'PCM_16':
                print(f"Wrong subtype ({info.subtype}) in {path}")
                issues += 1
            if info.channels != 1:
                print(f"Wrong channels ({info.channels}) in {path}")
                issues += 1
        except Exception as e:
            print(f"Error reading {path}: {e}")
            issues += 1
            
    if issues == 0:
        print(f"{manifest_path} is fully valid! All files are 16kHz, 16-bit Mono PCM.")
    else:
        print(f"Found {issues} issues in {manifest_path}.")

def main():
    manifests = ["data/manifests/clean.csv", "data/manifests/noise.csv", "data/manifests/rir.csv"]
    for m in manifests:
        validate_manifest(m)

if __name__ == "__main__":
    main()
