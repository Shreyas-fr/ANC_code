import os
import sys
import hashlib
import torch
import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.enhance.complex_crn import ComplexCRN_Wrapper, ComplexCRN

CHECKPOINT = "checkpoints/dtln/latest.pt"
ONNX_PATH  = "checkpoints/dtln/model.onnx"

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def export_to_onnx(checkpoint_path=CHECKPOINT, onnx_path=ONNX_PATH):
    device = torch.device('cpu')

    # Load full wrapper so key remapping works, then extract core
    wrapper = ComplexCRN_Wrapper().to(device)
    if os.path.exists(checkpoint_path):
        print(f"Loading weights from {checkpoint_path}")
        state_dict = torch.load(checkpoint_path, map_location=device)
        new_state_dict = {}
        for k, v in state_dict.items():
            if not k.startswith("core."):
                new_state_dict["core." + k] = v
            else:
                new_state_dict[k] = v
        wrapper.load_state_dict(new_state_dict)
        print(f"  Checkpoint SHA-256: {sha256(checkpoint_path)}")
    else:
        print(f"WARNING: checkpoint not found at {checkpoint_path}. Exporting random weights.")

    core = wrapper.core
    core.eval()

    # Dummy: [B=1, F=257, T=16] — must have enough time frames to avoid LSTM issues
    dummy = torch.randn(1, 257, 16)

    # --- PyTorch reference output (before export) ---
    with torch.no_grad():
        ref_real, ref_imag = core(dummy)

    os.makedirs(os.path.dirname(onnx_path), exist_ok=True)
    print(f"Exporting to ONNX: {onnx_path}")

    # dynamo=False forces the legacy TorchScript-based exporter, which correctly
    # serialises LSTM _flat_weights into the graph. The new torch.export path
    # (dynamo=True, default in PyTorch >= 2.1) does NOT embed LSTM weights.
    torch.onnx.export(
        core,
        dummy,
        onnx_path,
        export_params=True,
        opset_version=17,
        do_constant_folding=True,
        input_names=['mag_input'],
        output_names=['mask_real', 'mask_imag'],
        dynamo=False,
    )
    print(f"  ONNX SHA-256: {sha256(onnx_path)}")
    print(f"  ONNX size:    {os.path.getsize(onnx_path)} bytes")

    # --- Verify ONNX output matches PyTorch ---
    try:
        import onnxruntime as ort
        sess = ort.InferenceSession(onnx_path, providers=['CPUExecutionProvider'])
        onnx_out = sess.run(None, {'mag_input': dummy.numpy()})
        diff_real = np.abs(ref_real.numpy() - onnx_out[0]).max()
        diff_imag = np.abs(ref_imag.numpy() - onnx_out[1]).max()
        print(f"  PyTorch vs ONNX max abs diff — mask_real: {diff_real:.2e}  mask_imag: {diff_imag:.2e}")
        if diff_real < 1e-4 and diff_imag < 1e-4:
            print("  PASS: ONNX output matches PyTorch.")
        else:
            print("  FAIL: ONNX output diverges from PyTorch — weights may not be embedded correctly.")
    except ImportError:
        print("  (onnxruntime not available — skipping parity check)")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default=CHECKPOINT)
    parser.add_argument("--output",     default=ONNX_PATH)
    args = parser.parse_args()
    export_to_onnx(args.checkpoint, args.output)

