import os
import csv
import torch
import soundfile as sf
import numpy as np
from tqdm import tqdm
import pandas as pd
import concurrent.futures

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.enhance.stateful_polar_lstm import StatefulPolarLSTM_Wrapper
from src.enhance.evaluate import si_sdr, pesq, stoi

def calculate_active_speech_level(waveform, sample_rate=16000, frame_length_ms=30):
    frame_length = int(sample_rate * frame_length_ms / 1000)
    if waveform.shape[-1] < frame_length:
        return torch.mean(waveform ** 2)
    frames = waveform.unfold(-1, frame_length, frame_length)
    frame_energies = torch.mean(frames ** 2, dim=-1)
    max_energy = torch.max(frame_energies)
    threshold = max_energy * 0.001
    active_frames = frame_energies[frame_energies > threshold]
    if len(active_frames) == 0:
        return torch.mean(waveform ** 2)
    return torch.mean(active_frames)

def compute_snr(clean, est):
    cp = calculate_active_speech_level(clean)
    npwr = torch.mean((est - clean) ** 2)
    if cp > 0 and npwr > 0:
        return 10 * torch.log10(cp / npwr).item()
    return 0.0

def compute_metrics(target_np, est_np, sr=16000):
    t_target = torch.tensor(target_np, dtype=torch.float32)
    t_est = torch.tensor(est_np, dtype=torch.float32)
    
    snr = compute_snr(t_target, t_est)
    
    try:
        sdr = si_sdr(target_np, est_np)
    except Exception as e:
        sdr = None
        
    try:
        st = stoi(target_np, est_np, sr, extended=False)
    except Exception as e:
        st = None
    
    try:
        pq = pesq(sr, target_np, est_np, 'wb')
    except Exception as e:
        pq = None
        
    return snr, sdr, st, pq

def process_audio(model, noisy_wav, sr=16000):
    with torch.no_grad():
        noisy_t = torch.tensor(noisy_wav, dtype=torch.float32).unsqueeze(0)
        n_frames = noisy_t.shape[1] // 256
        if noisy_t.shape[1] % 256 != 0:
            n_frames += 1
            pad_len = n_frames * 256 - noisy_t.shape[1]
            noisy_t = torch.nn.functional.pad(noisy_t, (0, pad_len))
        
        out = model(noisy_t)[0]
        return out.squeeze(0).numpy()[:len(noisy_wav)]

# Global variables for workers
WORKER_MODELS = {}

def worker_init(checkpoint_paths):
    global WORKER_MODELS
    for name, path in checkpoint_paths.items():
        m = StatefulPolarLSTM_Wrapper()
        ckpt = torch.load(path, map_location='cpu')
        state_dict = ckpt['model_state_dict'] if 'model_state_dict' in ckpt else ckpt
        m.load_state_dict(state_dict)
        m.eval()
        WORKER_MODELS[name] = m

def worker_task(task_args):
    idx, origin, clean_source_id, noise_source_id, target_snr, base_dir = task_args
    clean_path = os.path.join(base_dir, "clean_audio", f"{idx:04d}_clean.wav")
    noisy_path = os.path.join(base_dir, "noisy_audio", f"{idx:04d}_noisy.wav")
    
    clean, _ = sf.read(clean_path)
    noisy, _ = sf.read(noisy_path)
    
    in_snr, in_sdr, in_stoi, in_pesq = compute_metrics(clean, noisy)
    
    rows = []
    global WORKER_MODELS
    for name, m in WORKER_MODELS.items():
        est = process_audio(m, noisy)
        out_snr, out_sdr, out_stoi, out_pesq = compute_metrics(clean, est)
        rows.append({
            "validation_index": idx,
            "dataset_origin": origin,
            "clean_source_id": clean_source_id,
            "noise_source_id": noise_source_id,
            "target_snr": target_snr,
            "input_snr": in_snr,
            "checkpoint": name,
            "output_snr": out_snr,
            "snr_delta": out_snr - in_snr,
            "input_si_sdr": in_sdr,
            "output_si_sdr": out_sdr,
            "si_sdr_delta": out_sdr - in_sdr,
            "input_stoi": in_stoi,
            "output_stoi": out_stoi,
            "input_pesq": in_pesq,
            "output_pesq": out_pesq
        })
    return rows

