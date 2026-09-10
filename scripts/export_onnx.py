import sys
import os
import torch
import torchaudio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.enhance.complex_crn import ComplexCRN

def export_to_onnx():
    model = ComplexCRN()
    
    # Load best checkpoint if available
    checkpoint_path = "checkpoints/dtln/best.pt"
    if os.path.exists(checkpoint_path):
        print(f"Loading weights from {checkpoint_path}")
        model.load_state_dict(torch.load(checkpoint_path, map_location='cpu'))
    else:
        print("Warning: best.pt not found. Exporting untrained model.")
        
    model.eval()
    
    # Dummy input: [Batch=1, Time=512] representing one 32ms frame at 16kHz
    dummy_input = torch.randn(1, 512)
    
    onnx_path = "checkpoints/dtln/model.onnx"
    os.makedirs(os.path.dirname(onnx_path), exist_ok=True)
    
    print("Exporting to ONNX...")
    try:
        torch.onnx.export(
            model,
            dummy_input,
            onnx_path,
            export_params=True,
            opset_version=18,
            do_constant_folding=True,
            input_names=['input_audio'],
            output_names=['enhanced_audio']
        )
        print(f"Success! Model exported to {onnx_path}")
    except Exception as e:
        print(f"ONNX Export Failed: {e}")

if __name__ == "__main__":
    export_to_onnx()
