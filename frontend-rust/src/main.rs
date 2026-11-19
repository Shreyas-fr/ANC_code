//! SIH 26052 Live Defence Communication Desktop Dashboard (Rust Native).
//!
//! Real-Time Audio Playback, DSP Waveform Visualization, FFT Spectrum,
//! Telemetry Monitoring, and Network Diagnostics.

#![allow(dead_code)]

use clap::Parser;
use eframe::egui;

mod app;
mod audio;
mod dsp;
mod network;
mod ui;

use app::AncDashboardApp;

#[derive(Parser, Debug)]
#[command(
    name = "anc-frontend",
    author = "DRDO SIH 26052 Team",
    version = "0.1.0",
    about = "DRDO SIH 26052 Edge-AI Audio Mission Control Desktop Dashboard"
)]
struct Args {
    #[arg(long, default_value_t = 5005)]
    audio_port: u16,

    #[arg(long, default_value_t = 5006)]
    telemetry_port: u16,

    #[arg(long, default_value_t = 5007)]
    input_port: u16,

    #[arg(long, default_value_t = 16000)]
    sample_rate: u32,

    #[arg(long, default_value_t = false)]
    demo: bool,
}

fn main() -> Result<(), eframe::Error> {
    let _args = Args::parse();

    println!("============================================================");
    println!("  DRDO SIH 26052 LIVE DEFENCE DASHBOARD (RUST NATIVE)");
    println!("============================================================");
    println!("Streaming Ports: Enhanced: 5005, Telemetry: 5006, Raw: 5007");
    println!("Audio Playback:  Real-Time CPAL Soundcard Stream (Memory-Only)");
    println!("Launching GPU-Accelerated Desktop Mission Control Window...");

    let native_options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("SIH 26052 Edge-AI Audio Mission Control")
            .with_inner_size([1280.0, 820.0])
            .with_min_inner_size([1000.0, 700.0]),
        ..Default::default()
    };

    eframe::run_native(
        "SIH 26052 Mission Control",
        native_options,
        Box::new(|cc| Ok(Box::new(AncDashboardApp::new(cc)))),
    )
}
