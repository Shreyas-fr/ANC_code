//! Tactical Squad Mesh & Spatial Audio Consensus Radar HUD Widget.
//!
//! Developed for SIH 26052 Dismounted Soldier Situational Awareness.
//!
//! Visualizes real-time tactical squad mesh topology and spatial audio consensus:
//! - 360° Polar situational awareness radar displaying squad teammates.
//! - Relative azimuth, distance, and elevation bearings.
//! - Ad-hoc mesh hop count and RF link RSSI (dBm).
//! - 3D Binaural spatialization parameters (ITD delay & ILD level delta).

use super::theme::Theme;
pub use anc_rust::network::mesh::{Position3D, SquadMemberNode, MAX_SQUAD_MEMBERS};
use egui::{Color32, Frame, Margin, Pos2, Rounding, Sense, Stroke, Ui, Vec2};
use std::f32::consts::PI;

/// Interactive Squad Mesh & Spatial Audio Consensus Widget.
#[derive(Debug, Clone)]
pub struct MeshRadarWidget {
    pub squad: [SquadMemberNode; MAX_SQUAD_MEMBERS],
    pub local_callsign: &'static str,
    pub max_range_m: f32,
}

impl Default for MeshRadarWidget {
    fn default() -> Self {
        let mut widget = Self {
            squad: [SquadMemberNode::default(); MAX_SQUAD_MEMBERS],
            local_callsign: "WARRIOR-ALPHA",
            max_range_m: 100.0,
        };

        // Initialize with default squad members for tactical preview
        widget.squad[0] = SquadMemberNode {
            node_id: 102,
            position: Position3D {
                x_m: 25.0,
                y_m: 40.0,
                z_m: 0.0,
            },
            relative_azimuth_deg: 32.0,
            relative_elevation_deg: 0.0,
            distance_m: 47.1,
            last_rssi_dbm: -68,
            hop_distance: 1,
            active: true,
        };
        widget.squad[1] = SquadMemberNode {
            node_id: 103,
            position: Position3D {
                x_m: -35.0,
                y_m: 20.0,
                z_m: 2.0,
            },
            relative_azimuth_deg: -60.2,
            relative_elevation_deg: 2.5,
            distance_m: 40.3,
            last_rssi_dbm: -74,
            hop_distance: 1,
            active: true,
        };
        widget.squad[2] = SquadMemberNode {
            node_id: 104,
            position: Position3D {
                x_m: 10.0,
                y_m: -65.0,
                z_m: -1.0,
            },
            relative_azimuth_deg: 171.2,
            relative_elevation_deg: -0.9,
            distance_m: 65.8,
            last_rssi_dbm: -82,
            hop_distance: 2,
            active: true,
        };

        widget
    }
}

impl MeshRadarWidget {
    pub fn new() -> Self {
        Self::default()
    }

    /// Updates internal squad table snapshot.
    pub fn update(&mut self, squad: [SquadMemberNode; MAX_SQUAD_MEMBERS]) {
        self.squad = squad;
    }

