"""Export FullSubNet Fullband and Subband single-step models to ONNX.

This script extracts fb_model and sb_model from the frozen epoch-58 checkpoint
and exports them as standalone single-step graphs with explicit recurrent state inputs and outputs.
"""

from __future__ import annotations

import sys
from pathlib import Path
import torch
import torch.nn as nn
import onnx

REPO = Path(__file__).resolve().parents[2]
VENDOR = REPO / "third_party/fullsubnet_vendor"
CHECKPOINT = REPO / "checkpoints/fullsubnet/fullsubnet_best_model_58epochs.tar"
OUT_DIR = Path(__file__).resolve().parent / "models"
OUT_DIR.mkdir(parents=True, exist_ok=True)

if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

from fullsubnet.model import Model


class FullbandStep(nn.Module):
    """Fullband single time-step module with explicit recurrent state."""

    def __init__(self, fb_seq):
        super().__init__()
        self.lstm = fb_seq.sequence_model
        self.fc = fb_seq.fc_output_layer
        self.act = nn.ReLU()

    def forward(self, x: torch.Tensor, h: torch.Tensor, c: torch.Tensor):
        # x: [1, 1, 257], h: [2, 1, 512], c: [2, 1, 512]
        out, (h_next, c_next) = self.lstm(x, (h, c))
        out = self.act(self.fc(out))
        return out, h_next, c_next


class SubbandStep(nn.Module):
    """Subband single time-step module with explicit recurrent state across 257 bins."""

    def __init__(self, sb_seq):
        super().__init__()
        self.lstm = sb_seq.sequence_model
        self.fc = sb_seq.fc_output_layer

    def forward(self, x: torch.Tensor, h: torch.Tensor, c: torch.Tensor):
        # x: [257, 1, 32], h: [2, 257, 384], c: [2, 257, 384]
        out, (h_next, c_next) = self.lstm(x, (h, c))
        out = self.fc(out)
        return out, h_next, c_next


def main() -> int:
    print(f"Loading checkpoint from {CHECKPOINT}...")
    ckpt = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
    state = ckpt.get("model") or ckpt.get("model_state_dict")
    state = {k.removeprefix("module."): v for k, v in state.items()}

    model = Model(
        num_freqs=257,
        look_ahead=2,
        sequence_model="LSTM",
        fb_num_neighbors=0,
        sb_num_neighbors=15,
        fb_output_activate_function="ReLU",
        sb_output_activate_function=False,
        fb_model_hidden_size=512,
        sb_model_hidden_size=384,
        norm_type="offline_laplace_norm",
        num_groups_in_drop_band=2,
        weight_init=False,
    )
    model.load_state_dict(state)
    model.eval()

    fb_step = FullbandStep(model.fb_model)
    sb_step = SubbandStep(model.sb_model)

    fb_onnx_path = OUT_DIR / "fullband_step.onnx"
    sb_onnx_path = OUT_DIR / "subband_step.onnx"

    print("Exporting FullbandStep to ONNX...")
    dummy_fb_x = torch.randn(1, 1, 257, dtype=torch.float32)
    dummy_fb_h = torch.zeros(2, 1, 512, dtype=torch.float32)
    dummy_fb_c = torch.zeros(2, 1, 512, dtype=torch.float32)

    torch.onnx.export(
        fb_step,
        (dummy_fb_x, dummy_fb_h, dummy_fb_c),
        str(fb_onnx_path),
        input_names=["x", "h_in", "c_in"],
        output_names=["out", "h_out", "c_out"],
        opset_version=14,
        dynamo=False,
    )
    print(f"Saved {fb_onnx_path} ({fb_onnx_path.stat().st_size:,} bytes)")

    print("Exporting SubbandStep to ONNX...")
    dummy_sb_x = torch.randn(257, 1, 32, dtype=torch.float32)
    dummy_sb_h = torch.zeros(2, 257, 384, dtype=torch.float32)
    dummy_sb_c = torch.zeros(2, 257, 384, dtype=torch.float32)

    torch.onnx.export(
        sb_step,
        (dummy_sb_x, dummy_sb_h, dummy_sb_c),
        str(sb_onnx_path),
        input_names=["x", "h_in", "c_in"],
        output_names=["out", "h_out", "c_out"],
        opset_version=14,
        dynamo=False,
    )
    print(f"Saved {sb_onnx_path} ({sb_onnx_path.stat().st_size:,} bytes)")

    # Validate ONNX models
    m_fb = onnx.load(str(fb_onnx_path))
    onnx.checker.check_model(m_fb)
    print("Fullband ONNX checker PASSED!")

    m_sb = onnx.load(str(sb_onnx_path))
    onnx.checker.check_model(m_sb)
    print("Subband ONNX checker PASSED!")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

