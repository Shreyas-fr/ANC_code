use rubato::{FftFixedInOut, Resampler};
use std::{env, fs, io, path::PathBuf};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    if args.len() != 5 {
        return Err("usage: stage25-rubato-resample INPUT.raw OUTPUT.raw INPUT_HZ OUTPUT_HZ".into());
    }
    let input_path = PathBuf::from(&args[1]);
    let output_path = PathBuf::from(&args[2]);
    let input_rate: usize = args[3].parse()?;
    let output_rate: usize = args[4].parse()?;
    let bytes = fs::read(input_path)?;
    if bytes.len() % 4 != 0 {
        return Err("input raw file length must be divisible by sizeof(f32)".into());
    }
    let input: Vec<f32> = bytes
        .chunks_exact(4)
        .map(|b| f32::from_le_bytes([b[0], b[1], b[2], b[3]]))
        .collect();
    let out_len = ((input.len() as f64 * output_rate as f64) / input_rate as f64).ceil() as usize;
    let mut resampler = FftFixedInOut::<f32>::new(input_rate, output_rate, 2048, 1)?;
    let chunk_in = resampler.input_frames_max();
    let chunk_out = resampler.output_frames_max();
    let mut inbuf = resampler.input_buffer_allocate(true);
    let mut outbuf = resampler.output_buffer_allocate(true);
    let mut rendered = Vec::new();
    for chunk in input.chunks(chunk_in) {
        let channel = &mut inbuf[0];
        channel[..chunk.len()].copy_from_slice(chunk);
        channel[chunk.len()..].fill(0.0);
        resampler.process_into_buffer(&inbuf, &mut outbuf, None)?;
        rendered.extend_from_slice(&outbuf[0][..chunk_out]);
    }
    inbuf[0].fill(0.0);
    resampler.process_into_buffer(&inbuf, &mut outbuf, None)?;
    rendered.extend_from_slice(&outbuf[0][..chunk_out]);

    // Match libDF transforms::resample: discard half of one output chunk as
    // resampler startup padding, then retain the ceil-ratio output length.
    let start = chunk_out / 2;
    let end = start + out_len;
    if rendered.len() < end {
        return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "Rubato output shorter than requested crop").into());
    }
    let mut output = Vec::with_capacity(out_len * 4);
    for sample in &rendered[start..end] {
        output.extend_from_slice(&sample.to_le_bytes());
    }
    fs::write(output_path, output)?;
    Ok(())
}
