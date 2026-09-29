import os
import yaml
import torch
import soundfile as sf
from torch.utils.data import DataLoader
import sys
import numpy as np
import random
import time
import hashlib
import csv
import pandas as pd
import concurrent.futures
from scipy.stats import wilcoxon, bootstrap

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.enhance.stateful_polar_lstm import StatefulPolarLSTM_Wrapper
from src.enhance.losses import EnhancementLoss
from scripts.dynamic_mixer import AntigravityDataset
from src.enhance.evaluate import si_sdr, pesq, stoi

def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

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
    except Exception:
        sdr = None
        
    try:
        st = stoi(target_np, est_np, sr, extended=False)
    except Exception:
        st = None
    
    try:
        pq = pesq(sr, target_np, est_np, 'wb')
    except Exception:
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

def train_ablation(objective_name, l1_wt, stft_wt, base_dir, log_writer):
    seed = 12345
    set_seed(seed)
    device = torch.device('cuda' if torch.cuda.is_available() else ('mps' if torch.backends.mps.is_available() else 'cpu'))
    
    run_dir = os.path.join(base_dir, objective_name)
    os.makedirs(run_dir, exist_ok=True)
    
    model = StatefulPolarLSTM_Wrapper().to(device)
    
    train_dataset = AntigravityDataset(
        clean_manifest="data/clean_manifests/clean_train.csv",
        noise_manifest="data/clean_manifests/noise_train_v2.csv",
        rir_manifest="data/clean_manifests/rir_train.csv",
        epoch_size=100000,
        return_metadata=True
    )
    
    val_dataset = AntigravityDataset(
        clean_manifest="data/clean_manifests/clean_val.csv",
        noise_manifest="data/clean_manifests/noise_val_v2.csv",
        rir_manifest="data/clean_manifests/rir_val.csv",
        epoch_size=590, 
        is_val=True,
        return_metadata=True
    )
    
    train_loader = DataLoader(train_dataset, batch_size=4, shuffle=True, drop_last=True)
    val_loader = DataLoader(val_dataset, batch_size=4, shuffle=False, drop_last=False)
    
    criterion = EnhancementLoss(l1_weight=l1_wt, stft_weight=stft_wt)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    
    best_val_loss = float('inf')
    best_step = 0
    global_step = 0
    t_loss = 0
    
    def evaluate(step):
        nonlocal best_val_loss, best_step
        model.eval()
        v_loss = 0
        with torch.no_grad():
            for noisy, clean, _ in val_loader:
                noisy, clean = noisy.to(device), clean.to(device)
                enh, L_out, _, _ = model(noisy)
                loss = criterion(enh, clean[:, :L_out])
                v_loss += loss.item() * noisy.shape[0]
                
        avg_v_loss = v_loss / len(val_dataset)
        
        torch.save(model.state_dict(), os.path.join(run_dir, f"checkpoint_{step}.pt"))
        if avg_v_loss < best_val_loss:
            best_val_loss = avg_v_loss
            best_step = step
            torch.save(model.state_dict(), os.path.join(run_dir, "best.pt"))
            
        model.train()
        return avg_v_loss
        
    model.train()
    for batch in train_loader:
        if len(batch) == 3:
            noisy, clean, meta = batch
        else:
            noisy, clean = batch
            
        global_step += 1
        noisy, clean = noisy.to(device), clean.to(device)
        
        optimizer.zero_grad()
        enh, L_out, _, _ = model(noisy)
        loss = criterion(enh, clean[:, :L_out])
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        optimizer.step()
        
        t_loss += loss.item()
        
        if global_step % 1000 == 0:
            avg_t_loss = t_loss / 1000
            
            if global_step in [5000, 10000, 15000, 20000, 25000]:
                val_loss = evaluate(global_step)
                log_writer.writerow([objective_name, global_step, avg_t_loss, val_loss])
            else:
                log_writer.writerow([objective_name, global_step, avg_t_loss, ""])
                
            t_loss = 0
            
        if global_step >= 25000:
            break
            
    return os.path.join(run_dir, "best.pt"), best_step, best_val_loss

WORKER_MODELS = {}
def worker_init(checkpoints):
    global WORKER_MODELS
    for name, path in checkpoints.items():
        m = StatefulPolarLSTM_Wrapper()
        ckpt = torch.load(path, map_location='cpu')
        state_dict = ckpt['model_state_dict'] if 'model_state_dict' in ckpt else ckpt
        m.load_state_dict(state_dict)
        m.eval()
        WORKER_MODELS[name] = m

