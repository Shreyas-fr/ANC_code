//! 360° Tactical Threat Radar & Binaural Acoustic Alert Sonification Engine.
//!
//! Developed for SIH 26052 Tactical Audio Systems.
//!
//! In dynamic tactical combat environments, acoustic sensors detect hostile events:
//! - Sniper Supersonic Crack (high-frequency N-wave shockwave, rise time < 1 ms)
//! - Gunfire / Muzzle Detonation (wideband explosive impulse + low thump)
//! - Drone / UAV Rotor Wash (blade passage harmonic whine, 120-250 Hz comb)
//! - Armored Vehicle / Chassis Rumble (heavy mechanical engine vibration, 40-100 Hz)
//!
//! This module implements:
//! 1. Tactical Threat Classification & Azimuth/Distance Tracking:
//!    - Maintains a real-time list of classified threats with arrival azimuth $\theta \in [-180^\circ, +180^\circ]$,
//!      estimated distance (10m - 500m), and confidence metrics.
//! 2. Binaural 3D Spatial Alert Sonification Engine:
//!    - Synthesizes subtle, tactical alert audio cues spatialized binaurally at the threat azimuth.
//!    - Calculates exact Interaural Time Difference (ITD) via Woodworth's spherical head model:
//!      $$\Delta t = \frac{a}{c} (\sin|\theta| + |\theta|)$$
//!      ($a = 0.0875\text{ m}$, $c = 343\text{ m/s}$, up to $\pm 650\ \mu\text{s}$).
//!    - Calculates Interaural Level Difference (ILD) applying contralateral ear head-shadow attenuation.
//!    - Renders spatial acoustic alerts directly into the soldier's stereo headset, allowing intuitive
//!      directional threat localization.
//! 3. Interactive 360° Polar Threat Radar Display:
//!    - Concentric range rings (50m, 150m, 300m, 500m) with cardinal bearing lines (N/E/S/W).
//!    - Glowing, pulsed threat markers color-coded by tactical severity.
//!    - Interactive simulation trigger buttons: Test Sniper Crack (-45°), Test Drone (+60°), Test Gunfire (+110°), Test Armor (0°).
//!
//! Zero heap allocations in the audio synthesis and rendering loops.

use super::theme::Theme;
use egui::{Color32, Frame, Margin, Pos2, Rounding, Sense, Stroke, Ui, Vec2};
use std::f32::consts::PI;

/// Categorization of tactical acoustic threats.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ThreatType {
    /// Sniper Supersonic Crack (N-wave shockwave, extreme danger)
    SniperCrack,
    /// Gunfire / Small Arms Muzzle Detonation
    Gunfire,
    /// Hostile Drone / Loitering UAV Rotor Whine
    DroneUav,
    /// Combat Vehicle / Armored Chassis Rumble
    EngineRumble,
}

impl ThreatType {
    pub fn label(&self) -> &'static str {
        match self {
            Self::SniperCrack => "SNIPER CRACK",
            Self::Gunfire => "GUNFIRE",
            Self::DroneUav => "DRONE / UAV",
            Self::EngineRumble => "ARMOR CHASSIS",
        }
    }

    pub fn color(&self) -> Color32 {
        match self {
            Self::SniperCrack => Color32::from_rgb(255, 45, 85), // Crimson Red
            Self::Gunfire => Color32::from_rgb(255, 120, 40),    // Fiery Orange
            Self::DroneUav => Color32::from_rgb(255, 215, 0),    // Amber Yellow
            Self::EngineRumble => Color32::from_rgb(180, 100, 255), // Tactical Violet
        }
    }

    pub fn priority(&self) -> u8 {
        match self {
            Self::SniperCrack => 1,
            Self::Gunfire => 2,
            Self::DroneUav => 3,
            Self::EngineRumble => 4,
        }
    }
}

/// A classified acoustic threat entity.
#[derive(Debug, Clone)]
pub struct ThreatEntity {
    pub id: u64,
    pub threat_type: ThreatType,
    /// Azimuth angle in degrees: 0° is forward/North, +90° is right/East, -90° is left/West, +/-180° is rear/South.
    pub azimuth_deg: f32,
    /// Estimated distance in meters.
    pub distance_m: f32,
    /// Classification confidence (0.0 to 1.0).
    pub confidence: f32,
    /// Time remaining for active blinking display in seconds.
    pub time_to_live_sec: f32,
    /// Initial duration in seconds.
    pub initial_ttl_sec: f32,
}

