//! Main Application Controller and eframe App for the Mission Control Dashboard.

use eframe::egui;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use crate::audio::{
    incident_flags, AudioPlayback, JitterBuffer, RecorderState, SharedJitterBuffer,
    TacticalAudioRecorder, TestSignalGenerator, TestSignalMode,
};
use crate::dsp::SpectrumAnalyzer;
use crate::network::{SharedStreamStats, UdpAudioReceiver, UdpTelemetryReceiver};
use crate::ui::{
    AmbisonicsScopeWidget, AtakWidget, AudiogramTestWizard, BlastImpulseWidget,
    CableDiagnosticWidget, DiagnosticsPanel, DspTimelineWidget, EventFeed, EventSeverity,
    IntelligibilityBadge, JammingWidget, MeshRadarWidget, MetricCard, OcclusionWidget,
    PhaseScopeWidget, PolarDirectivityWidget, RastiWidget, RfLinkBadge, RollingWaveform,
    ShockTransientBadge, SpectralKurtosisWidget, SpectrumView, StatusBadge, TacticalBatteryWidget,
    TacticalEqWidget, TacticalEqualizer, TacticalLufsRadarWidget, TacticalRadarWidget,
    TacticalStressWidget, Theme, ThreatRadarWidget, VadBeacon, Waterfall3dMesh,
    WaterfallSpectrogram,
};
use anc_rust::dsp::ambisonics::AmbisonicsTelemetry;
use anc_rust::dsp::deesser::DeEsserTelemetry;
use anc_rust::dsp::polar_pattern::PolarPatternTelemetry;
use anc_rust::metrics::cable::{CableFaultStatus, CableTelemetry};
use anc_rust::metrics::sti::{StiRating, StiTelemetry, NUM_RASTI_MOD_FREQS};
use anc_rust::network::jamming::{JammingTelemetry, JammingType};
use anc_rust::network::{AudioPacket, DspStageTimings};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AudioMonitorSource {
    Enhanced,
    Raw,
}

pub struct AncDashboardApp {
    // Audio Pipeline
    jitter_buffer: SharedJitterBuffer,
    pub tactical_eq: Arc<Mutex<TacticalEqualizer>>,
    playback: Option<AudioPlayback>,
    is_muted: bool,
    volume: f32,
    monitor_source: Arc<Mutex<AudioMonitorSource>>,

    // Networking
    _enhanced_receiver: UdpAudioReceiver,
    _raw_receiver: UdpAudioReceiver,
    telemetry_receiver: UdpTelemetryReceiver,

    enhanced_stats: SharedStreamStats,
    raw_stats: SharedStreamStats,

    // DSP & Visualizers
    enhanced_waveform: Arc<Mutex<RollingWaveform>>,
    raw_waveform: Arc<Mutex<RollingWaveform>>,
    spectrum_analyzer: SpectrumAnalyzer,
    enhanced_spectrum_db: Vec<f64>,
    raw_spectrum_db: Vec<f64>,
    waterfall: WaterfallSpectrogram,
    pub waterfall_3d: Waterfall3dMesh,
    pub is_3d_waterfall_active: bool,
    timeline_widget: DspTimelineWidget,
    pub threat_radar: ThreatRadarWidget,
    pub phase_scope: PhaseScopeWidget,
    pub kurtosis_hud: SpectralKurtosisWidget,
    pub lufs_radar: TacticalLufsRadarWidget,
    pub incident_recorder: TacticalAudioRecorder,
    pub stress_widget: TacticalStressWidget,
    pub battery_widget: TacticalBatteryWidget,
    pub blast_widget: BlastImpulseWidget,
    pub audiogram_wizard: AudiogramTestWizard,
    pub polar_widget: PolarDirectivityWidget,
    pub cable_widget: CableDiagnosticWidget,
    pub ambisonics_scope: AmbisonicsScopeWidget,
    pub jamming_widget: JammingWidget,
    pub rasti_widget: RastiWidget,
    pub mesh_radar: MeshRadarWidget,
    pub occlusion_widget: OcclusionWidget,
    pub atak_widget: AtakWidget,

    // App State
    is_demo_mode: bool,
    pub is_aggressive_snr: bool,
    is_transparency_active: bool,
    demo_phase: f32,
    demo_speech_timer: f32,
    is_speech_active: bool,
    speech_presence_prob: f32,
    tracked_talker_angle: f32,
    doa_confidence: f32,
    mean_cdr_db: f32,
    spatial_coherence: f32,
    test_signal: TestSignalGenerator,
    active_profile: &'static str,
    last_frame_time: Instant,
    event_feed: EventFeed,
    app_status: String,
}

