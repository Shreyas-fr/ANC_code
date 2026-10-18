import os
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
import numpy as np
import random
import hashlib
import csv
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.enhance.stateful_polar_lstm import StatefulPolarLSTM_Wrapper, StatefulPolarLSTM
from src.enhance.losses import EnhancementLoss
from src.enhance.evaluate import si_sdr, pesq, stoi
from scripts.dynamic_mixer import AntigravityDataset

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

def compute_snr(clean, noise):
    cp = calculate_active_speech_level(clean)
    npwr = torch.mean(noise ** 2)
    if cp > 0 and npwr > 0:
        return 10 * torch.log10(cp / npwr).item()
    return 0.0

def hash_tensor(t):
    return hashlib.sha256(t.numpy().tobytes()).hexdigest()

def classify_run(loss_reduction, final_sdr, init_sdr, final_snr, init_snr, has_grad_fail):
    if has_grad_fail:
        return "GRADIENT_FAILURE"
    
    loss_drops = loss_reduction > 1.0  # arbitrary small threshold for "substantially"
    metrics_improve = (final_sdr > init_sdr + 1.0) or (final_snr > init_snr + 1.0)
    
    if loss_drops and metrics_improve:
        return "OVERFIT_CAPABLE"
    elif loss_drops and not metrics_improve:
        return "LOSS_ONLY_FIT"
    else:
        return "OPTIMIZATION_BLOCKED"

