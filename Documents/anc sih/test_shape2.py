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
import torch
from df.enhance import init_df, df_features, ModelParams
from libdf import DF

model, df_state, _ = init_df("DeepFilterNet3", log_file=None)
p = ModelParams()
df_state_pt = DF(p.sr, p.fft_size, p.hop_size, p.nb_erb, p.min_nb_freqs)

chunk1 = torch.randn(1, 480)
spec1, erb1, spec_f1 = df_features(chunk1, df_state_pt, p.nb_df, device="cpu")
print("chunk1 sizes:", spec1.shape, erb1.shape, spec_f1.shape)

chunk2 = torch.randn(1, 480)
spec2, erb2, spec_f2 = df_features(chunk2, df_state_pt, p.nb_df, device="cpu")
print("chunk2 sizes:", spec2.shape, erb2.shape, spec_f2.shape)
