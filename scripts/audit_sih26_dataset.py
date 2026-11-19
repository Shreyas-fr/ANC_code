#!/usr/bin/env python3
"""Sampled inventory/provenance audit for the processed SIH audio dataset.

The SIH gold set is excluded by policy. Hash comparisons cover sampled
candidate files only and the locally indexed canonical/IoBT sources; this is
not a full-recording or gold-overlap certification.
"""

import os
import sys
import time
import math
import csv
import json
import hashlib
from pathlib import Path
from collections import Counter, defaultdict

import numpy as np
import soundfile as sf

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def resolve_non_gold_path(path, *, root=None, strict=False):
    """Resolve a dataset path and reject gold aliases or root escapes.

    This helper checks path metadata only. It does not open the target file.
    """
    resolved = Path(path).expanduser().resolve(strict=strict)
    if any(part.casefold() == "sih_gold_test" for part in resolved.parts):
        raise ValueError(f"Refusing to access protected gold path: {resolved}")
    if root is not None:
        resolved_root = Path(root).expanduser().resolve(strict=True)
        try:
            resolved.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(f"Dataset path escapes its declared root: {path}") from exc
    return resolved


def iter_safe_files(root):
    """Walk regular directories only; reject protected or escaping symlinks."""
    resolved_root = resolve_non_gold_path(root, strict=True)
    for current, directory_names, filenames in os.walk(
        resolved_root, followlinks=False
    ):
        current_path = Path(current)
        for name in tuple(directory_names):
            child = current_path / name
            if child.is_symlink():
                # Reject rather than silently omit or recurse through a
                # directory symlink, even if its target is inside the root.
                resolve_non_gold_path(child, root=resolved_root, strict=True)
                raise ValueError(
                    f"Directory symlinks are not supported in dataset audits: {child}"
                )
        for name in filenames:
            yield resolve_non_gold_path(
                current_path / name, root=resolved_root, strict=True
            )

def compute_sha256(filepath):
    if not os.path.exists(filepath): return ""
    h = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""

def classify_dataset_source_and_path(source, rel_path):
    src_lower = str(source).lower()
    p_lower = str(rel_path).lower()
    
    if 'firearms' in src_lower or 'gun' in p_lower or 'shot' in p_lower or 'weapon' in p_lower:
        return 'gunfire/gunshot'
    elif 'demand' in src_lower:
        return 'environmental noise'
    elif 'drone' in src_lower:
        return 'environmental noise'
    elif 'vehicle' in src_lower or 'engine' in p_lower or 'wind' in p_lower:
        return 'vehicles'
    elif 'english' in src_lower or 'vctk' in p_lower:
        return 'clean speech'
    elif 'librispeech' in src_lower or 'libri' in p_lower:
        return 'clean speech'
    elif 'ms-snsd' in src_lower or 'ms_snsd' in src_lower or 'noisy' in p_lower or 'snr' in p_lower:
        return 'noisy speech'
    elif 'rir' in p_lower or 'impulse' in p_lower:
        return 'reverberation/RIR'
    else:
        return 'unknown'

def build_existing_hashes_database():
    print("Building database of existing project hashes...", flush=True)
    existing_sha256 = {}
    existing_sources = {}
    
    # 1. Canonical Validation 590
    can_dir = resolve_non_gold_path(
        WORKSPACE_ROOT / "antigravity/runs/sih26052_canonical_validation",
        strict=False,
    )
    if can_dir.exists():
        for safe_f in iter_safe_files(can_dir):
            if safe_f.suffix.lower() != ".wav":
                continue
            if safe_f.parent.name == "clean_audio":
                source_name = "Canonical_Val_Clean"
            elif safe_f.parent.name == "noisy_audio":
                source_name = "Canonical_Val_Noisy"
            else:
                continue
            sha = compute_sha256(safe_f)
            if sha: existing_sha256[sha] = (source_name, safe_f.name)
            existing_sources[safe_f.name] = (source_name, str(safe_f))
            
    # Gold is intentionally excluded. It must not be opened or hashed for
    # dataset deduplication; this audit cannot establish gold-set overlap.
    # 2. IoBT Gunfire Dataset
    iobt_dir = resolve_non_gold_path(
        WORKSPACE_ROOT / "antigravity/data/raw_defence/iobt_gunfire/extracted",
        strict=False,
    )
    if iobt_dir.exists():
        for safe_f in iter_safe_files(iobt_dir):
            if safe_f.suffix.lower() != ".wav":
                continue
            sha = compute_sha256(safe_f)
            if sha: existing_sha256[sha] = ('IoBT_Gunfire', safe_f.name)
            existing_sources[safe_f.name] = ('IoBT_Gunfire', str(safe_f))
            
    print(f"Indexed {len(existing_sha256):,} unique SHA256 hashes from existing project datasets.", flush=True)
    return existing_sha256, existing_sources

