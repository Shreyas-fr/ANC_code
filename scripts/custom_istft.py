import torch
import torch.nn.functional as F_nn

def causal_istft(stft_matrix, n_fft, hop_length, window):
    # stft_matrix: [B, F, T]
    B, F_bins, T_frames = stft_matrix.shape
    
    # inverse FFT
    frames = torch.fft.irfft(stft_matrix, n=n_fft, dim=1) # [B, n_fft, T_frames]
    
    # apply window
    frames = frames * window.view(1, -1, 1).to(stft_matrix.device)
    
    # overlap-add using fold
    # fold expects [B, C*L, L_out]
    frames_fold = frames # [B, n_fft, T_frames]
    
    output_len = (T_frames - 1) * hop_length + n_fft
    
    output = F_nn.fold(frames_fold, output_size=(1, output_len), kernel_size=(1, n_fft), stride=(1, hop_length))
    output = output.squeeze(1).squeeze(1) # [B, output_len]
    
    # compute overlap-add envelope
    window_sq = window ** 2
    window_sq_exp = window_sq.view(1, -1, 1).repeat(1, 1, T_frames).to(stft_matrix.device)
    env = F_nn.fold(window_sq_exp, output_size=(1, output_len), kernel_size=(1, n_fft), stride=(1, hop_length))
    env = env.squeeze(1).squeeze(1)
    
    # To avoid division by zero, clamp env
    env = env.clamp(min=1e-8)
    
    return output / env

x = torch.randn(1, 16000)
stft = torch.stft(x, n_fft=512, hop_length=256, window=torch.hann_window(512), center=False, return_complex=True)
y = causal_istft(stft, 512, 256, torch.hann_window(512))
diff = torch.abs(x[:, 512:-512] - y[:, 512:-512]).max()
print(f"Diff: {diff}")
