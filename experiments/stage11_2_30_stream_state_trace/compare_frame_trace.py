#!/usr/bin/env python3
from pathlib import Path
import json
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'runs/stage11_2_30_stream_state_trace_20261114'
PY=ROOT/'runs/stage11_2_29_network_parity_20261114/pytorch'
N=RUN/'native_trace_0093'
idx=93
native_l=np.fromfile(N/'lsnr.f32',dtype='<f4')
native_m=np.fromfile(N/'mask.f32',dtype='<f4').reshape(-1,32)
native_c=np.fromfile(N/'coefs.f32',dtype='<f4').reshape(-1,96,5,2)
frame_idx=np.fromfile(N/'frame_index.u32',dtype='<u4')
py_l=np.load(PY/f'{idx:04d}_lsnr.npy').reshape(-1)
py_m=np.load(PY/f'{idx:04d}_mask.npy').reshape(300,32)
py_c=np.load(PY/f'{idx:04d}_coefs.npy')[0].transpose(1,2,0,3) # [T, F, order, RI]
assert len(native_l)==300 and len(frame_idx)==300 and np.array_equal(frame_idx,np.arange(300,dtype=np.uint32))
rows=[]
for shift in range(-5,6):
    # native frame i is compared to Python frame i+shift
    lo=max(0,-shift); hi=min(300,300-shift)
    pairs=(slice(lo,hi),slice(lo+shift,hi+shift))
    stats={}
    for name,a,b in [('lsnr',native_l,py_l),('mask',native_m,py_m),('coefs',native_c,py_c)]:
        x=a[pairs[0]].astype(np.float64); y=b[pairs[1]].astype(np.float64); d=x-y
        stats[name]={'rmse':float(np.sqrt(np.mean(d*d))),'max_abs':float(np.max(np.abs(d))), 'corr':float(np.corrcoef(x.reshape(-1),y.reshape(-1))[0,1])}
    rows.append({'python_frame_shift':shift,'aligned_frames':hi-lo,**stats})
print(json.dumps(rows,indent=2))
(RUN/'frame_alignment_comparison.json').write_text(json.dumps({'clip_id':idx,'frames':300,'mapping_definition':'native frame i compared to Python frame i+shift; diagnostic only; no samples shifted in output','results':rows},indent=2)+'\n')