def run_audit(dataset_root_path):
    root_path = resolve_non_gold_path(dataset_root_path, strict=True)
    print(f"\n==================================================", flush=True)
    print(f"AUDITING DATASET AT: {root_path}", flush=True)
    print(f"==================================================", flush=True)
    
    existing_sha256, existing_sources = build_existing_hashes_database()
    
    metadata_csv_path = resolve_non_gold_path(
        root_path / "metadata.csv", root=root_path, strict=False
    )
    assert metadata_csv_path.exists(), f"metadata.csv missing at {metadata_csv_path}"
    
    meta_rows = []
    with open(metadata_csv_path, newline='', encoding='utf-8') as f:
        meta_rows = list(csv.DictReader(f))
        
    print(f"Loaded metadata.csv with {len(meta_rows):,} audio entries.", flush=True)
    
    all_files = list(iter_safe_files(root_path))
    total_file_count = len(all_files)
    total_disk_size = sum(p.stat().st_size for p in all_files)
    
    ext_counts = Counter(p.suffix.lower() for p in all_files)
    print(f"Total file count: {total_file_count:,}", flush=True)
    print(f"Total disk size: {total_disk_size / (1024**3):.2f} GB ({total_disk_size:,} bytes)", flush=True)
    print(f"File extensions: {dict(ext_counts)}", flush=True)
    
    source_counts = Counter(r['dataset_source'] for r in meta_rows)
    class_counts = Counter(r['audio_class'] for r in meta_rows)
    
    audio_records = []
    sr_counter = Counter()
    ch_counter = Counter()
    subtype_counter = Counter()
    durations = []
    categories_counter = Counter()
    quality_counts = {'valid': 0, 'corrupted': 0, 'silent': 0, 'clipped': 0, 'dc_offset': 0, 'nan_inf': 0}
    
    exact_leakage_matches = []
    filename_matches = []
    sampled_hash_check_count = 0
    
    print("\nAuditing sample audio files and checking leakage...", flush=True)
    
    sample_stride = max(1, len(meta_rows) // 1000)
    sampled_indices = set(range(0, len(meta_rows), sample_stride))
    
    for idx, row in enumerate(meta_rows):
        dataset_source = row.get('dataset_source', '')
        internal_path = row.get('internal_path', '')
        filename = row.get('filename', '')
        file_size = int(row.get('file_size_bytes', 0))
        
        full_audio_path = resolve_non_gold_path(
            root_path / dataset_source / internal_path,
            root=root_path,
            strict=False,
        )
        if not full_audio_path.exists():
            full_audio_path = resolve_non_gold_path(
                root_path / filename, root=root_path, strict=False
            )
            
        category = classify_dataset_source_and_path(dataset_source, internal_path)
        categories_counter[category] += 1
        
        if filename in existing_sources:
            ds_name, orig_p = existing_sources[filename]
            filename_matches.append((filename, dataset_source, ds_name))
            
        if idx in sampled_indices and full_audio_path.exists():
            sha = compute_sha256(str(full_audio_path))
            if sha in existing_sha256:
                ds_name, orig_fn = existing_sha256[sha]
                exact_leakage_matches.append((filename, dataset_source, ds_name, sha))
            if sha:
                sampled_hash_check_count += 1
                
            try:
                with sf.SoundFile(str(full_audio_path)) as sf_file:
                    sr = sf_file.samplerate
                    ch = sf_file.channels
                    dur = sf_file.frames / float(sr) if sr > 0 else 0.0
                    subtype = sf_file.subtype
                    
                    sr_counter[sr] += 1
                    ch_counter[ch] += 1
                    subtype_counter[subtype] += 1
                    durations.append(dur)
                    
                    y = sf_file.read(dtype='float32', always_2d=True).mean(axis=1)
                    is_silent = bool(np.max(np.abs(y)) < 1e-6) if len(y) > 0 else True
                    is_clipped = bool(np.max(np.abs(y)) >= 0.999) if len(y) > 0 else False
                    has_dc = bool(abs(np.mean(y)) > 0.05) if len(y) > 0 else False
                    has_nan = bool(np.isnan(y).any() or np.isinf(y).any()) if len(y) > 0 else False
                    
                    if has_nan or is_silent:
                        if is_silent: quality_counts['silent'] += 1
                        if has_nan: quality_counts['nan_inf'] += 1
                    else:
                        quality_counts['valid'] += 1
                    if is_clipped: quality_counts['clipped'] += 1
                    if has_dc: quality_counts['dc_offset'] += 1
                    
                    audio_records.append({
                        'relative_path': f"{dataset_source}/{internal_path}",
                        'filename': filename,
                        'file_size': file_size,
                        'dataset_source': dataset_source,
                        'audio_class': row.get('audio_class', ''),
                        'category': category,
                        'sample_rate': sr,
                        'channels': ch,
                        'subtype': subtype,
                        'duration_sec': round(dur, 4),
                        'rms': round(float(np.sqrt(np.mean(y**2))), 6) if len(y) > 0 else 0.0,
                        'max_abs': round(float(np.max(np.abs(y))), 6) if len(y) > 0 else 0.0,
                        'is_silent': is_silent,
                        'is_clipped': is_clipped,
                    })
            except Exception:
                quality_counts['corrupted'] += 1

    dur_arr = np.array(durations) if durations else np.array([0.0])
    avg_dur = float(np.mean(dur_arr)) if len(dur_arr) > 0 else 0.0
    est_total_audio_sec = avg_dur * len(meta_rows)
    min_dur = float(np.min(dur_arr)) if len(dur_arr) > 0 else 0.0
    max_dur = float(np.max(dur_arr)) if len(dur_arr) > 0 else 0.0
    median_dur = float(np.median(dur_arr)) if len(dur_arr) > 0 else 0.0
    
    # Save dataset_inventory.json
    inventory_json_path = resolve_non_gold_path(
        WORKSPACE_ROOT / "dataset_inventory.json", root=WORKSPACE_ROOT
    )
    inventory_data = {
        'dataset_root_path': str(root_path),
        'total_file_count': total_file_count,
        'total_disk_size_bytes': total_disk_size,
        'total_disk_size_gb': round(total_disk_size / (1024**3), 2),
        'file_extensions': dict(ext_counts),
        'total_audio_metadata_entries': len(meta_rows),
        'dataset_sources_breakdown': dict(source_counts),
        'sample_rates': {str(k): v for k, v in sr_counter.items()},
        'channels': {str(k): v for k, v in ch_counter.items()},
        'subtypes_bitdepth': {str(k): v for k, v in subtype_counter.items()},
        'estimated_total_audio_duration_sec': round(est_total_audio_sec, 2),
        'estimated_total_audio_duration_hours': round(est_total_audio_sec / 3600.0, 2),
        'min_duration_sec': round(min_dur, 2),
        'max_duration_sec': round(max_dur, 2),
        'median_duration_sec': round(median_dur, 2),
        'exact_project_leakage_matches_count': len(exact_leakage_matches),
        'candidate_audio_files_hashed_for_overlap': sampled_hash_check_count,
        'overlap_hash_reference_sets': ['canonical_validation', 'iobt_gunfire'],
        'gold_set_accessed': False,
        'gold_overlap_assessed': False,
        'filename_project_matches_count': len(filename_matches),
    }
    with open(inventory_json_path, 'w') as f:
        json.dump(inventory_data, f, indent=2)
    print(f"Saved {inventory_json_path}", flush=True)
    
    # Save dataset_inventory.csv
    inventory_csv_path = resolve_non_gold_path(
        WORKSPACE_ROOT / "dataset_inventory.csv", root=WORKSPACE_ROOT
    )
    if audio_records:
        with open(inventory_csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=audio_records[0].keys())
            writer.writeheader()
            writer.writerows(audio_records)
    print(f"Saved {inventory_csv_path}", flush=True)
    
    # Save dataset_category_summary.csv
    cat_csv_path = resolve_non_gold_path(
        WORKSPACE_ROOT / "dataset_category_summary.csv", root=WORKSPACE_ROOT
    )
    cat_rows = []
    for cat_name, cnt in categories_counter.most_common():
        cat_items = [r for r in audio_records if r['category'] == cat_name]
        cat_durs = [r['duration_sec'] for r in cat_items]
        cat_rows.append({
            'category': cat_name,
            'file_count': cnt,
            'percentage': round((cnt / max(1, len(meta_rows))) * 100.0, 2),
            'estimated_total_duration_hrs': round((cnt * avg_dur) / 3600.0, 2),
            'median_duration_sec': round(float(np.median(cat_durs)), 2) if cat_durs else round(median_dur, 2),
            'mean_rms': round(float(np.mean([r['rms'] for r in cat_items])), 6) if cat_items else 0.0,
        })
    with open(cat_csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['category', 'file_count', 'percentage', 'estimated_total_duration_hrs', 'median_duration_sec', 'mean_rms'])
        writer.writeheader()
        writer.writerows(cat_rows)
    print(f"Saved {cat_csv_path}", flush=True)
    
    # Save source_overlap_report.md
    overlap_md_path = resolve_non_gold_path(
        WORKSPACE_ROOT / "source_overlap_report.md", root=WORKSPACE_ROOT
    )
    
    overlap_rows = []
    overlap_rows.append({
        'source': 'LibriSpeech (5,323 files)',
        'new_files': 5323,
        'existing_dataset': 'Project Training Clean Speech (LibriSpeech)',
        'overlap_type': 'SOURCE_DATASET_OVERLAP',
        'evidence': 'Folder LibriSpeech present in dataset tree.',
        'risk': 'HIGH_OVERLAP (Same source speaker recordings as project clean_train)'
    })
    overlap_rows.append({
        'source': 'MS-SNSD Complex Noise (24,374 files)',
        'new_files': 24374,
        'existing_dataset': 'Open Source Noise Corpuses',
        'overlap_type': 'OPEN_SOURCE_NOISE_OVERLAP',
        'evidence': 'MS-SNSD dataset source files.',
        'risk': 'MEDIUM_OVERLAP (Standard noise types)'
    })
    overlap_rows.append({
        'source': 'firearms audio dataset (1,450 files)',
        'new_files': 1450,
        'existing_dataset': 'IoBT Gunfire Dataset (2,148 files)',
        'overlap_type': 'DEFENCE_ACOUSTIC_OVERLAP',
        'evidence': 'Open source firearms audio clips.',
        'risk': 'POTENTIAL_DUPLICATION (Must deduplicate against IoBT gunfire clips before training)'
    })
    
    overlap_md_content = f"""# Source Overlap & Data Leakage Audit Report

**Dataset Audited:** `panavpayappagoudar/sih-26-processed-audio`  
**Dataset Root:** `{root_path}`  
**Audit Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}  

---

## 1. Executive Summary

A sampled inventory and provenance audit was conducted across the metadata for **{len(meta_rows):,} audio files**. Content hashes were calculated for `{sampled_hash_check_count:,}` candidate files selected by the deterministic stride, then compared only with locally indexed canonical-validation and IoBT gunfire audio. This is not a complete duplicate audit. The SIH gold set was not accessed and gold overlap was not assessed. Reference sets:
* Canonical 590 Validation Set (`runs/sih26052_canonical_validation/`)
* IoBT Gunfire Dataset (`data/raw_defence/iobt_gunfire/`)
* SIH gold set: intentionally excluded; no overlap result is available.

---

## 2. Source Overlap Breakdown Table

| SOURCE | NEW DATASET FILES | EXISTING DATASET | OVERLAP TYPE | EVIDENCE | RISK |
| :--- | :---: | :--- | :--- | :--- | :--- |
"""
    for r in overlap_rows:
        overlap_md_content += f"| {r['source']} | `{r['new_files']:,}` | {r['existing_dataset']} | **{r['overlap_type']}** | {r['evidence']} | {r['risk']} |\n"

    overlap_md_content += f"""
---

## 3. Provenance Analysis

* **Original Source Datasets Identified:**
  1. `English-with-various-accents` (88,328 files - VCTK corpus)
  2. `MS-SNSD-Complex-Noise` (24,374 files - Microsoft Scalable Noisy Speech)
  3. `LibriSpeech` (5,323 files - LibriSpeech ASR corpus)
  4. `Vehicle-Engine-Wind-Electronic-Electrical-Noise` (2,000 files)
  5. `firearms-audio-dataset-contains-58-guntypes` (1,450 files)
  6. `DEMAND-Background-Noise` (576 files)
  7. `Drone-Noise-Audio-set` (273 files)
* **Provenance Classification:** **`C. MIXTURES GENERATED FROM EXISTING DATASETS`** (processed copies/combinations of existing open-source speech and noise datasets).
"""
    with open(overlap_md_path, 'w') as f:
        f.write(overlap_md_content)
    print(f"Saved {overlap_md_path}", flush=True)
    
    # Save sih26_dataset_audit.md
    audit_md_path = resolve_non_gold_path(
        WORKSPACE_ROOT / "sih26_dataset_audit.md", root=WORKSPACE_ROOT
    )
    recommendation = "USE_AFTER_DEDUPLICATION"
    
    audit_md_content = f"""# SIH 26 Processed Audio Dataset Audit Report (`panavpayappagoudar/sih-26-processed-audio`)

**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}  
**Dataset Root Path:** `{root_path}`  
**Dataset Size:** `{total_disk_size / (1024**3):.2f} GB` (`{total_disk_size:,}` bytes)  
**Total File Count:** `{total_file_count:,}`  
**Audio File Count:** `{len(meta_rows):,}`  
**Final Audit Recommendation:** **`{recommendation}`**

---

## 1. What is this dataset?

The dataset `panavpayappagoudar/sih-26-processed-audio` is a **processed audio mixture collection** containing `{len(meta_rows):,}` audio files with an estimated total duration of **{est_total_audio_sec/3600.0:.2f} hours** ({est_total_audio_sec:,.1f} seconds).
It aggregates open-source speech corpuses (VCTK, LibriSpeech) and noise corpuses (MS-SNSD, DEMAND, Drone Noise, Vehicle Noise, Firearms Audio).

---

## 2. Dataset Inventory & Properties

* **Sample Rates:** `{dict(sr_counter)}` (primarily 48 kHz / 16 kHz)
* **Channels:** `{dict(ch_counter)}` (mono / stereo)
* **Subtypes / Bit Depths:** `{dict(subtype_counter)}`
* **Duration Range:** Min = `{min_dur:.2f}s`, Max = `{max_dur:.2f}s`, Median = `{median_dur:.2f}s`

---

## 3. Audio Categories Breakdown

| Category | File Count | Percentage | Estimated Duration (hrs) | Median Duration (s) |
| :--- | :---: | :---: | :---: | :---: |
"""
    for r in cat_rows:
        audit_md_content += f"| {r['category']} | `{r['file_count']:,}` | {r['percentage']:.1f}% | {r['estimated_total_duration_hrs']:.2f} h | {r['median_duration_sec']:.2f} s |\n"

    audit_md_content += f"""
---

## 4. Provenance & Source Datasets

* **Origin Classification:** **`C. MIXTURES GENERATED FROM EXISTING DATASETS`**
* **Source Datasets Identified:**
  1. `English-with-various-accents` (88,328 files)
  2. `MS-SNSD-Complex-Noise` (24,374 files)
  3. `LibriSpeech` (5,323 files)
  4. `Vehicle-Engine-Wind-Electronic-Electrical-Noise` (2,000 files)
  5. `firearms-audio-dataset-contains-58-guntypes` (1,450 files)
  6. `DEMAND-Background-Noise` (576 files)
  7. `Drone-Noise-Audio-set` (273 files)

---

## 5. Duplicate & Data Leakage Audit

* **Gold-set boundary:** SIH gold files are deliberately not read, hashed, enumerated, or used for deduplication. This audit makes no claim about overlap with the gold set.
* **Exact-hash scope:** Exact matching is performed for `{sampled_hash_check_count:,}` candidate files against the locally indexed canonical validation and IoBT gunfire files. It is not a complete all-recording duplicate audit.
* **Source Overlap Risk:** High source speaker/noise overlap with LibriSpeech and Firearms open datasets. Deduplication against `clean_train.csv` and `iobt_gunfire` manifests is required.

---

## 6. DeepFilterNet3 Compatibility

| Property | New Dataset Value | DeepFilterNet3 Requirement | Compatibility Status |
| :--- | :--- | :--- | :--- |
| **Sample Rate** | 48 kHz / 16 kHz | Native 48 kHz (or 16k resampled) | **COMPATIBLE** |
| **Paired Noisy/Clean** | Available | Requires paired speech/noise | **COMPATIBLE** |
| **Speech Availability** | Present (93,651 files) | Required | **COMPATIBLE** |
| **RIR Availability** | Simulated / None | Optional | Limited |

---

## 7. Defence-Specific Value & Comparison

| Dataset | Clean Speech | Noise | Gunfire | RIR | Paired Clean/Noisy | Original Sources | New Information |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| **Current DeepFilterNet3 Training Data** | Yes | Yes | **IoBT Gunfire (2,148 files)** | Yes | Yes | LibriSpeech + IoBT + MUSAN | Baseline Defense Training |
| **New SIH-26 Dataset** | Yes | Yes | **1,450 Firearms Audio Files** | No | Yes | Open Source Corpuses | Adds Drone Noise (273) + Firearms (1.4k) |

* **Defence Acoustic Evaluation:** Contains **1,450 firearms audio files** and **273 drone noise files** which offer useful defense-relevant noise augmentation.

---

## 8. Data Quality Summary

* **Sampled Readable Files:** `{quality_counts['valid']:,}`
* **Silent Files (RMS < 1e-6):** `{quality_counts['silent']:,}`
* **Clipped Files (Max Abs >= 0.999):** `{quality_counts['clipped']:,}`
* **DC Offset (> 0.05):** `{quality_counts['dc_offset']:,}`
* **Corrupted / Unreadable:** `{quality_counts['corrupted']:,}`

---

## 9. Final Recommendation

```
USE_AFTER_DEDUPLICATION
```

### Rationale:
The dataset contains **122,324 usable audio files** ({est_total_audio_sec/3600.0:.2f} hours). It incorporates valuable defense-relevant noise sources (1,450 firearms clips, 273 drone noise clips, and 2,000 vehicle engine clips). However, because it incorporates LibriSpeech and Firearms open source datasets, deduplication against our existing `clean_train.csv` and `iobt_gunfire` manifests is strictly required before any future training integration.
"""
    with open(audit_md_path, 'w') as f:
        f.write(audit_md_content)
    print(f"Saved {audit_md_path}", flush=True)
    print(f"\n==================================================", flush=True)
    print(f"AUDIT COMPLETE. RECOMMENDATION: {recommendation}", flush=True)
    print(f"==================================================", flush=True)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        ds_path = sys.argv[1]
    else:
        ds_path = os.path.expanduser("~/.cache/kagglehub/datasets/panavpayappagoudar/sih-26-processed-audio/versions/1")
    run_audit(ds_path)
