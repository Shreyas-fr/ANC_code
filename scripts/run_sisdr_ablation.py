import os
import torch
import soundfile as sf
from torch.utils.data import DataLoader
import sys
import numpy as np
import random
import hashlib
import csv
import pandas as pd
import concurrent.futures
from scipy.stats import wilcoxon, bootstrap
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.enhance.stateful_polar_lstm import StatefulPolarLSTM_Wrapper
from src.enhance.losses import MultiResolutionSTFTLoss, SISDRLoss
from scripts.dynamic_mixer import AntigravityDataset
from src.enhance.evaluate import si_sdr, pesq, stoi

def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

def compute_snr(clean, est):
    cp = torch.mean(clean ** 2)
    npwr = torch.mean((est - clean) ** 2)
    if cp > 0 and npwr > 0:
        return 10 * torch.log10(cp / npwr).item()
    return 0.0

def compute_metrics(target_np, est_np, sr=16000):
    t_target = torch.tensor(target_np, dtype=torch.float32)
    t_est = torch.tensor(est_np, dtype=torch.float32)
    snr = compute_snr(t_target, t_est)
    
    try: sdr = si_sdr(target_np, est_np)
    except: sdr = None
    try: st = stoi(target_np, est_np, sr, extended=False)
    except: st = None
    try: pq = pesq(sr, target_np, est_np, 'wb')
    except: pq = None
    return snr, sdr, st, pq

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

def process_audio(model, noisy_wav):
    with torch.no_grad():
        noisy_t = torch.tensor(noisy_wav, dtype=torch.float32).unsqueeze(0)
        n_frames = noisy_t.shape[1] // 256
        if noisy_t.shape[1] % 256 != 0:
            n_frames += 1
            pad_len = n_frames * 256 - noisy_t.shape[1]
            noisy_t = torch.nn.functional.pad(noisy_t, (0, pad_len))
        out, expected_len, mag, phase = model(noisy_t)
        return out.squeeze(0).numpy()[:len(noisy_wav)]

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

def compute_diagnostics(model, val_loader, device):
    model.eval()
    all_mag = []
    all_phase = []
    all_est = []
    all_clean = []
    all_noisy = []
    
    total_l1 = 0
    total_stft = 0
    total_sisdr = 0
    stft_fn = MultiResolutionSTFTLoss().to(device)
    sisdr_fn = SISDRLoss().to(device)
    
    n_items = 0
    with torch.no_grad():
        for noisy, clean, meta in val_loader:
            noisy, clean = noisy.to(device), clean.to(device)
            enh, L_out, mag, phase = model(noisy)
            
            est = enh
            tgt = clean[:, :L_out]
            
            l1 = torch.nn.functional.l1_loss(est, tgt).item()
            stft = stft_fn(est, tgt).item()
            sdr_loss = sisdr_fn(est, tgt).item()
            
            bz = noisy.shape[0]
            total_l1 += l1 * bz
            total_stft += stft * bz
            total_sisdr += sdr_loss * bz
            n_items += bz
            
            all_mag.append(mag.cpu().numpy())
            all_phase.append(phase.cpu().numpy())
            
            for i in range(bz):
                all_est.append(est[i].cpu().numpy())
                all_clean.append(tgt[i].cpu().numpy())
                all_noisy.append(noisy[i].cpu().numpy())

    mag_arr = np.concatenate(all_mag, axis=0)
    phase_arr = np.concatenate(all_phase, axis=0)
    
    avg_l1 = total_l1 / n_items
    avg_stft = total_stft / n_items
    avg_sisdr = total_sisdr / n_items
    total_loss = 5.0 * avg_l1 + 5.0 * avg_stft + 1.0 * avg_sisdr
    
    # Mask diagnostics
    mag_mean = float(np.mean(mag_arr))
    mag_std = float(np.std(mag_arr))
    pct_gt_1 = float(np.mean(mag_arr > 1.0) * 100)
    phase_mean = float(np.mean(phase_arr))
    phase_std = float(np.std(phase_arr))
    nan_inf = int(np.isnan(mag_arr).sum() + np.isinf(mag_arr).sum())
    
    # RMS and correlation
    speech_corrs = []
    rms_ratios = []
    
    for c, e, n in zip(all_clean, all_est, all_noisy):
        if np.std(c) > 0 and np.std(e) > 0:
            corr = np.corrcoef(c, e)[0, 1]
            speech_corrs.append(corr)
        rms_in = np.sqrt(np.mean(n**2))
        rms_out = np.sqrt(np.mean(e**2))
        if rms_in > 0:
            rms_ratios.append(rms_out / rms_in)
            
    mean_corr = float(np.nanmean(speech_corrs)) if len(speech_corrs) > 0 else 0.0
    mean_rms_ratio = float(np.nanmean(rms_ratios)) if len(rms_ratios) > 0 else 0.0
    
    return {
        "val_total_loss": total_loss,
        "val_l1": avg_l1,
        "val_mrstft": avg_stft,
        "val_sisdr": avg_sisdr,
        "mag_mean": mag_mean,
        "mag_std": mag_std,
        "pct_gt_1": pct_gt_1,
        "phase_mean": phase_mean,
        "phase_std": phase_std,
        "speech_corr": mean_corr,
        "rms_ratio": mean_rms_ratio,
        "nan_inf": nan_inf
    }

