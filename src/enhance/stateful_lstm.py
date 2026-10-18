import torch
import torch.nn as nn
import torch.nn.functional as F

def causal_istft(stft_matrix, n_fft, hop_length, window):
    B, F_bins, T_frames = stft_matrix.shape
    frames = torch.fft.irfft(stft_matrix, n=n_fft, dim=1)
    frames = frames * window.view(1, -1, 1).to(stft_matrix.device)
    
    output_len = (T_frames - 1) * hop_length + n_fft
    frames_fold = frames
    
    output = F.fold(frames_fold, output_size=(1, output_len), kernel_size=(1, n_fft), stride=(1, hop_length))
    output = output.squeeze(1).squeeze(1)
    
    window_sq = window ** 2
    window_sq_exp = window_sq.view(1, -1, 1).repeat(1, 1, T_frames).to(stft_matrix.device)
    env = F.fold(window_sq_exp, output_size=(1, output_len), kernel_size=(1, n_fft), stride=(1, hop_length))
    env = env.squeeze(1).squeeze(1)
    
    env = env.clamp(min=1e-8)
    return output / env

class StatefulComplexLSTM(nn.Module):
    def __init__(self, input_dim=514, hidden_size=256, num_layers=2):
        super(StatefulComplexLSTM, self).__init__()
        self.lstm = nn.LSTM(input_size=input_dim, 
                            hidden_size=hidden_size, 
                            num_layers=num_layers, 
                            batch_first=True, 
                            bidirectional=False)
        self.fc_real = nn.Linear(hidden_size, input_dim // 2)
        self.fc_imag = nn.Linear(hidden_size, input_dim // 2)
        
        self._verify_params()

    def _verify_params(self):
        total_params = sum(p.numel() for p in self.parameters())
        expected_params = 1448962
        if total_params != expected_params:
            raise ValueError(f"CRITICAL ARCHITECTURE MISMATCH: Expected {expected_params} parameters, found {total_params}.")

    def forward(self, features, h_in, c_in):
        out, (h_out, c_out) = self.lstm(features, (h_in, c_in))
        mask_real = self.fc_real(out)
        mask_imag = self.fc_imag(out)
        return mask_real, mask_imag, h_out, c_out

class StatefulComplexLSTM_Wrapper(nn.Module):
    def __init__(self, n_fft=512, hop_length=256, hidden_size=256, num_layers=2):
        super(StatefulComplexLSTM_Wrapper, self).__init__()
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.core = StatefulComplexLSTM(input_dim=514, hidden_size=hidden_size, num_layers=num_layers)
        self.register_buffer('window', torch.hann_window(self.n_fft))

    def forward(self, x):
        stft = torch.stft(x, n_fft=self.n_fft, hop_length=self.hop_length, 
                          window=self.window, return_complex=True, center=False)
        
        stft_t = stft.transpose(1, 2)
        
        real_part = stft_t.real
        imag_part = stft_t.imag
        
        features = torch.cat([real_part, imag_part], dim=-1)
        
        B, T_frames, _ = features.shape
        device = features.device
        
        h_in = torch.zeros(2, B, 256, device=device)
        c_in = torch.zeros(2, B, 256, device=device)
        
        mask_real, mask_imag, h_out, c_out = self.core(features, h_in, c_in)
        
        mask_complex = torch.complex(mask_real, mask_imag)
        mask_complex_t = mask_complex.transpose(1, 2)
        
        enhanced_stft = stft * mask_complex_t
        
        # Calculate expected output length
        expected_length = (T_frames - 1) * self.hop_length + self.n_fft
        
        enhanced_wav = causal_istft(enhanced_stft, self.n_fft, self.hop_length, self.window)
        
        return enhanced_wav, expected_length
