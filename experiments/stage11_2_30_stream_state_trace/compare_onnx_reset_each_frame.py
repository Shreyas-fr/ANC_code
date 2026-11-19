#!/usr/bin/env python3
import json
from pathlib import Path
import numpy as np, onnxruntime as ort
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'runs/stage11_2_30_stream_state_trace_20261114'
ONNX=ROOT/'runs/stage11_2_29_network_parity_20261114/tract_export/tmp/export/enc.onnx'
FEAT=ROOT/'runs/stage11_2_28_frontend_parity_20261114/python_features_py310'
N=RUN/'native_trace_0093_v2'
s=ort.InferenceSession(str(ONNX),providers=['CPUExecutionProvider'])
e=np.fromfile(FEAT/'0093_erb_features.f32',dtype='<f4').reshape(1,300,32)
c=np.fromfile(FEAT/'0093_complex_features.f32',dtype=np.complex64).reshape(1,300,96).view(np.float32).reshape(1,300,96,2).transpose(0,3,1,2).copy()
# Fresh session each frame guarantees any state is reset. Encoder lookahead
# input shift is applied as it is in the full-sequence comparison.
e=np.concatenate([e[:,2:,:],np.zeros_like(e[:,:2,:])],axis=1)
c=np.concatenate([c[:,:,2:,:],np.zeros_like(c[:,:,:2,:])],axis=2)
v=[]
for t in range(300):
    z=s.run(['lsnr'],{'feat_erb':e[:,t:t+1,:].reshape(1,1,1,32),'feat_spec':c[:,:,t:t+1,:]})[0]
    v.append(float(z.reshape(-1)[0]))
native=np.fromfile(N/'lsnr.f32',dtype='<f4')
a=np.array(v,dtype=np.float32)
rows=[]
for shift in range(-5,6):
    lo=max(0,-shift);hi=min(300,300-shift);x=native[lo:hi].astype(float);y=a[lo+shift:hi+shift].astype(float);d=x-y
    rows.append({'python_frame_shift':shift,'frames':hi-lo,'rmse':float(np.sqrt(np.mean(d*d))),'max_abs':float(np.max(np.abs(d))),'corr':float(np.corrcoef(x,y)[0,1])})
print(json.dumps(rows,indent=2));(RUN/'onnx_reset_each_frame_comparison.json').write_text(json.dumps(rows,indent=2)+'\n')
