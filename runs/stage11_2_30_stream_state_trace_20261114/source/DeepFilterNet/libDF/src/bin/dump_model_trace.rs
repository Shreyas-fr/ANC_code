use std::{env, path::PathBuf};
use df::{tract::*, wav_utils::*};
use ndarray::{ArrayD, Axis};

fn main() -> anyhow::Result<()> {
    let a: Vec<String> = env::args().collect();
    if a.len() != 3 { anyhow::bail!("usage: dump_model_trace MODEL.tar.gz INPUT_48K_FLOAT.wav"); }
    let model_params = DfParams::new(PathBuf::from(&a[1]))?;
    let runtime = RuntimeParams::default();
    let mut model = DfTract::new(model_params, &runtime)?;
    let input = ReadWav::new(&a[2])?;
    if input.sr != 48_000 || input.channels != 1 { anyhow::bail!("expected mono 48 kHz WAV"); }
    let samples = input.samples_arr2()?;
    let noisy = samples.as_standard_layout();
    if noisy.len_of(Axis(1)) % model.hop_size != 0 { anyhow::bail!("sample count not hop aligned"); }
    let mut enhanced: ndarray::Array2<f32> = ArrayD::default(noisy.shape()).into_dimensionality()?;
    for (x, y) in noisy.view().axis_chunks_iter(Axis(1), model.hop_size)
        .zip(enhanced.view_mut().axis_chunks_iter_mut(Axis(1), model.hop_size)) {
        model.process(x, y)?;
    }
    println!("frames={} sr={} hop={} lookahead={}", noisy.len_of(Axis(1))/model.hop_size, model.sr, model.hop_size, model.lookahead);
    Ok(())
}
