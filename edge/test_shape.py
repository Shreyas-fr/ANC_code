import torch
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
from df.enhance import init_df, df_features, ModelParams
from libdf import DF

model, df_state, _ = init_df("DeepFilterNet3", log_file=None)
p = ModelParams()
df_state_pt = DF(p.sr, p.fft_size, p.hop_size, p.nb_erb, p.min_nb_freqs)

chunk = torch.randn(1, 480)
spec, erb_feat, spec_feat = df_features(chunk, df_state_pt, p.nb_df, device="cpu")
print("No padding:")
print(spec.shape, erb_feat.shape, spec_feat.shape)

try:
    model(spec, erb_feat, spec_feat)
    print("model() success on 1 frame!")
except Exception as e:
    print("model() failed on 1 frame:", e)
