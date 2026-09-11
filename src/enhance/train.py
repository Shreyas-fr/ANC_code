import os
import argparse
import yaml
import torch
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter
from tqdm import tqdm
import sys

# Add root to sys.path to import scripts
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from scripts.dynamic_mixer import AntigravityDataset
from src.enhance.complex_crn import ComplexCRN_Wrapper
from src.enhance.losses import EnhancementLoss
from src.enhance.evaluate import pesq, stoi, si_sdr
import numpy as np

def train(config):
    device = torch.device(config.get('device', 'cpu'))
    if device.type == 'cuda' and not torch.cuda.is_available():
        print("CUDA not available, falling back to CPU")
        device = torch.device('cpu')
    print(f"Using device: {device}")

    # Dataset
    train_dataset = AntigravityDataset(
        clean_manifest="data/manifests/clean_train.csv",
        noise_manifest="data/manifests/noise_train.csv",
        rir_manifest="data/manifests/rir_train.csv",
        epoch_size=config.get('epoch_size', 5000)
    )
    
    val_dataset = AntigravityDataset(
        clean_manifest="data/manifests/clean_val.csv",
        noise_manifest="data/manifests/noise_val.csv",
        rir_manifest="data/manifests/rir_val.csv",
        epoch_size=config.get('val_size', 500),
        is_val=True
    )

    train_loader = DataLoader(train_dataset, batch_size=config['batch_size'], shuffle=True, num_workers=config.get('num_workers', 0))
    val_loader = DataLoader(val_dataset, batch_size=config['batch_size'], shuffle=False, num_workers=config.get('num_workers', 0))

    model = ComplexCRN_Wrapper().to(device)
    criterion = EnhancementLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=config['learning_rate'])
    
    os.makedirs(config['checkpoint_dir'], exist_ok=True)
    writer = SummaryWriter(log_dir=os.path.join(config['checkpoint_dir'], 'logs'))

    best_val_loss = float('inf')

    # Check for legacy checkpoints to resume
    if os.path.exists(os.path.join(config['checkpoint_dir'], 'latest.pt')):
        print("Resuming from latest.pt")
        state_dict = torch.load(os.path.join(config['checkpoint_dir'], 'latest.pt'), map_location=device)
        new_state_dict = {}
        for k, v in state_dict.items():
            if not k.startswith("core."):
                new_state_dict["core." + k] = v
            else:
                new_state_dict[k] = v
        model.load_state_dict(new_state_dict)

    print("Starting training...")
    for epoch in range(1, config['epochs'] + 1):
        model.train()
        train_loss = 0.0
        
        pbar = tqdm(train_loader, desc=f"Epoch {epoch}/{config['epochs']} [Train]")
        for noisy, clean in pbar:
            noisy, clean = noisy.to(device), clean.to(device)
            
            optimizer.zero_grad()
            enhanced = model(noisy)
            
            loss = criterion(enhanced, clean)
            loss.backward()
            
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            
            train_loss += loss.item()
            pbar.set_postfix({'loss': f"{loss.item():.4f}"})
            
        avg_train_loss = train_loss / len(train_loader)
        
        model.eval()
        val_loss = 0.0
        val_sisdr, val_pesq, val_stoi = [], [], []
        
        with torch.no_grad():
            for noisy, clean in tqdm(val_loader, desc=f"Epoch {epoch}/{config['epochs']} [Val]"):
                noisy, clean = noisy.to(device), clean.to(device)
                enhanced = model(noisy)
                loss = criterion(enhanced, clean)
                val_loss += loss.item()
                
                # Compute objective metrics
                for i in range(noisy.shape[0]):
                    n_i = noisy[i].cpu().numpy()
                    c_i = clean[i].cpu().numpy()
                    e_i = enhanced[i].cpu().numpy()
                    
                    # Filter out perfectly clean anomalies (ESC-50 silent crops)
                    if np.max(np.abs(n_i - c_i)) < 1e-4:
                        continue
                        
                    try:
                        sdr = si_sdr(c_i, e_i)
                        if sdr > 40: continue
                        val_sisdr.append(sdr)
                        
                        c_norm = c_i / (np.max(np.abs(c_i)) + 1e-8)
                        e_norm = e_i / (np.max(np.abs(e_i)) + 1e-8)
                        
                        val_stoi.append(stoi(c_norm, e_norm, 16000, extended=False))
                        val_pesq.append(pesq(16000, c_norm, e_norm, 'wb'))
                    except:
                        pass
                
        avg_val_loss = val_loss / len(val_loader)
        avg_sisdr = np.median(val_sisdr) if val_sisdr else 0.0
        avg_pesq = np.mean(val_pesq) if val_pesq else 0.0
        avg_stoi = np.mean(val_stoi) if val_stoi else 0.0
        
        print(f"Epoch {epoch:02d} | Train Loss: {avg_train_loss:.4f} | Val Loss: {avg_val_loss:.4f} | SI-SDR: {avg_sisdr:.2f} | PESQ: {avg_pesq:.2f} | STOI: {avg_stoi:.2f}")
        
        writer.add_scalar('Loss/Train', avg_train_loss, epoch)
        writer.add_scalar('Loss/Val', avg_val_loss, epoch)
        writer.add_scalar('Metrics/SI-SDR', avg_sisdr, epoch)
        writer.add_scalar('Metrics/PESQ', avg_pesq, epoch)
        writer.add_scalar('Metrics/STOI', avg_stoi, epoch)
        
        torch.save(model.state_dict(), os.path.join(config['checkpoint_dir'], f'epoch_{epoch:03d}.pt'))
        torch.save(model.state_dict(), os.path.join(config['checkpoint_dir'], 'latest.pt'))
        
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            torch.save(model.state_dict(), os.path.join(config['checkpoint_dir'], 'best.pt'))
            print("  --> Saved new best model!")

    writer.close()
    print("Training complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True, help="Path to config file")
    args = parser.parse_args()
    
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)
        
    train(config)
