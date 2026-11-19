use std::{env, fs, io::Write, path::PathBuf};
use df::{Complex32, DFState};

fn write_f32(path: PathBuf, values: impl Iterator<Item = f32>) -> std::io::Result<()> {
    let mut file = fs::File::create(path)?;
    for value in values { file.write_all(&value.to_le_bytes())?; }
    Ok(())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    if args.len()!=4 { return Err("usage: dump_frontend INPUT_FLOAT_WAV OUT_DIR ALPHA".into()); }
    let input=PathBuf::from(&args[1]); let out=PathBuf::from(&args[2]); let alpha:f32=args[3].parse()?;
    fs::create_dir_all(&out)?;
    let mut reader=hound::WavReader::open(input)?;
    let spec_wav=reader.spec();
    if spec_wav.sample_rate!=48_000 || spec_wav.channels!=1 || spec_wav.sample_format!=hound::SampleFormat::Float { return Err("expected mono 48kHz IEEE float input".into()); }
    let samples:Vec<f32>=reader.samples::<f32>().collect::<Result<_,_>>()?;
    if samples.len()%480!=0 { return Err("input length must be divisible by 480".into()); }
    let mut state=DFState::new(48_000,960,480,32,2); state.init_norm_states(96);
    let mut specs:Vec<Vec<Complex32>>=Vec::new(); let mut erb_all=Vec::new(); let mut cplx_all=Vec::new();
    for frame in samples.chunks_exact(480) {
        let mut spec=vec![Complex32::default();481]; state.analysis(frame,&mut spec);
        let mut erb=vec![0f32;32]; state.feat_erb(&spec,alpha,&mut erb);
        let mut cplx=vec![Complex32::default();96]; state.feat_cplx(&spec[..96],alpha,&mut cplx);
        specs.push(spec); erb_all.extend(erb); cplx_all.extend(cplx);
    }
    write_f32(out.join("stft.f32"), specs.iter().flat_map(|f|f.iter().flat_map(|c|[c.re,c.im])))?;
    write_f32(out.join("erb_features.f32"), erb_all.into_iter())?;
    write_f32(out.join("complex_features.f32"), cplx_all.iter().flat_map(|c|[c.re,c.im]))?;
    let mut synthesis=DFState::new(48_000,960,480,32,2); let mut output=Vec::with_capacity(samples.len());
    for frame in specs { let mut frame=frame; let mut out_frame=vec![0f32;480]; synthesis.synthesis(&mut frame,&mut out_frame); output.extend(out_frame); }
    write_f32(out.join("synthesis.f32"), output.into_iter())?;
    println!("frames={} samples={} alpha={alpha}",samples.len()/480,samples.len());
    Ok(())
}