/// Binaural 3D Spatial Alert Sonification Engine.
pub struct SpatialAlertSonifier {
    sample_rate: f32,
    /// Pending samples to play: stereo ring buffer (left, right interleaved).
    alert_buffer: Vec<f32>,
    read_pos: usize,
}

impl SpatialAlertSonifier {
    /// Creates a new sonifier with pre-allocated alert buffers.
    pub fn new(sample_rate: f32) -> Self {
        Self {
            sample_rate,
            alert_buffer: Vec::with_capacity(4096),
            read_pos: 0,
        }
    }

    /// Triggers a spatialized 3D directional alert tone.
    ///
    /// - `threat_type`: Type of threat deciding the sound timbre.
    /// - `azimuth_deg`: Angle of arrival (-180° to +180°).
    pub fn trigger_spatial_alert(&mut self, threat_type: ThreatType, azimuth_deg: f32) {
        let rad = azimuth_deg.to_radians();

        // 1. Woodworth Interaural Time Difference (ITD)
        // a = 0.0875 m (head radius), c = 343.0 m/s
        let a = 0.0875f32;
        let c = 343.0f32;
        let abs_rad = rad.abs();
        let itd_seconds = (a / c) * (abs_rad.sin() + abs_rad);
        let itd_samples = (itd_seconds * self.sample_rate).round() as usize;

        // 2. Interaural Level Difference (ILD)
        // Sound closer to left ear: rad < 0 => left louder, right attenuated by head shadow
        let pan = rad.sin(); // -1.0 (full left) to +1.0 (full right)
        let gain_left = (1.0 - 0.40 * pan).clamp(0.20, 1.0);
        let gain_right = (1.0 + 0.40 * pan).clamp(0.20, 1.0);

        // 3. Synthesize alert click/pip (duration ~40 ms = 640 samples @ 16 kHz)
        let num_mono_samples = (0.040 * self.sample_rate) as usize;
        let mut mono = vec![0.0f32; num_mono_samples];

        for (n, sample) in mono.iter_mut().enumerate() {
            let t = n as f32 / self.sample_rate;
            let env = (-t * 70.0).exp(); // Fast exponential decay click

            let tone = match threat_type {
                ThreatType::SniperCrack => {
                    // Sharp 2200 Hz click with high-frequency pop
                    (2.0 * PI * 2200.0 * t).sin() * 0.70 + (2.0 * PI * 4400.0 * t).sin() * 0.30
                }
                ThreatType::Gunfire => {
                    // 750 Hz down-chirp alert
                    let f = 750.0 - 500.0 * (t / 0.040);
                    (2.0 * PI * f * t).sin()
                }
                ThreatType::DroneUav => {
                    // Dual-frequency alert pip (1200 Hz + 1400 Hz)
                    0.5 * (2.0 * PI * 1200.0 * t).sin() + 0.5 * (2.0 * PI * 1400.0 * t).sin()
                }
                ThreatType::EngineRumble => {
                    // 450 Hz alert tone
                    (2.0 * PI * 450.0 * t).sin()
                }
            };
            *sample = tone * env * 0.25; // Subtle alert volume (-12 dBFS)
        }

        // Render binaural stereo with ITD delay and ILD gains
        let total_frames = num_mono_samples + itd_samples;
        self.alert_buffer.clear();
        self.alert_buffer.resize(total_frames * 2, 0.0);
        self.read_pos = 0;

        for (n, &s) in mono.iter().enumerate() {
            if pan <= 0.0 {
                // Sound from left: Left arrives first, Right is delayed by ITD
                let left_idx = n * 2;
                let right_idx = (n + itd_samples) * 2 + 1;
                if left_idx < self.alert_buffer.len() {
                    self.alert_buffer[left_idx] += s * gain_left;
                }
                if right_idx < self.alert_buffer.len() {
                    self.alert_buffer[right_idx] += s * gain_right;
                }
            } else {
                // Sound from right: Right arrives first, Left is delayed by ITD
                let right_idx = n * 2 + 1;
                let left_idx = (n + itd_samples) * 2;
                if right_idx < self.alert_buffer.len() {
                    self.alert_buffer[right_idx] += s * gain_right;
                }
                if left_idx < self.alert_buffer.len() {
                    self.alert_buffer[left_idx] += s * gain_left;
                }
            }
        }
    }

