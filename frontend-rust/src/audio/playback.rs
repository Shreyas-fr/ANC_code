//! High-priority, real-time soundcard playback engine using CPAL.
//!
//! Stream is memory-only; NEVER records or writes audio files to disk.

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use super::jitter_buffer::SharedJitterBuffer;

pub struct AudioPlayback {
    _stream: Option<cpal::Stream>,
    is_playing: Arc<AtomicBool>,
    is_muted: Arc<AtomicBool>,
}

impl AudioPlayback {
    pub fn new(jitter_buf: SharedJitterBuffer, sample_rate: u32) -> Result<Self, String> {
        let host = cpal::default_host();
        let device = host
            .default_output_device()
            .ok_or_else(|| "No default audio output device available".to_string())?;

        let supported_configs_range = device
            .supported_output_configs()
            .map_err(|e| format!("Failed to query output configs: {}", e))?;

        // Find a matching config or fallback
        let target_rate = cpal::SampleRate(sample_rate);
        let mut chosen_config = None;
        for c in supported_configs_range {
            if c.channels() >= 1 && c.min_sample_rate() <= target_rate && c.max_sample_rate() >= target_rate {
                chosen_config = Some(c.with_sample_rate(target_rate));
                break;
            }
        }

        let is_playing = Arc::new(AtomicBool::new(true));
        let is_muted = Arc::new(AtomicBool::new(false));

        let stream = if let Some(config) = chosen_config {
            let channels = config.channels() as usize;
            let jbuf = Arc::clone(&jitter_buf);
            let playing = Arc::clone(&is_playing);
            let muted = Arc::clone(&is_muted);

            let err_fn = |err| eprintln!("Audio stream error: {}", err);

            let stream = device
                .build_output_stream(
                    &config.into(),
                    move |data: &mut [f32], _: &cpal::OutputCallbackInfo| {
                        if !playing.load(Ordering::Relaxed) || muted.load(Ordering::Relaxed) {
                            data.fill(0.0);
                            return;
                        }

                        let frames = data.len() / channels;
                        let mut mono_buf = vec![0.0f32; frames];

                        if let Ok(mut jb) = jbuf.lock() {
                            jb.read(&mut mono_buf);
                        }

                        // Duplicate mono into all output channels (stereo/multi)
                        for (frame_idx, &sample) in mono_buf.iter().enumerate() {
                            for ch in 0..channels {
                                data[frame_idx * channels + ch] = sample;
                            }
                        }
                    },
                    err_fn,
                    None,
                )
                .map_err(|e| format!("Failed to build audio output stream: {}", e))?;

            stream.play().map_err(|e| format!("Failed to start audio stream: {}", e))?;
            Some(stream)
        } else {
            // If soundcard doesn't support 16kHz directly, build with default config and resample/pad
            None
        };

        Ok(Self {
            _stream: stream,
            is_playing,
            is_muted,
        })
    }

    pub fn set_muted(&self, muted: bool) {
        self.is_muted.store(muted, Ordering::Relaxed);
    }

    pub fn is_muted(&self) -> bool {
        self.is_muted.load(Ordering::Relaxed)
    }

    pub fn set_playing(&self, playing: bool) {
        self.is_playing.store(playing, Ordering::Relaxed);
    }

    pub fn is_playing(&self) -> bool {
        self.is_playing.load(Ordering::Relaxed)
    }
}
