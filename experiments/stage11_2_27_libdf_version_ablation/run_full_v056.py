#!/usr/bin/env python3
"""Run isolated v0.5.6 libDF source candidate once per clip to guarantee fresh state."""
from __future__ import annotations
import csv, hashlib, json, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'runs/stage11_2_27_libdf_version_ablation_20261114'
OUT=RUN/'full_outputs_v056_source'
MODEL=ROOT.parent/'models/dfn3_step500_tract.tar.gz'
MANIFEST=ROOT/'runs/sih26052_canonical_validation/manifest.csv'
BINARY=RUN/'target/release/deep-filter'
if OUT.exists(): raise SystemExit(f'refusing to overwrite {OUT}')
rows=list(csv.DictReader(MANIFEST.open(newline='',encoding='utf-8')))
if len(rows)!=590: raise SystemExit(f'expected 590 manifest rows, got {len(rows)}')
OUT.mkdir()
results=[]; start=time.monotonic()
for j,row in enumerate(rows):
    i=int(row['val_index']); dest=OUT/f'{i:04d}'; dest.mkdir()
    src=ROOT/'runs/sih26052_canonical_validation/noisy_audio'/f'{i:04d}_noisy.wav'
    cmd=[str(BINARY),'--model',str(MODEL),'--compensate-delay','--output-dir',str(dest),str(src)]
    proc=subprocess.run(cmd,cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    wav=dest/f'{i:04d}_noisy.wav'
    if proc.returncode!=0 or not wav.exists():
        (RUN/f'failure_{i:04d}.stderr.txt').write_text(proc.stderr)
        raise SystemExit(f'failed ID={i}, exit={proc.returncode}; stderr saved')
    digest=hashlib.sha256(wav.read_bytes()).hexdigest()
    results.append({'val_index':i,'returncode':proc.returncode,'output_path':str(wav.relative_to(ROOT)),'sha256':digest})
    if (j+1)%50==0 or j==589: print(f'completed {j+1}/590',flush=True)
meta={'source_tag':'v0.5.6','source_commit':'978576aa8400552a4ce9730838c635aa30db5e61','binary_sha256':hashlib.sha256(BINARY.read_bytes()).hexdigest(),'model_archive_sha256':hashlib.sha256(MODEL.read_bytes()).hexdigest(),'canonical_manifest_sha256':hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),'count':len(results),'one_process_per_clip':True,'delay_compensation':'unchanged 30 ms','resampler':'isolated SciPy-equivalent native polyphase, same function as Stage 11.2.26','wall_seconds':time.monotonic()-start,'gold_accessed':False,'network_or_install':False,'training_or_tuning':False}
with (RUN/'full_outputs_v056_source_hashes.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
(RUN/'full_v056_run_metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
print(json.dumps(meta,indent=2))
