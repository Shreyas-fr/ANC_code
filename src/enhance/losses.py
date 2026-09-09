import torch
import torch.nn as nn

class MultiResolutionSTFTLoss(nn.Module):
    def __init__(self, fft_sizes=[512, 1024, 2048], hop_sizes=[120, 240, 480], win_lengths=[240, 480, 960]):
        super().__init__()
        self.fft_sizes = fft_sizes
        self.hop_sizes = hop_sizes
        self.win_lengths = win_lengths

    def stft_loss(self, x_mag, y_mag):
        # Spectral Convergence
        sc_loss = torch.norm(y_mag - x_mag, p="fro") / (torch.norm(y_mag, p="fro") + 1e-7)
        # Log STFT Magnitude
        log_mag_loss = torch.nn.functional.l1_loss(torch.log(x_mag + 1e-7), torch.log(y_mag + 1e-7))
        return sc_loss + log_mag_loss

    def forward(self, x, y):
        # x is enhanced, y is clean
        loss = 0.0
        for fs, hop, win in zip(self.fft_sizes, self.hop_sizes, self.win_lengths):
            window = torch.hann_window(win).to(x.device)
            # Use padding to avoid size mismatch
            x_stft = torch.stft(x, n_fft=fs, hop_length=hop, win_length=win, window=window, return_complex=True, center=True)
            y_stft = torch.stft(y, n_fft=fs, hop_length=hop, win_length=win, window=window, return_complex=True, center=True)
            
            x_mag = torch.abs(x_stft)
            y_mag = torch.abs(y_stft)
            loss += self.stft_loss(x_mag, y_mag)
            
        return loss / len(self.fft_sizes)

class EnhancementLoss(nn.Module):
    def __init__(self, l1_weight=10.0, stft_weight=1.0):
        super().__init__()
        self.l1_weight = l1_weight
        self.stft_weight = stft_weight
        self.stft_loss = MultiResolutionSTFTLoss()

    def forward(self, enhanced, clean):
        l1_loss = torch.nn.functional.l1_loss(enhanced, clean)
        stft_loss = self.stft_loss(enhanced, clean)
        return self.l1_weight * l1_loss + self.stft_weight * stft_loss
