#!/usr/bin/env python3
import csv,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]; RUN=ROOT/'runs/stage11_2_28_frontend_parity_20261114'; ids=[6,93,287]
shapes={'stft':(300,481,2),'erb_features':(300,32),'complex_features':(300,96,2),'synthesis':(144000,)}
rows=[]
for i in ids:
    for stage,shape in shapes.items():
        py=RUN/'python_features_py310'/f'{i:04d}_{stage}.f32'
        ru=RUN/'rust_features_py310'/f'{i:04d}'/({'stft':'stft','erb_features':'erb_features','complex_features':'complex_features','synthesis':'synthesis'}[stage]+'.f32')
        if stage in ('stft','complex_features'):
            a=np.fromfile(py,dtype=np.complex64).view('<f4').reshape(shape)
        else: a=np.fromfile(py,dtype='<f4').reshape(shape)
        b=np.fromfile(ru,dtype='<f4').reshape(shape)
        if not np.isfinite(a).all() or not np.isfinite(b).all(): raise RuntimeError(f'non-finite: {i}/{stage}')
        d=a.astype(np.float64)-b.astype(np.float64)
        rows.append({'val_index':i,'stage':stage,'shape':'x'.join(map(str,shape)),'elements':int(a.size),'exact_equal':bool(np.array_equal(a,b)),'max_abs_diff':float(np.max(np.abs(d))),'mean_abs_diff':float(np.mean(np.abs(d))),'rmse':float(np.sqrt(np.mean(d*d)))})
        print(i,stage,'equal',np.array_equal(a,b),'max',float(np.max(np.abs(d))),'rmse',float(np.sqrt(np.mean(d*d))))
with (RUN/'frontend_comparison.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
summary={'selected_ids':ids,'stage_count':len(rows),'all_exact':all(r['exact_equal'] for r in rows),'comparisons':rows,'python_reference':'DeepFilterLib 0.5.6 source compiled locally for Python 3.10.22; same source code as native Rust diagnostic','native_reference':'Rust DFState 0.5.6 source, same isolated snapshot','note':'This confirms language binding/frame-array parity for libDF front-end; it does not compare PyTorch network outputs with Tract ONNX outputs.'}
(RUN/'frontend_comparison_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print('all exact',summary['all_exact'])
