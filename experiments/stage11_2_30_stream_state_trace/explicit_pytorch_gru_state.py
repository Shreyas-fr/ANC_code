#!/usr/bin/env python3
"""Compare full-sequence and explicit hidden-state PyTorch GRU inference."""
import sys,types,json,hashlib
from pathlib import Path
import numpy as np,torch
ROOT=Path(__file__).resolve().parents[2]
ST28=ROOT/'runs/stage11_2_28_frontend_parity_20261114'
RUN=ROOT/'runs/stage11_2_30_stream_state_trace_20261114'
SRC=ST28/'DeepFilterNet/DeepFilterNet'
CKPT=ROOT/'runs/sih26052_rpi_deployment_audit/runs/step500_from_pi.pt'
libdf=types.ModuleType('libdf');libdf.DF=object;libdf.unit_norm_init=lambda n:np.ones(n,dtype=np.float32);sys.modules['libdf']=libdf
pkg=types.ModuleType('df');pkg.__path__=[str(SRC/'df')];sys.modules['df']=pkg;sys.path.insert(0,str(SRC))
from df.config import config
from df.deepfilternet3 import DfNet
from df.modules import erb_fb
from df.utils import as_real
config.load(str(ST28/'config.ini'),config_must_exist=True)
widths=np.array([1,1,1,1,1,1,2,2,2,3,3,4,4,5,5,7,7,8,10,12,13,15,18,20,24,28,31,37,42,50,56,67])
model=DfNet(erb_fb(widths,48000),erb_fb(widths,48000,inverse=True)).eval()
model.load_state_dict(torch.load(CKPT,map_location='cpu',weights_only=True),strict=True)
features={}
def capture(module,args,out):
    features['pre_gru']=args[0].detach()
    features['full_out']=out[0].detach()
h=model.enc.emb_gru.register_forward_hook(capture)
f=ST28/'python_features_py310';idx=93
spec=np.fromfile(f/f'{idx:04d}_stft.f32',dtype=np.complex64).reshape(1,300,481)
erb=np.fromfile(f/f'{idx:04d}_erb_features.f32',dtype='<f4').reshape(1,300,32)
cplx=np.fromfile(f/f'{idx:04d}_complex_features.f32',dtype=np.complex64).reshape(1,300,96)
spec=as_real(torch.from_numpy(spec).unsqueeze(1))
erb=torch.from_numpy(erb).unsqueeze(1)
cplx=as_real(torch.from_numpy(cplx).unsqueeze(1))
with torch.inference_mode():
    _=model(spec,erb,cplx)
h.remove()
pre=features['pre_gru'];full=features['full_out']
step=[];reset=[];state=None
with torch.inference_mode():
    for t in range(pre.shape[1]):
        out,state=model.enc.emb_gru(pre[:,t:t+1,:],state)
        step.append(out)
        reset.append(model.enc.emb_gru(pre[:,t:t+1,:],None)[0])
step=torch.cat(step,dim=1)
reset=torch.cat(reset,dim=1)
full_np=full.cpu().numpy()[0];step_np=step.cpu().numpy()[0]
reset_np=reset.cpu().numpy()[0]
native=np.fromfile(RUN/'native_trace_0093_v3/enc_output_4.f32',dtype='<f4').reshape(300,512)
native_e3=np.fromfile(RUN/'native_trace_0093_v3/enc_output_3.f32',dtype='<f4').reshape(300,64,8)
native_c0=np.fromfile(RUN/'native_trace_0093_v3/enc_output_5.f32',dtype='<f4').reshape(300,64,96)
# Reconstruct the exact input that PyTorch's encoder GRU would receive from
# the native per-frame convolution maps, then run that GRU with persistent h.
# This isolates the recurrent op from differences in its inputs.
native_gru_inputs=[]
with torch.inference_mode():
    for t in range(300):
        e3=torch.from_numpy(native_e3[t].copy()).reshape(1,64,1,8)
        c0=torch.from_numpy(native_c0[t].copy()).reshape(1,64,1,96)
        c1=model.enc.df_conv1(c0)
        cemb=model.enc.df_fc_emb(c1.permute(0,2,3,1).flatten(2))
        eemb=e3.permute(0,2,3,1).flatten(2)
        gru_in=model.enc.combine(eemb,cemb)
        native_gru_inputs.append(gru_in)
