use std::{env, fs, io::Write, path::PathBuf};
use tract_core::prelude::*;
use tract_onnx::prelude::*;

fn load_f32(path: &str) -> anyhow::Result<Vec<f32>> {
    let bytes=fs::read(path)?;
    if bytes.len()%4!=0 { anyhow::bail!("f32 file size is not divisible by four"); }
    Ok(bytes.chunks_exact(4).map(|b| f32::from_le_bytes([b[0],b[1],b[2],b[3]])).collect())
}
fn save_tensor(path: PathBuf, v: &TValue) -> anyhow::Result<()> {
    let mut f=fs::File::create(path)?;
    for &x in v.to_array_view::<f32>()?.iter() { f.write_all(&x.to_le_bytes())?; }
    Ok(())
}
fn main() -> anyhow::Result<()> {
    let a:Vec<String>=env::args().collect();
    if a.len()!=5 { anyhow::bail!("usage: dump_enc_full_sequence ENC.onnx ERB.f32 COMPLEX.f32 OUT_DIR"); }
    let out=PathBuf::from(&a[4]);fs::create_dir_all(&out)?;
    let mut erb=load_f32(&a[2])?;
    let cplx_interleaved=load_f32(&a[3])?;
    if erb.len()!=300*32 || cplx_interleaved.len()!=300*96*2 { anyhow::bail!("expected 300 feature frames"); }
    let mut cplx=vec![0f32;2*300*96];
    for t in 0..300 { for f in 0..96 {
        let src=(t*96+f)*2;
        cplx[t*96+f]=cplx_interleaved[src];
        cplx[300*96+t*96+f]=cplx_interleaved[src+1];
    }}
    // Match Python pad_feat=(0,0,-2,+2): drop first two and zero-pad the end.
    erb.copy_within(2*32..,0);erb[298*32..].fill(0.0);
    for ch in 0..2 {
        let off=ch*300*96;
        cplx.copy_within(off+2*96..off+300*96,off);
        cplx[off+298*96..off+300*96].fill(0.0);
    }
    let mut model=tract_onnx::onnx().model_for_path(&a[1])?;
    model=model
        .with_input_fact(0,InferenceFact::dt_shape(f32::datum_type(),tvec!(1,1,300,32)))?
        .with_input_fact(1,InferenceFact::dt_shape(f32::datum_type(),tvec!(1,2,300,96)))?
        .with_input_names(["feat_erb","feat_spec"])?
        .with_output_names(["e0","e1","e2","e3","emb","c0","lsnr"])?;
    let runnable=model.into_typed()?.into_optimized()?.into_runnable()?;
    let erb_tensor=Tensor::from_shape(&[1,1,300,32],&erb)?;
    let cplx_tensor=Tensor::from_shape(&[1,2,300,96],&cplx)?;
    let outputs=runnable.run(tvec!(erb_tensor.into_tvalue(),cplx_tensor.into_tvalue()))?;
    for (i,v) in outputs.iter().enumerate() { save_tensor(out.join(format!("enc_output_{i}.f32")),v)?; }
    println!("outputs={} frames=300 unpulsed=true",outputs.len());
    Ok(())
}
