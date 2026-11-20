//! 2D Circular Tactical DOA Radar & Headset Compass Widget with CDR Indicator.
//!
//! Visualizes:
//! - Real-time acoustic arrival angle theta(t) from the GCC-PHAT / Kalman tracker
//! - Multi-Microphone Coherence-to-Diffuse Ratio (CDR) & Spatial Coherence
//! - 30mm microphone array baseline markers (M1 & M2)
//! - Acoustic field-of-view (+/- 45 degrees broadside)
//! - Diffuse field halo ring (visualizing ambient diffuse noise intensity)
//! - Spatial MVDR interference null vectors (+/- 90 degrees)

use super::theme::Theme;
use egui::{Color32, Frame, Margin, Pos2, Rounding, Sense, Stroke, Ui, Vec2};
use std::f32::consts::PI;

/// 2D Tactical DOA & Spatial Coherence Radar Widget.
pub struct TacticalRadarWidget;

impl TacticalRadarWidget {
    /// Renders the 2D Circular Radar widget with default CDR parameters (for compatibility).
    pub fn show(
        ui: &mut Ui,
        talker_angle_deg: f32,
        confidence: f32,
        is_speech_active: bool,
        interference_nulls_deg: &[f32],
        diameter: f32,
    ) -> Option<f32> {
        Self::show_with_cdr(
            ui,
            talker_angle_deg,
            confidence,
            is_speech_active,
            12.5,
            0.88,
            interference_nulls_deg,
            diameter,
        )
    }