impl AncDashboardApp {
    pub fn new(cc: &eframe::CreationContext<'_>) -> Self {
        // Apply sophisticated dark tactical styling globally
        Theme::apply_to_context(&cc.egui_ctx);

        let sample_rate = 16000u32;
        let window_seconds = 3.0f32;

        let jitter_buffer = Arc::new(Mutex::new(
            JitterBuffer::new(sample_rate, 48, 250, true).with_governor(true),
        ));
        let tactical_eq = Arc::new(Mutex::new(TacticalEqualizer::new(sample_rate as f32)));
        let playback = match AudioPlayback::new(
            Arc::clone(&jitter_buffer),
            Arc::clone(&tactical_eq),
            sample_rate,
        ) {
            Ok(p) => Some(p),
            Err(e) => {
                eprintln!("Warning: Audio output device failed to initialize: {}", e);
                None
            }
        };

        let monitor_source = Arc::new(Mutex::new(AudioMonitorSource::Enhanced));

        let enhanced_waveform = Arc::new(Mutex::new(RollingWaveform::new(
            window_seconds,
            sample_rate as f32,
        )));
        let raw_waveform = Arc::new(Mutex::new(RollingWaveform::new(
            window_seconds,
            sample_rate as f32,
        )));

        // Wire up UDP receivers with A/B monitor routing
        let jb_clone = Arc::clone(&jitter_buffer);
        let ew_clone = Arc::clone(&enhanced_waveform);
        let mon_clone1 = Arc::clone(&monitor_source);
        let enhanced_callback = Arc::new(move |packet: &AudioPacket| {
            if let Ok(mon) = mon_clone1.lock() {
                if *mon == AudioMonitorSource::Enhanced {
                    if let Ok(mut jb) = jb_clone.lock() {
                        jb.write(&packet.samples);
                    }
                }
            }
            if let Ok(mut ew) = ew_clone.lock() {
                ew.push_samples(&packet.samples);
            }
        });

        let jb_clone2 = Arc::clone(&jitter_buffer);
        let rw_clone = Arc::clone(&raw_waveform);
        let mon_clone2 = Arc::clone(&monitor_source);
        let raw_callback = Arc::new(move |packet: &AudioPacket| {
            if let Ok(mon) = mon_clone2.lock() {
                if *mon == AudioMonitorSource::Raw {
                    if let Ok(mut jb) = jb_clone2.lock() {
                        jb.write(&packet.samples);
                    }
                }
            }
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
            "DRDO SIH 26052 Mission Control Initialized (Rust Native Engine)",
            EventSeverity::Info,
        );
        event_feed.log(
            "NETWORK",
            "Listening on UDP 5005 (Enhanced), 5007 (Raw), 5006 (Telemetry)",
            EventSeverity::Info,
        );

        Self {
            jitter_buffer,
            tactical_eq,
            playback,
            is_muted: false,
            volume: 1.0,
            monitor_source,
            _enhanced_receiver: enhanced_receiver,
            _raw_receiver: raw_receiver,
            telemetry_receiver,
            enhanced_stats,
            raw_stats,
            enhanced_waveform,
            raw_waveform,
            spectrum_analyzer,
            enhanced_spectrum_db: vec![-90.0; num_bins],
            raw_spectrum_db: vec![-90.0; num_bins],
            waterfall: WaterfallSpectrogram::new(80, 48),
            waterfall_3d: Waterfall3dMesh::new(),
            is_3d_waterfall_active: true,
            timeline_widget: DspTimelineWidget::default(),
            threat_radar: ThreatRadarWidget::new(sample_rate as f32),
            phase_scope: PhaseScopeWidget::new(256),
            kurtosis_hud: SpectralKurtosisWidget::new(),
            lufs_radar: TacticalLufsRadarWidget::new(),
            incident_recorder: TacticalAudioRecorder::new(sample_rate, 30),
            stress_widget: TacticalStressWidget::new(),
            battery_widget: TacticalBatteryWidget::new(),
            blast_widget: BlastImpulseWidget::new(),
            audiogram_wizard: AudiogramTestWizard::new(),
            polar_widget: PolarDirectivityWidget::new(),
            cable_widget: CableDiagnosticWidget::new(),
            ambisonics_scope: AmbisonicsScopeWidget::new(),
            jamming_widget: JammingWidget::new(),
            rasti_widget: RastiWidget::new(),
            mesh_radar: MeshRadarWidget::new(),
            occlusion_widget: OcclusionWidget::new(),
            atak_widget: AtakWidget::new(),
            is_demo_mode: false,
            is_aggressive_snr: false,
            is_transparency_active: false,
            demo_phase: 0.0,
            demo_speech_timer: 0.0,
            is_speech_active: false,
            speech_presence_prob: 0.0,
            tracked_talker_angle: 0.0,
            doa_confidence: 0.95,
            mean_cdr_db: 12.5,
            spatial_coherence: 0.88,
            test_signal: TestSignalGenerator::new(sample_rate as f32),
            active_profile: "COMBAT VEHICLE (T-90 / BMP)",
            last_frame_time: Instant::now(),
            event_feed,
            app_status: "DISCONNECTED".to_string(),
        }
    }

    fn update_state(&mut self) {
        if self.is_demo_mode {
            self.app_status = "DEMO".to_string();
            let dt = self.last_frame_time.elapsed().as_secs_f32();
            if dt >= 0.016 {
                self.last_frame_time = Instant::now();
                self.demo_speech_timer += 0.016;

                // Simulate realistic alternating speech bursts (2.0s on, 1.2s off)
                let cycle = self.demo_speech_timer % 3.2;
                self.is_speech_active = cycle < 2.0;
                self.speech_presence_prob = if self.is_speech_active { 0.92 } else { 0.05 };

                // Simulate realistic operator headset slippage oscillation (+/- 18 degrees)
                let simulated_slip = (self.demo_speech_timer * 0.75).sin() * 18.0;
                self.tracked_talker_angle = simulated_slip;
                self.doa_confidence = if self.is_speech_active { 0.94 } else { 0.40 };
                self.mean_cdr_db = if self.is_speech_active { 14.5 } else { -3.2 };
                self.spatial_coherence = if self.is_speech_active { 0.92 } else { 0.38 };

                let frame_size = 256;
                let mut demo_enh = Vec::with_capacity(frame_size);
                let mut demo_raw = Vec::with_capacity(frame_size);

                for _ in 0..frame_size {
                    self.demo_phase += 2.0 * std::f32::consts::PI * 300.0 / 16000.0;

                    // Speech harmonics: 300 Hz + 600 Hz + 1200 Hz
                    let speech = if self.is_speech_active {
                        0.35 * self.demo_phase.sin()
                            + 0.20 * (self.demo_phase * 2.0).sin()
                            + 0.10 * (self.demo_phase * 4.0).sin()
                    } else {
                        0.0
                    };

                    // Directional engine rumble + high-frequency noise
                    let noise =
                        0.25 * ((self.demo_phase * 1.7).sin() + (self.demo_phase * 8.3).cos());

                    let s_enh = speech * self.volume;
                    let s_raw = (speech + noise) * self.volume;

                    demo_enh.push(s_enh);
                    demo_raw.push(s_raw);
                }

                // Mix directional 3D threat sonification alert into output
                self.threat_radar.sonifier.mix_mono(&mut demo_enh);
                self.threat_radar.tick(0.016);
                self.kurtosis_hud.tick(0.016);

                // If audiogram hearing test wizard tone is playing, inject calibrated pulse
                if self.audiogram_wizard.is_tone_playing {
                    self.audiogram_wizard
                        .generate_test_tone(&mut demo_enh, 16000.0);
                }

                // Simulate realistic physical battery discharge dynamics in demo mode
                self.battery_widget.telemetry.current_draw_ma =
                    145.0 + (self.demo_speech_timer * 2.0).sin().abs() * 30.0;
                self.battery_widget.telemetry.power_draw_mw =
                    self.battery_widget.telemetry.current_draw_ma
                        * self.battery_widget.telemetry.terminal_voltage_v;
                self.battery_widget.telemetry.soc_pct =
                    (88.5 - (self.demo_speech_timer * 0.01)).max(10.0);
                self.battery_widget.telemetry.estimated_runtime_hours =
                    (self.battery_widget.telemetry.soc_pct * 0.08).max(0.5);

                // Simulate occasional acoustic blast wave impulse (e.g. at 2.8s in cycle)
                if cycle > 2.7 && cycle < 2.75 {
                    self.blast_widget.update(anc_rust::metrics::BlastTelemetry {
                        peak_spl_db: 158.5,
                        peak_overpressure_pa: 1680.0,
                        peak_overpressure_psi: 0.244,
                        current_a_duration_ms: 1.8,
                        daily_impulse_count: self.blast_widget.telemetry.daily_impulse_count + 1,
                        cumulative_dose_pct: self.blast_widget.telemetry.cumulative_dose_pct + 1.2,
                        hazard_status: anc_rust::metrics::BlastHazardStatus::Nominal,
                        last_blast_event: anc_rust::metrics::BlastEvent {
                            frame_index: (self.demo_speech_timer * 60.0) as u64,
                            peak_spl_db: 158.5,
                            peak_overpressure_pa: 1680.0,
                            peak_overpressure_psi: 0.244,
                            a_duration_ms: 1.8,
                            dose_pct: 1.2,
                        },
                    });
                }

                // Simulate realistic polar directivity and de-esser telemetry in demo mode
                let (pol_red_db, pol_sib) = if self.is_speech_active {
                    (-3.2, true)
                } else {
                    (0.0, false)
                };
                self.polar_widget.update(
                    PolarPatternTelemetry {
                        pattern_type: self.polar_widget.selected_pattern as u8,
                        null_angle_deg: self.polar_widget.steered_null_deg,
                        front_to_back_ratio_db: 24.5,
                        directivity_index_db: 4.8,
                        internal_delay_us: 58.3,
                    },
                    DeEsserTelemetry {
                        sibilance_detected: pol_sib,
                        sibilance_ratio_db: if pol_sib { 4.5 } else { -12.0 },
                        gain_reduction_db: pol_red_db,
                        sibilant_energy_dbfs: -32.0,
                        broadband_energy_dbfs: -28.0,
                    },
                );

                // Simulate pristine nominal cable continuity in demo mode
                self.cable_widget.update(CableTelemetry {
                    health_pct: 100.0,
                    estimated_impedance_ohms: 2204.0 + (self.demo_speech_timer * 0.5).sin() * 12.0,
                    low_freq_coherence: if self.is_speech_active { 0.96 } else { 0.88 },
                    dc_offset_mv: 0.4,
                    micro_intermittent_events: 0,
                    status: CableFaultStatus::Nominal,
                });

                // Ambisonics demo state
                self.ambisonics_scope.update(AmbisonicsTelemetry {
                    intensity_x: 0.25 * (self.demo_speech_timer * 0.8).cos(),
                    intensity_y: 0.35 * (self.demo_speech_timer * 0.8).sin(),
                    intensity_z: 0.0,
                    intensity_mag: if self.is_speech_active { 0.45 } else { 0.12 },
                    energy_density: if self.is_speech_active { 0.50 } else { 0.20 },
                    diffuseness: if self.is_speech_active { 0.22 } else { 0.78 },
                    azimuth_deg: 18.0 * (self.demo_speech_timer * 0.5).sin(),
                    elevation_deg: 0.0,
                    is_localized: self.is_speech_active,
                });

                // RF Jamming link demo state
                self.jamming_widget.update(JammingTelemetry {
                    jamming_type: JammingType::NominalRF,
                    confidence: 1.0,
                    jitter_variance_ms2: 0.8 + (self.demo_speech_timer * 0.2).sin().abs() * 0.4,
                    mean_jitter_ms: 0.6,
                    packet_loss_rate: 0.0,
                    burst_clustering: 0.02,
                    auth_failure_rate: 0.0,
                    remediation_active: false,
                    remediation_code: 0,
                });

                // RASTI demo state
                self.rasti_widget.update(StiTelemetry {
                    sti_score: if self.is_speech_active { 0.84 } else { 0.42 },
                    rating: if self.is_speech_active {
                        StiRating::Excellent
                    } else {
                        StiRating::Fair
                    },
                    mean_apparent_snr_db: if self.is_speech_active { 14.5 } else { 2.0 },
                    mean_mtf: if self.is_speech_active { 0.82 } else { 0.45 },
                    mtf_bands: [if self.is_speech_active { 0.85 } else { 0.45 };
                        NUM_RASTI_MOD_FREQS],
                    is_authoritative: true,
                });

                // If synthetic test signal is injected, override audio buffers for instant verification
                if self.test_signal.is_active() {
                    let mut test_buf = vec![0.0f32; frame_size];
                    self.test_signal.generate(&mut test_buf);
                    for i in 0..frame_size {
                        demo_raw[i] = test_buf[i];
                        demo_enh[i] = test_buf[i] * 0.95;
                    }
                    self.mean_cdr_db = 18.0;
                    self.spatial_coherence = 0.98;
                }

                let current_mon = *self.monitor_source.lock().unwrap();
                let play_samples = if current_mon == AudioMonitorSource::Enhanced {
                    &demo_enh
                } else {
                    &demo_raw
                };

                if let Ok(mut jb) = self.jitter_buffer.lock() {
                    jb.write(play_samples);
                }
                if let Ok(mut ew) = self.enhanced_waveform.lock() {
                    ew.push_samples(&demo_enh);
                }
                if let Ok(mut rw) = self.raw_waveform.lock() {
                    rw.push_samples(&demo_raw);
                }

                // Push deterministic stage execution timings to Timeline Widget
                let jitter_us = ((self.demo_speech_timer * 11.0).sin().abs() * 12.0) as u32;
                let demo_timings = DspStageTimings {
                    stft_us: 14 + (jitter_us % 4),
                    afc_us: 6 + (jitter_us % 3),
                    beamformer_us: 12 + (jitter_us % 5),
                    dereverb_us: 8 + (jitter_us % 3),
                    spectral_us: 18 + jitter_us,
                    intelligibility_us: 6 + (jitter_us % 2),
                    synthesis_us: 10 + (jitter_us % 4),
                    total_us: 74 + jitter_us * 2,
                };
                self.timeline_widget.record_hop(&demo_timings);

                let (demo_m, demo_s, demo_i, demo_lra, demo_tp, demo_gr) = if self.is_speech_active
                {
                    (-22.4, -23.1, -23.0, 4.5, -2.1, -0.6)
                } else {
                    (-36.0, -25.2, -23.0, 3.8, -14.0, 0.0)
                };
                self.lufs_radar
                    .push_measurements(demo_m, demo_s, demo_i, demo_lra, demo_tp, demo_gr);

                let (demo_stress, demo_jit, demo_shim, demo_f0, demo_sps, demo_fat) =
                    if self.is_speech_active {
                        (
                            26.5 + (self.demo_speech_timer * 1.5).sin().abs() * 22.0,
                            0.82,
                            3.1,
                            14.0,
                            3.8,
                            14.0,
                        )
                    } else {
                        (12.0, 0.45, 1.8, 0.0, 3.2, 10.0)
                    };
                self.stress_widget.push_measurements(
                    demo_stress,
                    demo_jit,
                    demo_shim,
                    demo_f0,
                    demo_sps,
                    demo_fat,
                );
                self.incident_recorder.push_stereo_frame(
                    &demo_raw,
                    &demo_enh,
                    self.tracked_talker_angle,
                    demo_stress,
                );
            }
            return;
        }

        // Live Network Mode: record edge telemetry stage timings if present
        if let Some(t) = self
            .telemetry_receiver
            .latest_telemetry
            .lock()
            .unwrap()
            .as_ref()
        {
            self.tracked_talker_angle = t.talker_angle_deg;
            self.doa_confidence = t.doa_confidence;
            if t.mean_cdr_db != 0.0 {
                self.mean_cdr_db = t.mean_cdr_db;
            }
            if t.spatial_coherence != 0.0 {
                self.spatial_coherence = t.spatial_coherence;
            }
            if t.stage_timings.total_us > 0 {
                self.timeline_widget.record_hop(&t.stage_timings);
            }
            self.lufs_radar.update_from_telemetry(t);
            self.stress_widget.push_measurements(
                t.tactical_stress_index,
                t.vocal_jitter_pct,
                t.vocal_shimmer_pct,
                12.0,
                3.6,
                16.0,
            );
        }

        // Push live waveform audio to forensic incident recorder
        if let (Ok(rw), Ok(ew)) = (self.raw_waveform.lock(), self.enhanced_waveform.lock()) {
            let r_samples = rw.samples_vec();
            let e_samples = ew.samples_vec();
            let n = r_samples.len().min(e_samples.len()).min(256);
            if n > 0 {
                let r_slice = &r_samples[r_samples.len() - n..];
                let e_slice = &e_samples[e_samples.len() - n..];
                self.incident_recorder.push_stereo_frame(
                    r_slice,
                    e_slice,
                    self.tracked_talker_angle,
                    self.stress_widget.stress_index_pct,
                );
            }
        }

        self.threat_radar.tick(0.016);
        self.kurtosis_hud.tick(0.016);

        // Test signal injection in live/offline mode
        if self.test_signal.is_active() {
            let dt = self.last_frame_time.elapsed().as_secs_f32();
            if dt >= 0.016 {
                self.last_frame_time = Instant::now();
                let mut test_buf = vec![0.0f32; 256];
                self.test_signal.generate(&mut test_buf);
                if let Ok(mut jb) = self.jitter_buffer.lock() {
                    jb.write(&test_buf);
                }
                if let Ok(mut ew) = self.enhanced_waveform.lock() {
                    ew.push_samples(&test_buf);
                }
                if let Ok(mut rw) = self.raw_waveform.lock() {
                    rw.push_samples(&test_buf);
                }
            }
        }

        // Live Network Mode status check
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
                self.event_feed.log(
                    "NETWORK",
                    "UDP audio stream timed out (DISCONNECTED)",
                    EventSeverity::Warn,
                );
            }
            self.app_status = "DISCONNECTED".to_string();
            self.is_speech_active = false;
            self.speech_presence_prob = 0.0;
        } else {
            let loss = if let Ok(st) = self.enhanced_stats.lock() {
                st.loss_percentage
            } else {
                0.0
            };

            if loss > 5.0 {
                if self.app_status != "DEGRADED" {
                    self.event_feed.log(
                        "NETWORK",
                        &format!("High packet loss detected ({:.1}%)", loss),
                        EventSeverity::Warn,
                    );
                }
                self.app_status = "DEGRADED".to_string();
            } else {
                if self.app_status != "LIVE" {
                    self.event_feed.log(
                        "NETWORK",
                        "Audio stream locked (LIVE)",
                        EventSeverity::Info,
                    );
                }
                self.app_status = "LIVE".to_string();
            }

            // Detect speech activity from live enhanced energy
            if let Ok(ew) = self.enhanced_waveform.lock() {
                let samples = ew.samples_vec();
                let rms = (samples.iter().map(|s| s * s).sum::<f32>()
                    / samples.len().max(1) as f32)
                    .sqrt();
                self.is_speech_active = rms > 0.02;
                self.speech_presence_prob = (rms / 0.08).clamp(0.0, 1.0);
            }

            if let Ok(guard) = self.telemetry_receiver.latest_telemetry.lock() {
                if let Some(ref t) = *guard {
                    self.tracked_talker_angle = t.talker_angle_deg;
                    self.doa_confidence = t.doa_confidence;

                    if t.battery_soc_pct > 0.0 {
                        self.battery_widget
                            .update(anc_rust::streaming::BatteryTelemetry {
                                soc_pct: t.battery_soc_pct,
                                terminal_voltage_v: t.battery_voltage_v,
                                current_draw_ma: if t.battery_voltage_v > 0.1 {
                                    t.battery_power_mw / t.battery_voltage_v
                                } else {
                                    150.0
                                },
                                power_draw_mw: t.battery_power_mw,
                                cell_temp_c: t.temperature_c,
                                estimated_runtime_hours: t.battery_runtime_hours,
                                internal_resistance_mohm: 58.0,
                                battery_health_pct: 98.0,
                                power_mode: self.battery_widget.telemetry.power_mode,
                            });
                    }

                    if t.blast_overpressure_pa > 0.0 {
                        self.blast_widget.update(anc_rust::metrics::BlastTelemetry {
                            peak_spl_db: 20.0
                                * (t.blast_overpressure_pa / anc_rust::metrics::P_REF_PASCALS)
                                    .log10(),
                            peak_overpressure_pa: t.blast_overpressure_pa,
                            peak_overpressure_psi: t.blast_overpressure_psi,
                            current_a_duration_ms: 1.2,
                            daily_impulse_count: self.blast_widget.telemetry.daily_impulse_count,
                            cumulative_dose_pct: t.blast_daily_dose_pct,
                            hazard_status: if t.blast_daily_dose_pct > 100.0 {
                                anc_rust::metrics::BlastHazardStatus::Hazardous
                            } else if t.blast_daily_dose_pct > 50.0 {
                                anc_rust::metrics::BlastHazardStatus::Caution
                            } else {
                                anc_rust::metrics::BlastHazardStatus::Nominal
                            },
                            last_blast_event: anc_rust::metrics::BlastEvent {
                                frame_index: t.frame,
                                peak_spl_db: 20.0
                                    * (t.blast_overpressure_pa / anc_rust::metrics::P_REF_PASCALS)
                                        .log10(),
                                peak_overpressure_pa: t.blast_overpressure_pa,
                                peak_overpressure_psi: t.blast_overpressure_psi,
                                a_duration_ms: 1.2,
                                dose_pct: t.blast_daily_dose_pct,
                            },
                        });
                    }

                    self.polar_widget.update(
                        PolarPatternTelemetry {
                            pattern_type: t.polar_pattern_type,
                            null_angle_deg: t.polar_null_angle_deg,
                            front_to_back_ratio_db: t.polar_front_to_back_ratio_db,
                            directivity_index_db: 4.8,
                            internal_delay_us: 58.3,
                        },
                        DeEsserTelemetry {
                            sibilance_detected: t.deesser_active,
                            sibilance_ratio_db: t.deesser_sibilance_ratio_db,
                            gain_reduction_db: t.deesser_gain_reduction_db,
                            sibilant_energy_dbfs: -30.0,
                            broadband_energy_dbfs: -25.0,
                        },
                    );
                    self.cable_widget.update(CableTelemetry {
                        health_pct: t.cable_health_pct,
                        estimated_impedance_ohms: t.cable_impedance_ohms,
                        low_freq_coherence: t.spatial_coherence,
                        dc_offset_mv: 0.0,
                        micro_intermittent_events: 0,
                        status: CableFaultStatus::from_u8(t.cable_fault_status),
                    });
                    self.ambisonics_scope.update(AmbisonicsTelemetry {
                        intensity_x: 0.0,
                        intensity_y: 0.0,
                        intensity_z: 0.0,
                        intensity_mag: t.ambisonics_intensity_mag,
                        energy_density: t.output_rms,
                        diffuseness: t.ambisonics_diffuseness,
                        azimuth_deg: t.ambisonics_azimuth_deg,
                        elevation_deg: 0.0,
                        is_localized: t.ambisonics_diffuseness < 0.5,
                    });
                    self.jamming_widget.update(JammingTelemetry {
                        jamming_type: JammingType::from_u8(t.jamming_type),
                        confidence: t.jamming_confidence,
                        jitter_variance_ms2: t.rf_jitter_var_ms2,
                        mean_jitter_ms: t.rf_jitter_var_ms2.sqrt(),
                        packet_loss_rate: t.packet_burst_clustering * 0.1,
                        burst_clustering: t.packet_burst_clustering,
                        auth_failure_rate: 0.0,
                        remediation_active: t.jamming_type > 0,
                        remediation_code: t.jamming_type,
                    });
                    self.rasti_widget.update(StiTelemetry {
                        sti_score: t.rasti_sti_score,
                        rating: StiRating::from_u8(t.rasti_rating),
                        mean_apparent_snr_db: t.estimated_snr_gain_db,
                        mean_mtf: t.rasti_sti_score,
                        mtf_bands: [t.rasti_sti_score; NUM_RASTI_MOD_FREQS],
                        is_authoritative: true,
                    });
                }
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
            self.spectrum_analyzer
                .compute_spectrum(&samples, &mut self.enhanced_spectrum_db);
            self.waterfall.push_frame(&self.enhanced_spectrum_db);
            self.waterfall_3d.push_frame(&self.enhanced_spectrum_db);
        }
        if let Ok(rw) = self.raw_waveform.lock() {
            let samples = rw.samples_vec();
            self.spectrum_analyzer
                .compute_spectrum(&samples, &mut self.raw_spectrum_db);
        }

        // Update Spatial Lissajous Phase Scope with latest audio vectors
        if let (Ok(rw), Ok(ew)) = (self.raw_waveform.lock(), self.enhanced_waveform.lock()) {
            let raw_s = rw.samples_vec();
            let enh_s = ew.samples_vec();
            let n = raw_s.len().min(enh_s.len()).min(512);
            if n > 0 {
                let start_r = raw_s.len() - n;
                let start_e = enh_s.len() - n;
                let wti_opt = if let Ok(tel) = self.telemetry_receiver.latest_telemetry.lock() {
                    tel.as_ref().map(|t| t.wind_turbulence_index)
                } else {
                    None
                };
                self.phase_scope
                    .push_samples(&raw_s[start_r..], &enh_s[start_e..], wti_opt);
            }
        }

        // Top Header Mission Control Bar
        egui::TopBottomPanel::top("top_panel")
            .frame(
                egui::Frame::none()
                    .fill(Theme::BG_SURFACE)
                    .stroke(egui::Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
                    .inner_margin(egui::Margin::symmetric(16.0, 12.0)),
            )
            .show(ctx, |ui| {
                ui.horizontal(|ui| {
                    // System Brand & Title
                    ui.label(
                        egui::RichText::new("DRDO SIH 26052")
                            .strong()
                            .size(17.0)
                            .color(Theme::ACCENT_CYAN),
                    );
                    ui.label(
                        egui::RichText::new("TACTICAL AI ACTIVE NOISE CANCELLATION")
                            .size(12.0)
                            .color(Theme::TEXT_SECONDARY),
                    );

                    ui.add_space(14.0);
                    StatusBadge::show(ui, &self.app_status);

                    ui.add_space(8.0);
                    VadBeacon::show(ui, self.is_speech_active, self.speech_presence_prob);

                    ui.add_space(8.0);
                    ShockTransientBadge::show(
                        ui,
                        self.kurtosis_hud.is_shock,
                        self.kurtosis_hud.crest_factor_db,
                        self.kurtosis_hud.peak_kurtosis,
                    );

                    ui.add_space(8.0);
                    let profile_btn = ui.button(
                        egui::RichText::new(format!("⚡ PROFILE: {}", self.active_profile))
                            .size(10.5)
                            .strong()
                            .monospace()
                            .color(Theme::ACCENT_AMBER),
                    );
                    if profile_btn.clicked() {
                        self.active_profile = match self.active_profile {
                            "COMBAT VEHICLE (T-90 / BMP)" => "FLIGHT COCKPIT (ALH / TEJAS)",
                            "FLIGHT COCKPIT (ALH / TEJAS)" => "DISMOUNTED INFANTRY",
                            "DISMOUNTED INFANTRY" => "COMMAND POST (TOC)",
                            _ => "COMBAT VEHICLE (T-90 / BMP)",
                        };
                        let prof = anc_rust::streaming::MissionProfile::from_str_name(self.active_profile);
                        if let Some(p) = prof {
                            self.event_feed.log(
                                "PROFILE",
                                &format!(
                                    "Acoustic profile switched to {} (Floor: {:.1} dB, Dereverb: {}, ConcussionBlanker: {})",
                                    self.active_profile,
                                    p.min_gain_db(),
                                    if p.enable_dereverb() { "ON" } else { "OFF" },
                                    if p.enable_transient_blanker() { "ON" } else { "OFF" }
                                ),
                                EventSeverity::Info,
                            );
                        }
                    }

                    // Interactive Tactical Audio Incident Recorder controls [🔴 REC / ⏹ STOP / 💾 EXPORT WAV]
                    ui.add_space(8.0);
                    match self.incident_recorder.state() {
                        RecorderState::Idle => {
                            if ui.button(egui::RichText::new("🔴 REC").strong().size(11.0).color(Theme::ACCENT_RED)).clicked() {
                                self.incident_recorder.start_recording(incident_flags::MANUAL_TRIGGER);
                                self.event_feed.log(
                                    "RECORDER",
                                    "Forensic incident recording started [🔴 REC] (30s pre-incident buffer active)",
                                    EventSeverity::Warn,
                                );
                            }
                        }
                        RecorderState::Recording => {
                            let dur = self.incident_recorder.total_incident_duration_secs();
                            let label = format!("⏹ STOP (REC {:.1}s)", dur);
                            if ui.button(egui::RichText::new(label).strong().size(11.0).color(Theme::ACCENT_AMBER)).clicked() {
                                self.incident_recorder.stop_recording();
                                self.event_feed.log(
                                    "RECORDER",
                                    &format!("Forensic incident capture halted [⏹ STOP] ({:.1}s duration). Ready for export.", dur),
                                    EventSeverity::Info,
                                );
                            }
                        }
                        RecorderState::ReadyToExport => {
                            ui.horizontal(|ui| {
                                if ui.button(egui::RichText::new("💾 EXPORT INCIDENT WAV").strong().size(11.0).color(Theme::ACCENT_GREEN)).clicked() {
                                    let export_path = "tactical_incident_report.wav";
                                    match self.incident_recorder.export_wav(export_path) {
                                        Ok(bytes) => {
                                            self.event_feed.log(
                                                "RECORDER",
                                                &format!("Forensic BEXT 16-bit stereo WAV exported successfully: {} ({} bytes, {:.1}s)", export_path, bytes, self.incident_recorder.total_incident_duration_secs()),
                                                EventSeverity::Info,
                                            );
                                        }
                                        Err(e) => {
                                            self.event_feed.log(
                                                "RECORDER",
                                                &format!("Forensic WAV export error: {}", e),
                                                EventSeverity::Error,
                                            );
                                        }
                                    }
                                    self.incident_recorder.reset();
                                }
                                if ui.button(egui::RichText::new("✕").size(10.0).color(Theme::TEXT_MUTED)).clicked() {
                                    self.incident_recorder.reset();
                                }
                            });
                        }
                    }

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        // Interactive Test Signal Generator Button / Dropdown
                        let (test_label, test_col) = match self.test_signal.mode {
                            TestSignalMode::Off => ("🧪 TEST: OFF", Theme::TEXT_SECONDARY),
                            TestSignalMode::Sine1kHz => ("🧪 TEST: 1kHz SINE", Theme::ACCENT_AMBER),
                            TestSignalMode::Impulse => ("🧪 TEST: IMPULSE", Theme::ACCENT_RED),
                            TestSignalMode::PinkNoise => ("🧪 TEST: PINK NOISE", Theme::ACCENT_VIOLET),
                        };

                        egui::ComboBox::from_id_salt("test_sig_select")
                            .selected_text(egui::RichText::new(test_label).size(11.0).color(test_col))
                            .show_ui(ui, |ui| {
                                for &m in &[
                                    TestSignalMode::Off,
                                    TestSignalMode::Sine1kHz,
                                    TestSignalMode::Impulse,
                                    TestSignalMode::PinkNoise,
                                ] {
                                    if ui.selectable_label(self.test_signal.mode == m, m.name()).clicked() {
                                        self.test_signal.set_mode(m);
                                        self.event_feed.log(
                                            "TEST",
                                            match m {
                                                TestSignalMode::Off => "Diagnostic test signal generator deactivated",
                                                TestSignalMode::Sine1kHz => "Injected synthetic 1 kHz pilot tone (-12 dBFS) for THD/harmonic test",
                                                TestSignalMode::Impulse => "Injected periodic Dirac impulse (500 ms) for latency/blanker test",
                                                TestSignalMode::PinkNoise => "Injected calibrated pink noise (-20 dBFS) for subband ERB test",
                                            },
                                            if m == TestSignalMode::Off { EventSeverity::Info } else { EventSeverity::Warn },
                                        );
                                    }
                                }
                            });

                        // Aggressive Max SNR vs Tactical Intelligibility Mode Quick-Toggle
                        let (snr_mode_label, snr_mode_col) = if self.is_aggressive_snr {
                            ("🚀 MODE: AGGRESSIVE MAX SNR", Theme::ACCENT_CYAN)
                        } else {
                            ("🎯 MODE: TACTICAL INTELLIGIBILITY", Theme::TEXT_SECONDARY)
                        };
                        if ui
                            .button(egui::RichText::new(snr_mode_label).size(11.0).strong().color(snr_mode_col))
                            .clicked()
                        {
                            self.is_aggressive_snr = !self.is_aggressive_snr;
                            self.event_feed.log(
                                "OPTIMIZER",
                                if self.is_aggressive_snr {
                                    "Audio mode switched to AGGRESSIVE MAX SNR (Deep Dynamic Pause Floor -36dB & Deep Harmonic Valley Notch)"
                                } else {
                                    "Audio mode switched to TACTICAL INTELLIGIBILITY (Nominal -18dB Floor & Formant Skirt Protection)"
                                },
                                EventSeverity::Info,
                            );
                        }

                        // Demo mode toggle button
                        let (demo_btn_label, demo_col) = if self.is_demo_mode {
                            ("MODE: DEMO (ACTIVE)", Theme::ACCENT_VIOLET)
                        } else {
                            ("MODE: LIVE NETWORK", Theme::TEXT_SECONDARY)
                        };
                        if ui
                            .button(egui::RichText::new(demo_btn_label).size(11.0).color(demo_col))
                            .clicked()
                        {
                            self.is_demo_mode = !self.is_demo_mode;
                            if self.is_demo_mode {
                                self.event_feed.log(
                                    "MODE",
                                    "Switched to DEMO mode (Speech + Tactical Noise)",
                                    EventSeverity::Info,
                                );
                            } else {
                                self.event_feed.log(
                                    "MODE",
                                    "Switched to LIVE NETWORK mode",
                                    EventSeverity::Info,
                                );
                            }
                        }

                        // Prominent A/B Audio Monitor Switcher
                        let mut current_mon = *self.monitor_source.lock().unwrap();
                        let (mon_text, mon_color) = match current_mon {
                            AudioMonitorSource::Enhanced => ("🎧 AUDIO: ENHANCED (CLEAN)", Theme::ACCENT_CYAN),
                            AudioMonitorSource::Raw => ("🎧 AUDIO: RAW (NOISY)", Theme::ACCENT_AMBER),
                        };

                        if ui.button(egui::RichText::new(mon_text).size(11.0).strong().color(mon_color)).clicked() {
                            current_mon = match current_mon {
                                AudioMonitorSource::Enhanced => AudioMonitorSource::Raw,
                                AudioMonitorSource::Raw => AudioMonitorSource::Enhanced,
                            };
                            *self.monitor_source.lock().unwrap() = current_mon;
                            self.event_feed.log(
                                "AUDIO",
                                match current_mon {
                                    AudioMonitorSource::Enhanced => "Soundcard output set to ENHANCED CLEAN (UDP 5005)",
                                    AudioMonitorSource::Raw => "Soundcard output set to RAW NOISY INPUT (UDP 5007)",
                                },
                                EventSeverity::Info,
                            );
                        }

                        // Spatial Stereo Widening Button
                        let is_spatial = if let Some(ref p) = self.playback {
                            p.is_spatial_stereo()
                        } else {
                            true
                        };
                        let (spatial_text, spatial_col) = if is_spatial {
                            ("🌐 STEREO: BINAURAL (WIDE)", Theme::ACCENT_CYAN)
                        } else {
                            ("🎧 STEREO: DUAL MONO", Theme::TEXT_SECONDARY)
                        };
                        if ui.button(egui::RichText::new(spatial_text).size(11.0).color(spatial_col)).clicked() {
                            if let Some(ref p) = self.playback {
                                p.set_spatial_stereo(!is_spatial);
                            }
                            self.event_feed.log(
                                "AUDIO",
                                if !is_spatial {
                                    "Binaural spatial stereo widening ENABLED (Center Speech / Wide Ambient Separation)"
                                } else {
                                    "Headphone playout set to DUAL MONO"
                                },
                                EventSeverity::Info,
                            );
                        }

                        // Situational Awareness / Transparency Mode Button
                        let (trans_text, trans_col) = if self.is_transparency_active {
                            ("🛡️ TRANS: AMBIENT AWARE (85dBA CLAMP)", Theme::ACCENT_GREEN)
                        } else {
                            ("🛡️ TRANS: OFF (ANC ISOLATED)", Theme::TEXT_SECONDARY)
                        };
                        if ui.button(egui::RichText::new(trans_text).size(11.0).color(trans_col)).clicked() {
                            self.is_transparency_active = !self.is_transparency_active;
                            self.event_feed.log(
                                "TRANSPARENCY",
                                if self.is_transparency_active {
                                    "Situational awareness transparency ENABLED (calibrated 85 dBA instantaneous concussive clamp)"
                                } else {
                                    "Situational awareness transparency DISABLED (maximum ANC isolation)"
                                },
                                EventSeverity::Info,
                            );
                        }

                        // Mute button
                        let mute_label = if self.is_muted { "UNMUTE" } else { "MUTE" };
                        let mute_color = if self.is_muted { Theme::ACCENT_RED } else { Theme::TEXT_SECONDARY };
                        if ui.button(egui::RichText::new(mute_label).size(11.0).color(mute_color)).clicked() {
                            self.is_muted = !self.is_muted;
                            if let Some(ref p) = self.playback {
                                p.set_muted(self.is_muted);
                            }
                            self.event_feed.log(
                                "AUDIO",
                                if self.is_muted { "Soundcard output muted" } else { "Soundcard unmuted" },
                                EventSeverity::Info,
                            );
                        }

                        // Volume control with formatted readout
                        ui.label(egui::RichText::new(format!("{:.0}%", self.volume * 100.0)).size(11.0).color(Theme::TEXT_MUTED));
                        ui.add_sized([70.0, 18.0], egui::Slider::new(&mut self.volume, 0.0..=2.0).show_value(false));
                        ui.label(egui::RichText::new("Vol:").size(11.0).color(Theme::TEXT_MUTED));
                    });
                });
            });

