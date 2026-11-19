import torch
import torch.nn as nn
import torch.nn.functional as F
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.enhance.stateful_lstm import causal_istft

class StatefulPolarLSTM(nn.Module):
    def __init__(self, input_dim=514, hidden_size=256, num_layers=2):
        super().__init__()
        self.lstm = nn.LSTM(input_size=input_dim, hidden_size=hidden_size, num_layers=num_layers, batch_first=True)
        # We output magnitude and phase parameters separately
        self.fc_mag = nn.Linear(hidden_size, 257)
        self.fc_phase = nn.Linear(hidden_size, 257)
        
        # Identity Stable Initialization
        # mag = sigmoid(raw) * 2.0. We want mag = 1.0 -> sigmoid(raw) = 0.5 -> raw = 0.0
        nn.init.normal_(self.fc_mag.weight, std=1e-4)
        nn.init.zeros_(self.fc_mag.bias)
        
        # phase = tanh(raw) * pi. We want phase = 0.0 -> tanh(raw) = 0.0 -> raw = 0.0
        nn.init.normal_(self.fc_phase.weight, std=1e-4)
        nn.init.zeros_(self.fc_phase.bias)

    def forward(self, x, h_in, c_in):
        out, (h_out, c_out) = self.lstm(x, (h_in, c_in))
        
        raw_mag = self.fc_mag(out)
        raw_phase = self.fc_phase(out)
        
        mag = torch.sigmoid(raw_mag) * 2.0
        phase = torch.tanh(raw_phase) * torch.pi
        
        mr = mag * torch.cos(phase)
        mi = mag * torch.sin(phase)
        
        return mr, mi, h_out, c_out, mag, phase

class StatefulPolarLSTM_Wrapper(nn.Module):
    def __init__(self):
        super().__init__()
        self.n_fft = 512
        self.hop_length = 256
        self.register_buffer("window", torch.hann_window(self.n_fft))
        self.core = StatefulPolarLSTM()

    def forward(self, audio, h_in=None, c_in=None):
        B, T = audio.shape
        stft = torch.stft(audio, n_fft=self.n_fft, hop_length=self.hop_length, 
                          window=self.window, return_complex=True, center=False)
        
        features = torch.cat([stft.transpose(1, 2).real, stft.transpose(1, 2).imag], dim=-1)
        T_frames = features.shape[1]
        
        if h_in is None:
            h_in = torch.zeros(2, B, 256, device=audio.device)
            c_in = torch.zeros(2, B, 256, device=audio.device)
            
        mr, mi, h_out, c_out, mag, phase = self.core(features, h_in, c_in)
        
        mask_complex = torch.complex(mr, mi).transpose(1, 2)
        enh_stft = stft * mask_complex
        enh_wav = causal_istft(enh_stft, self.n_fft, self.hop_length, self.window)
        
        expected_len = (T_frames - 1) * self.hop_length + self.n_fft
        return enh_wav, expected_len, mag, phase
