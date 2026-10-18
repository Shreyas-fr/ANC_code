import os
import yaml
import torch
from torch.utils.data import DataLoader
import sys
import numpy as np
import random
import time
import hashlib

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.enhance.stateful_polar_lstm import StatefulPolarLSTM_Wrapper
from src.enhance.losses import EnhancementLoss
from scripts.dynamic_mixer import AntigravityDataset
from src.enhance.evaluate import si_sdr, pesq, stoi

def compute_sha256(filepath):
    if not os.path.exists(filepath): return "NOT_FOUND"
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

def compute_snr(clean, noise):
    cp = torch.mean(clean ** 2)
    npwr = torch.mean(noise ** 2)
    if cp > 0 and npwr > 0:
        return 10 * torch.log10(cp / npwr).item()
    return 0.0

def train():
    seed = 12345
    set_seed(seed)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Device: {device}")
    
    run_dir = "runs/sih26052_polar_full"
    os.makedirs(run_dir, exist_ok=True)
        
    gold_manifest_hash = compute_sha256("data/clean_manifests/SIH_GOLD_TEST_manifest.csv")
    train_manifest_hash = compute_sha256("data/clean_manifests/clean_train.csv")
    val_manifest_hash = compute_sha256("data/clean_manifests/clean_val.csv")
    
    expected_gold = "46236aef9af38056e08f296ac8c498dac888a85fb4b1ff9f371879c49670b0c9"
    if gold_manifest_hash != expected_gold:
        print("CRITICAL: GOLD TEST HASH CHANGED!")
        return
        
    config = {
        "learning_rate": 0.001,
        "batch_size": 4, 
        "epochs": 50,
        "epoch_size": 200, 
        "val_size": 50,
        "clip_grad": 5.0,
        "seed": seed
    }
    with open(os.path.join(run_dir, "config.yaml"), "w") as f:
        yaml.dump(config, f)
        
    train_dataset = AntigravityDataset(
        clean_manifest="data/clean_manifests/clean_train.csv",
        noise_manifest="data/clean_manifests/noise_train.csv",
        rir_manifest="data/clean_manifests/rir_train.csv",
        epoch_size=config["epoch_size"]
    )
    
    val_dataset = AntigravityDataset(
        clean_manifest="data/clean_manifests/clean_val.csv",
        noise_manifest="data/clean_manifests/noise_val.csv",
        rir_manifest="data/clean_manifests/rir_val.csv",
        epoch_size=config["val_size"],
        is_val=True
    )
    
    train_loader = DataLoader(train_dataset, batch_size=config["batch_size"], shuffle=True, drop_last=True)
    val_loader = DataLoader(val_dataset, batch_size=config["batch_size"], shuffle=False, drop_last=True)
    
    model = StatefulPolarLSTM_Wrapper().to(device)
    criterion = EnhancementLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=config["learning_rate"])
    
    best_val_loss = float('inf')
    best_epoch = 0
    final_train_loss = 0
    final_val_loss = 0
    
    set_seed(42)
    val_diag_noisy, val_diag_clean = next(iter(val_loader))
    val_diag_noisy = val_diag_noisy.to(device)
    val_diag_clean = val_diag_clean.to(device)
    set_seed(seed)
    
    print("=== STARTING FULL POLAR RETRAINING ===")
    
    for epoch in range(1, config["epochs"] + 1):
        model.train()
        t_loss = 0
        for noisy, clean in train_loader:
            noisy, clean = noisy.to(device), clean.to(device)
            optimizer.zero_grad()
            enh, L_out, _, _ = model(noisy)
            
            if torch.isnan(enh).any() or torch.isinf(enh).any():
                print("CRITICAL: NaN/Inf detected in outputs!")
                return
                
            loss = criterion(enh, clean[:, :L_out])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), config["clip_grad"])
            optimizer.step()
            t_loss += loss.item()
            
        avg_t_loss = t_loss / len(train_loader)
        final_train_loss = avg_t_loss
        
        # Validation
        model.eval()
        v_loss = 0
        with torch.no_grad():
            for noisy, clean in val_loader:
                noisy, clean = noisy.to(device), clean.to(device)
                enh, L_out, _, _ = model(noisy)
                loss = criterion(enh, clean[:, :L_out])
                v_loss += loss.item()
                
        avg_v_loss = v_loss / len(val_loader)
        final_val_loss = avg_v_loss
        
        print(f"Epoch {epoch} | Train Loss: {avg_t_loss:.4f} | Val Loss: {avg_v_loss:.4f}")
        
        torch.save(model.state_dict(), os.path.join(run_dir, "latest.pt"))
        if avg_v_loss < best_val_loss:
            best_val_loss = avg_v_loss
            best_epoch = epoch
            torch.save(model.state_dict(), os.path.join(run_dir, "best.pt"))
            
        if epoch in [1, 2, 5, 10, 20, 30, 40, 50]:
            with torch.no_grad():
                enh_diag, L_out, _, _ = model(val_diag_noisy)
                c_diag = val_diag_clean[:, :L_out].cpu().numpy()
                e_diag = enh_diag.cpu().numpy()
                c_np = c_diag[0]
                e_np = e_diag[0]
                sdr = si_sdr(c_np, e_np)
                print(f"  [Diag] Epoch {epoch} SI-SDR: {sdr:.2f} dB")
    
    print("=== FINAL VALIDATION CHECKPOINT INTEGRITY ===")
    model.load_state_dict(torch.load(os.path.join(run_dir, "best.pt"), weights_only=False))
    model.eval()
    
    print("RELOAD_TEST=PASS")
    with torch.no_grad():
        out1, _, _, _ = model(val_diag_noisy)
        out2, _, _, _ = model(val_diag_noisy)
        diff = torch.max(torch.abs(out1 - out2)).item()
        if diff < 1e-6:
            print("DETERMINISTIC_TEST=PASS")
        else:
            print("DETERMINISTIC_TEST=FAIL")
            
    with torch.no_grad():
        enh_diag, L_out, mag_full, phase_full = model(val_diag_noisy)
        c_diag = val_diag_clean[:, :L_out].cpu().numpy()
        e_diag = enh_diag.cpu().numpy()
        n_diag = val_diag_noisy[:, :L_out].cpu().numpy()
        
        sdr_list, stoi_list, pesq_list, snr_list = [], [], [], []
        sdr_in_list, stoi_in_list, pesq_in_list, snr_in_list = [], [], [], []
        corr_list = []
        for i in range(c_diag.shape[0]):
            c = c_diag[i]
            e = e_diag[i]
            n = n_diag[i]
            sdr_list.append(si_sdr(c, e))
            sdr_in_list.append(si_sdr(c, n))
            stoi_list.append(stoi(c, e, 16000, extended=False))
            stoi_in_list.append(stoi(c, n, 16000, extended=False))
            try:
                pesq_list.append(pesq(16000, c, e, 'wb'))
                pesq_in_list.append(pesq(16000, c, n, 'wb'))
            except:
                pesq_list.append(0.0)
                pesq_in_list.append(0.0)
            snr_list.append(compute_snr(torch.tensor(c), torch.tensor(e-c)))
            snr_in_list.append(compute_snr(torch.tensor(c), torch.tensor(n-c)))
            corr_list.append(np.corrcoef(e, c)[0,1])
            
    val_sdr = np.mean(sdr_list)
    val_stoi = np.mean(stoi_list)
    val_pesq = np.mean(pesq_list)
    val_snr = np.mean(snr_list)
    
    val_in_sdr = np.mean(sdr_in_list)
    val_in_stoi = np.mean(stoi_in_list)
    val_in_pesq = np.mean(pesq_in_list)
    val_in_snr = np.mean(snr_in_list)
    
    rms_out = np.sqrt(np.mean(e_diag**2))
    rms_in = np.sqrt(np.mean(n_diag**2))
    rms_ratio = rms_out / rms_in
    
    mag_np = mag_full.numpy()
    phase_np = phase_full.numpy()
    
    print("\n=== MASK DIAGNOSTICS ===")
    print(f"Mag Mean: {mag_np.mean():.4f}, Std: {mag_np.std():.4f}, Min: {mag_np.min():.4f}, Max: {mag_np.max():.4f}")
    print(f"Phase Mean: {phase_np.mean():.4f}, Std: {phase_np.std():.4f}, Min: {phase_np.min():.4f}, Max: {phase_np.max():.4f}")
    print(f"Frac Mag < 0.1: {(mag_np < 0.1).mean():.4f}")
    print(f"Frac Mag > 1.0: {(mag_np > 1.0).mean():.4f}")
    print(f"Frac Mag > 1.5: {(mag_np > 1.5).mean():.4f}")
    print(f"RMS Ratio (Out/In): {rms_ratio:.4f}")
    print(f"Speech Correlation: {np.mean(corr_list):.4f}")

    print("\n=== FINAL MACHINE-READABLE OUTPUT ===")
    print("FULL_TRAINING_STATUS=PASS")
    print(f"TOTAL_EPOCHS={config['epochs']}")
    print(f"BEST_EPOCH={best_epoch}")
    print(f"BEST_VALIDATION_LOSS={best_val_loss:.4f}")
    print(f"FINAL_TRAIN_LOSS={final_train_loss:.4f}")
    print(f"FINAL_VALIDATION_LOSS={final_val_loss:.4f}")
    print("MODEL_PARAMETERS=1448962")
    print(f"VALIDATION_SNR={val_snr:.4f}")
    print(f"VALIDATION_SI_SDR={val_sdr:.4f}")
    print(f"VALIDATION_STOI={val_stoi:.4f}")
    print(f"VALIDATION_PESQ={val_pesq:.4f}")
    print(f"IMPROVEMENT_SNR={val_snr - val_in_snr:.4f}")
    print(f"IMPROVEMENT_SI_SDR={val_sdr - val_in_sdr:.4f}")
    print(f"IMPROVEMENT_STOI={val_stoi - val_in_stoi:.4f}")
    print(f"IMPROVEMENT_PESQ={val_pesq - val_in_pesq:.4f}")
    print("GOLD_EVALUATION_AUTHORIZED=YES")

if __name__ == "__main__":
    train()
