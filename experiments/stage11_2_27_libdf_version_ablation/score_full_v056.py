#!/usr/bin/env python3
from __future__ import annotations
import csv,hashlib,json,sys,subprocess
from pathlib import Path
import numpy as np,soundfile as sf
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'runs/stage11_2_27_libdf_version_ablation_20261114'
if not hasattr(np.exceptions,'RankWarning'): np.exceptions.RankWarning=np.RankWarning
sys.path.insert(0,str(ROOT))
from scripts.evaluate_dfn3_canonical import metrics
CAN=ROOT/'runs/sih26052_canonical_validation'; PY=ROOT/'runs/stage8_ensemble_20261113/step500_predictions'; CURRENT=ROOT/'runs/stage11_2_26_native_polyphase_candidate_20261114'
manifest=list(csv.DictReader((CAN/'manifest.csv').open(newline='')))
py_ledger={int(r['val_index']):r for r in csv.DictReader((PY/'prediction_files.csv').open(newline=''))}
py_m={int(r['val_index']):r for r in csv.DictReader((PY/'per_clip.csv').open(newline=''))}
cur_m={int(r['val_index']):r for r in csv.DictReader((CURRENT/'full_metrics/native/per_clip.csv').open(newline=''))}
old_rows=[]; py_rows=[]; cur_rows=[]; wave=[]
for i,item in enumerate(manifest):
    op=RUN/f'full_outputs_v056_source/{i:04d}/{i:04d}_noisy.wav'
    cp=CURRENT/f'full_native_outputs/{i:04d}_noisy.wav'
    pp=PY/py_ledger[i]['relative_path']
    assert hashlib.sha256(pp.read_bytes()).hexdigest()==py_ledger[i]['sha256']
    o,osr=sf.read(op,dtype='float32'); c,csr=sf.read(cp,dtype='float32'); p,psr=sf.read(pp,dtype='float32')
    clean,rsr=sf.read(CAN/'clean_audio'/f'{i:04d}_clean.wav',dtype='float32')
    if (osr,csr,psr,rsr)!=(16000,16000,16000,16000) or not all(np.isfinite(a).all() for a in (o,c,p,clean)):
        raise RuntimeError(f'bad waveform ID {i}')
    n=min(len(o),len(c),len(p),len(clean)); o,c,p,clean=[a[:n] for a in (o,c,p,clean)]
    om=metrics(clean,o); cm=metrics(clean,c); pm=metrics(clean,p)
    shared={'val_index':i,'target_snr_db':float(item['target_snr']),'input_snr_db':float(py_m[i]['input_snr_db'])}
    old_rows.append({**shared,**{f'output_{k}':v for k,v in om.items()}})
    py_rows.append({**shared,**{f'output_{k}':v for k,v in pm.items()}})
    cur_rows.append({**shared,**{f'output_{k}':v for k,v in cm.items()}})
    corr=float(np.corrcoef(o,c)[0,1]); rmse=float(np.sqrt(np.mean((o-c)**2))); maxdiff=float(np.max(np.abs(o-c)))
    wave.append({'val_index':i,'samples':n,'corr_v056_vs_v057':corr,'rmse_v056_vs_v057':rmse,'max_abs_v056_vs_v057':maxdiff,'snr_delta_v056_minus_v057':om['snr_db']-cm['snr_db'],'sisdr_delta_v056_minus_v057':om['si_sdr_db']-cm['si_sdr_db'],'stoi_delta_v056_minus_v057':om['stoi']-cm['stoi'],'pesq_delta_v056_minus_v057':om['pesq_wb']-cm['pesq_wb']})
    if (i+1)%100==0 or i==589: print(f'scored {i+1}/590',flush=True)
for name,rows in [('v056',old_rows),('v057',cur_rows),('python',py_rows)]:
    d=RUN/f'metrics/{name}'; d.mkdir(parents=True,exist_ok=False)
    with (d/'per_clip.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    vals={k:np.array([r['output_'+k] for r in rows],dtype=float) for k in ('snr_db','si_sdr_db','stoi','pesq_wb')}
    joint=(vals['snr_db']>15)&(vals['stoi']>0.85)&(vals['pesq_wb']>2.5)
    summary={'n':len(rows),'canonical_manifest_sha256':hashlib.sha256((CAN/'manifest.csv').read_bytes()).hexdigest(),'means':{k:float(v.mean()) for k,v in vals.items()},'joint_passes':int(joint.sum()),'joint_rate':float(joint.mean()),'metric_function':'unchanged scripts/evaluate_dfn3_canonical.py::metrics','samples_per_clip':n,'independence':'reused development benchmark; not independent validation'}
    (d/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
with (RUN/'waveform_v056_vs_v057_per_clip.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(wave[0]));w.writeheader();w.writerows(wave)
for candidate,label in [('v056','v056_vs_python'),('v057','v057_vs_python')]:
    cmd=[str(ROOT.parent/'pc_venv/bin/python'),str(ROOT/'scripts/compare_dfn3_canonical.py'),'--reference',str(RUN/'metrics/python/per_clip.csv'),'--candidate',str(RUN/f'metrics/{candidate}/per_clip.csv'),'--output',str(RUN/f'paired_{label}.json'),'--bootstrap','2000','--seed','26052']
    p=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True)
    (RUN/f'paired_{label}.stdout.txt').write_text(p.stdout);(RUN/f'paired_{label}.stderr.txt').write_text(p.stderr)
    if p.returncode: raise RuntimeError(f'comparer failed {label} rc={p.returncode}: {p.stderr}')
    print(label,'exit',p.returncode)
print('done. summaries:',*[str(RUN/f'metrics/{x}/summary.json') for x in ('v056','v057','python')])
