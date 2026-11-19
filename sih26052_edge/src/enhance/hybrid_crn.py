import torch
import torch.nn as nn
import torch.nn.functional as F

class WaveUNetBranch(nn.Module):
    """
    Time-domain 1D Convolutional branch for transient and impulsive noise suppression.
    Operates directly on the raw audio waveform to avoid STFT smearing.
    """
    def __init__(self, channels=2):
        super(WaveUNetBranch, self).__init__()
        # Downsampling path
        self.conv1 = nn.Conv1d(channels, 16, kernel_size=15, stride=1, padding=7)
        self.conv2 = nn.Conv1d(16, 32, kernel_size=15, stride=2, padding=7)
        
        # Upsampling path
        self.upconv = nn.ConvTranspose1d(32, 16, kernel_size=15, stride=2, padding=7, output_padding=1)
        self.final_conv = nn.Conv1d(32, 1, kernel_size=1, stride=1) # 32 because of skip connection (16 + 16)

    def forward(self, x):
        # x: [B, C=2, T]
        c1 = F.leaky_relu(self.conv1(x), 0.2)
        c2 = F.leaky_relu(self.conv2(c1), 0.2)
        
        u1 = F.leaky_relu(self.upconv(c2), 0.2)
        
        # Skip connection
        u1_concat = torch.cat([u1, c1], dim=1)
        
        out_time = torch.tanh(self.final_conv(u1_concat))
        return out_time # [B, 1, T]


class SpatialCRNBranch(nn.Module):
    """
    Frequency-domain branch utilizing Spatial Processing (Dual Mic).
    Takes magnitudes and Inter-channel Phase Differences (IPD).
    """
    def __init__(self, n_fft=512, hidden_size=128, num_layers=2):
        super(SpatialCRNBranch, self).__init__()
        self.freq_bins = (n_fft // 2) + 1
        # Inputs: Mag(Ch1), Mag(Ch2), Cos(IPD), Sin(IPD) -> 4 features per bin
        self.input_dim = self.freq_bins * 4 
        
        self.lstm = nn.LSTM(input_size=self.input_dim, 
                            hidden_size=hidden_size, 
                            num_layers=num_layers, 
                            batch_first=True, 
                            bidirectional=False)
                            
        self.fc_real = nn.Linear(hidden_size, self.freq_bins)
        self.fc_imag = nn.Linear(hidden_size, self.freq_bins)

    def forward(self, mag1, mag2, phase1, phase2):
        # IPD calculation
        ipd = phase1 - phase2
        cos_ipd = torch.cos(ipd)
        sin_ipd = torch.sin(ipd)
        
        # Stack spatial features: [B, F, T, 4]
        spatial_features = torch.stack([mag1, mag2, cos_ipd, sin_ipd], dim=-1)
        
        B, F, T, C = spatial_features.shape
        # Flatten spatial features per frequency bin: [B, T, F*4]
        features = spatial_features.permute(0, 2, 1, 3).reshape(B, T, F * C)
        
        out, _ = self.lstm(features)
        
        mask_real = torch.tanh(self.fc_real(out)).transpose(1, 2) # [B, F, T]
        mask_imag = torch.tanh(self.fc_imag(out)).transpose(1, 2)
        
        return mask_real, mask_imag


class HybridSpatialCRN(nn.Module):
    """
    Phase 2 Prototype Architecture for SIH26052.
    Combines Option 2 (Time-Domain Wave-U-Net) and Option 3 (Dual-Mic Spatial Processing).
    """
    def __init__(self, n_fft=512, hop_length=256, hidden_size=128):
        super(HybridSpatialCRN, self).__init__()
        self.n_fft = n_fft
        self.hop_length = hop_length
        
        # Branch 1: Time Domain (Transients & Impulses)
        self.wave_unet = WaveUNetBranch(channels=2)
        
        # Branch 2: Spatial Frequency Domain (Stationary / Background Noise)
        self.spatial_crn = SpatialCRNBranch(n_fft=n_fft, hidden_size=hidden_size)
        
        # Fusion layer to intelligently blend the outputs of both domains
        self.fusion_weight = nn.Parameter(torch.tensor([0.5])) 

    def forward(self, x):
        # x is stereo audio [B, 2, T]
        B, C, T = x.shape
        window = torch.hann_window(self.n_fft).to(x.device)
        
        # --- PATH 1: Time Domain (Fast Transient Detection) ---
        time_domain_enh = self.wave_unet(x).squeeze(1) # [B, T]
        
        # --- PATH 2: Spatial Frequency Domain ---
        # Compute STFT for both channels
        stft1 = torch.stft(x[:, 0, :], n_fft=self.n_fft, hop_length=self.hop_length, window=window, return_complex=True)
        stft2 = torch.stft(x[:, 1, :], n_fft=self.n_fft, hop_length=self.hop_length, window=window, return_complex=True)
        
        mag1, phase1 = torch.abs(stft1), torch.angle(stft1)
        mag2, phase2 = torch.abs(stft2), torch.angle(stft2)
        
        # Predict spatial complex mask based on both mics
        mask_real, mask_imag = self.spatial_crn(mag1, mag2, phase1, phase2)
        mask_complex = torch.complex(mask_real, mask_imag)
        
        # Apply mask to primary channel (Mic 1)
        enhanced_stft = stft1 * mask_complex
        freq_domain_enh = torch.istft(enhanced_stft, n_fft=self.n_fft, hop_length=self.hop_length, window=window, length=T)
        
        # --- PATH 3: Fusion ---
        # Blend the slow-spectral enhancement with the fast-transient enhancement
        w = torch.sigmoid(self.fusion_weight)
        final_output = (w * freq_domain_enh) + ((1 - w) * time_domain_enh)
        
        return final_output

if __name__ == "__main__":
    model = HybridSpatialCRN()
    dummy_input = torch.randn(4, 2, 16000) # 4 batches, 2 channels, 1 second of audio
    output = model(dummy_input)
    print(f"Input shape: {dummy_input.shape} (Dual Mic Stereo)")
    print(f"Output shape: {output.shape} (Cleaned Mono)")
    print("Hybrid Spatial CRN Initialized Successfully.")
