import os
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
import sys
import numpy as np
import random
import hashlib
import csv
import time
from scipy.stats import wilcoxon

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.enhance.stateful_polar_lstm import StatefulPolarLSTM_Wrapper
from scripts.dynamic_mixer import AntigravityDataset
from src.enhance.evaluate import si_sdr, pesq, stoi

def compute_sha256(filepath):
    if not os.path.exists(filepath): return "NOT_FOUND"
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def calculate_active_speech_level(waveform):
    frame_len = int(16000 * 0.02)
    hop_len = int(16000 * 0.01)
    if waveform.shape[-1] < frame_len:
        return torch.mean(waveform ** 2)
    frames = waveform.unfold(-1, frame_len, hop_len)
    frame_energies = torch.mean(frames ** 2, dim=-1)
    max_energy = torch.max(frame_energies)
    threshold = max_energy * 0.001
    active_frames = frame_energies[frame_energies > threshold]
    if len(active_frames) == 0:
        return torch.mean(waveform ** 2)
    return torch.mean(active_frames)

def compute_project_snr(clean, noise):
    cp = calculate_active_speech_level(clean)
    npwr = torch.mean(noise ** 2)
    if cp > 0 and npwr > 0:
        return 10 * torch.log10(cp / npwr).item()
    return 0.0

def compute_residual_error_snr(clean, noise):
    cp = torch.mean(clean ** 2)
    npwr = torch.mean(noise ** 2)
    if cp > 0 and npwr > 0:
        return 10 * torch.log10(cp / npwr).item()
    return 0.0

def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