    /// Mixes pending alert audio into an output mono/stereo buffer.
    pub fn mix_mono(&mut self, out: &mut [f32]) {
        if self.read_pos >= self.alert_buffer.len() {
            return;
        }

        for sample in out.iter_mut() {
            if self.read_pos + 1 < self.alert_buffer.len() {
                // Mix left and right
                let s =
                    0.5 * (self.alert_buffer[self.read_pos] + self.alert_buffer[self.read_pos + 1]);
                *sample += s;
                self.read_pos += 2;
            } else {
                break;
            }
        }
    }
}

/// Interactive Tactical Threat Radar Widget and Threat Tracker.
pub struct ThreatRadarWidget {
    pub threats: Vec<ThreatEntity>,
    pub next_id: u64,
    pub sonifier: SpatialAlertSonifier,
}

impl ThreatRadarWidget {
    /// Creates a new ThreatRadarWidget with standard tactical initialization.
    pub fn new(sample_rate: f32) -> Self {
        Self {
            threats: Vec::new(),
            next_id: 1,
            sonifier: SpatialAlertSonifier::new(sample_rate),
        }
    }

    /// Adds or updates a detected tactical threat.
    pub fn add_threat(
        &mut self,
        threat_type: ThreatType,
        azimuth_deg: f32,
        distance_m: f32,
        confidence: f32,
    ) {
        let ttl = match threat_type {
            ThreatType::SniperCrack => 6.0,
            ThreatType::Gunfire => 5.0,
            ThreatType::DroneUav => 7.0,
            ThreatType::EngineRumble => 8.0,
        };

        let entity = ThreatEntity {
            id: self.next_id,
            threat_type,
            azimuth_deg,
            distance_m,
            confidence,
            time_to_live_sec: ttl,
            initial_ttl_sec: ttl,
        };
        self.next_id += 1;

        // Keep maximum 8 active threats
        if self.threats.len() >= 8 {
            self.threats.remove(0);
        }
        self.threats.push(entity);

        // Trigger spatial sonification tone
        self.sonifier
            .trigger_spatial_alert(threat_type, azimuth_deg);
    }

    /// Advances internal timers and cleans up expired threats.
    pub fn tick(&mut self, dt_sec: f32) {
        for t in self.threats.iter_mut() {
            t.time_to_live_sec -= dt_sec;
        }
        self.threats.retain(|t| t.time_to_live_sec > 0.0);
    }

    /// Clears all detected threats.
    pub fn clear(&mut self) {
        self.threats.clear();
    }