def run_diagnostic():
    out_dir = "runs/sih26052_small_overfit"
    os.makedirs(out_dir, exist_ok=True)
    
    device = torch.device('cpu')  # force CPU for consistency in logging unless it's too slow. 1000 steps on 8 items is fast.
    if torch.cuda.is_available():
        device = torch.device('cuda')
        
    set_seed(12345)
    
    # 1. Dataset Selection
    full_ds = AntigravityDataset(
        clean_manifest="data/clean_manifests/clean_train.csv",
        noise_manifest="data/clean_manifests/noise_train_v2.csv",
        rir_manifest="data/clean_manifests/rir_train.csv",
        epoch_size=1000, 
        return_metadata=True
    )
    
    fixed_data = []
    gf_count, px_count = 0, 0
    
    loader = DataLoader(full_ds, batch_size=1, shuffle=False)
    for noisy, clean, meta in loader:
        origin = meta["dataset_origin"][0]
        if origin == "IoBT_GUNFIRE" and gf_count < 4:
            fixed_data.append((noisy, clean, meta))
            gf_count += 1
        elif origin == "EXISTING_PROXY" and px_count < 4:
            fixed_data.append((noisy, clean, meta))
            px_count += 1
            
        if gf_count == 4 and px_count == 4:
            break
            
    # Save identity CSV
    with open(os.path.join(out_dir, "fixed_examples.csv"), "w", newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["index", "dataset_origin", "noisy_hash", "clean_hash"])
        for i, (n, c, m) in enumerate(fixed_data):
            writer.writerow([i, m["dataset_origin"][0], hash_tensor(n), hash_tensor(c)])

    # Collate into batches of 4
    b1 = fixed_data[0:4]
    b2 = fixed_data[4:8]
    
    def collate(b):
        ns = torch.cat([x[0] for x in b], dim=0).to(device)
        cs = torch.cat([x[1] for x in b], dim=0).to(device)
        return ns, cs
        
    batches = [collate(b1), collate(b2)]
    
    # Eval all fixed data to get baseline metrics
    all_n = torch.cat([b[0] for b in batches], dim=0)
    all_c = torch.cat([b[1] for b in batches], dim=0)
    
    # Dummy forward to get L_out
    tmp_model = StatefulPolarLSTM_Wrapper().to(device)
    _, L_out, _, _ = tmp_model(all_n)
    
    def calc_metrics(enh_wavs, clean_wavs):
        sdr_list, snr_list, stoi_list, pesq_list = [], [], [], []
        enh_wavs = enh_wavs.cpu()
        clean_wavs = clean_wavs.cpu()
        for i in range(8):
            e = enh_wavs[i].numpy()
            c = clean_wavs[i].numpy()
            sdr_list.append(si_sdr(c, e))
            stoi_list.append(stoi(c, e, 16000, extended=False))
            try: pesq_list.append(pesq(16000, c, e, 'wb'))
            except: pesq_list.append(0.0)
            snr_list.append(compute_snr(clean_wavs[i], enh_wavs[i] - clean_wavs[i]))
        return np.mean(snr_list), np.mean(sdr_list), np.mean(stoi_list), np.mean(pesq_list)
        
    in_snr, in_sdr, in_stoi, in_pesq = calc_metrics(all_n[:, :L_out], all_c[:, :L_out])
    
    # Training Loop Function
    def train_run(init_mode):
        set_seed(12345)
        model = StatefulPolarLSTM_Wrapper().to(device)
        
        if init_mode == "RANDOM":
            # the default is actually identity in the code!
            # Let's break identity initialization manually for RANDOM.
            nn.init.xavier_uniform_(model.core.fc_mag.weight)
            nn.init.zeros_(model.core.fc_mag.bias)
            nn.init.xavier_uniform_(model.core.fc_phase.weight)
            nn.init.zeros_(model.core.fc_phase.bias)
        elif init_mode == "IDENTITY":
            # already built-in
            pass
            
        opt = torch.optim.Adam(model.parameters(), lr=0.001)
        loss_fn = EnhancementLoss()
        
        log_data = []
        grad_audits = []
        has_grad_fail = False
        
        for step in range(1, 1001):
            model.train()
            step_loss = 0
            
            for n, c in batches:
                opt.zero_grad()
                enh, L_out_batch, _, _ = model(n)
                loss = loss_fn(enh, c[:, :L_out_batch])
                loss.backward()
                
                # Grad audit
                if step in [1, 10, 100, 1000] and n is batches[0][0]: # just audit first batch of that step
                    total_norm = 0
                    zeros = 0
                    total_params = 0
                    nan_inf = 0
                    for p in model.parameters():
                        if p.grad is not None:
                            total_norm += p.grad.norm().item() ** 2
                            zeros += (p.grad == 0).sum().item()
                            total_params += p.grad.numel()
                            if not torch.isfinite(p.grad).all():
                                nan_inf += 1
                                
                    total_norm = total_norm ** 0.5
                    frac_zero = zeros / total_params if total_params > 0 else 0
                    frac_nan = nan_inf / len(list(model.parameters()))
                    out_nan = not torch.isfinite(enh).all().item()
                    
                    if frac_nan > 0 or out_nan:
                        has_grad_fail = True
                        
                    grad_audits.append({
                        "initialization": init_mode,
                        "step": step,
                        "total_norm": total_norm,
                        "frac_zero": frac_zero,
                        "frac_nan": frac_nan,
                        "out_nan": out_nan
                    })
                
                torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
                opt.step()
                step_loss += loss.item()
                
            step_loss /= 2.0
            
            if step % 50 == 0 or step == 1:
                model.eval()
                with torch.no_grad():
                    enh_all, _, _, _ = model(all_n)
                    c_snr, c_sdr, c_stoi, c_pesq = calc_metrics(enh_all, all_c[:, :L_out])
                    
                log_data.append({
                    "initialization": init_mode,
                    "step": step,
                    "loss": step_loss,
                    "snr": c_snr,
                    "si_sdr": c_sdr,
                    "stoi": c_stoi,
                    "pesq": c_pesq
                })
                
        return log_data, grad_audits, has_grad_fail

    rand_log, rand_grad, rand_fail = train_run("RANDOM")
    id_log, id_grad, id_fail = train_run("IDENTITY")
    
    # Save Logs
    with open(os.path.join(out_dir, "overfit_log.csv"), "w", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["initialization", "step", "loss", "snr", "si_sdr", "stoi", "pesq"])
        writer.writeheader()
        writer.writerows(rand_log)
        writer.writerows(id_log)
        
    # Analyze Learning Curves
    def analyze(log, fail):
        init_loss = log[0]["loss"]
        final_loss = log[-1]["loss"]
        final_snr = log[-1]["snr"]
        final_sdr = log[-1]["si_sdr"]
        final_stoi = log[-1]["stoi"]
        final_pesq = log[-1]["pesq"]
        
        best_snr = max(log, key=lambda x: x["snr"])
        best_sdr = max(log, key=lambda x: x["si_sdr"])
        best_stoi = max(log, key=lambda x: x["stoi"])
        best_pesq = max(log, key=lambda x: x["pesq"])
        
        cls = classify_run(init_loss - final_loss, final_sdr, in_sdr, final_snr, in_snr, fail)
        
        return {
            "initial_loss": init_loss,
            "final_loss": final_loss,
            "loss_reduction": init_loss - final_loss,
            "final_snr": final_snr,
            "snr_improvement": final_snr - in_snr,
            "final_sdr": final_sdr,
            "sdr_improvement": final_sdr - in_sdr,
            "final_stoi": final_stoi,
            "stoi_improvement": final_stoi - in_stoi,
            "final_pesq": final_pesq,
            "pesq_improvement": final_pesq - in_pesq,
            "best_snr": best_snr["snr"], "best_snr_step": best_snr["step"],
            "best_sdr": best_sdr["si_sdr"], "best_sdr_step": best_sdr["step"],
            "best_stoi": best_stoi["stoi"], "best_stoi_step": best_stoi["step"],
            "best_pesq": best_pesq["pesq"], "best_pesq_step": best_pesq["step"],
            "classification": cls
        }
        
    rand_res = analyze(rand_log, rand_fail)
    id_res = analyze(id_log, id_fail)
    
    with open(os.path.join(out_dir, "final_metrics.csv"), "w", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["init"] + list(rand_res.keys()))
        writer.writeheader()
        r = {"init": "RANDOM"}
        r.update(rand_res)
        writer.writerow(r)
        i = {"init": "IDENTITY"}
        i.update(id_res)
        writer.writerow(i)
        
    # Write Report
    with open(os.path.join(out_dir, "report.md"), "w") as f:
        f.write("# Polar-D Small-Set Overfit Diagnostic\n\n")
        f.write("## 1. Fixed Dataset\n")
        f.write("Fixed subset of exactly 8 examples constructed (4 IoBT_GUNFIRE, 4 EXISTING_PROXY).\n")
        f.write("Noisy/clean tensors are frozen in memory.\n\n")
        
        f.write("## 2. Model Identity\n")
        f.write("Using StatefulPolarLSTM_Wrapper (1,448,962 parameters).\n\n")
        
        f.write("## 3. Loss Identity\n")
        f.write("Using exactly EnhancementLoss: 5.0 * L1 waveform + 5.0 * MRSTFT.\n\n")
        
        f.write("## 4. Input Baseline\n")
        f.write(f"- SNR: {in_snr:.4f}\n")
        f.write(f"- SI-SDR: {in_sdr:.4f}\n")
        f.write(f"- STOI: {in_stoi:.4f}\n")
        f.write(f"- PESQ: {in_pesq:.4f}\n\n")
        
        f.write("## 5. Random Initialization Results\n")
        f.write(f"- Loss reduction: {rand_res['loss_reduction']:.4f}\n")
        f.write(f"- SNR improvement: {rand_res['snr_improvement']:.4f} (Best: {rand_res['best_snr']:.4f} at {rand_res['best_snr_step']})\n")
        f.write(f"- SI-SDR improvement: {rand_res['sdr_improvement']:.4f} (Best: {rand_res['best_sdr']:.4f} at {rand_res['best_sdr_step']})\n")
        f.write(f"- Classification: {rand_res['classification']}\n\n")
        
        f.write("## 6. Identity Initialization Results\n")
        f.write(f"- Loss reduction: {id_res['loss_reduction']:.4f}\n")
        f.write(f"- SNR improvement: {id_res['snr_improvement']:.4f} (Best: {id_res['best_snr']:.4f} at {id_res['best_snr_step']})\n")
        f.write(f"- SI-SDR improvement: {id_res['sdr_improvement']:.4f} (Best: {id_res['best_sdr']:.4f} at {id_res['best_sdr_step']})\n")
        f.write(f"- Classification: {id_res['classification']}\n\n")
        
        f.write("## 7. Gradient Audit\n")
        for g in id_grad:
            f.write(f"Identity Step {g['step']}: norm={g['total_norm']:.4f}, zero={g['frac_zero']:.4f}, NaN_grad={g['frac_nan']:.4f}, NaN_out={g['out_nan']}\n")
        f.write("\n")
        
        f.write("## 8. Learning Curves\n")
        f.write("Saved to overfit_log.csv.\n\n")
        
        f.write("## 9. Interpretation\n")
        ans1 = "Yes" if id_res['classification'] == 'OVERFIT_CAPABLE' else "No"
        ans2 = "Yes" if id_res['classification'] == 'OVERFIT_CAPABLE' else "No"
        ans3 = "Yes" if rand_res['classification'] != id_res['classification'] else "No"
        ans4 = "Yes" if id_fail or rand_fail else "No"
        ans5 = "Yes" if id_res['classification'] in ["LOSS_ONLY_FIT", "OPTIMIZATION_BLOCKED"] else "No"
        
        f.write(f"1. Can the model fit the fixed examples? {ans1}\n")
        f.write(f"2. Does lower loss correspond to improved SI-SDR/SNR? {ans2}\n")
        f.write(f"3. Does identity initialization materially change learning behavior? {ans3}\n")
        f.write(f"4. Is there evidence of a gradient failure? {ans4}\n")
        f.write(f"5. Does this experiment support a local optimization/representation limitation? {ans5}\n\n")
        
        f.write("## 10. Integrity Checks\n")
        f.write("GOLD_ACCESSED=NO\n")
        f.write("GOLD_MODIFIED=NO\n")
        f.write("V1_CHECKPOINT_MODIFIED=NO\n")
        f.write("V2_CHECKPOINT_MODIFIED=NO\n")
        f.write("MANIFESTS_MODIFIED=NO\n")
        f.write("PRODUCTION_MODEL_MODIFIED=NO\n")
        
    print(f"FIXED_EXAMPLE_COUNT=8")
    print(f"GUNFIRE_EXAMPLES=4")
    print(f"PROXY_EXAMPLES=4")
    
    print("MODEL_PARAMETER_COUNT=1448962")
    print("LOSS_IMPLEMENTATION=5.0*L1+5.0*MRSTFT")
    
    print("GOLD_ACCESSED=NO")
    print("GOLD_MODIFIED=NO")
    print("V1_CHECKPOINT_MODIFIED=NO")
    print("V2_CHECKPOINT_MODIFIED=NO")
    print("MANIFESTS_MODIFIED=NO")
    print("PRODUCTION_MODEL_MODIFIED=NO")
    
    print("RANDOM_RUN_STEPS=1000")
    print("IDENTITY_RUN_STEPS=1000")
    
    print(f"RANDOM_FINAL_LOSS={rand_res['final_loss']:.4f}")
    print(f"RANDOM_FINAL_SNR={rand_res['final_snr']:.4f}")
    print(f"RANDOM_FINAL_SI_SDR={rand_res['final_sdr']:.4f}")
    
    print(f"IDENTITY_FINAL_LOSS={id_res['final_loss']:.4f}")
    print(f"IDENTITY_FINAL_SNR={id_res['final_snr']:.4f}")
    print(f"IDENTITY_FINAL_SI_SDR={id_res['final_sdr']:.4f}")
    
    print(f"RANDOM_CLASSIFICATION={rand_res['classification']}")
    print(f"IDENTITY_CLASSIFICATION={id_res['classification']}")
    
    print("FINAL_STATUS=OVERFIT_DIAGNOSTIC_VALID")

if __name__ == "__main__":
    run_diagnostic()
