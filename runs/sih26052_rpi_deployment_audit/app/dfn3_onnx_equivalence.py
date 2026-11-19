import sys, types
import torchaudio
if not hasattr(getattr(torchaudio, "backend", None), "common"):
    cm = types.ModuleType("torchaudio.backend.common")
    class AudioMetaData:
        def __init__(self, sr, nf, nc, bps, enc):
            self.sample_rate=sr; self.num_frames=nf
            self.num_channels=nc; self.bits_per_sample=bps; self.encoding=enc
    cm.AudioMetaData = AudioMetaData
    sys.modules["torchaudio.backend.common"] = cm
    if not hasattr(torchaudio, "backend"):
        bm = types.ModuleType("torchaudio.backend")
        bm.common = cm
        sys.modules["torchaudio.backend"] = bm
        torchaudio.backend = bm
    else:
        torchaudio.backend.common = cm

import numpy as np
import torch
import torch.nn.functional as F
import onnxruntime as ort
import os

from df.enhance import init_df, df_features, ModelParams
from df.utils import as_complex
from libdf import DF

def calculate_si_sdr(reference, estimation):
    # Scale invariant SDR
    reference = reference - np.mean(reference)
    estimation = estimation - np.mean(estimation)
    
    ref_energy = np.sum(reference ** 2)
    if ref_energy == 0:
        return 0.0
        
    alpha = np.sum(reference * estimation) / ref_energy
    target = alpha * reference
    res = estimation - target
    
    target_energy = np.sum(target ** 2)
    res_energy = np.sum(res ** 2)
    
    if res_energy == 0:
        return 100.0
        
    return 10 * np.log10(target_energy / res_energy)