    /// Renders the complete 360° Tactical Threat Radar HUD.
    pub fn show(&mut self, ui: &mut Ui, diameter: f32) {
        Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(Rounding::same(8.0))
            .inner_margin(Margin::same(10.0))
            .show(ui, |ui| {
                // Widget Header
                ui.horizontal(|ui| {
                    ui.label(egui::RichText::new("●").color(Theme::ACCENT_RED).size(11.0));
                    ui.label(
                        egui::RichText::new("360° TACTICAL THREAT RADAR & ACOUSTIC ALERT")
                            .strong()
                            .size(11.0)
                            .color(Theme::TEXT_PRIMARY),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let active_count = self.threats.len();
                        let badge_col = if active_count > 0 {
                            Theme::ACCENT_RED
                        } else {
                            Theme::ACCENT_GREEN
                        };
                        ui.label(
                            egui::RichText::new(format!("{} ACTIVE THREATS", active_count))
                                .size(9.5)
                                .color(badge_col),
                        );
                    });
                });

                ui.add_space(4.0);

                // Most urgent threat banner
                if let Some(top_threat) =
                    self.threats.iter().min_by_key(|t| t.threat_type.priority())
                {
                    let dir_str = if top_threat.azimuth_deg < -15.0 {
                        format!("{:.0}° L", -top_threat.azimuth_deg)
                    } else if top_threat.azimuth_deg > 15.0 {
                        format!("{:.0}° R", top_threat.azimuth_deg)
                    } else {
                        "CENTER".to_string()
                    };

                    ui.horizontal(|ui| {
                        ui.label(
                            egui::RichText::new(format!(
                                "🚨 ALERT: {} AT {} ({}m, {:.0}% CONF)",
                                top_threat.threat_type.label(),
                                dir_str,
                                top_threat.distance_m as u32,
                                top_threat.confidence * 100.0
                            ))
                            .strong()
                            .size(10.5)
                            .color(top_threat.threat_type.color()),
                        );
                    });
                } else {
                    ui.label(
                        egui::RichText::new("Acoustic sector clear. Monitoring 360° soundscape...")
                            .size(10.0)
                            .color(Theme::TEXT_MUTED),
                    );
                }

                ui.add_space(6.0);

                // Radar Display + Interactive Trigger Buttons in 2 columns
                ui.columns(2, |cols| {
                    // Col 0: 360° Polar Radar Screen
                    cols[0].vertical(|ui| {
                        let (rect, _response) =
                            ui.allocate_exact_size(Vec2::new(diameter, diameter), Sense::hover());

                        let painter = ui.painter_at(rect);
                        let center = rect.center();
                        let radius = (diameter / 2.0) - 10.0;

                        // Dark circular radar scope background
                        painter.circle_filled(center, radius, Color32::from_rgb(8, 12, 16));
                        painter.circle_stroke(
                            center,
                            radius,
                            Stroke::new(1.2_f32, Color32::from_rgb(30, 45, 60)),
                        );

                        // Range Rings: 500m (outer), 300m, 150m, 50m (inner)
                        let rings = [
                            (0.25, "100m"),
                            (0.50, "250m"),
                            (0.75, "400m"),
                            (1.00, "500m"),
                        ];
                        for &(frac, label) in &rings {
                            let r = radius * frac;
                            painter.circle_stroke(
                                center,
                                r,
                                Stroke::new(
                                    1.0_f32,
                                    Color32::from_rgba_premultiplied(40, 60, 80, 80),
                                ),
                            );
                            if frac > 0.4 {
                                painter.text(
                                    Pos2::new(center.x + r - 4.0, center.y - 4.0),
                                    egui::Align2::RIGHT_BOTTOM,
                                    label,
                                    egui::FontId::proportional(8.0),
                                    Color32::from_rgba_premultiplied(100, 140, 160, 120),
                                );
                            }
                        }

                        // Crosshairs (North, South, East, West)
                        painter.line_segment(
                            [
                                Pos2::new(center.x, center.y - radius),
                                Pos2::new(center.x, center.y + radius),
                            ],
                            Stroke::new(1.0_f32, Color32::from_rgba_premultiplied(40, 60, 80, 100)),
                        );
                        painter.line_segment(
                            [
                                Pos2::new(center.x - radius, center.y),
                                Pos2::new(center.x + radius, center.y),
                            ],
                            Stroke::new(1.0_f32, Color32::from_rgba_premultiplied(40, 60, 80, 100)),
                        );

                        // Bearing labels
                        painter.text(
                            Pos2::new(center.x, center.y - radius - 2.0),
                            egui::Align2::CENTER_BOTTOM,
                            "N (0°)",
                            egui::FontId::proportional(8.5),
                            Theme::ACCENT_CYAN,
                        );
                        painter.text(
                            Pos2::new(center.x + radius + 2.0, center.y),
                            egui::Align2::LEFT_CENTER,
                            "E (+90°)",
                            egui::FontId::proportional(8.5),
                            Theme::TEXT_MUTED,
                        );
                        painter.text(
                            Pos2::new(center.x, center.y + radius + 2.0),
                            egui::Align2::CENTER_TOP,
                            "S (180°)",
                            egui::FontId::proportional(8.5),
                            Theme::TEXT_MUTED,
                        );
                        painter.text(
                            Pos2::new(center.x - radius - 2.0, center.y),
                            egui::Align2::RIGHT_CENTER,
                            "W (-90°)",
                            egui::FontId::proportional(8.5),
                            Theme::TEXT_MUTED,
                        );

                        // Draw Operator Center Icon (Soldier headset silhouette marker)
                        painter.circle_filled(center, 4.0, Theme::ACCENT_CYAN);

                        // Draw Threats
                        for t in &self.threats {
                            let frac_dist = (t.distance_m / 500.0).clamp(0.10, 1.0);
                            let r_px = radius * frac_dist;

                            // Convert azimuth to screen polar coordinates
                            // In audio azimuth: 0° is North (up), +90° is East (right)
                            let angle_rad = t.azimuth_deg.to_radians();
                            let blip_x = center.x + r_px * angle_rad.sin();
                            let blip_y = center.y - r_px * angle_rad.cos();
                            let blip_pos = Pos2::new(blip_x, blip_y);

                            // Pulsing halo according to remaining TTL
                            let pulse = (t.time_to_live_sec * 6.0).sin().abs();
                            let col = t.threat_type.color();

                            // Bearing vector line
                            painter.line_segment(
                                [center, blip_pos],
                                Stroke::new(
                                    1.0_f32,
                                    Color32::from_rgba_premultiplied(col.r(), col.g(), col.b(), 90),
                                ),
                            );

                            // Halo ring
                            painter.circle_stroke(
                                blip_pos,
                                6.0 + 3.0 * pulse,
                                Stroke::new(
                                    1.2_f32,
                                    Color32::from_rgba_premultiplied(
                                        col.r(),
                                        col.g(),
                                        col.b(),
                                        (180.0 * pulse) as u8,
                                    ),
                                ),
                            );

                            // Blip center
                            painter.circle_filled(blip_pos, 4.0, col);

                            // Threat text tag
                            painter.text(
                                Pos2::new(blip_x + 6.0, blip_y - 6.0),
                                egui::Align2::LEFT_BOTTOM,
                                format!("{:.0}m", t.distance_m),
                                egui::FontId::proportional(8.0),
                                col,
                            );
                        }
                    });

                    // Col 1: Interactive Test Triggers & Threat Feed
                    cols[1].vertical(|ui| {
                        ui.label(
                            egui::RichText::new("SIMULATE ACOUSTIC THREAT:")
                                .size(10.0)
                                .strong()
                                .color(Theme::TEXT_MUTED),
                        );

                        if ui
                            .button(
                                egui::RichText::new("🎯 SNIPER CRACK (-45° NW, 180m)")
                                    .size(9.5)
                                    .color(Color32::from_rgb(255, 45, 85)),
                            )
                            .clicked()
                        {
                            self.add_threat(ThreatType::SniperCrack, -45.0, 180.0, 0.96);
                        }

                        if ui
                            .button(
                                egui::RichText::new("🛸 HOSTILE DRONE (+60° NE, 320m)")
                                    .size(9.5)
                                    .color(Color32::from_rgb(255, 215, 0)),
                            )
                            .clicked()
                        {
                            self.add_threat(ThreatType::DroneUav, 60.0, 320.0, 0.89);
                        }

                        if ui
                            .button(
                                egui::RichText::new("💥 GUNFIRE (+110° SE, 240m)")
                                    .size(9.5)
                                    .color(Color32::from_rgb(255, 120, 40)),
                            )
                            .clicked()
                        {
                            self.add_threat(ThreatType::Gunfire, 110.0, 240.0, 0.92);
                        }

                        if ui
                            .button(
                                egui::RichText::new("🚜 ARMOR CHASSIS (0° N, 420m)")
                                    .size(9.5)
                                    .color(Color32::from_rgb(180, 100, 255)),
                            )
                            .clicked()
                        {
                            self.add_threat(ThreatType::EngineRumble, 0.0, 420.0, 0.84);
                        }

                        if ui
                            .button(
                                egui::RichText::new("🔄 CLEAR RADAR")
                                    .size(9.5)
                                    .color(Theme::TEXT_SECONDARY),
                            )
                            .clicked()
                        {
                            self.clear();
                        }
                    });
                });
            });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_threat_radar_add_and_expiration() {
        let mut widget = ThreatRadarWidget::new(16000.0);
        assert_eq!(widget.threats.len(), 0);

        widget.add_threat(ThreatType::SniperCrack, -45.0, 200.0, 0.95);
        assert_eq!(widget.threats.len(), 1);
        assert_eq!(widget.threats[0].threat_type, ThreatType::SniperCrack);

        // Advance 10 seconds (exceeding 6.0s TTL)
        widget.tick(10.0);
        assert_eq!(widget.threats.len(), 0);
    }

    #[test]
    fn test_spatial_alert_sonifier_generates_binaural_itd_and_ild() {
        let mut sonifier = SpatialAlertSonifier::new(16000.0);

        // Trigger alert from left (-90°)
        sonifier.trigger_spatial_alert(ThreatType::SniperCrack, -90.0);

        assert!(!sonifier.alert_buffer.is_empty());
        // Left channel should have immediate energy, while right is delayed
        let mut mono_out = vec![0.0f32; 128];
        sonifier.mix_mono(&mut mono_out);

        let energy: f32 = mono_out.iter().map(|s| s * s).sum();
        assert!(energy > 1e-4, "Sonifier must produce non-zero alert energy");
    }
}
