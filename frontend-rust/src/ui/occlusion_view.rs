//! Active Occlusion Suppression & Earcup Seal Telemetry Widget.
//!
//! Developed for SIH 26052 Tactical Headsets & Combat Helmet Earcup Modules.
//!
//! Visualizes real-time ear-canal acoustic overpressure suppression (Occlusion Effect)
//! and secondary path acoustic seal integrity:
//! - Active bone VAD speech detection indicator.
//! - Occlusion boom reduction meter (dB in 100-500 Hz resonance band).
//! - Dual-sensor power telemetry (Bone vibration vs In-Ear acoustic mic).
//! - Earcup acoustic seal integrity & seal leak warning flag.

use super::theme::Theme;
pub use anc_rust::dsp::occlusion::OcclusionTelemetry;
pub use anc_rust::dsp::secondary_path::SecondaryPathTelemetry;
use egui::{Color32, Frame, Margin, Rect, Rounding, Sense, Stroke, Ui, Vec2};

/// Interactive Occlusion Effect and Seal Health HUD Widget.
#[derive(Debug, Clone)]
pub struct OcclusionWidget {
    pub occlusion: OcclusionTelemetry,
    pub secondary: SecondaryPathTelemetry,
}

impl Default for OcclusionWidget {
    fn default() -> Self {
        Self {
            occlusion: OcclusionTelemetry {
                soldier_speaking: false,
                boom_reduction_db: 14.5,
                bone_power_dbfs: -42.0,
                in_ear_power_dbfs: -56.5,
                adaptation_factor: 0.98,
            },
            secondary: SecondaryPathTelemetry {
                seal_integrity: 0.98,
                leak_warning: false,
                secondary_gain_db: -2.4,
                convergence_error: 0.012,
                impulse_preview: [0.0; 16],
                probe_power_dbfs: -52.0,
            },
        }
    }
}

impl OcclusionWidget {
    pub fn new() -> Self {
        Self::default()
    }

    /// Updates internal occlusion and secondary path telemetry snapshots.
    pub fn update(&mut self, occ: OcclusionTelemetry, sec: SecondaryPathTelemetry) {
        self.occlusion = occ;
        self.secondary = sec;
    }

    /// Renders the Occlusion & Seal Health HUD Widget.
    pub fn render(&mut self, ui: &mut Ui) {
        Frame::none()
            .fill(Theme::BG_CARD)
            .rounding(Rounding::same(8.0))
            .stroke(Stroke::new(1.0_f32, Theme::BORDER_DEFAULT))
            .inner_margin(Margin::same(12.0))
            .show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new("OCCLUSION EFFECT & EARCUP SEAL")
                            .size(13.0)
                            .strong()
                            .color(Theme::ACCENT_CYAN),
                    );
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        let (status_text, status_color) = if self.secondary.leak_warning {
                            ("SEAL LEAK DETECTED", Theme::ACCENT_RED)
                        } else if self.occlusion.soldier_speaking {
                            ("SOLDIER TRANSMITTING", Theme::ACCENT_GREEN)
                        } else {
                            ("HERMETIC SEAL OK", Theme::TEXT_MUTED)
                        };

                        ui.label(
                            egui::RichText::new(status_text)
                                .size(11.0)
                                .strong()
                                .color(status_color),
                        );
                    });
                });

                ui.add_space(8.0);

                // Top row: Occlusion Reduction Meter + Seal Integrity Meter
                ui.columns(2, |cols| {
                    // Left: Boom Reduction Gauge
                    cols[0].vertical(|ui| {
                        ui.label(
                            egui::RichText::new("BOOM REDUCTION (100-500 Hz)")
                                .size(10.0)
                                .color(Theme::TEXT_MUTED),
                        );
                        let bar_size = Vec2::new(ui.available_width(), 16.0);
                        let (rect, _) = ui.allocate_exact_size(bar_size, Sense::hover());
                        let painter = ui.painter_at(rect);

                        painter.rect_filled(
                            rect,
                            Rounding::same(3.0),
                            Color32::from_rgb(18, 24, 32),
                        );
                        let frac = (self.occlusion.boom_reduction_db / 24.0).clamp(0.0, 1.0);
                        let filled_rect = Rect::from_min_max(
                            rect.min,
                            egui::pos2(rect.min.x + rect.width() * frac, rect.max.y),
                        );
                        painter.rect_filled(filled_rect, Rounding::same(3.0), Theme::ACCENT_GREEN);

                        ui.label(
                            egui::RichText::new(format!(
                                "{:.1} dB CANAL ATTENUATION",
                                self.occlusion.boom_reduction_db
                            ))
                            .size(11.0)
                            .strong()
                            .color(Theme::TEXT_PRIMARY),
                        );
                    });

                    // Right: Seal Integrity Meter
                    cols[1].vertical(|ui| {
                        ui.label(
                            egui::RichText::new("EARCUP ACOUSTIC SEAL")
                                .size(10.0)
                                .color(Theme::TEXT_MUTED),
                        );
                        let bar_size = Vec2::new(ui.available_width(), 16.0);
                        let (rect, _) = ui.allocate_exact_size(bar_size, Sense::hover());
                        let painter = ui.painter_at(rect);

                        painter.rect_filled(
                            rect,
                            Rounding::same(3.0),
                            Color32::from_rgb(18, 24, 32),
                        );
                        let frac = self.secondary.seal_integrity.clamp(0.0, 1.0);
                        let filled_rect = Rect::from_min_max(
                            rect.min,
                            egui::pos2(rect.min.x + rect.width() * frac, rect.max.y),
                        );
                        let color = if self.secondary.leak_warning {
                            Theme::ACCENT_RED
                        } else {
                            Theme::ACCENT_CYAN
                        };
                        painter.rect_filled(filled_rect, Rounding::same(3.0), color);

                        ui.label(
                            egui::RichText::new(format!(
                                "{:.0}% INTEGRITY",
                                self.secondary.seal_integrity * 100.0
                            ))
                            .size(11.0)
                            .strong()
                            .color(Theme::TEXT_PRIMARY),
                        );
                    });
                });

                ui.add_space(6.0);

                // Bottom row: Sensor telemetry breakdown
                ui.horizontal(|ui| {
                    ui.label(
                        egui::RichText::new(format!(
                            "BONE SENSOR: {:.1} dBFS | IN-EAR MIC: {:.1} dBFS | PROBE: {:.1} dBFS",
                            self.occlusion.bone_power_dbfs,
                            self.occlusion.in_ear_power_dbfs,
                            self.secondary.probe_power_dbfs
                        ))
                        .size(10.0)
                        .color(Theme::TEXT_MUTED),
                    );
                });
            });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_occlusion_widget_initialization() {
        let widget = OcclusionWidget::new();
        assert!(!widget.secondary.leak_warning);
        assert!(widget.occlusion.boom_reduction_db > 10.0);
    }

    #[test]
    fn test_occlusion_widget_headless_context() {
        let ctx = egui::Context::default();
        let mut widget = OcclusionWidget::new();

        let _ = ctx.run(Default::default(), |ctx| {
            egui::CentralPanel::default().show(ctx, |ui| {
                widget.render(ui);
            });
        });
    }
}
