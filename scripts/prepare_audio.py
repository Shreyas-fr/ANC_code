import os
from pathlib import Path
import soundfile as sf
import librosa
import numpy as np
from tqdm import tqdm
import argparse
import multiprocessing

TARGET_SR = 16000

def process_file(args):
    src, dst = args
    if dst.exists():
        return # Skip if already processed
    
    try:
        audio, sr = sf.read(str(src))
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1) # convert to mono
            
        if sr != TARGET_SR:
            audio = librosa.resample(
                audio.astype(np.float32), 
                orig_sr=sr, 
                target_sr=TARGET_SR
            )
            
        audio = audio.astype(np.float32)
        dst.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(dst), audio, TARGET_SR, subtype="PCM_16")
    except Exception as e:
        print(f"ERROR processing {src}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Resample and normalize raw datasets to 16kHz PCM")
    parser.add_argument("--src", type=str, required=True, help="Raw data directory")
    parser.add_argument("--dst", type=str, required=True, help="Cleaned output directory")
    args = parser.parse_args()

    src_dir = Path(args.src)
    dst_dir = Path(args.dst)

    files = list(src_dir.rglob("*.flac")) + list(src_dir.rglob("*.wav"))
    print(f"Found {len(files)} audio files in {src_dir}")

    if not files:
        print("No files found to process.")
        return

    # Prepare multiprocessing arguments
    tasks = []
    for src in files:
        relative = src.relative_to(src_dir)
        dst = dst_dir / relative.with_suffix(".wav")
        tasks.append((src, dst))

    # Use multiprocessing to speed up resampling
    pool = multiprocessing.Pool(processes=max(1, multiprocessing.cpu_count() - 1))
    for _ in tqdm(pool.imap_unordered(process_file, tasks), total=len(tasks)):
        pass
    
    pool.close()
    pool.join()
    print(f"Done processing {src_dir} to {dst_dir}.")

if __name__ == "__main__":
    main()
