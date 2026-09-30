import torch
import sys
import os
sys.path.append(os.path.expanduser("~/sih26052_edge/app"))
from stateful_polar_lstm import StatefulPolarLSTM

class DecayingCore(torch.nn.Module):
    def __init__(self, core, alpha):
        super().__init__()
        self.core = core
        self.alpha = alpha
    def forward(self, features, h_in, c_in):
        return self.core(features, h_in * self.alpha, c_in * self.alpha)

core = StatefulPolarLSTM()
wrapped = DecayingCore(core, 0.95)

features = torch.randn(1, 1, 514)
h_in = torch.zeros(2, 1, 256)
c_in = torch.zeros(2, 1, 256)

res = wrapped(features, h_in, c_in)
print(type(res), len(res))
for i, r in enumerate(res):
    print(f"res[{i}]: {r.shape} nan: {torch.isnan(r).any().item()}")