def run_equivalence():
    np.random.seed(42)
    
    # 2 seconds of random noise audio at 48kHz
    hop = 480
    test_audio = np.random.randn(1, 48000 * 2).astype(np.float32) * 0.1
    
    # Init PyTorch Model
    model, df_state, _ = init_df("DeepFilterNet3", log_file=None)
    model.eval()
    nb_df = getattr(model.p, "nb_df", 96) if hasattr(model, "p") else 96
    
    # Init ONNX
    base_dir = "models/onnx"
    enc_sess = ort.InferenceSession(os.path.join(base_dir, "enc.onnx"), providers=["CPUExecutionProvider"])
    erb_dec_sess = ort.InferenceSession(os.path.join(base_dir, "erb_dec.onnx"), providers=["CPUExecutionProvider"])
    df_dec_sess = ort.InferenceSession(os.path.join(base_dir, "df_dec.onnx"), providers=["CPUExecutionProvider"])
    
    pt_out = []
    onnx_out = []
    
    # State
    p = ModelParams()
    df_state_pt = DF(p.sr, p.fft_size, p.hop_size, p.nb_erb, p.min_nb_freqs)
    df_state_onnx = DF(p.sr, p.fft_size, p.hop_size, p.nb_erb, p.min_nb_freqs)
    
    for state in model.modules():
        if hasattr(state, "reset_state"):
            state.reset_state()
            
    num_chunks = test_audio.shape[-1] // hop
    
    from df.enhance import enhance
    print("Running PyTorch full enhancement...")
    pt_audio = enhance(model, df_state_pt, torch.from_numpy(test_audio), pad=False).numpy().flatten()
    print("PyTorch full enhancement done.")
    
    for i in range(num_chunks):
        chunk = test_audio[:, i*hop:(i+1)*hop]
        
        # --- ONNX PATH ---
        audio_onnx = torch.from_numpy(chunk)
        spec_onnx, erb_feat_onnx, spec_feat_onnx = df_features(audio_onnx, df_state_onnx, nb_df, device="cpu")
        if spec_onnx.shape[2] == 0:
            continue
        feat_spec_onnx = spec_feat_onnx.transpose(1, 4).squeeze(4)
        
        enc_out = enc_sess.run(None, {
            "feat_erb": erb_feat_onnx.numpy(),
            "feat_spec": feat_spec_onnx.numpy()
        })
        e0, e1, e2, e3, emb, c0, lsnr = enc_out
        
        m_out = erb_dec_sess.run(None, {
            "emb": emb, "e3": e3, "e2": e2, "e1": e1, "e0": e0
        })
        m_onnx = m_out[0]
        
        coefs_out = df_dec_sess.run(None, {
            "emb": emb, "c0": c0
        })
        coefs_onnx = coefs_out[0]
        
        if i < 5:
            print("m_onnx:", m_onnx.shape)
            print("coefs_onnx:", coefs_onnx.shape)
            print("spec_onnx:", spec_onnx.shape)
        
        spec_t = spec_onnx
        m_t = torch.from_numpy(m_onnx).view(1, 1, 1, 32)
        coefs_t = torch.from_numpy(coefs_onnx).view(1, 1, 96, 10)
        
        spec_m = model.mask(spec_t, m_t)
        
        df_coefs = model.df_out_transform(coefs_t)
        spec_e = model.df_op(spec_t.clone(), df_coefs)
        spec_e[..., model.nb_df :, :] = spec_m[..., model.nb_df :, :]
        
        
        from df.utils import as_complex
        if model.post_filter:
            beta = model.post_filter_beta
            eps = 1e-12
            PI = torch.pi
            mask_pf = (as_complex(spec_e).abs() / as_complex(spec_t).abs().add(eps)).clamp(eps, 1)
            mask_sin = mask_pf * torch.sin(PI * mask_pf / 2).clamp_min(eps)
            pf = (1 + beta) / (1 + beta * mask_pf.div(mask_sin).pow(2))
            spec_e = spec_e * pf.unsqueeze(-1)
        
        enh_onnx = as_complex(spec_e.squeeze(1))
        
        out_onnx = df_state_onnx.synthesis(enh_onnx.detach().numpy())
        
        if i < 5:
            print("out_onnx shape:", out_onnx.shape)
        onnx_out.append(out_onnx)

    onnx_audio = np.concatenate(onnx_out, axis=-1).flatten()
    
    # Ignore the first few frames due to state initialization
    pt_audio = pt_audio[480*10:]
    onnx_audio = onnx_audio[480*10:]
    
    diff = np.abs(pt_audio - onnx_audio)
    max_err = np.max(diff)
    rms_err = np.sqrt(np.mean(diff**2))
    corr = np.corrcoef(pt_audio, onnx_audio)[0, 1]
    si_sdr = calculate_si_sdr(pt_audio, onnx_audio)
    
    print("=== EQUIVALENCE REPORT ===")
    print(f"Output length: {len(pt_audio)}")
    print(f"Finite samples: {np.all(np.isfinite(onnx_audio))}")
    print(f"PyTorch RMS: {np.sqrt(np.mean(pt_audio**2)):.6f}")
    print(f"ONNX RMS: {np.sqrt(np.mean(onnx_audio**2)):.6f}")
    print(f"PyTorch Peak: {np.max(np.abs(pt_audio)):.6f}")
    print(f"ONNX Peak: {np.max(np.abs(onnx_audio)):.6f}")
    print(f"PyTorch Mean: {np.mean(pt_audio):.6f}")
    print(f"ONNX Mean: {np.mean(onnx_audio):.6f}")
    print(f"PyTorch Std: {np.std(pt_audio):.6f}")
    print(f"ONNX Std: {np.std(onnx_audio):.6f}")
    print(f"Waveform correlation: {corr:.6f}")
    print(f"RMS error: {rms_err:.8f}")
    print(f"Max absolute error: {max_err:.8f}")
    print(f"SI-SDR between outputs: {si_sdr:.2f} dB")
    
    with open("runs/dfn3_pi_optimization/onnx_equivalence_report.md", "w") as f:
        f.write("# Equivalence Report\n")
        f.write(f"- Output length: {len(pt_audio)}\n")
        f.write(f"- Finite samples: {np.all(np.isfinite(onnx_audio))}\n")
        f.write(f"- Waveform correlation: {corr:.6f}\n")
        f.write(f"- RMS error: {rms_err:.8f}\n")
        f.write(f"- Max absolute error: {max_err:.8f}\n")
        f.write(f"- SI-SDR between outputs: {si_sdr:.2f} dB\n")

if __name__ == "__main__":
    run_equivalence()