    /// Renders the Squad Mesh Radar UI.
    pub fn render(&mut self, ui: &mut Ui) {
        Frame::none()
            .fill(Theme::BG_CARD)
            .rounding(Rounding::same(8.0))
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .inner_margin(Margin::same(12.0))
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("SQUAD MESH & 3D SPATIAL CONSENSUS")
                            .size(13.0)
                            .strong()
                            .color(Theme::ACCENT_CYAN),
                    );
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let active_count = self.squad.iter().filter(|m| m.active).count();
                        ui.label(
                            egui::RichText::new(format!("TEAMMATES: {} ACTIVE", active_count))
                                .size(11.0)
                                .color(Theme::TEXT_MUTED),
                        );
                    });
                });

                ui.add_space(8.0);

                // Render circular radar scope
                let radar_size = Vec2::new(ui.available_width(), 160.0);
                let (rect, _resp) = ui.allocate_exact_size(radar_size, Sense::hover());
                let painter = ui.painter_at(rect);

                let center = rect.center();
                let radius = (rect.height() / 2.0) - 10.0;

                // Scope background
                painter.circle_filled(center, radius, Color32::from_rgb(10, 14, 20));
                painter.circle_stroke(
                    center,
                    radius,
                    Stroke::new(1.5_f32, Color32::from_rgb(26, 42, 58)),
                );

                // Concentric range rings
                for frac in [0.25, 0.50, 0.75, 1.0] {
                    let r = radius * frac;
                    painter.circle_stroke(
                        center,
                        r,
                        Stroke::new(0.8_f32, Color32::from_rgba_unmultiplied(40, 65, 88, 120)),
                    );
                }

                // Crosshair axis lines
                painter.line_segment(
                    [
                        Pos2::new(center.x - radius, center.y),
                        Pos2::new(center.x + radius, center.y),
                    ],
                    Stroke::new(0.8_f32, Color32::from_rgba_unmultiplied(40, 65, 88, 140)),
                );
                painter.line_segment(
                    [
                        Pos2::new(center.x, center.y - radius),
                        Pos2::new(center.x, center.y + radius),
                    ],
                    Stroke::new(0.8_f32, Color32::from_rgba_unmultiplied(40, 65, 88, 140)),
                );

                // Local soldier marker in center
                painter.circle_filled(center, 4.0, Theme::ACCENT_GREEN);
                painter.circle_stroke(center, 7.0, Stroke::new(1.0_f32, Theme::ACCENT_GREEN));

                // Plot squad teammates
                for m in &self.squad {
                    if !m.active {
                        continue;
                    }

                    let r_norm = (m.distance_m / self.max_range_m).clamp(0.05, 1.0) * radius;
                    let angle_rad = m.relative_azimuth_deg.to_radians() - (PI / 2.0); // 0 deg = top (North)

                    let px = center.x + r_norm * angle_rad.cos();
                    let py = center.y + r_norm * angle_rad.sin();
                    let node_pos = Pos2::new(px, py);

                    // Marker color based on hop distance
                    let (color, ring_color) = if m.hop_distance == 1 {
                        (Theme::ACCENT_CYAN, Color32::from_rgb(0, 150, 220))
                    } else {
                        (Theme::ACCENT_AMBER, Color32::from_rgb(220, 140, 0))
                    };

                    painter.circle_filled(node_pos, 4.5, color);
                    painter.circle_stroke(node_pos, 8.0, Stroke::new(1.0_f32, ring_color));

                    // Node label
                    let label = format!("ID:{}\n{}m", m.node_id, m.distance_m.round());
                    painter.text(
                        Pos2::new(px + 10.0, py - 6.0),
                        egui::Align2::LEFT_CENTER,
                        label,
                        egui::FontId::proportional(9.0),
                        Theme::TEXT_PRIMARY,
                    );
                }

                ui.add_space(8.0);

                // Squad telemetry cards
                ui.horizontal_wrapped(|ui| {
                    for m in &self.squad {
                        if !m.active {
                            continue;
                        }

                        let card_rect = ui.allocate_ui(Vec2::new(140.0, 48.0), |ui| {
                            Frame::none()
                                .fill(Color32::from_rgb(14, 20, 28))
                                .rounding(Rounding::same(4.0))
                                .stroke(Stroke::new(1.0_f32, Color32::from_rgb(28, 40, 56)))
                                .inner_margin(Margin::same(6.0))
                                .show(ui, |ui| {
                                    ui.horizontal(|ui| {
                                        ui.label(
                                            egui::RichText::new(format!("NODE {}", m.node_id))
                                                .size(10.0)
                                                .strong()
                                                .color(Theme::ACCENT_CYAN),
                                        );
                                        ui.with_layout(
                                            egui::Layout::right_to_left(egui::Align::Center),
                                            |ui| {
                                                ui.label(
                                                    egui::RichText::new(format!(
                                                        "{}H",
                                                        m.hop_distance
                                                    ))
                                                    .size(9.0)
                                                    .color(Theme::TEXT_MUTED),
                                                );
                                            },
                                        );
                                    });
                                    ui.label(
                                        egui::RichText::new(format!(
                                            "AZ: {:+.1}° | RSSI: {}dBm",
                                            m.relative_azimuth_deg, m.last_rssi_dbm
                                        ))
                                        .size(9.0)
                                        .color(Theme::TEXT_MUTED),
                                    );
                                });
                        });
                        let _ = card_rect;
                    }
                });
            });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mesh_radar_initialization() {
        let radar = MeshRadarWidget::new();
        let active = radar.squad.iter().filter(|m| m.active).count();
        assert_eq!(active, 3);
    }

    #[test]
    fn test_mesh_radar_headless_context() {
        let ctx = egui::Context::default();
        let mut radar = MeshRadarWidget::new();

        let _ = ctx.run(Default::default(), |ctx| {
            egui::CentralPanel::default().show(ctx, |ui| {
                radar.render(ui);
            });
        });
    }
}