    /// Renders the 2D Circular Radar widget with live Coherence-to-Diffuse Ratio (CDR) telemetry.
    ///
    /// - `talker_angle_deg`: Live tracked talker DOA angle theta(t) in degrees (-45.0 to +45.0).
    /// - `confidence`: DOA tracking confidence metric [0.0, 1.0].
    /// - `is_speech_active`: Whether speech presence is currently active.
    /// - `mean_cdr_db`: Live Coherence-to-Diffuse Ratio in decibels (e.g. +14.2 dB direct vs -3.5 dB diffuse).
    /// - `spatial_coherence`: Magnitude coherence [0.0, 1.0].
    /// - `interference_nulls_deg`: Angular positions of spatial interference nulls (e.g. +/- 90.0 deg).
    /// - `diameter`: Widget pixel size (e.g. 175.0 px).
    ///
    /// Returns `Some(angle_deg)` if user clicked/dragged to manually test or override steering angle.
    #[allow(clippy::too_many_arguments)]
    pub fn show_with_cdr(
        ui: &mut Ui,
        talker_angle_deg: f32,
        confidence: f32,
        is_speech_active: bool,
        mean_cdr_db: f32,
        spatial_coherence: f32,
        interference_nulls_deg: &[f32],
        diameter: f32,
    ) -> Option<f32> {
        let mut user_override_deg = None;

        Frame::none()
            .fill(Theme::BG_CARD)
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .rounding(Rounding::same(8.0))
            .inner_margin(Margin::same(10.0))
            .show(ui, |ui| {
                // Widget Header
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("●")
                            .color(Theme::ACCENT_CYAN)
                            .size(11.0),
                    );
                    ui.label(
                        egui::RichText::new("2D TACTICAL DOA & CDR RADAR")
                            .strong()
                            .size(11.0)
                            .color(Theme::TEXT_PRIMARY),
                    );
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let conf_color = if confidence > 0.70 {
                            Theme::ACCENT_GREEN
                        } else if confidence > 0.40 {
                            Theme::ACCENT_AMBER
                        } else {
                            Theme::TEXT_MUTED
                        };
                        ui.label(
                            egui::RichText::new(format!("{:.0}% CONF", confidence * 100.0))
                                .size(9.5)
                                .color(conf_color),
                        );
                        ui.label(egui::RichText::new("·").size(10.0).color(Theme::TEXT_MUTED));
                        let coh_color = if spatial_coherence > 0.75 {
                            Theme::ACCENT_CYAN
                        } else if spatial_coherence > 0.45 {
                            Theme::ACCENT_AMBER
                        } else {
                            Theme::ACCENT_VIOLET
                        };
                        ui.label(
                            egui::RichText::new(format!("{:.0}% COH", spatial_coherence * 100.0))
                                .size(9.5)
                                .color(coh_color),
                        );
                    });
                });

                ui.add_space(3.0);

                // Allocate circular canvas
                let canvas_size = Vec2::new(diameter, diameter);
                let (rect, response) = ui.allocate_exact_size(canvas_size, Sense::click_and_drag());
                let painter = ui.painter();
                let center = rect.center();
                let radius = (diameter * 0.5) - 14.0;

                // Handle user interaction (manual angle steering / test)
                if response.clicked() || response.dragged() {
                    if let Some(mouse_pos) = response.interact_pointer_pos() {
                        let dx = mouse_pos.x - center.x;
                        let dy = center.y - mouse_pos.y; // Invert Y so up is positive
                        let click_angle_deg = dx.atan2(dy) * 180.0 / PI;
                        user_override_deg = Some(click_angle_deg.clamp(-45.0, 45.0));
                    }
                }

                // 1. Radar Void Background Disc
                painter.circle_filled(center, radius, Color32::from_rgb(10, 16, 26));

                // 2. Diffuse Field Halo Ring:
                // Visualizes diffuse sound intensity (high diffuse noise illuminates a glowing halo)
                let diffuse_ratio = 1.0 / (1.0 + 10.0f32.powf(mean_cdr_db / 10.0).max(1e-3));
                if diffuse_ratio > 0.20 {
                    let halo_alpha = ((diffuse_ratio - 0.20) * 180.0).clamp(0.0, 110.0) as u8;
                    painter.circle_stroke(
                        center,
                        radius * 0.82,
                        Stroke::new(
                            3.0_f32,
                            Color32::from_rgba_premultiplied(180, 80, 220, halo_alpha),
                        ),
                    );
                }

                // 3. Concentric Range Rings (33%, 66%, 100%)
                for &frac in &[0.33_f32, 0.66_f32, 1.00_f32] {
                    painter.circle_stroke(
                        center,
                        radius * frac,
                        Stroke::new(1.0_f32, Color32::from_rgba_premultiplied(40, 65, 95, 80)),
                    );
                }

                // 4. Acoustic Field of View (+/- 45 deg sector)
                let fov_rad = 45.0_f32 * PI / 180.0;
                let p_left_fov = Pos2::new(
                    center.x - radius * fov_rad.sin(),
                    center.y - radius * fov_rad.cos(),
                );
                let p_right_fov = Pos2::new(
                    center.x + radius * fov_rad.sin(),
                    center.y - radius * fov_rad.cos(),
                );

                painter.line_segment(
                    [center, p_left_fov],
                    Stroke::new(1.0_f32, Color32::from_rgba_premultiplied(60, 110, 160, 100)),
                );
                painter.line_segment(
                    [center, p_right_fov],
                    Stroke::new(1.0_f32, Color32::from_rgba_premultiplied(60, 110, 160, 100)),
                );

                // 5. Broadside Centerline (0 deg)
                painter.line_segment(
                    [center, Pos2::new(center.x, center.y - radius)],
                    Stroke::new(1.0_f32, Color32::from_rgba_premultiplied(0, 240, 255, 90)),
                );

                // 6. 30mm Microphone Array Baseline Axis (Horizontal Line)
                painter.line_segment(
                    [
                        Pos2::new(center.x - radius * 0.85, center.y),
                        Pos2::new(center.x + radius * 0.85, center.y),
                    ],
                    Stroke::new(1.0_f32, Color32::from_rgba_premultiplied(50, 75, 100, 120)),
                );

                // Mic 1 (Primary - Left) & Mic 2 (Reference - Right) Physical Badges
                let mic_dist_px = radius * 0.38;
                let p_mic1 = Pos2::new(center.x - mic_dist_px, center.y);
                let p_mic2 = Pos2::new(center.x + mic_dist_px, center.y);

                painter.circle_filled(p_mic1, 3.5, Theme::ACCENT_CYAN);
                painter.circle_filled(p_mic2, 3.5, Theme::ACCENT_AMBER);

                painter.text(
                    Pos2::new(p_mic1.x, p_mic1.y + 7.0),
                    egui::Align2::CENTER_TOP,
                    "M1",
                    egui::FontId::monospace(8.0),
                    Theme::ACCENT_CYAN,
                );
                painter.text(
                    Pos2::new(p_mic2.x, p_mic2.y + 7.0),
                    egui::Align2::CENTER_TOP,
                    "M2",
                    egui::FontId::monospace(8.0),
                    Theme::ACCENT_AMBER,
                );

                // 7. Perimeter Degree Ticks and Labels (-45, -30, -15, 0, +15, +30, +45)
                for deg in [-45, -30, -15, 0, 15, 30, 45] {
                    let rad = (deg as f32) * PI / 180.0;
                    let p_outer =
                        Pos2::new(center.x + radius * rad.sin(), center.y - radius * rad.cos());
                    let p_inner = Pos2::new(
                        center.x + (radius - 5.0) * rad.sin(),
                        center.y - (radius - 5.0) * rad.cos(),
                    );
                    painter.line_segment(
                        [p_inner, p_outer],
                        Stroke::new(
                            1.0_f32,
                            Color32::from_rgba_premultiplied(100, 150, 190, 140),
                        ),
                    );

                    if deg % 30 == 0 || deg == 0 {
                        let p_text = Pos2::new(
                            center.x + (radius + 8.0) * rad.sin(),
                            center.y - (radius + 8.0) * rad.cos(),
                        );
                        let label = if deg == 0 {
                            "0°"
                        } else if deg > 0 {
                            "+30°"
                        } else {
                            "-30°"
                        };
                        painter.text(
                            p_text,
                            egui::Align2::CENTER_CENTER,
                            label,
                            egui::FontId::proportional(8.5),
                            Theme::TEXT_MUTED,
                        );
                    }
                }

                // 8. Spatial Interference Null Vectors (Amber/Red glowing vectors)
                for &null_deg in interference_nulls_deg {
                    let null_rad = null_deg * PI / 180.0;
                    let p_null = Pos2::new(
                        center.x + radius * null_rad.sin(),
                        center.y - radius * null_rad.cos(),
                    );
                    painter.line_segment(
                        [center, p_null],
                        Stroke::new(1.2_f32, Color32::from_rgba_premultiplied(255, 75, 75, 140)),
                    );
                    painter.circle_filled(p_null, 2.5, Theme::ACCENT_RED);
                }

                // 9. Live Tracked Talker Arrival Vector theta(t) (Glowing Cyan Reticle)
                let clamped_angle = talker_angle_deg.clamp(-45.0, 45.0);
                let talker_rad = clamped_angle * PI / 180.0;
                let target_pos = Pos2::new(
                    center.x + radius * talker_rad.sin(),
                    center.y - radius * talker_rad.cos(),
                );

                let (beam_color, glow_color, beam_thickness) = if is_speech_active {
                    (
                        Theme::ACCENT_CYAN,
                        Color32::from_rgba_premultiplied(0, 240, 255, 70),
                        2.2_f32,
                    )
                } else {
                    (
                        Color32::from_rgb(40, 140, 170),
                        Color32::from_rgba_premultiplied(40, 140, 170, 40),
                        1.4_f32,
                    )
                };

                // Glow beam aura
                painter.line_segment(
                    [center, target_pos],
                    Stroke::new(beam_thickness + 3.0, glow_color),
                );
                // Core beam reticle
                painter.line_segment(
                    [center, target_pos],
                    Stroke::new(beam_thickness, beam_color),
                );

                // Target Talker Blip Marker at the perimeter
                painter.circle_filled(target_pos, 4.0, beam_color);
                painter.circle_stroke(target_pos, 7.0, Stroke::new(1.2_f32, beam_color));

                // Readout HUD Sub-bar
                ui.add_space(4.0);
                ui.horizontal(|ui| {
                    let slip_label = if clamped_angle.abs() < 4.0 {
                        "BROADSIDE"
                    } else if clamped_angle > 0.0 {
                        "SLIP RIGHT"
                    } else {
                        "SLIP LEFT"
                    };

                    ui.label(
                        egui::RichText::new(format!("DOA: {:+.1}°", clamped_angle))
                            .size(10.5)
                            .strong()
                            .color(if is_speech_active {
                                Theme::ACCENT_CYAN
                            } else {
                                Theme::TEXT_PRIMARY
                            }),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        ui.label(egui::RichText::new(slip_label).size(9.5).color(
                            if clamped_angle.abs() >= 10.0 {
                                Theme::ACCENT_AMBER
                            } else {
                                Theme::TEXT_MUTED
                            },
                        ));
                    });
                });

                // Line 2: Coherence-to-Diffuse Ratio (CDR) Status Indicator
                ui.horizontal(|ui| {
                    let (cdr_text, cdr_color) = if mean_cdr_db >= 6.0 {
                        (
                            format!("CDR: {:+.1} dB (DIRECT)", mean_cdr_db),
                            Theme::ACCENT_CYAN,
                        )
                    } else if mean_cdr_db >= 0.0 {
                        (
                            format!("CDR: {:+.1} dB (MODERATE)", mean_cdr_db),
                            Theme::ACCENT_AMBER,
                        )
                    } else {
                        (
                            format!("CDR: {:+.1} dB (DIFFUSE)", mean_cdr_db),
                            Theme::ACCENT_VIOLET,
                        )
                    };

                    ui.label(
                        egui::RichText::new(cdr_text)
                            .size(10.0)
                            .strong()
                            .color(cdr_color),
                    );

                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let diff_pct = diffuse_ratio * 100.0;
                        ui.label(
                            egui::RichText::new(format!("DIFF: {:.0}%", diff_pct))
                                .size(9.5)
                                .color(Theme::TEXT_MUTED),
                        );
                    });
                });
            });

        user_override_deg
    }
}
