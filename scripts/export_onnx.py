import os
import torch
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.enhance.complex_crn import ComplexCRN_Wrapper

def export_to_onnx():
    # Load wrapper to get the migrated state_dict, then export just the core
    device = torch.device('cpu')
    wrapper = ComplexCRN_Wrapper().to(device)
    
    checkpoint_path = "checkpoints/dtln_finetune/best.pt"
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
    
    model = wrapper.core
    model.eval()
    
    # Dummy input: Magnitude spectrogram of 1 frame [Batch=1, Freq=257, Time=1]
    dummy_input = torch.randn(1, 257, 1)
    
    onnx_path = "checkpoints/dtln/model.onnx"  # overwrite in-place so rpi_infer.py path unchanged
    os.makedirs(os.path.dirname(onnx_path), exist_ok=True)
    
    print("Exporting Core Model to ONNX...")
    try:
        torch.onnx.export(
            model,
            dummy_input,
            onnx_path,
            export_params=True,
            opset_version=18,
            do_constant_folding=True,
            input_names=['mag_input'],
            output_names=['mask_real', 'mask_imag']
        )
        print(f"Success! Core Model exported to {onnx_path}")
    except Exception as e:
        print(f"ONNX Export Failed: {e}")

if __name__ == "__main__":
    export_to_onnx()
