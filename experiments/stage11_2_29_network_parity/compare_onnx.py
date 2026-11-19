#!/usr/bin/env python3
import csv
from pathlib import Path
import numpy as np
import onnxruntime as ort

ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'runs/stage11_2_29_network_parity_20261114'
PY=RUN/'pytorch'
ONNX=RUN/'tract_export/tmp/export'
FEAT=ROOT/'runs/stage11_2_28_frontend_parity_20261114/python_features_py310'
sessions={n:ort.InferenceSession(str(ONNX/f'{n}.onnx'),providers=['CPUExecutionProvider']) for n in ('enc','erb_dec','df_dec')}
rows=[]
for idx in (6,93,287):
    erb=np.fromfile(FEAT/f'{idx:04d}_erb_features.f32',dtype='<f4').reshape(1,1,300,32)
    cplx=np.fromfile(FEAT/f'{idx:04d}_complex_features.f32',dtype=np.complex64).reshape(1,300,96)
    spec=cplx.view(np.float32).reshape(1,300,96,2).transpose(0,3,1,2).copy()
    # Match the exported runtime's causal frame plus 2-frame encoder lookahead
    # to PyTorch's pad_feat(0,0,-2,+2) sequence convention.
    erb=np.concatenate([erb[:,:,2:,:],np.zeros_like(erb[:,:,:2,:])],axis=2)
    spec=np.concatenate([spec[:,:,2:,:],np.zeros_like(spec[:,:,:2,:])],axis=2)
    ort_enc=sessions['enc'].run(None,{'feat_erb':erb,'feat_spec':spec})
    enc_names=('e0','e1','e2','e3','emb','c0','lsnr')
    for name,arr in zip(enc_names,ort_enc):
        torch_arr=np.load(PY/f'{idx:04d}_enc_{enc_names.index(name)}.npy')
        d=torch_arr.astype(np.float64)-arr.astype(np.float64)
        rows.append({'id':idx,'component':'enc.'+name,'shape_python':str(torch_arr.shape),'shape_onnx':str(arr.shape),'exact':bool(np.array_equal(torch_arr,arr)),'max_abs':float(np.max(np.abs(d))),'rmse':float(np.sqrt(np.mean(d*d)))})
    e0,e1,e2,e3,emb,c0,lsnr=ort_enc
    ort_mask=sessions['erb_dec'].run(None,{'emb':emb,'e3':e3,'e2':e2,'e1':e1,'e0':e0})[0]
    py_mask=np.load(PY/f'{idx:04d}_erb_dec_0.npy')
    d=py_mask.astype(np.float64)-ort_mask.astype(np.float64)
    rows.append({'id':idx,'component':'erb_dec.m','shape_python':str(py_mask.shape),'shape_onnx':str(ort_mask.shape),'exact':bool(np.array_equal(py_mask,ort_mask)),'max_abs':float(np.max(np.abs(d))),'rmse':float(np.sqrt(np.mean(d*d)))})
    ort_coef=sessions['df_dec'].run(None,{'emb':emb,'c0':c0})[0]
    py_coef=np.load(PY/f'{idx:04d}_df_dec_0.npy')
    d=py_coef.astype(np.float64)-ort_coef.astype(np.float64)
    rows.append({'id':idx,'component':'df_dec.coefs','shape_python':str(py_coef.shape),'shape_onnx':str(ort_coef.shape),'exact':bool(np.array_equal(py_coef,ort_coef)),'max_abs':float(np.max(np.abs(d))),'rmse':float(np.sqrt(np.mean(d*d)))})
    print(idx,'enc max',max(r['max_abs'] for r in rows if r['id']==idx and r['component'].startswith('enc.')),'erb',rows[-2]['max_abs'],'df',rows[-1]['max_abs'])
with (RUN/'onnx_component_comparison.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print('exact components',sum(r['exact'] for r in rows),'/',len(rows))
