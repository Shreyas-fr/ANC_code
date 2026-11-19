#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
import numpy as np
if not hasattr(np.exceptions,'RankWarning'): np.exceptions.RankWarning=np.RankWarning
import scipy.signal,soundfile as sf
ROOT=Path(__file__).resolve().parents[2]; RUN=ROOT/'runs/stage11_2_28_frontend_parity_20261114'
CAN=ROOT/'runs/sih26052_canonical_validation'; ids=[6,93,287]
INPUTS=RUN/'inputs_debug2'; FEATS=RUN/'python_features_debug2'; INPUTS.mkdir(exist_ok=True); FEATS.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(RUN/'DeepFilterNet/DeepFilterNet'))
from scripts.evaluate_dfn3_canonical import install_torchaudio_compat_shim
install_torchaudio_compat_shim()
from df.config import config
from df.model import ModelParams
from df.utils import get_norm_alpha
from libdf import DF,erb,erb_norm,unit_norm
config.load(str(RUN/'config.ini'),config_must_exist=True,allow_defaults=True,allow_reload=True)
p=ModelParams(); alpha=get_norm_alpha(False)
print('params',{'sr':p.sr,'fft_size':p.fft_size,'hop_size':p.hop_size,'nb_erb':p.nb_erb,'nb_df':p.nb_df,'min_nb_freqs':p.min_nb_freqs,'norm_alpha':alpha})
manifest_hash=hashlib.sha256((CAN/'manifest.csv').read_bytes()).hexdigest(); records=[]
for i in ids:
    x,sr=sf.read(CAN/'noisy_audio'/f'{i:04d}_noisy.wav',dtype='float32')
    if sr!=16000 or x.ndim!=1: raise RuntimeError(f'bad canonical clip {i}')
    x48=scipy.signal.resample_poly(x,3,1).astype(np.float32)
    inp=INPUTS/f'{i:04d}.wav'; sf.write(inp,x48,48000,subtype='FLOAT')
    print('clip',i,'input ready',len(x48),flush=True)
    df=DF(p.sr,p.fft_size,p.hop_size,p.nb_erb,p.min_nb_freqs)
    print('calling analysis',flush=True); spec=df.analysis(np.ascontiguousarray(x48.reshape(1,-1))).astype(np.complex64); print('analysis done',spec.shape,flush=True)
    print('calling erb',flush=True); erbfeat=erb(spec,df.erb_widths()); print('erb done',getattr(erbfeat,'shape',None),flush=True)
    print('calling erb_norm',flush=True); erbfeat=erb_norm(np.array(erbfeat,copy=True),alpha).astype(np.float32); print('erb norm done',flush=True)
    print('calling unit_norm',flush=True); cplxfeat=unit_norm(np.array(spec[...,:p.nb_df],copy=True),alpha).astype(np.complex64); print('unit norm done',flush=True)
    synth_df=DF(p.sr,p.fft_size,p.hop_size,p.nb_erb,p.min_nb_freqs)
    print('calling synthesis',flush=True); synth=synth_df.synthesis(spec.copy()).astype(np.float32).reshape(-1); print('synthesis done',len(synth),flush=True)
    base=FEATS/f'{i:04d}'
    np.asarray(spec,dtype=np.complex64).tofile(str(base)+'_stft.f32')
    np.asarray(erbfeat,dtype='<f4').tofile(str(base)+'_erb_features.f32')
    np.asarray(cplxfeat,dtype=np.complex64).tofile(str(base)+'_complex_features.f32')
    np.asarray(synth,dtype='<f4').tofile(str(base)+'_synthesis.f32')
    records.append({'val_index':i,'input_samples_48k':len(x48),'frames':int(spec.shape[1]),'freq_bins':int(spec.shape[2]),'python_stft_shape':list(spec.shape),'python_erb_shape':list(erbfeat.shape),'python_cplx_shape':list(cplxfeat.shape),'python_synthesis_samples':len(synth),'input_sha256':hashlib.sha256(inp.read_bytes()).hexdigest()})
meta={'canonical_manifest_sha256':manifest_hash,'selected_ids':ids,'sample_rate_hz':48000,'fft_size':p.fft_size,'hop_size':p.hop_size,'nb_erb':p.nb_erb,'nb_df':p.nb_df,'min_nb_freqs':p.min_nb_freqs,'norm_alpha':alpha,'python_versions':{'python':sys.version.split()[0],'numpy':np.__version__},'gold_accessed':False,'checkpoint_loaded':False,'network_or_install':False,'frames':records}
(RUN/'python_frontend_debug2_metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
print(json.dumps(meta,indent=2))