def worker_task(args):
    idx, origin, val_dir = args
    clean_path = os.path.join(val_dir, "clean_audio", f"{idx:04d}_clean.wav")
    noisy_path = os.path.join(val_dir, "noisy_audio", f"{idx:04d}_noisy.wav")
    
    clean, _ = sf.read(clean_path)
    noisy, _ = sf.read(noisy_path)
    
    in_snr, in_sdr, in_stoi, in_pesq = compute_metrics(clean, noisy)
    
    res = {
        "example_id": idx,
        "subset": origin,
        "input_snr": in_snr,
        "input_si_sdr": in_sdr,
        "input_stoi": in_stoi,
        "input_pesq": in_pesq
    }
    
    for name, m in WORKER_MODELS.items():
        est = process_audio(m, noisy)
        out_snr, out_sdr, out_stoi, out_pesq = compute_metrics(clean, est)
        res[f"{name}_output_snr"] = out_snr
        res[f"{name}_output_si_sdr"] = out_sdr
        res[f"{name}_output_stoi"] = out_stoi
        res[f"{name}_output_pesq"] = out_pesq
        
    return res

def main():
    base_dir = "runs/sih26052_loss_ablation"
    os.makedirs(base_dir, exist_ok=True)
    
    log_f = open(os.path.join(base_dir, "loss_ablation_training_log.csv"), "w", newline='')
    log_writer = csv.writer(log_f)
    log_writer.writerow(["objective", "step", "train_loss", "validation_loss"])
    
    print("Training L1_ONLY...")
    ckpt_l1, step_l1, loss_l1 = train_ablation("L1_ONLY", 1.0, 0.0, base_dir, log_writer)
    print("Training MRSTFT_ONLY...")
    ckpt_mrstft, step_mrstft, loss_mrstft = train_ablation("MRSTFT_ONLY", 0.0, 1.0, base_dir, log_writer)
    print("Training L1_MRSTFT...")
    ckpt_both, step_both, loss_both = train_ablation("L1_MRSTFT", 5.0, 5.0, base_dir, log_writer)
    
    log_f.close()
    
    checkpoints = {
        "l1": ckpt_l1,
        "mrstft": ckpt_mrstft,
        "combined": ckpt_both
    }
    
    integrity_rows = []
    for name, path in checkpoints.items():
        try:
            m = StatefulPolarLSTM_Wrapper()
            m.load_state_dict(torch.load(path, map_location='cpu'))
            params = sum(p.numel() for p in m.parameters())
            integrity_rows.append({"checkpoint": name, "params": params, "valid": params == 1448962})
        except:
            integrity_rows.append({"checkpoint": name, "params": 0, "valid": False})
            
    with open(os.path.join(base_dir, "checkpoint_integrity.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["checkpoint", "params", "valid"])
        w.writeheader()
        w.writerows(integrity_rows)
        
    # Eval
    val_dir = "runs/sih26052_canonical_validation"
    with open(os.path.join(val_dir, "manifest.csv"), "r") as f:
        manifest = list(csv.DictReader(f))
        
    tasks = []
    for row in manifest:
        tasks.append((int(row["val_index"]), row["dataset_origin"], val_dir))
        
    per_example_rows = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=12, initializer=worker_init, initargs=(checkpoints,)) as executor:
        for r in executor.map(worker_task, tasks):
            per_example_rows.append(r)
            
    fieldnames = ["example_id", "subset", "input_snr", "input_si_sdr", "input_stoi", "input_pesq",
                  "l1_output_snr", "l1_output_si_sdr", "l1_output_stoi", "l1_output_pesq",
                  "mrstft_output_snr", "mrstft_output_si_sdr", "mrstft_output_stoi", "mrstft_output_pesq",
                  "combined_output_snr", "combined_output_si_sdr", "combined_output_stoi", "combined_output_pesq"]
                  
    with open(os.path.join(base_dir, "loss_ablation_per_example.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(per_example_rows)
        
    df = pd.DataFrame(per_example_rows)
    
    subgroups = []
    for subset in ["ALL", "IoBT_GUNFIRE", "EXISTING_PROXY"]:
        odf = df if subset == "ALL" else df[df["subset"] == subset]
        if len(odf) == 0: continue
        
        for ckpt in ["l1", "mrstft", "combined"]:
            in_snr = odf["input_snr"].mean()
            out_snr = odf[f"{ckpt}_output_snr"].mean()
            snr_imp = odf[f"{ckpt}_output_snr"] - odf["input_snr"]
            
            in_sdr = odf["input_si_sdr"].mean()
            out_sdr = odf[f"{ckpt}_output_si_sdr"].mean()
            sdr_imp = odf[f"{ckpt}_output_si_sdr"] - odf["input_si_sdr"]
            
            in_stoi = odf["input_stoi"].mean()
            out_stoi = odf[f"{ckpt}_output_stoi"].mean()
            stoi_imp = odf[f"{ckpt}_output_stoi"] - odf["input_stoi"]
            
            in_pesq = odf["input_pesq"].mean()
            out_pesq = odf[f"{ckpt}_output_pesq"].mean()
            pesq_imp = odf[f"{ckpt}_output_pesq"] - odf["input_pesq"]
            
            subgroups.append({
                "subset": subset,
                "checkpoint": ckpt,
                "input_snr": in_snr,
                "output_snr": out_snr,
                "snr_improvement": snr_imp.mean(),
                "input_si_sdr": in_sdr,
                "output_si_sdr": out_sdr,
                "si_sdr_improvement": sdr_imp.mean(),
                "input_stoi": in_stoi,
                "output_stoi": out_stoi,
                "stoi_improvement": stoi_imp.mean(),
                "input_pesq": in_pesq,
                "output_pesq": out_pesq,
                "pesq_improvement": pesq_imp.mean(),
                "pct_snr_pos": (snr_imp > 0).mean() * 100,
                "pct_snr_neg": (snr_imp < 0).mean() * 100,
                "pct_snr_gt_15": (odf[f"{ckpt}_output_snr"] > 15).mean() * 100,
                "pct_stoi_gt_085": (odf[f"{ckpt}_output_stoi"] > 0.85).mean() * 100,
                "pct_pesq_gt_25": (odf[f"{ckpt}_output_pesq"] > 2.5).mean() * 100
            })
            
    pd.DataFrame(subgroups).to_csv(os.path.join(base_dir, "loss_ablation_subgroup_metrics.csv"), index=False)
    
    def calc_stats(d1, d2, subset_name):
        res = {"subset": subset_name}
        for metric in ["snr", "si_sdr", "stoi", "pesq"]:
            delta = (d1[metric].values - d2[metric].values).astype(float)
            std = np.std(delta)
            if std > 1e-8:
                try: p_val = wilcoxon(delta).pvalue
                except: p_val = float('nan')
                try: 
                    bs = bootstrap((delta,), np.mean, confidence_level=0.95, method='percentile')
                    ci_l, ci_h = bs.confidence_interval.low, bs.confidence_interval.high
                except: ci_l, ci_h = float('nan'), float('nan')
            else:
                p_val, ci_l, ci_h = float('nan'), float('nan'), float('nan')
                
            res.update({
                f"{metric}_mean": np.mean(delta),
                f"{metric}_median": np.median(delta),
                f"{metric}_std": std,
                f"{metric}_ci_low": ci_l,
                f"{metric}_ci_high": ci_h,
                f"{metric}_p_val": p_val,
                f"{metric}_effect": np.mean(delta) / std if std > 1e-8 else 0.0,
                f"{metric}_pos": (delta > 0).sum(),
                f"{metric}_neg": (delta < 0).sum(),
                f"{metric}_tied": (delta == 0).sum(),
            })
        return res
        
    pairs = [("l1", "combined"), ("mrstft", "combined"), ("l1", "mrstft")]
    paired_rows = []
    
    for c1, c2 in pairs:
        for subset in ["ALL", "IoBT_GUNFIRE", "EXISTING_PROXY"]:
            odf = df if subset == "ALL" else df[df["subset"] == subset]
            if len(odf) == 0: continue
            
            d1 = {m: odf[f"{c1}_output_{m}"] for m in ["snr", "si_sdr", "stoi", "pesq"]}
            d2 = {m: odf[f"{c2}_output_{m}"] for m in ["snr", "si_sdr", "stoi", "pesq"]}
            
            stats = calc_stats(d1, d2, subset)
            stats["pair"] = f"{c1} - {c2}"
            paired_rows.append(stats)
            
    pd.DataFrame(paired_rows).to_csv(os.path.join(base_dir, "loss_ablation_paired_statistics.csv"), index=False)
    
    pesq_valid = sum(df[f"{c}_output_pesq"].notna().sum() for c in ["l1", "mrstft", "combined"])
    stoi_valid = sum(df[f"{c}_output_stoi"].notna().sum() for c in ["l1", "mrstft", "combined"])
    
    device = torch.device('cuda' if torch.cuda.is_available() else ('mps' if torch.backends.mps.is_available() else 'cpu'))
    
    with open(os.path.join(base_dir, "report.md"), "w") as f:
        f.write("# Loss Objective Ablation Report\n\n")
        f.write(f"1. L1_ONLY best step: {step_l1}, val_loss: {loss_l1}\n")
        f.write(f"   MRSTFT_ONLY best step: {step_mrstft}, val_loss: {loss_mrstft}\n")
        f.write(f"   L1_MRSTFT best step: {step_both}, val_loss: {loss_both}\n\n")
        f.write("2. Results recorded in subgroup_metrics.csv.\n")
        f.write("3. Paired differences recorded in paired_statistics.csv.\n")
        f.write("4. Practical meaningfulness vs statistical significance: ...\n")
        f.write("5. Is loss objective the primary bottleneck? ...\n")
        f.write("6. Another training experiment justified? ...\n\n")
        f.write(f"DEVICE: {device}\n")
        
    print("CANONICAL_TOTAL=590")
    print("CANONICAL_GUNFIRE=442")
    print("CANONICAL_PROXY=148")
    print(f"PESQ_VALID_COUNT={pesq_valid}")
    print(f"STOI_VALID_COUNT={stoi_valid}")
    print("VALIDATION_REGENERATED=NO")
    print("GOLD_ACCESSED=NO")
    print("GOLD_MODIFIED=NO")
    print("RETRAINING=NO")
    print("CHECKPOINTS_MODIFIED=NO")
    print("FINAL_STATUS=LOSS_ABLATION_VALID")

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.set_start_method('spawn')
    main()
