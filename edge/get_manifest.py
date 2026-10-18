import sys, os, hashlib, platform
import onnx
import onnxruntime as ort
import torch
import importlib.metadata

def hash_file(filepath):
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        hasher.update(f.read())
    return hasher.hexdigest()

onnx_dir = "models/onnx"
files = ["enc.onnx", "erb_dec.onnx", "df_dec.onnx"]
manifest_lines = []

for fn in files:
    path = os.path.join(onnx_dir, fn)
    manifest_lines.append(f"{fn} SHA256: {hash_file(path)}")
    model = onnx.load(path)
    manifest_lines.append(f"  Input Shapes:")
    for inp in model.graph.input:
        shape = [d.dim_value if d.HasField("dim_value") else d.dim_param for d in inp.type.tensor_type.shape.dim]
        manifest_lines.append(f"    {inp.name}: {shape}")

manifest_lines.append(f"\nONNX Runtime version: {ort.__version__}")
manifest_lines.append(f"Python version: {platform.python_version()}")
manifest_lines.append(f"PyTorch version: {torch.__version__}")
try:
    manifest_lines.append(f"DeepFilterNet version: {importlib.metadata.version('deepfilternet')}")
except:
    manifest_lines.append(f"DeepFilterNet version: unknown")
manifest_lines.append(f"CPU architecture: {platform.machine()} {platform.processor()}")
manifest_lines.append(f"OS/Kernel: {platform.platform()} {platform.release()}")

out_dir = "runs/dfn3_pi_optimization"
os.makedirs(out_dir, exist_ok=True)
with open(os.path.join(out_dir, "onnx_artifact_manifest.txt"), "w") as f:
    f.write("\n".join(manifest_lines))
print("Manifest created.")