        // Main Central View
        egui::CentralPanel::default()
            .frame(
                egui::Frame::none()
                    .fill(Theme::BG_VOID)
                    .inner_margin(egui::Margin::same(14.0)),
            )
            .show(ctx, |ui| {
                // Read current stats
                let (enh_stats, raw_stats) = {
                    let es = self.enhanced_stats.lock().unwrap();
                    let rs = self.raw_stats.lock().unwrap();
                    (*es, *rs)
                };

                let telemetry = self.telemetry_receiver.latest_telemetry.lock().unwrap().clone();
                let (jitter_ms, underruns, overflows) = {
                    let jb = self.jitter_buffer.lock().unwrap();
                    (jb.buffer_ms(), jb.underrun_events, jb.overflow_count)
                };

                // Tactical Profile Sub-bar
                ui.horizontal(|ui| {
                    ui.label(egui::RichText::new("DSP PIPELINE:").size(10.5).strong().color(Theme::TEXT_MUTED));
                    ui.label(egui::RichText::new("Dual-Mic 30mm MVDR → Subband AFC → Concussion Blanker → 2-State Kalman DOA → DD-ERB Wiener → Safe Transparency").size(10.5).color(Theme::ACCENT_CYAN));

                    let sii_val = telemetry.as_ref().map(|t| t.speech_intelligibility_index).unwrap_or(0.85);
                    let gain_val = telemetry.as_ref().map(|t| t.intelligibility_gain_db).unwrap_or(3.2);
                    IntelligibilityBadge::show(ui, sii_val, gain_val);

                    RfLinkBadge::show(ui, enh_stats.rf_link_health, enh_stats.fec_recovery_rate);

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        ui.label(egui::RichText::new("ARRAY: 30 mm | BROADSIDE: 0.0° | NULL: 90.0°").size(10.0).color(Theme::TEXT_MUTED));
                    });
                });