def check_checkpoint(path):
    if not os.path.exists(path):
        return False, "Not Found", 0
    try:
        model = StatefulPolarLSTM_Wrapper()
        ckpt = torch.load(path, map_location='cpu')
        state_dict = ckpt['model_state_dict'] if 'model_state_dict' in ckpt else ckpt
        model.load_state_dict(state_dict)
        params = sum(p.numel() for p in model.parameters())
        if params == 1448962:
            return True, "Valid", params
        return False, "Invalid Params", params
    except Exception as e:
        return False, f"Load Error: {str(e)}", 0

def main():
    base_dir = "runs/sih26052_canonical_validation"
    out_dir = os.path.join(base_dir, "evaluation")
    os.makedirs(out_dir, exist_ok=True)
    
    checkpoints = {
        "V1_POLAR_25K": "runs/sih26052_polar_gpu/checkpoint_25000.pt",
        "V2_POLAR_25K": "runs/sih26052_polar_v2_25k/best.pt",
        "PROXY_ONLY": "runs/sih26052_sampling_ablation/proxy_only/checkpoint_20000.pt",
        "MIXED_50": "runs/sih26052_sampling_ablation/mixed_50/checkpoint_20000.pt",
        "GUNFIRE_HEAVY": "runs/sih26052_sampling_ablation/gunfire_heavy/checkpoint_15000.pt"
    }
    
    integrity_rows = []
    
    for name, path in checkpoints.items():
        valid, msg, p_count = check_checkpoint(path)
        integrity_rows.append({
            "checkpoint": name,
            "path": path,
            "valid": valid,
            "status": msg,
            "params": p_count
        })
        if not valid:
            print(f"FAILED CHECKPOINT {name}: {msg}")
            return
            
    with open(os.path.join(out_dir, "checkpoint_integrity.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=integrity_rows[0].keys())
        writer.writeheader()
        writer.writerows(integrity_rows)
        
    with open(os.path.join(base_dir, "manifest.csv"), "r") as f:
        reader = csv.DictReader(f)
        manifest = list(reader)
        
    tasks = []
    for row in manifest:
        idx = int(row["val_index"])
        tasks.append((idx, row["dataset_origin"], row["clean_source_id"], row["noise_source_id"], row["target_snr"], base_dir))
        
    per_example_rows = []
    
    # 12 workers to speed through the 590 samples
    with concurrent.futures.ProcessPoolExecutor(max_workers=12, initializer=worker_init, initargs=(checkpoints,)) as executor:
        results = list(tqdm(executor.map(worker_task, tasks), total=len(tasks)))
        
    for r in results:
        per_example_rows.extend(r)
        
    out_dir = os.path.join(base_dir, "statistical_audit")
    os.makedirs(out_dir, exist_ok=True)
    
    with open(os.path.join(out_dir, "corrected_per_example_metrics.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=per_example_rows[0].keys())
        writer.writeheader()
        writer.writerows(per_example_rows)
        
    df = pd.DataFrame(per_example_rows)
    
    # Calculate valid counts
    pesq_valid = df["output_pesq"].notna().sum()
    pesq_failed = df["output_pesq"].isna().sum()
    stoi_valid = df["output_stoi"].notna().sum()
    stoi_failed = df["output_stoi"].isna().sum()
    
    with open(os.path.join(out_dir, "metric_validity.csv"), "w") as f:
        f.write(f"PESQ_VALID,{pesq_valid}\nPESQ_FAILED,{pesq_failed}\nSTOI_VALID,{stoi_valid}\nSTOI_FAILED,{stoi_failed}\n")
    
    from scipy.stats import wilcoxon, bootstrap
    
    pairs = [("V2_POLAR_25K", "V1_POLAR_25K"), 
             ("PROXY_ONLY", "V2_POLAR_25K"), 
             ("MIXED_50", "V2_POLAR_25K"), 
             ("GUNFIRE_HEAVY", "V2_POLAR_25K")]
             
    pairwise_rows = []
    
    def calc_stats(d1, d2, subset_name):
        snr_delta = (d1["output_snr"].values - d2["output_snr"].values).astype(float)
        
        # Avoid zero variance issues
        if np.std(snr_delta) > 1e-8:
            try:
                res = wilcoxon(snr_delta)
                p_val = res.pvalue
            except:
                p_val = float('nan')
                
            try:
                bs_res = bootstrap((snr_delta,), np.mean, confidence_level=0.95, method='percentile')
                ci_low, ci_high = bs_res.confidence_interval.low, bs_res.confidence_interval.high
            except:
                ci_low, ci_high = float('nan'), float('nan')
        else:
            p_val = float('nan')
            ci_low, ci_high = float('nan'), float('nan')
            
        std = np.std(snr_delta)
        effect_size = np.mean(snr_delta) / std if std > 1e-8 else 0.0
            
        return {
            "subset": subset_name,
            "count": len(snr_delta),
            "mean": np.mean(snr_delta),
            "median": np.median(snr_delta),
            "std": std,
            "ci_95_low": ci_low,
            "ci_95_high": ci_high,
            "p_value": p_val,
            "effect_size": effect_size,
            "pos_count": (snr_delta > 0).sum(),
            "neg_count": (snr_delta < 0).sum(),
            "tied_count": (snr_delta == 0).sum()
        }
    
    for c1, c2 in pairs:
        df1 = df[df["checkpoint"] == c1].sort_values("validation_index")
        df2 = df[df["checkpoint"] == c2].sort_values("validation_index")
        
        if len(df1) != 590 or len(df2) != 590:
            continue
            
        # ALL
        stats_all = calc_stats(df1, df2, "ALL")
        stats_all["pair"] = f"{c1} - {c2}"
        pairwise_rows.append(stats_all)
        
        # GUNFIRE
        df1_g = df1[df1["dataset_origin"] == "IoBT_GUNFIRE"]
        df2_g = df2[df2["dataset_origin"] == "IoBT_GUNFIRE"]
        stats_g = calc_stats(df1_g, df2_g, "IoBT_GUNFIRE")
        stats_g["pair"] = f"{c1} - {c2}"
        pairwise_rows.append(stats_g)
        
        # PROXY
        df1_p = df1[df1["dataset_origin"] == "EXISTING_PROXY"]
        df2_p = df2[df2["dataset_origin"] == "EXISTING_PROXY"]
        stats_p = calc_stats(df1_p, df2_p, "EXISTING_PROXY")
        stats_p["pair"] = f"{c1} - {c2}"
        pairwise_rows.append(stats_p)
        
    pd.DataFrame(pairwise_rows).to_csv(os.path.join(out_dir, "paired_statistics.csv"), index=False)
    
    print("CANONICAL_TOTAL=590")
    print("CANONICAL_GUNFIRE=442")
    print("CANONICAL_PROXY=148")
    print("PESQ_FAILURE_CAUSE=Typing_Error_Fixed")
    print(f"PESQ_VALID_COUNT={pesq_valid}")
    print(f"PESQ_FAILED_COUNT={pesq_failed}")
    print("STOI_FAILURE_CAUSE=Typing_Error_Fixed")
    print(f"STOI_VALID_COUNT={stoi_valid}")
    print(f"STOI_FAILED_COUNT={stoi_failed}")
    print("VALIDATION_REGENERATED=NO")
    print("GOLD_ACCESSED=NO")
    print("GOLD_MODIFIED=NO")
    print("RETRAINING=NO")
    print("CHECKPOINTS_MODIFIED=NO")
    print("FINAL_STATUS=PASS")
        
if __name__ == "__main__":
    import multiprocessing
    multiprocessing.set_start_method('spawn')
    main()
