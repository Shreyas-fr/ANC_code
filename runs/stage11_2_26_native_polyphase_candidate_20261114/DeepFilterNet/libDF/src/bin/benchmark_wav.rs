use std::{path::PathBuf, process::exit, time::Instant};
use anyhow::Result;
use clap::{Parser, ValueHint};
use df::{tract::*, transforms::resample, wav_utils::*};
use ndarray::{prelude::*, Axis};

#[cfg(all(
    not(windows),
    not(target_os = "android"),
    not(target_os = "macos"),
    not(target_os = "freebsd"),
    not(target_env = "musl"),
    not(target_arch = "riscv64"),
    feature = "use-jemalloc"
))]
#[global_allocator]
static ALLOC: jemallocator::Jemalloc = jemallocator::Jemalloc;

#[derive(Parser)]
#[command(author, version, about, long_about = None)]
struct Args {
    #[arg(short, long, value_hint = ValueHint::FilePath)]
    model: Option<PathBuf>,
    #[arg(long = "pf")]
    post_filter: bool,
    #[arg(long = "pf-beta", default_value_t = 0.02)]
    post_filter_beta: f32,
    #[arg(short, long, default_value_t = 100.)]
    atten_lim_db: f32,
    #[arg(long, default_value = "out", value_hint = ValueHint::DirPath)]
    output_dir: PathBuf,
    #[arg(required = true)]
    files: Vec<PathBuf>,
}

fn main() -> Result<()> {
    let args = Args::parse();
    
    let mut r_params = RuntimeParams::default();
    r_params = r_params.with_atten_lim(args.atten_lim_db);
    if args.post_filter {
        r_params = r_params.with_post_filter(args.post_filter_beta);
    }
    
    let df_params = if let Some(tar) = args.model.as_ref() {
        DfParams::new(tar.clone()).unwrap()
    } else {
        DfParams::default()
    };
    
    let mut model: DfTract = DfTract::new(df_params.clone(), &r_params)?;
    let mut sr = model.sr;
    let delay = model.fft_size - model.hop_size + model.lookahead * model.hop_size;
    
    if !args.output_dir.is_dir() {
        std::fs::create_dir_all(args.output_dir.clone())?;
    }
    
    for file in args.files {
        let reader = ReadWav::new(file.to_str().unwrap())?;
        if r_params.n_ch != reader.channels {
            r_params.n_ch = reader.channels;
            model = DfTract::new(df_params.clone(), &r_params)?;
            sr = model.sr;
        }
        let sample_sr = reader.sr;
        let mut noisy = reader.samples_arr2()?;
        if sr != sample_sr {
            noisy = resample(noisy.view(), sample_sr, sr, None).expect("Error during resample");
        }
        let noisy = noisy.as_standard_layout();
        let mut enh: Array2<f32> = ArrayD::default(noisy.shape()).into_dimensionality()?;
        
        let mut latencies_ms = Vec::new();
        
        for (ns_f, enh_f) in noisy
            .view()
            .axis_chunks_iter(Axis(1), model.hop_size)
            .zip(enh.view_mut().axis_chunks_iter_mut(Axis(1), model.hop_size))
        {
            if ns_f.len_of(Axis(1)) < model.hop_size {
                break;
            }
            let t0 = Instant::now();
            model.process(ns_f, enh_f)?;
            latencies_ms.push(t0.elapsed().as_secs_f64() * 1000.0);
        }
        
        // Print latencies to CSV format on stdout
        println!("frame_idx,latency_ms");
        for (i, l) in latencies_ms.iter().enumerate() {
            println!("{},{:.4}", i, l);
        }
        
        let mut enh_file = args.output_dir.clone();
        enh_file.push(file.file_name().unwrap());
        enh.slice_axis_inplace(Axis(1), ndarray::Slice::from(delay..));
        if sr != sample_sr {
            enh = resample(enh.view(), sr, sample_sr, None).expect("Error during resample");
        }
        write_wav_arr2(enh_file.to_str().unwrap(), enh.view(), sample_sr as u32)?;
    }
    
    Ok(())
}
