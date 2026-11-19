#!/usr/bin/env python3
import hashlib,json
from pathlib import Path
import numpy as np
if not hasattr(np.exceptions,'RankWarning'): np.exceptions.RankWarning=np.RankWarning
import scipy.signal,soundfile as sf
ROOT=Path(__file__).resolve().parents[2]; RUN=ROOT/'runs/stage11_2_28_frontend_parity_20261114'; CAN=ROOT/'runs/sih26052_canonical_validation'
ids=[6,93,287]; rows=[]
for i in ids:
    x,sr=sf.read(CAN/'noisy_audio'/f'{i:04d}_noisy.wav',dtype='float32')
    y=scipy.signal.resample_poly(x,3,1).astype(np.float32)
    p=RUN/'inputs_shared'/f'{i:04d}.wav'; sf.write(p,y,48000,subtype='FLOAT')
    rows.append({'val_index':i,'source_sr':sr,'output_sr':48000,'samples':len(y),'input_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(RUN/'shared_inputs_metadata.json').write_text(json.dumps({'selected_ids':ids,'manifest_sha256':hashlib.sha256((CAN/'manifest.csv').read_bytes()).hexdigest(),'resampler':'scipy.signal.resample_poly(x,3,1).astype(float32)','inputs':rows,'gold_accessed':False},indent=2)+'\n')
print(rows)
