#!/usr/bin/env python3
"""Diagnostic: compare Tract per-call output to PyTorch with recurrent state reset each call."""
import sys,types,json
from pathlib import Path
import numpy as np, torch
ROOT=Path(__file__).resolve().parents[2]
STAGE28=ROOT/'runs/stage11_2_28_frontend_parity_20261114'
SRC=STAGE28/'DeepFilterNet/DeepFilterNet'
CKPT=ROOT/'runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt'
libdf=types.ModuleType('libdf'); libdf.DF=object; libdf.unit_norm_init=lambda n:np.ones(n,dtype=np.float32); sys.modules['libdf']=libdf
pkg=types.ModuleType('df'); pkg.__path__=[str(SRC/'df')];sys.modules['df']=pkg;sys.path.insert(0,str(SRC))
from df.config import config
from df.deepfilternet3 import DfNet
from df.modules import erb_fb
config.load(str(STAGE28/'config.ini'),config_must_exist=True)
widths=np.array([1,1,1,1,1,1,2,2,2,3,3,4,4,5,5,7,7,8,10,12,13,15,18,20,24,28,31,37,42,50,56,67])
model=DfNet(erb_fb(widths,48000),erb_fb(widths,48000,inverse=True)).eval()
model.load_state_dict(torch.load(CKPT,map_location='cpu',weights_only=True),strict=True)
f=STAGE28/'python_features_py310'; i=93
erb=torch.from_numpy(np.fromfile(f/f'{i:04d}_erb_features.f32',dtype='<f4').reshape(1,1,300,32))
c=np.fromfile(f/f'{i:04d}_complex_features.f32',dtype=np.complex64).reshape(1,300,96).view(np.float32).reshape(1,300,96,2)
spec=torch.from_numpy(c).permute(0,3,1,2)
with torch.inference_mode():
    # Apply the exact configured 2-frame feature-lookahead shift first, then
    # invoke the encoder once per frame so its GRU starts from zero each call.
    ep=model.pad_feat(erb)
    sp=model.pad_feat(spec)
    out=[]
    for t in range(300):
        values=model.enc(ep[:,:,t:t+1,:],sp[:,:,t:t+1,:])
        out.append(values[6].reshape(-1).item())
torch_reset=np.asarray(out,dtype=np.float32)
native=np.fromfile(ROOT/'runs/stage11_2_30_stream_state_trace_20261114/native_trace_0093_v2/lsnr.f32',dtype='<f4')
rows=[]
for shift in range(-5,6):
    lo=max(0,-shift); hi=min(300,300-shift)
    a=native[lo:hi].astype(float);b=torch_reset[lo+shift:hi+shift].astype(float);d=a-b
    rows.append({'python_frame_shift':shift,'frames':hi-lo,'rmse':float(np.sqrt(np.mean(d*d))),'max_abs':float(np.max(np.abs(d))),'corr':float(np.corrcoef(a,b)[0,1])})
print(json.dumps(rows,indent=2))
(ROOT/'runs/stage11_2_30_stream_state_trace_20261114/reset_per_frame_comparison.json').write_text(json.dumps(rows,indent=2)+'\n')