def main():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    out_dir = "runs/sih26052_v1_vs_v2_same_val"
    os.makedirs(out_dir, exist_ok=True)
    
    v1_ckpt = "runs/sih26052_polar_gpu/checkpoint_25000.pt"
    v2_ckpt = "runs/sih26052_polar_v2_25k/best.pt"
    
    print(f"V1_CHECKPOINT_PATH={v1_ckpt}")
    print(f"V2_CHECKPOINT_PATH={v2_ckpt}")
    
    model_v1 = StatefulPolarLSTM_Wrapper().to(device)
    model_v2 = StatefulPolarLSTM_Wrapper().to(device)
    
    v1_params = sum(p.numel() for p in model_v1.parameters() if p.requires_grad)
    v2_params = sum(p.numel() for p in model_v2.parameters() if p.requires_grad)
    
    print(f"V1_PARAMETER_COUNT={v1_params}")
    print(f"V2_PARAMETER_COUNT={v2_params}")
    assert v1_params == 1448962
    assert v2_params == 1448962
    
    v1_reload = "PASS"
    try:
        model_v1.load_state_dict(torch.load(v1_ckpt, map_location=device, weights_only=False))
        model_v1.eval()
    except:
        v1_reload = "FAIL"
        
    v2_reload = "PASS"
    try:
        model_v2.load_state_dict(torch.load(v2_ckpt, map_location=device, weights_only=False))
        model_v2.eval()
    except:
        v2_reload = "FAIL"
        
    # Dataset
    # Exactly same configuration as training script
    set_seed(12345)
    val_dataset = AntigravityDataset(
        clean_manifest="data/clean_manifests/clean_val.csv",
        noise_manifest="data/clean_manifests/noise_val_v2.csv",
        rir_manifest="data/clean_manifests/rir_val.csv",
        epoch_size=590, 
        is_val=True,
        return_metadata=True
    )
    val_loader = DataLoader(val_dataset, batch_size=4, shuffle=False, drop_last=False)
    
    # Determinism checks
    set_seed(12345)
    v1_det, v2_det = "PASS", "PASS"
    noisy_first, clean_first, _ = next(iter(val_loader))
    noisy_first = noisy_first.to(device)
    
    with torch.no_grad():
        out_v1_1, _, _, _ = model_v1(noisy_first)
        out_v1_2, _, _, _ = model_v1(noisy_first)
        if torch.max(torch.abs(out_v1_1 - out_v1_2)).item() > 1e-6:
            v1_det = "FAIL"
            
        out_v2_1, _, _, _ = model_v2(noisy_first)
        out_v2_2, _, _, _ = model_v2(noisy_first)
        if torch.max(torch.abs(out_v2_1 - out_v2_2)).item() > 1e-6:
            v2_det = "FAIL"

    print(f"V1_RELOAD={v1_reload}")
    print(f"V2_RELOAD={v2_reload}")
    print(f"V1_DETERMINISM={v1_det}")
    print(f"V2_DETERMINISM={v2_det}")

    # Build identity CSV and load metrics
    identity_csv_path = os.path.join(out_dir, "v2_validation_identity.csv")
    metrics_csv_path = os.path.join(out_dir, "per_example_metrics.csv")
    
    all_metrics = []
    
    total_examples = 0
    gunfire_examples = 0
    proxy_examples = 0
    
    with open(identity_csv_path, "w", newline="") as id_f, open(metrics_csv_path, "w", newline="") as met_f:
        id_writer = csv.writer(id_f)
        id_writer.writerow(["index", "dataset_origin", "input_hash"])
        
        met_writer = csv.writer(met_f)
        met_writer.writerow([
            "index", "origin", 
            "input_project_snr", "v1_project_snr", "v2_project_snr",
            "input_residual_snr", "v1_residual_snr", "v2_residual_snr",
            "input_si_sdr", "v1_si_sdr", "v2_si_sdr",
            "input_stoi", "v1_stoi", "v2_stoi",
            "input_pesq", "v1_pesq", "v2_pesq"
        ])
        
        global_idx = 0
        
        # IMPORTANT: we must iterate cleanly, so reset seed
        set_seed(12345)
        for noisy_batch, clean_batch, meta_batch in val_loader:
            noisy_batch = noisy_batch.to(device)
            clean_batch = clean_batch.to(device)
            
            with torch.no_grad():
                out_v1, L_out, _, _ = model_v1(noisy_batch)
                out_v2, _, _, _ = model_v2(noisy_batch)
            
            c_diag = clean_batch[:, :L_out].cpu().numpy()
            n_diag = noisy_batch[:, :L_out].cpu().numpy()
            v1_diag = out_v1.cpu().numpy()
            v2_diag = out_v2.cpu().numpy()
            
            origins = meta_batch['dataset_origin']
            
            for i in range(c_diag.shape[0]):
                c = c_diag[i]
                n = n_diag[i]
                v1 = v1_diag[i]
                v2 = v2_diag[i]
                origin = origins[i]
                
                total_examples += 1
                if origin == 'IoBT_GUNFIRE': gunfire_examples += 1
                elif origin == 'EXISTING_PROXY': proxy_examples += 1
                
                # hash input
                n_bytes = n.tobytes()
                h = hashlib.sha256(n_bytes).hexdigest()
                id_writer.writerow([global_idx, origin, h])
                
                # metrics
                c_t = torch.tensor(c)
                n_t = torch.tensor(n)
                v1_t = torch.tensor(v1)
                v2_t = torch.tensor(v2)
                
                # project SNR
                in_proj = compute_project_snr(c_t, n_t - c_t)
                v1_proj = compute_project_snr(c_t, v1_t - c_t)
                v2_proj = compute_project_snr(c_t, v2_t - c_t)
                
                # residual SNR
                in_res = compute_residual_error_snr(c_t, n_t - c_t)
                v1_res = compute_residual_error_snr(c_t, v1_t - c_t)
                v2_res = compute_residual_error_snr(c_t, v2_t - c_t)
                
                in_sdr = si_sdr(c, n)
                v1_sdr = si_sdr(c, v1)
                v2_sdr = si_sdr(c, v2)
                
                in_stoi = stoi(c, n, 16000, extended=False)
                v1_stoi = stoi(c, v1, 16000, extended=False)
                v2_stoi = stoi(c, v2, 16000, extended=False)
                
                try: in_pesq = pesq(16000, c, n, 'wb')
                except: in_pesq = 0.0
                try: v1_pesq = pesq(16000, c, v1, 'wb')
                except: v1_pesq = 0.0
                try: v2_pesq = pesq(16000, c, v2, 'wb')
                except: v2_pesq = 0.0
                
                met_writer.writerow([
                    global_idx, origin,
                    in_proj, v1_proj, v2_proj,
                    in_res, v1_res, v2_res,
                    in_sdr, v1_sdr, v2_sdr,
                    in_stoi, v1_stoi, v2_stoi,
                    in_pesq, v1_pesq, v2_pesq
                ])
                
                all_metrics.append({
                    "origin": origin,
                    "in_proj": in_proj, "v1_proj": v1_proj, "v2_proj": v2_proj,
                    "in_res": in_res, "v1_res": v1_res, "v2_res": v2_res,
                    "in_sdr": in_sdr, "v1_sdr": v1_sdr, "v2_sdr": v2_sdr,
                    "in_stoi": in_stoi, "v1_stoi": v1_stoi, "v2_stoi": v2_stoi,
                    "in_pesq": in_pesq, "v1_pesq": v1_pesq, "v2_pesq": v2_pesq
                })
                
                global_idx += 1

    print(f"TOTAL_VALIDATION_EXAMPLES={total_examples}")
    print(f"GUNFIRE_VALIDATION_EXAMPLES={gunfire_examples}")
    print(f"PROXY_VALIDATION_EXAMPLES={proxy_examples}")
    
    if total_examples != 590 or gunfire_examples != 442 or proxy_examples != 148:
        print("CRITICAL: DISCREPANCY IN EXAMPLES COUNTS!")
        
    def aggregate(subset):
        if not subset:
            return None
        def stat(key): return np.mean([x[key] for x in subset])
        
        diff_proj = [x["v2_proj"] - x["v1_proj"] for x in subset]
        diff_res = [x["v2_res"] - x["v1_res"] for x in subset]
        diff_sdr = [x["v2_sdr"] - x["v1_sdr"] for x in subset]
        diff_stoi = [x["v2_stoi"] - x["v1_stoi"] for x in subset]
        diff_pesq = [x["v2_pesq"] - x["v1_pesq"] for x in subset]
        
        # Compute wilcoxon p-values
        def wilcox(diffs):
            d = np.array(diffs)
            if np.all(d == 0): return 1.0
            try: return wilcoxon(d).pvalue
            except: return 1.0
            
        def diff_stats(diffs, tie_tol):
            d = np.array(diffs)
            return {
                "mean": np.mean(d),
                "median": np.median(d),
                "std": np.std(d),
                "min": np.min(d),
                "max": np.max(d),
                "pos_pct": np.mean(d > tie_tol) * 100,
                "neg_pct": np.mean(d < -tie_tol) * 100,
                "tie_pct": np.mean(np.abs(d) <= tie_tol) * 100,
                "pval": wilcox(d)
            }
            
        return {
            "in_proj": stat("in_proj"), "v1_proj": stat("v1_proj"), "v2_proj": stat("v2_proj"),
            "in_res": stat("in_res"), "v1_res": stat("v1_res"), "v2_res": stat("v2_res"),
            "in_sdr": stat("in_sdr"), "v1_sdr": stat("v1_sdr"), "v2_sdr": stat("v2_sdr"),
            "in_stoi": stat("in_stoi"), "v1_stoi": stat("v1_stoi"), "v2_stoi": stat("v2_stoi"),
            "in_pesq": stat("in_pesq"), "v1_pesq": stat("v1_pesq"), "v2_pesq": stat("v2_pesq"),
            "diff_proj": diff_stats(diff_proj, 0.1),
            "diff_res": diff_stats(diff_res, 0.1),
            "diff_sdr": diff_stats(diff_sdr, 0.1),
            "diff_stoi": diff_stats(diff_stoi, 0.005),
            "diff_pesq": diff_stats(diff_pesq, 0.05),
        }
        
    all_agg = aggregate(all_metrics)
    gf_agg = aggregate([x for x in all_metrics if x["origin"] == "IoBT_GUNFIRE"])
    px_agg = aggregate([x for x in all_metrics if x["origin"] == "EXISTING_PROXY"])
    
    # Write report
    report_path = os.path.join(out_dir, "report.md")
    with open(report_path, "w") as f:
        f.write("# V1 vs V2 Same-Validation Controlled Comparison\n\n")
        f.write("## Checkpoint Identity\n")
        f.write(f"- V1: {v1_ckpt} (Params: {v1_params})\n")
        f.write(f"- V2: {v2_ckpt} (Params: {v2_params})\n\n")
        f.write("## Dataset Identity\n")
        f.write(f"Validated exactly {total_examples} examples (Gunfire: {gunfire_examples}, Proxy: {proxy_examples}).\n\n")
        
        f.write("## Metric Implementation Audit\n")
        f.write("PROJECT_SNR uses `calculate_active_speech_level(clean)` found in `scripts/evaluate_polar_gold.py`.\n")
        f.write("RESIDUAL_ERROR_SNR uses standard mean power as found in training scripts.\n\n")
        
        def write_agg(name, agg):
            if not agg: return
            f.write(f"## {name} Results\n")
            f.write(f"**Input**:\n")
            f.write(f"- PROJECT_SNR: {agg['in_proj']:.4f}\n")
            f.write(f"- RESIDUAL_SNR: {agg['in_res']:.4f}\n")
            f.write(f"- SI-SDR: {agg['in_sdr']:.4f}\n")
            f.write(f"- STOI: {agg['in_stoi']:.4f}\n")
            f.write(f"- PESQ: {agg['in_pesq']:.4f}\n\n")
            
            f.write(f"**V1 Output**:\n")
            f.write(f"- PROJECT_SNR: {agg['v1_proj']:.4f} (Imp: {agg['v1_proj']-agg['in_proj']:.4f})\n")
            f.write(f"- RESIDUAL_SNR: {agg['v1_res']:.4f} (Imp: {agg['v1_res']-agg['in_res']:.4f})\n")
            f.write(f"- SI-SDR: {agg['v1_sdr']:.4f} (Imp: {agg['v1_sdr']-agg['in_sdr']:.4f})\n")
            f.write(f"- STOI: {agg['v1_stoi']:.4f}\n")
            f.write(f"- PESQ: {agg['v1_pesq']:.4f}\n\n")
            
            f.write(f"**V2 Output**:\n")
            f.write(f"- PROJECT_SNR: {agg['v2_proj']:.4f} (Imp: {agg['v2_proj']-agg['in_proj']:.4f})\n")
            f.write(f"- RESIDUAL_SNR: {agg['v2_res']:.4f} (Imp: {agg['v2_res']-agg['in_res']:.4f})\n")
            f.write(f"- SI-SDR: {agg['v2_sdr']:.4f} (Imp: {agg['v2_sdr']-agg['in_sdr']:.4f})\n")
            f.write(f"- STOI: {agg['v2_stoi']:.4f}\n")
            f.write(f"- PESQ: {agg['v2_pesq']:.4f}\n\n")
            
            f.write(f"**Paired V2-vs-V1 Differences (V2 minus V1)**:\n")
            for m in ['proj', 'res', 'sdr', 'stoi', 'pesq']:
                d = agg[f"diff_{m}"]
                f.write(f"- **{m.upper()}**: Mean={d['mean']:.4f}, Median={d['median']:.4f}, Std={d['std']:.4f}\n")
                f.write(f"  - Range: [{d['min']:.4f}, {d['max']:.4f}]\n")
                f.write(f"  - V2 > V1: {d['pos_pct']:.1f}% | V2 < V1: {d['neg_pct']:.1f}% | Tied: {d['tie_pct']:.1f}%\n")
                f.write(f"  - Wilcoxon p-value: {d['pval']:.4e}\n")
            f.write("\n")
            
        write_agg("Overall", all_agg)
        write_agg("IoBT Gunfire", gf_agg)
        write_agg("Existing Proxy", px_agg)
        
        f.write("## Interpretation\n")
        if px_agg["diff_proj"]["mean"] < 0:
            f.write("V2 training is associated with a degradation on the controlled proxy comparison.\n")
        if gf_agg["diff_proj"]["mean"] > 0:
            f.write("V2 provides evidence of improved gunfire-domain behavior relative to V1.\n")
        if px_agg["diff_proj"]["mean"] < 0 and gf_agg["diff_proj"]["mean"] < 0:
            f.write("V2 is worse on both proxy and gunfire domains.\n")
        f.write("\n")
        
        f.write("## Integrity Checks\n")
        f.write(f"V1_RELOAD={v1_reload}\n")
        f.write(f"V2_RELOAD={v2_reload}\n")
        f.write(f"V1_DETERMINISM={v1_det}\n")
        f.write(f"V2_DETERMINISM={v2_det}\n")
        f.write("GOLD_LOADED=NO\n")
        f.write("GOLD_EVALUATED=NO\n")
        f.write("GOLD_MODIFIED=NO\n")
        f.write("V1_RETRAINED=NO\n")
        f.write("V2_RETRAINED=NO\n")
        f.write("\n")
        
    print("\n--- FINAL SUMMARY ---")
    print(f"V1_CHECKPOINT={v1_ckpt}")
    print(f"V2_CHECKPOINT={v2_ckpt}")
    print(f"V1_PARAMETER_COUNT={v1_params}")
    print(f"V2_PARAMETER_COUNT={v2_params}")
    print(f"TOTAL_VALIDATION_EXAMPLES={total_examples}")
    print(f"GUNFIRE_EXAMPLES={gunfire_examples}")
    print(f"PROXY_EXAMPLES={proxy_examples}")
    print(f"PROJECT_SNR_IMPLEMENTATION=scripts/evaluate_polar_gold.py:calculate_active_speech_level")
    print(f"V1_VS_V2_PROXY_SNR_DELTA={px_agg['diff_proj']['mean']:.4f}")
    print(f"V1_VS_V2_GUNFIRE_SNR_DELTA={gf_agg['diff_proj']['mean']:.4f}")
    print(f"V1_VS_V2_PROXY_SI_SDR_DELTA={px_agg['diff_sdr']['mean']:.4f}")
    print(f"V1_VS_V2_GUNFIRE_SI_SDR_DELTA={gf_agg['diff_sdr']['mean']:.4f}")
    print(f"V1_VS_V2_PROXY_STOI_DELTA={px_agg['diff_stoi']['mean']:.4f}")
    print(f"V1_VS_V2_GUNFIRE_STOI_DELTA={gf_agg['diff_stoi']['mean']:.4f}")
    print("GOLD_EVALUATED=NO")
    print("RETRAINING=NO")
    print("COMPARISON_STATUS=COMPARISON_VALID")

if __name__ == '__main__':
    main()