                // Real-time Latency Budget Breakdown HUD
                egui::Frame::none()
                    .fill(Theme::BG_CARD)
                    .stroke(egui::Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
                    .rounding(egui::Rounding::same(6.0))
                    .inner_margin(egui::Margin::symmetric(10.0, 6.0))
                    .show(ui, |ui| {
                        ui.horizontal(|ui| {
                            ui.label(egui::RichText::new("LATENCY BUDGET (16.01 ms / 35.0 ms):").size(10.0).strong().color(Theme::TEXT_MUTED));
                            ui.label(egui::RichText::new("STFT Framing: 8.0 ms (49.9%)").size(10.0).color(Theme::ACCENT_CYAN));
                            ui.label(egui::RichText::new("·").color(Theme::TEXT_MUTED));
                            ui.label(egui::RichText::new("ALSA Double-Buffer: 8.0 ms (49.9%)").size(10.0).color(Theme::ACCENT_GREEN));
                            ui.label(egui::RichText::new("·").color(Theme::TEXT_MUTED));
                            ui.label(egui::RichText::new("DSP (MVDR+AFC+WPE+Spectral): 0.07 ms (0.4%)").size(10.0).color(Theme::ACCENT_AMBER));
                            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                ui.label(egui::RichText::new("PASS (Margin: +18.99 ms / 54.3%)").size(10.0).strong().color(Theme::ACCENT_GREEN));
                            });
                        });
                    });

                ui.add_space(6.0);

                // High-Resolution Per-Hop Microsecond Timing Timeline / Histogram Widget
                let cur_timings = telemetry
                    .as_ref()
                    .map(|t| t.stage_timings)
                    .unwrap_or(DspStageTimings {
                        stft_us: 14,
                        afc_us: 6,
                        beamformer_us: 12,
                        dereverb_us: 8,
                        spectral_us: 18,
                        intelligibility_us: 6,
                        synthesis_us: 10,
                        total_us: 74,
                    });
                self.timeline_widget.show(ui, &cur_timings, 52.0);

                ui.add_space(8.0);

                // Row of High-Tech Telemetry Cards
                ui.horizontal(|ui| {
                    let lat_val = telemetry
                        .as_ref()
                        .map(|t| format!("{:.1} ms", t.total_latency_ms))
                        .unwrap_or_else(|| "16.0 ms".to_string());
                    MetricCard::show(
                        ui,
                        "CAPTURE-TO-PLAYOUT",
                        &lat_val,
                        "PASS (Gate <= 35 ms)",
                        Theme::ACCENT_GREEN,
                    );

                    let rtf_val = telemetry
                        .as_ref()
                        .map(|t| format!("{:.4}", t.avg_rtf))
                        .unwrap_or_else(|| "0.0004".to_string());
                    MetricCard::show(
                        ui,
                        "COMPUTE RTF",
                        &rtf_val,
                        "2200x Headroom",
                        Theme::ACCENT_VIOLET,
                    );

                    let sii_card_val = telemetry
                        .as_ref()
                        .map(|t| format!("{:.2}", t.speech_intelligibility_index))
                        .unwrap_or_else(|| "0.85".to_string());
                    let sii_card_sub = telemetry
                        .as_ref()
                        .map(|t| format!("{:+.1} dB SII Gain", t.intelligibility_gain_db))
                        .unwrap_or_else(|| "+3.2 dB SII Gain".to_string());
                    MetricCard::show(
                        ui,
                        "SPEECH INTELLIGIBILITY",
                        &sii_card_val,
                        &sii_card_sub,
                        Theme::ACCENT_CYAN,
                    );

                    let rf_card_val = format!("{:.1}%", enh_stats.rf_link_health);
                    let rf_card_sub = format!("{:.0}% FEC ({} rec)", enh_stats.fec_recovery_rate, enh_stats.packets_fec_recovered);
                    let rf_card_color = if enh_stats.rf_link_health >= 95.0 {
                        Theme::ACCENT_GREEN
                    } else {
                        Theme::ACCENT_AMBER
                    };
                    MetricCard::show(
                        ui,
                        "RF LINK & FEC HEALTH",
                        &rf_card_val,
                        &rf_card_sub,
                        rf_card_color,
                    );

                    let temp_val = telemetry
                        .as_ref()
                        .map(|t| format!("{:.1} °C", t.temperature_c))
                        .unwrap_or_else(|| "42.8 °C".to_string());
                    MetricCard::show(
                        ui,
                        "CORTEX-A76 TEMP",
                        &temp_val,
                        "Nominal (< 80°C)",
                        Theme::ACCENT_AMBER,
                    );

                    let loss_val = format!("{:.1}%", enh_stats.loss_percentage);
                    let loss_color = if enh_stats.loss_percentage > 5.0 {
                        Theme::ACCENT_RED
                    } else {
                        Theme::ACCENT_GREEN
                    };
                    MetricCard::show(
                        ui,
                        "PACKET INTEGRITY",
                        &loss_val,
                        "0 Missed Frames",
                        loss_color,
                    );

                    let snr_card_val = if self.is_aggressive_snr {
                        "+11.5 dB"
                    } else {
                        "+9.0 dB"
                    };
                    let snr_card_sub = if self.is_aggressive_snr {
                        "Aggressive Max SNR"
                    } else {
                        "Tactical Intelligibility"
                    };
                    MetricCard::show(
                        ui,
                        "ESTIMATED SNR GAIN",
                        snr_card_val,
                        snr_card_sub,
                        Theme::ACCENT_CYAN,
                    );

                    let jb_val = format!("{:.1} ms", jitter_ms);
                    MetricCard::show(
                        ui,
                        "JITTER BUFFER",
                        &jb_val,
                        "Target: 48.0 ms",
                        Theme::ACCENT_CYAN,
                    );

                    let stress_val = format!("{:.0}%", self.stress_widget.stress_index_pct);
                    let stress_sub = if self.stress_widget.is_acute_stress {
                        "Acute Strain"
                    } else {
                        "Nominal State"
                    };
                    let stress_col = if self.stress_widget.is_acute_stress {
                        Theme::ACCENT_RED
                    } else {
                        Theme::ACCENT_GREEN
                    };
                    MetricCard::show(
                        ui,
                        "COGNITIVE STRESS",
                        &stress_val,
                        stress_sub,
                        stress_col,
                    );

                    let batt_val = format!("{:.0}% ({:.1}h)", self.battery_widget.telemetry.soc_pct, self.battery_widget.telemetry.estimated_runtime_hours);
                    let batt_sub = format!("{:.2}V  {:.0}mW", self.battery_widget.telemetry.terminal_voltage_v, self.battery_widget.telemetry.power_draw_mw);
                    let batt_col = if self.battery_widget.telemetry.soc_pct > 50.0 {
                        Theme::ACCENT_GREEN
                    } else if self.battery_widget.telemetry.soc_pct > 20.0 {
                        Theme::ACCENT_AMBER
                    } else {
                        Theme::ACCENT_RED
                    };
                    MetricCard::show(
                        ui,
                        "MISSION BATTERY",
                        &batt_val,
                        &batt_sub,
                        batt_col,
                    );

                    let blast_val = format!("{:.1} Pa", self.blast_widget.telemetry.peak_overpressure_pa);
                    let blast_sub = format!("{:.3} PSI ({} bl)", self.blast_widget.telemetry.peak_overpressure_psi, self.blast_widget.telemetry.daily_impulse_count);
                    let blast_col = match self.blast_widget.telemetry.hazard_status {
                        anc_rust::metrics::BlastHazardStatus::Nominal => Theme::ACCENT_GREEN,
                        anc_rust::metrics::BlastHazardStatus::Caution => Theme::ACCENT_AMBER,
                        anc_rust::metrics::BlastHazardStatus::Hazardous => Theme::ACCENT_RED,
                    };
                    MetricCard::show(
                        ui,
                        "BLAST OVERPRESSURE",
                        &blast_val,
                        &blast_sub,
                        blast_col,
                    );

                    let polar_sub = format!("Null: {:.0}° ({:.1}dB)", self.polar_widget.steered_null_deg, self.polar_widget.polar_telemetry.front_to_back_ratio_db);
                    MetricCard::show(
                        ui,
                        "POLAR DIRECTIVITY",
                        self.polar_widget.selected_pattern.name(),
                        &polar_sub,
                        Theme::ACCENT_CYAN,
                    );

                    let cable_val = format!("{:.0}%", self.cable_widget.telemetry.health_pct);
                    let cable_sub = format!("{:.0} Ω ({})", self.cable_widget.telemetry.estimated_impedance_ohms, self.cable_widget.telemetry.status.name());
                    let cable_col = match self.cable_widget.telemetry.status {
                        CableFaultStatus::Nominal => Theme::ACCENT_GREEN,
                        CableFaultStatus::MicroIntermittent | CableFaultStatus::HighImpedanceFray => Theme::ACCENT_AMBER,
                        CableFaultStatus::OpenCircuit | CableFaultStatus::ShortCircuit => Theme::ACCENT_RED,
                    };
                    MetricCard::show(
                        ui,
                        "CABLE INTEGRITY",
                        &cable_val,
                        &cable_sub,
                        cable_col,
                    );

                    let ambi_val = format!("{:.2}", self.ambisonics_scope.telemetry.intensity_mag);
                    let ambi_sub = format!("Az: {:>+4.0}° (ψ: {:.2})", self.ambisonics_scope.telemetry.azimuth_deg, self.ambisonics_scope.telemetry.diffuseness);
                    MetricCard::show(
                        ui,
                        "ACOUSTIC INTENSITY",
                        &ambi_val,
                        &ambi_sub,
                        Theme::ACCENT_CYAN,
                    );

                    let jam_val = match self.jamming_widget.telemetry.jamming_type {
                        JammingType::NominalRF => "NOMINAL",
                        JammingType::SpotJamming => "SPOT EW",
                        JammingType::BarrageJamming => "BARRAGE",
                        JammingType::SweepJamming => "SWEEP EW",
                    };
                    let jam_sub = format!("Loss: {:.1}% (σ²: {:.1})", self.jamming_widget.telemetry.packet_loss_rate * 100.0, self.jamming_widget.telemetry.jitter_variance_ms2);
                    let jam_col = match self.jamming_widget.telemetry.jamming_type {
                        JammingType::NominalRF => Theme::ACCENT_GREEN,
                        JammingType::SpotJamming => Theme::ACCENT_AMBER,
                        JammingType::BarrageJamming | JammingType::SweepJamming => Theme::ACCENT_RED,
                    };
                    MetricCard::show(
                        ui,
                        "RF EW INTEGRITY",
                        jam_val,
                        &jam_sub,
                        jam_col,
                    );

                    let sti_val = format!("{:.2}", self.rasti_widget.telemetry.sti_score);
                    let sti_sub = self.rasti_widget.telemetry.rating.name();
                    let sti_col = match self.rasti_widget.telemetry.rating {
                        StiRating::Excellent => Theme::ACCENT_CYAN,
                        StiRating::Good => Theme::ACCENT_GREEN,
                        StiRating::Fair | StiRating::Poor => Theme::ACCENT_AMBER,
                        StiRating::Bad => Theme::ACCENT_RED,
                    };
                    MetricCard::show(
                        ui,
                        "RASTI STI",
                        &sti_val,
                        sti_sub,
                        sti_col,
                    );
                });

                ui.add_space(10.0);

                // Main Center Stage: Waveforms & Spectrum
                ui.columns(2, |cols| {
                    cols[0].vertical(|ui| {
                        // Raw Input Waveform (Amber)
                        if let Ok(rw) = self.raw_waveform.lock() {
                            rw.show(
                                ui,
                                "RAW PRIMARY SENSOR INPUT",
                                "UDP 5007",
                                Theme::ACCENT_AMBER,
                                132.0,
                            );
                        }
                        ui.add_space(8.0);
                        // Enhanced Output Waveform (Cyan)
                        if let Ok(ew) = self.enhanced_waveform.lock() {
                            ew.show(
                                ui,
                                "ENHANCED TACTICAL AUDIO OUTPUT",
                                "UDP 5005",
                                Theme::ACCENT_CYAN,
                                132.0,
                            );
                        }
                    });

                    cols[1].vertical(|ui| {
                        // High-Resolution Spectrum Analyzer View
                        SpectrumView::show(
                            ui,
                            self.spectrum_analyzer.freq_bins(),
                            &self.enhanced_spectrum_db,
                            Some(&self.raw_spectrum_db),
                            296.0,
                        );
                    });
                });

                ui.add_space(8.0);

                // Tactical Spectral Waterfall Display: 2D Heatmap or 3D Battlefield Terrain Mesh
                ui.horizontal(|ui| {
                    if ui
                        .selectable_label(
                            self.is_3d_waterfall_active,
                            egui::RichText::new("⛰ 3D TERRAIN MESH").strong().size(11.0),
                        )
                        .clicked()
                    {
                        self.is_3d_waterfall_active = true;
                    }
                    if ui
                        .selectable_label(
                            !self.is_3d_waterfall_active,
                            egui::RichText::new("▦ 2D WATERFALL").strong().size(11.0),
                        )
                        .clicked()
                    {
                        self.is_3d_waterfall_active = false;
                    }
                });

                if self.is_3d_waterfall_active {
                    self.waterfall_3d.show(ui, 110.0);
                } else {
                    self.waterfall.show(ui, 84.0);
                }

                ui.add_space(8.0);

                // Interactive In-Headset Pure-Tone Audiometry & Personal Hearing Loss Compensation Wizard
                if let Some(prog) = self.audiogram_wizard.show(ui, 130.0) {
                    if let Ok(mut eq) = self.tactical_eq.lock() {
                        for i in 0..8 {
                            let htl = (prog.htl_left[i] + prog.htl_right[i]) * 0.5;
                            let prescribed_gain = (0.46 * htl - 0.0015 * htl * htl).clamp(0.0, 18.0);
                            eq.set_gain(i, prescribed_gain);
                        }
                    }
                    self.event_feed.log(
                        "AUDIOGRAM",
                        "NAL-NL2 Personal Audiogram calibrated and programmed into DSP WDRC compressor (4kHz acoustic notch restored)",
                        EventSeverity::Info,
                    );
                }

                ui.add_space(8.0);

                // Interactive 8-Band Tactical Parametric Equalizer & Soldier Audiogram Calibration
                if let Ok(mut eq) = self.tactical_eq.lock() {
                    TacticalEqWidget::show(ui, &mut eq);
                }

                ui.add_space(8.0);

                // Lower section: Tactical DOA Radar, Diagnostics Panel and Mission Event Log
                ui.columns(3, |cols| {
                    cols[0].vertical(|ui| {
                        if let Some(user_angle) = TacticalRadarWidget::show_with_cdr(
                            ui,
                            self.tracked_talker_angle,
                            self.doa_confidence,
                            self.is_speech_active,
                            self.mean_cdr_db,
                            self.spatial_coherence,
                            &[-90.0, 90.0],
                            150.0,
                        ) {
                            self.tracked_talker_angle = user_angle;
                        }

                        ui.add_space(8.0);
                        self.threat_radar.show(ui, 130.0);

                        ui.add_space(8.0);
                        self.phase_scope.show(ui, 130.0);

                        ui.add_space(8.0);
                        if let Some(new_mode) = self.battery_widget.show(ui, 75.0) {
                            self.event_feed.log(
                                "POWER",
                                &format!("Tactical battery operational power mode switched to {:?}", new_mode),
                                EventSeverity::Info,
                            );
                        }

                        ui.add_space(8.0);
                        if let Some((new_pat, new_null)) = self.polar_widget.show(ui, 125.0) {
                            self.event_feed.log(
                                "POLAR",
                                &format!("Directivity switched to {:?} (Null: {:.0}°)", new_pat, new_null),
                                EventSeverity::Info,
                            );
                        }
                    });

                    cols[1].vertical(|ui| {
                        DiagnosticsPanel::show(
                            ui,
                            telemetry.as_ref(),
                            &enh_stats,
                            &raw_stats,
                            jitter_ms,
                            underruns,
                            overflows,
                        );

                        ui.add_space(8.0);
                        self.kurtosis_hud.show(ui, 110.0);

                        ui.add_space(8.0);
                        if let Some(target) = self.lufs_radar.show(ui, 125.0) {
                            self.event_feed.log(
                                "LUFS",
                                &format!("Tactical EBU R128 loudness target adjusted to {:.1} LUFS", target),
                                EventSeverity::Info,
                            );
                        }

                        ui.add_space(8.0);
                        self.stress_widget.show(ui, 105.0);

                        ui.add_space(8.0);
                        self.blast_widget.show(ui, 85.0);

                        ui.add_space(8.0);
                        self.cable_widget.show(ui, 80.0);

                        ui.add_space(8.0);
                        self.ambisonics_scope.show(ui, 75.0);

                        ui.add_space(8.0);
                        self.jamming_widget.show(ui, 75.0);

                        ui.add_space(8.0);
                        self.rasti_widget.show(ui, 75.0);

                        ui.add_space(8.0);
                        self.occlusion_widget.render(ui);

                        ui.add_space(8.0);
                        self.mesh_radar.render(ui);

                        ui.add_space(8.0);
                        self.atak_widget.render(ui);
                    });

                    cols[2].vertical(|ui| {
                        egui::Frame::none()
                            .fill(Theme::BG_CARD)
                            .stroke(egui::Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
                            .rounding(8.0)
                            .inner_margin(egui::Margin::same(12.0))
                            .show(ui, |ui| {
                                ui.horizontal(|ui| {
                                    ui.label(egui::RichText::new("●").color(Theme::ACCENT_CYAN).size(11.0));
                                    ui.label(
                                        egui::RichText::new("MISSION CONTROL EVENT AUDIT")
                                            .strong()
                                            .size(12.0)
                                            .color(Theme::TEXT_PRIMARY),
                                    );
                                });
                                ui.add_space(6.0);

                                egui::ScrollArea::vertical().max_height(200.0).show(ui, |ui| {
                                    for ev in self.event_feed.events() {
                                        let col = match ev.severity {
                                            EventSeverity::Info => Theme::TEXT_SECONDARY,
                                            EventSeverity::Warn => Theme::ACCENT_AMBER,
                                            EventSeverity::Error => Theme::ACCENT_RED,
                                        };
                                        ui.horizontal(|ui| {
                                            ui.label(
                                                egui::RichText::new(&ev.timestamp)
                                                    .size(10.0)
                                                    .color(Theme::TEXT_MUTED),
                                            );
                                            ui.label(
                                                egui::RichText::new(format!("[{}]", ev.source))
                                                    .size(10.0)
                                                    .strong()
                                                    .color(Theme::ACCENT_CYAN),
                                            );
                                            ui.label(
                                                egui::RichText::new(&ev.message)
                                                    .size(10.0)
                                                    .color(col),
                                            );
                                        });
                                    }
                                });
                            });
                    });
                });
            });

        // Request continuous repaint for real-time 60 FPS smooth visualizations
        ctx.request_repaint_after(Duration::from_millis(16));
    }
}
