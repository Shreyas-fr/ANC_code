#!/usr/bin/env python3
from pathlib import Path
import csv,json
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
N=ROOT/'runs/stage11_2_30_stream_state_trace_20261114/native_trace_0093_v3'
P=ROOT/'runs/stage11_2_29_network_parity_20261114/pytorch'
shapes=[(64,32),(64,16),(64,8),(64,8),(512,),(64,96),(1,)]
rows=[]
for j,shape in enumerate(shapes):
    a=np.fromfile(N/f'enc_output_{j}.f32',dtype='<f4').reshape((300,)+shape)
    raw=np.load(P/f'0093_enc_{j}.npy')
    # PyTorch feature maps are [B,C,T,F], while native trace appends each
    # frame as [C,1,F]. Reorder the Python time axis before flattening.
    if j in (0,1,2,3,5):
        b=raw.transpose(0,2,1,3)[0]
    else:
        b=raw[0]
    for shift in range(-4,5):
        lo=max(0,-shift);hi=min(300,300-shift)
        x=a[lo:hi].astype(float);y=b[lo+shift:hi+shift].astype(float);d=x-y
        rows.append({'output_index':j,'shape':list(shape),'python_frame_shift':shift,'frames':hi-lo,'rmse':float(np.sqrt(np.mean(d*d))),'max_abs':float(np.max(np.abs(d))),'corr':float(np.corrcoef(x.ravel(),y.ravel())[0,1])})
for j in range(7):
    best=min((r for r in rows if r['output_index']==j),key=lambda r:r['rmse'])
    print(j,'best_shift',best['python_frame_shift'],'RMSE',best['rmse'],'max',best['max_abs'],'corr',best['corr'])
out=ROOT/'runs/stage11_2_30_stream_state_trace_20261114/encoder_state_comparison.json'
out.write_text(json.dumps({'id':93,'outputs':['e0','e1','e2','e3','emb','c0','lsnr'],'mapping':'native frame i compared with PyTorch frame i+shift; shift search diagnostic only, no waveform correction','results':rows},indent=2)+'\n')
