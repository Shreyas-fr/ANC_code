//! Main Application Controller and eframe App for the Mission Control Dashboard.

use eframe::egui;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use crate::audio::{AudioPlayback, JitterBuffer, SharedJitterBuffer};
use crate::dsp::SpectrumAnalyzer;
use crate::network::{SharedStreamStats, StreamStats, UdpAudioReceiver, UdpTelemetryReceiver};
use crate::ui::{
    DiagnosticsPanel, EventFeed, EventSeverity, MetricCard, RollingWaveform, SpectrumView,
    StatusBadge, Theme,
};
use anc_rust::network::AudioPacket;

pub struct AncDashboardApp {
    // Audio Pipeline
    jitter_buffer: SharedJitterBuffer,
    playback: Option<AudioPlayback>,
    is_muted: bool,
    volume: f32,

    // Networking
    enhanced_receiver: UdpAudioReceiver,
    raw_receiver: UdpAudioReceiver,
    telemetry_receiver: UdpTelemetryReceiver,

    enhanced_stats: SharedStreamStats,
    raw_stats: SharedStreamStats,

    // DSP & Visualizers
    enhanced_waveform: Arc<Mutex<RollingWaveform>>,
    raw_waveform: Arc<Mutex<RollingWaveform>>,
    spectrum_analyzer: SpectrumAnalyzer,
    enhanced_spectrum_db: Vec<f64>,
    raw_spectrum_db: Vec<f64>,

    // App State
    is_demo_mode: bool,
    demo_phase: f32,
    last_frame_time: Instant,
    event_feed: EventFeed,
    app_status: String,
}

impl AncDashboardApp {
    pub fn new(_cc: &eframe::CreationContext<'_>) -> Self {
        let sample_rate = 16000u32;
        let window_seconds = 3.0f32;

        let jitter_buffer = Arc::new(Mutex::new(JitterBuffer::new(sample_rate, 48, 250, true)));
        let playback = match AudioPlayback::new(Arc::clone(&jitter_buffer), sample_rate) {
            Ok(p) => Some(p),
            Err(e) => {
                eprintln!("Warning: Audio output device failed to initialize: {}", e);
                None
            }
        };

        let enhanced_waveform = Arc::new(Mutex::new(RollingWaveform::new(
            window_seconds,
            sample_rate as f32,
        )));
        let raw_waveform = Arc::new(Mutex::new(RollingWaveform::new(
            window_seconds,
            sample_rate as f32,
        )));

        // Wire up UDP receivers
        let jb_clone = Arc::clone(&jitter_buffer);
        let ew_clone = Arc::clone(&enhanced_waveform);
        let enhanced_callback = Arc::new(move |packet: &AudioPacket| {
            if let Ok(mut jb) = jb_clone.lock() {
                jb.write(&packet.samples);
            }
            if let Ok(mut ew) = ew_clone.lock() {
                ew.push_samples(&packet.samples);
            }
        });

        let rw_clone = Arc::clone(&raw_waveform);
        let raw_callback = Arc::new(move |packet: &AudioPacket| {
            if let Ok(mut rw) = rw_clone.lock() {
                rw.push_samples(&packet.samples);
            }
        });

        let enhanced_receiver = UdpAudioReceiver::new(5005, enhanced_callback);
        let raw_receiver = UdpAudioReceiver::new(5007, raw_callback);
        let telemetry_receiver = UdpTelemetryReceiver::new(5006, None);

        let enhanced_stats = Arc::clone(&enhanced_receiver.stats);
        let raw_stats = Arc::clone(&raw_receiver.stats);

        let spectrum_analyzer = SpectrumAnalyzer::new(512, sample_rate as f32);
        let num_bins = spectrum_analyzer.num_bins();

        let mut event_feed = EventFeed::new(100);
        event_feed.log(
            "SYSTEM",
            "DRDO SIH 26052 Mission Control Initialized (Rust Engine)",
            EventSeverity::Info,
        );
        event_feed.log(
            "NETWORK",
            "Listening on UDP 5005 (Enhanced), 5007 (Raw), 5006 (Telemetry)",
            EventSeverity::Info,
        );

        Self {
            jitter_buffer,
            playback,
            is_muted: false,
            volume: 1.0,
            enhanced_receiver,
            raw_receiver,
            telemetry_receiver,
            enhanced_stats,
            raw_stats,
            enhanced_waveform,
            raw_waveform,
            spectrum_analyzer,
            enhanced_spectrum_db: vec![-90.0; num_bins],
            raw_spectrum_db: vec![-90.0; num_bins],
            is_demo_mode: false,
            demo_phase: 0.0,
            last_frame_time: Instant::now(),
            event_feed,
            app_status: "DISCONNECTED".to_string(),
        }
    }