def verify_integrity(val_dir):
    with open(os.path.join(val_dir, "manifest.csv"), "r") as f:
        data = f.read()
    h = hashlib.sha256(data.encode()).hexdigest()
    assert h == "3975924a685a74ea91323867d13220afb87325977303c3bb4b680b5e1b9f15b7", f"Canonical validation mismatch: {h}"
    return True

def main():
    seed = 12345
    set_seed(seed)
    
    base_dir = "runs/sih26052_sisdr_loss_25k"
    os.makedirs(base_dir, exist_ok=True)
    val_dir = "runs/sih26052_canonical_validation"
    
    verify_integrity(val_dir)
    
    device = torch.device('cuda' if torch.cuda.is_available() else ('mps' if torch.backends.mps.is_available() else 'cpu'))
    model = StatefulPolarLSTM_Wrapper().to(device)
    params = sum(p.numel() for p in model.parameters())
    assert params == 1448962
    
    train_dataset = AntigravityDataset(
        clean_manifest="data/clean_manifests/clean_train.csv",
        noise_manifest="data/clean_manifests/noise_train_v2.csv",
        rir_manifest="data/clean_manifests/rir_train.csv",
        epoch_size=100000,
        return_metadata=True
    )
    
    # Override dataset to just load the frozen mixtures directly
    class FrozenValDataset(torch.utils.data.Dataset):
        def __init__(self, val_dir):
            self.val_dir = val_dir
            with open(os.path.join(val_dir, "manifest.csv"), "r") as f:
                self.manifest = list(csv.DictReader(f))
        def __len__(self):
            return len(self.manifest)
        def __getitem__(self, idx):
            row = self.manifest[idx]
            v_idx = int(row['val_index'])
            clean_path = os.path.join(self.val_dir, "clean_audio", f"{v_idx:04d}_clean.wav")
            noisy_path = os.path.join(self.val_dir, "noisy_audio", f"{v_idx:04d}_noisy.wav")
            c, _ = sf.read(clean_path)
            n, _ = sf.read(noisy_path)
            return torch.tensor(n, dtype=torch.float32), torch.tensor(c, dtype=torch.float32), row
            
    frozen_val_dataset = FrozenValDataset(val_dir)
    train_loader = DataLoader(train_dataset, batch_size=4, shuffle=True, drop_last=True, num_workers=4)
    val_loader = DataLoader(frozen_val_dataset, batch_size=4, shuffle=False)
    
    stft_loss_fn = MultiResolutionSTFTLoss().to(device)
    sisdr_loss_fn = SISDRLoss().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    
    log_f = open(os.path.join(base_dir, "training_log.csv"), "w", newline='')
    log_writer = csv.DictWriter(log_f, fieldnames=["step", "train_loss", "val_total_loss", "val_l1", "val_mrstft", "val_sisdr", "mag_mean", "mag_std", "pct_gt_1", "phase_mean", "phase_std", "speech_corr", "rms_ratio", "nan_inf"])
    log_writer.writeheader()
    
    global_step = 0
    t_loss_sum = 0
    best_val_loss = float('inf')
    best_step = 0
    
    print("Starting training...")
    for batch in train_loader:
        if len(batch) == 3:
            noisy, clean, meta = batch
        else:
            noisy, clean = batch
            
        global_step += 1
        noisy, clean = noisy.to(device), clean.to(device)
        
        optimizer.zero_grad()
        enh, L_out, _, _ = model(noisy)
        tgt = clean[:, :L_out]
        
        l1 = torch.nn.functional.l1_loss(enh, tgt)
        stft = stft_loss_fn(enh, tgt)
        sisdr = sisdr_loss_fn(enh, tgt)
        
        loss = 5.0 * l1 + 5.0 * stft + 1.0 * sisdr
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        optimizer.step()
        
        t_loss_sum += loss.item()
        
        if global_step % 5000 == 0:
            avg_t_loss = t_loss_sum / 5000
            t_loss_sum = 0
            
            torch.save(model.state_dict(), os.path.join(base_dir, f"checkpoint_{global_step}.pt"))
            print(f"Evaluating at step {global_step}...")
            
            diag = compute_diagnostics(model, val_loader, device)
            row = {"step": global_step, "train_loss": avg_t_loss}
            row.update(diag)
            log_writer.writerow(row)
            log_f.flush()
            
            if diag["val_total_loss"] < best_val_loss:
                best_val_loss = diag["val_total_loss"]
                best_step = global_step
                torch.save(model.state_dict(), os.path.join(base_dir, "best.pt"))
                
        if global_step >= 25000:
            break
            
    log_f.close()
    
    print("Evaluating best checkpoint vs V2 baseline...")
    checkpoints = {
        "v2_baseline": "runs/sih26052_polar_v2_25k/best.pt",
        "sisdr_best": os.path.join(base_dir, "best.pt"),
        "sisdr_25k": os.path.join(base_dir, "checkpoint_25000.pt")
    }
    
    with open(os.path.join(val_dir, "manifest.csv"), "r") as f:
        manifest = list(csv.DictReader(f))
        
    tasks = []
    for row in manifest:
        tasks.append((int(row["val_index"]), row["dataset_origin"], val_dir))
        
    per_example_rows = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=12, initializer=worker_init, initargs=(checkpoints,)) as executor:
        for r in executor.map(worker_task, tasks):
            per_example_rows.append(r)
            
    df = pd.DataFrame(per_example_rows)
    df.to_csv(os.path.join(base_dir, "per_example_metrics.csv"), index=False)
    
    # Calc paired stats for sisdr_best vs v2_baseline
    def calc_stats(d1, d2):
        res = {}
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
                f"{metric}_mean_delta": np.mean(delta),
                f"{metric}_median_delta": np.median(delta),
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

    paired_rows = []
    for subset in ["ALL", "IoBT_GUNFIRE", "EXISTING_PROXY"]:
        odf = df if subset == "ALL" else df[df["subset"] == subset]
        if len(odf) == 0: continue
        
        # sisdr_best vs v2_baseline (Positive means sisdr_best is better)
        d1 = {m: odf[f"sisdr_best_output_{m}"] for m in ["snr", "si_sdr", "stoi", "pesq"]}
        d2 = {m: odf[f"v2_baseline_output_{m}"] for m in ["snr", "si_sdr", "stoi", "pesq"]}
        
        stats = calc_stats(d1, d2)
        stats["subset"] = subset
        stats["comparison"] = "sisdr_best_vs_v2_baseline"
        paired_rows.append(stats)
        
    pd.DataFrame(paired_rows).to_csv(os.path.join(base_dir, "paired_statistics.csv"), index=False)
    
    # Check Gold
    gold_hash = "46236aef9af38056e08f296ac8c498dac888a85fb4b1ff9f371879c49670b0c9"
    with open("data/clean_manifests/sih26052_gold_test.csv", "rb") as f:
        curr_hash = hashlib.sha256(f.read()).hexdigest()
    assert curr_hash == gold_hash, "Gold hash mismatch"
    
    # Write report
    with open(os.path.join(base_dir, "report.md"), "w") as f:
        f.write("# SI-SDR Loss Ablation Report\n\n")
        f.write("## 1. Integrity Checks\n")
        f.write(f"- Parameter count: {params}\n")
        f.write(f"- Architecture: StatefulPolarLSTM\n")
        f.write(f"- Canonical Hash: Verified\n")
        f.write(f"- Gold Hash: Verified ({curr_hash})\n\n")
        
        f.write("## 2. Best Checkpoint\n")
        f.write(f"- Best validation step: {best_step}\n")
        f.write(f"- Best validation loss: {best_val_loss}\n\n")
        
        f.write("## 3. Conclusion\n")
        # Logic to determine conclusion
        all_stats = [r for r in paired_rows if r["subset"] == "ALL"][0]
        sdr_imp = all_stats["si_sdr_mean_delta"]
        sdr_p = all_stats["si_sdr_p_val"]
        stoi_imp = all_stats["stoi_mean_delta"]
        
        if sdr_imp > 0.5 and sdr_p < 0.05 and stoi_imp > 0.0:
            conclusion = "SI_SDR_ABLATION_IMPROVED"
        elif sdr_imp < -0.5 and sdr_p < 0.05:
            conclusion = "SI_SDR_ABLATION_REGRESSED"
        else:
            conclusion = "SI_SDR_ABLATION_NO_MEANINGFUL_IMPROVEMENT"
            
        f.write(f"STATUS: {conclusion}\n")

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.set_start_method('spawn')
    main()
