#!/usr/bin/env python3
import hashlib,json,sys
from pathlib import Path
import numpy as np,soundfile as sf
ROOT=Path(__file__).resolve().parents[2]; RUN=ROOT/'runs/stage11_2_28_frontend_parity_20261114'
sys.path.insert(0,str(RUN/'py310libdf'))
from libdf import DF,erb,erb_norm,unit_norm
ids=[6,93,287]; alpha=0.99; sr=48000; fft=960; hop=480; nb_erb=32; nb_df=96; min_nb=2
records=[]
for i in ids:
    x,rate=sf.read(RUN/'inputs_shared'/f'{i:04d}.wav',dtype='float32')
    if rate!=sr or x.ndim!=1 or len(x)%hop: raise RuntimeError(f'invalid input {i}')
    state=DF(sr,fft,hop,nb_erb,min_nb)
    spec=state.analysis(np.ascontiguousarray(x.reshape(1,-1))).astype(np.complex64)
    erb_features=erb_norm(np.ascontiguousarray(erb(spec,state.erb_widths()),dtype=np.float32),alpha).astype(np.float32)
    complex_features=unit_norm(np.ascontiguousarray(spec[...,:nb_df]),alpha).astype(np.complex64)
    synthesis_state=DF(sr,fft,hop,nb_erb,min_nb)
    synthesis=synthesis_state.synthesis(np.ascontiguousarray(spec.copy())).astype(np.float32).reshape(-1)
    stem=RUN/'python_features_py310'/f'{i:04d}'
    np.asarray(spec,dtype=np.complex64).tofile(str(stem)+'_stft.f32')
    np.asarray(erb_features,dtype='<f4').tofile(str(stem)+'_erb_features.f32')
    np.asarray(complex_features,dtype=np.complex64).tofile(str(stem)+'_complex_features.f32')
    np.asarray(synthesis,dtype='<f4').tofile(str(stem)+'_synthesis.f32')
    records.append({'id':i,'frames':spec.shape[1],'stft_shape':list(spec.shape),'erb_shape':list(erb_features.shape),'cplx_shape':list(complex_features.shape),'synthesis_samples':len(synthesis),'input_sha256':hashlib.sha256((RUN/'inputs_shared'/f'{i:04d}.wav').read_bytes()).hexdigest()})
meta={'python':'3.10.22','numpy':'1.24.4','libdf_source':'0.5.6 source commit 978576aa8400552a4ce9730838c635aa30db5e61','alpha':alpha,'sr':sr,'fft_size':fft,'hop_size':hop,'nb_erb':nb_erb,'nb_df':nb_df,'min_nb_freqs':min_nb,'frames':records}
(RUN/'python_libdf_py310_metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
print(json.dumps(meta,indent=2))