native_gru_inputs=torch.cat(native_gru_inputs,dim=1)
native_step=[];state=None
with torch.inference_mode():
    for t in range(300):
        out_step,state=model.enc.emb_gru(native_gru_inputs[:,t:t+1,:],state)
        native_step.append(out_step)
native_step=torch.cat(native_step,dim=1).cpu().numpy()[0]
# Build the correctly time-paired reference sequence: the first two Python
# GRU inputs, followed by native inputs beginning at native frame 4 (which
# match Python frames 2 onward). This tests whether the observed divergence is
# fully explained by the pulsed encoder's startup prelude.
with torch.inference_mode():
    aligned_inputs=torch.cat([pre[:,:2,:],native_gru_inputs[:,4:,:]],dim=1)
    aligned_out=model.enc.emb_gru(aligned_inputs,None)[0].cpu().numpy()[0]
# The ordinary Python model's captured GRU input allows us to test whether
# the convolution-to-GRU input itself differs after the known 2-frame lookahead.
native_in_np=native_gru_inputs.cpu().numpy()[0]
python_in_np=pre.cpu().numpy()[0]
def stat(a,b):
    a=a.astype(np.float64);b=b.astype(np.float64);d=a-b
    return {'rmse':float(np.sqrt(np.mean(d*d))),'max_abs':float(np.max(np.abs(d))),'mean_a_minus_b':float(np.mean(d)),'correlation':float(np.corrcoef(a.ravel(),b.ravel())[0,1])}
windows=[]
for lo,hi in [(2,10),(10,25),(25,50),(50,100),(100,200),(200,298)]:
    windows.append({'native_frames':[lo,hi],'comparison':'native[t] vs Python[t-2]','embedding':stat(native[lo:hi],step_np[lo-2:hi-2])})
startup=[]
for t in range(8):
    candidates={}
    for shift in range(-3,4):
        j=t+shift
        if 0<=j<300:
            candidates[str(shift)]={'python_frame':j,'gru_input_rmse':float(np.sqrt(np.mean((native_in_np[t].astype(np.float64)-python_in_np[j].astype(np.float64))**2)))}
    startup.append({'native_frame':t,'native_input_rms':float(np.sqrt(np.mean(native_in_np[t].astype(np.float64)**2))),'python_candidates':candidates})
summary={'clip_id':idx,'frames':300,'strict_checkpoint_load':True,'pytorch_full_vs_explicit_stepwise':stat(full_np,step_np),'pytorch_full_vs_reset_each_frame':stat(full_np,reset_np),'native_vs_pytorch_explicit_stepwise_after_startup':stat(native[50:298],step_np[48:296]),'native_vs_pytorch_reset_each_frame_after_startup':stat(native[50:298],reset_np[48:296]),'native_embedding_vs_pytorch_gru_on_native_inputs_after_startup':stat(native[50:298],native_step[50:298]),'native_gru_input_vs_python_gru_input_after_startup':stat(native_in_np[50:298],python_in_np[48:296]),'aligned_sequence_reference_vs_python_full':stat(aligned_out,full_np[:aligned_out.shape[0]]),'native_vs_aligned_sequence_reference_after_startup':stat(native[4:298],aligned_out[2:296]),'shifted_embedding_error_by_frame_window':windows,'startup_gru_input_candidates':startup,'python_version':'3.14.7','torch_version':torch.__version__,'checkpoint_sha256':hashlib.sha256(CKPT.read_bytes()).hexdigest(),'gold_accessed':False}
out=RUN/'explicit_pytorch_gru_state_summary.json';out.write_text(json.dumps(summary,indent=2)+'\n')
np.save(RUN/'pytorch_stepwise_gru_embeddings.npy',step_np)
np.save(RUN/'pytorch_reset_gru_embeddings.npy',reset_np)
np.save(RUN/'pytorch_gru_on_native_inputs.npy',native_step)
np.save(RUN/'pytorch_reconstructed_native_gru_inputs.npy',native_in_np)
np.save(RUN/'pytorch_full_gru_inputs.npy',python_in_np)
np.save(RUN/'pytorch_aligned_startup_reference.npy',aligned_out)
print(json.dumps(summary,indent=2))