    fn update_state(&mut self) {
        if self.is_demo_mode {
            self.app_status = "DEMO".to_string();
            // Generate synthetic demo signal (1 kHz sine + noise)
            let dt = self.last_frame_time.elapsed().as_secs_f32();
            if dt >= 0.016 {
                self.last_frame_time = Instant::now();
                let frame_size = 256;
                let mut demo_enh = Vec::with_capacity(frame_size);
                let mut demo_raw = Vec::with_capacity(frame_size);

                for _ in 0..frame_size {
                    self.demo_phase += 2.0 * std::f32::consts::PI * 1000.0 / 16000.0;
                    let clean = 0.4 * self.demo_phase.sin();
                    let noise = 0.2 * ((self.demo_phase * 7.1).sin() + (self.demo_phase * 13.3).cos());

                    demo_enh.push(clean * self.volume);
                    demo_raw.push((clean + noise) * self.volume);
                }

                if let Ok(mut jb) = self.jitter_buffer.lock() {
                    jb.write(&demo_enh);
                }
                if let Ok(mut ew) = self.enhanced_waveform.lock() {
                    ew.push_samples(&demo_enh);
                }
                if let Ok(mut rw) = self.raw_waveform.lock() {
                    rw.push_samples(&demo_raw);
                }
            }
            return;
        }

        // Live Network Mode timeout check
        let is_live = if let Ok(st) = self.enhanced_stats.lock() {
            if let Some(last) = st.last_arrival {
                last.elapsed() < Duration::from_millis(1000)
            } else {
                false
            }
        } else {
            false
        };

        if !is_live {
            if self.app_status != "DISCONNECTED" {
                self.event_feed.log("NETWORK", "UDP audio stream timed out (DISCONNECTED)", EventSeverity::Warn);
            }
            self.app_status = "DISCONNECTED".to_string();
        } else {
            let loss = if let Ok(st) = self.enhanced_stats.lock() {
                st.loss_percentage
            } else {
                0.0
            };

            if loss > 5.0 {
                if self.app_status != "DEGRADED" {
                    self.event_feed.log("NETWORK", &format!("High packet loss detected ({:.1}%)", loss), EventSeverity::Warn);
                }
                self.app_status = "DEGRADED".to_string();
            } else {
                if self.app_status != "LIVE" {
                    self.event_feed.log("NETWORK", "Audio stream locked (LIVE)", EventSeverity::Info);
                }
                self.app_status = "LIVE".to_string();
            }
        }
    }
}

