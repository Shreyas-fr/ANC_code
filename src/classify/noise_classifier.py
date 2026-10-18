import torch
import torch.nn as nn

class NoiseClassifier(nn.Module):
    """Small CNN over log-mel spectrograms. Cheap enough to also run on-Pi
    if you want live classification, not just training-time labeling."""
    def __init__(self, n_mels=40, n_classes=3):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(1, 16, 3, padding=1), nn.BatchNorm2d(16), nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(16, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(),
            nn.AdaptiveAvgPool2d(1),
        )
        self.fc = nn.Linear(64, n_classes)

    def forward(self, x):          # x: (B, 1, n_mels, T)
        x = self.conv(x)
        x = x.flatten(1)
        return self.fc(x)          # logits over {stationary, non-stationary, impulsive}
