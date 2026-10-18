import os
import csv
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import numpy as np

# We'll import our feature extractor and model
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
from src.data.features import extract_features
from src.classify.noise_classifier import NoiseClassifier

class NoiseDataset(Dataset):
    def __init__(self, manifest_path, processed_dir, split="train", max_frames=128):
        self.samples = []
        self.max_frames = max_frames
        self.label_map = {"stationary": 0, "nonstationary": 1, "impulsive": 2}
        
        with open(manifest_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if row["split"] == split:
                    # Reconstruct the expected filename from the mix_noisy_clean.py naming convention
                    clean_name = os.path.splitext(os.path.basename(row["clean_path"]))[0]
                    noise_name = os.path.splitext(os.path.basename(row["noise_path"]))[0]
                    category = row["category"]
                    snr_db = float(row["snr_db"])
                    
                    if category not in self.label_map:
                        continue # ignore unknown
                        
                    out_basename = f"{i:04d}_{category}_{clean_name}_{noise_name}_{int(snr_db)}dB_noisy.wav"
                    file_path = os.path.join(processed_dir, out_basename)
                    
                    if os.path.exists(file_path):
                        self.samples.append((file_path, self.label_map[category]))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        file_path, label = self.samples[idx]
        import librosa
        wav, _ = librosa.load(file_path, sr=16000)
        
        # Extract features
        log_mag, _ = extract_features(wav, sr=16000) # log_mag is (n_mels/bins, T)
        
        # Ensure fixed length for batching (truncate or pad)
        if log_mag.shape[1] > self.max_frames:
            # Random crop
            start = np.random.randint(0, log_mag.shape[1] - self.max_frames)
            log_mag = log_mag[:, start:start+self.max_frames]
        else:
            # Pad
            pad_width = self.max_frames - log_mag.shape[1]
            log_mag = np.pad(log_mag, ((0, 0), (0, pad_width)), mode='constant')
            
        # The model expects (C, H, W) -> (1, bins, T)
        x = torch.tensor(log_mag, dtype=torch.float32).unsqueeze(0)
        y = torch.tensor(label, dtype=torch.long)
        return x, y

def train():
    manifest_path = "data/manifests/classifier_train.csv"
    processed_dir = "data/classifier_processed"
    
    print("Loading datasets...")
    train_ds = NoiseDataset(manifest_path, processed_dir, split="train")
    val_ds = NoiseDataset(manifest_path, processed_dir, split="val")
    
    if len(train_ds) == 0:
        print("No training data found. Make sure the data pipeline finished mixing!")
        return

    train_loader = DataLoader(train_ds, batch_size=4, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=4, shuffle=False)

    model = NoiseClassifier(n_mels=201, n_classes=3) # n_fft=400 -> 201 bins
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=1e-3)
    
    epochs = 20
    print(f"Starting training for {epochs} epochs...")
    for epoch in range(epochs):
        model.train()
        total_loss = 0
        correct = 0
        total = 0
        for x, y in train_loader:
            optimizer.zero_grad()
            logits = model(x)
            loss = criterion(logits, y)
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item()
            preds = torch.argmax(logits, dim=1)
            correct += (preds == y).sum().item()
            total += y.size(0)
            
        train_acc = correct / total if total > 0 else 0
        
        model.eval()
        val_correct = 0
        val_total = 0
        with torch.no_grad():
            for x, y in val_loader:
                logits = model(x)
                preds = torch.argmax(logits, dim=1)
                val_correct += (preds == y).sum().item()
                val_total += y.size(0)
                
        val_acc = val_correct / val_total if val_total > 0 else 0
        
        print(f"Epoch {epoch+1}/{epochs} | Loss: {total_loss/len(train_loader):.4f} | Train Acc: {train_acc:.4f} | Val Acc: {val_acc:.4f}")

if __name__ == "__main__":
    train()
