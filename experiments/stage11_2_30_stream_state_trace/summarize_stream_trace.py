#!/usr/bin/env python3
"""Create reproducible fixed-alignment summary for the Stage 11.2.30 trace."""
from pathlib import Path
import hashlib,json
import numpy as np,soundfile as sf,torch
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'runs/stage11_2_30_stream_state_trace_20261114'
ST28=ROOT/'runs/stage11_2_28_frontend_parity_20261114'
ST29=ROOT/'runs/stage11_2_29_network_parity_20261114'
idx=93;warmup=50;shift=-2
N=RUN/'native_trace_0093_v3';P=ST29/'pytorch';F=ST28/'python_features_py310'
def f32(path,shape): return np.fromfile(path,dtype='<f4').reshape(shape)
def stat(a,b):
    d=a.astype(np.float64)-b.astype(np.float64)
    return {'elements':int(d.size),'rmse':float(np.sqrt(np.mean(d*d))),'mean_native_minus_python':float(np.mean(d)),'max_abs':float(np.max(np.abs(d))),'correlation':float(np.corrcoef(a.ravel(),b.ravel())[0,1])}
feature={}
for key, pyfile, nativefile, shape in [('erb','0093_erb_features.f32','erb.f32',(300,32)),('complex','0093_complex_features.f32','complex.f32',(300,96,2))]:
    a=f32(N/nativefile,shape);b=f32(F/pyfile,shape)
    feature[key]={'exact':bool(np.array_equal(a,b)),**stat(a,b)}
outs=[];shapes=[(64,32),(64,16),(64,8),(64,8),(512,),(64,96),(1,)]
for j,shape in enumerate(shapes):
    native=f32(N/f'enc_output_{j}.f32',(300,)+shape)
    raw=np.load(P/f'{idx:04d}_enc_{j}.npy')
    py=raw.transpose(0,2,1,3)[0] if j in (0,1,2,3,5) else raw[0]
    a=native[warmup:298];b=py[warmup+shift:298+shift]
    outs.append({'name':['e0','e1','e2','e3','emb','c0','lsnr'][j],'shape_per_frame':list(shape),'alignment':'native[i] vs Python[i-2]','all_post_startup':stat(a,b)})
# Apply the protected local-SNR head to the native embedding trace.
ckpt=ROOT/'runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt'
state=torch.load(ckpt,map_location='cpu',weights_only=True)
emb=f32(N/'enc_output_4.f32',(300,512))[warmup:298]
native_lsnr=f32(N/'lsnr.f32',(300,))[warmup:298]
pred=torch.sigmoid(torch.from_numpy(emb) @ state['enc.lsnr_fc.0.weight'].T + state['enc.lsnr_fc.0.bias']).numpy().reshape(-1)*50-15
lsnr_head={'native_head_reproduced':bool(np.allclose(pred,native_lsnr,rtol=0,atol=2e-5)),**stat(pred,native_lsnr)}
manifest={'canonical_manifest_sha256':'d09a520d566fc1dc28c4bf07e9c860ce4ef9a2b5aae3a377ca109cb84c0049d4','checkpoint_sha256':hashlib.sha256(ckpt.read_bytes()).hexdigest(),'tract_archive_sha256':hashlib.sha256((ROOT.parent/'models/dfn3_step500_tract.tar.gz').read_bytes()).hexdigest()}
wav,sr=sf.read(ST28/'inputs_shared/0093.wav',dtype='float32')
quiet=[i for i,ch in enumerate(wav.reshape(-1,480)) if float(np.mean(ch.astype(np.float64)**2))<1e-7]
summary={'clip_id':idx,'frames_input':int(len(wav)//480),'native_model_calls':int(len(np.fromfile(N/'frame_index.u32',dtype='<u4'))),'sample_rate':sr,'warmup_frames_excluded':warmup,'expected_lookahead_shift':shift,'quiet_input_frames_below_1e_7':quiet,'front_end_feature_comparisons':feature,'encoder_outputs':outs,'lsnr_head_check':lsnr_head,'protected_hashes':manifest,'gold_accessed':False}
(RUN/'streaming_state_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
