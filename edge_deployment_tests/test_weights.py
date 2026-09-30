import sys
import os
import torch

sys.path.append(os.path.expanduser("~/sih26052_edge"))
from app.anc_stream import ANCStream

CONFIG_PATH = "/home/shreyas/sih26052_edge/config/config.json"
stream = ANCStream(CONFIG_PATH)

weight = stream.model.core.fc_mag.weight
print(f"fc_mag weight mean: {weight.mean().item():.8f}, std: {weight.std().item():.8f}")
print(f"fc_mag weight exact values: {weight.view(-1)[:5]}")
