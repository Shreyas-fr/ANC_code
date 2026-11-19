import sys
import types
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

import argparse
import torch
import df.scripts.export as export_module
from df.scripts.export import setup_df_argument_parser

# Monkey patch init_df
orig_init_df = export_module.init_df
def custom_init_df(*args, **kwargs):
    model, df_state, _ = orig_init_df(*args, **kwargs)
    import torch
    ckpt = torch.load("models/dfn3_final.pt", map_location='cpu')
    state_dict = ckpt['model_state_dict'] if 'model_state_dict' in ckpt else ckpt
    model.load_state_dict(state_dict, strict=True)
    model.eval()
    return model, df_state, _
export_module.init_df = custom_init_df

# Monkey patch export_impl to disable JIT and dynamic axes
orig_export_impl = export_module.export_impl
def custom_export_impl(path, model, inputs, input_names, output_names, dynamic_axes, jit=True, **kwargs):
    # Disable dynamic axes to prevent torch.export from crashing
    return orig_export_impl(path, model, inputs, input_names, output_names, None, jit=False, **kwargs)
export_module.export_impl = custom_export_impl

orig_export = export_module.export
def custom_export(*args, **kwargs):
    # Patch torch.randn specifically for the audio tensor creation inside export
    orig_randn = torch.randn
    def mocked_randn(*shape_args, **shape_kwargs):
        if len(shape_args) == 1 and shape_args[0] == (1, 48000): # 1 * p.sr
            return orig_randn((1, 480), **shape_kwargs)
        return orig_randn(*shape_args, **shape_kwargs)
    torch.randn = mocked_randn
    try:
        return orig_export(*args, **kwargs)
    finally:
        torch.randn = orig_randn
export_module.export = custom_export

export_module.get_test_sample = lambda sr: torch.randn(1, 480)

if __name__ == "__main__":
    parser = setup_df_argument_parser()
    parser.add_argument("export_dir", help="Directory for exporting the onnx model.")
    parser.add_argument(
        "--no-check",
        help="Don't check models with onnx checker.",
        action="store_false",
        dest="check",
    )
    parser.add_argument("--simplify", help="Simply onnx models using onnxsim.", action="store_true")
    parser.add_argument("--opset", help="ONNX opset version", type=int, default=14) # DeepFilter uses 14 for STFT
    args = parser.parse_args()
    export_module.main(args)
