import torch
import torch.nn as nn

class ComplexCRN(nn.Module):
    """
    Complex Ratio Masking (cRM) Convolutional Recurrent Network for Antigravity V1.1.
    Operates in the complex domain to preserve and reconstruct phase information.
    Optimized footprint for Raspberry Pi real-time inference (RTF < 1).
    """
    def __init__(self, n_fft=512, hop_length=256, hidden_size=128, num_layers=2):
        super(ComplexCRN, self).__init__()
        self.n_fft = n_fft
        self.hop_length = hop_length
        
        self.input_dim = (n_fft // 2) + 1
        
        # We use a single, lightweight LSTM block to process the magnitude 
        # (Could be modified to take complex STFT as well, but magnitude is standard for stable CRNs)
        self.lstm = nn.LSTM(input_size=self.input_dim, 
                            hidden_size=hidden_size, 
                            num_layers=num_layers, 
                            batch_first=True, 
                            bidirectional=False)
                            
        # The key to phase-awareness: predicting both real and imaginary masks
        self.fc_real = nn.Linear(hidden_size, self.input_dim)
        self.fc_imag = nn.Linear(hidden_size, self.input_dim)

    def forward(self, x):
        # x: [B, T]
        window = torch.hann_window(self.n_fft).to(x.device)
        
        stft = torch.stft(x, n_fft=self.n_fft, hop_length=self.hop_length, 
                          window=window, return_complex=True, center=True)
        # stft: [B, F, T]
        
        mag = torch.abs(stft)
        mag_t = mag.transpose(1, 2) # [B, T, F]
        
        out, _ = self.lstm(mag_t)
        
        # Predict unbounded complex mask (often passed through tanh for stability)
        mask_real = torch.tanh(self.fc_real(out)).transpose(1, 2) # [B, F, T]
        mask_imag = torch.tanh(self.fc_imag(out)).transpose(1, 2)
        
        mask_complex = torch.complex(mask_real, mask_imag)
        
        # Directly multiply complex STFT with complex mask (Modifies both amplitude AND phase)
        enhanced_stft = stft * mask_complex
        
        enhanced_wav = torch.istft(enhanced_stft, n_fft=self.n_fft, hop_length=self.hop_length, 
                                   window=window, length=x.shape[-1])
        
        return enhanced_wav
