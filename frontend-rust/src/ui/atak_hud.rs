//! Android Tactical Assault Kit (ATAK) CoT Telemetry HUD Widget.
//!
//! Developed for SIH 26052 Dismounted Soldier C4I Situational Awareness.
//!
//! Visualizes real-time ATAK Cursor-on-Target (CoT) broadcast integration:
//! - Soldier tactical callsign and electronic UID.
//! - Battlefield GPS coordinates (Lat, Lon, Altitude).
//! - Active UDP multicast heartbeat to ATAK mesh (239.2.3.1:6969).
//! - Transmitted ANC health and RASTI intelligibility status.

use super::theme::Theme;
pub use anc_rust::network::atak::{AtakTelemetry, TacticalSoldierProfile, ATAK_MULTICAST_ADDR};
use egui::{Color32, Frame, Margin, Rounding, Stroke, Ui};

/// Interactive ATAK Cursor-on-Target Status Widget.
#[derive(Debug, Clone, Default)]
pub struct AtakWidget {
    pub profile: TacticalSoldierProfile,
    pub telemetry: AtakTelemetry,
}

impl AtakWidget {
    pub fn new() -> Self {
        Self::default()
    }

    /// Updates internal ATAK profile and telemetry.
    pub fn update(&mut self, profile: TacticalSoldierProfile, telem: AtakTelemetry) {
        self.profile = profile;
        self.telemetry = telem;
    }

    /// Renders the ATAK CoT Integration Widget.
    pub fn render(&mut self, ui: &mut Ui) {
        Frame::none()
            .fill(Theme::BG_CARD)
            .rounding(Rounding::same(8.0))
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .inner_margin(Margin::same(12.0))
            .show(ui, |ui| {
                let cs_str = std::str::from_utf8(
                    &self.profile.callsign[0..self.profile.callsign_len as usize],
                )
                .unwrap_or("ALPHA-LEAD");
                let uid_str =
                    std::str::from_utf8(&self.profile.uid[0..self.profile.uid_len as usize])
                        .unwrap_or("ANC-SOLDIER-01");

                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("ATAK CURSOR-ON-TARGET (CoT) BRIDGE")
                            .size(13.0)
                            .strong()
                            .color(Theme::ACCENT_CYAN),
                    );
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let (dot_color, label) = if self.telemetry.broadcast_active {
                            (Theme::ACCENT_GREEN, "MCAST ACTIVE")
                        } else {
                            (Theme::TEXT_MUTED, "STANDBY")
                        };

                        ui.horizontal(|ui| {
                            let (r, _) =
                                ui.allocate_exact_size(egui::vec2(8.0, 8.0), egui::Sense::hover());
                            ui.painter_at(r).circle_filled(r.center(), 3.5, dot_color);
                            ui.label(egui::RichText::new(label).size(11.0).color(dot_color));
                        });
                    });
                });

                ui.add_space(6.0);

                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new(format!("CALLSIGN: {} | UID: {}", cs_str, uid_str))
                            .size(11.0)
                            .strong()
                            .color(Theme::TEXT_PRIMARY),
                    );
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        ui.label(
                            egui::RichText::new(format!("MCAST: {}", ATAK_MULTICAST_ADDR))
                                .size(10.0)
                                .color(Theme::TEXT_MUTED),
                        );
                    });
                });

                ui.add_space(4.0);

                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new(format!(
                            "GPS: {:.5}°N, {:.5}°E | ALT: {:.0}m | CoT PACKETS: {}",
                            self.profile.latitude,
                            self.profile.longitude,
                            self.profile.altitude_m,
                            self.telemetry.total_cot_sent
                        ))
                        .size(10.0)
                        .color(Color32::from_rgb(140, 180, 220)),
                    );
                });
            });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_atak_widget_initialization() {
        let widget = AtakWidget::new();
        assert!(widget.telemetry.broadcast_active);
    }

    #[test]
    fn test_atak_widget_headless_context() {
        let ctx = egui::Context::default();
        let mut widget = AtakWidget::new();

        let _ = ctx.run(Default::default(), |ctx| {
            egui::CentralPanel::default().show(ctx, |ui| {
                widget.render(ui);
            });
        });
    }
}