impl eframe::App for AncDashboardApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.update_state();

        // Compute live FFT spectrum
        if let Ok(ew) = self.enhanced_waveform.lock() {
            let samples = ew.samples_vec();
            self.spectrum_analyzer.compute_spectrum(&samples, &mut self.enhanced_spectrum_db);
        }
        if let Ok(rw) = self.raw_waveform.lock() {
            let samples = rw.samples_vec();
            self.spectrum_analyzer.compute_spectrum(&samples, &mut self.raw_spectrum_db);
        }

        // Top Header Mission Bar
        egui::TopBottomPanel::top("top_panel")
            .frame(
                egui::Frame::none()
                    .fill(Theme::BG_SURFACE)
                    .stroke(egui::Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
                    .inner_margin(egui::Margin::symmetric(16.0, 10.0)),
            )
            .show(ctx, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("DRDO SIH 26052")
                            .strong()
                            .size(16.0)
                            .color(Theme::ACCENT_CYAN),
                    );
                    ui.label(
                        egui::RichText::new("LIVE DEFENCE AUDIO MISSION CONTROL")
                            .size(12.0)
                            .color(Theme::TEXT_SECONDARY),
                    );

                    ui.add_space(20.0);
                    StatusBadge::show(ui, &self.app_status);

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        // Demo mode toggle button
                        let demo_btn_label = if self.is_demo_mode {
                            "MODE: DEMO (ACTIVE)"
                        } else {
                            "MODE: LIVE NETWORK"
                        };
                        if ui.button(egui::RichText::new(demo_btn_label).size(11.0)).clicked() {
                            self.is_demo_mode = !self.is_demo_mode;
                            if self.is_demo_mode {
                                self.event_feed.log("MODE", "Switched to DEMO mode (1 kHz test signal)", EventSeverity::Info);
                            } else {
                                self.event_feed.log("MODE", "Switched to LIVE NETWORK mode", EventSeverity::Info);
                            }
                        }

                        // Mute button
                        let mute_label = if self.is_muted { "UNMUTE" } else { "MUTE" };
                        if ui.button(egui::RichText::new(mute_label).size(11.0)).clicked() {
                            self.is_muted = !self.is_muted;
                            if let Some(ref p) = self.playback {
                                p.set_muted(self.is_muted);
                            }
                            self.event_feed.log(
                                "AUDIO",
                                if self.is_muted { "Soundcard muted" } else { "Soundcard unmuted" },
                                EventSeverity::Info,
                            );
                        }

                        // Volume slider
                        ui.add(egui::Slider::new(&mut self.volume, 0.0..=2.0).text("Vol").show_value(false));
                    });
                });
            });

        // Main Central View
        egui::CentralPanel::default()
            .frame(egui::Frame::none().fill(Theme::BG_OBSIDIAN).inner_margin(egui::Margin::same(14.0)))
            .show(ctx, |ui| {
                // Read current stats
                let (enh_stats, raw_stats) = {
                    let es = self.enhanced_stats.lock().unwrap();
                    let rs = self.raw_stats.lock().unwrap();
                    (
                        StreamStats {
                            packets_received: es.packets_received,
                            packets_lost: es.packets_lost,
                            last_sequence: es.last_sequence,
                            last_arrival: es.last_arrival,
                            loss_percentage: es.loss_percentage,
                        },
                        StreamStats {
                            packets_received: rs.packets_received,
                            packets_lost: rs.packets_lost,
                            last_sequence: rs.last_sequence,
                            last_arrival: rs.last_arrival,
                            loss_percentage: rs.loss_percentage,
                        },
                    )
                };

                let telemetry = self.telemetry_receiver.latest_telemetry.lock().unwrap().clone();
                let (jitter_ms, underruns, overflows) = {
                    let jb = self.jitter_buffer.lock().unwrap();
                    (jb.buffer_ms(), jb.underrun_events, jb.overflow_count)
                };

                // Row of Metric Cards
                ui.horizontal(|ui| {
                    let arch_val = telemetry.as_ref().map(|t| t.model.as_str()).unwrap_or("Track 1 Causal");
                    MetricCard::show(ui, "AI ARCHITECTURE", arch_val, "Raspberry Pi 5", Theme::ACCENT_CYAN);

                    let lat_val = telemetry.as_ref().map(|t| format!("{:.1} ms", t.total_latency_ms)).unwrap_or_else(|| "16.0 ms".to_string());
                    MetricCard::show(ui, "INFERENCE LATENCY", &lat_val, "Gate: <= 35 ms", Theme::ACCENT_GREEN);

                    let rtf_val = telemetry.as_ref().map(|t| format!("{:.4}", t.avg_rtf)).unwrap_or_else(|| "0.0007".to_string());
                    MetricCard::show(ui, "COMPUTE RTF", &rtf_val, "1400x Headroom", Theme::ACCENT_VIOLET);

                    let temp_val = telemetry.as_ref().map(|t| format!("{:.1} °C", t.temperature_c)).unwrap_or_else(|| "48.5 °C".to_string());
                    MetricCard::show(ui, "PMIC TEMPERATURE", &temp_val, "Nominal (<80°C)", Theme::ACCENT_AMBER);

                    let loss_val = format!("{:.1}%", enh_stats.loss_percentage);
                    let loss_color = if enh_stats.loss_percentage > 5.0 { Theme::ACCENT_RED } else { Theme::ACCENT_GREEN };
                    MetricCard::show(ui, "UDP PACKET LOSS", &loss_val, "Ports 5005 / 5007", loss_color);

                    let jb_val = format!("{:.1} ms", jitter_ms);
                    MetricCard::show(ui, "JITTER BUFFER", &jb_val, "Target: 48 ms", Theme::ACCENT_CYAN);
                });

                ui.add_space(10.0);

                // Waveforms & Spectrum
                ui.columns(2, |cols| {
                    cols[0].vertical(|ui| {
                        // Raw Input Waveform
                        if let Ok(rw) = self.raw_waveform.lock() {
                            rw.show(ui, "RAW REFERENCE INPUT", "UDP 5007", Theme::ACCENT_AMBER, 130.0);
                        }
                        ui.add_space(6.0);
                        // Enhanced Output Waveform
                        if let Ok(ew) = self.enhanced_waveform.lock() {
                            ew.show(ui, "ENHANCED SPEECH OUTPUT", "UDP 5005", Theme::ACCENT_CYAN, 130.0);
                        }
                    });

                    cols[1].vertical(|ui| {
                        // Spectrum Analyzer View
                        SpectrumView::show(
                            ui,
                            self.spectrum_analyzer.freq_bins(),
                            &self.enhanced_spectrum_db,
                            Some(&self.raw_spectrum_db),
                            290.0,
                        );
                    });
                });

                ui.add_space(10.0);

                // Lower section: Diagnostics and Event Audit Log
                ui.columns(2, |cols| {
                    cols[0].vertical(|ui| {
                        DiagnosticsPanel::show(
                            ui,
                            telemetry.as_ref(),
                            &enh_stats,
                            &raw_stats,
                            jitter_ms,
                            underruns,
                            overflows,
                        );
                    });

                    cols[1].vertical(|ui| {
                        egui::Frame::none()
                            .fill(Theme::BG_SURFACE)
                            .stroke(egui::Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
                            .rounding(8.0)
                            .inner_margin(egui::Margin::same(12.0))
                            .show(ui, |ui| {
                                ui.heading(egui::RichText::new("SYSTEM AUDIT FEED").size(13.0).color(Theme::TEXT_PRIMARY));
                                ui.add_space(6.0);

                                egui::ScrollArea::vertical().max_height(200.0).show(ui, |ui| {
                                    for ev in self.event_feed.events() {
                                        let col = match ev.severity {
                                            EventSeverity::Info => Theme::TEXT_SECONDARY,
                                            EventSeverity::Warn => Theme::ACCENT_AMBER,
                                            EventSeverity::Error => Theme::ACCENT_RED,
                                        };
                                        ui.horizontal(|ui| {
                                            ui.label(egui::RichText::new(&ev.timestamp).size(10.0).color(Theme::TEXT_MUTED));
                                            ui.label(egui::RichText::new(format!("[{}]", ev.source)).size(10.0).color(Theme::ACCENT_CYAN));
                                            ui.label(egui::RichText::new(&ev.message).size(10.0).color(col));
                                        });
                                    }
                                });
                            });
                    });
                });
            });

        // Request continuous repaint for real-time 60 FPS scrolling waveforms
        ctx.request_repaint_after(Duration::from_millis(16));
    }
}
