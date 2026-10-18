import torch
import torch.nn as nn

class ComplexCRN(nn.Module):
    """
    Core Mask Prediction Network.
    Takes STFT magnitude and outputs (mask_real, mask_imag).
    ONNX-friendly and completely stateless w.r.t STFT windows.
    """
    def __init__(self, n_fft=512, hidden_size=128, num_layers=2):
        super(ComplexCRN, self).__init__()
        self.input_dim = (n_fft // 2) + 1
        
        self.lstm = nn.LSTM(input_size=self.input_dim, 
                            hidden_size=hidden_size, 
                            num_layers=num_layers, 
                            batch_first=True, 
                            bidirectional=False)
                            
        self.fc_real = nn.Linear(hidden_size, self.input_dim)
        self.fc_imag = nn.Linear(hidden_size, self.input_dim)

    def forward(self, mag):
        # mag: [B, F, T]
        mag_t = mag.transpose(1, 2) # [B, T, F]
        out, _ = self.lstm(mag_t)
        
        mask_real = torch.tanh(self.fc_real(out)).transpose(1, 2) # [B, F, T]
        mask_imag = torch.tanh(self.fc_imag(out)).transpose(1, 2)
        
        return mask_real, mask_imag

class ComplexCRN_Wrapper(nn.Module):
    """
    Wrapper for training and bulk evaluation.
    Handles the STFT/ISTFT so the training loop remains unchanged.
    """
    def __init__(self, n_fft=512, hop_length=256, hidden_size=128, num_layers=2):
        super(ComplexCRN_Wrapper, self).__init__()
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.core = ComplexCRN(n_fft=n_fft, hidden_size=hidden_size, num_layers=num_layers)

    def forward(self, x):
        # x: [B, T]
        window = torch.hann_window(self.n_fft).to(x.device)
        
        stft = torch.stft(x, n_fft=self.n_fft, hop_length=self.hop_length, 
                          window=window, return_complex=True, center=True)
        # stft: [B, F, T]
        
        mag = torch.abs(stft)
        
        mask_real, mask_imag = self.core(mag)
        mask_complex = torch.complex(mask_real, mask_imag)
        
        enhanced_stft = stft * mask_complex
        
        enhanced_wav = torch.istft(enhanced_stft, n_fft=self.n_fft, hop_length=self.hop_length, 
                                   window=window, length=x.shape[-1])
        
        return enhanced_wav
